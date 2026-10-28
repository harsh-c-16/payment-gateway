"""Repeat the P3 offline checkpoint while retaining every command outcome."""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
CHECK_PATHS = [
    "projectctl",
    "benchmarks/metrics.py",
    "benchmarks/dataset_checks.py",
    "benchmarks/quality.py",
    "benchmarks/reconciliation.py",
    "benchmarks/fixtures.py",
    "benchmarks/manual",
    "services/conversation",
    "shared/contracts",
    "tests/projectctl",
    "tests/contracts",
    "tests/oracles",
    "tests/benchmarks",
]


def main():
    evidence = ROOT / "artifacts/p3" / str(uuid4())
    evidence.mkdir(parents=True, exist_ok=False)
    python = sys.executable
    commands = [
        (
            [
                python,
                "-c",
                "import sys; print(sys.version); "
                "raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 2)",
            ],
            0,
        ),
        ([python, "-m", "ruff", "check", *CHECK_PATHS], 0),
        ([python, "-m", "ruff", "format", "--check", *CHECK_PATHS], 0),
        ([python, "-m", "projectctl.schemas", "--check"], 0),
        ([python, "-m", "projectctl.conversation_contract", "--check"], 0),
        (
            [
                python,
                "-m",
                "pytest",
                "tests/projectctl",
                "tests/contracts",
                "tests/oracles",
                "tests/benchmarks",
                "-q",
                "--tb=short",
                "-W",
                "error::pytest.PytestCacheWarning",
                f"--junitxml={evidence.relative_to(ROOT).as_posix()}/pytest.xml",
            ],
            0,
        ),
        ([python, "-m", "tests.oracles.probe", "--out", str(evidence)], 0),
        (
            [
                python,
                "-m",
                "projectctl",
                "fixtures",
                "build",
                "--config",
                "configs/evaluation.yaml",
                "--seed",
                "42",
            ],
            0,
        ),
        ([python, "-m", "projectctl", "contracts", "check", "--all"], 4),
        (["git", "diff", "--check"], 0),
    ]
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    checks = []
    for command, expected in commands:
        try:
            result = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=environment,
                timeout=120,
            )
            actual, stdout, stderr = result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired as error:

            def decode(value):
                return (
                    value.decode("utf-8", errors="replace")
                    if isinstance(value, bytes)
                    else (value or "")
                )

            actual, stdout, stderr = (
                None,
                decode(error.stdout),
                decode(error.stderr) + "\ncommand exceeded 120 seconds",
            )
        except OSError as error:
            actual, stdout, stderr = None, "", str(error)
        checks.append(
            {
                "command": command,
                "expected_exit": expected,
                "actual_exit": actual,
                "passed": actual == expected,
                "stdout": stdout,
                "stderr": stderr,
                "completed_at": datetime.now(UTC).isoformat(),
                "cwd": str(ROOT),
            }
        )
        staged = evidence / "checks.json.tmp"
        staged.write_text(json.dumps(checks, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        staged.replace(evidence / "checks.json")
    passed = all(check["passed"] for check in checks)
    print(
        json.dumps(
            {
                "evidence_dir": evidence.relative_to(ROOT).as_posix(),
                "checks": len(checks),
                "expected_outcomes_matched": sum(check["passed"] for check in checks),
                "checkpoint": "offline/stub verified" if passed else "failed",
                "G0": "INCOMPLETE",
                "real_integration": "NOT_RUN",
                "human_label_review": "PENDING",
            }
        )
    )
    return 0 if passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
