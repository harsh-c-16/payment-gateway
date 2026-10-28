"""Canonical hashing and truthful P1 evidence; no synthetic performance measurements."""

import hashlib
import json
import os
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from projectctl.config import ROOT, repo_path, workload_timing
from projectctl.models import (
    ArtifactRef,
    EvidenceSlot,
    GitState,
    Host,
    Locks,
    Metric,
    RunManifest,
    Summary,
    WorkloadProtocol,
)


def canonical_json(value) -> bytes:
    def check_keys(item):
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise ValueError("JSON object keys must be strings")
            for child in item.values():
                check_keys(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                check_keys(child)

    check_keys(value)
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def content_hash(value: dict) -> str:
    return hashlib.sha256(
        canonical_json({k: v for k, v in value.items() if k != "content_sha256"})
    ).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_state() -> GitState:
    def git(*args):
        return subprocess.run(
            ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    try:
        return GitState(commit=git("rev-parse", "HEAD"), dirty=bool(git("status", "--porcelain")))
    except (OSError, subprocess.CalledProcessError):
        return GitState(commit=None, dirty=None)


REQUIRED_ARTIFACTS = (
    "emissions.jsonl",
    "timings.parquet",
    "lag.csv",
    "resources.csv",
    "correctness.json",
    "plans/",
    "manifests/",
    "faults.jsonl",
    "tests.jsonl",
    "comparison.md",
)


def write_json(path: Path, value):
    # Exclusive creation prevents accidental evidence replacement.
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(canonical_json(value).decode("utf-8") + "\n")


def save_evidence(
    invocation, result, *, workload=None, variant=None, repetition=None, execution=None, order=None
):
    config = invocation.config
    root = repo_path(config.artifacts.root) if config else ROOT / "artifacts" / "projectctl"
    directory = root / invocation.run_id
    # P4 creates journals first. Only its explicit execution path may reuse that directory.
    if execution is None:
        directory.mkdir(parents=True, exist_ok=False)
    elif not directory.is_dir() or (directory / "manifest.json").exists():
        raise ValueError("experiment directory missing or already finalized")
    config_dict = config.model_dump() if config else None
    config_sha = content_hash(config_dict) if config_dict else None
    refs = []
    if order is not None and execution is None:
        write_json(directory / "execution_order.json", order)
        refs.append(
            ArtifactRef(
                path="execution_order.json", sha256=file_hash(directory / "execution_order.json")
            )
        )
    if config:
        write_json(directory / "resolved_config.json", config_dict)
        refs.append(
            ArtifactRef(
                path="resolved_config.json", sha256=file_hash(directory / "resolved_config.json")
            )
        )
    protocol = None
    cohort = "measurement"
    if config and workload:
        item = config.workloads[workload]
        timing = workload_timing(config, workload)
        protocol = WorkloadProtocol(
            kind=item.kind,
            warmup_seconds=timing["warmup_seconds"],
            duration_seconds=timing["duration_seconds"],
            drain_seconds=timing["drain_seconds"],
            repetitions=config.timing.repetitions,
            record_count=item.record_count,
            query_count=item.query_count,
            warmups_per_query=item.warmups_per_query,
            executions_per_query=item.executions_per_query,
        )
        cohort = {"sustained": "measurement", "finite": "finite_job", "queries": "query"}[item.kind]
    summary = Summary(
        schema_version=1,
        run_id=invocation.run_id,
        namespace=invocation.namespace,
        command=invocation.action,
        status=execution["status"] if execution else "NOT_RUN",
        exit_code=int(result.code),
        test_mode=result.test_mode,
        reasons=list(result.reasons),
        config_sha256=config_sha,
        metrics=execution["metrics"]
        if execution
        else [
            Metric(
                name=name,
                unit=unit,
                value=None,
                sample_count=0,
                numerator=None,
                denominator=None,
                cohort=cohort,
                quantile_method=None,
                unresolved_count=None,
                timing_validity="NOT_RUN",
                run_id=invocation.run_id,
                config_sha256=config_sha,
                status="NOT_RUN",
                evidence_path=None,
            )
            for name, unit in [("elapsed_seconds", "seconds"), ("goodput", "items/second")]
        ],
        artifact_refs=refs.copy(),
    )
    if execution:
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.name != "resolved_config.json":
                refs.append(
                    ArtifactRef(path=path.relative_to(directory).as_posix(), sha256=file_hash(path))
                )
        summary.artifact_refs = refs.copy()
    write_json(directory / "summary.json", summary.model_dump())
    refs.append(ArtifactRef(path="summary.json", sha256=file_hash(directory / "summary.json")))
    lock = ROOT / "uv.lock"
    manifest = RunManifest(
        schema_version=1,
        run_id=invocation.run_id,
        namespace=invocation.namespace,
        command=invocation.action,
        workload_id=workload,
        variant_id=variant,
        repetition=repetition,
        seed=config.generator.seed if config else None,
        status=execution["status"]
        if execution
        else ("NOT_RUN" if result.code == 0 else "INCOMPLETE"),
        created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        started_at=execution["started_at"] if execution else None,
        completed_at=execution["completed_at"] if execution else None,
        git=git_state(),
        locks=Locks(
            application_sha256=file_hash(lock) if lock.exists() else None,
            infrastructure_sha256=None,
            event_schemas_sha256=None,
            image_digests=None,
            model_revision=None,
        ),
        host=Host(
            platform=platform.platform(),
            machine=platform.machine(),
            python=platform.python_version(),
            logical_cpu_count=os.cpu_count(),
            cpu_model=platform.processor() or None,
            physical_cores=None,
            total_memory_bytes=None,
            storage_description=None,
            resources_verified=False,
        ),
        topics_partitions_groups=execution.get("topics_partitions_groups", []) if execution else [],
        resolved_config=config,
        config_sha256=config_sha,
        fault_profiles=invocation.arguments.get("faults", ["none"]),
        workload_protocol=protocol,
        required_artifacts=[
            EvidenceSlot(path=name, status="PRESENT" if (directory / name).exists() else "NOT_RUN")
            for name in REQUIRED_ARTIFACTS
        ],
        artifacts=refs,
        correctness_passed=execution["correctness_passed"] if execution else None,
        content_sha256=None,
    )
    environment = execution.get("environment") if execution else None
    if environment:
        manifest.host.resources_verified = True
        manifest.host.cpu_model = environment["host"]["cpu_model"]
        manifest.host.physical_cores = environment["host"]["physical_cores"]
        manifest.host.total_memory_bytes = environment["host"]["total_memory_bytes"]
        manifest.host.storage_description = environment["host"]["storage"]
        manifest.locks.infrastructure_sha256 = config.locks.infrastructure.sha256
        manifest.locks.event_schemas_sha256 = config.locks.event_schemas.sha256
        manifest.locks.image_digests = environment["image_digests"]
    manifest.content_sha256 = content_hash(manifest.model_dump())
    write_json(directory / "manifest.json", manifest.model_dump())
    output = summary.model_dump()
    output["evidence_dir"] = directory.relative_to(ROOT).as_posix()
    return output
