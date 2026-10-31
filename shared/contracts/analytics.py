"""Analytics wire contracts; Jaineel's receipt agreement recorded in the M02 handoff."""

from typing import Annotated, Literal

from pydantic import Field, JsonValue, model_validator

from shared.contracts.common import Identifier, Money, UTCTime, UUIDText, WireModel
from shared.contracts.events import (
    Count,
    IsolatedNamespace,
    Namespace,
    Positive,
    ReasonCode,
    Sha256,
    SourceLocator,
)


class FileDescriptor(WireModel):
    path: Annotated[str, Field(min_length=1)]
    sha256: Sha256
    byte_size: Count
    row_count: Count
    schema_name: Identifier
    schema_version: Positive
    partition_values: dict[str, str | None]
    min_event_time: UTCTime | None
    max_event_time: UTCTime | None

    @model_validator(mode="after")
    def ordered_times(self):
        if (self.min_event_time is None) != (self.max_event_time is None):
            raise ValueError("file time bounds are both null or both present")
        if self.min_event_time is not None and self.min_event_time > self.max_event_time:
            raise ValueError("file minimum time exceeds maximum")
        return self


class SourceRange(WireModel):
    topic: str
    partition: Count
    first_offset: Count
    next_offset: Count
    receipt_membership_ref: Identifier

    @model_validator(mode="after")
    def ordered_offsets(self):
        if self.next_offset <= self.first_offset:
            raise ValueError("source range must be a nonempty half-open interval")
        return self


class DatasetManifest(WireModel):
    namespace: Namespace
    dataset: Literal["silver", "gold"]
    generation: Positive
    parent_generation: Positive | None
    files: list[FileDescriptor]
    source_ranges: list[SourceRange]
    transform_version: Identifier
    code_commit: Identifier
    input_manifest_ids: list[Identifier]
    created_at: UTCTime

    @model_validator(mode="after")
    def coherent_generation(self):
        if self.parent_generation is not None and self.parent_generation >= self.generation:
            raise ValueError("parent must precede manifest generation")
        if len({file.path for file in self.files}) != len(self.files):
            raise ValueError("manifest contains repeated file paths")
        return self


class ManifestCandidate(WireModel):
    base_generation: Positive
    candidate_manifest: DatasetManifest
    logical_row_digest: Sha256
    row_count: Count
    monetary_totals_by_currency: dict[Literal["INR"], Money]
    transformation_reason: Identifier


class DurableOffset(WireModel):
    topic: str
    partition: Count
    offset: Count


class BatchOutcome(WireModel):
    source_records: Count
    new_valid: Count
    duplicate_delivery: Count
    invalid: Count
    redelivery_noop: Count
    durable_offsets_by_partition: list[DurableOffset]
    pending_export_count: Count

    @model_validator(mode="after")
    def reconciles(self):
        if self.source_records != (
            self.new_valid + self.duplicate_delivery + self.invalid + self.redelivery_noop
        ):
            raise ValueError("source dispositions must reconcile")
        return self


class ReconciliationResult(WireModel):
    passed: Annotated[bool, Field(strict=True)]
    counts_by_disposition: dict[str, Count]
    missing_ids: list[UUIDText]
    unexpected_ids: list[UUIDText]
    conflicting_ids: list[UUIDText]
    totals_by_currency: dict[Literal["INR"], Money]
    invariant_failures: list[str]
    source_manifest_ids: list[Identifier]


class GoldQueryResult(WireModel):
    generation: Positive
    rows: list[dict[str, JsonValue]]
    queried_at: UTCTime


class SourceReceipt(WireModel):
    namespace: Namespace
    source: SourceLocator
    raw_sha256: Sha256
    event_id: UUIDText | None
    disposition: Literal["new_valid", "duplicate_delivery", "invalid", "redelivery_noop"]
    reason_code: ReasonCode | None
    ingested_at: UTCTime
    bronze_durable_at: UTCTime
    silver_committed_observed_at: UTCTime | None
    gold_visible_at: UTCTime | None
    visibility_generation: Positive | None
    timing_validity: Literal["observed", "missing", "recovery_upper_bound"]


class ReceiptPage(WireModel):
    receipts: list[SourceReceipt]
    next_cursor: Identifier | None


class QuarantineRecord(WireModel):
    quarantine_id: UUIDText
    namespace: Namespace
    source_locator: SourceLocator
    raw_sha256: Sha256
    reason_code: ReasonCode
    validation_path: str | None
    diagnostic_message: str
    first_seen_at: UTCTime
    schema_version: Positive | None
    transform_version: Identifier
    repair_status: Literal["unrepaired", "repaired"]
    repair_reference: Identifier | None


class QuarantinePage(WireModel):
    records: list[QuarantineRecord]
    next_cursor: Identifier | None


class ReplayRequest(WireModel):
    source_manifest_ids: Annotated[list[Identifier], Field(min_length=1)]
    target_namespace: IsolatedNamespace
    transform_version: Identifier


class ReplayAccepted(WireModel):
    replay_id: UUIDText
    status_url: str


class ReplayStatus(WireModel):
    status: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED"]
    counts: dict[str, Count]
    reconciliation: ReconciliationResult | None
    error: dict[str, JsonValue] | None


class ReplayJob(WireModel):
    replay_id: UUIDText
    source_manifest_ids: list[Identifier]
    target_namespace: IsolatedNamespace
    transform_version: Identifier
    status: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED"]
    started_at: UTCTime
    completed_at: UTCTime | None
    reconciliation: ReconciliationResult | None
