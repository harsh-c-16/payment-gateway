"""Order creation and status queries."""

import logging
from datetime import UTC, datetime
from uuid import uuid4

import httpx

from services.orders.errors import ServiceError, not_found
from shared.contracts.common import ErrorCode

logger = logging.getLogger("orders")


def create_order(db, events, namespace, request, context, *, catalog_url, internal_token):
    """Accept a checkout: fetch quote from catalog, create order + saga job atomically."""
    order_id = str(uuid4())
    now = datetime.now(UTC)

    quote = _fetch_quote(catalog_url, request.quote_id, context, internal_token)

    with db.transaction() as tx:
        result = tx.execute(
            """
            INSERT INTO orders
                (namespace, order_id, quote_id, user_id, session_id,
                 total_amount_minor, currency, status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, 'INR', 'PENDING', %s, %s)
            ON CONFLICT (namespace, user_id, quote_id) DO NOTHING
            RETURNING order_id
            """,
            (
                namespace,
                order_id,
                request.quote_id,
                context.user_id,
                request.session_id or context.session_id,
                quote["total_amount_minor"],
                now,
                now,
            ),
        ).fetchone()

        if result is None:
            existing = tx.execute(
                "SELECT order_id, status FROM orders WHERE namespace = %s AND user_id = %s AND quote_id = %s",
                (namespace, context.user_id, request.quote_id),
            ).fetchone()
            return {
                "order_id": existing["order_id"],
                "status": existing["status"],
                "status_url": f"/v1/orders/{existing['order_id']}",
            }

        for line in quote["lines"]:
            tx.execute(
                """
                INSERT INTO order_items
                    (namespace, order_id, sku, quantity, unit_price_minor, line_total_minor, catalog_version)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    namespace,
                    order_id,
                    line["sku"],
                    line["quantity"],
                    line["unit_price_minor"],
                    line["line_total_minor"],
                    line.get("catalog_version", 1),
                ),
            )

        tx.execute(
            """
            INSERT INTO saga_jobs (namespace, order_id, planned_step, next_attempt_at)
            VALUES (%s, %s, 'RESERVE', %s)
            """,
            (namespace, order_id, now),
        )

        events.append(
            tx,
            event_type="ORDER_CREATED",
            payload={
                "order_id": order_id,
                "order_status": "PENDING",
                "total_amount_minor": quote["total_amount_minor"],
                "currency": "INR",
                "created_at": now.isoformat().replace("+00:00", "Z"),
                "user_id": context.user_id,
                "session_id": request.session_id or context.session_id,
                "quote_id": request.quote_id,
                "failure_code": None,
            },
            context=context,
            aggregate_type="order",
            aggregate_id=order_id,
            aggregate_version=1,
            event_time=now,
        )

    return {
        "order_id": order_id,
        "status": "PENDING",
        "status_url": f"/v1/orders/{order_id}",
    }


def get_order_snapshot(db, namespace, order_id):
    with db.transaction() as tx:
        row = tx.execute(
            """
            SELECT order_id, quote_id, user_id, session_id, status, order_version,
                   total_amount_minor, currency, reservation_id, payment_id,
                   failure_code, created_at, updated_at
            FROM orders WHERE namespace = %s AND order_id = %s
            """,
            (namespace, order_id),
        ).fetchone()
        if row is None:
            raise not_found("Order")
        items = tx.execute(
            """
            SELECT sku, quantity, unit_price_minor, line_total_minor, catalog_version
            FROM order_items WHERE namespace = %s AND order_id = %s
            ORDER BY sku
            """,
            (namespace, order_id),
        ).fetchall()
    return {
        **row,
        "lines": items,
    }


def _fetch_quote(catalog_url, quote_id, context, internal_token):
    """Fetch the quote snapshot from the catalog service."""
    headers = {
        "X-Namespace": context.namespace,
        "X-Run-ID": context.run_id,
        "X-User-ID": context.user_id,
        "X-Correlation-ID": context.correlation_id,
        "X-Request-ID": context.request_id,
    }
    if context.session_id:
        headers["X-Session-ID"] = context.session_id
    if internal_token:
        headers["Authorization"] = f"Bearer {internal_token}"

    try:
        resp = httpx.get(
            f"{catalog_url}/internal/v1/quotes/{quote_id}",
            headers=headers,
            timeout=2.0,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise ServiceError(400, ErrorCode.BAD_REQUEST, "Quote not found or expired.") from exc
        raise ServiceError(
            503, ErrorCode.DEPENDENCY_UNAVAILABLE, "Catalog service unavailable."
        ) from exc
    except httpx.HTTPError as exc:
        raise ServiceError(
            503, ErrorCode.DEPENDENCY_UNAVAILABLE, "Catalog service unavailable."
        ) from exc
