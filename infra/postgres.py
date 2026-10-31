"""PostgreSQL-only projectctl providers; no service migrations or fake readiness."""

import json
import os
import re
import secrets
import subprocess
from pathlib import Path

import psycopg

from projectctl.models import ExitCode
from projectctl.providers import ProviderResult

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "artifacts/infra/postgres-local"
SERVICES = ("conversation", "catalog", "orders", "inventory", "payments", "analytics")
PROFILE = "postgres-local"
PROJECT = "group3-postgres-local"
COMPOSE = ROOT / "infra/compose.yaml"


class SetupError(RuntimeError):
    pass


def credentials(*, create=False):
    directory = RUNTIME / "secrets"
    if not directory.exists() and create:
        directory.mkdir(parents=True, mode=0o700)
        for name in ("admin", *SERVICES):
            path = directory / f"{name}_password"
            with path.open("x", encoding="ascii") as stream:
                stream.write(secrets.token_urlsafe(32))
            path.chmod(0o600)
    values = {}
    for name in ("admin", *SERVICES):
        path = directory / f"{name}_password"
        if not path.is_file():
            raise SetupError(
                "Credentials missing/incomplete; restore them, never reset the volume."
            )
        value = path.read_text(encoding="ascii")
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", value):
            raise SetupError("Invalid local credential file; restore the original credentials.")
        values[name] = value
    return values


def database_url(service, values):
    return f"postgresql://{service}_user:{values[service]}@127.0.0.1:5432/{service}_db"


def prepare():
    values = credentials(create=True)
    client_file = RUNTIME / ".env"
    client_file.write_text(
        "".join(
            f"{service.upper()}_DATABASE_URL={database_url(service, values)}\n"
            for service in SERVICES
        ),
        encoding="utf-8",
    )
    client_file.chmod(0o600)


def compose(*arguments):
    environment = {**os.environ, "POSTGRES_SECRETS_DIR": (RUNTIME / "secrets").as_posix()}
    return command(
        ["docker", "compose", "--project-name", PROJECT, "--file", str(COMPOSE), *arguments],
        environment=environment,
    )


def command(arguments, *, environment=None, timeout=180):
    try:
        completed = subprocess.run(
            arguments,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}),
        )
    except subprocess.TimeoutExpired:
        raise SetupError(
            "Docker command timed out; check container state before retrying."
        ) from None
    except OSError:
        raise SetupError("Docker unavailable; install and start Docker Desktop.") from None
    if completed.returncode:
        # Docker output can contain initialization SQL; keep credentials out of evidence.
        raise SetupError(f"Docker command failed (exit {completed.returncode}): {arguments[1:]}.")
    return completed.stdout.strip()


def check_engine():
    if command(["docker", "info", "--format", "{{.OSType}}"]) != "linux":
        raise SetupError("A running Linux Docker engine is required.")
    command(["docker", "compose", "version"])


def verify(*, memory_mib=2048, cpu_cores=0.75):
    check_engine()
    values = credentials()
    container = compose("ps", "--quiet", "postgres")
    if not container or len(container.splitlines()) != 1:
        raise SetupError("Exactly one PostgreSQL container must be running.")
    state = json.loads(
        command(
            [
                "docker",
                "inspect",
                "--format",
                '{"health":{{json .State.Health.Status}},"mounts":{{json .Mounts}},'
                '"ports":{{json .NetworkSettings.Ports}},"memory":{{json .HostConfig.Memory}},'
                '"cpu":{{json .HostConfig.NanoCpus}},"image_id":{{json .Image}},'
                '"image":{{json .Config.Image}}}',
                container,
            ]
        )
    )
    lock = json.loads((ROOT / "infra/images.lock.json").read_text(encoding="utf-8"))
    mounts = [item for item in state["mounts"] if item["Destination"] == "/var/lib/postgresql"]
    ports = state["ports"].get("5432/tcp")
    if (
        state["health"] != "healthy"
        or len(mounts) != 1
        or mounts[0]["Type"] != "volume"
        or not mounts[0]["RW"]
        or ports != [{"HostIp": "127.0.0.1", "HostPort": "5432"}]
        or state["memory"] != memory_mib * 1024 * 1024
        or state["cpu"] != int(cpu_cores * 1000000000)
        or state["image"] != lock["postgres"]["image"]
    ):
        raise SetupError("Container health, retained volume, loopback port or limits differ.")
    observations = {}
    for service in SERVICES:
        with psycopg.connect(database_url(service, values), connect_timeout=3) as tx:
            if not 180000 <= tx.info.server_version < 190000:
                raise SetupError("PostgreSQL 18 is required.")
            settings = {
                name: tx.execute("SHOW " + name).fetchone()[0]
                for name in ("fsync", "synchronous_commit", "full_page_writes")
            }
            if set(settings.values()) != {"on"}:
                raise SetupError("PostgreSQL durability settings must remain enabled.")
            role = tx.execute(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
                "FROM pg_roles WHERE rolname=current_user"
            ).fetchone()
            if role != (False, False, False, False, False):
                raise SetupError("A service role has administrative privileges.")
            allowed = tx.execute(
                "SELECT datname FROM pg_database WHERE has_database_privilege("
                "current_user, oid, 'CONNECT') AND datallowconn ORDER BY datname"
            ).fetchall()
            if allowed != [(f"{service}_db",)]:
                raise SetupError("Service database isolation failed.")
            tx.execute("CREATE TEMP TABLE m01_probe (value integer)")
            tx.execute("INSERT INTO m01_probe VALUES (1)")
            if tx.execute("SELECT value FROM m01_probe").fetchone() != (1,):
                raise SetupError("Service database write/read probe failed.")
            if service == "catalog":
                version = tx.execute(
                    "SELECT extversion FROM pg_extension WHERE extname='vector'"
                ).fetchone()
                if version != ("0.8.1",):
                    raise SetupError("Catalogue pgvector extension must be 0.8.1.")
            observations[service] = {"server_version_num": tx.info.server_version, **settings}
    return {
        "profile": PROFILE,
        "scope": "PostgreSQL checks only; full G0 NOT_RUN",
        "image_id": state["image_id"],
        "data_volume": mounts[0]["Name"],
        "databases": observations,
    }


def adapter(invocation):
    if invocation.arguments.get("profile", PROFILE) != PROFILE:
        return ProviderResult(
            ExitCode.BAD_INPUT, ("M01a supports only --profile postgres-local.",), "real"
        )
    try:
        check_engine()
        if invocation.action == "env up":
            prepare()
            compose("config", "--quiet")
            compose("up", "--detach", "--wait", "--wait-timeout", "90", "postgres")
        if invocation.action == "env down":
            credentials()
            compose("down", "--timeout", "30")
            return ProviderResult(
                ExitCode.COMPLETED, ("Stopped; database volume retained.",), "real"
            )
        observations = verify()
        out = RUNTIME / "checks" / invocation.run_id
        out.mkdir(parents=True, exist_ok=False)
        (out / "postgres.json").write_text(json.dumps(observations, indent=2), encoding="utf-8")
        return ProviderResult(
            ExitCode.COMPLETED,
            (
                "PostgreSQL-only verification passed; full environment NOT_RUN.",
                f"Evidence: {out.relative_to(ROOT).as_posix()}/postgres.json",
            ),
            "real",
        )
    except (SetupError, psycopg.Error) as exc:
        reason = (
            str(exc) if isinstance(exc, SetupError) else "Database unavailable or check failed."
        )
        return ProviderResult(ExitCode.DEPENDENCY_FAILURE, (reason,), "real")


def register(registry):
    for action in ("env up", "env verify", "env down"):
        registry.register(action, adapter)
