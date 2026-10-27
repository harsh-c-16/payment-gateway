"""Repeat P6 checks; retain commands/results and explicit real/shared dependency limits."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    out = args.out or ROOT / "artifacts/p6" / str(uuid4())
    out.mkdir(parents=True, exist_ok=False)
    python = sys.executable
    paths = [
        "services/conversation",
        "tests/conversation",
        "benchmarks/manual/p6_smoke.py",
        "benchmarks/manual/verify_p6.py",
    ]
    commands = [
        (
            [
                python,
                "-c",
                "import sys; print(sys.version); "
                "raise SystemExit(0 if sys.version_info[:2]==(3,11) else 2)",
            ],
            0,
        ),
        ([python, "-m", "ruff", "check", *paths], 0),
        ([python, "-m", "ruff", "format", "--check", *paths], 0),
        ([python, "-m", "projectctl.schemas", "--check"], 0),
        ([python, "-m", "projectctl.conversation_contract", "--check"], 0),
        (
            [
                python,
                "-m",
                "pytest",
                "tests/conversation",
                "tests/projectctl",
                "tests/contracts",
                "tests/oracles",
                "tests/benchmarks",
                "tests/telemetry",
                "-q",
                "--tb=short",
                f"--basetemp={out / 'test-temp'}",
                "-o",
                f"cache_dir={out / 'pytest-cache'}",
                f"--junitxml={out / 'pytest.xml'}",
            ],
            0,
        ),
        ([python, "-m", "projectctl", "contracts", "check", "--all"], 4),
        (["git", "diff", "--check"], 0),
        (
            [
                "git",
                "diff",
                "--exit-code",
                "--",
                "docs/specs",
                "uv.lock",
                "pyproject.toml",
                "configs",
                "contracts",
                "shared/contracts",
                "shared/outbox",
                "shared/event_transport",
                "infra",
                "pipelines",
                "services",
                ":(exclude)services/conversation",
                "migrations",
                ":(exclude)migrations/conversation",
            ],
            0,
        ),
    ]
    database_configured = bool(os.environ.get("P6_TEST_DATABASE_URL"))
    if database_configured:
        commands.insert(
            6, ([python, "-m", "benchmarks.manual.p6_smoke", "--out", str(out / "smoke")], 0)
        )
    records = []
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    for command, expected in commands:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        record = {
            "command": command,
            "expected_exit": expected,
            "actual_exit": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "matched": completed.returncode == expected,
        }
        records.append(record)
        (out / "checks.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
        print(f"{completed.returncode} (expected {expected}): {' '.join(command)}", flush=True)
    matched = all(record["matched"] for record in records)
    summary = {
        "checkpoint": "P6 only",
        "checks_matched": matched,
        "database": "real PostgreSQL 18" if database_configured else "NOT_RUN",
        "events_outbox": "explicit test doubles; real shared event path NOT_RUN",
        "provider_contracts": "incomplete; expected contracts command exit 4",
        "p7": "NOT_RUN",
        "status": "verified state/checkpoint; shared gate incomplete"
        if matched and database_configured
        else "INCOMPLETE",
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(out)
    return 0 if matched and database_configured else 4


if __name__ == "__main__":
    raise SystemExit(main())
