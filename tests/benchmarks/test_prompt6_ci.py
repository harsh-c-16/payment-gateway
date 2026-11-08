"""CI evidence regressions; subprocesses and XML below are explicit test doubles."""

import json
import subprocess
from types import SimpleNamespace

import pytest
import yaml

from benchmarks.manual.verify_prompt6 import (
    ROOT,
    Recorder,
    contract_outcome,
    database_ready,
    environment,
    junit_summary,
)


def test_offline_scrubs_local_service_opt_ins(monkeypatch):
    for key in (
        "P6_TEST_DATABASE_URL",
        "CATALOG_TEST_DATABASE_URL",
        "INVENTORY_TEST_DATABASE_URL",
        "ANALYTICS_TEST_DATABASE_URL",
        "CATALOG_TEST_KAFKA_BOOTSTRAP",
        "RUN_VERTICAL_LIVE_TESTS",
        "RUN_POSTGRES_LIVE_TESTS",
        "M09_BROKER_OUTAGE",
        "PROJECTCTL_ADAPTER_MODULE",
        "PROJECTCTL_RUNTIME_MODULE",
        "OPENAI_API_KEY",
    ):
        monkeypatch.setenv(key, "must-not-leak")
    env = environment("offline")
    assert "must-not-leak" not in env.values()
    assert env["ASSISTANT_MODE"] == "fixed" and env["ALLOW_INTENT_LLM"] == "false"
    assert environment("postgres")["P6_TEST_DATABASE_URL"] == "must-not-leak"


def test_summary_preserves_skip_xfail_strict_xpass_and_error(tmp_path):
    path = tmp_path / "pytest.xml"
    path.write_text(
        """<testsuites><testsuite>
      <testcase name="pass"/>
      <testcase name="unavailable"><skipped message="real Kafka absent"/></testcase>
      <testcase name="known"><skipped type="pytest.xfail" message="owner defect"/></testcase>
      <testcase name="stale"><failure message="[XPASS(strict)]"/></testcase>
      <testcase name="fixture"><error/></testcase>
    </testsuite></testsuites>""",
        encoding="utf-8",
    )
    counts = junit_summary(path)
    assert {k: v for k, v in counts.items() if k != "unavailable"} == {
        "tests": 5,
        "passed": 1,
        "failures": 1,
        "errors": 1,
        "skipped": 1,
        "xfail": 1,
    }
    assert [v["reason"] for v in counts["unavailable"]] == ["real Kafka absent", "owner defect"]
    assert all(v["status"] == "NOT_RUN" for v in counts["unavailable"])


@pytest.mark.parametrize(
    "code,status,reasons,okay",
    [
        (4, "NOT_RUN", ["UNREVIEWED: owner binding"], True),
        (4, "NOT_RUN", ["UNREVIEWED: owner binding", "FAIL: bad contract"], False),
        (4, "NOT_RUN", ["something went wrong"], False),
        (3, "INCOMPLETE", ["UNREVIEWED: owner binding"], False),
        (0, "MEASURED", ["PASS: contracts"], True),
        (0, "NOT_RUN", ["UNREVIEWED: owner binding"], False),
        (0, "NOT_RUN", ["PASS: contracts", "Offline inventory only"], True),
    ],
)
def test_contract_exit_is_checked_against_evidence(code, status, reasons, okay):
    assert (
        contract_outcome(
            code,
            json.dumps(
                {
                    "exit_code": code,
                    "status": status,
                    "reasons": reasons,
                }
            ),
        )
        is okay
    )
    assert not contract_outcome(code, "not a CLI result")
    assert not contract_outcome(code, "[]")
    assert not contract_outcome(code, "null")


def test_timeout_and_missing_executable_retain_failure_logs(tmp_path, monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 1, output=b"partial", stderr=b"failure")

    monkeypatch.setattr(subprocess, "run", timeout)
    recorder = Recorder(tmp_path, {})
    assert not recorder.run("timed", ["double"])
    assert (tmp_path / "timed.stdout.log").read_text() == "partial"
    assert "TimeoutExpired" in (tmp_path / "timed.stderr.log").read_text()
    assert recorder.checks[0]["actual_exit"] is None
    assert database_ready({}, ("P6_TEST_DATABASE_URL",))["status"] == "NOT_RUN"


def test_workflow_provisions_pinned_dependencies_and_always_uploads_evidence():
    # BaseLoader preserves GitHub's `on` key as a string instead of YAML 1.1 bool.
    workflow = yaml.load(
        (ROOT / ".github/workflows/offline.yml").read_text(), Loader=yaml.BaseLoader
    )
    jobs = workflow["jobs"]
    assert set(jobs) == {"offline", "postgres", "kafka-registry"}
    assert "@sha256:" in jobs["postgres"]["services"]["postgres"]["image"]
    for job in jobs.values():
        assert not job.get("continue-on-error")
        upload = next(
            s for s in job["steps"] if s.get("uses", "").startswith("actions/upload-artifact")
        )
        assert upload["if"] == "always()"
        assert "*.xml" in upload["with"]["path"] and "*.log" in upload["with"]["path"]
        assert all("secret" not in path for path in upload["with"]["path"].splitlines())
    assert any("streaming-local" in s.get("run", "") for s in jobs["kafka-registry"]["steps"])


def test_url_redacted_from_command_failure(tmp_path, monkeypatch):
    url = "postgresql://test:secret@localhost/test"
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(
            a[0],
            1,
            stdout=url,
            stderr=url,
        ),
    )
    assert not Recorder(tmp_path, {"P6_TEST_DATABASE_URL": url}).run("failed", ["double"])
    assert url not in (tmp_path / "failed.stderr.log").read_text()


def test_legacy_verifiers_preserve_existing_dirty_work_but_reject_new_changes(
    tmp_path, monkeypatch
):
    from benchmarks.manual.verifier_state import Preservation

    calls = []

    def saved(command, **kwargs):
        calls.append(command.copy())
        return "existing user edits\n"

    monkeypatch.setattr(subprocess, "check_output", saved)
    command = ["git", "diff", "--exit-code", "--", "configs", "services"]
    guard = Preservation([(command, 0)], tmp_path, tmp_path)
    assert "--exit-code" not in calls[0]
    assert guard.matches(command, "existing user edits\n")
    assert not guard.matches(command, "unexpected new edit\n")
    assert guard.matches(["python", "-m", "pytest"], "ordinary output")


def test_volume_runner_reuses_owner_stack_with_explicit_real_bindings(tmp_path, monkeypatch):
    from benchmarks.manual import prompt6_services as services

    (tmp_path / "infra").mkdir()
    for name in ("pyproject.toml", "uv.lock", "infra/storage.Dockerfile"):
        (tmp_path / name).write_text("explicit build-file double", encoding="utf-8")
    monkeypatch.setattr(services, "ROOT", tmp_path)
    monkeypatch.setattr(services.postgres, "credentials", lambda: {"analytics": "test-only"})
    monkeypatch.setattr(
        services.postgres, "database_url", lambda *a: "postgresql://test@127.0.0.1/analytics_db"
    )
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: "test-source\n")
    monkeypatch.setattr(services.sys, "argv", ["prompt6_services", "volume"])
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 1 if "compose" in command else 0)

    monkeypatch.setattr(subprocess, "run", run)
    assert services.main() == 1  # An actual worker failure must propagate to CI.
    command = calls[-1][0]
    assert "--no-deps" in command and "--rm" in command
    assert command[-4:] == ["--job", "volume", "--out", "artifacts/ci-volume"]
    overlay = json.loads((tmp_path / "artifacts/ci-private/volume.json").read_text())
    worker = overlay["services"]["storage-check"]
    assert worker["environment"]["RUN_VERTICAL_LIVE_TESTS"] == "1"
    assert (
        worker["environment"]["ANALYTICS_TEST_DATABASE_URL"]
        == "postgresql://test@postgres/analytics_db"
    )
    assert any("/analytics:/app/analytics:ro" in mount for mount in worker["volumes"])
    assert any("/migrations:/app/migrations:ro" in mount for mount in worker["volumes"])


@pytest.mark.parametrize(
    "vector,durable,status",
    [
        (None, "on", "NOT_RUN"),
        (("0.8.1",), "off", "FAIL"),
        (("0.8.1",), "on", "PASS"),
    ],
)
def test_postgres_preflight_requires_installed_vector_and_durability(
    monkeypatch, vector, durable, status
):
    class DatabaseDouble:
        info = SimpleNamespace(server_version=180002)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, query):
            row = vector if "pg_extension" in query else (durable,)
            return SimpleNamespace(fetchone=lambda: row)

    monkeypatch.setattr(
        "benchmarks.manual.verify_prompt6.psycopg.connect", lambda *a, **kw: DatabaseDouble()
    )
    assert (
        database_ready(
            {"CATALOG_TEST_DATABASE_URL": "explicit-double"}, ("CATALOG_TEST_DATABASE_URL",)
        )["status"]
        == status
    )


def test_unavailable_linux_job_is_not_a_database_pass(tmp_path, monkeypatch):
    from benchmarks.manual import verify_prompt6 as verifier

    monkeypatch.setattr(verifier, "ROOT", tmp_path)
    monkeypatch.setattr(verifier.sys, "platform", "win32")
    out = tmp_path / "artifacts/unavailable"
    assert verifier.main(["--job", "postgres", "--out", str(out)]) == 4
    summary = json.loads((out / "summary.json").read_text())
    assert summary["status"] == "NOT_RUN" and summary["pytest"] is None
    assert "Linux" in summary["dependencies"]["reason"]
