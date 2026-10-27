"""Repeat P5 acceptance and retain exact commands, outputs and exit statuses."""

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
    parser.add_argument(
        "--review-p1-p5",
        action="store_true",
        help="verify a P1-P5 review, allowing Jaineel's conversation client edits",
    )
    args = parser.parse_args()
    evidence = (
        ROOT / ("artifacts/p1-p5-review" if args.review_p1_p5 else "artifacts/p5") / str(uuid4())
    )
    evidence.mkdir(parents=True, exist_ok=False)
    relative = evidence.relative_to(ROOT).as_posix()
    python = sys.executable
    paths = [
        "benchmarks",
        "projectctl",
        "services/conversation",
        "shared/contracts",
        "shared/telemetry",
        "dashboards",
        "tests/projectctl",
        "tests/contracts",
        "tests/oracles",
        "tests/benchmarks",
        "tests/telemetry",
    ]
    commands = [
        (
            [
                python,
                "-c",
                "import sys; print(sys.version); "
                "raise SystemExit(0 if sys.version_info[:2] == (3,11) else 2)",
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
                "tests/telemetry",
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
        ([python, "-m", "benchmarks.manual.observer_stall", "--out", f"{relative}/demo"], 0),
        (
            [
                python,
                "-m",
                "benchmarks.observation_summary",
                "--run-dir",
                f"{relative}/demo/stub-stall",
                "--out",
                f"{relative}/rebuilt",
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
                "services",
                "infra",
                "pipelines",
                "migrations",
                "shared/outbox",
                "shared/event_transport",
                *([":(exclude)services/conversation"] if args.review_p1_p5 else []),
            ],
            0,
        ),
    ]
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    checks = []
    for command, expected in commands:
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=environment,
                timeout=240,
            )
            actual, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
        except subprocess.TimeoutExpired as exc:
            actual = None
            stdout = (exc.stdout or b"").decode("utf-8", errors="replace")
            stderr = "command exceeded 240 seconds; partial output retained"
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
                "expected_outcomes_matched": sum(c["passed"] for c in checks),
                "real_SUT": "NOT_RUN",
                "grafana_import": "NOT_RUN",
                "performance_matrix": "NOT_RUN",
            }
        )
    )
    return 0 if all(c["passed"] for c in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
