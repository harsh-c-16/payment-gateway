"""M03 contract and failure checks with explicitly labelled Kafka/outbox doubles."""

import copy
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from types import ModuleType, SimpleNamespace
from uuid import uuid4

import pytest
from confluent_kafka import TopicPartition
from psycopg.pq import TransactionStatus

import shared.event_transport as sdk
import shared.event_transport.publisher as publisher_module
from services.conversation.events import SharedEvents
from shared.contracts.common import RequestContext
from shared.contracts.events import EventEnvelope, LocalDiagnostic, ValidationFailure, ValidEvent
from shared.event_transport.codec import EventCodec, build_dlq_notice
from shared.event_transport.consumer import ConsumerBufferError, ConsumerGroup, raw_fingerprint
from shared.event_transport.publisher import (
    PRODUCER_SETTINGS,
    KafkaPublisher,
    RetryablePublishError,
)
from shared.event_transport.schemas import (
    RecordInvalid,
    SchemaCache,
    SchemaUnavailable,
    canonical_json,
    schema_hash,
)
from shared.local_diagnostics import OutboxUnavailable, quarantine_local_diagnostic

from .event_examples import examples, uid
from .transport_doubles import ConsumerDouble, MessageDouble, ProducerDouble, offline_cache

TOPIC = "bench-m03-unit.conversation-events.v1"


@pytest.fixture
def codec(monkeypatch):
    codec = EventCodec(
        offline_cache(), source_service="conversation", dataset_revision="synthetic-v1"
    )
    monkeypatch.setattr(sdk, "_codec", codec)
    monkeypatch.setattr(sdk, "_publisher", None)
    return codec


def event():
    return EventEnvelope.model_validate(examples()["CONVERSATION_TURN"])


def group(**kwargs):
    return ConsumerGroup(
        "bench-m03-unit.analytics.v1",
        [TOPIC],
        "explicit-kafka-double",
        consumer_factory=ConsumerDouble,
        **kwargs,
    )


def diagnostic():
    return LocalDiagnostic(
        diagnostic_id=uid(200),
        namespace="bench-m03-unit",
        run_id="m03-unit",
        source_service="conversation",
        reason_code="MODEL_OUTPUT_INVALID",
        correlation_id=uid(9),
        created_at=datetime.now(UTC),
        content_hash="0" * 64,
        restricted_content_reference="restricted/synthetic-1",
        source_coordinates=None,
    )


def test_m1_keyword_builder_and_existing_transaction_binding(codec, monkeypatch):
    outbox = ModuleType("shared.outbox")
    appended = []
    outbox.append_outbox = lambda tx, event: appended.append((tx, event))
    monkeypatch.setitem(sys.modules, "shared.outbox", outbox)
    request = RequestContext(
        namespace="bench-m03-unit",
        run_id="m03-unit",
        user_id="synthetic",
        correlation_id=uid(9),
        request_id=uid(1),
        session_id=uid(10),
    )
    tx = object()
    SharedEvents().append(
        tx,
        event_type="CONVERSATION_TURN",
        payload=event().payload,
        context=request,
        version=1,
        event_time=datetime.now(UTC),
    )
    assert appended[0][0] is tx
    built = appended[0][1]
    assert built.source_service == "conversation" and built.aggregate_id == request.session_id
    assert codec.encode(built)[0] == codec.encode(built)[0]


def test_constructor_copies_payload_and_preserves_optional_metadata(codec):
    template = event()
    payload = dict(template.payload)
    built = codec.build_event(
        "CONVERSATION_TURN",
        payload,
        {
            "namespace": template.namespace,
            "run_id": template.run_id,
            "correlation_id": template.correlation_id,
            "session_id": template.session_id,
            "user_id": template.user_id,
        },
        "session",
        template.session_id,
        1,
        template.event_time,
        metadata={"model_revision": "synthetic-model-v1", "nullable": None},
    )
    payload["mode"] = "assist"
    raw, headers, topic, key = codec.encode(built)
    result = sdk.validate_event(raw, headers, topic, key)
    assert isinstance(result, ValidEvent) and result.source_record is None
    assert result.document["metadata"]["model_revision"] == "synthetic-model-v1"
    assert result.document["metadata"]["nullable"] is None
    assert result.envelope.payload["mode"] == "fixed"
    assert isinstance(sdk.validate_event(b"\xff", headers, topic, key), ValidationFailure)


@pytest.mark.parametrize("metadata", [[], False, 0, ""])
def test_builder_does_not_coerce_invalid_metadata_to_an_empty_object(codec, metadata):
    record = event()
    with pytest.raises(RecordInvalid, match="INVALID_TYPE"):
        codec.build_event(
            record.event_type,
            record.payload,
            {
                "namespace": record.namespace,
                "run_id": record.run_id,
                "correlation_id": record.correlation_id,
                "session_id": record.session_id,
                "user_id": record.user_id,
            },
            record.aggregate_type,
            record.aggregate_id,
            1,
            record.event_time,
            metadata=metadata,
        )


def test_escaped_invalid_unicode_is_a_validation_failure_not_a_hashing_crash(codec):
    record = event()
    _, headers, topic, key = codec.encode(record)
    document = record.model_dump(mode="json", exclude_unset=True)
    document["metadata"]["unsupported_scalar"] = "\ud800"
    raw = json.dumps(document, ensure_ascii=True).encode()
    failure = codec.validate_event(raw, headers, topic, key)
    assert isinstance(failure, ValidationFailure) and failure.reason_code == "INVALID_JSON"


def test_publisher_requires_delivery_ack_and_freezes_native_settings(codec):
    publisher = KafkaPublisher(codec, "explicit-kafka-double", producer_factory=ProducerDouble)
    record = event()
    ack = publisher.publish_event(record, record.topic(), record.kafka_key())
    assert ack.event_id == record.event_id and ack.offset == 0
    assert publisher.pending_bytes == 0 and not publisher.pending
    assert publisher.producer.settings == {
        **PRODUCER_SETTINGS,
        "bootstrap.servers": "explicit-kafka-double",
    }
    publisher.close()


def test_ack_uncertainty_retry_preserves_identity_and_exact_wire_bytes(codec):
    publisher = KafkaPublisher(codec, "explicit-kafka-double", producer_factory=ProducerDouble)
    publisher.producer.deliver = False
    record = event()
    with pytest.raises(RetryablePublishError) as failure:
        publisher.publish_event(record, record.topic(), record.kafka_key(), timeout=0.003)
    assert failure.value.uncertain and failure.value.event_id == record.event_id
    assert len(publisher.pending) == 1 and publisher.pending_bytes > 0
    publisher.producer.deliver = True
    ack = publisher.publish_event(record, record.topic(), record.kafka_key())
    assert ack.event_id == record.event_id
    assert all(item[2] == publisher.producer.records[0][2] for item in publisher.producer.records)
    assert (
        canonical_json(record.model_dump(mode="json", exclude_unset=True))
        == publisher.producer.records[0][2]
    )
    publisher.close()


def test_queue_saturation_and_changed_inflight_identity_fail_without_drop(codec, monkeypatch):
    monkeypatch.setattr(publisher_module, "MAX_PENDING_RECORDS", 1)
    publisher = KafkaPublisher(codec, "explicit-kafka-double", producer_factory=ProducerDouble)
    publisher.producer.deliver = False
    record = event()
    with pytest.raises(RetryablePublishError):
        publisher.publish_event(record, record.topic(), record.kafka_key(), timeout=0.002)
    another = record.model_copy(update={"event_id": str(uuid4())})
    with pytest.raises(RetryablePublishError) as failure:
        publisher.publish_event(another, another.topic(), another.kafka_key())
    assert failure.value.reason == "PUBLISH_QUEUE_FULL" and not failure.value.uncertain
    changed = record.model_copy(update={"produced_at": datetime.now(UTC)})
    with pytest.raises(ValueError, match="identity cannot change"):
        publisher.publish_event(changed, changed.topic(), changed.kafka_key())
    assert len(publisher.producer.records) == 1
    with pytest.raises(RetryablePublishError):
        publisher.close(timeout=0)
    publisher.producer.deliver = True
    publisher.close()


def test_publish_failure_never_returns_queued_success(codec):
    publisher = KafkaPublisher(codec, "explicit-kafka-double", producer_factory=ProducerDouble)
    publisher.producer.error = object()
    record = event()
    with pytest.raises(RetryablePublishError, match="DELIVERY_UNCONFIRMED"):
        publisher.publish_event(record, record.topic(), record.kafka_key())
    assert not publisher.pending and publisher.pending_bytes == 0
    publisher.close()


def test_optional_envelope_properties_survive_relay_serialization(codec):
    document = examples()["CONVERSATION_TURN"]
    document["future_optional_property"] = {"explicit_null": None}
    record = EventEnvelope.model_validate(document)
    raw, headers, topic, key = codec.encode(record)
    assert codec.cache.validate(raw, headers, topic, key).document == document


def test_byte_budget_and_native_queue_full_do_not_claim_delivery(codec, monkeypatch):
    publisher = KafkaPublisher(codec, "explicit-kafka-double", producer_factory=ProducerDouble)
    monkeypatch.setattr(publisher_module, "MAX_PENDING_BYTES", 1)
    record = event()
    with pytest.raises(RetryablePublishError) as failure:
        publisher.publish_event(record, record.topic(), record.kafka_key())
    assert not failure.value.uncertain and not publisher.producer.records
    monkeypatch.setattr(publisher_module, "MAX_PENDING_BYTES", 64 * 1024 * 1024)

    def native_full(*args, **kwargs):
        raise BufferError("explicit native queue double full")

    publisher.producer.produce = native_full
    with pytest.raises(RetryablePublishError, match="PUBLISH_NOT_QUEUED"):
        publisher.publish_event(record, record.topic(), record.kafka_key())
    assert not publisher.pending and publisher.pending_bytes == 0
    publisher.close()


def test_public_publish_binding_and_analytics_dlq_notice(codec, monkeypatch):
    monkeypatch.setattr(
        sdk,
        "KafkaPublisher",
        lambda configured, bootstrap: KafkaPublisher(
            configured, "explicit-kafka-double", producer_factory=ProducerDouble
        ),
    )
    value = diagnostic().model_copy(update={"source_service": "analytics"})
    notice = sdk.build_dlq_notice(value)
    ack = sdk.publish_event(notice, notice.topic(), notice.kafka_key())
    assert ack.event_id == value.diagnostic_id and ack.topic.endswith(".dead-letter.v1")
    sdk.close_transport()
    assert sdk._codec is None and sdk._publisher is None


@pytest.mark.parametrize("bootstrap", ["", False])
def test_invalid_bootstrap_does_not_silently_choose_another_broker(codec, tmp_path, bootstrap):
    path = tmp_path / "cache.json"
    path.write_text(
        json.dumps(
            {"compatibility": "BACKWARD_TRANSITIVE", "schemas": list(codec.cache.entries.values())}
        )
    )
    with pytest.raises(ValueError, match="nonempty"):
        sdk.configure_transport(cache_path=path, bootstrap_servers=bootstrap)
    assert sdk._codec is codec


def test_released_history_id_is_hash_verified_and_validates_offline(codec):
    legacy = copy.deepcopy(codec.cache.entries["conversation-events.v1-value"]["schema"])
    legacy.pop("additionalProperties")
    legacy["definitions"]["EventMetadata"].pop("additionalProperties")
    historical = {
        "subject": "conversation-events.v1-value",
        "id": 777,
        "version": 1,
        "sha256": schema_hash(legacy),
        "schema": legacy,
    }
    manifest = {
        "compatibility": "BACKWARD_TRANSITIVE",
        "schemas": list(codec.cache.entries.values()),
        "historical_schemas": [historical],
    }
    cache = SchemaCache(manifest)
    raw, headers, topic, key = codec.encode(event())
    checked = cache.validate(raw, [headers[0], ("schema-id", b"777")], topic, key)
    assert checked.schema_id == 777
    legacy["title"] = "unverified history"
    historical["sha256"] = schema_hash(legacy)
    with pytest.raises(SchemaUnavailable, match="historical"):
        SchemaCache(manifest)


def test_only_contiguous_durable_prefix_is_committed():
    worker = group()
    worker.consumer.messages.extend(MessageDouble(TOPIC, offset) for offset in range(3))
    records = sdk.consume_records(worker, [TOPIC], 3, 20)
    worker.mark_durable(records[2])
    assert not sdk.commit_offsets(worker, {(TOPIC, 0): 3}).succeeded
    assert not worker.consumer.commits
    worker.mark_durable(records[0])
    assert worker.durable_next_offsets() == {(TOPIC, 0): 1}
    assert sdk.commit_offsets(worker, {(TOPIC, 0): 1}).succeeded
    worker.mark_durable(records[1])
    worker.consumer.fail_commit = True
    assert not sdk.commit_offsets(worker, {(TOPIC, 0): 3}).succeeded
    assert worker._buffered_count() == 2
    worker.consumer.fail_commit = False
    assert sdk.commit_offsets(worker, worker.durable_next_offsets()).succeeded
    assert worker._buffered_count() == 0 and worker.buffer_bytes == 0
    worker.close()


def test_revoke_commits_only_durable_prefix_and_fences_old_records():
    worker = group()
    worker.consumer.messages.extend(MessageDouble(TOPIC, offset) for offset in range(2))
    records = worker.consume_records([TOPIC], 2, 20)
    worker.mark_durable(records[0])
    worker._on_revoke(worker.consumer, [TopicPartition(TOPIC, 0)])
    assert worker.consumer.commits[0][0].offset == 1
    worker._on_assign(worker.consumer, [TopicPartition(TOPIC, 0)])
    with pytest.raises(ValueError, match="revoked"):
        worker.mark_durable(records[1])
    assert not worker.commit_offsets({(TOPIC, 0): 2}).succeeded
    worker.close()


def test_lost_assignment_never_commits_even_a_durable_record():
    worker = group()
    worker.consumer.messages.append(MessageDouble(TOPIC, 0))
    record = worker.consume_records([TOPIC], 1, 20)[0]
    worker.mark_durable(record)
    worker._on_lost(worker.consumer, [TopicPartition(TOPIC, 0)])
    assert not worker.consumer.commits and worker.buffer_bytes == 0
    worker.close()


def test_partial_commit_releases_only_acknowledged_partition():
    worker = ConsumerGroup(
        "bench-m03-unit.analytics.v1",
        [TOPIC],
        "explicit-kafka-double",
        consumer_factory=lambda settings: ConsumerDouble(settings, partitions=2),
    )
    worker.consumer.messages.extend(MessageDouble(TOPIC, 0, partition=p) for p in (0, 1))
    records = worker.consume_records([TOPIC], 2, 20)
    for record in records:
        worker.mark_durable(record)
    worker.consumer.commit = lambda **kwargs: [TopicPartition(TOPIC, 0, 1)]
    outcome = worker.commit_offsets(worker.durable_next_offsets())
    assert not outcome.succeeded and len(outcome.committed_next_offsets) == 1
    assert worker._buffered_count() == 1 and worker.durable_next_offsets() == {(TOPIC, 1): 1}
    worker._on_lost(worker.consumer, [TopicPartition(TOPIC, 1)])
    worker.close()


def test_consumer_handle_cannot_be_shared_between_worker_threads():
    worker = group()
    with ThreadPoolExecutor(max_workers=1) as executor:
        with pytest.raises(RuntimeError, match="another worker thread"):
            executor.submit(worker.consume_records, [TOPIC], 1, 0).result()
    worker.close()


def test_backpressure_pauses_fetching_but_keeps_polling(monkeypatch):
    import shared.event_transport.consumer as consumer_module

    monkeypatch.setattr(consumer_module, "GROUP_MAX_RECORDS", 3)
    worker = group()
    worker.consumer.messages.extend(MessageDouble(TOPIC, offset) for offset in range(3))
    records = worker.consume_records([TOPIC], 3, 10)
    assert len(records) == 2 and worker.consumer.paused
    polls = worker.consumer.polls
    assert worker.consume_records([TOPIC], 1, 5) == []
    assert worker.consumer.polls > polls and worker._buffered_count() <= 3
    for record in records:
        worker.mark_durable(record)
    worker.commit_offsets(worker.durable_next_offsets())
    assert worker.consume_records([TOPIC], 1, 10)[0].offset == 2
    worker.close()


def test_raw_source_bytes_and_tombstone_are_preserved(codec):
    worker = group()
    headers = (("x", b"\xff"), ("x", None), ("x", b""))
    worker.consumer.messages.append(MessageDouble(TOPIC, 0, value=None, key=None, headers=headers))
    record = worker.consume_records([TOPIC], 1, 20)[0]
    assert record.value_bytes is None and record.key_bytes is None and record.headers == headers
    assert raw_fingerprint(None, None, ()) != raw_fingerprint(b"", b"", ())
    failure = codec.validate_event(None, headers, TOPIC, None, source_record=record)
    assert (
        isinstance(failure, ValidationFailure)
        and failure.original_content_hash == record.raw_sha256
    )
    worker.close()


def test_oversized_source_rewinds_without_committing():
    worker = group()
    worker.consumer.messages.append(MessageDouble(TOPIC, 0, value=b"x" * (1024 * 1024 + 1)))
    with pytest.raises(ConsumerBufferError):
        worker.consume_records([TOPIC], 1, 20)
    assert worker.consumer.seeks[0].offset == 0 and not worker.consumer.commits
    assert not worker.ledger[(TOPIC, 0)]
    worker.close()


def test_worker_budgets_sum_to_group_limits_and_have_distinct_static_ids():
    workers = [group(workers=3, worker_index=index) for index in range(3)]
    assert sum(worker.record_limit for worker in workers) == 2000
    assert sum(worker.byte_limit for worker in workers) == 16 * 1024 * 1024
    assert len({worker.settings["group.instance.id"] for worker in workers}) == 3
    assert all(not worker.settings["enable.auto.commit"] for worker in workers)
    assert all(not worker.settings["enable.auto.offset.store"] for worker in workers)
    for worker in workers:
        worker.close()


def test_dlq_constructor_is_pure_and_helper_requires_existing_tx_and_real_outbox(monkeypatch):
    value = diagnostic()
    assert build_dlq_notice(value) == build_dlq_notice(value)
    assert build_dlq_notice(value).event_id == value.diagnostic_id
    with pytest.raises(ValueError, match="existing caller-owned"):
        quarantine_local_diagnostic(
            SimpleNamespace(info=SimpleNamespace(transaction_status=TransactionStatus.IDLE)), value
        )
    monkeypatch.setitem(sys.modules, "shared.outbox", ModuleType("shared.outbox"))
    with pytest.raises(OutboxUnavailable):
        quarantine_local_diagnostic(
            SimpleNamespace(info=SimpleNamespace(transaction_status=TransactionStatus.INTRANS)),
            value,
        )
