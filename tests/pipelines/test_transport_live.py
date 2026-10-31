"""Real SDK broker/offset checks and real SQL rollback with an explicit outbox double."""

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from types import ModuleType
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from infra import postgres, streaming
from shared.contracts.events import LocalDiagnostic, ValidEvent
from shared.event_transport.codec import EventCodec
from shared.event_transport.consumer import ConsumerGroup
from shared.event_transport.publisher import (
    PRODUCER_SETTINGS,
    KafkaPublisher,
    RetryablePublishError,
)
from shared.event_transport.schemas import SchemaCache
from shared.local_diagnostics import (
    DiagnosticConflict,
    diagnostic_table_ddl,
    quarantine_local_diagnostic,
)

from .event_examples import uid

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_TRANSPORT_LIVE_TESTS") != "1",
    reason="Real Kafka/PostgreSQL required; RUN_TRANSPORT_LIVE_TESTS=1",
)


def read_until(worker, count, deadline_seconds=40):
    records = []
    deadline = monotonic() + deadline_seconds
    while len(records) < count and monotonic() < deadline:
        records.extend(worker.consume_records(worker.topics, count - len(records), 100))
    assert len(records) == count
    return records


def save_evidence(name, value):
    path = Path("artifacts/m03") / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def test_real_sdk_acknowledgement_manual_offsets_and_uncertain_retry():
    namespace = "bench-m03-" + uuid4().hex
    streaming.provision_topics(namespace)
    codec = EventCodec(SchemaCache.load(streaming.SCHEMA_CACHE), source_service="conversation")
    publisher = KafkaPublisher(codec, streaming.BOOTSTRAP)
    topic = namespace + ".conversation-events.v1"
    worker = ConsumerGroup(namespace + ".analytics.v1", [topic], streaming.BOOTSTRAP)
    independent = ConsumerGroup(namespace + ".catalog-stock.v1", [topic], streaming.BOOTSTRAP)
    context = {
        "namespace": namespace,
        "run_id": "m03-real-smoke",
        "user_id": "synthetic-user",
        "session_id": uid(10),
        "correlation_id": uid(9),
    }
    events = [
        codec.build_event(
            "CONVERSATION_TURN",
            {
                "turn_id": str(uuid4()),
                "mode": "fixed",
                "outcome": "success",
                "duration_ms": 1.0,
                "llm_call_count": 0,
                "extractor_source": "rules",
            },
            context,
            "session",
            uid(10),
            version,
            datetime.now(UTC),
            metadata={
                "synthetic": True,
                "scenario_source": "simulation",
                "padding": "explicit synthetic SDK fixture",
            },
        )
        for version in (1, 2, 3)
    ]
    try:
        historical = [
            entry
            for entry in codec.cache.historical
            if entry["subject"] == "conversation-events.v1-value"
        ]
        if historical:
            raw, headers, _, key = codec.encode(events[0])
            checked = codec.validate_event(
                raw, [headers[0], ("schema-id", str(historical[0]["id"]).encode())], topic, key
            )
            assert isinstance(checked, ValidEvent) and checked.schema_id == historical[0]["id"]
        acks = [publisher.publish_event(event, topic, event.kafka_key()) for event in events]
        records = read_until(worker, 3)
        assert [
            codec.validate_event(
                record.value_bytes,
                record.headers,
                record.topic,
                record.key_bytes,
                source_record=record,
            ).envelope.event_id
            for record in records
        ] == [event.event_id for event in events]
        for record in records:
            assert isinstance(
                codec.validate_event(
                    record.value_bytes,
                    record.headers,
                    record.topic,
                    record.key_bytes,
                    source_record=record,
                ),
                ValidEvent,
            )
        worker.mark_durable(records[2])
        rejected = worker.commit_offsets({(topic, 0): records[2].offset + 1})
        assert not rejected.succeeded
        worker.mark_durable(records[0])
        first = worker.commit_offsets(worker.durable_next_offsets())
        assert first.succeeded and first.committed_next_offsets[0].offset == records[0].offset + 1
        worker.mark_durable(records[1])
        final = worker.commit_offsets(worker.durable_next_offsets())
        assert final.succeeded and final.committed_next_offsets[0].offset == records[2].offset + 1
        other = read_until(independent, 3)
        assert [record.value_bytes for record in other] == [
            record.value_bytes for record in records
        ]
        # This is SDK smoke evidence, not a claim of an actual durable M04 sink.
        for record in other:
            independent.mark_durable(record)
        assert independent.commit_offsets(independent.durable_next_offsets()).succeeded

        kafka = streaming.compose("ps", "--quiet", "kafka")
        uncertain = codec.build_event(
            "CONVERSATION_TURN",
            events[0].payload,
            context,
            "session",
            uid(10),
            4,
            datetime.now(UTC),
        )
        before = codec.encode(uncertain)[0]
        postgres.command(["docker", "pause", kafka])
        try:
            with pytest.raises(RetryablePublishError) as failure:
                publisher.publish_event(uncertain, topic, uncertain.kafka_key(), timeout=0.05)
            assert failure.value.uncertain
        finally:
            postgres.command(["docker", "unpause", kafka])
        retry_ack = publisher.publish_event(uncertain, topic, uncertain.kafka_key(), timeout=20)
        retry_record = read_until(worker, 1)[0]
        assert retry_record.value_bytes == before
        assert retry_ack.event_id == uncertain.event_id
        save_evidence(
            "kafka-sdk.json",
            {
                "test_mode": "real",
                "namespace": namespace,
                "acknowledged_ids": [ack.event_id for ack in acks],
                "first_committed_next": first.committed_next_offsets[0].offset,
                "final_committed_next": final.committed_next_offsets[0].offset,
                "gap_rejected": not rejected.succeeded,
                "independent_group_records": len(other),
                "uncertain_event_id": uncertain.event_id,
                "retry_preserved_exact_bytes": True,
                "sink_durability": "NOT_RUN; M04 required",
                "producer_settings": PRODUCER_SETTINGS,
                "consumer_settings": worker.settings,
                "verified_released_history_schemas": len(codec.cache.historical),
                "legacy_conversation_id_validated": historical[0]["id"] if historical else None,
            },
        )
    finally:
        worker.close()
        independent.close()
        publisher.close()


def test_real_caller_transaction_and_outbox_savepoint_rollback(monkeypatch):
    values = postgres.credentials()
    url = postgres.database_url("analytics", values)
    schema = "m03_" + uuid4().hex
    outbox = ModuleType("shared.outbox")

    def explicit_transactional_outbox_double(tx, event):
        tx.execute(
            "INSERT INTO test_outbox_double(event_id,body) VALUES (%s,%s)",
            (event.event_id, Jsonb(event.model_dump(mode="json"))),
        )

    outbox.append_outbox = explicit_transactional_outbox_double
    monkeypatch.setitem(sys.modules, "shared.outbox", outbox)
    value = LocalDiagnostic(
        diagnostic_id=str(uuid4()),
        namespace="bench-m03-sql",
        run_id="m03-real-sql",
        source_service="analytics",
        reason_code="INVALID_JSON",
        correlation_id=str(uuid4()),
        created_at=datetime.now(UTC),
        content_hash="0" * 64,
        restricted_content_reference="restricted/synthetic-m03",
        source_coordinates=None,
    )
    with psycopg.connect(url, autocommit=True, row_factory=dict_row) as tx:
        tx.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        tx.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        tx.execute(diagnostic_table_ddl())
        tx.execute(
            "CREATE TABLE test_outbox_double(event_id uuid PRIMARY KEY, body jsonb NOT NULL)"
        )
        try:
            with pytest.raises(RuntimeError, match="caller rollback"):
                with tx.transaction():
                    quarantine_local_diagnostic(tx, value)
                    raise RuntimeError("caller rollback")
            assert tx.execute("SELECT count(*) n FROM local_diagnostics").fetchone()["n"] == 0
            assert tx.execute("SELECT count(*) n FROM test_outbox_double").fetchone()["n"] == 0

            def failed_outbox(tx, event):
                raise RuntimeError("explicit outbox double failure")

            outbox.append_outbox = failed_outbox
            with tx.transaction():
                with pytest.raises(RuntimeError, match="outbox double failure"):
                    quarantine_local_diagnostic(tx, value)
            assert tx.execute("SELECT count(*) n FROM local_diagnostics").fetchone()["n"] == 0
            outbox.append_outbox = explicit_transactional_outbox_double
            with tx.transaction():
                assert quarantine_local_diagnostic(tx, value) == value.diagnostic_id
                assert quarantine_local_diagnostic(tx, value) == value.diagnostic_id
            assert tx.execute("SELECT count(*) n FROM local_diagnostics").fetchone()["n"] == 1
            assert tx.execute("SELECT count(*) n FROM test_outbox_double").fetchone()["n"] == 1
            changed = value.model_copy(update={"content_hash": "1" * 64})
            with tx.transaction():
                with pytest.raises(DiagnosticConflict):
                    quarantine_local_diagnostic(tx, changed)
            save_evidence(
                "diagnostics-sql.json",
                {
                    "postgres": "real",
                    "schema": schema,
                    "outbox": "EXPLICIT_TEST_DOUBLE",
                    "caller_rollback": "PASS",
                    "caught_outbox_failure_savepoint_rollback": "PASS",
                    "idempotent_retry": "PASS",
                    "altered_identity_rejected": "PASS",
                    "real_shared_outbox": "NOT_RUN; Aditya required",
                },
            )
        finally:
            # Only this isolated test-owned schema, after its evidence is saved.
            tx.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_real_rebalance_fences_old_owner_and_redelivers_exact_source():
    namespace = "bench-m03-r-" + uuid4().hex
    streaming.provision_topics(namespace, partitions=3)
    topic = namespace + ".conversation-events.v1"
    codec = EventCodec(SchemaCache.load(streaming.SCHEMA_CACHE), source_service="conversation")
    publisher = KafkaPublisher(codec, streaming.BOOTSTRAP)
    first = ConsumerGroup(
        namespace + ".analytics.v1", [topic], streaming.BOOTSTRAP, workers=3, worker_index=0
    )
    second = None
    try:
        target_ack = None
        for number in range(1, 65):
            session = uid(1000 + number)
            event = codec.build_event(
                "CONVERSATION_TURN",
                {
                    "turn_id": uid(2000 + number),
                    "mode": "fixed",
                    "outcome": "success",
                    "duration_ms": 1.0,
                    "llm_call_count": 0,
                    "extractor_source": "rules",
                },
                {
                    "namespace": namespace,
                    "run_id": "m03-rebalance",
                    "user_id": "synthetic",
                    "correlation_id": uid(9),
                    "session_id": session,
                },
                "session",
                session,
                1,
                datetime.now(UTC),
            )
            ack = publisher.publish_event(event, topic, event.kafka_key())
            if ack.partition == 2:
                target_ack = ack
                break
        assert target_ack is not None, "No default-hashed fixture key reached partition two"
        old = None
        deadline = monotonic() + 40
        while old is None and monotonic() < deadline:
            for record in first.consume_records([topic], 100, 100):
                if (record.partition, record.offset) == (2, target_ack.offset):
                    old = record
        assert old is not None
        second = ConsumerGroup(
            namespace + ".analytics.v1", [topic], streaming.BOOTSTRAP, workers=3, worker_index=1
        )
        deadline = monotonic() + 40
        while monotonic() < deadline:
            first.consume_records([topic], 0, 50)
            second.consume_records([topic], 0, 50)
            if not first.is_current(old) and (topic, 2) in second.assignments:
                break
        assert not first.is_current(old) and (topic, 2) in second.assignments
        with pytest.raises(ValueError, match="revoked"):
            first.mark_durable(old)
        replacement = read_until(second, 1)[0]
        assert (replacement.partition, replacement.offset) == (old.partition, old.offset)
        assert (
            replacement.value_bytes == old.value_bytes and replacement.raw_sha256 == old.raw_sha256
        )
        assert replacement.assignment_epoch != old.assignment_epoch
        second.mark_durable(replacement)
        assert second.commit_offsets(second.durable_next_offsets()).succeeded
        save_evidence(
            "rebalance.json",
            {
                "broker": "real",
                "namespace": namespace,
                "old_owner_fenced": True,
                "redelivered_exact_source": True,
                "committed_next_offset": replacement.offset + 1,
                "workers_declared": 3,
                "workers_started": 2,
                "not_a_scaling_benchmark": True,
            },
        )
    finally:
        first.close()
        if second is not None:
            second.close()
        publisher.close()
