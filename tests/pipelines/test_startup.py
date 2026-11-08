"""Explicit connection/clock doubles; a retry pass does not certify live infrastructure."""

import json
from uuid import uuid4

import httpx
import psycopg
import pytest
from confluent_kafka import KafkaError, KafkaException

from infra import audit_roles, postgres, startup, streaming
from projectctl.models import ExitCode
from projectctl.providers import Invocation
from shared.event_transport.schemas import SchemaUnavailable


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_transient_failure_recovers_and_start_is_logged_before_operation(tmp_path, monkeypatch):
    path = tmp_path / "startup.jsonl"
    check, calls, waits = startup.StartupChecks(path), [], []
    monkeypatch.setattr(startup, "sleep", waits.append)

    def operation():
        assert rows(path)[-1]["status"] == "STARTED"
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("private URL/token must not be logged")
        return "actual-operation-result"

    assert check("registry-verification", operation, retry=True) == "actual-operation-result"
    assert waits == [1]
    assert [r["status"] for r in rows(path)] == ["STARTED", "RETRY", "STARTED", "PASSED"]
    assert "private" not in path.read_text()


def test_persistent_timeout_is_bounded_and_docker_actions_are_not_retried(tmp_path, monkeypatch):
    waits, calls = [], []
    monkeypatch.setattr(startup, "sleep", waits.append)
    path = tmp_path / "startup.jsonl"

    def timeout():
        calls.append(1)
        raise psycopg.errors.ConnectionTimeout("sensitive-connection-string")

    with pytest.raises(startup.StartupFailure, match="postgres-connect.catalog.*3 attempt"):
        startup.StartupChecks(path)("postgres-connect.catalog", timeout, retry=True)
    assert len(calls) == 3 and waits == [1, 2]
    assert rows(path)[-1]["status"] == "FAILED"
    assert "sensitive" not in path.read_text()
    with pytest.raises(startup.StartupFailure, match="compose-up.*1 attempt"):
        startup.StartupChecks(path)("compose-up", timeout)
    assert len(calls) == 4 and waits == [1, 2]


@pytest.mark.parametrize(
    "status,expected",
    [
        (400, False),
        (401, False),
        (403, False),
        (409, False),
        (422, False),
        (429, True),
        (500, True),
        (502, True),
        (503, True),
        (504, True),
    ],
)
def test_http_policy_distinguishes_permanent_errors(status, expected):
    response = httpx.Response(
        status, request=httpx.Request("GET", "http://registry.invalid/config")
    )
    assert (
        startup.transient(
            httpx.HTTPStatusError("private", request=response.request, response=response)
        )
        is expected
    )


@pytest.mark.parametrize(
    "error,expected",
    [
        (psycopg.errors.InvalidPassword(), False),
        (psycopg.errors.InsufficientPrivilege(), False),
        (psycopg.errors.CannotConnectNow(), True),
        (psycopg.errors.ConnectionException(), True),
        (SchemaUnavailable("wrong hash"), False),
        (postgres.SetupError("wrong resource limit"), False),
    ],
)
def test_database_auth_and_invariant_failures_are_not_transient(error, expected):
    assert startup.transient(error) is expected


@pytest.mark.parametrize("retriable", [False, True])
def test_kafka_retry_policy_uses_broker_error_flag(retriable):
    error = KafkaException(KafkaError(KafkaError._TIMED_OUT, retriable=retriable))
    assert startup.transient(error) is retriable


@pytest.mark.parametrize(
    "error", [SchemaUnavailable("wrong hash"), postgres.SetupError("wrong RAM limit")]
)
def test_invariant_failure_stops_immediately(tmp_path, monkeypatch, error):
    monkeypatch.setattr(startup, "sleep", lambda value: pytest.fail("invariant was retried"))
    path = tmp_path / "startup.jsonl"
    with pytest.raises(startup.StartupFailure):
        startup.StartupChecks(path)("validation", lambda: (_ for _ in ()).throw(error), retry=True)
    assert [r["status"] for r in rows(path)] == ["STARTED", "FAILED"]


def test_adapter_retains_attempts_and_reports_actual_failed_stage(tmp_path, monkeypatch):
    monkeypatch.setattr(streaming, "RUNTIME", tmp_path)
    monkeypatch.setattr(postgres, "check_engine", lambda: None)
    monkeypatch.setattr(postgres, "prepare", lambda: None)
    monkeypatch.setattr(postgres, "command", lambda *args, **kw: "volume-double")
    monkeypatch.setattr(streaming, "compose", lambda *args: None)
    monkeypatch.setattr(streaming, "provision_topics", lambda *args: None)
    monkeypatch.setattr(audit_roles, "provision", lambda: None)
    monkeypatch.setattr(startup, "sleep", lambda value: None)
    calls = []

    def registration(*args):
        calls.append(1)
        raise httpx.ReadTimeout("do-not-log-this-credential")

    monkeypatch.setattr(streaming, "register_schemas", registration)
    monkeypatch.setattr(
        streaming, "verify", lambda **kw: pytest.fail("verification ran after failure")
    )
    invocation = Invocation("env up", {}, None, str(uuid4()), "dev")
    result = streaming.adapter(invocation)
    path = tmp_path / "checks" / invocation.run_id / "startup.jsonl"
    assert result.code == ExitCode.DEPENDENCY_FAILURE and len(calls) == 3
    assert "schema-registration" in result.reasons[0] and "ReadTimeout" in result.reasons[0]
    assert "do-not-log" not in path.read_text() + str(result.reasons)
    assert not (path.parent / "streaming.json").exists()
