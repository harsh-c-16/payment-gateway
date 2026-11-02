"""T-09 on real PostgreSQL: the common Appendix B vector, redelivery, gaps and deferred SKUs."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from services.catalog import projection
from shared.event_transport.codec import EventCodec
from shared.local_diagnostics import quarantine_local_diagnostic
from tests.catalog.helpers import apply_record, import_rows, row, source_record, stock_record
from tests.pipelines.transport_doubles import offline_cache

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
