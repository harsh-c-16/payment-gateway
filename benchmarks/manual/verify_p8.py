"""Reproducible P8 checkpoint. Missing real providers return 4, never a green stub gate."""

import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from benchmarks.dataset_checks import inspect_source
from benchmarks.manual.verify_p7 import docker_database
from projectctl.artifacts import file_hash, write_json
from projectctl.contract_checks import inspect_contracts

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--database-file",
        type=Path,
        help="ignored local JSON containing url of an isolated Docker test database",
    )
    args = parser.parse_args()
    destination = args.out.resolve()
    if not destination.is_relative_to(ROOT / "artifacts"):
        parser.error("--out must be a new directory within artifacts/")
    destination.mkdir(parents=True, exist_ok=False)
    environment = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "ASSISTANT_MODE": "fixed",
        "ALLOW_INTENT_LLM": "false",
    }
    if args.database_file:
        url = json.loads(args.database_file.read_text(encoding="utf-8"))["url"]
        write_json(destination / "database.json", docker_database(url))
        environment["P6_TEST_DATABASE_URL"] = url
    checks = []

    def run(label, arguments):
        command = [sys.executable, *arguments]
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        (destination / (label + ".stdout.txt")).write_text(completed.stdout, encoding="utf-8")
        (destination / (label + ".stderr.txt")).write_text(completed.stderr, encoding="utf-8")
        row = {
            "label": label,
            "command": command,
            "exit_code": completed.returncode,
            "status": "PASS"
            if completed.returncode == 0
            else "INCOMPLETE"
            if completed.returncode == 4
            else "FAIL",
            "stdout": label + ".stdout.txt",
            "stderr": label + ".stderr.txt",
        }
        try:
            row["output"] = json.loads(completed.stdout)
        except ValueError:
            pass
        checks.append(row)
        write_json(destination / (label + ".command.json"), row)
        print(f"{label}: exit {completed.returncode}", flush=True)
        return row

    write_json(destination / "handoffs.json", {"checks": inspect_contracts(ROOT)})
    write_json(
        destination / "dataset_checks.json",
        inspect_source(ROOT / "data/raw/flipkart_com-ecommerce_sample.csv"),
    )
    owned = [
        "benchmarks/integration.py",
        "benchmarks/integration_cases.py",
        "benchmarks/integration_clients.py",
        "benchmarks/integration_faults.py",
        "benchmarks/reconciliation.py",
        "benchmarks/manual/verify_p8.py",
        "projectctl/cli.py",
        "projectctl/providers.py",
        "tests/integration",
    ]
    run("lint", ["-m", "ruff", "check", *owned])
    run("format", ["-m", "ruff", "format", "--check", *owned])
    run("schemas", ["-m", "projectctl.schemas", "--check"])
    run("conversation-contract", ["-m", "projectctl.conversation_contract", "--check"])
    run(
        "pytest",
        [
            "-m",
            "pytest",
            "tests/conversation",
            "tests/projectctl",
            "tests/contracts",
            "tests/oracles",
            "tests/benchmarks",
            "tests/telemetry",
            "tests/integration",
            "-q",
            "--tb=short",
            "-o",
            "junit_family=xunit1",
            "-o",
            f"cache_dir={destination / 'cache'}",
            f"--basetemp={destination / 'tmp'}",
            f"--junitxml={destination / 'pytest.xml'}",
        ],
    )
    # Runbook §2 order. A failed prerequisite leaves dependent setup explicitly NOT_RUN.
    setup = [
        ["env", "up", "--profile", "local4c8g"],
        ["env", "verify", "--profile", "local4c8g"],
        ["db", "migrate", "--namespace", "bench-smoke"],
        ["contracts", "check", "--all"],
        [
            "catalog",
            "profile",
            "--source",
            "data/raw/flipkart_com-ecommerce_sample.csv",
            "--rules",
            "flipkart-v1",
            "--out",
            "artifacts/catalog/profile",
        ],
        [
            "catalog",
            "import",
            "--source",
            "data/raw/flipkart_com-ecommerce_sample.csv",
            "--rules",
            "flipkart-v1",
            "--load-mode",
            "row",
            "--namespace",
            "bench-smoke",
            "--out",
            "artifacts/catalog/bench-smoke",
        ],
        [
            "catalog",
            "verify",
            "--manifest",
            "artifacts/catalog/bench-smoke/normalized_manifest.json",
            "--namespace",
            "bench-smoke",
        ],
        [
            "inventory",
            "seed",
            "--sku-manifest",
            "artifacts/catalog/bench-smoke/sku_manifest.json",
            "--namespace",
            "bench-smoke",
            "--profile",
            "performance",
            "--seed",
            "42",
        ],
        [
            "projection",
            "wait",
            "--namespace",
            "bench-smoke",
            "--sku-manifest",
            "artifacts/catalog/bench-smoke/sku_manifest.json",
            "--timeout-seconds",
            "120",
        ],
        ["fixtures", "build", "--config", "configs/evaluation.yaml", "--seed", "42"],
        ["eval", "run", "--suite", "contracts,data,smoke", "--config", "configs/evaluation.yaml"],
    ]
    prerequisite = True
    for index, arguments in enumerate(setup):
        if prerequisite:
            row = run(f"setup-{index:02}", ["-m", "projectctl", *arguments])
            prerequisite = row["exit_code"] == 0
        else:
            checks.append(
                {
                    "label": f"setup-{index:02}",
                    "command": [sys.executable, "-m", "projectctl", *arguments],
                    "status": "NOT_RUN",
                    "exit_code": None,
                    "reason": "setup prerequisite unavailable; dependent steps not attempted",
                }
            )
    run("contracts", ["-m", "projectctl", "contracts", "check", "--all"])
    for label, suite in (
        ("smoke", "contracts,data,smoke"),
        ("correctness", "correctness"),
        ("assistant", "T-10,D-05"),
        ("outages", "T-11"),
    ):
        run(
            label,
            [
                "-m",
                "projectctl",
                "eval",
                "run",
                "--suite",
                suite,
                "--config",
                "configs/evaluation.yaml",
            ],
        )
    smoke = next(row for row in checks if row["label"] == "smoke")
    if "output" in smoke:
        run(
            "reconcile",
            [
                "-m",
                "projectctl",
                "benchmark",
                "reconcile",
                "--run-dir",
                smoke["output"]["evidence_dir"],
            ],
        )
    junit = ET.parse(destination / "pytest.xml").getroot()
    tests = list(junit.iter("testcase"))
    counts = {
        "tests": len(tests),
        "failures": sum(test.find("failure") is not None for test in tests),
        "errors": sum(test.find("error") is not None for test in tests),
        "skipped": sum(test.find("skipped") is not None for test in tests),
    }
    harness_ok = all(row["exit_code"] == 0 for row in checks[:5]) and not counts["skipped"]
    real_ok = prerequisite and all(
        row["exit_code"] == 0
        for row in checks
        if row["label"]
        in {"contracts", "smoke", "correctness", "assistant", "outages", "reconcile"}
    )
    write_json(destination / "checks.json", {"checks": checks})
    write_json(
        destination / "evidence_index.json",
        {
            "artifacts": [
                {"path": path.relative_to(destination).as_posix(), "sha256": file_hash(path)}
                for path in sorted(destination.iterdir())
                if path.is_file()
            ]
        },
    )
    summary = {
        "harness_checks_passed": harness_ok,
        "pytest": counts,
        "real_P8_status": "PASS" if real_ok else "INCOMPLETE",
        "G4_complete": False,
        "test_mode": "M1 PostgreSQL; explicit provider/event/audit/hook doubles in unit tests",
        "performance_results": None,
        "next_milestone_started": False,
    }
    write_json(destination / "summary.json", summary)
    print(json.dumps(summary), flush=True)
    return 3 if not harness_ok else 0 if real_ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
