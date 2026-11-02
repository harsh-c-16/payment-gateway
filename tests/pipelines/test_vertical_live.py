"""M05 real SQL/files/API tests. Outbox doubles are explicit; native Kafka is separate."""

import errno
import json
import os
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from pipelines.curation import AnalyticsPipeline
from pipelines.ingestion import BronzeCapture
from pipelines.ingestion.receipts import migrate_analytics
from pipelines.storage import FileStore
from pipelines.storage.readers import receipts
from shared.contracts.events import SourceRecord
from shared.event_transport.codec import EventCodec
from shared.event_transport.consumer import raw_fingerprint
from shared.event_transport.schemas import SchemaCache
from shared.local_diagnostics import OutboxUnavailable

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_VERTICAL_LIVE_TESTS") != "1",
    reason="RUN_VERTICAL_LIVE_TESTS=1 requires Linux volume and real analytics PostgreSQL",
)


@pytest.fixture
def vertical():
    params = dict(
        host=os.environ["STORAGE_TEST_POSTGRES_HOST"],
        dbname="analytics_db",
        user="analytics_user",
        password=Path("/run/secrets/analytics_password").read_text().strip(),
        autocommit=True,
    )
    schema = "m05_" + uuid4().hex
    admin = psycopg.connect(**params)
    admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

    def connect():
        return psycopg.connect(**params, options=f"-csearch_path={schema} -ctimezone=UTC")

    root = Path(os.environ["LAKEHOUSE_ROOT"]) / schema
    root.mkdir()
    with connect() as tx, tx.transaction():
        migrate_analytics(tx)
    codec = EventCodec(SchemaCache.load("/app/schema-cache.json"), source_service="conversation")
    pipeline = AnalyticsPipeline(
        connect, FileStore(root), codec, code_commit=os.environ["M05_CODE_COMMIT"]
    )
    pipeline.test_namespace = "bench-m05-" + uuid4().hex
    pipeline.test_session = str(uuid4())
    pipeline.test_event_time = datetime.now(UTC).replace(second=0, microsecond=0)
    try:
        yield pipeline
    finally:
        admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        admin.close()


def event(pipeline, version=1, event_time=None):
    return pipeline.codec.build_event(
        "CONVERSATION_TURN",
        {
            "turn_id": str(uuid4()),
            "mode": "fixed",
            "outcome": "success",
            "duration_ms": 1.25,
            "llm_call_count": 0,
            "extractor_source": "rules",
        },
        {
            "namespace": pipeline.test_namespace,
            "run_id": "m05-explicit-synthetic-fixture",
            "user_id": "synthetic-user",
            "session_id": pipeline.test_session,
            "correlation_id": str(uuid4()),
        },
        "session",
        pipeline.test_session,
        version,
        event_time or pipeline.test_event_time,
        metadata={"synthetic": True, "scenario_source": "simulation", "future_hint": None},
    )


def record(pipeline, value, offset=0):
    raw, headers, topic, key = pipeline.codec.encode(value)
    key = key.encode() if isinstance(key, str) else key
    return SourceRecord(
        pipeline.test_namespace,
        topic,
        0,
        offset,
        key,
        raw,
        tuple(headers),
        None,
        datetime.now(UTC),
        raw_fingerprint(key, raw, tuple(headers)),
    )


def curate(pipeline, records):
    raw = BronzeCapture(pipeline.store).ingest_bronze(records)
    return pipeline.curate_silver(raw, {"run_id": "m05-explicit-synthetic-fixture"})


def query(pipeline):
    now = datetime.now(UTC).date()
    return pipeline.query_gold(
        pipeline.test_namespace, "pipeline_minute", now - timedelta(days=2), now + timedelta(days=1)
    )


def count(pipeline, table):
    assert table in {
        "silver_events",
        "pipeline_minute",
        "quarantine",
        "test_outbox_double",
        "export_pending",
    }
    with pipeline.connect() as tx:
        return tx.execute(
            sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
        ).fetchone()[0]


@pytest.fixture
def outbox_double(vertical, monkeypatch):
    with vertical.connect() as tx:
        tx.execute(
            "CREATE TABLE test_outbox_double(event_id uuid PRIMARY KEY,payload jsonb NOT NULL)"
        )
    module = ModuleType("shared.outbox")

    def append(tx, notice):
        vertical.codec.encode(notice)  # Validate the actual registered DLQ wire schema.
        tx.execute(
            "INSERT INTO test_outbox_double VALUES (%s,%s)",
            (notice.event_id, Jsonb(notice.model_dump(mode="json"))),
        )

    module.append_outbox = append
    monkeypatch.setitem(sys.modules, "shared.outbox", module)
    return module


def test_real_valid_duplicate_redelivery_and_active_gold(vertical):
    first = event(vertical)
    initial = record(vertical, first)
    assert curate(vertical, [initial]).new_valid == 1
    assert vertical.publish_snapshot(vertical.test_namespace).generation == 1
    assert query(vertical).rows[0]["unique_events"] == 1
    assert curate(vertical, [record(vertical, first, 1)]).duplicate_delivery == 1
    assert curate(vertical, [replace(initial, ingested_at=datetime.now(UTC))]).redelivery_noop == 1
    assert vertical.publish_snapshot(vertical.test_namespace).generation == 1
    assert count(vertical, "silver_events") == 1 and count(vertical, "pipeline_minute") == 1
    page = receipts(vertical.connect, vertical.test_namespace)
    latest = {r.source.offset: r for r in page.receipts}
    assert len(latest) == 2 and latest[0].disposition == "new_valid"
    assert latest[1].disposition == "duplicate_delivery"
    assert all(
        r.gold_visible_at and r.silver_committed_observed_at and r.timing_validity == "observed"
        for r in latest.values()
    )
    assert latest[0].ingested_at == initial.ingested_at
    lineage = json.loads(
        vertical.store.read(
            vertical.active_manifest(vertical.test_namespace, "gold").input_manifest_ids[0]
        )
    )
    assert lineage["format_version"] == 2 and len(lineage["membership_files"]) == 1
    part = lineage["membership_files"][0]
    members = json.loads(vertical.store.read(part["path"]))
    assert members["event_ids"] == [first.event_id] and len(members["sources"]) == 1
    Path("artifacts/m05/valid-slice.json").write_text(
        json.dumps(
            {
                "namespace": vertical.test_namespace,
                "gold_generation": 1,
                "unique_events": 1,
                "new_valid": 1,
                "duplicate_delivery": 1,
                "redelivery_noop": 1,
                "real_outbox": "NOT_RUN; absent",
                "root": str(vertical.store.root),
            },
            indent=2,
        )
    )


def test_real_missing_outbox_leaves_invalid_source_pending(vertical):
    good = record(vertical, event(vertical))
    invalid = replace(
        good, value_bytes=b"\xff", raw_sha256=raw_fingerprint(good.key_bytes, b"\xff", good.headers)
    )
    with pytest.raises(OutboxUnavailable):
        curate(vertical, [invalid])
    assert count(vertical, "silver_events") == 0 and count(vertical, "quarantine") == 0
    with vertical.connect() as tx:
        assert tx.execute("SELECT disposition FROM source_receipts").fetchone()[0] is None


def test_real_quarantine_rollback_and_duplicate_identity_conflicts(
    vertical, outbox_double, monkeypatch
):
    first = event(vertical)
    curate(vertical, [record(vertical, first)])
    changed = first.model_copy(update={"payload": {**first.payload, "duration_ms": 2.0}})
    assert curate(vertical, [record(vertical, changed, 1)]).invalid == 1
    assert curate(vertical, [record(vertical, event(vertical), 2)]).invalid == 1
    assert count(vertical, "silver_events") == 1
    assert count(vertical, "quarantine") == count(vertical, "test_outbox_double") == 2
    metrics = vertical.telemetry.exposition()
    assert b'quarantine_total{reason="EVENT_ID_CONFLICT"} 1.0\n' in metrics
    assert b'quarantine_total{reason="AGGREGATE_VERSION_CONFLICT"} 1.0\n' in metrics
    original = outbox_double.append_outbox

    def fail(*args):
        raise RuntimeError("explicit outbox double append failure")

    monkeypatch.setattr(outbox_double, "append_outbox", fail)
    bad = record(vertical, event(vertical, 2), 3)
    bad = replace(
        bad,
        value_bytes=b"{broken",
        raw_sha256=raw_fingerprint(bad.key_bytes, b"{broken", bad.headers),
    )
    with pytest.raises(RuntimeError, match="explicit outbox"):
        curate(vertical, [bad])
    assert vertical.telemetry.exposition() == metrics
    assert count(vertical, "quarantine") == 2
    with vertical.connect() as tx:
        assert (
            tx.execute("SELECT disposition FROM source_receipts WHERE offset_number=3").fetchone()[
                0
            ]
            is None
        )
    monkeypatch.setattr(outbox_double, "append_outbox", original)
    assert curate(vertical, [bad]).invalid == 1
    assert count(vertical, "quarantine") == count(vertical, "test_outbox_double") == 3
    assert curate(vertical, [bad]).redelivery_noop == 1
    assert b'quarantine_total{reason="INVALID_JSON"} 1.0\n' in vertical.telemetry.exposition()


def test_real_publication_disk_failure_preserves_pointer_and_pending(vertical, monkeypatch):
    curate(vertical, [record(vertical, event(vertical))])
    vertical.publish_snapshot(vertical.test_namespace)
    curate(vertical, [record(vertical, event(vertical, 2), 1)])
    original = vertical.store.write_immutable

    def full(path, *args):
        if path.startswith("gold/"):
            raise OSError(errno.ENOSPC, "explicit publication disk-full fault")
        return original(path, *args)

    monkeypatch.setattr(vertical.store, "write_immutable", full)
    with pytest.raises(OSError):
        vertical.publish_snapshot(vertical.test_namespace)
    assert vertical.active_manifest(vertical.test_namespace, "gold").generation == 1
    assert count(vertical, "export_pending") == 1 and query(vertical).rows[0]["unique_events"] == 1
    monkeypatch.setattr(vertical.store, "write_immutable", original)
    assert vertical.publish_snapshot(vertical.test_namespace).generation == 2
    assert query(vertical).rows[0]["unique_events"] == 2


def test_real_postcommit_observation_failure_recovers_as_upper_bound(vertical, monkeypatch):
    initial = record(vertical, event(vertical))
    original = vertical._observe

    def lost(*args):
        raise RuntimeError("explicit post-COMMIT observation fault")

    monkeypatch.setattr(vertical, "_observe", lost)
    with pytest.raises(RuntimeError):
        curate(vertical, [initial])
    assert count(vertical, "silver_events") == 1
    monkeypatch.setattr(vertical, "_observe", original)
    assert curate(vertical, [initial]).redelivery_noop == 1
    monkeypatch.setattr(vertical, "_observe", lost)
    with pytest.raises(RuntimeError):
        vertical.publish_snapshot(vertical.test_namespace)
    assert query(vertical).generation == 1  # Active data precedes its timing observation.
    monkeypatch.setattr(vertical, "_observe", original)
    assert vertical.recover_observations(vertical.test_namespace) == 1
    assert all(
        r.timing_validity == "recovery_upper_bound"
        for r in receipts(vertical.connect, vertical.test_namespace).receipts
    )
