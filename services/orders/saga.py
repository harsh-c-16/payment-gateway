"""Durable orchestrated saga for checkout: reserve -> pay -> commit -> confirm.

Each step is idempotent. On failure, compensation releases inventory first, then reverses
payment (common spec §9.3). saga_jobs tracks the current step, attempt count and backoff.
Operation keys ensure the intended command is recorded before the network call.
A durable lease on saga_jobs.next_attempt_at prevents concurrent runners on one order.
"""

import logging
import os
import time
from datetime import UTC, datetime, timedelta

import httpx

from services.orders.errors import ServiceError
from shared.contracts.common import RequestContext

logger = logging.getLogger("orders.saga")
# One pooled client: a fresh httpx client per call costs ~200 ms of setup.
_HTTP = httpx.Client(timeout=2.0)

BACKOFF_BASE_SECONDS = 0.1
BACKOFF_CAP_SECONDS = 2.0
MANUAL_REVIEW_TIMEOUT_SECONDS = 60
CLAIM_LEASE_SECONDS = 10


def fault_injection_allowed(namespace):
    """Team-wide guard: both flags explicitly on and an isolated bench- namespace."""
    return all(
        os.environ.get(flag, "false").lower() == "true"
        for flag in ("BENCHMARK_MODE", "FAULT_INJECTION_ENABLED")
    ) and namespace.startswith("bench-")


class FaultBarrier:
    """Controlled crash/delay points; a no-op unless fault_injection_allowed(namespace)."""

    @staticmethod
    def check(db, namespace, barrier_name):
        if not fault_injection_allowed(namespace):
            return
        try:
            with db.transaction(statement_timeout_ms=1000) as tx:
                row = tx.execute(
                    "SELECT action, delay_ms FROM fault_barriers "
                    "WHERE namespace = %s AND barrier_name = %s AND enabled = true",
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


def run_pending_sagas(
    db, events, context, *, inventory_url, payments_url, internal_token, batch_size=10
):
    """Claim due saga jobs under a lease and run one step each. Returns count processed."""
    now = datetime.now(UTC)
    processed = 0

    # Claiming pushes next_attempt_at past the lease so other workers skip the job without a
    # transaction held open across network calls; a crashed worker's job reappears afterwards.
    with db.transaction(statement_timeout_ms=5000) as tx:
        jobs = tx.execute(
            """
            UPDATE saga_jobs sj SET next_attempt_at = %s, updated_at = %s
            FROM (
                SELECT namespace, order_id FROM saga_jobs
                WHERE next_attempt_at IS NOT NULL AND next_attempt_at <= %s
                ORDER BY next_attempt_at
                LIMIT %s
                FOR UPDATE SKIP LOCKED
            ) due
            WHERE sj.namespace = due.namespace AND sj.order_id = due.order_id
            RETURNING sj.namespace, sj.order_id, sj.planned_step, sj.attempt
            """,
            (now + timedelta(seconds=CLAIM_LEASE_SECONDS), now, now, batch_size),
        ).fetchall()

    for job in jobs:
        try:
            _execute_step(
                db,
                events,
                job,
                context,
                inventory_url=inventory_url,
                payments_url=payments_url,
                internal_token=internal_token,
            )
            processed += 1
        except Exception as error:
            logger.exception(
                "saga step failed for order %s step %s", job["order_id"], job["planned_step"]
            )
            _backoff(db, job, error)

    return processed


def _operation_key(order_id, step, version=1):
    return f"{order_id}:{step.lower()}:v{version}"


def _execute_step(db, events, job, context, *, inventory_url, payments_url, internal_token):
    ns = job["namespace"]
    oid = str(job["order_id"])
    step = job["planned_step"]
    now = datetime.now(UTC)
    # The worker polls every namespace; internal calls and events must carry the job's own.
    order = _get_order(db, ns, oid)
    origin = order.get("origin_context")
    context = (
        RequestContext.model_validate(origin)
        if origin
        else context.model_copy(update={"namespace": ns})
    )
    if context.namespace != ns:
        raise RuntimeError("order origin namespace differs from its saga job")

    headers = _internal_headers(context, internal_token)

    if step == "RESERVE":
        order = _get_order(db, ns, oid)
        items = _get_items(db, ns, oid)
        op_key = _operation_key(oid, "reserve")
        _record_operation_key(db, ns, oid, op_key, step)

        FaultBarrier.check(db, ns, "saga.before_reserve")
        resp = _HTTP.post(
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
            _advance(
                db,
                events,
                ns,
                oid,
                "RESERVING",
                "AUTHORIZE_PAYMENT",
                now,
                context,
                reservation_id=result["reservation_id"],
            )
        elif resp.status_code == 409:
            _advance(
                db,
                events,
                ns,
                oid,
                "COMPENSATING",
                "CANCEL",
                now,
                context,
                failure_code="RESERVATION_FAILED",
            )
        else:
            raise RuntimeError(f"inventory reserve returned {resp.status_code}")

    elif step == "AUTHORIZE_PAYMENT":
        headers.update(order.get("benchmark_headers") or {})
        po = _HTTP.get(
            f"{payments_url}/internal/v1/payments/by-order/{oid}",
            headers=headers,
            timeout=2.0,
        )
        if po.status_code != 200:
            raise RuntimeError(f"payment lookup returned {po.status_code}")
        payment_order = po.json()
        attempts = payment_order.get("attempts", [])
        success = next((a for a in attempts if a.get("status") == "SUCCESS"), None)
        if success is not None:
            _advance(
                db,
                events,
                ns,
                oid,
                "PAYMENT_PENDING",
                "COMMIT_STOCK",
                now,
                context,
                payment_id=success["payment_id"],
            )
            return
        latest = attempts[-1] if attempts else None
        pending = latest is not None and latest.get("status") == "PENDING"
        retryable = latest is not None and (
            latest.get("status") == "FAILED"
            and latest.get("failure_code") == "RETRYABLE_PROVIDER_FAILURE"
        )
        if (
            payment_order.get("quiesced")
            or (latest and not pending and not retryable)
            or (retryable and len(attempts) >= 2)
        ):
            _advance(
                db,
                events,
                ns,
                oid,
                "COMPENSATING",
                "COMPENSATE_RELEASE",
                now,
                context,
                failure_code=(latest or {}).get("failure_code") or "PAYMENT_FAILED",
            )
            return
        # Check the hold while awaiting payment and before authorizing another attempt.
        # An unavailable/invalid snapshot stays unresolved and retries through _backoff.
        reservation = _HTTP.get(
            f"{inventory_url}/internal/v1/reservations/by-order/{oid}",
            headers=headers,
            timeout=2.0,
        )
        if reservation.status_code != 200:
            raise RuntimeError(f"reservation lookup returned {reservation.status_code}")
        hold = reservation.json()
        expires = datetime.fromisoformat(hold["expires_at"].replace("Z", "+00:00"))
        if hold["state"] != "ACTIVE" or expires <= datetime.now(UTC):
            _advance(
                db,
                events,
                ns,
                oid,
                "COMPENSATING",
                "COMPENSATE_RELEASE",
                now,
                context,
                failure_code="RESERVATION_EXPIRED",
            )
            return
        if pending:
            # PENDING is never a reason to create attempt 2, even after response loss.
            _retry_step(db, ns, oid, step, now)
            return
        attempt_number = len(attempts) + 1
        op_key = _operation_key(oid, f"authorize:{attempt_number}")
        _record_operation_key(db, ns, oid, op_key, step)
        headers["Idempotency-Key"] = op_key
        FaultBarrier.check(db, ns, "saga.before_payment")
        resp = _HTTP.post(
            f"{payments_url}/internal/v1/payments/authorize",
            json={
                "order_id": oid,
                "attempt_number": attempt_number,
                "amount_minor": order["total_amount_minor"],
                "currency": order.get("currency", "INR"),
            },
            headers=headers,
            timeout=2.0,
        )
        FaultBarrier.check(db, ns, "saga.after_payment")
        if resp.status_code == 202:
            result = resp.json()
            if result["status"] == "SUCCESS":
                _advance(
                    db,
                    events,
                    ns,
                    oid,
                    "PAYMENT_PENDING",
                    "COMMIT_STOCK",
                    now,
                    context,
                    payment_id=result["payment_id"],
                )
            elif result["status"] == "PENDING" or (
                result["status"] == "FAILED"
                and attempt_number < 2
                and result.get("failure_code") == "RETRYABLE_PROVIDER_FAILURE"
            ):
                if order.get("status") != "PAYMENT_PENDING":
                    _advance(db, events, ns, oid, "PAYMENT_PENDING", step, now, context)
                _retry_step(db, ns, oid, step, now)
            else:
                _advance(
                    db,
                    events,
                    ns,
                    oid,
                    "COMPENSATING",
                    "COMPENSATE_RELEASE",
                    now,
                    context,
                    failure_code=result.get("failure_code") or "PAYMENT_FAILED",
                )
        elif resp.status_code == 409:
            _advance(
                db,
                events,
                ns,
                oid,
                "COMPENSATING",
                "COMPENSATE_RELEASE",
                now,
                context,
                failure_code="PAYMENT_CONFLICT",
            )
        else:
            raise RuntimeError(f"payment authorize returned {resp.status_code}")

    elif step == "COMMIT_STOCK":
        order = _get_order(db, ns, oid)
        op_key = _operation_key(oid, "commit")
        _record_operation_key(db, ns, oid, op_key, step)

        FaultBarrier.check(db, ns, "saga.before_commit")
        resp = _HTTP.post(
            f"{inventory_url}/internal/v1/reservations/by-order/{oid}/commit",
            json={"reservation_id": order["reservation_id"]},
            headers=headers,
            timeout=2.0,
        )
        FaultBarrier.check(db, ns, "saga.after_commit")

        if resp.status_code == 200:
            _advance(db, events, ns, oid, "COMMITTING_STOCK", "CONFIRM", now, context)
        elif resp.status_code == 409:
            _advance(
                db,
                events,
                ns,
                oid,
                "COMPENSATING",
                "COMPENSATE_RELEASE",
                now,
                context,
                failure_code="COMMIT_FAILED",
            )
        else:
            raise RuntimeError(f"inventory commit returned {resp.status_code}")

    elif step == "CONFIRM":
        FaultBarrier.check(db, ns, "saga.before_confirm")
        _finalize(db, events, ns, oid, "CONFIRMED", now, context)

    elif step == "COMPENSATE_RELEASE":
        # §9.3: release first. Only a proven release lets payment be reversed; a committed
        # sale finishes forward and is never refunded as a generic failure.
        order = _get_order(db, ns, oid)
        try:
            resp = _HTTP.post(
                f"{inventory_url}/internal/v1/reservations/by-order/{oid}/release",
                json={"reason": order["failure_code"] or "saga_compensation"},
                headers=headers,
                timeout=2.0,
            )
        except httpx.HTTPError as error:
            raise RuntimeError("inventory release outcome unknown") from error

        if resp.status_code == 200:
            _update_saga_step(db, ns, oid, "COMPENSATE_PAYMENT", now)
        elif resp.status_code == 409 and _reports_committed(resp):
            if not order["payment_id"]:
                raise RuntimeError("inventory committed without a recorded payment")
            logger.info("order %s: inventory already committed, finishing forward", oid)
            _advance(db, events, ns, oid, "COMMITTING_STOCK", "CONFIRM", now, context)
        else:
            raise RuntimeError(f"inventory release returned {resp.status_code}")

    elif step == "COMPENSATE_PAYMENT":
        order = _get_order(db, ns, oid)
        try:
            resp = _HTTP.post(
                f"{payments_url}/internal/v1/payments/by-order/{oid}/reverse",
                json={"reason": order["failure_code"] or "saga_compensation"},
                headers=headers,
                timeout=2.0,
            )
        except httpx.HTTPError as error:
            raise RuntimeError("payment reversal outcome unknown") from error
        if resp.status_code != 200:
            raise RuntimeError(f"payment reverse returned {resp.status_code}")
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
        updated = tx.execute(
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
                new_status,
                now,
                extra.get("reservation_id"),
                extra.get("payment_id"),
                extra.get("failure_code"),
                ns,
                oid,
            ),
        ).fetchone()
        if updated is None:
            raise RuntimeError(f"order {oid} not found in namespace {ns}")
        tx.execute(
            """
            UPDATE saga_jobs SET planned_step = %s, attempt = 0,
                                 next_attempt_at = %s, updated_at = %s
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
            UPDATE saga_jobs SET planned_step = %s, attempt = 0,
                                 next_attempt_at = %s, updated_at = %s
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
            (now + timedelta(milliseconds=100), now, ns, oid),
        )


def _backoff(db, job, error=None):
    """§9.3: exponential retry from 100 ms capped at 2 s; the job is never dropped.

    An order with no saga progress for MANUAL_REVIEW_TIMEOUT_SECONDS is surfaced as
    MANUAL_REVIEW while its durable retry continues and may still resolve it.
    """
    now = datetime.now(UTC)
    attempt = job["attempt"] + 1
    delay = min(BACKOFF_BASE_SECONDS * 2 ** (attempt - 1), BACKOFF_CAP_SECONDS)
    with db.transaction() as tx:
        tx.execute(
            """
            UPDATE saga_jobs
            SET attempt = %s, next_attempt_at = %s, last_error = %s, updated_at = %s
            WHERE namespace = %s AND order_id = %s
            """,
            (
                attempt,
                now + timedelta(seconds=delay),
                str(error or "retrying")[:500],
                now,
                job["namespace"],
                job["order_id"],
            ),
        )
        flagged = tx.execute(
            """
            UPDATE orders
            SET status = 'MANUAL_REVIEW', order_version = order_version + 1, updated_at = %s
            WHERE namespace = %s AND order_id = %s AND updated_at <= %s
              AND status NOT IN ('CONFIRMED', 'CANCELLED', 'MANUAL_REVIEW')
            RETURNING order_id
            """,
            (
                now,
                job["namespace"],
                job["order_id"],
                now - timedelta(seconds=MANUAL_REVIEW_TIMEOUT_SECONDS),
            ),
        ).fetchone()
    if flagged:
        logger.warning("order %s surfaced as MANUAL_REVIEW; retry continues", job["order_id"])


def _reports_committed(resp):
    try:
        message = resp.json().get("error", {}).get("message", "")
    except ValueError:
        return False
    return "committed" in message.lower()


def _get_order(db, ns, oid):
    with db.transaction() as tx:
        return tx.execute(
            "SELECT * FROM orders WHERE namespace = %s AND order_id = %s",
            (ns, oid),
        ).fetchone()


def _get_items(db, ns, oid):
    with db.transaction() as tx:
        return tx.execute(
            "SELECT sku, quantity FROM order_items "
            "WHERE namespace = %s AND order_id = %s ORDER BY sku",
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
    if context.trace_id:
        headers["X-Trace-ID"] = context.trace_id
    if internal_token:
        headers["Authorization"] = f"Bearer {internal_token}"
    return headers
