"""Lifecycle/result doubles; no service startup, reset or measured evaluation."""

import asyncio
import json
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest

from benchmarks.composition import OwnerCallbacks
from projectctl.artifacts import content_hash, file_hash
from projectctl.config import ROOT
from projectctl.evaluation_packet import process_profile, verify, worker_processes
from projectctl.models import ExitCode
from projectctl.providers import DependencyError, Invocation, ProviderResult
from projectctl.runtime import RuntimeBindings, merge_runtimes
from projectctl.setup import DATABASE_OWNERS, ResetCoordinator, ResetParticipant
from projectctl.team_runtime import runtime_bindings


def test_team_composes_m4_and_independent_operational_runtime_lazily(monkeypatch):
    async def forbidden(*args):
        pytest.fail("registration started a provider")

    callbacks = OwnerCallbacks(fresh_namespace=forbidden)
    extra = RuntimeBindings(
        workloads={"W-CHECKOUT": callbacks}, migrations={"orders": lambda _: None}
    )
    monkeypatch.setitem(
        sys.modules,
        "explicit_owner_runtime_double",
        SimpleNamespace(runtime_bindings=lambda: extra),
    )
    monkeypatch.setenv("PROJECTCTL_OWNER_RUNTIME_MODULES", "explicit_owner_runtime_double")
    team = runtime_bindings()
    assert team.workloads["W-CHECKOUT"] is callbacks
    assert team.workloads["W-PIPE"].audit is not None and team.quality.sources_factory is not None
    assert set(team.migrations) == {"conversation", "catalog", "orders", "analytics"}
    assert set(team.setup_actions) == {"db migrate", "env reset"}
    result = team.setup_actions["db migrate"](None)
    assert result.code == ExitCode.DEPENDENCY_FAILURE  # Missing owners block every write.


def test_supplied_m3_module_completes_migration_registration_without_execution(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("registration must not run migrations or connect to databases")

    monkeypatch.setenv("PROJECTCTL_OWNER_RUNTIME_MODULES", "services.orders.m3_setup")
    monkeypatch.setattr("infra.analytics_runtime.runtime_bindings", lambda: RuntimeBindings())
    monkeypatch.setattr("services.orders.m3_setup.setup", forbidden)
    team = runtime_bindings()
    assert set(team.migrations) == set(DATABASE_OWNERS)
    assert all(callable(callback) for callback in team.migrations.values())


def test_team_quality_seed_collects_exact_membership_without_replacing_provider_scope(monkeypatch):
    from benchmarks.quality_binding import QualityOwners
    from benchmarks.seed_audit import MEMBERSHIPS

    calls = []

    async def seed(context):
        calls.append("owner")
        return {"namespace": "bench-original-seed", "run_id": "original-run"}

    def collect(namespace):
        calls.append(namespace)
        return {field: ["FK-A"] for field in MEMBERSHIPS}

    monkeypatch.delenv("PROJECTCTL_OWNER_RUNTIME_MODULES", raising=False)
    monkeypatch.setattr(
        "infra.analytics_runtime.runtime_bindings",
        lambda: RuntimeBindings(quality=QualityOwners(seed_audit=seed)),
    )
    monkeypatch.setattr("benchmarks.seed_audit.collect_membership", collect)
    team = runtime_bindings()
    assert calls == []
    result = asyncio.run(team.quality.seed_audit({"namespace": "bench-measurement"}))
    assert calls == ["owner", "bench-original-seed"]
    assert result["run_id"] == "original-run" and result["inventory_skus"] == ["FK-A"]


@pytest.mark.parametrize("field", ["workloads", "migrations", "quality", "cases", "resets"])
def test_duplicate_handoffs_are_rejected(field):
    from pathlib import Path

    from benchmarks.integration import CaseBinding
    from benchmarks.quality_binding import QualityOwners

    value = {
        "workloads": {"W-PIPE": OwnerCallbacks()},
        "migrations": {"orders": lambda _: None},
        "quality": QualityOwners(),
        "cases": {"T-01/ingress": CaseBinding("real", Path("fixture.json"), None, None, None)},
        "resets": {"analytics": ResetParticipant(lambda _: None, lambda _: None)},
    }[field]
    binding = replace(RuntimeBindings(), **{field: value})
    with pytest.raises(DependencyError, match="duplicate"):
        merge_runtimes(binding, binding)


@pytest.mark.parametrize("namespace", ["dev", "bench-dev", "bench-production-run", "bench-live-x"])
def test_protected_reset_never_calls_an_owner(namespace):
    result = ResetCoordinator({})(Invocation("env reset", {}, None, "r", namespace))
    assert result.code == ExitCode.BAD_INPUT


@pytest.mark.parametrize("failure", [None, "missing", "preflight", "apply", "stub", "exception"])
def test_reset_checks_all_owners_before_any_delete_and_reports_partial_apply(failure):
    calls = []

    def callback(name, phase):
        def invoke(_):
            calls.append((phase, name))
            if name == "orders":
                if failure == "exception" and phase == "preflight":
                    raise RuntimeError("PRIVATE DSN")
                if failure == "stub" and phase == "preflight":
                    return ProviderResult(ExitCode.COMPLETED, (), "stub")
                if failure == phase:
                    return ProviderResult(
                        ExitCode.DEPENDENCY_FAILURE, ("explicit failure double",), "real"
                    )
            return ProviderResult(ExitCode.COMPLETED, (), "real")

        return invoke

    participants = {
        name: ResetParticipant(callback(name, "preflight"), callback(name, "apply"))
        for name in DATABASE_OWNERS
    }
    if failure == "missing":
        participants.pop("payments")
    result = ResetCoordinator(participants)(Invocation("env reset", {}, None, "r", "bench-reset"))
    assert (result.code == ExitCode.COMPLETED) == (failure is None)
    if failure == "missing":
        assert calls == []
    elif failure in {"preflight", "stub", "exception"}:
        assert not any(phase == "apply" for phase, _ in calls)
    else:
        assert calls[:6] == [("preflight", name) for name in DATABASE_OWNERS]
    if failure == "apply":
        assert "catalog reset apply completed" in result.reasons
        assert calls[-1] == ("apply", "orders")
    assert "PRIVATE" not in str(result)


def test_every_api_worker_and_relay_fits_the_declared_profiles():
    doc = json.loads((ROOT / "configs/evaluation_profiles.json").read_text("utf-8"))
    pipeline, _ = process_profile(doc, "pipeline-linux4c4g")
    integrated, processes = process_profile(doc, "integrated-linux9c8g")
    assert pipeline["service_allocations"]["analytics"] == {"cpu_cores": 2.0, "memory_mib": 1920}
    assert integrated["service_allocations"]["catalog"] == {"cpu_cores": 1.5, "memory_mib": 1152}
    assert integrated["connection_pools"]["conversation"] == 4  # Three API/audit + one relay.
    assert sum(p["memory_mib"] for p in processes) == 7808
    assert sum(p["cpu_cores"] for p in processes) == 8.25
    assert {p["name"] for p in processes if p["name"].endswith("-relay")} == {
        "conversation-relay",
        "catalog-relay",
        "orders-relay",
        "inventory-relay",
        "payments-relay",
    }
    # M4 publisher/relay threads share worker zero's counted process allocation.
    assert len(processes) == 16
    scaled = worker_processes(processes, 3)
    workers = [p for p in scaled if p["name"].startswith("analytics-worker-")]
    assert len(scaled) == 18 and len(workers) == 3
    assert sum(p["cpu_cores"] for p in workers) == 1.5
    assert sum(p["memory_mib"] for p in workers) == 1536
    assert [p["connections"] for p in workers] == [6, 4, 4]
    assert sum(p.get("connections", 0) for p in scaled if p["service"] == "analytics") == 16
    assert [p["name"] for p in workers if "analytics outbox relay" in p["roles"]] == [
        "analytics-worker-0"
    ]


def test_frozen_packet_verification_detects_exact_byte_drift(tmp_path, monkeypatch):
    monkeypatch.setattr("projectctl.config.ROOT", tmp_path)
    source = tmp_path / "dictionary.json"
    source.write_bytes(b"{}\n")
    lock = {
        "inputs": [{"path": "dictionary.json", "sha256": file_hash(source)}],
        "packet_files": [],
    }
    lock["content_sha256"] = content_hash(lock)
    (tmp_path / "input_lock.json").write_text(json.dumps(lock), encoding="utf-8")
    assert verify(tmp_path) == lock
    source.write_bytes(b"{}\r\n")
    with pytest.raises(ValueError, match="frozen bytes changed"):
        verify(tmp_path)
