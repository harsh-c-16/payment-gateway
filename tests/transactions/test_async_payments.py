"""Real PostgreSQL 18 state/locks; explicit offline registry fixture, no Kafka claim."""

import os
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from threading import Barrier, Event
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

import shared.event_transport as sdk
from benchmarks.workloads import generate_workload
from services.orders import m3_setup
from services.payments import authorize
from services.payments.database import Database
from services.payments.errors import ServiceError
from services.payments.events import PaymentEvents
from shared.contracts.common import RequestContext
from shared.contracts.transactions import AuthorizePaymentRequest
from shared.event_transport.codec import EventCodec
from tests.pipelines.transport_doubles import offline_cache


@pytest.fixture
def payments(monkeypatch):
    url = os.environ.get("INVENTORY_TEST_DATABASE_URL")
    if not url:
        pytest.skip("NOT_RUN: INVENTORY_TEST_DATABASE_URL required for PostgreSQL 18")
    schema = "m3_payment_" + uuid4().hex
    with psycopg.connect(url, autocommit=True) as admin:
        assert 180000 <= admin.info.server_version < 190000
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    database_url = make_conninfo(url, options=f"-c search_path={schema}")
    try:
        assert m3_setup.setup("payments", database_url)["applied"] == [
            "001_payments.sql",
            "003_async_completion.sql",
        ]
        assert m3_setup.setup("payments", database_url)["applied"] == []
        monkeypatch.setattr(sdk, "_codec", EventCodec(offline_cache(), dataset_revision="test"))
        events = PaymentEvents()
        events.configured = True
        context = RequestContext(
            namespace="bench-payment-" + uuid4().hex[:10],
            run_id="original-payment-run",
            user_id="payment-test",
            correlation_id=str(uuid4()),
            request_id=str(uuid4()),
            session_id=str(uuid4()),
        )
        yield Database(database_url), events, context
    finally:
        with psycopg.connect(url, autocommit=True) as admin:
            assert schema.startswith("m3_payment_")
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def request(order_id=None, attempt=1, amount=5000):
    return AuthorizePaymentRequest(
        order_id=order_id or str(uuid4()),
        attempt_number=attempt,
        amount_minor=amount,
        currency="INR",
    )


def ready(db):
    # Synchronize against the stored database due time; no test changes business state.
    with db.transaction() as tx:
        wait = tx.execute(
            "SELECT greatest(0, extract(epoch FROM max(completion_due_at) "
            "- clock_timestamp())) AS wait FROM payment_attempts"
        ).fetchone()["wait"]
    time.sleep(float(wait or 0) + 0.005)


def ledger(db):
    with db.transaction() as tx:
        return tx.execute("SELECT kind,amount_minor FROM ledger_entries ORDER BY kind").fetchall()


def test_pending_plan_survives_restart_and_completes_once_after_100ms(payments, monkeypatch):
    db, events, ctx = payments
    monkeypatch.setattr(authorize.random, "random", lambda: 0.9)
    req = request()
    pending = authorize.authorize(db, events, ctx.namespace, req, ctx)
    assert pending["status"] == "PENDING" and ledger(db) == []
    due = {
        "namespace": ctx.namespace,
        "order_id": req.order_id,
        "payment_id": pending["payment_id"],
    }
    # Real lock + database clock reject an early callback, even if dispatched incorrectly.
    assert authorize._complete_payment(db, events, due) == 0
    assert (
        authorize.authorize(db, events, ctx.namespace, req, ctx)["payment_id"]
        == pending["payment_id"]
    )
    ready(db)
    restarted = Database(db.url)
    assert authorize.complete_pending_payments(restarted, events) == 1
    assert authorize.complete_pending_payments(restarted, events) == 0
    assert ledger(db) == [{"kind": "DEBIT", "amount_minor": 5000}]
    with db.transaction() as tx:
        row = tx.execute(
            "SELECT created_at,updated_at,completion_due_at FROM payment_attempts"
        ).fetchone()
        assert row["updated_at"] >= row["completion_due_at"]
        assert row["completion_due_at"] - row["created_at"] >= timedelta(milliseconds=100)
        event = tx.execute(
            "SELECT convert_from(payload,'UTF8')::jsonb AS event FROM outbox"
        ).fetchone()["event"]
        assert event["run_id"] == ctx.run_id
        assert event["correlation_id"] == ctx.correlation_id
        assert event["payload"]["failure_code"] is None


@pytest.mark.parametrize("seed", [0, 42, 314159])
def test_all_frozen_scenarios_match_independent_workload_expectations(seed):
    workload = generate_workload(
        "W-CHECKOUT",
        seed,
        {"active_skus": ["FK-A"]},
        key_count=1,
        templates=[{"scenario_id": "cart", "sku": "FK-A"}],
    )
    rows = list(workload.records())
    for row in rows:
        control = {"X-Benchmark-Scenario-ID": row["scenario_id"], "X-Benchmark-Seed": str(seed)}
        expected = "DECLINED" if row["payload"]["payment_outcome"] == "decline" else None
        assert authorize.scenario_failure(control) == expected


def test_real_100_attempt_cohort_is_95_success_5_decline_and_identity_is_immutable(
    payments, monkeypatch
):
    db, events, ctx = payments
    monkeypatch.setenv("BENCHMARK_MODE", "true")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    for index in range(100):
        control = {
            "X-Benchmark-Scenario-ID": f"measurement:{index:06}:cart",
            "X-Benchmark-Seed": "42",
        }
        req = request()
        pending = authorize.authorize(
            db, events, ctx.namespace, req, ctx, benchmark_headers=control
        )
        assert pending["status"] == "PENDING"
        assert (
            authorize.authorize(db, events, ctx.namespace, req, ctx, benchmark_headers=control)
            == pending
        )
        with pytest.raises(ServiceError):
            authorize.authorize(db, events, ctx.namespace, request(req.order_id, amount=5001), ctx)
    ready(db)
    assert authorize.complete_pending_payments(db, events) == 100
    with db.transaction() as tx:
        counts = {
            r["status"]: r["n"]
            for r in tx.execute(
                "SELECT status,count(*) AS n FROM payment_attempts GROUP BY status"
            ).fetchall()
        }
        assert counts == {"SUCCESS": 95, "FAILED": 5}
        assert tx.execute("SELECT count(*) AS n FROM ledger_entries").fetchone()["n"] == 95
        assert (
            tx.execute(
                "SELECT DISTINCT failure_code FROM payment_attempts WHERE status='FAILED'"
            ).fetchone()["failure_code"]
            == "DECLINED"
        )
    assert authorize.complete_pending_payments(db, events) == 0


@pytest.mark.parametrize("state", ["PENDING", "SUCCESS", "DECLINED", "RETRYABLE_PROVIDER_FAILURE"])
def test_second_attempt_requires_definitive_retryable_failure(payments, monkeypatch, state):
    db, events, ctx = payments
    monkeypatch.setattr(authorize.random, "random", lambda: 0.9)
    req = request()
    pending = authorize.authorize(db, events, ctx.namespace, req, ctx)
    if state != "PENDING":
        # Explicit provider failure fixture; not an end-to-end simulator outcome.
        with db.transaction() as tx:
            tx.execute(
                "UPDATE payment_attempts SET planned_failure_code=%s WHERE payment_id=%s",
                (state if state not in {"SUCCESS"} else None, pending["payment_id"]),
            )
        ready(db)
        authorize.complete_pending_payments(db, events)
    if state == "RETRYABLE_PROVIDER_FAILURE":
        assert (
            authorize.authorize(db, events, ctx.namespace, request(req.order_id, 2), ctx)["status"]
            == "PENDING"
        )
    else:
        with pytest.raises(ServiceError):
            authorize.authorize(db, events, ctx.namespace, request(req.order_id, 2), ctx)


@pytest.mark.parametrize("winner", ["reverse", "complete", "race"])
def test_completion_reverse_serialization_and_repeated_callbacks(payments, monkeypatch, winner):
    db, events, ctx = payments
    monkeypatch.setattr(authorize.random, "random", lambda: 0.9)
    req = request()
    authorize.authorize(db, events, ctx.namespace, req, ctx)
    ready(db)

    def complete():
        return authorize.complete_pending_payments(db, events)

    def reverse():
        return authorize.reverse_payments(db, events, ctx.namespace, req.order_id, "test", ctx)

    if winner == "race":
        barrier = Barrier(2)

        def synchronized(callback):
            barrier.wait(timeout=5)
            return callback()

        with ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(synchronized, callback) for callback in (complete, reverse)]
            for future in futures:
                future.result(timeout=10)
    elif winner == "reverse":
        reverse()
        assert complete() == 0
    else:
        assert complete() == 1
        reverse()
    assert complete() == 0
    reverse()
    result = authorize.get_payment_order(db, ctx.namespace, req.order_id)
    assert result["quiesced"] is True and result["net_debit_minor"] == 0
    entries = ledger(db)
    assert entries in (
        [],
        [{"kind": "DEBIT", "amount_minor": 5000}, {"kind": "REVERSAL", "amount_minor": 5000}],
    )


def test_concurrent_completion_workers_create_one_event_and_debit(payments, monkeypatch):
    db, events, ctx = payments
    monkeypatch.setattr(authorize.random, "random", lambda: 0.9)
    authorize.authorize(db, events, ctx.namespace, request(), ctx)
    ready(db)
    barrier = Barrier(4)

    def complete():
        barrier.wait(timeout=5)
        return authorize.complete_pending_payments(db, events)

    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _: complete(), range(4)))
    assert sum(results) == 1
    assert ledger(db) == [{"kind": "DEBIT", "amount_minor": 5000}]
    with db.transaction() as tx:
        assert tx.execute("SELECT count(*) AS n FROM outbox").fetchone()["n"] == 1


def test_reverse_sees_attempt_created_while_creating_its_guard(payments, monkeypatch):
    """A missing-row lookup must not let a concurrent debit escape reversal."""
    db, events, ctx = payments
    monkeypatch.setattr(authorize.random, "random", lambda: 0.9)
    req = request()
    inserting, proceed = Event(), Event()

    class PausedGuardDatabase:
        @contextmanager
        def transaction(self):
            with db.transaction() as tx:

                class Connection:
                    def __getattr__(self, name):
                        return getattr(tx, name)

                    def execute(self, statement, parameters=None):
                        if "INSERT INTO payment_orders" in statement:
                            inserting.set()
                            assert proceed.wait(timeout=10)
                        return tx.execute(statement, parameters)

                yield Connection()

    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(
            authorize.reverse_payments,
            PausedGuardDatabase(),
            events,
            ctx.namespace,
            req.order_id,
            "concurrent-first-authorization",
            ctx,
        )
        try:
            assert inserting.wait(timeout=5)
            authorize.authorize(db, events, ctx.namespace, req, ctx)
            ready(db)
            assert authorize.complete_pending_payments(db, events) == 1
        finally:
            proceed.set()
        result = future.result(timeout=10)
    assert result["quiesced"] is True
    assert result["net_debit_minor"] == 0
    assert [a["status"] for a in result["attempts"]] == ["REVERSED"]
    assert ledger(db) == [
        {"kind": "DEBIT", "amount_minor": 5000},
        {"kind": "REVERSAL", "amount_minor": 5000},
    ]
    with db.transaction() as tx:
        times = tx.execute(
            "SELECT kind,created_at FROM ledger_entries ORDER BY created_at,kind"
        ).fetchall()
    assert [row["kind"] for row in times] == ["DEBIT", "REVERSAL"]
