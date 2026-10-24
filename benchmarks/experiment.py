"""Isolated P4 lifecycle. Provider callbacks are explicit and never auto-mocked."""

import asyncio
import json
import re
from dataclasses import dataclass
from uuid import uuid4

from benchmarks.scheduler import Limits, journal, run_schedule, utc_now
from benchmarks.workloads import generate_workload
from projectctl.artifacts import content_hash, file_hash, save_evidence, write_json
from projectctl.config import InputError, repo_path, resolve_config
from projectctl.models import ExitCode, Metric
from projectctl.providers import DependencyError, Invocation, ProviderResult


@dataclass(frozen=True)
class ExperimentBindings:
    """Callbacks are provider handoffs, not alternative domain implementations.

    prepare(ctx, manifest) must create NEW state and return created_new/namespace.
    validate checks provider readiness, seeds, hashes and resolved variant controls.
    drain(ctx, deadline_seconds) waits on downstream work; audit(ctx, directory)
    reads the complete planned journal and approved snapshots via an independent
    oracle. It returns passed: bool|None, with evidence/reasons. Missing callbacks
    remain dependency failures. Fault callbacks must retain barrier receipts.
    """

    mode: str
    driver: object
    catalog_manifest: dict | None = None
    templates: tuple = ()
    prepare: object = None
    validate: object = None
    drain: object = None
    audit: object = None
    fault: object = None


def admission_reconciliation(directory, manifest):
    """Reconcile every frozen physical offer, including misses/unknown admissions."""
    expected, observed, failures = {}, {}, []
    with (directory / "planned.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            expected[row["logical_record_id"]] = row
    sources = set()
    phases = {
        phase: {
            key: 0
            for key in (
                "planned",
                "attempted",
                "acknowledged",
                "failed",
                "missed",
                "unresolved",
                "acknowledged_in_window",
                "acknowledged_after_cutoff",
            )
        }
        for phase in ("warmup", "measurement")
    }
    with (directory / "emissions.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            identifier = row["record_id"]
            if identifier in observed:
                failures.append("DUPLICATE_EMISSION_RECEIPT:" + identifier)
            observed[identifier] = row
            if row.get("error") == "AckError":
                failures.append("ACK_CONTRACT_VIOLATION:" + identifier)
            if identifier not in expected:
                failures.append("UNPLANNED_EMISSION:" + identifier)
                continue
            phase = expected[identifier]["phase"]
            count = phases[phase]
            count["attempted"] += row["actual_send_at"] is not None
            outcome = row["outcome"]
            if outcome not in {"acknowledged", "failed", "missed", "unresolved"}:
                failures.append("INVALID_EMISSION_OUTCOME:" + identifier)
                continue
            count[outcome] += 1
            ack = row["ack_elapsed_seconds"]
            if outcome == "acknowledged":
                start = (manifest["warmup_seconds"] or 0) if phase == "measurement" else 0
                end = (
                    start + (manifest["duration_seconds"] or 0)
                    if phase == "measurement"
                    else (manifest["warmup_seconds"] or 0)
                )
                inside = manifest["kind"] != "sustained" or start <= ack < end
                count["acknowledged_in_window"] += inside
                count["acknowledged_after_cutoff"] += not inside and ack >= end
                if row["source"]:
                    source = row["source"]
                    coordinate = (source["topic"], source["partition"], source["offset"])
                    if coordinate in sources:
                        failures.append("DUPLICATE_BROKER_COORDINATE:" + identifier)
                    sources.add(coordinate)
            original = expected[identifier].get("duplicate_of")
            if original is not None:
                original_row = observed.get(f"source-{original:06}")
                # Completion order is arbitrary; compare after the entire journal is read.
                if (
                    row["wire_sha256"] is not None
                    and original_row
                    and (original_row["wire_sha256"] != row["wire_sha256"])
                ):
                    failures.append("DUPLICATE_BYTES_CHANGED:" + identifier)
    for identifier, row in expected.items():
        phases[row["phase"]]["planned"] += 1
        if identifier not in observed:
            failures.append("MISSING_EMISSION_RECEIPT:" + identifier)
        original = row.get("duplicate_of")
        if (
            original is not None
            and identifier in observed
            and observed[identifier]["wire_sha256"] is not None
        ):
            before = observed.get(f"source-{original:06}")
            if not before or before["wire_sha256"] != observed[identifier]["wire_sha256"]:
                failures.append("DUPLICATE_BYTES_CHANGED:" + identifier)
    missing = sorted(
        identifier
        for identifier in expected
        if identifier not in observed or observed[identifier]["outcome"] != "acknowledged"
    )
    return {
        "passed": not failures and not missing,
        "phases": phases,
        "missing_or_unadmitted_ids": missing,
        "invariant_failures": failures,
        "expected_count": len(expected),
        "observed_count": len(observed),
        "boundary": "broker/API admission; downstream correctness is separate",
    }


async def run_experiment(
    workload_id,
    variant_id,
    repetition,
    seed,
    namespace=None,
    duration_seconds=None,
    warmup_seconds=None,
    fault_profile="none",
    *,
    config,
    bindings=None,
    run_id=None,
    evidence_kind="performance",
    order=None,
):
    """Return the finalized RunArtifactManifest; failures retain journals and hashes."""
    from projectctl.cli import preflight

    config = config.model_copy(deep=True)
    config.generator.seed = seed
    resolved = resolve_config(config, workload_id, variant_id)
    if fault_profile not in resolved.faults:
        raise InputError("unregistered fault profile")
    if evidence_kind not in {"test", "smoke", "performance"}:
        raise InputError("explicit evidence kind required")
    run_id = run_id or str(uuid4())
    from uuid import UUID

    try:
        if str(UUID(run_id)) != run_id:
            raise ValueError
    except (ValueError, TypeError, AttributeError) as exc:
        raise InputError("canonical UUID run ID required") from exc
    namespace = namespace or "bench-" + run_id
    if not re.fullmatch(r"bench-[a-z0-9][a-z0-9-]{0,55}", namespace) or re.match(
        r"bench-(dev|live|prod|production)(-|$)", namespace
    ):
        raise InputError("experiment requires a fresh isolated bench namespace")
    if type(repetition) is not int or repetition <= 0:
        raise InputError("positive repetition required")
    mode = bindings.mode if bindings else "offline"
    if mode not in {"offline", "real", "stub"} or (
        mode == "stub" and evidence_kind == "performance"
    ):
        raise InputError("stub bindings are restricted to explicit test/smoke evidence")
    item = resolved.workloads[workload_id]
    duration = resolved.timing.duration_seconds if duration_seconds is None else duration_seconds
    warmup = resolved.timing.warmup_seconds if warmup_seconds is None else warmup_seconds
    if (
        type(duration) is not int
        or duration <= 0
        or type(warmup) is not int
        or warmup < 0
        or resolved.timing.drain_seconds > 120
    ):
        raise InputError("integer phase durations and drain <=120 seconds required")
    if (
        evidence_kind == "performance"
        and item.kind == "sustained"
        and (duration, warmup) != (600, 60)
    ):
        raise InputError("sustained performance runs require 60/600 seconds")
    if item.kind == "sustained":
        resolved.timing.duration_seconds = duration
        resolved.timing.warmup_seconds = warmup
    invocation = Invocation(
        "benchmark run", {"faults": [fault_profile]}, resolved, run_id, namespace
    )
    reasons = preflight(resolved, workload_id) if mode != "stub" else []
    if bindings is None:
        reasons.append(
            f"{workload_id} provider adapters unavailable; see docs/jaineel/p4_workloads.md"
        )
    elif any(
        getattr(bindings, name) is None
        for name in ("driver", "prepare", "validate", "drain", "audit")
    ):
        reasons.append("explicit driver/prepare/validate/drain/independent audit bindings required")
    if fault_profile != "none" and (bindings is None or bindings.fault is None):
        reasons.append("named fault/barrier adapter unavailable")
    if reasons:
        result = ProviderResult(ExitCode.DEPENDENCY_FAILURE, tuple(reasons), mode)
        output = save_evidence(
            invocation,
            result,
            workload=workload_id,
            variant=variant_id,
            repetition=repetition,
            order=order or {},
        )
        directory = repo_path(output["evidence_dir"])
        return json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    directory = repo_path(resolved.artifacts.root) / run_id
    directory.mkdir(parents=True, exist_ok=False)
    context = {
        "namespace": namespace,
        "run_id": run_id,
        "seed": seed,
        "workload_id": workload_id,
        "variant_id": variant_id,
        "parameters": (order or {}).get(
            "effective_parameters", resolved.variants[variant_id].config.model_dump()
        ),
        "dataset": resolved.dataset.model_dump(),
        "assistant": resolved.assistant.model_dump(),
        "planned_path": str(directory / "planned.jsonl"),
        "evidence_directory": str(directory),
        "topic": namespace + ".inventory-events.v1",
    }
    started, code, correctness, generator = utc_now(), ExitCode.COMPLETED, None, None
    fault_task = None
    stage = "prepare"
    with (directory / "lifecycle.jsonl").open("x", encoding="utf-8") as lifecycle:

        def record(name, details=None):
            journal(lifecycle, {"stage": name, "at": utc_now(), "details": details})

        try:
            record("prepare")
            workload = generate_workload(
                workload_id,
                seed,
                bindings.catalog_manifest,
                rate_per_second=item.rate_per_second,
                duration_seconds=duration,
                warmup_seconds=warmup,
                key_count=resolved.generator.key_count,
                key_distribution=resolved.generator.key_distribution,
                templates=bindings.templates,
                record_count=item.record_count,
                warmups_per_query=item.warmups_per_query or 0,
                executions_per_query=item.executions_per_query or 1,
            )
            manifest = workload.as_dict()
            context["workload_manifest"] = manifest
            if item.template_sha256 and item.template_sha256 != manifest["logical_fixture_sha256"]:
                raise InputError("workload template hash differs from frozen configuration")
            with (directory / "planned.jsonl").open("x", encoding="utf-8") as planned:
                for row in workload.records():
                    journal(planned, row)
            manifest["planned_sha256"] = file_hash(directory / "planned.jsonl")
            write_json(directory / "workload_manifest.json", manifest)
            write_json(directory / "execution_order.json", order or {})
            prepared = await bindings.prepare(context, manifest)
            write_json(directory / "preparation.json", prepared)
            if prepared.get("namespace") != namespace or prepared.get("created_new") is not True:
                raise DependencyError("provider did not acknowledge a new isolated namespace")
            stage = "validate"
            record(stage)
            await bindings.validate(context, manifest)
            stage = "warmup"

            async def inject_fault():
                fault = resolved.faults[fault_profile]
                # Relative to the planned boundary, including any scheduler lateness.
                elapsed = measure_snapshot["elapsed_seconds"]
                await asyncio.sleep(max(0, warmup + fault.measurement_second - elapsed))
                receipt = await bindings.fault(context, fault_profile, fault.model_dump())
                journal(faults, receipt)
                if receipt.get("acknowledged") is not True or (
                    fault.barrier and receipt.get("barrier") != fault.barrier
                ):
                    raise DependencyError("fault boundary acknowledgement missing")

            def boundary(name, snapshot):
                nonlocal stage, fault_task, measure_snapshot
                stage = {"measurement": "measure"}.get(name, name)
                record(stage, snapshot)
                if name == "measurement" and fault_profile != "none":
                    measure_snapshot = snapshot
                    fault_task = asyncio.create_task(inject_fault())

            measure_snapshot = {}
            with (directory / "faults.jsonl").open("x", encoding="utf-8") as faults:
                generator = await run_schedule(
                    directory / "planned.jsonl",
                    directory,
                    bindings.driver,
                    context,
                    kind=item.kind,
                    warmup_seconds=warmup,
                    duration_seconds=duration,
                    drain_seconds=resolved.timing.drain_seconds,
                    limits=Limits(
                        min(resolved.generator.concurrency, 32)
                        if workload_id == "W-SEARCH"
                        else resolved.generator.concurrency,
                        resolved.generator.queue_limit,
                    ),
                    boundary=boundary,
                )
                remaining = generator["remaining_drain_seconds"]
                if remaining <= 0:
                    raise DependencyError("generator exhausted the declared drain deadline")
                async with asyncio.timeout(remaining):
                    await bindings.drain(context, remaining)
                    if fault_task:
                        await fault_task
            stage = "reconcile"
            record(stage)
            if file_hash(directory / "planned.jsonl") != manifest["planned_sha256"]:
                raise InputError("frozen planned journal was modified during the run")
            admission = admission_reconciliation(directory, manifest)
            write_json(directory / "admission.json", admission)
            audit = await bindings.audit(context, directory)
            write_json(directory / "audit.json", audit)
            correctness = audit.get("passed")
            if (correctness is not None and type(correctness) is not bool) or audit.get(
                "test_mode"
            ) != mode:
                raise DependencyError("independent audit mode/result contract invalid")
            write_json(directory / "correctness.json", {"admission": admission, "audit": audit})
            if workload_id == "W-IMPORT":
                with (directory / "emissions.jsonl").open(encoding="utf-8") as stream:
                    for line in stream:
                        details = json.loads(line).get("details") or {}
                        if "import_timings" in details:
                            write_json(directory / "import_timings.json", details["import_timings"])
                            break
            if correctness is False or admission["invariant_failures"]:
                code = ExitCode.CORRECTNESS_FAILURE
                reasons.append("independent reconciliation failed")
            elif correctness is None:
                code = ExitCode.DEPENDENCY_FAILURE
                reasons.append("downstream/business audit incomplete")
            elif not admission["passed"]:
                code = ExitCode.TARGET_MISSED
                reasons.append("planned load was not fully admitted; misses/unknowns retained")
        except (Exception, asyncio.CancelledError) as exc:
            code = (
                ExitCode.BAD_INPUT if isinstance(exc, InputError) else ExitCode.DEPENDENCY_FAILURE
            )
            reasons.append(f"{stage} failed: {type(exc).__name__}; no fallback used")
            record("failure", {"stage": stage, "error_type": type(exc).__name__})
        finally:
            if fault_task:
                if not fault_task.done():
                    fault_task.cancel()
                await asyncio.gather(fault_task, return_exceptions=True)
            record("persist")
    if (directory / "emissions.jsonl").is_file() and not (directory / "admission.json").exists():
        write_json(directory / "admission.json", admission_reconciliation(directory, manifest))
    if not (directory / "correctness.json").exists():
        write_json(
            directory / "correctness.json",
            {
                "passed": None,
                "status": "INCOMPLETE",
                "failed_stage": stage,
                "reasons": reasons,
                "downstream_reconciliation": "NOT_RUN",
            },
        )
    metrics = []
    sha = content_hash(resolved.model_dump())
    if generator and file_hash(directory / "planned.jsonl") == manifest["planned_sha256"]:
        admission = admission_reconciliation(directory, manifest)
        count = admission["phases"]["measurement"]
        denominator = generator["window_seconds"] or generator["measured_job_seconds"]
        for name, numerator in (
            ("generator_offered_rate", count["planned"]),
            ("admitted_rate", count["acknowledged_in_window"]),
        ):
            metrics.append(
                Metric(
                    name=name,
                    unit="operations/second",
                    value=numerator / denominator if denominator and denominator > 0 else None,
                    sample_count=count["planned"],
                    numerator=float(numerator),
                    denominator=denominator,
                    cohort={"sustained": "measurement", "finite": "finite_job", "queries": "query"}[
                        item.kind
                    ],
                    quantile_method=None,
                    unresolved_count=count["unresolved"],
                    timing_validity="VALID" if denominator and denominator > 0 else "MISSING",
                    run_id=run_id,
                    config_sha256=sha,
                    status="MEASURED" if denominator and denominator > 0 else "INCOMPLETE",
                    evidence_path="emissions.jsonl",
                )
            )
    metrics.append(
        Metric(
            name="gold_goodput",
            unit="events/second",
            value=None,
            sample_count=0,
            numerator=None,
            denominator=None,
            cohort={
                "sustained": "measurement",
                "finite": "finite_job",
                "queries": "query",
            }[item.kind],
            quantile_method=None,
            unresolved_count=None,
            timing_validity="NOT_RUN",
            run_id=run_id,
            config_sha256=sha,
            status="NOT_RUN",
            evidence_path=None,
        )
    )
    write_json(
        directory / "execution.json",
        {
            "evidence_kind": evidence_kind,
            "test_mode": mode,
            "order": order,
            "generator": generator,
            "sut_performance": "NOT_RUN" if mode == "stub" else "INCOMPLETE",
            "unavailable_collectors": ["timings.parquet", "lag.csv", "resources.csv"],
        },
    )
    output = save_evidence(
        invocation,
        ProviderResult(code, tuple(reasons), mode),
        workload=workload_id,
        variant=variant_id,
        repetition=repetition,
        execution={
            "status": "MEASURED" if code == 0 else "INCOMPLETE",
            "metrics": metrics,
            "started_at": started,
            "completed_at": utc_now(),
            "correctness_passed": correctness,
        },
    )
    return json.loads(
        (repo_path(output["evidence_dir"]) / "manifest.json").read_text(encoding="utf-8")
    )
