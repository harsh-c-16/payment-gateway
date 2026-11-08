"""Concrete runtime wiring with explicit connection/container doubles."""

import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from benchmarks.observation import Series
from infra import analytics_resources, analytics_runtime, audit_roles
from pipelines.ingestion.adapters import AnalyticsCallbacks
from projectctl.providers import DependencyError


def test_runtime_registers_real_callbacks_without_opening_connections(monkeypatch):
    monkeypatch.setattr(
        analytics_runtime, "pipeline_from_env", lambda: pytest.fail("eager startup")
    )
    bindings = analytics_runtime.runtime_bindings().validate()
    assert bindings.workloads["W-PIPE"].cleanup is not None
    assert bindings.quality.cleanup is not None
    assert all(
        callable(getattr(bindings.quality, name))
        for name in ("fresh_namespace", "seed_audit", "sources_factory", "collectors_factory")
    )


@pytest.mark.parametrize("readonly,writes", [("off", False), ("on", True)])
def test_audit_connection_refuses_writer_roles(monkeypatch, readonly, writes):
    monkeypatch.setenv("ANALYTICS_AUDIT_DATABASE_URL", "explicit-db-double")

    @contextmanager
    def connect(*args, **kwargs):
        yield SimpleNamespace(
            execute=lambda sql: SimpleNamespace(
                fetchone=lambda: (readonly if sql.startswith("SHOW") else writes,)
            )
        )

    monkeypatch.setattr(analytics_runtime.psycopg, "connect", connect)
    with pytest.raises(DependencyError):
        with analytics_runtime.read_connection("ANALYTICS_AUDIT_DATABASE_URL"):
            pytest.fail("writer role admitted")


def test_docker_counters_are_actual_values_and_missing_is_not_zero(monkeypatch):
    def command(args, **kwargs):
        if "inspect" in args:
            return json.dumps({"NanoCpus": 500000000, "Memory": 384 * 1024**2})
        return "usage_usec 2000000\nnr_periods 3\n1024\n2048\noom_kill 0\n"

    monkeypatch.setattr(analytics_resources.postgres, "command", command)
    reader = analytics_resources.DockerResources("a" * 64, "analytics-worker-0")
    readings = reader.read()
    assert [readings[s.key].value for s in reader.series] == [2, 1024, 2048]
    monkeypatch.setattr(analytics_resources.postgres, "command", lambda *args, **kwargs: "")
    assert reader.read() == {}


def test_resource_proof_rejects_mismatched_actual_allocation(monkeypatch):
    runtime = analytics_runtime.TeamAnalyticsRuntime()
    reader = SimpleNamespace(cores=1, memory=1024)
    monkeypatch.setattr(
        runtime,
        "resource_readers",
        lambda context: [SimpleNamespace(name="analytics-worker-0", read=reader)],
    )
    context = {
        "resource_profile": {
            "service_allocations": {"analytics": {"cpu_cores": 0.5, "memory_mib": 384}}
        }
    }
    with pytest.raises(DependencyError, match="Actual"):
        runtime.resource_proof(context)


def test_resource_proof_counts_api_worker_and_relay_together(monkeypatch):
    runtime = analytics_runtime.TeamAnalyticsRuntime()
    monkeypatch.setattr(
        runtime,
        "resource_readers",
        lambda context: [
            SimpleNamespace(
                name=f"resources-catalog-{index}",
                read=SimpleNamespace(
                    service="catalog",
                    cores=0.5,
                    memory=384 * 1024**2,
                ),
            )
            for index in range(3)
        ],
    )
    context = {
        "resource_profile": {
            "service_allocations": {"catalog": {"cpu_cores": 1.5, "memory_mib": 1152}}
        }
    }
    assert runtime.resource_proof(context) == context["resource_profile"]
    context["resource_profile"]["service_allocations"]["catalog"]["memory_mib"] = 384
    with pytest.raises(DependencyError, match="Actual"):
        runtime.resource_proof(context)


@pytest.mark.parametrize("existing", [False, True])
def test_audit_roles_grant_select_and_preserve_existing_secrets(monkeypatch, tmp_path, existing):
    monkeypatch.setattr(audit_roles.postgres, "RUNTIME", tmp_path)
    (tmp_path / "secrets").mkdir()
    monkeypatch.setattr(audit_roles.postgres, "credentials", lambda: {"admin": "admin-double"})
    if existing:
        for service in audit_roles.SERVICES:
            (tmp_path / "secrets" / f"{service}_audit_password").write_text("x" * 43)
    statements = []

    @contextmanager
    def connect(**kwargs):
        def execute(query, parameters=None):
            text = query if isinstance(query, str) else query.as_string()
            statements.append(text)
            return SimpleNamespace(fetchone=lambda: (False,) * 6 if existing else None)

        yield SimpleNamespace(execute=execute)

    monkeypatch.setattr(audit_roles.psycopg, "connect", connect)
    audit_roles.provision()
    assert sum("GRANT SELECT ON ALL TABLES" in s for s in statements) == 3
    assert sum("ALTER DEFAULT PRIVILEGES" in s for s in statements) == 3
    assert sum("default_transaction_read_only=on" in s for s in statements) == 3
    assert sum("CREATE ROLE" in s for s in statements) == (0 if existing else 3)
    assert not any("GRANT INSERT" in s or "GRANT ALL" in s for s in statements)
    if existing:
        assert all(
            audit_roles.audit_password(service) == "x" * 43 for service in audit_roles.SERVICES
        )
        assert not any("PASSWORD" in s for s in statements)
    assert (tmp_path / "audit.env").is_file()


def test_existing_audit_role_without_its_secret_is_not_rotated(monkeypatch, tmp_path):
    monkeypatch.setattr(audit_roles.postgres, "RUNTIME", tmp_path)
    (tmp_path / "secrets").mkdir()
    monkeypatch.setattr(audit_roles.postgres, "credentials", lambda: {"admin": "admin-double"})

    @contextmanager
    def connect(**kwargs):
        yield SimpleNamespace(execute=lambda *args: SimpleNamespace(fetchone=lambda: (False,) * 6))

    monkeypatch.setattr(audit_roles.psycopg, "connect", connect)
    with pytest.raises(audit_roles.postgres.SetupError, match="original"):
        audit_roles.provision()
    assert not list((tmp_path / "secrets").iterdir())


@pytest.mark.parametrize("grouped", [False, True])
def test_concrete_metrics_and_resources_have_distinct_collector_names(
    monkeypatch, tmp_path, grouped
):
    context = {
        "namespace": "bench-resources",
        "run_id": "fixture",
        "workload_id": "W-PIPE",
        "variant_id": "B0",
        "resource_profile": {"services": ["analytics", "kafka"]},
    }
    monkeypatch.delenv("PROJECTCTL_SUT_CONTAINERS", raising=False)
    if grouped:
        monkeypatch.setenv("PROJECTCTL_SUT_CONTAINERS", json.dumps({"kafka": ["c" * 64, "d" * 64]}))
    deployment = SimpleNamespace(
        services=("m4-bench-resources-worker-0", "m4-bench-resources-api"),
        workers=("m4-bench-resources-worker-0",),
        command=lambda *args: {"kafka": "c", "m4-bench-resources-api": "b"}.get(args[-1], "a") * 64,
    )
    monkeypatch.setattr(
        analytics_resources.postgres,
        "command",
        lambda *args, **kwargs: json.dumps({"NanoCpus": 500000000, "Memory": 384 * 1024**2}),
    )
    runtime = analytics_runtime.TeamAnalyticsRuntime()
    monkeypatch.setattr(
        runtime,
        "runner",
        lambda context: SimpleNamespace(
            for_run=lambda context: SimpleNamespace(deployment=deployment)
        ),
    )
    callbacks = AnalyticsCallbacks(None, lambda: None, deployment, bootstrap="broker-double")
    monkeypatch.setattr(
        callbacks,
        "lag",
        lambda context: SimpleNamespace(
            series=(Series("kafka_lag_records", "kafka", "records"),), mode="real"
        ),
    )
    # Construction validates collector identities without scraping or opening Kafka/SQL.
    observation = callbacks.observer_factory(resource_factory=runtime.resource_readers)(
        context, tmp_path, "test"
    )
    names = [item.name for item in observation.config.collectors]
    assert "analytics-worker-0" in names and "resources-analytics-worker-0" in names
    assert "kafka" in names
    assert ("resources-kafka-0" if grouped else "resources-kafka") in names
