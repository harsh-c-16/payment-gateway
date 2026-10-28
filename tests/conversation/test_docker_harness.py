"""Docker lifecycle failure tests use explicit command doubles, not real integration."""

import copy
import json
import subprocess
from urllib.parse import urlsplit

import pytest

from benchmarks.manual import p6_docker, verify_p6


def container():
    return {
        "Id": "p6-container",
        "Image": "p6-image",
        "Config": {"Labels": {"group3.p6.run": "p6-test", "group3.owner": "jaineel"}},
        "State": {
            "Status": "running",
            "Health": {"Status": "healthy"},
            "StartedAt": "2026-10-27T00:00:00Z",
        },
        "Mounts": [
            {
                "Destination": "/var/lib/postgresql",
                "Type": "volume",
                "RW": True,
                "Name": "p6-test_data",
            }
        ],
        "NetworkSettings": {"Ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "55123"}]}},
    }


@pytest.mark.parametrize(
    "issue",
    [
        "owner",
        "project",
        "unhealthy",
        "missing_volume",
        "bind_volume",
        "readonly_volume",
        "public_port",
    ],
)
def test_docker_validation_rejects_wrong_or_unusable_resources(issue):
    actual = container()
    broken = copy.deepcopy(actual)
    if issue == "owner":
        broken["Config"]["Labels"]["group3.owner"] = "someone-else"
    if issue == "project":
        broken["Config"]["Labels"]["group3.p6.run"] = "unrelated"
    if issue == "unhealthy":
        broken["State"]["Health"]["Status"] = "unhealthy"
    if issue == "missing_volume":
        broken["Mounts"] = []
    if issue == "bind_volume":
        broken["Mounts"][0]["Type"] = "bind"
    if issue == "readonly_volume":
        broken["Mounts"][0]["RW"] = False
    if issue == "public_port":
        broken["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostIp"] = "0.0.0.0"
    with pytest.raises(p6_docker.DockerCheckError):
        p6_docker.validate_container(broken, "p6-test")
    assert p6_docker.validate_container(actual, "p6-test")["data_volume"] == "p6-test_data"


@pytest.mark.parametrize("issue", ["missing_cli", "daemon_down", "windows_engine"])
def test_docker_failure_retains_evidence_without_native_fallback(monkeypatch, tmp_path, issue):
    attempted = []

    def explicit_command_double(command, **kwargs):
        attempted.append(command)
        if issue == "missing_cli":
            raise FileNotFoundError
        if command[1:3] == ["context", "show"]:
            return subprocess.CompletedProcess(command, 0, "desktop-linux", "")
        if issue == "daemon_down":
            return subprocess.CompletedProcess(command, 1, "", "synthetic missing daemon pipe")
        return subprocess.CompletedProcess(command, 0, '{"version":"test","os":"windows"}', "")

    monkeypatch.setattr(p6_docker.subprocess, "run", explicit_command_double)
    monkeypatch.setenv("P6_TEST_DATABASE_URL", "postgresql://native-must-not-be-used")
    monkeypatch.setattr(
        p6_docker, "database_facts", lambda _: pytest.fail("native fallback attempted")
    )
    out = tmp_path / "failed-docker"
    assert p6_docker.run(out) == 4
    summary = json.loads((out / "docker-summary.json").read_text())
    assert summary["status"] == "INCOMPLETE" and summary["failure"]
    assert all(command[0] == "docker" for command in attempted)
    assert not (out / "compose.json").exists()
    assert (out / "docker-checks.json").exists()


def test_timed_out_docker_command_preserves_partial_redacted_output(monkeypatch, tmp_path):
    def timed_out(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            "docker", 1, output=b"partial generated-secret", stderr=b"retained diagnostics"
        )

    monkeypatch.setattr(p6_docker.subprocess, "run", timed_out)
    commands = p6_docker.Commands(tmp_path, secret="generated-secret")
    with pytest.raises(p6_docker.DockerCheckError):
        commands.run(["docker", "info"], timeout=1)
    saved = (tmp_path / "docker-checks.json").read_text()
    assert "partial [test credential]" in saved and "generated-secret" not in saved
    assert "retained diagnostics" in saved and "TimeoutExpired" in saved


def test_default_verifier_dispatches_to_docker_despite_existing_database_env(monkeypatch, tmp_path):
    requested = []
    monkeypatch.setenv("P6_TEST_DATABASE_URL", "postgresql://native-must-not-be-used")
    monkeypatch.setattr(p6_docker, "run", lambda out: requested.append(out) or 4)
    monkeypatch.setattr("sys.argv", ["verify_p6.py", "--out", str(tmp_path / "docker")])
    assert verify_p6.main() == 4
    assert requested == [tmp_path / "docker"]


def test_restart_refreshes_remapped_port_and_child_connection(monkeypatch, tmp_path):
    """Explicit Docker/DB command doubles; reproduce a real dynamic-port restart."""
    inspected = 0
    observed_urls = []
    child_urls = []

    def command_double(command, **kwargs):
        nonlocal inspected
        output = ""
        if command[1:3] == ["context", "show"]:
            output = "desktop-linux"
        elif command[1] == "info":
            output = '{"version":"test","os":"linux"}'
        elif command[1] == "inspect":
            value = container()
            value["Config"]["Labels"]["group3.p6.run"] = json.loads(
                (tmp_path / "run/compose.json").read_text()
            )["name"]
            value["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostPort"] = str(55123 + inspected)
            value["State"]["StartedAt"] = str(inspected)
            inspected += 1
            output = json.dumps(value)
        elif "ps" in command:
            output = "p6-container"
        elif command[0] != "docker":
            child_urls.append(kwargs["env"]["P6_TEST_DATABASE_URL"])
        return subprocess.CompletedProcess(command, 0, output, "")

    def facts_double(url):
        observed_urls.append(url)
        return {"server_version_num": 180006, "settings": {"fsync": "on"}}

    monkeypatch.setattr(p6_docker.subprocess, "run", command_double)
    monkeypatch.setattr(p6_docker, "database_facts", facts_double)
    out = tmp_path / "run"
    assert p6_docker.run(out) == 0
    assert len(observed_urls) == 2 and len(child_urls) == 2
    assert [urlsplit(url).port for url in observed_urls] == [55123, 55124]
    assert [urlsplit(url).port for url in child_urls] == [55123, 55124]
    saved = json.loads((out / "local-database.json").read_text())["url"]
    assert urlsplit(saved).port == 55124
