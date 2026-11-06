"""Actual broker offsets across sink acknowledgement loss and consumer restart."""

import json
import os
from pathlib import Path
from time import monotonic

import pytest
from confluent_kafka import Producer, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic

from shared.event_transport.consumer import ConsumerGroup
from shared.event_transport.publisher import KafkaPublisher
from shared.local_diagnostics import OutboxUnavailable

from . import test_vertical_live as live
from .test_vertical_live import count, event, query

vertical = live.vertical
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_VERTICAL_LIVE_TESTS") != "1",
    reason="RUN_VERTICAL_LIVE_TESTS=1 requires real Kafka/PostgreSQL and the Linux volume",
)


def read_one(pipeline, group):
    deadline = monotonic() + 40
    while monotonic() < deadline:
        result = pipeline.ingest_once(group, run_id="m05-real-kafka-fixture", max_records=1)
        if result is not None:
            return result
    raise AssertionError("Native Kafka source not received")


def test_native_sink_commit_before_offset_restart_and_invalid_backpressure(vertical, monkeypatch):
    namespace = vertical.test_namespace
    topic = namespace + ".conversation-events.v1"
    bootstrap = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
    admin = AdminClient({"bootstrap.servers": bootstrap})
    for future in admin.create_topics(
        [NewTopic(topic, 1, 1, config={"retention.ms": "604800000"})]
    ).values():
        future.result(30)
    publisher = KafkaPublisher(vertical.codec, bootstrap)
    fact = event(vertical)
    try:
        publisher.publish_event(fact, topic, fact.kafka_key())
        publisher.publish_event(fact, topic, fact.kafka_key())
    finally:
        publisher.close()
    group_id = namespace + ".analytics.v1"
    group = ConsumerGroup(group_id, [topic], bootstrap)
    original = vertical._observe

    def lost(*args):
        raise RuntimeError("M05_AFTER_SINK_COMMIT_BEFORE_OFFSET_ACK")

    monkeypatch.setattr(vertical, "_observe", lost)
    try:
        with pytest.raises(RuntimeError, match="AFTER_SINK_COMMIT"):
            read_one(vertical, group)
        assert count(vertical, "silver_events") == 1
        assert group.consumer.committed([TopicPartition(topic, 0)], timeout=10)[0].offset < 0
    finally:
        group.close()
    monkeypatch.setattr(vertical, "_observe", original)
    restarted = ConsumerGroup(group_id, [topic], bootstrap)
    try:
        assert read_one(vertical, restarted).redelivery_noop == 1
        assert read_one(vertical, restarted).duplicate_delivery == 1
        assert restarted.consumer.committed([TopicPartition(topic, 0)], timeout=10)[0].offset == 2
        vertical.publish_snapshot(namespace)
        assert query(vertical).rows[0]["unique_events"] == 1
        injector = Producer({"bootstrap.servers": bootstrap})
        injector.produce(topic, key=fact.kafka_key().encode(), value=b"\xff-malformed")
        assert injector.flush(15) == 0
        import shared.outbox as outbox

        monkeypatch.delattr(outbox, "append_outbox")
        with pytest.raises(OutboxUnavailable):
            read_one(vertical, restarted)
        committed = restarted.consumer.committed([TopicPartition(topic, 0)], timeout=10)[0].offset
        assert committed == 2 and count(vertical, "quarantine") == 0
        Path("artifacts/m05/kafka-offsets.json").write_text(
            json.dumps(
                {
                    "namespace": namespace,
                    "group_id": group_id,
                    "sink_commit_before_offset": "PASS",
                    "restart_redelivery_noop": 1,
                    "duplicate_delivery": 1,
                    "gold_unique_events": 1,
                    "broker_committed_next_offset": committed,
                    "invalid_source_offset": 2,
                    "invalid_missing_outbox": "BLOCKED; no offset advanced",
                    "real_outbox": "EXPLICIT missing-binding injection for backpressure check",
                },
                indent=2,
            )
        )
    finally:
        restarted.close()
