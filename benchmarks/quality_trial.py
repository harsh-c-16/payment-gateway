"""Separately named real G1 trial; never reduces the W-QUALITY/T-03 fixture."""

import asyncio
import hashlib
from uuid import uuid4

from benchmarks.composition import catalog_projection
from benchmarks.quality_audit import fixture_rows
from benchmarks.quality_binding import QualityLifecycle, QualityOwners, build_quality_bindings
from benchmarks.scheduler import Limits, journal, run_schedule
from benchmarks.workloads import generate_workload
from projectctl.artifacts import canonical_json, file_hash, write_json
from projectctl.cli import preflight
from projectctl.config import resolve_config


async def run_g1(config, directory, *, owners=None):
    """Retain raw evidence and return exit 4 before any I/O when dependencies lack.

    directory must be new. This is correctness evidence, never a performance
    measurement, and never a substitute for the separate full T-03 gate.
    """
    directory.mkdir(parents=True, exist_ok=False)
    owners = owners or QualityOwners()
    binding = build_quality_bindings(config, owners=owners)
    reasons = [*preflight(config, "W-QUALITY"), *binding.dependency_reasons]
    run_id = str(uuid4())
    result = {
        "gate": "G1",
        "run_id": run_id,
        "test_mode": "real",
        "status": "NOT_RUN",
        "exit_code": 4,
        "passed": None,
        "reasons": reasons,
        "T-03": "NOT_RUN",
        "performance": "NOT_RUN",
    }
    if reasons:
        write_json(directory / "summary.json", result)
        return result
    resolved = resolve_config(config, "W-QUALITY", "B0")
    projection = catalog_projection(config)
    lifecycle = QualityLifecycle(resolved, owners, projection, gate="G1")
    manifest = generate_workload("W-QUALITY", config.generator.seed, projection).as_dict() | {
        "gate": "G1",
        "expected_counts": lifecycle.counts,
        "phase_counts": {"measurement": 3},
        "workload_id": "G1",
    }
    manifest["source_quality_recipe_sha256"] = manifest.pop("logical_fixture_sha256")
    manifest["logical_fixture_sha256"] = hashlib.sha256(canonical_json(manifest)).hexdigest()
    context = {
        "namespace": "bench-" + run_id,
        "run_id": run_id,
        "seed": config.generator.seed,
        "workload_id": "G1",
        "variant_id": "B0",
        "parameters": resolved.variants["B0"].config.model_dump(),
        "evidence_directory": str(directory),
    }
    path = directory / "planned.jsonl"
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        for row in fixture_rows(config.generator.seed, "G1"):
            journal(
                stream,
                row
                | {
                    "phase": "measurement",
                    "offset_seconds": None,
                    "scenario_id": row["logical_record_id"],
                },
            )
    planned_hash = file_hash(path)
    manifest["planned_sha256"] = planned_hash
    write_json(directory / "workload_manifest.json", manifest)
    try:
        async with asyncio.timeout(120):
            await lifecycle.prepare(context, manifest)
            await lifecycle.validate(context, manifest)
        observer = lifecycle.observer(context, directory, "test")
        async with observer:
            generator = await run_schedule(
                path,
                directory,
                lifecycle.driver,
                context,
                kind="finite",
                warmup_seconds=0,
                duration_seconds=1,
                drain_seconds=120,
                limits=Limits(1, 10),
            )
            async with asyncio.timeout(generator["remaining_drain_seconds"]):
                await lifecycle.drain(context, generator["remaining_drain_seconds"])
            if file_hash(path) != planned_hash:
                raise ValueError("frozen G1 plan changed")
            audit = await lifecycle.audit(context, directory)
            write_json(directory / "correctness.json", audit)
            result.update(
                passed=audit["passed"],
                status=audit["status"],
                exit_code=0 if audit["passed"] else 3 if audit["passed"] is False else 4,
            )
    except Exception as error:
        result.update(
            status="INCOMPLETE",
            reasons=[
                f"G1 callback failed: {type(error).__name__}; raw evidence retained; no fallback"
            ],
        )
    finally:
        if lifecycle.publisher is not None:
            try:
                await lifecycle.publisher.close()
            except Exception as error:
                result.update(exit_code=4, passed=None, status="INCOMPLETE")
                result["reasons"].append("publisher close failed: " + type(error).__name__)
    write_json(directory / "summary.json", result)
    return result
