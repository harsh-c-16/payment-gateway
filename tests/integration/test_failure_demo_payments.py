"""Real PostgreSQL plans; explicit registry fixture. No Kafka/integration claim here."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from services.payments import authorize
from shared.local_diagnostics.demo_controls import directory
from tests.transactions.test_async_payments import payments as payments
from tests.transactions.test_async_payments import request


@pytest.mark.parametrize(
    "scenario,delay,failure", [("late", 35_000, None), ("decline", 100, "DECLINED")]
)
def test_scoped_payment_plan_is_persisted_and_retry_does_not_replan(
    payments, tmp_path, monkeypatch, scenario, delay, failure
):
    db, events, context = payments
    monkeypatch.setenv("LOCAL_FAILURE_DEMOS_ENABLED", "true")
    monkeypatch.setenv("LOCAL_DEMO_CONTROL_ROOT", str(tmp_path))
    context = context.model_copy(update={"run_id": str(uuid4())})
    folder = directory("payments")
    folder.mkdir(parents=True)
    path = folder / (context.run_id + ".json")
    path.write_text(
        json.dumps(
            {
                "run_id": context.run_id,
                "namespace": context.namespace,
                "scenario": scenario,
                "expires_at": (datetime.now(UTC) + timedelta(seconds=60)).isoformat(),
            }
        )
    )
    body = request()
    first = authorize.authorize(db, events, context.namespace, body, context)
    path.unlink()
    retry = authorize.authorize(db, events, context.namespace, body, context)
    assert retry["payment_id"] == first["payment_id"]
    with db.transaction() as tx:
        rows = tx.execute(
            "SELECT created_at,completion_due_at,planned_failure_code FROM payment_attempts"
        ).fetchall()
        assert len(rows) == 1
        assert (
            round((rows[0]["completion_due_at"] - rows[0]["created_at"]).total_seconds() * 1000)
            == delay
        )
        assert rows[0]["planned_failure_code"] == failure
        assert tx.execute("SELECT count(*) AS n FROM ledger_entries").fetchone()["n"] == 0
