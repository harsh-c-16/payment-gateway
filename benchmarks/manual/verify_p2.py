"""Collect P2 offline/stub evidence. Expected missing contracts remain incomplete."""

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
    "services/conversation",
    "shared/contracts",
    "tests/contracts",
    "tests/projectctl",
    "benchmarks/manual/verify_p1.py",
    "benchmarks/manual/verify_p2.py",
]


def main():
    evidence = ROOT / "artifacts/p2" / str(uuid4())
    evidence.mkdir(parents=True, exist_ok=False)
    python = sys.executable
    checks = [
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
                "tests/contracts",
                "tests/projectctl",
                "-q",
                "--tb=short",
                "-W",
                "error::pytest.PytestCacheWarning",
                f"--junitxml={evidence.relative_to(ROOT).as_posix()}/pytest.xml",
            ],
            0,
        ),
        ([python, "-m", "tests.contracts.probe", "--out", str(evidence)], 0),
        ([python, "-m", "projectctl", "contracts", "check", "--all"], 4),
        (["git", "diff", "--check"], 0),
    ]
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    records = []
    for command, expected in checks:
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=environment,
                timeout=120,
            )
            actual, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
        except subprocess.TimeoutExpired as error:

            def decoded(value):
                return (
                    value.decode("utf-8", errors="replace")
                    if isinstance(value, bytes)
                    else (value or "")
                )

            actual, stdout = None, decoded(error.stdout)
            stderr = decoded(error.stderr) + "\ncheckpoint command exceeded 120 seconds"
        except OSError as error:
            actual, stdout, stderr = None, "", str(error)
        records.append(
            {
                "command": command,
                "cwd": str(ROOT),
                "expected_exit": expected,
                "actual_exit": actual,
                "passed": actual == expected,
                "stdout": stdout,
                "stderr": stderr,
                "completed_at": datetime.now(UTC).isoformat(),
            }
        )
        # Persist after every command, retaining earlier evidence if a later check fails.
        staged = evidence / "checks.json.tmp"
        staged.write_text(
            json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        staged.replace(evidence / "checks.json")
    passed = all(record["passed"] for record in records)
    print(
        json.dumps(
            {
                "evidence_dir": evidence.relative_to(ROOT).as_posix(),
                "checks": len(records),
                "expected_outcomes_matched": sum(record["passed"] for record in records),
                "checkpoint": "stub verified" if passed else "failed",
                "G0": "INCOMPLETE",
                "real_integration": "NOT_RUN",
            }
        )
    )
    return 0 if passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
