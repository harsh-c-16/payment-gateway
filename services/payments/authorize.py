"""Simulated payment authorization with idempotent ledger. Max 2 attempts per order."""

import random
from datetime import UTC, datetime
from uuid import uuid4

from services.payments.errors import conflict

SIMULATED_FAILURE_RATE = 0.15


def authorize(db, events, namespace, request, context):
    """Create a payment attempt. Simulated: succeeds ~85% of the time."""
    payment_id = str(uuid4())
    now = datetime.now(UTC)

    with db.transaction() as tx:
        tx.execute(
            """
            INSERT INTO payment_orders (namespace, order_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (namespace, order_id) DO NOTHING
            """,
            (namespace, request.order_id, now, now),
        )

        po = tx.execute(
            "SELECT quiesced FROM payment_orders WHERE namespace = %s AND order_id = %s",
            (namespace, request.order_id),
        ).fetchone()
        if po["quiesced"]:
            raise conflict("Payment order is quiesced (reversed/cancelled).")

        result = tx.execute(
            """
            INSERT INTO payment_attempts
                (namespace, payment_id, order_id, attempt_number, status,
                 amount_minor, currency, created_at, updated_at)
            VALUES (%s, %s, %s, %s, 'PENDING', %s, %s, %s, %s)
            ON CONFLICT (namespace, order_id, attempt_number) DO NOTHING
            RETURNING payment_id
            """,
            (
                namespace,
                payment_id,
                request.order_id,
                request.attempt_number,
                request.amount_minor,
                request.currency,
                now,
                now,
            ),
        ).fetchone()

        if result is None:
            existing = tx.execute(
                """
                SELECT payment_id, status, amount_minor
                FROM payment_attempts
                WHERE namespace = %s AND order_id = %s AND attempt_number = %s
                """,
                (namespace, request.order_id, request.attempt_number),
            ).fetchone()
            return _attempt_snapshot(tx, namespace, existing["payment_id"])

        succeeded = random.random() >= SIMULATED_FAILURE_RATE
        if succeeded:
            debit_id = str(uuid4())
            tx.execute(
                """
                UPDATE payment_attempts
                SET status = 'SUCCESS', debit_id = %s, updated_at = %s
                WHERE namespace = %s AND payment_id = %s
                """,
                (debit_id, now, namespace, payment_id),
            )
            tx.execute(
                """
                INSERT INTO ledger_entries (namespace, entry_id, payment_id, kind, amount_minor, currency, created_at)
                VALUES (%s, %s, %s, 'DEBIT', %s, %s, %s)
                """,
                (namespace, debit_id, payment_id, request.amount_minor, request.currency, now),
            )
            events.append(
                tx,
                event_type="PAYMENT_SUCCESS",
                payload={
                    "payment_id": payment_id,
                    "order_id": request.order_id,
                    "attempt_number": request.attempt_number,
                    "status": "SUCCESS",
                    "amount_minor": request.amount_minor,
                    "currency": request.currency,
                    "attempt_created_at": now.isoformat().replace("+00:00", "Z"),
                    "failure_code": None,
                    "debit_id": debit_id,
                    "reversal_id": None,
                },
                context=context,
                aggregate_type="payment_attempt",
                aggregate_id=payment_id,
                aggregate_version=1,
                event_time=now,
            )
        else:
            failure_code = random.choice(
                [
                    "SIMULATED_DECLINE",
                    "SIMULATED_TIMEOUT",
                    "SIMULATED_INSUFFICIENT_FUNDS",
                ]
            )
            tx.execute(
                """
                UPDATE payment_attempts
                SET status = 'FAILED', failure_code = %s, updated_at = %s
                WHERE namespace = %s AND payment_id = %s
                """,
                (failure_code, now, namespace, payment_id),
            )
            events.append(
                tx,
                event_type="PAYMENT_FAILED",
                payload={
                    "payment_id": payment_id,
                    "order_id": request.order_id,
                    "attempt_number": request.attempt_number,
                    "status": "FAILED",
                    "amount_minor": request.amount_minor,
                    "currency": request.currency,
                    "attempt_created_at": now.isoformat().replace("+00:00", "Z"),
                    "failure_code": failure_code,
                    "debit_id": None,
                    "reversal_id": None,
                },
                context=context,
                aggregate_type="payment_attempt",
                aggregate_id=payment_id,
                aggregate_version=1,
                event_time=now,
            )

        tx.execute(
            "UPDATE payment_orders SET updated_at = %s WHERE namespace = %s AND order_id = %s",
            (now, namespace, request.order_id),
        )

    return _attempt_snapshot(tx, namespace, payment_id)


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
    now = datetime.now(UTC)

    with db.transaction() as tx:
        po = tx.execute(
            """
            SELECT quiesced FROM payment_orders
            WHERE namespace = %s AND order_id = %s
            FOR UPDATE
            """,
            (namespace, order_id),
        ).fetchone()
        if po is None:
            tx.execute(
                """
                INSERT INTO payment_orders (namespace, order_id, quiesced, created_at, updated_at)
                VALUES (%s, %s, true, %s, %s)
                ON CONFLICT (namespace, order_id) DO UPDATE SET quiesced = true, updated_at = %s
                """,
                (namespace, order_id, now, now, now),
            )
            return {"attempts": [], "quiesced": True, "net_debit_minor": 0}

        if not po["quiesced"]:
            tx.execute(
                "UPDATE payment_orders SET quiesced = true, updated_at = %s WHERE namespace = %s AND order_id = %s",
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
                    INSERT INTO ledger_entries (namespace, entry_id, payment_id, kind, amount_minor, currency, created_at)
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
        SELECT COALESCE(SUM(CASE WHEN kind = 'DEBIT' THEN amount_minor ELSE -amount_minor END), 0) AS net
        FROM ledger_entries
        WHERE namespace = %s AND payment_id = ANY(%s)
        """,
        (namespace, payment_ids),
    ).fetchone()
    return max(0, rows["net"])
