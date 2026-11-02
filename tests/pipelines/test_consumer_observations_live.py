"""Real bounded consumer pause/resume, SQL dispositions, offsets and Gold visibility."""

import os
from time import monotonic

from confluent_kafka import TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic

import shared.event_transport.consumer as consumer
from pipelines.ingestion import BronzeCapture
from shared.event_transport.publisher import KafkaPublisher

from . import test_vertical_live as live
from .test_vertical_live import event, query

vertical = live.vertical
pytestmark = live.pytestmark


def test_real_pressure_peak_survives_drain_without_early_offset_commit(vertical, monkeypatch):
    # Small explicit boundary fixture; the production 2,000-record budget is unchanged.
    monkeypatch.setattr(consumer, "GROUP_MAX_RECORDS", 3)
    namespace, bootstrap = vertical.test_namespace, os.environ["KAFKA_BOOTSTRAP_SERVERS"]
    topic = namespace + ".conversation-events.v1"
    admin = AdminClient({"bootstrap.servers": bootstrap})
    for future in admin.create_topics([NewTopic(topic, 1, 1)]).values():
        future.result(30)
    publisher = KafkaPublisher(vertical.codec, bootstrap)
    try:
        for version in (1, 2, 3):
            fact = event(vertical, version)
            publisher.publish_event(fact, topic, fact.kafka_key())
    finally:
        publisher.close()
    group = consumer.ConsumerGroup(namespace + ".analytics.v1", [topic], bootstrap)
    try:
        records = []
        deadline = monotonic() + 40
        while len(records) < 2 and monotonic() < deadline:
            records.extend(group.consume_records([topic], 3 - len(records), 50))
        assert len(records) == 2
        group.consume_records([topic], 0, 50)
        sample = group.buffer_snapshot()
        assert sample["pending_records"] == sample["peak_pending_records"] == 2
        assert sample["fetch_paused"] and sample["pause_required"] and sample["pause_count"] == 1
        assert sample["pending_raw_bytes"] == sum(consumer.record_size(r) for r in records)
        assert group.consumer.committed([TopicPartition(topic, 0)], timeout=5)[0].offset < 0
        receipt = BronzeCapture(vertical.store).ingest_bronze(records)
        assert vertical.curate_silver(receipt, {"run_id": "real-buffer-boundary"}).new_valid == 2
        for record in records:
            group.mark_durable(record)
        assert group.commit_offsets(group.durable_next_offsets()).succeeded
        last = []
        deadline = monotonic() + 20
        while not last and monotonic() < deadline:
            last = group.consume_records([topic], 1, 50)
        assert len(last) == 1 and last[0].offset == 2
        receipt = BronzeCapture(vertical.store).ingest_bronze(last)
        assert vertical.curate_silver(receipt, {"run_id": "real-buffer-boundary"}).new_valid == 1
        group.mark_durable(last[0])
        assert group.commit_offsets(group.durable_next_offsets()).succeeded
        drained = group.buffer_snapshot()
        assert drained["pending_records"] == drained["pending_raw_bytes"] == 0
        assert drained["peak_pending_records"] == 2 and drained["peak_pending_raw_bytes"] > 0
        assert drained["pause_count"] == 1 and not drained["fetch_paused"]
        assert drained["overflow_rejections"] == 0
        assert group.consumer.committed([TopicPartition(topic, 0)], timeout=5)[0].offset == 3
        vertical.publish_snapshot(namespace)
        assert query(vertical).rows[0]["unique_events"] == 3
    finally:
        group.close()
