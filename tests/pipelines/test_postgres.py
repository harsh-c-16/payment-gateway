"""Offline provider boundary checks; doubles do not certify a running database."""

import json
import subprocess
from types import SimpleNamespace
from uuid import uuid4

import pytest
import yaml

from infra import postgres
from projectctl.models import ExitCode
from projectctl.providers import Invocation, ProviderRegistry


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    directory = tmp_path / "runtime"
    monkeypatch.setattr(postgres, "RUNTIME", directory)
    return directory


def invocation(action="env verify", profile="postgres-local"):
    return Invocation(action, {"profile": profile}, None, str(uuid4()), "bench-m01")


def test_credentials_stable_distinct_and_missing_file_never_rotated(runtime):
    values = postgres.credentials(create=True)
    assert len(set(values.values())) == 7
    assert postgres.credentials(create=True) == values
    (runtime / "secrets/orders_password").unlink()
    with pytest.raises(postgres.SetupError, match="restore"):
        postgres.credentials(create=True)
    assert (runtime / "secrets/catalog_password").read_text() == values["catalog"]
    assert not (runtime / "secrets/orders_password").exists()


def test_missing_or_invalid_credentials_fail_without_exposing_content(runtime):
    with pytest.raises(postgres.SetupError, match="missing/incomplete"):
        postgres.credentials()
    assert not runtime.exists()
    postgres.credentials(create=True)
    (runtime / "secrets/catalog_password").write_text("sensitive-invalid-value")
    with pytest.raises(postgres.SetupError) as error:
        postgres.credentials()
    assert "sensitive-invalid-value" not in str(error.value)


def test_prepare_reuses_credentials_and_writes_the_same_local_urls(runtime):
    values = postgres.credentials(create=True)
    postgres.prepare()
    before = (runtime / ".env").read_text()
    postgres.prepare()
    assert (runtime / ".env").read_text() == before
    assert postgres.credentials() == values
    for service in postgres.SERVICES:
        assert f"{service.upper()}_DATABASE_URL={postgres.database_url(service, values)}" in before


@pytest.mark.parametrize("failure", [FileNotFoundError(), subprocess.TimeoutExpired("docker", 180)])
def test_missing_or_stalled_docker_is_a_dependency_failure(runtime, monkeypatch, failure):
    def unavailable(*args, **kwargs):
        raise failure

    monkeypatch.setattr(postgres.subprocess, "run", unavailable)
    result = postgres.adapter(invocation("env up"))
    assert result.code == ExitCode.DEPENDENCY_FAILURE
    assert result.test_mode == "real"
    if isinstance(failure, subprocess.TimeoutExpired):
        assert "timed out" in result.reasons[0] and "install" not in result.reasons[0]
    assert not runtime.exists()


def test_docker_error_output_is_not_exposed(monkeypatch):
    monkeypatch.setattr(
        postgres.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(
            returncode=1, stdout="secret in SQL", stderr="secret in container configuration"
        ),
    )
    with pytest.raises(postgres.SetupError) as error:
        postgres.command(["docker", "compose", "up"])
    assert "secret" not in str(error.value)


def test_full_profile_is_not_claimed_and_only_owned_actions_registered():
    registry = ProviderRegistry()
    postgres.register(registry)
    assert registry.missing("env reset")
    assert registry.missing("db migrate")
    assert registry.invoke(invocation(profile="local4c8g")).code == ExitCode.BAD_INPUT


def test_down_keeps_volume_and_credentials(runtime, monkeypatch):
    values = postgres.credentials(create=True)
    commands = []
    monkeypatch.setattr(postgres, "check_engine", lambda: None)
    monkeypatch.setattr(postgres, "compose", lambda *args: commands.append(args))
    result = postgres.adapter(invocation("env down"))
    assert result.code == ExitCode.COMPLETED
    assert commands == [("down", "--timeout", "30")]
    assert postgres.credentials() == values


def test_compose_uses_secrets_locked_image_volume_and_proposed_database_limits():
    document = yaml.safe_load(postgres.COMPOSE.read_text(encoding="utf-8"))
    service = document["services"]["postgres"]
    lock = json.loads((postgres.ROOT / "infra/images.lock.json").read_text())
    assert service["image"] == lock["postgres"]["image"]
    assert service["image"].endswith("@sha256:" + lock["postgres"]["manifest_sha256"])
    assert service["ports"] == ["127.0.0.1:5432:5432"]
    assert "postgres_data:/var/lib/postgresql" in service["volumes"]
    assert service["cpus"] == 0.75 and service["mem_limit"] == "2048m"
    assert len(service["secrets"]) == 7
    assert not any(
        "PASSWORD" in key and not key.endswith("_FILE") for key in service["environment"]
    )
    if lock["postgres"]["status"] == "SMOKE_TESTED":
        assert lock["postgres"]["observed_server_version"].startswith("18.")
        assert lock["postgres"]["smoke_evidence"].endswith("/live-test.json")
    else:
        assert lock["postgres"]["status"] == "RESOLVED_NOT_SMOKE_TESTED"
        assert lock["postgres"]["observed_server_version"] is None
        assert lock["postgres"]["smoke_evidence"] is None
    assert "-h 127.0.0.1" in service["healthcheck"]["test"][1]


def container_state():
    lock = json.loads((postgres.ROOT / "infra/images.lock.json").read_text())
    return {
        "health": "healthy",
        "image_id": "explicit-test-image-id",
        "image": lock["postgres"]["image"],
        "mounts": [
            {
                "Destination": "/var/lib/postgresql",
                "Type": "volume",
                "RW": True,
                "Name": "explicit-test-volume",
            }
        ],
        "ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "5432"}]},
        "memory": 2048 * 1024 * 1024,
        "cpu": 750000000,
    }


def mock_container(monkeypatch, state):
    monkeypatch.setattr(postgres, "check_engine", lambda: None)
    monkeypatch.setattr(postgres, "compose", lambda *args: "explicit-test-container")
    monkeypatch.setattr(postgres, "command", lambda *a, **kw: json.dumps(state))


@pytest.mark.parametrize(
    "mutation", ["public_port", "no_volume", "unlimited_memory", "wrong_image"]
)
def test_verify_rejects_container_guarantee_changes(runtime, monkeypatch, mutation):
    postgres.credentials(create=True)
    state = container_state()
    if mutation == "public_port":
        state["ports"]["5432/tcp"][0]["HostIp"] = "0.0.0.0"
    elif mutation == "no_volume":
        state["mounts"] = []
    elif mutation == "unlimited_memory":
        state["memory"] = 0
    else:
        state["image"] = "postgres:latest"
    mock_container(monkeypatch, state)
    with pytest.raises(postgres.SetupError, match="Container"):
        postgres.verify()


class DatabaseDouble:
    """Explicit query double covering rejection paths, never real SQL evidence."""

    def __init__(self, service, failure=None):
        self.service, self.failure = service, failure
        self.info = SimpleNamespace(server_version=180001 if failure != "version" else 170000)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement):
        if statement.startswith("SHOW"):
            row = ("off" if self.failure == "durability" else "on",)
        elif "FROM pg_roles" in statement:
            row = (self.failure == "superuser", False, False, False, False)
        elif "FROM pg_database" in statement:
            rows = [(f"{self.service}_db",)]
            if self.failure == "isolation":
                rows.append(("another_service_db",))
            return SimpleNamespace(fetchall=lambda: rows)
        elif "FROM pg_extension" in statement:
            row = ("0.8.2" if self.failure == "vector" else "0.8.1",)
        else:
            row = (1,)
        return SimpleNamespace(fetchone=lambda: row)


@pytest.mark.parametrize("failure", ["version", "durability", "superuser", "isolation", "vector"])
def test_database_validation_rejects_incorrect_guarantees(runtime, monkeypatch, failure):
    postgres.credentials(create=True)
    mock_container(monkeypatch, container_state())
    monkeypatch.setattr(
        postgres.psycopg,
        "connect",
        lambda url, **kw: DatabaseDouble(url.split("/")[-1].removesuffix("_db"), failure),
    )
    with pytest.raises(postgres.SetupError):
        postgres.verify()


def test_success_evidence_contains_no_credentials(runtime, monkeypatch):
    values = postgres.credentials(create=True)
    mock_container(monkeypatch, container_state())
    monkeypatch.setattr(
        postgres.psycopg,
        "connect",
        lambda url, **kw: DatabaseDouble(url.split("/")[-1].removesuffix("_db")),
    )
    request = invocation()
    result = postgres.adapter(request)
    assert result.code == ExitCode.COMPLETED
    evidence = (runtime / "checks" / request.run_id / "postgres.json").read_text()
    assert all(password not in evidence for password in values.values())
    assert "full G0 NOT_RUN" in evidence


def test_smaller_postgres_limits_need_the_explicit_profile(runtime, monkeypatch):
    postgres.credentials(create=True)
    state = container_state()
    state.update(memory=512 * 1024 * 1024, cpu=500000000)
    mock_container(monkeypatch, state)
    monkeypatch.setattr(
        postgres.psycopg,
        "connect",
        lambda url, **kw: DatabaseDouble(url.split("/")[-1].removesuffix("_db")),
    )
    with pytest.raises(postgres.SetupError, match="limits differ"):
        postgres.verify()
    assert postgres.verify(memory_mib=512, cpu_cores=0.5)["databases"]
