"""P11 local checks with explicit model/provider doubles; live results always stay NOT_RUN."""

import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

from benchmarks.assistant_evaluation import evaluate_workflows
from benchmarks.manual.verify_p7 import docker_database
from projectctl.artifacts import content_hash, file_hash, write_json
from projectctl.config import ROOT, repo_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--database-file",
        type=Path,
        required=True,
        help="explicit ignored Docker test DB JSON; credentials never logged",
    )
    parser.add_argument("--focused", action="store_true")
    args = parser.parse_args(argv)
    destination = repo_path(args.out)
    if not destination.is_relative_to(ROOT / "artifacts"):
        parser.error("--out must be a new directory inside artifacts/")
    destination.mkdir(parents=True, exist_ok=False)
    environment = {
        k: v
        for k, v in os.environ.items()
        if k not in {"OPENAI_API_KEY", "INTENT_LLM_MODEL", "PROJECTCTL_ADAPTER_MODULE"}
    }
    environment.update(PYTHONIOENCODING="utf-8", ASSISTANT_MODE="fixed", ALLOW_INTENT_LLM="false")
    url = json.loads(args.database_file.read_text(encoding="utf-8"))["url"]
    write_json(destination / "database.json", docker_database(url))
    environment["P6_TEST_DATABASE_URL"] = url
    fixture = ROOT / "contracts/fixtures/assistant/scenarios.json"
    fixture_hash = file_hash(fixture)
    checks = []

    def run(label, arguments):
        command, started = [sys.executable, *arguments], datetime.now(UTC).isoformat()
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        (destination / f"{label}.stdout.txt").write_text(result.stdout, encoding="utf-8")
        (destination / f"{label}.stderr.txt").write_text(result.stderr, encoding="utf-8")
        row = {
            "command": command,
            "exit_code": result.returncode,
            "started_at": started,
            "completed_at": datetime.now(UTC).isoformat(),
        }
        write_json(destination / f"{label}.command.json", row)
        checks.append(row)
        print(f"{label}: exit {result.returncode}", flush=True)
        return result

    paths = [
        "services/conversation",
        "tests/conversation",
        "benchmarks/assistant_evaluation.py",
        "benchmarks/manual/verify_p11.py",
        "tests/benchmarks/test_assistant_evaluation.py",
    ]
    run("lint", ["-m", "ruff", "check", *paths])
    run("format", ["-m", "ruff", "format", "--check", *paths])
    run("schemas", ["-m", "projectctl.schemas", "--check"])
    run("conversation-contract", ["-m", "projectctl.conversation_contract", "--check"])
    suites = (
        ["tests/conversation", "tests/benchmarks/test_assistant_evaluation.py"]
        if args.focused
        else [
            "tests/conversation",
            "tests/projectctl",
            "tests/contracts",
            "tests/oracles",
            "tests/benchmarks",
            "tests/telemetry",
            "tests/integration",
        ]
    )
    run(
        "pytest",
        [
            "-m",
            "pytest",
            *suites,
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
    real = run(
        "real-assistant-cases",
        [
            "-m",
            "projectctl",
            "eval",
            "run",
            "--suite",
            "T-10,D-05",
            "--config",
            "configs/evaluation.yaml",
        ],
    )
    tree = ET.parse(destination / "pytest.xml").getroot()
    cases = list(tree.iter("testcase"))
    counts = {
        "tests": len(cases),
        "failures": sum(c.find("failure") is not None for c in cases),
        "errors": sum(c.find("error") is not None for c in cases),
        "skipped": sum(c.find("skipped") is not None for c in cases),
    }
    traces = {"fixed": {}, "assist": {}}
    for case in cases:
        for prop in case.findall("properties/property"):
            if prop.get("name") == "assistant_turn":
                row = json.loads(prop.get("value"))
                key = row["scenario_id"]
                if key in traces[row["mode"]]:
                    raise ValueError("duplicate scenario trace")
                traces[row["mode"]][key] = row

    class SavedAdapter:
        backend_identity = "M1 PostgreSQL18 / identical explicit synthetic catalogue-orders-v2"
        test_mode = "stub"

        def __init__(self, mode):
            self.mode = mode

        def __call__(self, scenario):
            return traces[self.mode][scenario["scenario_id"]]

    document = json.loads(fixture.read_text(encoding="utf-8"))
    comparison = None
    if all(len(traces[m]) == 60 for m in traces):
        comparison = evaluate_workflows(
            document["scenarios"], SavedAdapter("fixed"), SavedAdapter("assist")
        )
        comparison["fixture_sha256"] = fixture_hash
        comparison["fixture_frozen_for_test_reproduction"] = True
        comparison["human_label_freeze"] = "NOT_RUN"
        write_json(destination / "assistant_comparison.json", comparison)
    harness_ok = (
        all(c["exit_code"] == 0 for c in checks[:-1])
        and not any(counts[k] for k in ("failures", "errors", "skipped"))
        and comparison is not None
    )
    summary = {
        "schema_version": 1,
        "harness_checks_passed": harness_ok,
        "pytest": counts,
        "test_mode": "real M1 PostgreSQL; explicit HTTP/model/outbox doubles",
        "fixture_sha256": fixture_hash,
        "fixture_bytes_unchanged": fixture_hash == file_hash(fixture),
        "human_review_and_final_quality": "NOT_RUN",
        "real_DE_gates": "INCOMPLETE",
        "sequencing_exception": "user authorized isolated P11 while real gates stay incomplete",
        "live_quality": "NOT_RUN",
        "live_latency": None,
        "live_tokens": None,
        "live_cost": None,
        "live_model_calls": 0,
        "real_eval_exit": real.returncode,
        "checks": checks,
    }
    summary["content_sha256"] = content_hash(summary)
    write_json(destination / "checks.json", summary)
    write_json(
        destination / "evidence-index.json",
        {
            "artifacts": [
                {"path": p.relative_to(ROOT).as_posix(), "sha256": file_hash(p)}
                for p in sorted(destination.iterdir())
                if p.is_file()
            ]
        },
    )
    print(
        json.dumps(
            {
                "harness_checks_passed": harness_ok,
                "pytest": counts,
                "live_quality": "NOT_RUN",
                "evidence_dir": args.out,
            }
        ),
        flush=True,
    )
    return 0 if harness_ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
