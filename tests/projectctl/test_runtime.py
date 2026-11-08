"""Explicit registration/migration doubles; never an executed real gate."""

import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.composition import OwnerCallbacks
from benchmarks.g3 import G3Binding, G3Owners
from benchmarks.integration import CaseBinding
from projectctl.config import load_config
from projectctl.jaineel import register
from projectctl.models import ExitCode
from projectctl.providers import (
    DependencyError,
    Invocation,
    ProviderRegistry,
    ProviderResult,
    default_registry,
)
from projectctl.runtime import RuntimeBindings
from projectctl.setup import DATABASE_OWNERS, MigrationCoordinator


def test_all_core_drivers_are_composed_without_starting_providers():
    registry = ProviderRegistry()
    register(registry)
    assert sum(registry.availability()["workloads"].values()) == 7
    for workload, exists in registry.availability()["workloads"].items():
        if exists:
            binding = registry.workload(workload, load_config())
            assert binding.mode == "real" and binding.driver is not None
            assert binding.dependency_reasons  # real readiness remains unavailable


def test_explicit_runtime_wires_hooks_cases_and_one_global_setup(monkeypatch):
    calls = []

    async def forbidden(*args):
        pytest.fail("registration called a lifecycle hook")

    def migrate(invocation):
        calls.append("migrate")
        return ProviderResult(ExitCode.COMPLETED, ("explicit setup-result double",), "real")

    owners = OwnerCallbacks(fresh_namespace=forbidden, performance_review_path="fixture-review")
    adapter = G3Binding("smoke/G3-success", "fixture.json", G3Owners(), lambda: None)
    case = CaseBinding("real", Path("fixture.json"), forbidden, forbidden, forbidden)
    runtime = RuntimeBindings(
        workloads={"W-IMPORT": owners},
        setup_actions={"db migrate": migrate},
        g3={adapter.case_id: adapter},
        cases={"D-01/source": case},
    )
    registry = ProviderRegistry()
    register(registry, runtime=runtime)
    assert calls == []
    binding = registry.workload("W-IMPORT", load_config())
    assert binding.performance_review_path == "fixture-review"
    assert not any("fresh_namespace" in reason for reason in binding.dependency_reasons)
    assert registry.case("D-01/source") is case
    assert registry.case("smoke/G3-success").prepare == adapter.prepare
    registry.invoke(Invocation("db migrate", {}, None, "run", "bench-runtime"))
    assert calls == ["migrate"]


@pytest.mark.parametrize("fault", ["stub", "unknown", "duplicate", "bad_type"])
def test_invalid_explicit_runtime_discards_partial_registry(monkeypatch, fault):
    runtime = RuntimeBindings()
    if fault == "stub":
        runtime = replace(runtime, mode="stub")
    elif fault == "unknown":
        runtime = replace(runtime, workloads={"W-UNKNOWN": OwnerCallbacks()})
    elif fault == "duplicate":
        runtime = replace(runtime, cases={"smoke/G3-success": None}, g3={"smoke/G3-success": None})
    else:
        runtime = object()
    monkeypatch.setitem(
        sys.modules, "explicit_runtime_double", SimpleNamespace(runtime_bindings=lambda: runtime)
    )
    monkeypatch.setenv("PROJECTCTL_RUNTIME_MODULE", "explicit_runtime_double")
    monkeypatch.setenv("PROJECTCTL_ADAPTER_MODULE", "projectctl.jaineel")
    registry = default_registry()
    assert registry.binding_failure
    assert registry.missing("env up")
    assert not any(registry.availability()["workloads"].values())


def test_setup_override_refuses_a_stub_pass():
    registry = ProviderRegistry()
    register(
        registry,
        runtime=RuntimeBindings(
            setup_actions={
                "env reset": lambda _: ProviderResult(
                    ExitCode.COMPLETED, ("explicit result double",), "stub"
                )
            }
        ),
    )
    with pytest.raises(DependencyError, match="test-double"):
        registry.invoke(Invocation("env reset", {}, None, "r", "bench-runtime"))


def test_missing_migration_participant_does_no_partial_work():
    calls = []
    coordinator = MigrationCoordinator({"conversation": lambda _: calls.append("write")})
    result = coordinator(None)
    assert result.code == ExitCode.DEPENDENCY_FAILURE and calls == []
    assert any("payments" in reason for reason in result.reasons)


@pytest.mark.parametrize("failure", [None, "orders", "stub", "exception"])
def test_coordinated_migrations_are_ordered_and_preserve_failures(failure):
    calls = []

    def participant(name):
        def invoke(_):
            calls.append(name)
            if name == "orders":
                if failure == "exception":
                    raise RuntimeError("PRIVATE connection details")
                if failure == "orders":
                    return ProviderResult(ExitCode.CORRECTNESS_FAILURE, ("mismatch",), "real")
                if failure == "stub":
                    return ProviderResult(ExitCode.COMPLETED, (), "stub")
            return ProviderResult(ExitCode.COMPLETED, (), "real")

        return invoke

    result = MigrationCoordinator({name: participant(name) for name in DATABASE_OWNERS})(None)
    assert calls == list(DATABASE_OWNERS if failure is None else DATABASE_OWNERS[:3])
    assert result.code == (
        ExitCode.COMPLETED
        if failure is None
        else ExitCode.CORRECTNESS_FAILURE
        if failure == "orders"
        else ExitCode.DEPENDENCY_FAILURE
    )
    assert "PRIVATE" not in str(result)
