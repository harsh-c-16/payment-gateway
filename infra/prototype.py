"""Local prototype lifecycle through projectctl; no operational migrations or resets."""

import json
import os
import secrets
import shutil
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import psycopg
import yaml
from psycopg import sql
from pydantic import TypeAdapter

from infra import postgres, streaming
from infra.startup import StartupChecks
from pipelines.ingestion.receipts import migrate_analytics
from projectctl.models import ExitCode
from projectctl.providers import ProviderResult
from shared.contracts.common import Identifier

RUNTIME = postgres.ROOT / "artifacts/infra/prototype-local"
FILES = (
    "compose.yaml",
    "compose.streaming.yaml",
    "compose.catalog.yaml",
    "compose.analytics.yaml",
    "compose.prototype.yaml",
)
APPS = (
    "catalog",
    "catalog-worker",
    "analytics",
    "analytics-worker",
    "conversation",
    "orders",
    "inventory",
    "payments",
    "prototype-relays",
)
BASE = ("postgres", "kafka", "schema-registry")
TABLES = {
    "conversation": ("sessions", "carts", "confirmations", "intent_attempts", "outbox"),
    "catalog": ("products", "quotes", "stock_projection", "outbox"),
    "orders": ("orders", "order_items", "saga_jobs", "operation_keys", "fault_barriers", "outbox"),
    "inventory": ("inventory", "inventory_seeds", "reservations", "fault_barriers", "outbox"),
    "payments": ("payment_orders", "payment_attempts", "ledger_entries", "outbox"),
}


def prepare(run_id):
    """Keep local credentials stable; only public run identity goes in context.json."""
    postgres.prepare()
    RUNTIME.mkdir(parents=True, exist_ok=True)
    path = RUNTIME / "context.json"
    previous = json.loads(path.read_text()) if path.exists() else {}
    namespace = os.environ.get("RUN_NAMESPACE", previous.get("RUN_NAMESPACE", "dev"))
    streaming.topic_names(namespace)
    revision = TypeAdapter(Identifier).validate_python(
        os.environ.get(
            "CATALOG_DATASET_REVISION",
            previous.get("CATALOG_DATASET_REVISION", "flipkart-v1-3a401f32ca99379f8298ce42"),
        )
    )
    context = {
        "RUN_NAMESPACE": namespace,
        "RUN_ID": previous.get("RUN_ID", run_id),
        "CODE_COMMIT": postgres.command(["git", "rev-parse", "HEAD"]),
        "CATALOG_DATASET_REVISION": revision,
    }
    if previous and previous["RUN_NAMESPACE"] != namespace:
        raise postgres.SetupError("Prototype namespace is retained; use its original RUN_NAMESPACE")
    token = RUNTIME / "internal_token"
    if previous and not token.exists():
        raise postgres.SetupError("Restore the original private prototype internal_token")
    if not token.exists():
        with token.open("x", encoding="ascii") as stream:
            stream.write(secrets.token_urlsafe(32))
        token.chmod(0o600)
    path.write_text(json.dumps(context, indent=2), encoding="utf-8")
    for name, host in ((".env", True), (".container.env", False)):
        values = environment(host=host)
        env_file = RUNTIME / name
        env_file.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
        env_file.chmod(0o600)


def environment(*, host=False):
    context = json.loads((RUNTIME / "context.json").read_text())
    token = (RUNTIME / "internal_token").read_text(encoding="ascii")
    if len(token) < 32 or not token.replace("-", "").replace("_", "").isalnum():
        raise postgres.SetupError("Restore the original private prototype internal_token")
    values = postgres.credentials()
    return {
        **context,
        **shopping_environment(),
        "INTERNAL_API_TOKEN": token,
        "POSTGRES_SECRETS_DIR": (postgres.RUNTIME / "secrets").as_posix(),
        "EVENT_SCHEMA_CACHE_PATH": streaming.SCHEMA_CACHE.as_posix(),
        "KAFKA_BOOTSTRAP_SERVERS": streaming.BOOTSTRAP if host else "kafka:9092",
        **{
            name.upper() + "_DATABASE_URL": postgres.database_url(name, values).replace(
                "@127.0.0.1:", "@postgres:" if not host else "@127.0.0.1:"
            )
            for name in postgres.SERVICES
        },
    }


def shopping_environment():
    """Read only the private M1 model settings; never include them in public context/evidence."""
    names = {"SHOPPING_LLM_ENABLED", "SHOPPING_LLM_MODEL", "GEMINI_API_KEY"}
    values = {k: os.environ[k] for k in names if k in os.environ}
    path = RUNTIME / "shopping-llm.env"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            name, separator, value = line.partition("=")
            if not separator or name not in names or not value or any(c.isspace() for c in value):
                raise postgres.SetupError("Invalid private shopping-llm.env entry")
            values[name] = value
    return values


def compose(*arguments, semantic=None):
    from infra import retrieval

    semantic = retrieval.enabled() if semantic is None else semantic
    files = FILES + (("compose.retrieval.yaml",) if semantic else ())
    return postgres.command(
        [
            "docker",
            "compose",
            "--project-name",
            postgres.PROJECT,
            *[arg for name in files for arg in ("--file", str(postgres.ROOT / "infra" / name))],
            *arguments,
        ],
        environment={**os.environ, **environment()},
        timeout=1800
        if "pipelines.catalog.embeddings" in arguments
        else 600
        if arguments[0] in {"up", "run"}
        else 180,
    )


def allocations():
    from infra import retrieval

    infrastructure = json.loads((postgres.ROOT / "infra/streaming-profile.json").read_text())
    overlay = yaml.safe_load((postgres.ROOT / "infra/compose.prototype.yaml").read_text())
    if retrieval.enabled():
        semantic = yaml.safe_load((postgres.ROOT / "infra/compose.retrieval.yaml").read_text())
        overlay["services"]["catalog"]["mem_limit"] = semantic["services"]["catalog"]["mem_limit"]
    return {
        **infrastructure["services"],
        **{
            name: {
                "memory_mib": int(overlay["services"][name]["mem_limit"][:-1]),
                "cpu_cores": overlay["services"][name]["cpus"],
            }
            for name in APPS
        },
    }


def budget():
    limits = allocations()
    memory = int(postgres.command(["docker", "info", "--format", "{{.MemTotal}} "]))
    cpus = int(postgres.command(["docker", "info", "--format", "{{.NCPU}}"]))
    required = sum(row["memory_mib"] for row in limits.values())
    if memory < (required + 256) * 1024 * 1024:
        raise postgres.SetupError(f"Prototype needs {required} MiB plus 256 MiB Docker headroom")
    if cpus < sum(row["cpu_cores"] for row in limits.values()):
        raise postgres.SetupError("Docker CPUs are below the prototype allocations")
    running = postgres.command(
        [
            "docker",
            "ps",
            "--filter",
            "label=com.docker.compose.project=" + postgres.PROJECT,
            "--format",
            '{{.Label "com.docker.compose.service"}}',
        ]
    )
    if set(running.splitlines()) - set(BASE + APPS):
        raise postgres.SetupError(
            "Stop this project's setup/benchmark containers before prototype startup"
        )
    return {
        "docker_memory_bytes": memory,
        "docker_cpus": cpus,
        "container_limits_mib": required,
        "headroom_mib": 256,
    }


def prerequisites(*, migrate=False):
    """Only analytics is migrated here; other owners' schemas are checked read-only."""
    values = postgres.credentials()
    unavailable = []
    for name, tables in TABLES.items():
        with psycopg.connect(postgres.database_url(name, values), connect_timeout=3) as tx:
            tx.execute("SET TRANSACTION READ ONLY")
            tx.execute("SET LOCAL statement_timeout='5000ms'")
            missing = [
                table
                for table in tables
                if tx.execute("SELECT to_regclass(%s)", ("public." + table,)).fetchone()[0] is None
            ]
            if missing:
                unavailable.append(
                    name + " owner migrations required; missing tables: " + ", ".join(missing)
                )
            else:
                if (
                    name == "conversation"
                    and not tx.execute(
                        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                        "WHERE table_schema='public' AND table_name='sessions' "
                        "AND column_name='shopping_context')"
                    ).fetchone()[0]
                ):
                    unavailable.append(
                        "conversation migration 005 required; run services.conversation.database "
                        "to add saved shopping_context"
                    )
                tx.execute(
                    sql.SQL("SELECT event_id,published_at FROM {} LIMIT 0").format(
                        sql.Identifier("outbox")
                    )
                )
    if unavailable:
        raise postgres.SetupError("; ".join(unavailable))
    if migrate:
        with (
            psycopg.connect(postgres.database_url("analytics", values), connect_timeout=3) as tx,
            tx.transaction(),
        ):
            migrate_analytics(tx)


def build_image():
    with TemporaryDirectory(prefix="image-", dir=RUNTIME) as directory:
        directory = Path(directory)
        for source in ("infra/storage.Dockerfile", "pyproject.toml", "uv.lock"):
            shutil.copyfile(postgres.ROOT / source, directory / Path(source).name)
        postgres.command(
            [
                "docker",
                "build",
                "--tag",
                "group3-m04-storage:local",
                "--file",
                str(directory / "storage.Dockerfile"),
                str(directory),
            ],
            timeout=600,
        )
    from infra import retrieval

    if retrieval.enabled():
        retrieval.build_image()


def verify():
    ids = compose("ps", "--all", "--quiet", *BASE, *APPS).splitlines()
    if len(ids) != len(BASE) + len(APPS):
        raise postgres.SetupError("Every prototype container must exist")
    # Never inspect Config.Env: it contains the private service credentials/token.
    raw = postgres.command(
        [
            "docker",
            "inspect",
            "--format",
            '{"service":{{json (index .Config.Labels "com.docker.compose.service")}},'
            '"state":{{json .State}},"memory":{{json .HostConfig.Memory}},'
            '"cpu":{{json .HostConfig.NanoCpus}}}',
            *ids,
        ]
    )
    facts = {}
    for line in raw.splitlines():
        row = json.loads(line)
        name, state = row["service"], row["state"]
        expected = allocations().get(name)
        if (
            not expected
            or name in facts
            or not state["Running"]
            or state["OOMKilled"]
            or state.get("Health", {}).get("Status") != "healthy"
            or row["memory"] != expected["memory_mib"] * 1024 * 1024
            or row["cpu"] != round(expected["cpu_cores"] * 1_000_000_000)
        ):
            raise postgres.SetupError("Prototype health/resource mismatch: " + name)
        facts[name] = {"health": "healthy", "memory_bytes": row["memory"], "nano_cpus": row["cpu"]}
    if set(facts) != set(BASE + APPS):
        raise postgres.SetupError("Prototype container mapping incomplete")
    return facts


def start_applications(check):
    # Bound cold imports; providers become healthy before clients and individual workers.
    for stage, services in (
        ("domain-apis", ("catalog", "inventory", "payments")),
        ("client-apis", ("orders", "conversation", "analytics")),
        ("stock-worker", ("catalog-worker",)),
        ("analytics-worker", ("analytics-worker",)),
        ("outbox-relays", ("prototype-relays",)),
    ):
        check(
            "start-" + stage,
            lambda services=services: compose(
                "up", "--detach", "--no-deps", "--wait", "--wait-timeout", "240", *services
            ),
        )


def adapter(invocation):
    if invocation.arguments.get("profile", "prototype-local") != "prototype-local":
        return ProviderResult(ExitCode.BAD_INPUT, ("Use --profile prototype-local",), "real")
    check = StartupChecks(RUNTIME / "checks" / invocation.run_id / "startup.jsonl")
    try:
        check("docker-engine", postgres.check_engine)
        if invocation.action == "env down":
            check("stop-applications", lambda: compose("stop", "--timeout", "40", *APPS))
            check(
                "stop-infrastructure", lambda: streaming.compose("stop", "--timeout", "40", *BASE)
            )
            return ProviderResult(
                ExitCode.COMPLETED, ("Prototype stopped; all data retained",), "real"
            )
        resources = check("development-budget", budget)
        if invocation.action == "env up":
            check("private-bindings", lambda: prepare(invocation.run_id))
            check("stop-retained-applications", lambda: compose("stop", "--timeout", "40", *APPS))
            base = streaming.adapter(replace(invocation, arguments={"profile": "streaming-local"}))
            if base.code != ExitCode.COMPLETED:
                return base
            check("schema-prerequisites", lambda: prerequisites(migrate=True))
            check(
                "namespace-topics",
                lambda: streaming.provision_topics(environment()["RUN_NAMESPACE"]),
                retry=True,
            )
            check("application-image", build_image)
            check("compose-config", lambda: compose("config", "--quiet"))
            start_applications(check)
        else:
            check("schema-prerequisites", prerequisites)
        facts = check("prototype-verification", verify)
        out = check.path.with_name("prototype.json")
        out.write_text(
            json.dumps(
                {
                    "profile": "prototype-local",
                    "resources": resources,
                    "containers": facts,
                    "context": json.loads((RUNTIME / "context.json").read_text()),
                    "source_dirty": bool(postgres.command(["git", "status", "--porcelain"])),
                    "checkout_acceptance": "NOT_RUN",
                    "evaluation_readiness": "NOT_RUN",
                },
                indent=2,
            )
        )
        return ProviderResult(
            ExitCode.COMPLETED,
            (
                "Prototype processes ready; checkout/data acceptance remains separate",
                "Evidence: " + postgres.evidence_path(out),
            ),
            "real",
        )
    except Exception as exc:
        reason = str(exc) if isinstance(exc, postgres.SetupError) else type(exc).__name__
        return ProviderResult(
            ExitCode.DEPENDENCY_FAILURE,
            (reason, "Retained startup diagnostics: " + postgres.evidence_path(check.path)),
            "real",
        )


def register(registry):
    from pipelines.catalog.adapter import register as register_catalog
    from services.inventory.adapter import register as register_inventory

    for action in ("env up", "env verify", "env down"):
        registry.register(action, adapter)
    register_catalog(registry)
    register_inventory(registry)
