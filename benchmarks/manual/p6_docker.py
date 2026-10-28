"""Isolated Docker Compose PostgreSQL for P6. No native-database fallback.

This is Jaineel's test harness, not Vichitr's full application infrastructure.
Generated Compose files, credentials and raw evidence stay under artifacts/.
"""

import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from time import monotonic, sleep
from uuid import uuid4

import psycopg

ROOT = Path(__file__).resolve().parents[2]
POSTGRES_IMAGE = (
    "postgres:18.6@sha256:edb0c08dc33befd0262ab3b5cf1c4f3f8cfd8b09e88c05b45adee29d6761ddb6"
)


class DockerCheckError(RuntimeError):
    pass


class Commands:
    def __init__(self, out, *, secret):
        self.out, self.secret, self.records = out, secret, []

    def run(self, command, *, environment=None, timeout=120, expected=0):
        try:
            options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
            completed = subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                **options,
            )
            code, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
        except subprocess.TimeoutExpired as exc:

            def decoded(value):
                return (
                    value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
                )

            code = None
            stdout = decoded(exc.stdout) or ""
            stderr = (decoded(exc.stderr) or "") + "\nTimeoutExpired"
        except OSError as exc:
            code, stdout, stderr = None, "", type(exc).__name__
        self.records.append(
            {
                "command": command,
                "exit": code,
                "expected_exit": expected,
                "stdout": stdout.replace(self.secret, "[test credential]"),
                "stderr": stderr.replace(self.secret, "[test credential]"),
            }
        )
        (self.out / "docker-checks.json").write_text(
            json.dumps(self.records, indent=2), encoding="utf-8"
        )
        print(f"{code} (expected {expected}): {' '.join(command)}", flush=True)
        if code != expected:
            raise DockerCheckError("Command failed; inspect docker-checks.json.")
        return stdout.strip()


def compose_document(project, password):
    return {
        "name": project,
        "services": {
            "postgres": {
                "image": POSTGRES_IMAGE,
                "environment": {
                    "POSTGRES_USER": "p6_test",
                    "POSTGRES_PASSWORD": password,
                    "POSTGRES_DB": "conversation_p6",
                },
                "ports": [{"target": 5432, "published": "0", "host_ip": "127.0.0.1"}],
                "volumes": ["data:/var/lib/postgresql"],
                "healthcheck": {
                    "test": ["CMD-SHELL", "pg_isready -U p6_test -d conversation_p6"],
                    "interval": "1s",
                    "timeout": "3s",
                    "retries": 30,
                },
                "labels": {
                    "group3.owner": "jaineel",
                    "group3.milestone": "P6",
                    "group3.p6.run": project,
                },
                "cpus": 1,
                "mem_limit": "512m",
                "shm_size": "128m",
                "pids_limit": 128,
            }
        },
        "volumes": {"data": {"labels": {"group3.owner": "jaineel", "group3.p6.run": project}}},
    }


def validate_container(value, project):
    if (
        value["Config"]["Labels"].get("group3.p6.run") != project
        or value["Config"]["Labels"].get("group3.owner") != "jaineel"
        or value["State"]["Status"] != "running"
        or value["State"].get("Health", {}).get("Status") != "healthy"
    ):
        raise DockerCheckError("P6 container identity/health is invalid.")
    mounts = [m for m in value["Mounts"] if m["Destination"] == "/var/lib/postgresql"]
    if len(mounts) != 1 or mounts[0]["Type"] != "volume" or not mounts[0]["RW"]:
        raise DockerCheckError("P6 PostgreSQL 18 requires its retained named data volume.")
    ports = value["NetworkSettings"]["Ports"].get("5432/tcp") or []
    if len(ports) != 1 or ports[0]["HostIp"] != "127.0.0.1":
        raise DockerCheckError("P6 database must publish only to loopback.")
    return {
        "container_id": value["Id"],
        "image_id": value["Image"],
        "started_at": value["State"]["StartedAt"],
        "data_volume": mounts[0]["Name"],
        "host_port": int(ports[0]["HostPort"]),
        "status": "healthy",
    }


def database_facts(url):
    deadline = monotonic() + 30
    while True:
        try:
            with psycopg.connect(url, connect_timeout=2) as tx:
                version = tx.info.server_version
                facts = {
                    "server_version_num": version,
                    "settings": {
                        name: tx.execute("SHOW " + name).fetchone()[0]
                        for name in ("fsync", "synchronous_commit", "full_page_writes")
                    },
                }
                if not 180000 <= version < 190000 or set(facts["settings"].values()) != {"on"}:
                    raise DockerCheckError("PostgreSQL version/durability check failed.")
                return facts
        except psycopg.OperationalError:
            if monotonic() >= deadline:
                raise DockerCheckError(
                    "Docker PostgreSQL is unreachable from the test client."
                ) from None
            sleep(0.2)


def client_binding(out, password, container):
    # Docker can allocate another ephemeral host port on restart. Refresh every
    # client and the retained local connection file from inspected live state.
    url = f"postgresql://p6_test:{password}@127.0.0.1:{container['host_port']}/conversation_p6"
    (out / "local-database.json").write_text(json.dumps({"url": url}), encoding="utf-8")
    environment = {**os.environ, "P6_TEST_DATABASE_URL": url, "PYTHONIOENCODING": "utf-8"}
    return url, environment


def run(out=None):
    out = (out or ROOT / "artifacts/p6-docker" / str(uuid4())).resolve()
    out.mkdir(parents=True, exist_ok=False)
    project = "p6-" + uuid4().hex
    password = secrets.token_urlsafe(24)
    commands = Commands(out, secret=password)
    compose_file = out / "compose.json"
    base = ["docker", "compose", "--project-name", project, "--file", str(compose_file)]
    summary = {
        "checkpoint": "P6",
        "status": "INCOMPLETE",
        "project": project,
        "database": "Docker PostgreSQL 18",
        "image": POSTGRES_IMAGE,
        "event_outbox": "explicit test doubles; real shared gate NOT_RUN",
        "p7": "NOT_RUN",
    }
    try:
        summary["context"] = commands.run(["docker", "context", "show"])
        info = json.loads(
            commands.run(
                [
                    "docker",
                    "info",
                    "--format",
                    '{"version":"{{.ServerVersion}}","os":"{{.OSType}}"}',
                ]
            )
        )
        if info["os"] != "linux":
            raise DockerCheckError("P6 requires a Linux Docker engine/context.")
        summary["engine"] = info
        commands.run(["docker", "compose", "version"])
        commands.run(["docker", "pull", POSTGRES_IMAGE], timeout=300)
        compose_file.write_text(
            json.dumps(compose_document(project, password), indent=2), encoding="utf-8"
        )
        commands.run([*base, "config", "--quiet"])
        commands.run([*base, "up", "--detach", "--wait", "--wait-timeout", "60"])
        container_id = commands.run([*base, "ps", "--quiet", "postgres"])
        if not container_id or len(container_id.splitlines()) != 1:
            raise DockerCheckError("Exactly one P6 database container is required.")

        def inspect():
            # Select fields: full Docker inspect includes the generated password.
            raw = commands.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    '{"Id":{{json .Id}},"Image":{{json .Image}},'
                    '"Config":{"Labels":{{json .Config.Labels}}},"State":{{json .State}},'
                    '"Mounts":{{json .Mounts}},"NetworkSettings":{"Ports":'
                    "{{json .NetworkSettings.Ports}}}}",
                    container_id,
                ]
            )
            return validate_container(json.loads(raw), project)

        before = inspect()
        url, environment = client_binding(out, password, before)
        summary["container_before"] = before
        summary["database_before"] = database_facts(url)
        commands.run(
            [
                sys.executable,
                str(ROOT / "benchmarks/manual/verify_p6.py"),
                "--external-database",
                "--out",
                str(out / "checkpoint"),
            ],
            environment=environment,
            timeout=900,
        )
        commands.run([*base, "restart", "--timeout", "30", "postgres"])
        commands.run([*base, "up", "--detach", "--wait", "--wait-timeout", "60"])
        after = inspect()
        summary["container_after"] = after
        if (
            before["container_id"] != after["container_id"]
            or before["data_volume"] != after["data_volume"]
            or before["started_at"] == after["started_at"]
            or before["image_id"] != after["image_id"]
        ):
            raise DockerCheckError("Docker restart/retained-volume evidence does not match.")
        url, environment = client_binding(out, password, after)
        summary["database_after"] = database_facts(url)
        commands.run(
            [
                sys.executable,
                "-m",
                "benchmarks.manual.p6_smoke",
                "--out",
                str(out / "checkpoint/smoke"),
                "--resume",
            ],
            environment=environment,
        )
        summary["status"] = "PASS; real shared event gate incomplete"
        return 0
    except DockerCheckError as exc:
        summary["failure"] = str(exc)
        print(str(exc) + " No native fallback. Check Docker Desktop and docker-checks.json.")
        return 4
    finally:
        if "container_before" in summary:
            try:
                commands.run([*base, "logs", "--no-color", "postgres"])
            except DockerCheckError:
                summary["logs"] = "UNAVAILABLE"
        (out / "docker-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(out, flush=True)


if __name__ == "__main__":
    raise SystemExit(run())
