"""P4 CLI orchestration. Empty production registry fails visibly, without doubles."""

import asyncio
import json
from uuid import uuid4

from benchmarks.experiment import run_experiment
from benchmarks.planning import plan_matrix, plan_trials, reusable_run
from projectctl.artifacts import write_json
from projectctl.config import load_matrix, repo_path


def execute_benchmarks(args, registry, config):
    if args["action"] == "benchmark matrix":
        matrix = load_matrix(args["matrix"], config)
        trials, pending = plan_matrix(config, matrix)
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
        outputs = []
        for trial in trials:
            existing = None
            if args["action"] == "benchmark matrix":
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
                    bindings=registry.workload(trial.workload),
                    order=trial.order,
                )
                directory = root / manifest["run_id"]
                output = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
                output["evidence_dir"] = str(directory.relative_to(repo_path("."))).replace(
                    "\\", "/"
                )
            outputs.append(output)
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
