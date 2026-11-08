"""Read-only Prompt 4 readiness checkpoint; never starts a partial live fixture.

python -m benchmarks.manual.verify_prompt4 --out artifacts/jaineel/prompt4-NEW
Reviewed owners can later supply QualityOwners to run_g1/build_quality_bindings.
This command records dependencies only and returns 4 until those bindings exist.
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys

from benchmarks.quality_binding import build_quality_bindings
from benchmarks.quality_trial import run_g1
from projectctl.artifacts import write_json
from projectctl.cli import preflight
from projectctl.config import load_config, repo_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    directory = repo_path(args.out)
    directory.mkdir(parents=True, exist_ok=False)
    config = load_config()
    binding = build_quality_bindings(config)
    reasons = [*preflight(config, "W-QUALITY"), *binding.dependency_reasons]
    probes = {}
    commands = {
        "docker": ["docker", "ps", "-a", "--format", "{{.Names}} {{.Status}}"],
        "lock": ["uv", "sync", "--locked", "--check"],
    }
    for name, command in commands.items():
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="replace",
            )
            (directory / (name + ".stdout.log")).write_text(result.stdout, encoding="utf-8")
            (directory / (name + ".stderr.log")).write_text(result.stderr, encoding="utf-8")
            probes[name] = {"argv": command, "exit_code": result.returncode}
        except (OSError, subprocess.TimeoutExpired) as error:
            probes[name] = {"argv": command, "exit_code": None, "error_type": type(error).__name__}
    cache = os.environ.get("EVENT_SCHEMA_CACHE_PATH")
    readiness = {
        "status": "INCOMPLETE",
        "reasons": reasons,
        "probes": probes,
        "schema_cache_configured": cache is not None,
        "schema_cache_exists": bool(cache and repo_path(cache).is_file()),
        "schema_registry_live_check": "NOT_RUN; no approved full setup",
        "postgres_kafka_trial": "NOT_RUN",
        "T-03": "NOT_RUN",
        "G1": "NOT_RUN",
        "performance": "NOT_RUN",
        "correctness_passed": None,
        "setup_handoff": (
            "review seed/projection evidence without contaminating quality analytics; "
            "seed STOCK_UPDATED v1 and quality v1 for the same SKU otherwise conflict"
        ),
    }
    write_json(directory / "readiness.json", readiness)
    g1 = asyncio.run(run_g1(config, directory / "g1"))
    result = {
        "exit_code": 4,
        "status": "INCOMPLETE",
        "reasons": reasons,
        "G1": g1["status"],
        "T-03": "NOT_RUN",
        "performance": "NOT_RUN",
        "evidence_dir": args.out,
        "python": sys.executable,
    }
    write_json(directory / "summary.json", result)
    print(json.dumps(result))
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
