"""All-domain transactional Silver with B0/O1 grouping and durable contributions."""

from dataclasses import replace
from datetime import UTC, datetime
from time import monotonic
from typing import Annotated

from psycopg.types.json import Jsonb
from pydantic import Field, TypeAdapter, field_validator

from pipelines.gold import aggregate_gold
from pipelines.gold.business import GoldConflict
from pipelines.ingestion import BronzeCapture, read_bronze
from pipelines.ingestion.receipts import persist_capture
from shared.contracts.analytics import BatchOutcome, DurableOffset, RawBatchReceipt
from shared.contracts.common import Identifier, WireModel
from shared.contracts.events import EventEnvelope, Namespace, ReasonCode, ValidationFailure
from shared.telemetry.metrics import Telemetry

from .db import journal, one, sink_lock
from .event_time import track_event_time
from .normalization import normalize_payload
from .observations import enqueue_observation, observe, recover_observations
from .quarantine import route_dlq
from .sink_observations import observe_sink_batch


class UnsupportedEvent(RuntimeError):
    pass


class BatchConfig(WireModel):
    run_id: Identifier
    sink_batch_max_rows: Annotated[int, Field(strict=True, ge=1, le=100)] = 1

    @field_validator("sink_batch_max_rows")
    @classmethod
    def supported_rows(cls, value):
        if value not in (1, 100):
            raise ValueError("Use B0 (1 row) or O1 (100 rows)")
        return value


class AnalyticsPipeline:
    def __init__(
        self,
        connect,
        store,
        codec,
        *,
        code_commit,
        transform_version="m07-business-v1",
        sink_batch_max_rows=1,
    ):
        if not callable(connect):
            raise TypeError("connect must create an autocommit analytics connection")
        self.sink_batch_max_rows = BatchConfig(
            run_id="configuration", sink_batch_max_rows=sink_batch_max_rows
        ).sink_batch_max_rows
        self.connect, self.store, self.codec = connect, store, codec
        self.after_sink_commit = None
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

    def curate_silver(self, raw_receipt, batch_config, *, replay_id=None):
        config = BatchConfig.model_validate(batch_config)
        raw_receipt = RawBatchReceipt.model_validate(raw_receipt)
        records = read_bronze(self.store, raw_receipt)
        if not records:
            raise ValueError("A nonempty Bronze capture is required")
        namespace = records[0].source_namespace
        from pipelines.replay.jobs import capture_scope

        with self.connect() as tx:
            namespace, locators, replay_ingress = capture_scope(tx, self, raw_receipt, replay_id)
        if locators is not None:
            records = [
                r
                for r, captured in zip(records, raw_receipt.records, strict=True)
                if captured.source.raw_locator in locators
            ]
            if not records:
                raise ValueError("Replay capture has no selected records")
        self.recover_observations(namespace)
        # Captured rows remain non-final until their complete sink transaction commits.
        with self.connect() as tx, tx.transaction():
            sink_lock(tx, namespace)
            # Hold the namespace lock while checking that live ingestion cannot claim a replay.
            capture_scope(tx, self, raw_receipt, replay_id)
            persist_capture(
                tx,
                raw_receipt,
                self.store,
                effective_namespace=namespace if replay_id is not None else None,
                locators=locators,
                replay_ingress=replay_ingress,
            )
        counts = dict.fromkeys(("new_valid", "duplicate_delivery", "invalid", "redelivery_noop"), 0)
        for offset in range(0, len(records), config.sink_batch_max_rows):
            batch = records[offset : offset + config.sink_batch_max_rows]
            started_at = datetime.now(UTC)
            started = monotonic()
            results = []
            batch_counts = dict.fromkeys(counts, 0)
            with self.connect() as tx:
                with tx.transaction():
                    sink_lock(tx, namespace)
                    for record in batch:
                        result = self._curate_record(tx, namespace, record, config, replay_id)
                        results.append(result)
                        batch_counts[result[0]] += 1
                    sequence = tx.execute(
                        """INSERT INTO sink_batches(namespace,run_id,capture_id,replay_id,
                        code_commit,transform_version,sources,batch_rows,new_valid,duplicate_delivery,
                        invalid,redelivery_noop,started_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        RETURNING batch_sequence""",
                        (
                            namespace,
                            config.run_id,
                            raw_receipt.capture_id,
                            replay_id,
                            self.code_commit,
                            self.transform_version,
                            Jsonb(
                                [
                                    dict(topic=r.topic, partition=r.partition, offset=r.offset)
                                    for r in batch
                                ]
                            ),
                            len(batch),
                            *batch_counts.values(),
                            started_at,
                        ),
                    ).fetchone()[0]
                duration = monotonic() - started
                committed_at = datetime.now(UTC)
            observe_sink_batch(self.connect, namespace, sequence, committed_at, duration)
            for disposition, job, reason in results:
                if job is not None:
                    self._observe(namespace, job)  # Only after the entire batch commits.
                counts[disposition] += 1
                self.telemetry.record(
                    "source_records_total", 1, pipeline="analytics", disposition=disposition
                )
                if disposition == "new_valid":
                    self.telemetry.record("silver_unique_total", 1)
                elif disposition == "invalid":
                    self.telemetry.record("quarantine_total", 1, reason=reason)
            self.telemetry.record("sink_batch_rows", len(batch))
            self.telemetry.record("sink_flush_duration_seconds", duration)
            if self.after_sink_commit is not None:
                self.after_sink_commit(namespace)
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

    def _curate_record(self, tx, namespace, record, config, replay_id):
        stored = one(
            tx,
            """SELECT * FROM source_receipts WHERE namespace=%s AND topic=%s
            AND partition=%s AND offset_number=%s FOR UPDATE""",
            (namespace, record.topic, record.partition, record.offset),
        )
        if stored["disposition"] is not None:
            return "redelivery_noop", None, None
        record = replace(record, ingested_at=stored["ingested_at"])
        checked = self.codec.validate_event(
            record.value_bytes,
            record.headers,
            record.topic,
            record.key_bytes,
            source_record=record,
        )
        if replay_id is not None and not isinstance(checked, ValidationFailure):
            from pipelines.replay.repairs import repair_failure

            checked = repair_failure(checked, record.raw_sha256, tx) or checked
        return self._finalize(tx, stored, record, checked, config)

    def _finalize(self, tx, stored, record, checked, config):
        failure = checked if isinstance(checked, ValidationFailure) else None
        namespace = stored["namespace"]
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
                track_event_time(tx, record, event, new_fact=False, namespace=namespace)
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
                record,
                failure,
                tx,
                run_id=config.run_id,
                transform_version=self.transform_version,
                effective_namespace=namespace,
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
            return disposition, None, failure.reason_code.value
        return (
            disposition,
            enqueue_observation(
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
            ),
            None,
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
                stored["namespace"],
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
        aggregate_gold(
            [event],
            tx,
            transform_version=self.transform_version,
            effective_namespace=stored["namespace"],
        )
        track_event_time(tx, record, event, new_fact=True, namespace=stored["namespace"])

    def ingest_once(self, group, *, run_id, max_records=100):
        records = group.consume_records(group.topics, max_records, 50)
        if not records:
            return None
        receipt = BronzeCapture(self.store).ingest_bronze(records)
        outcome = self.curate_silver(
            receipt, {"run_id": run_id, "sink_batch_max_rows": self.sink_batch_max_rows}
        )
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

    def replay_bronze(self, request):
        from pipelines.replay.jobs import create_replay, run_replay

        accepted = create_replay(self, request)
        return run_replay(self, accepted.replay_id)

    def query_gold(self, namespace, table, date_from, date_to, currency=None):
        from pipelines.storage.readers import query_gold

        return query_gold(self, namespace, table, date_from, date_to, currency)
