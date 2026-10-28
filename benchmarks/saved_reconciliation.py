"""Read-only P10 rechecks; use each workload's independent audit, never a reducer."""

from datetime import UTC, datetime

from benchmarks.performance import (
    load_performance_run,
    read_json,
    validate_outputs,
    verified_bundle,
)
from projectctl.artifacts import file_hash, save_evidence, write_json
from projectctl.config import repo_path
from projectctl.models import ExitCode
from projectctl.providers import DependencyError, ProviderResult


def execute_reconciliation(invocation):
    source = repo_path(invocation.arguments["run_dir"])
    manifest = None
    try:
        manifest = verified_bundle(source, {"summary.json"})
        if manifest["command"] == "eval run":
            from benchmarks.integration import execute_reconciliation as recheck_cases

            return recheck_cases(invocation)
        if manifest["command"] not in {"benchmark run", "benchmark matrix"}:
            raise DependencyError("command has no independent reconciliation binding")
        execution = read_json(source / "execution.json")
        if execution.get("test_mode") == "stub":
            # Existing explicitly labelled stub evidence stays a contract check.
            from benchmarks.integration import execute_reconciliation as recheck_cases

            return recheck_cases(invocation)
        run = load_performance_run(source)
        passed, reason = True, "raw admission, workload audit and telemetry independently rebuilt"
        code = ExitCode.COMPLETED
    except (DependencyError, OSError, ValueError, KeyError, TypeError):
        run = None
        passed, reason = False, "saved performance evidence unavailable, incomplete or invalid"
        code = ExitCode.DEPENDENCY_FAILURE
        if manifest and manifest["workload_id"] and manifest["started_at"]:
            verdict = validate_outputs(
                source,
                {
                    "workload_id": manifest["workload_id"],
                    "namespace": manifest["namespace"],
                    "run_id": manifest["run_id"],
                    "fault_profile": manifest["fault_profiles"][0],
                },
            )
            if verdict["correctness_failed"]:
                code = ExitCode.CORRECTNESS_FAILURE
                reason = "saved workload audit independently failed correctness"
    directory = repo_path("artifacts/projectctl") / invocation.run_id
    directory.mkdir(parents=True, exist_ok=False)
    write_json(
        directory / "correctness.json",
        {
            "passed": passed,
            "reason": reason,
            "source": {
                "path": invocation.arguments["run_dir"] + "/manifest.json",
                "sha256": file_hash(source / "manifest.json")
                if (source / "manifest.json").is_file()
                else None,
            },
            "workload": run["manifest"]["workload_id"] if run else None,
        },
    )
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return save_evidence(
        invocation,
        ProviderResult(code, (reason,), "offline"),
        execution={
            "status": "MEASURED" if passed else "INCOMPLETE",
            "started_at": now,
            "completed_at": now,
            "correctness_passed": passed,
            "metrics": [],
        },
    )
