"""Order creation and status queries."""

import logging
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from services.orders.errors import ServiceError, conflict, not_found
from shared.contracts.catalog import Quote
from shared.contracts.common import ErrorCode
from shared.contracts.transactions import QuoteLine

logger = logging.getLogger("orders")
# One pooled client: a fresh httpx client per call costs ~200 ms of setup.
_HTTP = httpx.Client(timeout=2.0)


def create_order(
    db, events, namespace, request, context, *, catalog_url, internal_token, benchmark_headers=None
):
    """Accept a checkout: verify the catalogue quote, create order + saga job atomically."""
    # Common spec §8: a retry of an already-accepted quote resolves to the same order,
    # even after the quote has expired, so check consumption before re-validating.
    with db.transaction() as tx:
        existing = _accepted_order(tx, namespace, context.user_id, request.quote_id)
    if existing is not None:
        return existing

    order_id = str(uuid4())
    quote = _fetch_quote(catalog_url, request.quote_id, context, internal_token)
    now = datetime.now(UTC)
    _verify_quote(quote, request.quote_id, context.user_id, now)

    with db.transaction() as tx:
        result = tx.execute(
            """
            INSERT INTO orders
                (namespace, order_id, quote_id, user_id, session_id,
                 total_amount_minor, currency, status, created_at, updated_at,
                 origin_context, benchmark_headers)
            VALUES (%s, %s, %s, %s, %s, %s, 'INR', 'PENDING', %s, %s, %s, %s)
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
                Jsonb(
                    context.model_copy(
                        update={"session_id": request.session_id or context.session_id}
                    ).model_dump(mode="json")
                ),
                Jsonb(benchmark_headers or {}),
            ),
        ).fetchone()

        if result is None:
            return _accepted_order(tx, namespace, context.user_id, request.quote_id)

        for line in quote["lines"]:
            tx.execute(
                """
                INSERT INTO order_items
                    (namespace, order_id, sku, quantity, unit_price_minor,
                     line_total_minor, catalog_version)
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


def _accepted_order(tx, namespace, user_id, quote_id):
    row = tx.execute(
        "SELECT order_id, status FROM orders "
        "WHERE namespace = %s AND user_id = %s AND quote_id = %s",
        (namespace, user_id, quote_id),
    ).fetchone()
    if row is None:
        return None
    return {
        "order_id": row["order_id"],
        "status": row["status"],
        "status_url": f"/v1/orders/{row['order_id']}",
    }


def _verify_quote(quote, quote_id, user_id, now):
    """Common spec §9.1: Orders checks quote user, currency, expiry and lines (server time)."""
    try:
        parsed = Quote.model_validate(quote)
        lines = [QuoteLine.model_validate(line) for line in quote["lines"]]
    except (ValidationError, KeyError, TypeError) as exc:
        raise ServiceError(
            503, ErrorCode.DEPENDENCY_UNAVAILABLE, "Catalog returned an invalid quote."
        ) from exc
    if parsed.quote_id != quote_id:
        raise ServiceError(
            503, ErrorCode.DEPENDENCY_UNAVAILABLE, "Catalog returned a different quote."
        )
    if parsed.user_id != user_id:
        raise ServiceError(403, ErrorCode.FORBIDDEN, "Quote belongs to another user.")
    if parsed.expires_at <= now:
        raise conflict("Quote has expired; request a new quote.", code=ErrorCode.QUOTE_EXPIRED)
    if len({line.sku for line in lines}) != len(lines) or parsed.total_amount_minor != sum(
        line.line_total_minor for line in lines
    ):
        raise conflict("Quote lines are inconsistent with its total.")


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
        resp = _HTTP.get(
            f"{catalog_url}/internal/v1/quotes/{quote_id}",
            headers=headers,
            timeout=2.0,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 404:
            raise not_found("Quote") from exc
        if status == 403:
            raise ServiceError(403, ErrorCode.FORBIDDEN, "Quote belongs to another user.") from exc
        raise ServiceError(
            503, ErrorCode.DEPENDENCY_UNAVAILABLE, "Catalog service unavailable."
        ) from exc
    except httpx.HTTPError as exc:
        raise ServiceError(
            503, ErrorCode.DEPENDENCY_UNAVAILABLE, "Catalog service unavailable."
        ) from exc
