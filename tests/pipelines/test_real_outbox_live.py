"""Real PostgreSQL/outbox/Kafka/Bronze/Silver/Gold/DLQ integration with explicit crash injection."""

import json
import os
from dataclasses import replace
from pathlib import Path
from time import monotonic
from uuid import uuid4

import httpx
import pytest
from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient, NewTopic

from pipelines.ingestion.api import create_app
from shared.contracts.events import DlqNotice, PublishAck
from shared.event_transport import ConsumerGroup, KafkaPublisher, RetryablePublishError
from shared.event_transport.consumer import raw_fingerprint
from shared.outbox import append_outbox, outbox_table_ddl, relay_once

from . import test_vertical_live as live
from .test_dlq_recovery_live import wait_marker
from .test_vertical_live import curate, event, query, record

vertical = live.vertical
pytestmark = live.pytestmark


def receive(group, topic, count):
    records = []
    deadline = monotonic() + 45
    while len(records) < count and monotonic() < deadline:
        records.extend(group.consume_records([topic], count - len(records), 100))
    assert len(records) == count
    return records


def pending(pipeline):
    with pipeline.connect() as tx:
        return tx.execute("SELECT count(*) FROM outbox WHERE published_at IS NULL").fetchone()[0]


def test_real_ack_before_mark_crash_redelivers_once_and_dlq_is_transactional(vertical):
    bootstrap = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
    topic = vertical.test_namespace + ".conversation-events.v1"
    dlq_topic = vertical.test_namespace + ".dead-letter.v1"
    admin = AdminClient({"bootstrap.servers": bootstrap})
    for future in admin.create_topics([NewTopic(topic, 1, 1), NewTopic(dlq_topic, 1, 1)]).values():
        future.result(30)
    original = event(vertical)
    with pytest.raises(RuntimeError, match="explicit caller rollback"):
        with vertical.connect() as tx, tx.transaction():
            append_outbox(tx, original)
            raise RuntimeError("explicit caller rollback")
    assert pending(vertical) == 0
    with vertical.connect() as tx, tx.transaction():
        append_outbox(tx, original)
    assert pending(vertical) == 1
    with vertical.connect() as tx:
        before = bytes(tx.execute("SELECT payload FROM outbox").fetchone()[0])

    first = KafkaPublisher(vertical.codec, bootstrap)
    acknowledgements = []

    class LostAckAfterRealDelivery:
        def publish_event(self, *args):
            ack = first.publish_event(*args)
            assert ack.offset >= 0
            acknowledgements.append(ack)
            raise RetryablePublishError(
                original.event_id, "EXPLICIT_AFTER_ACK_CRASH", uncertain=True
            )

    try:
        with vertical.connect() as tx:
            tx.autocommit = False
            result = relay_once(tx, LostAckAfterRealDelivery())
            assert result.uncertain == 1 and result.marked_published == 0
    finally:
        first.close()
    assert len(acknowledgements) == 1
    assert pending(vertical) == 1
    with vertical.connect() as tx:
        assert bytes(tx.execute("SELECT payload FROM outbox").fetchone()[0]) == before

    publisher = KafkaPublisher(vertical.codec, bootstrap)
    group = ConsumerGroup(vertical.test_namespace + ".analytics.v1", [topic], bootstrap)
    notices = ConsumerGroup(vertical.test_namespace + ".dlq-monitor.v1", [dlq_topic], bootstrap)
    try:
        with vertical.connect() as tx:
            tx.autocommit = False
            result = relay_once(tx, publisher)
            assert result.broker_acked == result.marked_published == 1
        assert pending(vertical) == 0
        records = receive(group, topic, 2)
        assert records[0].value_bytes == records[1].value_bytes == before
        outcome = curate(vertical, records)
        assert outcome.new_valid == outcome.duplicate_delivery == 1
        for source in records:
            group.mark_durable(source)
        assert group.commit_offsets(group.durable_next_offsets()).succeeded
        vertical.publish_snapshot(vertical.test_namespace)
        assert sum(row["unique_events"] for row in query(vertical).rows) == 1

        # Deliberately malformed bytes enter through the actual broker.
        producer = Producer({"bootstrap.servers": bootstrap, "acks": "all"})
        deliveries = []
        producer.produce(
            topic,
            value=b"\xff",
            key=records[0].key_bytes,
            headers=list(records[0].headers),
            on_delivery=lambda error, message: deliveries.append(error),
        )
        assert producer.flush(30) == 0 and deliveries == [None]
        malformed = receive(group, topic, 1)
        assert curate(vertical, malformed).invalid == 1
        assert pending(vertical) == 1
        group.mark_durable(malformed[0])
        assert group.commit_offsets(group.durable_next_offsets()).succeeded
        with vertical.connect() as tx:
            assert tx.execute("SELECT count(*) FROM quarantine").fetchone()[0] == 1
            tx.autocommit = False
            assert relay_once(tx, publisher).marked_published == 1
        notice = receive(notices, dlq_topic, 1)[0]
        checked = vertical.codec.validate_event(
            notice.value_bytes,
            notice.headers,
            notice.topic,
            notice.key_bytes,
            source_record=notice,
        )
        assert isinstance(checked.envelope, DlqNotice)
        assert checked.envelope.source_locator.offset == malformed[0].offset
        assert pending(vertical) == 0
        # Durable invalid-source redelivery emits no second notification.
        assert curate(vertical, malformed).redelivery_noop == 1
        with vertical.connect() as tx:
            assert tx.execute("SELECT count(*) FROM outbox").fetchone()[0] == 2
    finally:
        group.close()
        notices.close()
        publisher.close()


def test_analytics_migration_installs_real_outbox_and_readiness_checks_table(vertical):
    from pipelines.ingestion.receipts import OUTBOX_MIGRATION, migrate_analytics

    assert OUTBOX_MIGRATION.read_text() == outbox_table_ddl()
    with vertical.connect() as tx, tx.transaction():
        migrate_analytics(tx)
    app = create_app(vertical, internal_token="explicit-integration-token")

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://analytics"
        ) as client:
            assert (await client.get("/health/ready")).status_code == 200
            with vertical.connect() as tx:
                tx.execute("DROP TABLE outbox")
            assert (await client.get("/health/ready")).status_code == 503

    import asyncio

    asyncio.run(check())


@pytest.mark.parametrize("failure", ["uncertain", "not_queued", "corrupt_payload"])
def test_real_relay_keeps_later_aggregate_versions_pending_after_failed_head(vertical, failure):
    from datetime import UTC, datetime

    vertical.test_session = "00000000-0000-4000-8000-000000000001"
    first, second = event(vertical), event(vertical, 2)
    other_session = "ffffffff-ffff-4fff-bfff-ffffffffffff"
    other = event(vertical).model_copy(
        update={
            "event_id": str(uuid4()),
            "session_id": other_session,
            "aggregate_id": other_session,
        }
    )
    for fact in (first, second, other):
        vertical.codec.encode(fact)
    with vertical.connect() as tx, tx.transaction():
        for fact in (first, second, other):
            append_outbox(tx, fact)
        original = bytes(
            tx.execute(
                "SELECT payload FROM outbox WHERE event_id=%s", (first.event_id,)
            ).fetchone()[0]
        )
        if failure == "corrupt_payload":
            # Explicit storage-corruption injection; restore the exact saved bytes before retry.
            tx.execute("UPDATE outbox SET payload=%s WHERE event_id=%s", (b"{", first.event_id))

    class PublisherDouble:
        """Explicit delivery uncertainty; the SQL/outbox/relay are real."""

        fail = True

        def __init__(self):
            self.calls = []

        def publish_event(self, fact, topic, key):
            self.calls.append(fact.event_id)
            if self.fail and fact.event_id == first.event_id:
                raise RetryablePublishError(
                    fact.event_id, "EXPLICIT_HEAD_FAILURE", uncertain=failure == "uncertain"
                )
            return PublishAck(
                event_id=fact.event_id,
                topic=topic,
                partition=0,
                offset=len(self.calls) - 1,
                broker_acked_at=datetime.now(UTC),
            )

    publisher = PublisherDouble()
    with vertical.connect() as tx:
        tx.autocommit = False
        result = relay_once(tx, publisher)
    assert result.uncertain == int(failure == "uncertain")
    assert result.retryable_failed == int(failure != "uncertain")
    assert result.marked_published == 1
    assert publisher.calls == ([first.event_id] if failure != "corrupt_payload" else []) + [
        other.event_id
    ]
    assert pending(vertical) == 2
    publisher.fail = False
    publisher.calls.clear()
    with vertical.connect() as tx:
        if failure == "corrupt_payload":
            tx.execute("UPDATE outbox SET payload=%s WHERE event_id=%s", (original, first.event_id))
        tx.autocommit = False
        result = relay_once(tx, publisher)
    assert result.marked_published == 2
    assert publisher.calls == [first.event_id, second.event_id]
    assert pending(vertical) == 0


@pytest.mark.skipif(
    os.environ.get("M09_BROKER_OUTAGE") != "1",
    reason="M09_BROKER_OUTAGE=1 requires the external broker pause/resume controller",
)
def test_real_outbox_retains_dlq_during_broker_outage_and_recovers(vertical):
    source = record(vertical, event(vertical))
    source = replace(
        source,
        value_bytes=b"\xff",
        raw_sha256=raw_fingerprint(source.key_bytes, b"\xff", source.headers),
    )
    assert curate(vertical, [source]).invalid == 1
    assert pending(vertical) == 1
    bootstrap = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
    topic = vertical.test_namespace + ".dead-letter.v1"
    admin = AdminClient({"bootstrap.servers": bootstrap})
    for future in admin.create_topics([NewTopic(topic, 1, 1)]).values():
        future.result(30)
    publisher = KafkaPublisher(vertical.codec, bootstrap)
    publisher.producer.list_topics(topic, timeout=15)
    base = Path("artifacts/m09")
    namespace = vertical.test_namespace
    control = {"namespace": namespace, "source_commit": vertical.code_commit, "topic": topic}
    (base / "dlq-ready.json").write_text(json.dumps(control))
    try:
        wait_marker(base / (namespace + "-paused"))
        with vertical.connect() as tx:
            tx.autocommit = False
            result = relay_once(tx, publisher)
        assert result.uncertain == 1 and result.marked_published == 0
        assert pending(vertical) == 1
        with vertical.connect() as tx:
            assert tx.execute("SELECT count(*) FROM quarantine").fetchone()[0] == 1
            assert tx.execute("SELECT count(*) FROM silver_events").fetchone()[0] == 0
    finally:
        try:
            publisher.close(timeout=0.1)
        except RetryablePublishError:
            pass
        (base / (namespace + "-resume-request")).write_text("resume")
    wait_marker(base / (namespace + "-resumed"))
    recovered = KafkaPublisher(vertical.codec, bootstrap)
    group = ConsumerGroup(namespace + ".dlq-monitor.v1", [topic], bootstrap)
    try:
        with vertical.connect() as tx:
            tx.autocommit = False
            assert relay_once(tx, recovered).marked_published == 1
        notice = receive(group, topic, 1)[0]
        checked = vertical.codec.validate_event(
            notice.value_bytes, notice.headers, notice.topic, notice.key_bytes
        )
        assert isinstance(checked.envelope, DlqNotice)
        assert checked.envelope.source_locator.offset == source.offset
        assert pending(vertical) == 0
        assert curate(vertical, [source]).redelivery_noop == 1
        with vertical.connect() as tx:
            assert tx.execute("SELECT count(*) FROM outbox").fetchone()[0] == 1
    finally:
        group.close()
        recovered.close()
    (base / "dlq-recovery.json").write_text(
        json.dumps(
            control
            | {
                "pending_during_outage": 1,
                "pending_after_ack": 0,
                "outbox_and_relay": "REAL shared transactional outbox and relay_once",
            }
        )
    )
