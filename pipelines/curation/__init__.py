"""All-domain B0 transactional Silver and unique pipeline-minute contributions."""

from dataclasses import replace
from time import monotonic
from typing import Annotated

from psycopg.types.json import Jsonb
from pydantic import Field, TypeAdapter

from pipelines.gold import aggregate_gold
from pipelines.gold.business import GoldConflict
from pipelines.ingestion import BronzeCapture, read_bronze
from pipelines.ingestion.receipts import persist_capture
from shared.contracts.analytics import BatchOutcome, DurableOffset
from shared.contracts.common import Identifier, WireModel
from shared.contracts.events import EventEnvelope, Namespace, ReasonCode, ValidationFailure
from shared.telemetry.metrics import Telemetry

from .db import journal, one, sink_lock
from .normalization import normalize_payload
from .observations import enqueue_observation, observe, recover_observations
from .quarantine import route_dlq


class UnsupportedEvent(RuntimeError):
    pass


class BatchConfig(WireModel):
    run_id: Identifier
    sink_batch_max_rows: Annotated[int, Field(strict=True, ge=1, le=1)] = 1


class AnalyticsPipeline:
    def __init__(self, connect, store, codec, *, code_commit, transform_version="m07-business-v1"):
        if not callable(connect):
            raise TypeError("connect must create an autocommit analytics connection")
        self.connect, self.store, self.codec = connect, store, codec
        self.code_commit = TypeAdapter(Identifier).validate_python(code_commit)
        self.transform_version = TypeAdapter(Identifier).validate_python(transform_version)
        self.telemetry = Telemetry(
            label_values={
                "pipeline": ["analytics"],
                "disposition": ["new_valid", "duplicate_delivery", "invalid", "redelivery_noop"],
                "reason": [reason.value for reason in ReasonCode],
            }
        )

    def _observe(self, namespace, job_id):
        observe(self.connect, namespace, job_id)

    def recover_observations(self, namespace):
        TypeAdapter(Namespace).validate_python(namespace)
        return recover_observations(self.connect, namespace)

    def curate_silver(self, raw_receipt, batch_config):
        config = BatchConfig.model_validate(batch_config)
        records = read_bronze(self.store, raw_receipt)
        if not records:
            raise ValueError("A nonempty Bronze capture is required")
        namespace = records[0].source_namespace
        self.recover_observations(namespace)
        # Captured rows remain non-final until each B0 sink transaction below commits.
        with self.connect() as tx, tx.transaction():
            sink_lock(tx, namespace)
            persist_capture(tx, raw_receipt, self.store)
        counts = dict.fromkeys(("new_valid", "duplicate_delivery", "invalid", "redelivery_noop"), 0)
        for record in records:
            started = monotonic()
            with self.connect() as tx, tx.transaction():
                sink_lock(tx, namespace)
                stored = one(
                    tx,
                    """SELECT * FROM source_receipts WHERE namespace=%s AND topic=%s
                    AND partition=%s AND offset_number=%s FOR UPDATE""",
                    (namespace, record.topic, record.partition, record.offset),
                )
                if stored["disposition"] is not None:
                    disposition, job = "redelivery_noop", None
                else:
                    record = replace(record, ingested_at=stored["ingested_at"])
                    checked = self.codec.validate_event(
                        record.value_bytes,
                        record.headers,
                        record.topic,
                        record.key_bytes,
                        source_record=record,
                    )
                    disposition, job = self._finalize(tx, stored, record, checked, config)
            if job is not None:
                self._observe(namespace, job)  # Only after the sink COMMIT acknowledgement.
            counts[disposition] += 1
            self.telemetry.record(
                "source_records_total", 1, pipeline="analytics", disposition=disposition
            )
            self.telemetry.record("sink_batch_rows", 1)
            self.telemetry.record("sink_flush_duration_seconds", monotonic() - started)
            if disposition == "new_valid":
                self.telemetry.record("silver_unique_total", 1)
        candidates = {}
        for record in records:
            key = (record.topic, record.partition)
            candidates[key] = max(candidates.get(key, 0), record.offset + 1)
        with self.connect() as tx:
            pending = one(
                tx, "SELECT count(*) AS n FROM export_pending WHERE namespace=%s", (namespace,)
            )["n"]
            offsets = []
            for (topic, partition), next_offset in candidates.items():
                gap = one(
                    tx,
                    """SELECT min(offset_number) AS gap FROM source_receipts
                    WHERE namespace=%s AND topic=%s AND partition=%s AND disposition IS NULL
                      AND offset_number<%s""",
                    (namespace, topic, partition, next_offset),
                )["gap"]
                offsets.append(
                    DurableOffset(
                        topic=topic, partition=partition, offset=next_offset if gap is None else gap
                    )
                )
        self.telemetry.record("gold_pending_events", pending)
        return BatchOutcome(
            source_records=len(records),
            **counts,
            durable_offsets_by_partition=offsets,
            pending_export_count=pending,
        )

    def _finalize(self, tx, stored, record, checked, config):
        failure = checked if isinstance(checked, ValidationFailure) else None
        namespace = record.source_namespace
        event_id = None
        if failure is None:
            event = checked.envelope
            if not isinstance(event, EventEnvelope):
                raise UnsupportedEvent("DLQ notices are not business Silver facts")
            event_id = event.event_id
            existing = one(
                tx,
                "SELECT content_hash FROM silver_events WHERE namespace=%s AND event_id=%s",
                (namespace, event_id),
            )
            version = one(
                tx,
                """SELECT event_id FROM silver_events WHERE namespace=%s
                AND source_service=%s AND aggregate_type=%s AND aggregate_id=%s
                AND aggregate_version=%s""",
                (
                    namespace,
                    event.source_service,
                    event.aggregate_type,
                    event.aggregate_id,
                    event.aggregate_version,
                ),
            )
            if existing and existing["content_hash"] != checked.canonical_content_hash:
                failure = ValidationFailure(
                    reason_code=ReasonCode.EVENT_ID_CONFLICT,
                    field_path="event_id",
                    diagnostic_message="Event identity has changed content",
                    original_content_hash=record.raw_sha256,
                )
            elif existing:
                disposition = "duplicate_delivery"
            elif version:
                failure = ValidationFailure(
                    reason_code=ReasonCode.AGGREGATE_VERSION_CONFLICT,
                    field_path="aggregate_version",
                    diagnostic_message="Aggregate version already exists",
                    original_content_hash=record.raw_sha256,
                )
            else:
                try:
                    with tx.transaction():
                        self._insert_valid(tx, checked, record, stored)
                except GoldConflict as exc:
                    failure = ValidationFailure(
                        reason_code=exc.reason,
                        field_path="payload",
                        diagnostic_message=str(exc),
                        original_content_hash=record.raw_sha256,
                    )
                else:
                    disposition = "new_valid"
        if failure is not None:
            route_dlq(
                record, failure, tx, run_id=config.run_id, transform_version=self.transform_version
            )
            disposition, event_id = "invalid", None
        visible = (
            None
            if event_id is None
            else one(
                tx,
                "SELECT * FROM event_visibility WHERE namespace=%s AND event_id=%s",
                (namespace, event_id),
            )
        )
        tx.execute(
            """UPDATE source_receipts SET disposition=%s,event_id=%s,reason_code=%s,
            gold_visible_at=%s,visibility_generation=%s,timing_validity=%s
            WHERE namespace=%s AND topic=%s AND partition=%s AND offset_number=%s""",
            (
                disposition,
                event_id,
                None if failure is None else failure.reason_code.value,
                None if visible is None else visible["observed_at"],
                None
                if visible is None or visible["observed_at"] is None
                else visible["generation"],
                "recovery_upper_bound"
                if visible and visible["timing_validity"] == "recovery_upper_bound"
                else "missing",
                namespace,
                record.topic,
                record.partition,
                record.offset,
            ),
        )
        journal(tx, namespace, stored)
        if event_id is None:
            return disposition, None
        return disposition, enqueue_observation(
            tx,
            namespace,
            "sink",
            [
                {
                    "topic": record.topic,
                    "partition": record.partition,
                    "offset_number": record.offset,
                }
            ],
        )

    def _insert_valid(self, tx, checked, record, stored):
        event = checked.envelope
        tx.execute(
            """INSERT INTO silver_events
                    (namespace,event_id,content_hash,event_time,event_type,source_service,
                     aggregate_type,aggregate_id,aggregate_version,document,source_topic,
                     source_partition,source_offset,raw_locator,normalized_payload)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                record.source_namespace,
                event.event_id,
                checked.canonical_content_hash,
                event.event_time,
                event.event_type,
                event.source_service,
                event.aggregate_type,
                event.aggregate_id,
                event.aggregate_version,
                Jsonb(checked.document),
                record.topic,
                record.partition,
                record.offset,
                stored["raw_locator"],
                Jsonb(normalize_payload(event)),
            ),
        )
        aggregate_gold([event], tx, transform_version=self.transform_version)

    def ingest_once(self, group, *, run_id, max_records=100):
        records = group.consume_records(group.topics, max_records, 50)
        if not records:
            return None
        receipt = BronzeCapture(self.store).ingest_bronze(records)
        outcome = self.curate_silver(receipt, {"run_id": run_id})
        for record in records:
            group.mark_durable(record)
        committed = group.commit_offsets(group.durable_next_offsets())
        if not committed.succeeded:
            raise RuntimeError("Kafka offset commit is unconfirmed; durable sources may redeliver")
        return outcome

    def publish_snapshot(self, namespace):
        from pipelines.storage.publication import publish_snapshot

        return publish_snapshot(self, namespace)

    def active_manifest(self, namespace, dataset):
        from pipelines.storage.readers import active_manifest

        return active_manifest(self.connect, namespace, dataset)

    def publish_candidate(self, candidate):
        from pipelines.storage.candidates import publish_candidate

        return publish_candidate(self, candidate)

    def query_gold(self, namespace, table, date_from, date_to, currency=None):
        from pipelines.storage.readers import query_gold

        return query_gold(self, namespace, table, date_from, date_to, currency)
