"""Repeat P4 acceptance; preserve exact commands, outputs, exits and failures."""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]


def main():
    evidence = ROOT / "artifacts/p4" / str(uuid4())
    evidence.mkdir(parents=True, exist_ok=False)
    relative = evidence.relative_to(ROOT).as_posix()
    python = sys.executable
    paths = [
        "benchmarks",
        "projectctl",
        "services/conversation",
        "shared/contracts",
        "tests/projectctl",
        "tests/contracts",
        "tests/oracles",
        "tests/benchmarks",
    ]
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
        ([python, "-m", "ruff", "check", *paths], 0),
        ([python, "-m", "ruff", "format", "--check", *paths], 0),
        ([python, "-m", "projectctl.schemas", "--check"], 0),
        ([python, "-m", "projectctl.conversation_contract", "--check"], 0),
        (
            [
                python,
                "-m",
                "pytest",
                "tests/benchmarks",
                "tests/projectctl",
                "tests/contracts",
                "tests/oracles",
                "-q",
                "--tb=short",
                "-W",
                "error::pytest.PytestCacheWarning",
                f"--junitxml={relative}/pytest.xml",
            ],
            0,
        ),
        ([python, "-m", "benchmarks.manual.slow_publisher", "--out", f"{relative}/slow"], 0),
        (
            [
                python,
                "-m",
                "projectctl",
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
                "shared",
                "services",
                "infra",
                "pipelines",
                "migrations",
            ],
            0,
        ),
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
                timeout=180,
            )
            actual, stdout, stderr = result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired as exc:
            actual = None
            stdout = (exc.stdout or b"").decode("utf-8", errors="replace")
            stderr = "command exceeded 180 seconds; raw partial output retained"
        except OSError as exc:
            actual, stdout, stderr = None, "", str(exc)
        checks.append(
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
        temporary = evidence / "checks.json.tmp"
        temporary.write_text(json.dumps(checks, indent=2) + "\n", encoding="utf-8")
        temporary.replace(evidence / "checks.json")
        print(json.dumps({"check": len(checks), "passed": checks[-1]["passed"]}), flush=True)
    print(
        json.dumps(
            {
                "evidence_dir": relative,
                "checks": len(checks),
                "expected_outcomes_matched": sum(check["passed"] for check in checks),
                "real_G1": "NOT_RUN",
                "performance_matrix": "NOT_RUN",
            }
        )
    )
    return 0 if all(check["passed"] for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
