"""Prototype deployment checks with explicit Docker/SQL doubles, never a live pass."""

import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
import yaml

from infra import postgres, prototype, prototype_relays
from projectctl.models import ExitCode
from projectctl.providers import Invocation, ProviderRegistry


@pytest.fixture
def private_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(prototype, "RUNTIME", tmp_path / "prototype")
    monkeypatch.setattr(postgres, "RUNTIME", tmp_path / "postgres")
    monkeypatch.setattr(postgres, "command", lambda *a, **kw: "a" * 40)
    monkeypatch.delenv("RUN_NAMESPACE", raising=False)
    monkeypatch.delenv("CATALOG_DATASET_REVISION", raising=False)


def test_bindings_keep_credentials_namespace_and_run_identity(private_runtime):
    prototype.prepare("first-run")
    original = prototype.environment(host=True)
    prototype.prepare("second-run")
    assert prototype.environment(host=True) == original
    assert original["RUN_NAMESPACE"] == "dev" and original["RUN_ID"] == "first-run"
    assert "@127.0.0.1:" in original["ORDERS_DATABASE_URL"]
    assert "@postgres:" in prototype.environment()["ORDERS_DATABASE_URL"]
    public = (prototype.RUNTIME / "context.json").read_text()
    assert original["INTERNAL_API_TOKEN"] not in public
    assert original["ORDERS_DATABASE_URL"] not in public


def test_missing_token_is_not_silently_rotated(private_runtime):
    prototype.prepare("first-run")
    token = prototype.RUNTIME / "internal_token"
    token.unlink()
    with pytest.raises(postgres.SetupError, match="Restore"):
        prototype.prepare("second-run")
    assert not token.exists()


def test_namespace_change_requires_original_binding(private_runtime, monkeypatch):
    prototype.prepare("first-run")
    monkeypatch.setenv("RUN_NAMESPACE", "bench-other")
    with pytest.raises(postgres.SetupError, match="original RUN_NAMESPACE"):
        prototype.prepare("second-run")
    assert prototype.environment()["RUN_NAMESPACE"] == "dev"


def test_development_budget_matches_overlay_and_counts_all_relays():
    limits = prototype.allocations()
    assert set(limits) == set(prototype.BASE + prototype.APPS)
    assert sum(row["memory_mib"] for row in limits.values()) == 3584
    assert sum(row["cpu_cores"] for row in limits.values()) == 8
    overlay = yaml.safe_load((postgres.ROOT / "infra/compose.prototype.yaml").read_text())
    for service in prototype_relays.SERVICES:
        assert (
            service.upper() + "_DATABASE_URL"
            in overlay["services"]["prototype-relays"]["environment"]
        )
    assert "catalog-relay" not in prototype.APPS
    assert overlay["services"]["prototype-setup"]["mem_limit"] == "768m"
    assert (
        "lakehouse_data:/app/prototype-volume" in overlay["services"]["prototype-setup"]["volumes"]
    )
    assert "../data/raw:/app/data/raw:ro" in overlay["services"]["prototype-setup"]["volumes"]
    for name in ("analytics", "analytics-worker"):
        assert overlay["services"][name]["environment"]["SINK_BATCH_MAX_ROWS"] == "100"
    for service in prototype.APPS:
        assert "healthcheck" in overlay["services"][service]
        environment = overlay["services"][service]["environment"]
        assert environment["BENCHMARK_MODE"] == environment["FAULT_INJECTION_ENABLED"] == "false"
        assert environment["ASSISTANT_MODE"] == "fixed"


@pytest.mark.parametrize("available,passed", [(3840, True), (3839, False)])
def test_memory_headroom_is_required_before_start(monkeypatch, available, passed):
    monkeypatch.setattr(
        postgres,
        "command",
        lambda args: (
            "" if "ps" in args else str(available * 1024 * 1024 if "{{.MemTotal}} " in args else 8)
        ),
    )
    if passed:
        assert prototype.budget()["container_limits_mib"] == 3584
    else:
        with pytest.raises(postgres.SetupError, match="headroom"):
            prototype.budget()


@pytest.mark.parametrize("cpus,running", [(5, ""), (8, "prototype-setup")])
def test_cpu_shortage_and_competing_setup_are_rejected(monkeypatch, cpus, running):
    def command(args):
        if "ps" in args:
            return running
        return str(4040855552 if "{{.MemTotal}} " in args else cpus)

    monkeypatch.setattr(postgres, "command", command)
    with pytest.raises(postgres.SetupError):
        prototype.budget()


def test_missing_owner_schema_fails_read_only_without_running_migrations(
    private_runtime, monkeypatch
):
    prototype.prepare("fixture")
    queries = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, query, parameters=()):
            queries.append(str(query))
            return SimpleNamespace(fetchone=lambda: (None,))

    monkeypatch.setattr(prototype.psycopg, "connect", lambda *a, **kw: Connection())
    monkeypatch.setattr(prototype, "migrate_analytics", lambda tx: pytest.fail("migration ran"))
    with pytest.raises(postgres.SetupError, match="conversation owner migrations required"):
        prototype.prerequisites(migrate=True)
    assert queries[0] == "SET TRANSACTION READ ONLY"
    assert not any("CREATE" in query or "INSERT" in query for query in queries)


def test_analytics_migration_receives_active_caller_transaction(private_runtime, monkeypatch):
    prototype.prepare("fixture")
    migrated = []

    class Connection:
        active = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, *args):
            return SimpleNamespace(fetchone=lambda: ("present-double",))

        @contextmanager
        def transaction(self):
            self.active = True
            try:
                yield
            finally:
                self.active = False

    def migrate(connection):
        assert connection.active
        migrated.append(True)

    monkeypatch.setattr(prototype.psycopg, "connect", lambda *a, **kw: Connection())
    monkeypatch.setattr(prototype, "migrate_analytics", migrate)
    prototype.prerequisites(migrate=True)
    assert migrated == [True]


@pytest.mark.parametrize("broken", [None, "oom", "health", "allocation", "duplicate"])
def test_verification_requires_every_healthy_correctly_allocated_container(monkeypatch, broken):
    rows = [
        {
            "service": name,
            "state": {
                "Running": True,
                "OOMKilled": False,
                "Health": {"Status": "healthy", "Log": [{"Output": "private-double"}]},
            },
            "memory": limit["memory_mib"] * 1024 * 1024,
            "cpu": round(limit["cpu_cores"] * 1_000_000_000),
        }
        for name, limit in prototype.allocations().items()
    ]
    if broken == "oom":
        rows[0]["state"]["OOMKilled"] = True
    if broken == "health":
        rows[0]["state"]["Health"]["Status"] = "unhealthy"
    if broken == "allocation":
        rows[-1]["memory"] += 1024
    if broken == "duplicate":
        rows[-1] = rows[0]
    monkeypatch.setattr(
        prototype, "compose", lambda *a: "\n".join(str(i) for i in range(len(rows)))
    )
    monkeypatch.setattr(postgres, "command", lambda args: "\n".join(json.dumps(r) for r in rows))
    if broken:
        with pytest.raises(postgres.SetupError, match="mismatch"):
            prototype.verify()
    else:
        facts = prototype.verify()
        assert set(facts) == set(prototype.BASE + prototype.APPS)
        assert "private-double" not in json.dumps(facts)


def test_stop_is_explicit_and_retains_every_volume(monkeypatch, private_runtime):
    calls = []
    monkeypatch.setattr(postgres, "check_engine", lambda: None)
    monkeypatch.setattr(prototype, "compose", lambda *a: calls.append(a))
    monkeypatch.setattr(prototype.streaming, "compose", lambda *a: calls.append(a))
    result = prototype.adapter(Invocation("env down", {}, None, "fixture", "dev"))
    assert result.code == ExitCode.COMPLETED
    assert calls == [
        ("stop", "--timeout", "40", *prototype.APPS),
        ("stop", "--timeout", "40", *prototype.BASE),
    ]


@pytest.mark.parametrize("fail_service", [None, "orders"])
def test_relay_startup_unwinds_all_open_resources(monkeypatch, tmp_path, fail_service):
    calls = []
    ready = tmp_path / "ready"
    monkeypatch.setattr(prototype_relays, "READY", ready)
    monkeypatch.setattr(prototype_relays.signal, "signal", lambda *a: None)
    monkeypatch.setattr(prototype_relays.SchemaCache, "load", lambda *a: "cache-double")
    for service in prototype_relays.SERVICES:
        monkeypatch.setenv(service.upper() + "_DATABASE_URL", "url-double")
    monkeypatch.setenv("EVENT_SCHEMA_CACHE_PATH", "cache-double")
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "broker-double")

    class Stop:
        stopped = False

        def is_set(self):
            return self.stopped

        def wait(self, seconds):
            assert ready.exists()
            self.stopped = True

    monkeypatch.setattr(prototype_relays, "Event", Stop)

    @contextmanager
    def relay(url, codec, bootstrap, *, service_name):
        if service_name == fail_service:
            raise RuntimeError("explicit failure double")
        assert codec.source_service == service_name
        calls.append(("open", service_name))
        try:
            yield SimpleNamespace(
                _thread=SimpleNamespace(is_alive=lambda: True),
                _stop=SimpleNamespace(set=lambda: calls.append(("stop", service_name))),
            )
        finally:
            calls.append(("close", service_name))

    monkeypatch.setattr(prototype_relays, "catalog_relay", relay)
    assert prototype_relays.main() == (4 if fail_service else 0)
    opened = [name for action, name in calls if action == "open"]
    closed = [name for action, name in calls if action == "close"]
    assert opened == list(reversed(closed)) and not ready.exists()
    assert {name for action, name in calls if action == "stop"} == set(opened)
    assert max(i for i, row in enumerate(calls) if row[0] == "stop") < min(
        i for i, row in enumerate(calls) if row[0] == "close"
    )


def test_registration_uses_existing_owner_data_adapters():
    registry = ProviderRegistry()
    prototype.register(registry)
    for action in (
        "env up",
        "env verify",
        "env down",
        "catalog import",
        "inventory seed",
        "projection wait",
    ):
        assert registry.missing(action) is None
    assert registry.missing("env reset") is not None
    assert registry.missing("db migrate") is not None
