"""Simulated payment authorization with idempotent ledger. Max 2 attempts per order."""

import random
from random import Random
from uuid import uuid4

from psycopg.types.json import Jsonb

from services.payments.errors import conflict
from shared.contracts.common import RequestContext
from shared.telemetry.benchmark import benchmark_headers as validate_benchmark_headers

SIMULATED_FAILURE_RATE = 0.05


def scenario_failure(headers):
    """Independent implementation of the frozen v2 95/5 logical scenario rule."""
    import hashlib
    import json

    phase, ordinal, _ = headers["X-Benchmark-Scenario-ID"].split(":", 2)
    index = int(ordinal)
    recipe = {"seed": int(headers["X-Benchmark-Seed"]), "phase": phase, "block": index // 100}
    encoded = json.dumps(recipe, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    block_seed = int(hashlib.sha256(encoded.encode()).hexdigest()[:16], 16)
    declined = Random(block_seed).sample(range(100), 5)
    return "DECLINED" if index % 100 in declined else None


def authorize(db, events, namespace, request, context, *, benchmark_headers=None):
    """Persist a PENDING attempt and immutable plan; completion belongs to the worker."""
    control = validate_benchmark_headers(benchmark_headers or {}, namespace)
    payment_id = str(uuid4())
    with db.transaction() as tx:
        tx.execute(
            "INSERT INTO payment_orders (namespace,order_id) VALUES (%s,%s) "
            "ON CONFLICT (namespace,order_id) DO NOTHING",
            (namespace, request.order_id),
        )
        po = tx.execute(
            "SELECT quiesced FROM payment_orders WHERE namespace=%s AND order_id=%s FOR UPDATE",
            (namespace, request.order_id),
        ).fetchone()
        attempts = tx.execute(
            "SELECT * FROM payment_attempts WHERE namespace=%s AND order_id=%s "
            "ORDER BY attempt_number FOR UPDATE",
            (namespace, request.order_id),
        ).fetchall()
        existing = next(
            (a for a in attempts if a["attempt_number"] == request.attempt_number), None
        )
        if existing:
            if (existing["amount_minor"], existing["currency"]) != (
                request.amount_minor,
                request.currency,
            ) or (control and control != existing["benchmark_headers"]):
                raise conflict("Payment attempt identity reused with different input.")
            return _attempt_snapshot(tx, namespace, existing["payment_id"])
        if po["quiesced"]:
            raise conflict("Payment order is quiesced (reversed/cancelled).")
        if request.attempt_number != len(attempts) + 1 or any(
            a["status"] != "FAILED" or a["failure_code"] != "RETRYABLE_PROVIDER_FAILURE"
            for a in attempts
        ):
            raise conflict("Only a definitive retryable provider failure permits another attempt.")
        # Select once, persist before responding, and never re-roll on retry/restart.
        failure = (
            scenario_failure(control)
            if control
            else ("DECLINED" if random.random() < SIMULATED_FAILURE_RATE else None)
        )
        from shared.local_diagnostics.demo_controls import read_control

        local_plan = read_control("payments", context.run_id, namespace)
        delay_ms = 100
        if local_plan:
            failure = "DECLINED" if local_plan["scenario"] == "decline" else None
            delay_ms = 35_000 if local_plan["scenario"] == "late" else 100
        tx.execute(
            """
            INSERT INTO payment_attempts
                (namespace,payment_id,order_id,attempt_number,status,amount_minor,currency,
                 created_at,updated_at,completion_due_at,planned_failure_code,
                 origin_context,benchmark_headers)
            VALUES (%s,%s,%s,%s,'PENDING',%s,%s,clock_timestamp(),clock_timestamp(),
                    clock_timestamp() + %s * interval '1 millisecond',%s,%s,%s)
            """,
            (
                namespace,
                payment_id,
                request.order_id,
                request.attempt_number,
                request.amount_minor,
                request.currency,
                delay_ms,
                failure,
                Jsonb(context.model_dump(mode="json")),
                Jsonb(control),
            ),
        )
        return _attempt_snapshot(tx, namespace, payment_id)


def complete_pending_payments(db, events, *, batch_size=100):
    """Restart-safe callbacks; serialize with authorize/reverse on payment_orders first."""
    with db.transaction() as tx:
        due = tx.execute(
            "SELECT namespace,payment_id,order_id FROM payment_attempts "
            "WHERE status='PENDING' AND completion_due_at <= clock_timestamp() "
            "ORDER BY completion_due_at LIMIT %s",
            (batch_size,),
        ).fetchall()
    return sum(_complete_payment(db, events, row) for row in due)


def _complete_payment(db, events, due):
    ns, pid = due["namespace"], due["payment_id"]
    with db.transaction() as tx:
        guard = tx.execute(
            "SELECT quiesced FROM payment_orders WHERE namespace=%s AND order_id=%s "
            "FOR UPDATE SKIP LOCKED",
            (ns, due["order_id"]),
        ).fetchone()
        if guard is None:
            return 0
        attempt = tx.execute(
            "SELECT * FROM payment_attempts WHERE namespace=%s AND payment_id=%s FOR UPDATE",
            (ns, pid),
        ).fetchone()
        now = tx.execute("SELECT clock_timestamp() AS now").fetchone()["now"]
        if attempt["status"] != "PENDING" or attempt["completion_due_at"] > now:
            return 0
        if guard["quiesced"]:
            tx.execute(
                "UPDATE payment_attempts SET status='CANCELLED',updated_at=%s "
                "WHERE namespace=%s AND payment_id=%s",
                (now, ns, pid),
            )
            return 0
        context = RequestContext.model_validate(attempt["origin_context"])
        if context.namespace != ns:
            raise RuntimeError("payment origin namespace differs from its attempt")
        failure = attempt["planned_failure_code"]
        debit_id = None if failure else str(uuid4())
        status = "FAILED" if failure else "SUCCESS"
        if debit_id:
            tx.execute(
                "INSERT INTO ledger_entries "
                "(namespace,entry_id,payment_id,kind,amount_minor,currency,created_at) "
                "VALUES (%s,%s,%s,'DEBIT',%s,%s,%s)",
                (ns, debit_id, pid, attempt["amount_minor"], attempt["currency"], now),
            )
        tx.execute(
            "UPDATE payment_attempts SET status=%s,failure_code=%s,debit_id=%s,updated_at=%s "
            "WHERE namespace=%s AND payment_id=%s",
            (status, failure, debit_id, now, ns, pid),
        )
        tx.execute(
            "UPDATE payment_orders SET updated_at=%s WHERE namespace=%s AND order_id=%s",
            (now, ns, due["order_id"]),
        )
        events.append(
            tx,
            event_type="PAYMENT_FAILED" if failure else "PAYMENT_SUCCESS",
            payload={
                "payment_id": pid,
                "order_id": due["order_id"],
                "attempt_number": attempt["attempt_number"],
                "status": status,
                "amount_minor": attempt["amount_minor"],
                "currency": attempt["currency"],
                "attempt_created_at": attempt["created_at"].isoformat().replace("+00:00", "Z"),
                "failure_code": failure,
                "debit_id": debit_id,
                "reversal_id": None,
            },
            context=context,
            aggregate_type="payment_attempt",
            aggregate_id=pid,
            aggregate_version=1,
            event_time=now,
        )
        return 1


def get_payment_order(db, namespace, order_id):
    with db.transaction() as tx:
        po = tx.execute(
            "SELECT quiesced FROM payment_orders WHERE namespace = %s AND order_id = %s",
            (namespace, order_id),
        ).fetchone()
        if po is None:
            return {"attempts": [], "quiesced": False, "net_debit_minor": 0}
        attempts = tx.execute(
            """
            SELECT payment_id, order_id, attempt_number, status, amount_minor, currency,
                   failure_code, debit_id, reversal_id, created_at, updated_at
            FROM payment_attempts
            WHERE namespace = %s AND order_id = %s
            ORDER BY attempt_number
            """,
            (namespace, order_id),
        ).fetchall()
        net = _net_debit(tx, namespace, [a["payment_id"] for a in attempts])
    return {
        "attempts": attempts,
        "quiesced": po["quiesced"],
        "net_debit_minor": net,
    }


def reverse_payments(db, events, namespace, order_id, reason, context):
    """Quiesce the payment order and reverse all successful payments."""
    with db.transaction() as tx:
        # Establish the same guard as authorize before reading attempts. A missing-row
        # SELECT cannot lock out a concurrent first authorization; an upsert followed
        # by an early return could otherwise leave its newly committed debit behind.
        tx.execute(
            "INSERT INTO payment_orders (namespace,order_id) VALUES (%s,%s) "
            "ON CONFLICT (namespace,order_id) DO NOTHING",
            (namespace, order_id),
        )
        po = tx.execute(
            """
            SELECT quiesced FROM payment_orders
            WHERE namespace = %s AND order_id = %s
            FOR UPDATE
            """,
            (namespace, order_id),
        ).fetchone()
        # Take time after acquiring the guard so reversal cannot predate a success
        # that held it first. Ledger and attempt timestamps share the database clock.
        now = tx.execute("SELECT clock_timestamp() AS now").fetchone()["now"]

        if not po["quiesced"]:
            tx.execute(
                "UPDATE payment_orders SET quiesced = true, updated_at = %s "
                "WHERE namespace = %s AND order_id = %s",
                (now, namespace, order_id),
            )

        attempts = tx.execute(
            """
            SELECT payment_id, order_id, attempt_number, status, amount_minor, currency,
                   failure_code, debit_id, reversal_id, created_at, updated_at
            FROM payment_attempts
            WHERE namespace = %s AND order_id = %s
            ORDER BY attempt_number
            FOR UPDATE
            """,
            (namespace, order_id),
        ).fetchall()

        for attempt in attempts:
            if attempt["status"] == "SUCCESS" and attempt["reversal_id"] is None:
                reversal_id = str(uuid4())
                tx.execute(
                    """
                    INSERT INTO ledger_entries
                        (namespace, entry_id, payment_id, kind, amount_minor, currency, created_at)
                    VALUES (%s, %s, %s, 'REVERSAL', %s, %s, %s)
                    """,
                    (
                        namespace,
                        reversal_id,
                        attempt["payment_id"],
                        attempt["amount_minor"],
                        attempt["currency"],
                        now,
                    ),
                )
                tx.execute(
                    """
                    UPDATE payment_attempts
                    SET status = 'REVERSED', reversal_id = %s, updated_at = %s
                    WHERE namespace = %s AND payment_id = %s
                    """,
                    (reversal_id, now, namespace, attempt["payment_id"]),
                )
                events.append(
                    tx,
                    event_type="PAYMENT_REVERSED",
                    payload={
                        "payment_id": attempt["payment_id"],
                        "order_id": order_id,
                        "attempt_number": attempt["attempt_number"],
                        "status": "REVERSED",
                        "amount_minor": attempt["amount_minor"],
                        "currency": attempt["currency"],
                        "attempt_created_at": attempt["created_at"]
                        .isoformat()
                        .replace("+00:00", "Z"),
                        "failure_code": None,
                        "debit_id": attempt["debit_id"],
                        "reversal_id": reversal_id,
                    },
                    context=context,
                    aggregate_type="payment_attempt",
                    aggregate_id=attempt["payment_id"],
                    aggregate_version=2,
                    event_time=now,
                )
            elif attempt["status"] == "PENDING":
                tx.execute(
                    """
                    UPDATE payment_attempts
                    SET status = 'CANCELLED', updated_at = %s
                    WHERE namespace = %s AND payment_id = %s
                    """,
                    (now, namespace, attempt["payment_id"]),
                )

    return get_payment_order(db, namespace, order_id)


def _attempt_snapshot(tx, namespace, payment_id):
    return tx.execute(
        """
        SELECT payment_id, order_id, attempt_number, status, amount_minor, currency,
               failure_code, debit_id, reversal_id, created_at, updated_at
        FROM payment_attempts
        WHERE namespace = %s AND payment_id = %s
        """,
        (namespace, payment_id),
    ).fetchone()


def _net_debit(tx, namespace, payment_ids):
    if not payment_ids:
        return 0
    rows = tx.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN kind = 'DEBIT'
                           THEN amount_minor ELSE -amount_minor END), 0) AS net
        FROM ledger_entries
        WHERE namespace = %s AND payment_id = ANY(%s)
        """,
        (namespace, payment_ids),
    ).fetchone()
    return max(0, rows["net"])
