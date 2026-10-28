"""P4 CLI orchestration. Empty production registry fails visibly, without doubles."""

import asyncio
import json
from uuid import uuid4

from benchmarks.experiment import run_experiment
from benchmarks.planning import plan_matrix, plan_trials
from benchmarks.planning import reusable_performance_run as reusable_run
from projectctl.artifacts import write_json
from projectctl.config import load_matrix, repo_path


def execute_benchmarks(args, registry, config):
    from benchmarks.selection import load_selection
    from projectctl.config import InputError

    if args.get("smoke") and (args["variants"] != ["B0"] or args["faults"] != ["none"]):
        raise InputError("P9 setup smoke requires B0 and no fault; never labelled performance")
    if args["action"] == "benchmark matrix":
        matrix = load_matrix(args["matrix"], config)
        if matrix.repetitions != 3:
            raise InputError("P9 performance matrix requires three retained repetitions")
        try:
            selection = load_selection(args.get("selection"), config)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            raise InputError(
                "invalid or unsupported measured selection; retain evidence and review"
            ) from exc
        trials, pending = plan_matrix(config, matrix, selection)
    else:
        repetitions = args["repetitions"] or config.timing.repetitions
        config.timing.repetitions = repetitions
        trials = plan_trials(
            config, args["workload"], args["variants"], repetitions, args["faults"]
        )
        pending = []
    root = repo_path(config.artifacts.root)
    root.mkdir(parents=True, exist_ok=True)
    plan_path = root / ("plan-" + str(uuid4()) + ".json")
    write_json(
        plan_path,
        {
            "schema_version": 1,
            "order_seed": config.generator.seed,
            "trials": [trial.order for trial in trials],
            "pending": pending,
        },
    )

    async def execute():
        from projectctl.cli import preflight

        def capacity_failure(trial, assessment):
            from projectctl.artifacts import save_evidence
            from projectctl.models import ExitCode
            from projectctl.providers import Invocation, ProviderResult

            invocation = Invocation(
                "benchmark matrix", args, trial.config, str(uuid4()), "bench-" + str(uuid4())
            )
            return save_evidence(
                invocation,
                ProviderResult(
                    ExitCode.TARGET_MISSED
                    if assessment.get("status") == "MEASURED"
                    else ExitCode.DEPENDENCY_FAILURE,
                    tuple(assessment.get("reasons", ["capacity evidence incomplete"])),
                    "real",
                ),
            )

        outputs = []
        blocked_tiers = set()
        tier_results = {}
        capacity_results = []
        for trial in trials:
            blocking = [registry.binding_failure] if registry.binding_failure else []
            stress = trial.order.get("stress_tier")
            if stress and stress > 500 and blocked_tiers:
                blocking.append("previous stress tier failed/incomplete; escalation NOT_RUN")
            bindings = registry.workload(trial.workload)
            from benchmarks.performance import review_blockers

            qualified = (
                args["action"] == "benchmark matrix"
                or len(args.get("variants", [])) > 1
                or trial.variant not in {"B0", "I0"}
            )
            readiness = args.get("readiness") or (
                bindings.performance_review_path if bindings else None
            )
            blocking.extend(
                review_blockers(
                    trial.config,
                    readiness,
                    qualified=qualified,
                    require_smoke=not args.get("smoke"),
                )
            )
            existing = None
            # A blocked configuration can never reuse a measured result.
            # Check once before scanning history rather than hashing the source
            # again for every old run directory in each draft trial.
            if (
                args["action"] == "benchmark matrix"
                and not blocking
                and not preflight(trial.config, trial.workload)
            ):
                existing = next(
                    (
                        path
                        for path in root.iterdir()
                        if path.is_dir() and reusable_run(path, trial)
                    ),
                    None,
                )
            if existing:
                output = json.loads((existing / "summary.json").read_text(encoding="utf-8"))
                output["evidence_dir"] = str(existing.relative_to(repo_path("."))).replace(
                    "\\", "/"
                )
            else:
                manifest = await run_experiment(
                    trial.workload,
                    trial.variant,
                    trial.repetition,
                    config.generator.seed,
                    config=trial.config,
                    fault_profile=trial.fault,
                    bindings=bindings,
                    order=trial.order,
                    evidence_kind="smoke" if args.get("smoke") else "performance",
                    duration_seconds=5 if args.get("smoke") else None,
                    warmup_seconds=0 if args.get("smoke") else None,
                    review_path=readiness,
                    qualified=qualified,
                    blocking_reasons=blocking,
                )
                directory = root / manifest["run_id"]
                output = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
                output["evidence_dir"] = str(directory.relative_to(repo_path("."))).replace(
                    "\\", "/"
                )
            outputs.append(output)
            if stress and output["exit_code"] != 0:
                blocked_tiers.add(stress)
            if stress and output["exit_code"] == 0:
                from benchmarks.capacity import assess_run, qualify_tier

                try:
                    assessment = assess_run(repo_path(output["evidence_dir"]), stress)
                    group = tier_results.setdefault((stress, trial.variant), [])
                    group.append(assessment)
                    if not assessment["capacity_valid"]:
                        blocked_tiers.add(stress)
                        outputs.append(capacity_failure(trial, assessment))
                    if len(group) == 3:
                        capacity_results.append(
                            qualify_tier(group)
                            | {"variant": trial.variant, "label": trial.order.get("label")}
                        )
                except (OSError, ValueError, KeyError, TypeError, RuntimeError):
                    blocked_tiers.add(stress)
                    outputs.append(capacity_failure(trial, {"status": "INCOMPLETE"}))
                    capacity_results.append(
                        {
                            "rate": stress,
                            "variant": trial.variant,
                            "status": "INCOMPLETE",
                            "reason": "capacity evidence invalid",
                        }
                    )
        if pending:
            # Preserve unresolved measured-selection rows as explicit dependency evidence.
            from projectctl.artifacts import save_evidence
            from projectctl.models import ExitCode
            from projectctl.providers import Invocation, ProviderResult

            invocation = Invocation(
                "benchmark matrix", args, config, str(uuid4()), "bench-" + str(uuid4())
            )
            outputs.append(
                save_evidence(
                    invocation,
                    ProviderResult(
                        ExitCode.DEPENDENCY_FAILURE,
                        tuple(item["reason"] for item in pending),
                        "offline",
                    ),
                )
            )
        write_json(
            root / (plan_path.stem + "-capacity.json"),
            {
                "tiers": capacity_results,
                "blocked_tiers": sorted(blocked_tiers),
                "maximum_sustainable_rate": max(
                    (r["rate"] for r in capacity_results if r.get("sustainable_with_slo")),
                    default=None,
                ),
                "status": "MEASURED" if capacity_results and not blocked_tiers else "INCOMPLETE",
            },
        )
        return outputs

    outputs = asyncio.run(execute())
    write_json(
        root / (plan_path.stem + "-results.json"),
        {
            "plan": plan_path.name,
            "runs": [
                {
                    "run_id": r["run_id"],
                    "evidence_dir": r["evidence_dir"],
                    "exit_code": r["exit_code"],
                }
                for r in outputs
            ],
            "pending": pending,
        },
    )
    return outputs
