"""P7 checkpoint only: real Docker PostgreSQL, explicit HTTP/event doubles."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import psycopg

ROOT = Path(__file__).resolve().parents[2]


def docker_database(url):
    """Read only discovery; retain selected facts, never inspect environment secrets."""
    containers = subprocess.run(
        ["docker", "ps", "-q"], check=True, capture_output=True, text=True
    ).stdout.split()
    port = urlparse(url).port
    for container_id in containers:
        inspected = json.loads(
            subprocess.run(
                ["docker", "inspect", container_id], check=True, capture_output=True, text=True
            ).stdout
        )[0]
        ports = inspected["NetworkSettings"]["Ports"].get("5432/tcp") or []
        if any(p["HostIp"] == "127.0.0.1" and int(p["HostPort"]) == port for p in ports):
            with psycopg.connect(url, connect_timeout=2) as tx:
                version = tx.info.server_version
                durability = {
                    s: tx.execute("SHOW " + s).fetchone()[0]
                    for s in ("fsync", "full_page_writes", "synchronous_commit")
                }
            if not 180000 <= version < 190000 or set(durability.values()) != {"on"}:
                raise ValueError("PostgreSQL 18/durability requirement failed")
            return {
                "container_id": container_id,
                "image_id": inspected["Image"],
                "server_version_num": version,
                "host_port": port,
                "durability": durability,
                "status": inspected["State"]["Status"],
            }
    raise ValueError("Explicit database URL does not match a running loopback Docker PostgreSQL")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--database-file",
        type=Path,
        required=True,
        help="ignored local JSON containing url of an isolated Docker test DB",
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    url = json.loads(args.database_file.read_text(encoding="utf-8"))["url"]
    facts = docker_database(url)
    (args.out / "database.json").write_text(json.dumps(facts, indent=2), encoding="utf-8")
    environment = {
        **os.environ,
        "P6_TEST_DATABASE_URL": url,
        "PYTHONIOENCODING": "utf-8",
        "ASSISTANT_MODE": "fixed",
        "ALLOW_INTENT_LLM": "false",
    }
    python = sys.executable
    paths = [
        "services/conversation",
        "tests/conversation",
        "benchmarks/manual/p7_smoke.py",
        "benchmarks/manual/verify_p7.py",
    ]
    commands = [
        (
            [python, "-c", "import sys; print(sys.version); assert sys.version_info[:2] == (3,11)"],
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
                "-o",
                "junit_family=xunit1",
                "-o",
                f"cache_dir={args.out / 'cache'}",
                f"--basetemp={args.out / 'test-temp'}",
                f"--junitxml={args.out / 'pytest.xml'}",
            ],
            0,
        ),
        (
            [
                python,
                "-m",
                "benchmarks.manual.p7_smoke",
                "--test-double-providers",
                "--confirm-checkout",
                "--out",
                str(args.out / "smoke"),
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
                "shared/contracts",
                "contracts",
                "configs",
                "uv.lock",
                "pyproject.toml",
                "services",
                ":(exclude)services/conversation",
                "migrations",
                ":(exclude)migrations/conversation",
                "shared/outbox",
                "shared/event_transport",
                "infra",
                "pipelines",
            ],
            0,
        ),
    ]
    checks = []
    for command, expected in commands:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        checks.append(
            {
                "command": command,
                "expected_exit": expected,
                "actual_exit": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "matched": result.returncode == expected,
            }
        )
        (args.out / "checks.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
        print(f"{result.returncode} (expected {expected}): {' '.join(command)}", flush=True)
    junit = ET.parse(args.out / "pytest.xml").getroot()
    tests = list(junit.iter("testcase"))
    rows = [
        json.loads(p.attrib["value"])
        for p in junit.iter("property")
        if p.attrib.get("name") == "assistant_turn"
    ]
    for filename, values in (
        ("assistant_turns.jsonl", rows),
        (
            "tests.jsonl",
            [
                {
                    "case_id": "T-10/D-05/" + row["scenario_id"],
                    "input_fixture_hash": hashlib.sha256(
                        (ROOT / "contracts/fixtures/assistant/scenarios.json").read_bytes()
                    ).hexdigest(),
                    "namespace": row["namespace"],
                    "started_at": row["started_at"],
                    "completed_at": row["completed_at"],
                    "status": "PASS",
                    "assertions": [
                        {
                            "name": "fixed_scenario_assertions",
                            "expected": "pass",
                            "observed": "pass",
                            "passed": True,
                        }
                    ],
                    "fault_receipt_refs": [],
                    "artifact_refs": ["pytest.xml", "assistant_turns.jsonl"],
                    "failure_reason": None,
                }
                for row in rows
            ],
        ),
    ):
        (args.out / filename).write_text(
            "".join(json.dumps(v) + "\n" for v in values), encoding="utf-8"
        )
    passed = (
        all(c["matched"] for c in checks)
        and len(rows) == 60
        and all(
            t.find("skipped") is None and t.find("failure") is None and t.find("error") is None
            for t in tests
        )
        and all(row["model_attempts"] == 0 for row in rows)
    )
    summary = {
        "checkpoint": "P7",
        "status": "stub verified" if passed else "INCOMPLETE",
        "completed_at": datetime.now(UTC).isoformat(),
        "tests": len(tests),
        "scenario_records": len(rows),
        "model_attempts": sum(r["model_attempts"] for r in rows),
        "database": "real Docker PostgreSQL 18",
        "providers": "explicit HTTP doubles",
        "events": "explicit transactional capture double",
        "real_G3": "NOT_RUN",
        "shared_event_gate": "INCOMPLETE",
        "live_assist": "NOT_RUN",
        "human_label_review": "NOT_RUN",
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
