"""Repository CI checks. Offline passes never certify PostgreSQL, Kafka or DE gates.

Run from the repository root with the locked Python. Service jobs require explicit
isolated test URLs; the workflow provisions pinned images before invoking them.
"""

import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

import psycopg

ROOT = Path(__file__).resolve().parents[2]
SUITES = (
    "conversation",
    "catalog",
    "analytics",
    "pipelines",
    "transactions",
    "contracts",
    "projectctl",
    "benchmarks",
    "oracles",
    "telemetry",
    "integration",
)
OWNED = (
    "benchmarks",
    "projectctl",
    "services/conversation",
    "shared/telemetry",
    "dashboards",
    *(
        f"tests/{name}"
        for name in SUITES
        if name
        not in {
            "catalog",
            "analytics",
            "pipelines",
            "transactions",
        }
    ),
)
DATABASES = (
    "P6_TEST_DATABASE_URL",
    "CATALOG_TEST_DATABASE_URL",
    "ANALYTICS_TEST_DATABASE_URL",
    "INVENTORY_TEST_DATABASE_URL",
)
NATIVE = (
    "tests/pipelines/test_postgres_live.py",
    "tests/pipelines/test_streaming_live.py",
    "tests/pipelines/test_event_contracts_live.py",
    "tests/pipelines/test_transport_live.py",
    "tests/catalog/test_projection_kafka_live.py",
)


def environment(job):
    """Do not let a developer's opt-ins turn offline CI into a service test."""
    env = {
        k: v
        for k, v in os.environ.items()
        if not (k.startswith("RUN_") and k.endswith("_LIVE_TESTS"))
        and k
        not in {
            *DATABASES,
            "CATALOG_TEST_KAFKA_BOOTSTRAP",
            "M09_BROKER_OUTAGE",
            "PROJECTCTL_ADAPTER_MODULE",
            "PROJECTCTL_RUNTIME_MODULE",
            "PROJECTCTL_OWNER_RUNTIME_MODULES",
            "PROJECTCTL_PERFORMANCE_REVIEW_PATH",
            "PROJECTCTL_CONTRACT_REVIEW_PATH",
            "ANALYTICS_BINDING_REVIEW_PATH",
            "OPENAI_API_KEY",
            "GEMINI_API_KEY",
            "SHOPPING_LLM_MODEL",
            "SHOPPING_LLM_ENABLED",
        }
    }
    env.update(PYTHONIOENCODING="utf-8", ASSISTANT_MODE="fixed", ALLOW_INTENT_LLM="false")
    if job != "offline":
        env.update({k: os.environ[k] for k in DATABASES if os.environ.get(k)})
    if job == "kafka":
        env.update(
            {
                "RUN_POSTGRES_LIVE_TESTS": "1",
                "RUN_STREAMING_LIVE_TESTS": "1",
                "RUN_CONTRACTS_LIVE_TESTS": "1",
                "RUN_TRANSPORT_LIVE_TESTS": "1",
                "CATALOG_TEST_KAFKA_BOOTSTRAP": "127.0.0.1:9092",
            }
        )
    if job == "volume":
        env.update(RUN_VERTICAL_LIVE_TESTS="1", RUN_STORAGE_LIVE_TESTS="1")
    return env


def junit_summary(path):
    """Count outcomes separately; xfail is NOT_RUN and strict XPASS is a failure."""
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    counts = dict.fromkeys(("tests", "passed", "failures", "errors", "skipped", "xfail"), 0)
    counts["tests"] = len(cases)
    unavailable = []
    for case in cases:
        skip = case.find("skipped")
        if case.find("failure") is not None:
            counts["failures"] += 1
        elif case.find("error") is not None:
            counts["errors"] += 1
        elif skip is not None:
            key = "xfail" if skip.get("type") == "pytest.xfail" else "skipped"
            counts[key] += 1
            unavailable.append(
                {
                    "case": case.get("classname", "") + "::" + case.get("name", ""),
                    "status": "NOT_RUN",
                    "kind": key,
                    "reason": skip.get("message") or skip.text or "unspecified",
                }
            )
        else:
            counts["passed"] += 1
    return {**counts, "unavailable": unavailable}


def contract_outcome(code, stdout):
    """Exit 4 is dependency evidence only when the CLI actually says so."""
    try:
        result = json.loads(stdout)
    except (ValueError, TypeError):
        return False
    if not isinstance(result, dict):
        return False
    reasons = result.get("reasons")
    if (
        result.get("exit_code") != code
        or not isinstance(reasons, list)
        or not reasons
        or not all(isinstance(reason, str) for reason in reasons)
    ):
        return False
    if code == 0:
        return result.get("status") in {"NOT_RUN", "MEASURED"} and all(
            r.startswith(("PASS:", "Offline inventory")) for r in result["reasons"]
        )
    return (
        code == 4
        and result.get("status") == "NOT_RUN"
        and any(r.startswith(("UNREVIEWED:", "MISSING:")) for r in result["reasons"])
        and not any(r.startswith("FAIL:") for r in result["reasons"])
    )


class Recorder:
    def __init__(self, out, env):
        self.out, self.env, self.checks = out, env, []

    def run(self, label, command, *, contracts=False, timeout=1800):
        started, tick = datetime.now(UTC).isoformat(), monotonic()
        try:
            result = subprocess.run(
                command,
                cwd=ROOT,
                env=self.env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            code, stdout, stderr = result.returncode, result.stdout, result.stderr
        except (OSError, subprocess.TimeoutExpired) as exc:

            def decode(value):
                return (
                    value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
                )

            code = None
            stdout = decode(getattr(exc, "stdout", "")) or ""
            stderr = (decode(getattr(exc, "stderr", "")) or "") + type(exc).__name__
        # Service URLs may contain credentials in a failing driver's traceback.
        for value in (self.env.get(key) for key in DATABASES):
            if value:
                stdout, stderr = (
                    stdout.replace(value, "[test URL]"),
                    stderr.replace(value, "[test URL]"),
                )
        (self.out / f"{label}.stdout.log").write_text(stdout, encoding="utf-8")
        (self.out / f"{label}.stderr.log").write_text(stderr, encoding="utf-8")
        row = {
            "label": label,
            "command": command,
            "cwd": str(ROOT),
            "actual_exit": code,
            "started_at": started,
            "elapsed_seconds": monotonic() - tick,
            "passed": contract_outcome(code, stdout) if contracts else code == 0,
            "status": "NOT_RUN"
            if contracts and code in {0, 4}
            else ("PASS" if code == 0 else "FAIL"),
        }
        self.checks.append(row)
        (self.out / "checks.json").write_text(json.dumps(self.checks, indent=2), encoding="utf-8")
        print(f"{label}: exit {code}; {row['status']}", flush=True)
        return row["passed"]


def database_ready(env, keys):
    for key in keys:
        if not env.get(key):
            return {"status": "NOT_RUN", "reason": f"{key} is required"}
        try:
            with psycopg.connect(env[key], connect_timeout=3) as tx:
                if not 180000 <= tx.info.server_version < 190000:
                    return {"status": "FAIL", "reason": f"{key} requires PostgreSQL 18"}
                if key == "CATALOG_TEST_DATABASE_URL":
                    version = tx.execute(
                        "SELECT extversion FROM pg_extension WHERE extname='vector'"
                    ).fetchone()
                    if version != ("0.8.1",):
                        return {"status": "NOT_RUN", "reason": f"{key} requires pgvector 0.8.1"}
                if any(
                    tx.execute("SHOW " + name).fetchone()[0] != "on"
                    for name in (
                        "fsync",
                        "full_page_writes",
                        "synchronous_commit",
                    )
                ):
                    return {"status": "FAIL", "reason": f"{key} durability is disabled"}
        except psycopg.Error as exc:
            return {"status": "NOT_RUN", "reason": f"{key}: {type(exc).__name__}"}
    return {"status": "PASS", "postgres_major": 18, "durability": "on"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", choices=("offline", "postgres", "kafka", "volume"), required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    out = args.out.resolve()
    if not out.is_relative_to(ROOT / "artifacts"):
        parser.error("--out must be a new directory under artifacts/")
    out.mkdir(parents=True, exist_ok=False)
    env = environment(args.job)
    recorder = Recorder(out, env)
    summary = {
        "job": args.job,
        "status": "INCOMPLETE",
        "pytest": None,
        "real_DE_gates": "NOT_RUN",
        "performance_matrix": "NOT_RUN",
        "doubles": "Test-specific HTTP/model/registry-ID/outbox doubles; see test docstrings",
        "external_broker_pause_controller": "NOT_RUN",
    }
    try:
        if args.job != "offline":
            if sys.platform != "linux":
                summary["status"] = "NOT_RUN"
                summary["dependencies"] = {
                    "status": "NOT_RUN",
                    "reason": "Selected suites require Linux directory fsync; use Linux CI jobs",
                }
                return 4
            keys = (
                DATABASES
                if args.job == "postgres"
                else (
                    ("CATALOG_TEST_DATABASE_URL",)
                    if args.job == "kafka"
                    else ("ANALYTICS_TEST_DATABASE_URL",)
                )
            )
            summary["dependencies"] = database_ready(env, keys)
            if summary["dependencies"]["status"] != "PASS":
                summary["status"] = summary["dependencies"]["status"]
                return 4 if summary["status"] == "NOT_RUN" else 1
        if args.job == "offline":
            for label, arguments in (
                ("lint", ["ruff", "check", *OWNED]),
                ("format", ["ruff", "format", "--check", *OWNED]),
                ("schemas", ["projectctl.schemas", "--check"]),
                ("conversation-contract", ["projectctl.conversation_contract", "--check"]),
            ):
                recorder.run(label, [sys.executable, "-m", *arguments])
            recorder.run(
                "contracts",
                [sys.executable, "-m", "projectctl", "contracts", "check", "--all"],
                contracts=True,
            )
            suites = [f"tests/{name}" for name in SUITES]
        elif args.job == "postgres":
            suites = [f"tests/{name}" for name in ("conversation", "catalog", "transactions")]
        elif args.job == "kafka":
            # These native tests recreate only the dedicated CI stack, serially.
            suites = list(NATIVE)
        else:
            suites = ["tests/pipelines", "tests/analytics"]
        recorder.run(
            "pytest",
            [
                sys.executable,
                "-m",
                "pytest",
                *suites,
                "-q",
                "-ra",
                "--tb=short",
                "-o",
                "junit_family=xunit1",
                f"--junitxml={out / 'pytest.xml'}",
                # Keep private pytest directories outside the artifact upload tree.
                f"--basetemp={out.parent / (out.name + '-pytest-tmp')}",
                "-o",
                f"cache_dir={out / 'cache'}",
            ],
        )
        if (out / "pytest.xml").is_file():
            summary["pytest"] = junit_summary(out / "pytest.xml")
        counts = summary["pytest"]
        okay = bool(counts and counts["tests"] and not (counts["failures"] or counts["errors"]))
        summary["status"] = "PASS" if okay and all(c["passed"] for c in recorder.checks) else "FAIL"
        return 0 if summary["status"] == "PASS" else 1
    finally:
        (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        console = {**summary}
        if console["pytest"]:
            console["pytest"] = {k: v for k, v in console["pytest"].items() if k != "unavailable"}
        print(json.dumps(console), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
