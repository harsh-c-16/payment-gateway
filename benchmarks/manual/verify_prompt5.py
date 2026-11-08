"""Read-only G3 checkpoint. Missing owner review blocks all real transaction writes."""

import argparse
import json
import subprocess

from benchmarks.g3 import dependencies
from benchmarks.integration_cases import BY_ID
from projectctl.artifacts import write_json
from projectctl.cli import preflight
from projectctl.config import load_config, repo_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    directory = repo_path(args.out)
    directory.mkdir(parents=True, exist_ok=False)
    reasons = [*preflight(load_config()), *dependencies()]
    probes = {}
    for name, argv in {
        "docker": ["docker", "ps", "-a", "--format", "{{.Names}} {{.Status}}"],
        "lock": ["uv", "sync", "--locked", "--check"],
    }.items():
        try:
            result = subprocess.run(
                argv, capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace"
            )
            for stream in ("stdout", "stderr"):
                (directory / f"{name}.{stream}.log").write_text(
                    getattr(result, stream), encoding="utf-8"
                )
            probes[name] = {"argv": argv, "exit_code": result.returncode}
        except (OSError, subprocess.TimeoutExpired) as error:
            probes[name] = {"argv": argv, "exit_code": None, "error_type": type(error).__name__}
    result = {
        "status": "INCOMPLETE",
        "exit_code": 4,
        "correctness_passed": None,
        "G3": {
            key: {"status": "NOT_RUN", "owner": BY_ID[key].owner, "reasons": reasons}
            for key in ("smoke/G3-success", "smoke/G3-decline")
        },
        "probes": probes,
        "performance": "NOT_RUN",
        "real_writes_attempted": False,
        "compaction": {
            "status": "NOT_RUN",
            "owner_boundary": "after_candidate_files_before_publish",
            "owner_target": "compaction",
            "mapped_case": None,
            "existing_stale_case": {
                "barrier": BY_ID["T-12/stale-compaction"].barrier,
                "target": BY_ID["T-12/stale-compaction"].target,
            },
            "review_required": ["Jaineel", "Harsh", "Vichitr"],
            "proposed_recovery_facts": [
                "killed candidate absent from active membership",
                "active generation unchanged by killed attempt",
                "retained files/volume verified",
                "replacement candidate preserves row digest, count and currency totals",
                "one successor generation published from unchanged pinned base",
            ],
        },
        "quote_expiry_regression": {
            "status": "NOT_RUN",
            "owner": "Aditya",
            "contracts": ["02_COMMON_SPEC.md §§3,5,8 and Appendix A"],
            "requirements": [
                "accepted quote resolves to same order after expiry for old/new key",
                "new expired quote returns 409 QUOTE_EXPIRED",
                "same key changed business input returns 409 IDEMPOTENCY_CONFLICT",
            ],
        },
    }
    write_json(directory / "readiness.json", result)
    print(
        json.dumps({"exit_code": 4, "G3": "NOT_RUN", "evidence_dir": args.out, "reasons": reasons})
    )
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
