"""Prompt 3 read-only/setup checkpoint. No workload, seed, reset or performance run.

python -m benchmarks.manual.verify_prompt3 --out artifacts/jaineel/prompt3-NEW
Retain dependency exit 4 until owner lifecycle and pin-policy handoffs are complete.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from benchmarks.dataset_checks import inspect_source
from projectctl.artifacts import write_json
from projectctl.config import load_config, repo_path
from projectctl.input_pins import review_input_pins
from projectctl.providers import default_registry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = repo_path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    environment = {**os.environ, "PROJECTCTL_ADAPTER_MODULE": "projectctl.jaineel"}
    os.environ["PROJECTCTL_ADAPTER_MODULE"] = "projectctl.jaineel"
    registry = default_registry()
    config = load_config()
    write_json(out / "registrations.json", registry.availability())
    write_json(out / "hash-review.json", review_input_pins())
    write_json(out / "source-checks.json", inspect_source(repo_path(config.dataset.source_path)))
    from projectctl.cli import preflight

    missing = {}
    for workload in ("W-IMPORT", "W-SEARCH", "W-ANALYTICS"):
        binding = registry.workload(workload, config)
        missing[workload] = list(binding.dependency_reasons)
    write_json(
        out / "readiness.json",
        {
            "status": "INCOMPLETE",
            "performance": "NOT_RUN",
            "preflight": preflight(config),
            "owner_callbacks": missing,
            "global_db_migrate": "owner registers analytics only; other services NOT_RUN",
            "env_reset": registry.missing("env reset"),
            "source_import_seed_projection": "NOT_RUN; fresh namespace callback unavailable",
        },
    )
    commands = {
        "help": ["-m", "projectctl", "--help"],
        "schemas": ["-m", "projectctl.schemas", "--check"],
        "contracts": ["-m", "projectctl", "contracts", "check", "--all"],
        "catalog-profile": [
            "-m",
            "projectctl",
            "catalog",
            "profile",
            "--source",
            config.dataset.source_path,
            "--rules",
            "flipkart-v1",
            "--out",
            (Path(args.out) / "profile").as_posix(),
        ],
        # A missing action must leave structured dependency evidence without touching Docker.
        "missing-reset": ["-m", "projectctl", "env", "reset", "--namespace", "bench-prompt3"],
    }
    outcomes = {}
    for label, command in commands.items():
        argv = [sys.executable, *command]
        result = subprocess.run(
            argv,
            cwd=repo_path("."),
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        (out / (label + ".stdout.log")).write_text(result.stdout, encoding="utf-8")
        (out / (label + ".stderr.log")).write_text(result.stderr, encoding="utf-8")
        outcomes[label] = result.returncode
        write_json(out / (label + ".command.json"), {"argv": argv, "exit_code": result.returncode})
    write_json(
        out / "summary.json",
        {
            "exit_code": 4,
            "status": "INCOMPLETE",
            "commands": outcomes,
            "performance": "NOT_RUN",
            "real_workload": "NOT_RUN",
            "scope": "actual registrations, source/profile, contracts and dependency evidence",
        },
    )
    print(json.dumps({"exit_code": 4, "evidence_dir": args.out, "commands": outcomes}))
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
