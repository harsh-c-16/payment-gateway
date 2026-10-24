"""Strict evaluation contracts; generated schemas are checked into contracts/evaluation."""

from enum import IntEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")]
Namespace = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]{0,61}$")]
UUIDString = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$"),
    Field(json_schema_extra={"format": "uuid"}),
]
UTCStamp = Annotated[
    str,
    StringConstraints(pattern=r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z$"),
    Field(json_schema_extra={"format": "date-time"}),
]
Positive = Annotated[int, Field(gt=0)]
Nonnegative = Annotated[int, Field(ge=0)]
WorkloadID = Literal[
    "W-IMPORT",
    "W-PIPE",
    "W-QUALITY",
    "W-SEARCH",
    "W-CHECKOUT",
    "W-INTEGRATED",
    "W-ANALYTICS",
    "W-AGENT",
]
VariantID = Literal[
    "B0",
    "O1",
    "O2",
    "O3",
    "P10",
    "P30",
    "P33",
    "F-COMPACT",
    "F-PARTITION",
    "I0",
    "I1",
    "R-EXACT",
    "R-ANN",
    "A-FIXED",
    "A-ASSIST",
]


class ExitCode(IntEnum):
    COMPLETED = 0
    BAD_INPUT = 2
    CORRECTNESS_FAILURE = 3
    DEPENDENCY_FAILURE = 4
    TARGET_MISSED = 5


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Allocation(StrictModel):
    cpu_cores: Annotated[float, Field(gt=0)]
    memory_mib: Positive


class Profile(StrictModel):
    name: Identifier
    allocation_status: Literal["planned", "enforced"]
    sut: Allocation
    generator: Allocation
    services: list[Identifier]
    service_allocations: dict[Identifier, Allocation]
    connection_pools: dict[Identifier, Positive]
    consumer_group_total: Allocation


class Dataset(StrictModel):
    source_path: str
    expected_sha256: Sha256 | None
    rules_version: Literal["flipkart-v1"]
    dictionary_path: str | None
    dictionary_sha256: Sha256 | None
    canonical_manifest: str | None
    sku_manifest: str | None


class Workload(StrictModel):
    required: bool
    kind: Literal["finite", "sustained", "queries"]
    rate_per_second: Annotated[float, Field(gt=0)] | None
    record_count: Positive | None
    query_count: Positive | None
    warmups_per_query: Nonnegative | None
    executions_per_query: Positive | None
    template_sha256: Sha256 | None


class Parameters(StrictModel):
    partitions: Positive
    consumers: Positive
    sink_batch_max_rows: Positive
    sink_batch_max_wait_ms: Nonnegative
    raw_capture_max_bytes: Positive
    raw_capture_max_wait_ms: Positive
    gold_publish_interval_ms: Positive
    outbox_poll_ms: Positive
    outbox_pass_limit: Positive
    expiry_sweep_ms: Positive
    catalog_optional_btree: bool
    catalog_load_mode: Literal["row", "copy"]
    catalog_chunk_rows: Positive
    file_layout: Literal["small", "compact", "partition_comparison"]
    target_file_mib: Positive
    codec: Literal["zstd"]
    partitioning: Literal["date_type", "unpartitioned"]
    retrieval_mode: Literal["filter_only", "lexical", "hybrid_exact", "hybrid_ann"]
    assistant_mode: Literal["fixed", "assist"]
    hnsw_m: Positive
    hnsw_ef_construction: Positive
    hnsw_ef_search: Positive
    iterative_scan: Literal["off", "strict_order", "relaxed_order"]


class Variant(StrictModel):
    optional: bool
    workloads: list[WorkloadID]
    allowed_differences: list[str]
    config: Parameters


class Timing(StrictModel):
    warmup_seconds: Nonnegative
    duration_seconds: Positive
    drain_seconds: Positive
    repetitions: Positive
    sample_interval_seconds: Positive


class Generator(StrictModel):
    seed: Nonnegative
    template_sha256: Sha256 | None
    rate_per_second: Annotated[float, Field(gt=0)]
    concurrency: Positive
    queue_limit: Positive
    key_distribution: Literal["uniform", "hot80"]
    key_count: Positive
    payment_success_percent: Annotated[int, Field(ge=0, le=100)]
    payment_delay_ms: Nonnegative
    initial_on_hand: Nonnegative


class Retrieval(StrictModel):
    mode: Literal["filter_only", "lexical", "hybrid_exact", "hybrid_ann"]
    query_sha256: Sha256 | None
    label_sha256: Sha256 | None
    embedding_sha256: Sha256 | None
    model_sha256: Sha256 | None
    cache_state: Literal["warm", "cold"]
    top_k: Annotated[int, Field(ge=1, le=20)]
    candidate_k: Positive
    index_inventory: list[str]


class Assistant(StrictModel):
    mode: Literal["fixed", "assist"]
    allow_intent_llm: bool
    llm_max_calls: Annotated[int, Field(ge=0, le=1)]
    timeout_ms: Literal[1500]
    turn_deadline_ms: Literal[3000]
    provider: str | None
    model: str | None
    prompt_sha256: Sha256 | None

    @model_validator(mode="after")
    def call_budget(self):
        enabled = self.mode == "assist" and self.allow_intent_llm
        if self.llm_max_calls != int(enabled):
            raise ValueError("fixed/disabled assistant requires 0 calls; enabled assist requires 1")
        if self.mode == "fixed" and self.allow_intent_llm:
            raise ValueError("fixed mode cannot enable generative calls")
        return self


class Fault(StrictModel):
    trigger: Literal["none", "measurement_second", "barrier"]
    measurement_second: Nonnegative | None
    barrier: str | None
    target: str | None
    duration_seconds: Nonnegative
    recovery_deadline_seconds: Positive

    @model_validator(mode="after")
    def trigger_fields(self):
        if self.trigger != "none" and (self.measurement_second is None or self.target is None):
            raise ValueError("fault requires measurement_second and target")
        if self.trigger == "barrier" and not self.barrier:
            raise ValueError("barrier fault requires a named acknowledgement barrier")
        return self


class ArtifactConfig(StrictModel):
    root: str
    schema_version: Literal[1]
    retain_raw_timings: Literal[True]


class LockRef(StrictModel):
    path: str | None
    sha256: Sha256 | None


class ConfigurationLocks(StrictModel):
    application: LockRef
    infrastructure: LockRef
    event_schemas: LockRef


class EvaluationConfig(StrictModel):
    schema_version: Literal[1]
    state: Literal["draft", "ready"]
    profile: Profile
    dataset: Dataset
    workloads: dict[WorkloadID, Workload]
    variants: dict[VariantID, Variant]
    timing: Timing
    generator: Generator
    retrieval: Retrieval
    assistant: Assistant
    faults: dict[Identifier, Fault]
    artifacts: ArtifactConfig
    locks: ConfigurationLocks


class MatrixRow(StrictModel):
    workload: WorkloadID
    variants: list[VariantID] = Field(min_length=1)
    retrieval_modes: list[Literal["filter_only", "lexical"]] = Field(default_factory=list)
    key_distributions: list[Literal["uniform", "hot80"]] = Field(default_factory=list)
    rates_per_second: list[Positive] = Field(default_factory=list)
    faults: list[Identifier] = Field(default_factory=lambda: ["none"])
    selection: Literal["registered", "measured_best"] = "registered"


class MatrixConfig(StrictModel):
    schema_version: Literal[1]
    repetitions: Positive
    rows: list[MatrixRow] = Field(min_length=1)


class ArtifactRef(StrictModel):
    path: str
    sha256: Sha256


class EvidenceSlot(StrictModel):
    path: str
    status: Literal["NOT_RUN", "PRESENT"]


class GitState(StrictModel):
    commit: str | None
    dirty: bool | None


class Locks(StrictModel):
    application_sha256: Sha256 | None
    infrastructure_sha256: Sha256 | None
    event_schemas_sha256: Sha256 | None
    image_digests: list[str] | None
    model_revision: str | None


class Host(StrictModel):
    platform: str
    machine: str
    python: str
    logical_cpu_count: Positive | None
    cpu_model: str | None
    physical_cores: Positive | None
    total_memory_bytes: Positive | None
    storage_description: str | None
    resources_verified: bool


class WorkloadProtocol(StrictModel):
    kind: Literal["finite", "sustained", "queries"]
    warmup_seconds: Nonnegative | None
    duration_seconds: Positive | None
    drain_seconds: Positive
    repetitions: Positive
    record_count: Positive | None
    query_count: Positive | None
    warmups_per_query: Nonnegative | None
    executions_per_query: Positive | None


class RunManifest(StrictModel):
    schema_version: Literal[1]
    run_id: UUIDString
    namespace: Namespace
    command: str
    workload_id: WorkloadID | None
    variant_id: VariantID | None
    repetition: Positive | None
    seed: Nonnegative | None
    status: Literal["NOT_RUN", "INCOMPLETE", "MEASURED"]
    created_at: UTCStamp
    started_at: UTCStamp | None
    completed_at: UTCStamp | None
    git: GitState
    locks: Locks
    host: Host
    topics_partitions_groups: list[str]
    resolved_config: EvaluationConfig | None
    config_sha256: Sha256 | None
    fault_profiles: list[str]
    workload_protocol: WorkloadProtocol | None
    required_artifacts: list[EvidenceSlot]
    artifacts: list[ArtifactRef]
    correctness_passed: bool | None
    content_sha256: Sha256 | None


class Metric(StrictModel):
    model_config = ConfigDict(
        json_schema_extra={
            "allOf": [
                {
                    "if": {"properties": {"status": {"const": "NOT_RUN"}}},
                    "then": {
                        "properties": {"value": {"type": "null"}, "sample_count": {"const": 0}}
                    },
                },
                {
                    "if": {"properties": {"status": {"const": "MEASURED"}}},
                    "then": {
                        "properties": {
                            "value": {"type": "number"},
                            "sample_count": {"minimum": 1},
                            "evidence_path": {"type": "string", "minLength": 1},
                        }
                    },
                },
            ]
        }
    )
    name: str
    unit: str
    value: float | None
    sample_count: Nonnegative
    numerator: float | None
    denominator: float | None
    cohort: Literal["measurement", "finite_job", "query"]
    quantile_method: str | None
    unresolved_count: Nonnegative | None
    timing_validity: Literal["NOT_RUN", "VALID", "MISSING", "RECOVERY_UPPER_BOUND"]
    run_id: UUIDString
    config_sha256: Sha256 | None
    status: Literal["NOT_RUN", "INCOMPLETE", "MEASURED"]
    evidence_path: str | None

    @model_validator(mode="after")
    def evidence_required(self):
        if self.status == "NOT_RUN" and (self.value is not None or self.sample_count != 0):
            raise ValueError("NOT_RUN metrics require null value and zero samples")
        if self.status == "MEASURED" and (
            self.value is None or not self.evidence_path or self.sample_count == 0
        ):
            raise ValueError("MEASURED metrics require value, samples and evidence")
        return self


class Summary(StrictModel):
    schema_version: Literal[1]
    run_id: UUIDString
    namespace: Namespace
    command: str
    status: Literal["NOT_RUN", "INCOMPLETE", "MEASURED"]
    exit_code: Literal[0, 2, 3, 4, 5]
    test_mode: Literal["offline", "stub", "real"]
    reasons: list[str]
    metrics: list[Metric]
    artifact_refs: list[ArtifactRef]
    config_sha256: Sha256 | None


class ExpectedCounts(StrictModel):
    planned: Nonnegative
    unique_valid: Nonnegative
    duplicate_deliveries: Nonnegative
    invalid: Nonnegative


class FixtureManifest(StrictModel):
    schema_version: Literal[1]
    workload_id: WorkloadID
    template_version: str
    seed: Nonnegative
    logical_fixture_sha256: Sha256
    expected_counts: ExpectedCounts
    schedule_parameters: Workload
    source_manifests: list[ArtifactRef]
    content_sha256: Sha256 | None
