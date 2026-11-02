"""Real SQL/file transaction audits; outbox and elapsed-clock doubles are explicit."""

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from confluent_kafka import TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic

import pipelines.curation as curation
from pipelines.curation.db import rows
from pipelines.curation.sink_observations import read_sink_batches
from pipelines.ingestion import BronzeCapture
from pipelines.ingestion.receipts import migrate_analytics
from shared.event_transport.consumer import ConsumerGroup, raw_fingerprint
from shared.event_transport.publisher import KafkaPublisher

from . import test_vertical_live as live
from .test_vertical_kafka_live import read_one
from .test_vertical_live import count, curate, event, query, record

vertical = live.vertical
outbox_double = live.outbox_double
RUN = "m05-explicit-synthetic-fixture"
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_VERTICAL_LIVE_TESTS") != "1",
    reason="RUN_VERTICAL_LIVE_TESTS=1 requires real PostgreSQL/Kafka and the Linux volume",
)


def test_committed_batches_reconcile_all_dispositions_and_page_scope(vertical, outbox_double):
    first = event(vertical)
    source = record(vertical, first)
    bad = record(vertical, event(vertical, 2), 2)
    bad = replace(
        bad, value_bytes=b"\xff", raw_sha256=raw_fingerprint(bad.key_bytes, b"\xff", bad.headers)
    )
    receipt = BronzeCapture(vertical.store).ingest_bronze([source, record(vertical, first, 1), bad])
    outcome = vertical.curate_silver(receipt, {"run_id": RUN})
    assert (outcome.new_valid, outcome.duplicate_delivery, outcome.invalid) == (1, 1, 1)
    assert curate(vertical, [source]).redelivery_noop == 1
    batches = read_sink_batches(vertical.connect, vertical.test_namespace, RUN, limit=2)
    batches += read_sink_batches(
        vertical.connect, vertical.test_namespace, RUN, after=batches[-1]["batch_sequence"], limit=2
    )
    assert len(batches) == 4
    assert all(b["batch_rows"] == 1 and b["timing_validity"] == "observed" for b in batches)
    for index, disposition in enumerate(
        ("new_valid", "duplicate_delivery", "invalid", "redelivery_noop")
    ):
        batch = batches[index]
        assert batch[disposition] == 1
        assert (
            sum(batch[d] for d in ("new_valid", "duplicate_delivery", "invalid", "redelivery_noop"))
            == 1
        )
        assert batch["sources"] == [
            dict(topic=source.topic, partition=0, offset=index if index < 3 else 0)
        ]
        assert batch["flush_duration_seconds"] >= 0
        assert batch["committed_observed_at"] >= batch["started_at"]
        assert batch["code_commit"] == vertical.code_commit and batch["replay_id"] is None
    assert all(str(b["capture_id"]) == receipt.capture_id for b in batches[:3])
    assert read_sink_batches(vertical.connect, vertical.test_namespace, "another-run") == []
    assert read_sink_batches(vertical.connect, "bench-another-namespace", RUN) == []
    vertical.publish_snapshot(vertical.test_namespace)
    assert query(vertical).rows[0]["unique_events"] == 1


def test_flush_elapsed_ends_at_commit_before_observation_work(vertical, monkeypatch):
    clock = [100.0]
    finalize, observe, receipt_observe = (
        vertical._finalize,
        curation.observe_sink_batch,
        vertical._observe,
    )

    def finalized(*args):
        result = finalize(*args)
        clock[0] += 0.125
        return result

    def observed(*args):
        clock[0] += 10  # Explicit clock double, not a delay or performance reading.
        return observe(*args)

    def receipts_observed(*args):
        clock[0] += 20
        return receipt_observe(*args)

    monkeypatch.setattr(curation, "monotonic", lambda: clock[0])
    monkeypatch.setattr(vertical, "_finalize", finalized)
    monkeypatch.setattr(curation, "observe_sink_batch", observed)
    monkeypatch.setattr(vertical, "_observe", receipts_observed)
    curate(vertical, [record(vertical, event(vertical))])
    batch = read_sink_batches(vertical.connect, vertical.test_namespace, RUN)[0]
    assert batch["flush_duration_seconds"] == 0.125
    metric = vertical.telemetry.exposition().decode()
    assert "sink_flush_duration_seconds_sum 0.125" in metric


def test_rollback_has_neither_final_disposition_nor_committed_batch(vertical, monkeypatch):
    finalize = vertical._finalize

    def fail(*args):
        finalize(*args)
        raise RuntimeError("explicit failure before sink commit")

    monkeypatch.setattr(vertical, "_finalize", fail)
    with pytest.raises(RuntimeError, match="before sink commit"):
        curate(vertical, [record(vertical, event(vertical))])
    assert read_sink_batches(vertical.connect, vertical.test_namespace, RUN) == []
    assert count(vertical, "silver_events") == 0
    with vertical.connect() as tx:
        assert tx.execute("SELECT disposition FROM source_receipts").fetchone() == (None,)


def test_lost_commit_timer_stays_missing_after_recovery_and_redelivery(vertical, monkeypatch):
    observe = curation.observe_sink_batch

    def lost(*args):
        raise RuntimeError("explicit lost post-COMMIT sample")

    source = record(vertical, event(vertical))
    monkeypatch.setattr(curation, "observe_sink_batch", lost)
    with pytest.raises(RuntimeError, match="post-COMMIT"):
        curate(vertical, [source])
    assert count(vertical, "silver_events") == 1
    vertical.recover_observations(vertical.test_namespace)
    monkeypatch.setattr(curation, "observe_sink_batch", observe)
    assert curate(vertical, [source]).redelivery_noop == 1
    batches = read_sink_batches(vertical.connect, vertical.test_namespace, RUN)
    assert [b["timing_validity"] for b in batches] == ["missing", "observed"]
    assert batches[0]["flush_duration_seconds"] is batches[0]["committed_observed_at"] is None
    assert batches[0]["new_valid"] == batches[1]["redelivery_noop"] == 1


def test_migration_009_upgrades_existing_receipts_without_inventing_old_batches(vertical):
    curate(vertical, [record(vertical, event(vertical))])
    with vertical.connect() as tx, tx.transaction():
        tx.execute("DROP TABLE sink_batches")
        tx.execute("DELETE FROM analytics_schema_migrations WHERE version=9")
    for _ in range(2):
        with vertical.connect() as tx, tx.transaction():
            migrate_analytics(tx)
    assert read_sink_batches(vertical.connect, vertical.test_namespace, RUN) == []
    assert count(vertical, "silver_events") == 1
    assert curate(vertical, [record(vertical, event(vertical, 2), 1)]).new_valid == 1


def test_process_death_after_sink_commit_preserves_unknown_timer_and_broker_redelivery(vertical):
    namespace, bootstrap = vertical.test_namespace, os.environ["KAFKA_BOOTSTRAP_SERVERS"]
    topic, group_id = namespace + ".conversation-events.v1", namespace + ".analytics.v1"
    admin = AdminClient({"bootstrap.servers": bootstrap})
    for future in admin.create_topics([NewTopic(topic, 1, 1)]).values():
        future.result(30)
    publisher = KafkaPublisher(vertical.codec, bootstrap)
    fact = event(vertical)
    try:
        publisher.publish_event(fact, topic, fact.kafka_key())
    finally:
        publisher.close()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tests.pipelines.sink_crash",
            str(vertical.store.root),
            namespace,
            vertical.store.root.name,
        ],
        capture_output=True,
        text=True,
        timeout=75,
        check=False,
    )
    assert result.returncode == 73, result.stdout + result.stderr
    assert "M11_BOUNDARY_ACK:after_sink_commit_before_timer_and_offset" in result.stdout
    restarted = ConsumerGroup(group_id, [topic], bootstrap)
    try:
        assert restarted.consumer.committed([TopicPartition(topic, 0)], timeout=10)[0].offset < 0
        assert read_one(vertical, restarted).redelivery_noop == 1
        assert restarted.consumer.committed([TopicPartition(topic, 0)], timeout=10)[0].offset == 1
    finally:
        restarted.close()
    batches = read_sink_batches(vertical.connect, namespace, "m05-real-kafka-fixture")
    assert [b["timing_validity"] for b in batches] == ["missing", "observed"]
    assert batches[0]["new_valid"] == batches[1]["redelivery_noop"] == 1
    vertical.publish_snapshot(namespace)
    assert query(vertical).rows[0]["unique_events"] == 1
    with vertical.connect() as tx:
        sources = rows(tx, "SELECT disposition,silver_committed_observed_at FROM source_receipts")
    assert sources[0]["disposition"] == "new_valid" and sources[0]["silver_committed_observed_at"]
    Path("artifacts/m11/sink-crash.json").write_text(
        json.dumps(
            {
                "source_commit": vertical.code_commit,
                "namespace": namespace,
                "boundary_ack": result.stdout.strip(),
                "process_exit_code": result.returncode,
                "timing_validity": [b["timing_validity"] for b in batches],
                "committed_next_offset_before_restart": None,
                "committed_next_offset_after_restart": 1,
                "gold_unique_events": 1,
                "real_outbox": "NOT_RUN; no invalid source in this case",
            },
            indent=2,
        )
    )
