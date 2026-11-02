"""T-09 on real PostgreSQL: the common Appendix B vector, redelivery, gaps and deferred SKUs."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest

from pipelines.catalog import adapter
from projectctl.models import ExitCode
from projectctl.providers import Invocation
from services.catalog import projection, worker
from shared.event_transport import ConsumerGroup
from shared.event_transport.codec import EventCodec
from shared.local_diagnostics import quarantine_local_diagnostic
from tests.catalog.helpers import apply_record, import_rows, row, source_record, stock_record
from tests.pipelines.transport_doubles import ConsumerDouble, MessageDouble, offline_cache

CODEC = EventCodec(offline_cache(), source_service="inventory")


@pytest.fixture
def world(tmp_path, database_url, outbox_double):
    namespace = "bench-h-" + uuid4().hex[:16]
    import_rows(tmp_path, database_url, namespace, [row("A1"), row("A2")])
    return namespace


def apply(db, namespace, version, on_hand, reserved, offset, sku="FK-A1"):
    record = stock_record(CODEC, namespace, sku, version, on_hand, reserved, offset=offset)
    return apply_record(db, CODEC, record, quarantine_local_diagnostic)


def state(db, namespace, sku="FK-A1"):
    with db.transaction() as tx:
        return tx.execute(
            "SELECT stock_version,on_hand,reserved,available FROM stock_projection "
            "WHERE namespace=%s AND sku=%s",
            (namespace, sku),
        ).fetchone()


def receipts(db, namespace):
    with db.transaction() as tx:
        return tx.execute(
            'SELECT "offset",outcome,previous_version,current_version,version_gap '
            'FROM projection_receipts WHERE namespace=%s ORDER BY "offset"',
            (namespace,),
        ).fetchall()


def test_appendix_b_stale_duplicate_and_conflict_vector(world, db, outbox_double):
    namespace = world
    assert apply(db, namespace, 1, 10, 0, 1).outcome == "applied"
    assert apply(db, namespace, 3, 10, 3, 2).outcome == "applied"
    assert apply(db, namespace, 2, 10, 2, 3).outcome == "stale"
    assert apply(db, namespace, 3, 10, 3, 4).outcome == "duplicate"
    assert apply(db, namespace, 3, 10, 4, 5).outcome == "conflict"
    assert state(db, namespace) == {
        "stock_version": 3,
        "on_hand": 10,
        "reserved": 3,
        "available": 7,
    }
    assert [r["outcome"] for r in receipts(db, namespace)] == [
        "applied",
        "applied",
        "stale",
        "duplicate",
        "conflict",
    ]
    with db.transaction() as tx:
        diagnostics = tx.execute(
            "SELECT reason_code FROM local_diagnostics WHERE namespace=%s", (namespace,)
        ).fetchall()
    assert [d["reason_code"] for d in diagnostics] == ["AGGREGATE_VERSION_CONFLICT"]
    assert len(outbox_double) == 1


def test_version_gap_is_recorded_and_newer_snapshot_still_applies(world, db):
    namespace = world
    apply(db, namespace, 1, 10, 0, 1)
    apply(db, namespace, 5, 9, 1, 2)
    rows = receipts(db, namespace)
    assert [r["version_gap"] for r in rows] == [False, True]
    assert state(db, namespace)["stock_version"] == 5


def test_redelivered_offset_and_republished_event_are_noops(world, db):
    namespace = world
    record = stock_record(CODEC, namespace, "FK-A1", 1, 10, 0, offset=7)
    assert apply_record(db, CODEC, record, quarantine_local_diagnostic).outcome == "applied"
    assert apply_record(db, CODEC, record, quarantine_local_diagnostic).outcome == "duplicate"
    event = CODEC.cache.validate(
        record.value_bytes, record.headers, record.topic, record.key_bytes
    ).envelope
    moved = source_record(CODEC, event, namespace, 8)
    assert apply_record(db, CODEC, moved, quarantine_local_diagnostic).outcome == "duplicate"
    assert [r["outcome"] for r in receipts(db, namespace)] == ["applied", "duplicate"]
    assert state(db, namespace)["stock_version"] == 1


def test_same_event_id_with_changed_content_is_a_conflict(world, db):
    namespace = world
    record = stock_record(CODEC, namespace, "FK-A1", 1, 10, 0, offset=7)
    apply_record(db, CODEC, record, quarantine_local_diagnostic)
    event = CODEC.cache.validate(
        record.value_bytes, record.headers, record.topic, record.key_bytes
    ).envelope
    changed = event.model_copy(
        update={"payload": {**event.payload, "on_hand": 11, "available": 11}}
    )
    moved = source_record(CODEC, changed, namespace, 8)
    assert apply_record(db, CODEC, moved, quarantine_local_diagnostic).outcome == "conflict"
    assert state(db, namespace)["on_hand"] == 10


def test_synthetic_benchmark_facts_cannot_move_real_stock(world, db):
    namespace = world
    record = stock_record(CODEC, namespace, "FK-A1", 1, 10, 0, offset=1, source="benchmark")
    assert apply_record(db, CODEC, record, quarantine_local_diagnostic).outcome == "conflict"
    assert state(db, namespace) is None


def test_unknown_sku_defers_durably_then_reconciles(tmp_path, database_url, db, world):
    namespace = world
    outcome = apply(db, namespace, 2, 8, 1, 1, sku="FK-LATE")
    assert outcome.outcome == "deferred"
    assert state(db, namespace, "FK-LATE") is None
    with db.transaction() as tx:
        assert projection.reconcile_deferred(tx, namespace) == 0
    import_rows(tmp_path, database_url, namespace, [row("A1"), row("A2"), row("LATE")])
    with db.transaction() as tx:
        assert projection.reconcile_deferred(tx, namespace) == 1
    assert state(db, namespace, "FK-LATE")["available"] == 7


def test_deferred_snapshot_cannot_regress_a_newer_applied_version(
    tmp_path, database_url, db, world
):
    namespace = world
    apply(db, namespace, 2, 8, 1, 1, sku="FK-LATE")
    import_rows(tmp_path, database_url, namespace, [row("A1"), row("A2"), row("LATE")])
    apply(db, namespace, 5, 3, 0, 2, sku="FK-LATE")
    with db.transaction() as tx:
        projection.reconcile_deferred(tx, namespace)
    assert state(db, namespace, "FK-LATE")["stock_version"] == 5


def test_malformed_record_keeps_a_diagnostic_and_advances(world, db):
    namespace = world
    good = stock_record(CODEC, namespace, "FK-A1", 1, 10, 0, offset=1)
    event = CODEC.cache.validate(
        good.value_bytes, good.headers, good.topic, good.key_bytes
    ).envelope
    bad = source_record(CODEC, event, namespace, 2, raw=b"{not json")
    marked = []
    metrics = worker.telemetry()
    for _ in range(2):  # the second pass is a Kafka redelivery of both offsets
        worker.process_batch(
            db,
            [good, bad],
            validate=CODEC.validate_event,
            diagnostics=quarantine_local_diagnostic,
            run_id="h-test",
            metrics=metrics,
            mark=marked.append,
        )
    assert [r.offset for r in marked] == [1, 2, 1, 2]
    assert [r["outcome"] for r in receipts(db, namespace)] == ["applied", "invalid"]
    with db.transaction() as tx:
        rows = tx.execute(
            "SELECT reason_code FROM local_diagnostics WHERE namespace=%s", (namespace,)
        ).fetchall()
        observed = tx.execute(
            "SELECT count(*) AS n FROM projection_receipts "
            "WHERE namespace=%s AND observed_commit_at IS NOT NULL",
            (namespace,),
        ).fetchone()
    assert [r["reason_code"] for r in rows] == ["INVALID_JSON"]
    assert observed["n"] == 2
    assert 'projection_apply_total{outcome="applied"} 1.0' in metrics.exposition().decode()


def test_commit_failure_before_mark_means_redelivery_not_loss(world, db):
    """A crash after the projection commit but before the offset commit replays harmlessly."""
    namespace = world
    record = stock_record(CODEC, namespace, "FK-A1", 1, 10, 0, offset=1)

    def crash(_):
        raise RuntimeError("process died before the offset advanced")

    with pytest.raises(RuntimeError):
        worker.process_batch(
            db,
            [record],
            validate=CODEC.validate_event,
            diagnostics=quarantine_local_diagnostic,
            run_id="h-test",
            metrics=worker.telemetry(),
            mark=crash,
        )
    assert state(db, namespace)["stock_version"] == 1
    assert apply_record(db, CODEC, record, quarantine_local_diagnostic).outcome == "duplicate"
    assert state(db, namespace)["stock_version"] == 1


def test_concurrent_versions_for_one_sku_settle_on_the_highest(world, db):
    namespace = world
    records = [
        stock_record(CODEC, namespace, "FK-A1", version, 100, version, offset=version)
        for version in range(1, 21)
    ]

    def one(record):
        return apply_record(db, CODEC, record, quarantine_local_diagnostic).outcome

    with ThreadPoolExecutor(6) as pool:
        outcomes = list(pool.map(one, records))
    assert state(db, namespace)["stock_version"] == 20
    assert set(outcomes) <= {"applied", "stale"}


def test_consumer_loop_commits_only_durable_prefix_and_restart_replays(world, db):
    """Real ConsumerGroup bookkeeping over Vichitr's labelled Kafka double, not a broker."""
    namespace = world
    records = [stock_record(CODEC, namespace, "FK-A1", v, 10, 0, offset=v - 1) for v in (1, 2, 3)]

    def deliver():
        doubles = []

        def factory(settings):
            consumer = ConsumerDouble(settings)
            consumer.messages.extend(
                MessageDouble(
                    r.topic, r.offset, value=r.value_bytes, key=r.key_bytes, headers=r.headers
                )
                for r in records
            )
            doubles.append(consumer)
            return consumer

        group = ConsumerGroup(
            f"{namespace}.catalog-projection.v1",
            [worker.topic_for(namespace)],
            "double:9092",
            consumer_factory=factory,
        )
        stop = Event()
        metrics = worker.telemetry()

        def stopping(*args, **kwargs):
            result = CODEC.validate_event(*args, **kwargs)
            if kwargs["source_record"].offset == 2:
                stop.set()
            return result

        worker.run(
            db,
            group,
            namespace,
            stop=stop,
            run_id="h-test",
            metrics=metrics,
            validate=stopping,
            diagnostics=quarantine_local_diagnostic,
        )
        return doubles[0], metrics

    consumer, metrics = deliver()
    assert state(db, namespace)["stock_version"] == 3
    assert max(item.offset for item in consumer.commits[-1]) == 3
    assert metrics.metrics["projection_age_seconds"]
    second, metrics = deliver()
    assert state(db, namespace)["stock_version"] == 3
    assert 'projection_apply_total{outcome="applied"}' not in metrics.exposition().decode()
    assert len(receipts(db, namespace)) == 3


def test_projection_wait_reports_missing_and_completes(
    tmp_path, database_url, db, world, monkeypatch
):
    namespace = world
    monkeypatch.setenv("CATALOG_DATABASE_URL", database_url)
    manifest = tmp_path / namespace / "sku_manifest.json"
    invocation = Invocation(
        "projection wait",
        {"sku_manifest": str(manifest), "namespace": namespace, "timeout_seconds": 1},
        None,
        str(uuid4()),
        namespace,
    )
    apply(db, namespace, 1, 10, 0, 1, sku="FK-A1")
    result = adapter.projection_wait_action(invocation)
    assert result.code == ExitCode.DEPENDENCY_FAILURE
    assert '"expected": 2, "projected": 1' in result.reasons[0]
    apply(db, namespace, 1, 10, 0, 2, sku="FK-A2")
    assert adapter.projection_wait_action(invocation).code == ExitCode.COMPLETED
