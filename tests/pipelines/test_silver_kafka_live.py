"""M06 all-domain native Kafka → SQL → manifest integration; no outbox double."""

import json
import os
from collections import Counter
from datetime import timedelta
from pathlib import Path
from time import monotonic

from confluent_kafka import TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic

from shared.event_transport.consumer import ConsumerGroup
from shared.event_transport.publisher import KafkaPublisher

from . import test_vertical_live as live
from .test_silver_live import domain_event

vertical = live.vertical
pytestmark = live.pytestmark


def test_all_five_topics_have_durable_prefixes_and_one_effect_per_event(vertical):
    namespace = vertical.test_namespace
    events = [
        domain_event(vertical, name, index)
        for index, name in enumerate(
            (
                "CONVERSATION_TURN",
                "PRODUCT_RETRIEVED",
                "ORDER_CONFIRMED",
                "STOCK_UPDATED",
                "PAYMENT_SUCCESS",
            ),
            1,
        )
    ]
    topics = [event.topic() for event in events]
    bootstrap = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
    admin = AdminClient({"bootstrap.servers": bootstrap})
    for future in admin.create_topics(
        [NewTopic(topic, 1, 1, config={"retention.ms": "604800000"}) for topic in topics]
    ).values():
        future.result(30)
    publisher = KafkaPublisher(vertical.codec, bootstrap)
    try:
        for event in events:
            publisher.publish_event(event, event.topic(), event.kafka_key())
            publisher.publish_event(event, event.topic(), event.kafka_key())
    finally:
        publisher.close()
    group = ConsumerGroup(namespace + ".analytics.v1", topics, bootstrap)
    totals = Counter()
    try:
        deadline = monotonic() + 60
        while totals["source_records"] < 10 and monotonic() < deadline:
            result = vertical.ingest_once(
                group, run_id="m06-five-domain-native-fixture", max_records=1
            )
            if result is not None:
                totals.update(
                    {
                        name: getattr(result, name)
                        for name in ("source_records", "new_valid", "duplicate_delivery", "invalid")
                    }
                )
        assert dict(totals) == {
            "source_records": 10,
            "new_valid": 5,
            "duplicate_delivery": 5,
            "invalid": 0,
        }
        committed = group.consumer.committed(
            [TopicPartition(topic, 0) for topic in topics], timeout=10
        )
        assert {offset.topic: offset.offset for offset in committed} == dict.fromkeys(topics, 2)
        manifest = vertical.publish_snapshot(namespace)
        today = vertical.test_event_time.date()
        gold = vertical.query_gold(namespace, "pipeline_minute", today, today + timedelta(days=1))
        assert {row["event_type"] for row in gold.rows} == {event.event_type for event in events}
        assert all(row["unique_events"] == 1 for row in gold.rows)
        Path("artifacts/m06/kafka-domains.json").write_text(
            json.dumps(
                {
                    "source_commit": vertical.code_commit,
                    "namespace": namespace,
                    "dispositions": dict(totals),
                    "committed_next_offsets": {offset.topic: offset.offset for offset in committed},
                    "active_gold_generation": manifest.generation,
                    "real_outbox": "NOT_RUN; absent",
                },
                indent=2,
            )
        )
    finally:
        group.close()
