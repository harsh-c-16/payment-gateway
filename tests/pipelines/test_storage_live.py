"""Opt-in real Linux volume, PostgreSQL and Kafka capture checks; no outbox double."""

import json
import os
from pathlib import Path
from time import monotonic
from uuid import uuid4

import psycopg
import pytest
from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient, NewTopic
from psycopg import sql

import pipelines.ingestion.receipts as receipts_module
from pipelines.ingestion import BronzeCapture, SourceCorruption, read_bronze
from pipelines.ingestion.receipts import load_capture, migrate_analytics, persist_capture
from pipelines.storage import FileStore
from shared.event_transport.consumer import ConsumerGroup

from .test_storage import source

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_STORAGE_LIVE_TESTS") != "1",
    reason="RUN_STORAGE_LIVE_TESTS=1 requires the Linux storage-check container and real services",
)


@pytest.fixture
def database():
    password = Path("/run/secrets/analytics_password").read_text().strip()
    tx = psycopg.connect(
        host=os.environ["STORAGE_TEST_POSTGRES_HOST"],
        dbname="analytics_db",
        user="analytics_user",
        password=password,
        autocommit=True,
    )
    schema = "m04_test_" + uuid4().hex
    tx.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    tx.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    try:
        with tx.transaction():
            migrate_analytics(tx)
        yield tx
    finally:
        tx.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        tx.close()


@pytest.fixture
def volume():
    root = Path(os.environ["LAKEHOUSE_ROOT"]) / ("m04-live-" + uuid4().hex)
    root.mkdir()
    return FileStore(root)


def test_real_sql_rollback_redelivery_conflict_and_restart_receipts(database, volume):
    capture = BronzeCapture(volume)
    receipt = capture.ingest_bronze([source()])
    with pytest.raises(ValueError, match="active caller-owned"):
        persist_capture(database, receipt, volume)
    with pytest.raises(RuntimeError, match="rollback"):
        with database.transaction():
            assert persist_capture(database, receipt, volume).new_sources == 1
            raise RuntimeError("explicit caller rollback")
    assert database.execute("SELECT count(*) FROM source_receipts").fetchone()[0] == 0
    assert volume.list_orphans(set()) == [receipt.files[0].path]
    with database.transaction():
        assert persist_capture(database, receipt, volume).new_sources == 1
        assert persist_capture(database, receipt, volume).redelivery_noop == 1
        assert load_capture(database, receipt.capture_id) == receipt
        migrate_analytics(database)  # verified migration retry
    duplicate = capture.ingest_bronze([source()])
    with database.transaction():
        assert persist_capture(database, duplicate, volume).redelivery_noop == 1
    first_locator = database.execute("SELECT raw_locator FROM source_receipts").fetchone()[0]
    assert first_locator == receipt.records[0].source.raw_locator
    # Same event bytes at a different offset are a NEW source; Silver dedup is M05.
    next_offset = capture.ingest_bronze([source(1)])
    with database.transaction():
        assert persist_capture(database, next_offset, volume).new_sources == 1
    corrupt = capture.ingest_bronze([source(0, b"changed")])
    with database.transaction():
        with pytest.raises(SourceCorruption):
            persist_capture(database, corrupt, volume)
        assert load_capture(database, corrupt.capture_id) is None  # savepoint rolled back
    rows = database.execute(
        "SELECT disposition,silver_committed_observed_at,gold_visible_at,timing_validity "
        "FROM source_receipts ORDER BY offset_number"
    ).fetchall()
    assert rows == [(None, None, None, "missing")] * 2
    # Reopen the actual file store and load the receipt from committed PostgreSQL.
    with database.transaction():
        recovered = load_capture(database, receipt.capture_id)
    assert read_bronze(FileStore(volume.root), recovered)[0].value_bytes == b"\xff{invalid"
    evidence = {
        "postgresql_version": database.info.server_version,
        "capture_id": receipt.capture_id,
        "volume_root": str(volume.root),
        "source_rows": 2,
        "caller_rollback": "PASS",
        "caught_conflict_rollback": "PASS",
        "first_locator_preserved": True,
        "final_dispositions": "NOT_RUN; capture only",
        "real_outbox": "NOT_RUN; not required by capture",
    }
    Path("artifacts/m04/sql-capture.json").write_text(json.dumps(evidence, indent=2))


def test_real_migration_drift_is_rejected(database, tmp_path, monkeypatch):
    windows_copy = tmp_path / "capture-crlf.sql"
    windows_copy.write_bytes(
        receipts_module.MIGRATION.read_text(encoding="utf-8").replace("\n", "\r\n").encode()
    )
    monkeypatch.setattr(receipts_module, "MIGRATION", windows_copy)
    with database.transaction():
        migrate_analytics(database)  # Same migration with Windows line endings is a no-op.
    database.execute("UPDATE analytics_schema_migrations SET sha256=%s", ("0" * 64,))
    with database.transaction():
        with pytest.raises(SourceCorruption, match="checksum"):
            migrate_analytics(database)
    assert database.execute("SELECT count(*) FROM source_receipts").fetchone()[0] == 0


def test_real_kafka_capture_sql_does_not_advance_offsets(database, volume):
    namespace = "bench-m04-" + uuid4().hex
    topic = namespace + ".conversation-events.v1"
    bootstrap = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
    admin = AdminClient({"bootstrap.servers": bootstrap})
    for future in admin.create_topics(
        [NewTopic(topic, 1, 1, config={"retention.ms": "604800000"})]
    ).values():
        future.result(30)
    producer = Producer({"bootstrap.servers": bootstrap, "enable.idempotence": True, "acks": "all"})
    payloads = [b"\xff\x00invalid", b'{"synthetic_capture_fixture":true}', None]
    errors = []
    for value in payloads:
        producer.produce(
            topic,
            value=value,
            key=b"",
            headers=[("x", None), ("x", b"")],
            on_delivery=lambda error, _: errors.append(error),
        )
    assert producer.flush(15) == 0 and errors == [None] * 3
    worker = ConsumerGroup(namespace + ".analytics.v1", [topic], bootstrap)
    try:
        records = []
        deadline = monotonic() + 40
        while len(records) < 3 and monotonic() < deadline:
            records.extend(worker.consume_records([topic], 3 - len(records), 100))
        assert len(records) == 3
        receipt = BronzeCapture(volume).ingest_bronze(records)
        with database.transaction():
            assert persist_capture(database, receipt, volume).new_sources == 3
        decoded = read_bronze(volume, receipt)
        assert [r.value_bytes for r in decoded] == payloads
        assert all(r.headers == (("x", None), ("x", b"")) for r in decoded)
        assert worker.durable_next_offsets() == {}
        assert not worker.commit_offsets({(topic, 0): records[-1].offset + 1}).succeeded
        # Actual broker group query proves that no capture-only offset was committed.
        from confluent_kafka import TopicPartition

        committed = worker.consumer.committed([TopicPartition(topic, 0)], timeout=10)[0].offset
        assert committed < 0
        Path("artifacts/m04/kafka-capture.json").write_text(
            json.dumps(
                {
                    "namespace": namespace,
                    "source_offsets": [r.offset for r in records],
                    "capture_id": receipt.capture_id,
                    "volume_root": str(volume.root),
                    "broker_committed_offset": committed,
                    "capture_only_commit_rejected": True,
                    "source_hashes": [r.raw_sha256 for r in records],
                    "exact_bytes": "PASS",
                },
                indent=2,
            )
        )
    finally:
        worker.close()
