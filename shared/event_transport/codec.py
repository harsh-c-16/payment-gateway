"""Pure constructors/validation using a verified cache; never contact Kafka."""

import copy
import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from shared.contracts.events import (
    EVENTS,
    DlqNotice,
    EventEnvelope,
    LocalDiagnostic,
    ReasonCode,
    ValidationFailure,
    ValidEvent,
)

from .schemas import RecordInvalid, canonical_json


class EventCodec:
    def __init__(self, cache, *, source_service=None, dataset_revision=None):
        self.cache = cache
        self.source_service = source_service
        self.dataset_revision = dataset_revision

    def encode(self, event, topic=None, key=None):
        if not isinstance(event, (EventEnvelope, DlqNotice)):
            raise TypeError("publish an EventEnvelope or DlqNotice")
        document = event.model_dump(mode="json", exclude_unset=True)
        raw = canonical_json(document)
        topic = event.topic() if topic is None else topic
        key = event.kafka_key().encode() if key is None else key
        if isinstance(key, str):
            key = key.encode("utf-8")
        subject = event.topic().split(".", 1)[1] + "-value"
        headers = (
            ("content-type", b"application/json"),
            ("schema-id", str(self.cache.entries[subject]["id"]).encode()),
        )
        self.cache.validate(raw, headers, topic, key)
        return raw, headers, topic, key

    def build_event(
        self,
        event_type,
        payload,
        context,
        aggregate_type,
        aggregate_id,
        aggregate_version,
        event_time,
        *,
        metadata=None,
        source_service=None,
    ):
        if not isinstance(event_type, str) or event_type not in EVENTS:
            raise RecordInvalid(ReasonCode.UNKNOWN_EVENT_TYPE, "event_type")
        context = context.model_dump() if hasattr(context, "model_dump") else dict(context)
        if metadata is not None and not isinstance(metadata, dict):
            raise RecordInvalid(ReasonCode.INVALID_TYPE, "metadata")
        metadata = copy.deepcopy({} if metadata is None else metadata)
        if self.dataset_revision is not None:
            metadata.setdefault("dataset_revision", self.dataset_revision)
        source = self.source_service if source_service is None else source_service
        event = EventEnvelope.model_validate(
            {
                "event_id": str(uuid4()),
                "event_type": event_type,
                "schema_version": 1,
                "event_time": event_time,
                "produced_at": datetime.now(UTC),
                "namespace": context["namespace"],
                "run_id": context["run_id"],
                "source_service": EVENTS[event_type][1] if source is None else source,
                "correlation_id": context["correlation_id"],
                "session_id": context.get("session_id"),
                "user_id": context.get("user_id"),
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "aggregate_version": aggregate_version,
                "payload": copy.deepcopy(payload),
                "metadata": metadata,
            }
        )
        self.encode(event)
        return event

    def validate_event(
        self, raw_bytes, headers, topic, key, *, source_record=None, ingested_at=None
    ):
        if source_record is not None:
            if (raw_bytes, tuple(headers), topic, key) != (
                source_record.value_bytes,
                source_record.headers,
                source_record.topic,
                source_record.key_bytes,
            ):
                raise ValueError("source record and validation input differ")
            ingested_at = source_record.ingested_at if ingested_at is None else ingested_at
        if not isinstance(raw_bytes, bytes) and source_record is None:
            raise TypeError("raw_bytes must be bytes; tombstones require their SourceRecord")
        original_hash = (
            source_record.raw_sha256
            if source_record is not None
            else hashlib.sha256(raw_bytes).hexdigest()
        )
        try:
            checked = self.cache.validate(raw_bytes, headers, topic, key, ingested_at=ingested_at)
        except RecordInvalid as exc:
            return ValidationFailure(
                reason_code=exc.reason,
                field_path=exc.path,
                diagnostic_message=exc.reason.value,
                original_content_hash=original_hash,
            )
        return ValidEvent(
            checked.envelope,
            checked.schema_id,
            checked.canonical_content_hash,
            source_record,
            checked.document,
        )


def build_dlq_notice(diagnostic):
    diagnostic = LocalDiagnostic.model_validate(diagnostic)
    return DlqNotice(
        event_id=diagnostic.diagnostic_id,
        diagnostic_id=diagnostic.diagnostic_id,
        namespace=diagnostic.namespace,
        run_id=diagnostic.run_id,
        schema_version=1,
        produced_at=diagnostic.created_at,
        source_service=diagnostic.source_service,
        origin_kind="kafka_record"
        if diagnostic.source_coordinates is not None
        else "service_diagnostic",
        source_locator=diagnostic.source_coordinates or diagnostic.restricted_content_reference,
        reason_code=diagnostic.reason_code,
        created_at=diagnostic.created_at,
    )
