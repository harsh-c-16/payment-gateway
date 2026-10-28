"""Run the P1 checkpoint and retain exact command/output/exit evidence. No services start."""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]


def main():
    evidence = ROOT / "artifacts" / "p1" / str(uuid4())
    evidence.mkdir(parents=True, exist_ok=False)
    python = sys.executable
    checks = [
        ([python, "--version"], 0),
        (
            [
                python,
                "-m",
                "ruff",
                "check",
                "projectctl",
                "tests/projectctl",
                "benchmarks/manual/verify_p1.py",
            ],
            0,
        ),
        (
            [
                python,
                "-m",
                "ruff",
                "format",
                "--check",
                "projectctl",
                "tests/projectctl",
                "benchmarks/manual/verify_p1.py",
            ],
            0,
        ),
        ([python, "-m", "projectctl.schemas", "--check"], 0),
        (
            [
                python,
                "-m",
                "pytest",
                "tests/projectctl",
                "-q",
                f"--junitxml={evidence.relative_to(ROOT).as_posix()}/pytest.xml",
            ],
            0,
        ),
    ]
    cli = [python, "-m", "projectctl"]
    checks.extend(
        (cli + args, expected)
        for args, expected in [
            (["--help"], 0),
            (["eval", "run", "--help"], 0),
            (["benchmark", "run", "--help"], 0),
            (["env", "verify", "--profile", "local4c8g"], 4),
            (["env", "verify", "--profile", "local4c8g", "--unknown"], 2),
            (["env", "reset", "--namespace", "live"], 2),
            (["contracts", "check", "--all"], 4),
            (
                [
                    "eval",
                    "run",
                    "--suite",
                    "contracts,data,smoke",
                    "--config",
                    "configs/evaluation.yaml",
                ],
                4,
            ),
            (
                [
                    "benchmark",
                    "run",
                    "--workload",
                    "W-PIPE",
                    "--variants",
                    "B0,O1",
                    "--repetitions",
                    "3",
                    "--config",
                    "configs/evaluation.yaml",
                ],
                4,
            ),
            (
                [
                    "benchmark",
                    "run",
                    "--workload",
                    "W-IMPORT",
                    "--variants",
                    "I0,I1",
                    "--repetitions",
                    "1",
                    "--config",
                    "configs/evaluation.yaml",
                ],
                4,
            ),
            (
                [
                    "benchmark",
                    "matrix",
                    "--matrix",
                    "configs/core_matrix.yaml",
                    "--config",
                    "configs/evaluation.yaml",
                ],
                4,
            ),
        ]
    )
    records = []
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    for command, expected in checks:
        completed = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env=environment
        )
        record = {
            "command": command,
            "cwd": str(ROOT),
            "expected_exit": expected,
            "actual_exit": completed.returncode,
            "passed": completed.returncode == expected,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "completed_at": datetime.now(UTC).isoformat(),
        }
        records.append(record)
    output = {
        "test_mode": "offline_with_explicit_test_doubles",
        "evidence_dir": evidence.relative_to(ROOT).as_posix(),
        "checks": records,
        "all_expected_outcomes": all(r["passed"] for r in records),
        "real_integration": "NOT_RUN",
        "performance": "NOT_RUN",
    }
    (evidence / "checks.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: output[key] for key in ("evidence_dir", "all_expected_outcomes")}))
    return 0 if output["all_expected_outcomes"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
