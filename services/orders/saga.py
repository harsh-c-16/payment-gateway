"""Durable orchestrated saga for checkout: reserve -> pay -> commit -> confirm.

Each step is idempotent. On failure, compensation runs: release inventory, reverse payment.
The saga_jobs table tracks the current step, attempt count, and backoff schedule.
Operation keys ensure the intended command is recorded before the network call.
Per-order advisory locks prevent concurrent saga runners on the same order.
"""

import hashlib
import logging
import os
import time
from datetime import UTC, datetime, timedelta

import httpx

from services.orders.errors import ServiceError
from shared.contracts.common import ErrorCode

logger = logging.getLogger("orders.saga")

MAX_SAGA_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 2
MANUAL_REVIEW_TIMEOUT_SECONDS = 60

_BENCHMARK_MODE = os.environ.get("BENCHMARK_MODE", "false") == "true"


class FaultBarrier:
    """Controlled crash/delay points for benchmark testing. No-op outside benchmark mode."""

    @staticmethod
    def check(db, namespace, barrier_name):
        if not _BENCHMARK_MODE:
            return
        try:
            with db.transaction(statement_timeout_ms=1000) as tx:
                row = tx.execute(
                    "SELECT action, delay_ms FROM fault_barriers WHERE namespace = %s AND barrier_name = %s AND enabled = true",
                    (namespace, barrier_name),
                ).fetchone()
            if row is None:
                return
            if row["action"] == "CRASH":
                raise RuntimeError(f"Fault barrier triggered: {barrier_name}")
            elif row["action"] == "DELAY":
                time.sleep(row["delay_ms"] / 1000.0)
        except ServiceError:
            raise
        except RuntimeError:
            raise
        except Exception:
            pass


def _order_advisory_lock_id(order_id: str) -> int:
    return int(hashlib.sha256(f"saga-order-{order_id}".encode()).hexdigest()[:15], 16)


def run_pending_sagas(db, events, context, *, inventory_url, payments_url, internal_token, batch_size=10):
    """Process pending saga jobs. Returns count of jobs processed."""
    now = datetime.now(UTC)
    processed = 0

    with db.transaction(statement_timeout_ms=5000) as tx:
        jobs = tx.execute(
            """
            SELECT sj.namespace, sj.order_id, sj.planned_step, sj.attempt
            FROM saga_jobs sj
            WHERE sj.next_attempt_at IS NOT NULL AND sj.next_attempt_at <= %s
            ORDER BY sj.next_attempt_at
            LIMIT %s
            FOR UPDATE SKIP LOCKED
            """,
            (now, batch_size),
        ).fetchall()

    for job in jobs:
        try:
            _execute_step(
                db, events, job, context,
                inventory_url=inventory_url,
                payments_url=payments_url,
                internal_token=internal_token,
            )
            processed += 1
        except Exception:
            logger.exception("saga step failed for order %s step %s", job["order_id"], job["planned_step"])
            _backoff(db, job)

    return processed


def _operation_key(order_id, step, version=1):
    return f"{order_id}:{step.lower()}:v{version}"


def _execute_step(db, events, job, context, *, inventory_url, payments_url, internal_token):
    ns = job["namespace"]
    oid = job["order_id"]
    step = job["planned_step"]
    now = datetime.now(UTC)

    headers = _internal_headers(context, internal_token)

    if step == "RESERVE":
        order = _get_order(db, ns, oid)
        items = _get_items(db, ns, oid)
        op_key = _operation_key(oid, "reserve")
        _record_operation_key(db, ns, oid, op_key, step)

        FaultBarrier.check(db, ns, "saga.before_reserve")
        resp = httpx.post(
            f"{inventory_url}/internal/v1/reservations",
            json={
                "order_id": oid,
                "items": [{"sku": i["sku"], "quantity": i["quantity"]} for i in items],
                "ttl_seconds": 30,
            },
            headers=headers,
            timeout=2.0,
        )
        FaultBarrier.check(db, ns, "saga.after_reserve")

        if resp.status_code == 201:
            result = resp.json()
            _advance(db, events, ns, oid, "RESERVING", "AUTHORIZE_PAYMENT", now, context,
                     reservation_id=result["reservation_id"])
        elif resp.status_code == 409:
            _advance(db, events, ns, oid, "COMPENSATING", "CANCEL", now, context,
                     failure_code="RESERVATION_FAILED")
        else:
            raise RuntimeError(f"inventory reserve returned {resp.status_code}")

    elif step == "AUTHORIZE_PAYMENT":
        order = _get_order(db, ns, oid)
        po = httpx.get(
            f"{payments_url}/internal/v1/payments/by-order/{oid}",
            headers=headers, timeout=2.0,
        )
        existing_attempts = po.json().get("attempts", []) if po.status_code == 200 else []
        attempt_number = len(existing_attempts) + 1
        if attempt_number > 2:
            _advance(db, events, ns, oid, "COMPENSATING", "COMPENSATE_PAYMENT", now, context,
                     failure_code="ALL_PAYMENT_ATTEMPTS_FAILED")
            return

        op_key = _operation_key(oid, f"authorize:{attempt_number}")
        _record_operation_key(db, ns, oid, op_key, step)

        FaultBarrier.check(db, ns, "saga.before_payment")
        resp = httpx.post(
            f"{payments_url}/internal/v1/payments/authorize",
            json={
                "order_id": oid,
                "attempt_number": attempt_number,
                "amount_minor": order["total_amount_minor"],
                "currency": "INR",
            },
            headers=headers,
            timeout=2.0,
        )
        FaultBarrier.check(db, ns, "saga.after_payment")

        if resp.status_code == 202:
            result = resp.json()
            if result["status"] == "SUCCESS":
                _advance(db, events, ns, oid, "PAYMENT_PENDING", "COMMIT_STOCK", now, context,
                         payment_id=result["payment_id"])
            elif result["status"] == "FAILED" and attempt_number < 2:
                _retry_step(db, ns, oid, "AUTHORIZE_PAYMENT", now)
            else:
                _advance(db, events, ns, oid, "COMPENSATING", "COMPENSATE_PAYMENT", now, context,
                         failure_code="PAYMENT_FAILED")
        elif resp.status_code == 409:
            _advance(db, events, ns, oid, "COMPENSATING", "COMPENSATE_PAYMENT", now, context,
                     failure_code="PAYMENT_CONFLICT")
        else:
            raise RuntimeError(f"payment authorize returned {resp.status_code}")

    elif step == "COMMIT_STOCK":
        order = _get_order(db, ns, oid)
        op_key = _operation_key(oid, "commit")
        _record_operation_key(db, ns, oid, op_key, step)

        FaultBarrier.check(db, ns, "saga.before_commit")
        resp = httpx.post(
            f"{inventory_url}/internal/v1/reservations/by-order/{oid}/commit",
            json={"reservation_id": order["reservation_id"]},
            headers=headers,
            timeout=2.0,
        )
        FaultBarrier.check(db, ns, "saga.after_commit")

        if resp.status_code == 200:
            _advance(db, events, ns, oid, "COMMITTING_STOCK", "CONFIRM", now, context)
        elif resp.status_code == 409:
            _advance(db, events, ns, oid, "COMPENSATING", "COMPENSATE_PAYMENT", now, context,
                     failure_code="COMMIT_FAILED")
        else:
            raise RuntimeError(f"inventory commit returned {resp.status_code}")

    elif step == "CONFIRM":
        FaultBarrier.check(db, ns, "saga.before_confirm")
        _finalize(db, events, ns, oid, "CONFIRMED", now, context)

    elif step == "COMPENSATE_PAYMENT":
        order = _get_order(db, ns, oid)
        try:
            httpx.post(
                f"{payments_url}/internal/v1/payments/by-order/{oid}/reverse",
                json={"reason": order.get("failure_code", "saga_compensation")},
                headers=headers,
                timeout=2.0,
            )
        except httpx.HTTPError:
            raise RuntimeError("payments service unavailable during compensation")
        _update_saga_step(db, ns, oid, "COMPENSATE_RELEASE", now)

    elif step == "COMPENSATE_RELEASE":
        order = _get_order(db, ns, oid)
        try:
            resp = httpx.post(
                f"{inventory_url}/internal/v1/reservations/by-order/{oid}/release",
                json={"reason": order.get("failure_code", "saga_compensation")},
                headers=headers,
                timeout=2.0,
            )
        except httpx.HTTPError:
            raise RuntimeError("inventory service unavailable during compensation")

        if resp.status_code == 409:
            release_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            error_detail = release_data.get("error", {}).get("message", "")
            if "committed" in error_detail.lower():
                logger.info("order %s: inventory already committed, finishing forward", oid)
                _advance(db, events, ns, oid, "COMMITTING_STOCK", "CONFIRM", now, context)
                return

        _update_saga_step(db, ns, oid, "CANCEL", now)

    elif step == "CANCEL":
        _finalize(db, events, ns, oid, "CANCELLED", now, context)


def _record_operation_key(db, ns, oid, op_key, step):
    """Record the intended operation key before making the network call."""
    with db.transaction() as tx:
        tx.execute(
            """
            UPDATE saga_jobs SET operation_key = %s, updated_at = clock_timestamp()
            WHERE namespace = %s AND order_id = %s AND planned_step = %s
            """,
            (op_key, ns, oid, step),
        )


def _advance(db, events, ns, oid, new_status, next_step, now, context, **extra):
    with db.transaction() as tx:
        version = tx.execute(
            """
            UPDATE orders
            SET status = %s, order_version = order_version + 1, updated_at = %s,
                reservation_id = COALESCE(%s, reservation_id),
                payment_id = COALESCE(%s, payment_id),
                failure_code = COALESCE(%s, failure_code)
            WHERE namespace = %s AND order_id = %s
            RETURNING order_version
            """,
            (
                new_status, now,
                extra.get("reservation_id"), extra.get("payment_id"), extra.get("failure_code"),
                ns, oid,
            ),
        ).fetchone()["order_version"]
        tx.execute(
            """
            UPDATE saga_jobs SET planned_step = %s, attempt = 0, next_attempt_at = %s, updated_at = %s
            WHERE namespace = %s AND order_id = %s
            """,
            (next_step, now, now, ns, oid),
        )


def _finalize(db, events, ns, oid, terminal_status, now, context):
    with db.transaction() as tx:
        row = tx.execute(
            """
            UPDATE orders
            SET status = %s, order_version = order_version + 1, updated_at = %s
            WHERE namespace = %s AND order_id = %s
            RETURNING order_version, quote_id, user_id, session_id, total_amount_minor,
                      reservation_id, payment_id, failure_code, created_at
            """,
            (terminal_status, now, ns, oid),
        ).fetchone()
        tx.execute(
            """
            UPDATE saga_jobs SET planned_step = %s, next_attempt_at = NULL, updated_at = %s
            WHERE namespace = %s AND order_id = %s
            """,
            (terminal_status, now, ns, oid),
        )

        event_type = "ORDER_CONFIRMED" if terminal_status == "CONFIRMED" else "ORDER_CANCELLED"
        payload = {
            "order_id": oid,
            "order_status": terminal_status,
            "total_amount_minor": row["total_amount_minor"],
            "currency": "INR",
            "created_at": row["created_at"].isoformat().replace("+00:00", "Z"),
            "user_id": row["user_id"],
            "session_id": row["session_id"],
            "quote_id": row["quote_id"],
            "failure_code": row["failure_code"],
        }
        if terminal_status == "CONFIRMED":
            payload["reservation_id"] = row["reservation_id"]
            payload["payment_id"] = row["payment_id"]

        events.append(
            tx,
            event_type=event_type,
            payload=payload,
            context=context,
            aggregate_type="order",
            aggregate_id=oid,
            aggregate_version=row["order_version"],
            event_time=now,
        )


def _update_saga_step(db, ns, oid, next_step, now):
    with db.transaction() as tx:
        tx.execute(
            """
            UPDATE saga_jobs SET planned_step = %s, attempt = 0, next_attempt_at = %s, updated_at = %s
            WHERE namespace = %s AND order_id = %s
            """,
            (next_step, now, now, ns, oid),
        )


def _retry_step(db, ns, oid, step, now):
    with db.transaction() as tx:
        tx.execute(
            """
            UPDATE saga_jobs
            SET attempt = attempt + 1, next_attempt_at = %s, updated_at = %s
            WHERE namespace = %s AND order_id = %s
            """,
            (now + timedelta(seconds=1), now, ns, oid),
        )


def _backoff(db, job):
    now = datetime.now(UTC)
    attempt = job["attempt"] + 1
    if attempt >= MAX_SAGA_ATTEMPTS:
        with db.transaction() as tx:
            tx.execute(
                """
                UPDATE orders SET status = 'MANUAL_REVIEW', order_version = order_version + 1, updated_at = %s
                WHERE namespace = %s AND order_id = %s
                """,
                (now, job["namespace"], job["order_id"]),
            )
            tx.execute(
                """
                UPDATE saga_jobs SET planned_step = 'MANUAL_REVIEW', next_attempt_at = NULL,
                    attempt = %s, last_error = 'max_attempts', updated_at = %s
                WHERE namespace = %s AND order_id = %s
                """,
                (attempt, now, job["namespace"], job["order_id"]),
            )
        logger.warning("order %s moved to MANUAL_REVIEW after %d attempts", job["order_id"], attempt)
        return

    delay = min(BACKOFF_BASE_SECONDS * (2 ** attempt), 2.0)
    with db.transaction() as tx:
        tx.execute(
            """
            UPDATE saga_jobs
            SET attempt = %s, next_attempt_at = %s, last_error = 'retrying', updated_at = %s
            WHERE namespace = %s AND order_id = %s
            """,
            (attempt, now + timedelta(seconds=delay), now, job["namespace"], job["order_id"]),
        )


def _get_order(db, ns, oid):
    with db.transaction() as tx:
        return tx.execute(
            "SELECT * FROM orders WHERE namespace = %s AND order_id = %s",
            (ns, oid),
        ).fetchone()


def _get_items(db, ns, oid):
    with db.transaction() as tx:
        return tx.execute(
            "SELECT sku, quantity FROM order_items WHERE namespace = %s AND order_id = %s ORDER BY sku",
            (ns, oid),
        ).fetchall()


def _internal_headers(context, internal_token):
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
    return headers
