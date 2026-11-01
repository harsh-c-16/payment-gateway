"""Real broker pause/recovery; storage/relay double is explicitly not Aditya's outbox."""

import json
import os
from dataclasses import replace
from pathlib import Path
from time import monotonic, sleep

import pytest
from confluent_kafka.admin import AdminClient, NewTopic

from shared.contracts.events import DlqNotice
from shared.event_transport.consumer import ConsumerGroup, raw_fingerprint
from shared.event_transport.publisher import KafkaPublisher, RetryablePublishError

from . import test_vertical_live as live
from .test_vertical_live import count, curate, event, record

vertical = live.vertical
outbox_double = live.outbox_double
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_VERTICAL_LIVE_TESTS") != "1" or os.environ.get("M09_BROKER_OUTAGE") != "1",
    reason="M09_BROKER_OUTAGE=1 requires an external real-broker pause/resume controller",
)


def wait_marker(path):
    deadline = monotonic() + 90
    while monotonic() < deadline:
        if path.exists():
            return
        sleep(0.1)
    raise AssertionError("External broker controller did not acknowledge " + path.name)


def test_durable_notification_survives_real_broker_pause_and_relay_restart(vertical, outbox_double):
    source = record(vertical, event(vertical))
    source = replace(
        source,
        value_bytes=b"\xff-invalid",
        raw_sha256=raw_fingerprint(source.key_bytes, b"\xff-invalid", source.headers),
    )
    assert curate(vertical, [source]).invalid == 1
    ns = vertical.test_namespace
    bootstrap = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
    topic = ns + ".dead-letter.v1"
    admin = AdminClient({"bootstrap.servers": bootstrap})
    for future in admin.create_topics([NewTopic(topic, 1, 1)]).values():
        future.result(30)
    with vertical.connect() as tx:
        tx.execute(
            "ALTER TABLE test_outbox_double ADD COLUMN published boolean NOT NULL DEFAULT false"
        )
        payload = tx.execute("SELECT payload FROM test_outbox_double").fetchone()[0]
    notice = DlqNotice.model_validate(payload)
    publisher = KafkaPublisher(vertical.codec, bootstrap)
    publisher.producer.list_topics(topic, timeout=15)
    base = Path("artifacts/m09")
    control = {"namespace": ns, "source_commit": vertical.code_commit, "topic": topic}
    (base / "dlq-ready.json").write_text(json.dumps(control))
    try:
        wait_marker(base / (ns + "-paused"))
        with pytest.raises(RetryablePublishError):
            publisher.publish_event(notice, topic, notice.kafka_key(), timeout=1)
        with vertical.connect() as tx:
            assert (
                tx.execute(
                    "SELECT count(*) FROM test_outbox_double WHERE NOT published"
                ).fetchone()[0]
                == 1
            )
        assert count(vertical, "quarantine") == 1 and count(vertical, "silver_events") == 0
    finally:
        try:
            publisher.close(timeout=0.1)
        except RetryablePublishError:
            pass  # Unconfirmed sends must remain pending in the durable outbox.
        (base / (ns + "-resume-request")).write_text("resume")
    wait_marker(base / (ns + "-resumed"))
    recovered = KafkaPublisher(vertical.codec, bootstrap)
    try:
        # Explicit relay double: read durable SQL, mark only after the real delivery ack.
        with vertical.connect() as tx:
            restored = DlqNotice.model_validate(
                tx.execute("SELECT payload FROM test_outbox_double WHERE NOT published").fetchone()[
                    0
                ]
            )
        ack = recovered.publish_event(restored, topic, restored.kafka_key())
        with vertical.connect() as tx:
            tx.execute(
                "UPDATE test_outbox_double SET published=true WHERE event_id=%s", (ack.event_id,)
            )
    finally:
        recovered.close()
    group = ConsumerGroup(ns + ".dlq-inspection.v1", [topic], bootstrap)
    try:
        deadline = monotonic() + 40
        records = []
        while not records and monotonic() < deadline:
            records = group.consume_records([topic], 1, 100)
        assert records
        source = records[0]
        checked = vertical.codec.validate_event(
            source.value_bytes, source.headers, source.topic, source.key_bytes, source_record=source
        )
        assert isinstance(checked.envelope, DlqNotice)
        assert checked.envelope.diagnostic_id == notice.diagnostic_id
    finally:
        group.close()
    with vertical.connect() as tx:
        assert (
            tx.execute("SELECT count(*) FROM test_outbox_double WHERE NOT published").fetchone()[0]
            == 0
        )
        assert (
            tx.execute(
                "SELECT count(*) FROM source_receipts WHERE disposition='invalid'"
            ).fetchone()[0]
            == 1
        )
    assert count(vertical, "quarantine") == 1 and count(vertical, "silver_events") == 0
    (base / "dlq-recovery.json").write_text(
        json.dumps(
            {
                **control,
                "real_broker_pause_recovery": "PASS",
                "pending_during_outage": 1,
                "pending_after_ack": 0,
                "invalid_source_records": 1,
                "business_facts": 0,
                "outbox_and_relay": "EXPLICIT SQL/relay DOUBLE; real Aditya implementation NOT_RUN",
            },
            indent=2,
        )
    )
