"""Owned P10 report schema. Measurements retain the canonical summary metric DTO."""

from typing import Literal

from pydantic import Field

from projectctl.models import ArtifactRef, Metric, Sha256, StrictModel


class ReportRun(StrictModel):
    run_id: str
    evidence_dir: str
    workload: str | None
    variant: str | None
    repetition: int | None
    namespace: str
    config_sha256: Sha256 | None
    manifest_sha256: Sha256
    status: Literal["MEASURED", "INCOMPLETE", "NOT_RUN"]
    test_mode: Literal["real", "stub", "offline"]
    exit_code: int
    correctness_passed: bool | None
    metrics: list[Metric]
    reasons: list[str]
    order: dict
    context: dict


class MatrixRunRef(StrictModel):
    run_id: str
    evidence_dir: str
    exit_code: Literal[0, 2, 3, 4, 5]


class ReportSupport(StrictModel):
    dataset_checks: ArtifactRef | None = None
    evaluations: list[ArtifactRef] = Field(default_factory=list)
    selection: ArtifactRef | None = None
    conclusions: list[ArtifactRef] = Field(default_factory=list)
    rehearsal: ArtifactRef | None = None


class MatrixResults(StrictModel):
    plan: str
    runs: list[MatrixRunRef]
    pending: list[dict]
    support: ReportSupport = Field(default_factory=ReportSupport)


class MatrixPlan(StrictModel):
    schema_version: Literal[1]
    order_seed: int
    trials: list[dict]
    pending: list[dict]


class ReportTable(StrictModel):
    name: str
    required: bool
    status: Literal["MEASURED", "INCOMPLETE", "NOT_RUN"]
    run_ids: list[str]


class FinalReport(StrictModel):
    schema_version: Literal[1]
    status: Literal["MEASURED", "INCOMPLETE"]
    required_core_complete: bool
    release_status: Literal["REVIEW_REQUIRED", "INCOMPLETE"]
    runs: list[ReportRun]
    tables: list[ReportTable]
    comparisons: list[dict]
    dataset_checks: dict | None
    correctness: list[dict]
    targets: list[dict]
    limitations: list[str]
    not_run: list[str]
    evidence_index: list[ArtifactRef]
    content_sha256: Sha256 | None = Field(default=None)
