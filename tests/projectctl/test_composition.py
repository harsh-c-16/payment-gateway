"""Composition tests: real owner exports; runtime/provider effects are never simulated as live."""

import sys
from types import SimpleNamespace

import pytest

from projectctl.config import load_config
from projectctl.input_pins import text_pin
from projectctl.providers import DependencyError, ProviderRegistry, default_registry


def test_example_namespace_and_m1_total_connections_match_frozen_contract():
    from pydantic import TypeAdapter

    from projectctl.config import ROOT
    from shared.contracts.events import Namespace

    values = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    }
    assert TypeAdapter(Namespace).validate_python(values["RUN_NAMESPACE"])
    # One separately composed shared outbox relay belongs to M1's total too.
    assert (
        int(values["CONVERSATION_MAX_CONNECTIONS"]) + 1
        <= load_config().profile.connection_pools["conversation"]
    )


def test_explicit_composition_registers_existing_owner_chain_once(monkeypatch):
    monkeypatch.setenv("PROJECTCTL_ADAPTER_MODULE", "projectctl.jaineel")
    registry = default_registry()
    inventory = registry.availability()
    assert registry.binding_failure is None
    assert all(
        inventory["actions"][name]["registered"]
        for name in (
            "env up",
            "env down",
            "env verify",
            "db migrate",
            "catalog profile",
            "catalog import",
            "catalog verify",
            "projection wait",
            "inventory seed",
            "contracts check",
            "fixtures build",
        )
    )
    assert registry.missing("env reset") is not None
    assert inventory["cases"] == []
    assert inventory["runtime_readiness"] == "NOT_RUN"
    assert {key for key, value in inventory["workloads"].items() if value} == {
        "W-IMPORT",
        "W-SEARCH",
        "W-ANALYTICS",
        "W-PIPE",
        "W-CHECKOUT",
        "W-INTEGRATED",
        "W-QUALITY",
    }
    config = load_config()
    for workload in ("W-IMPORT", "W-SEARCH", "W-ANALYTICS"):
        binding = registry.workload(workload, config)
        assert binding.mode == "real" and binding.driver is not None
        assert any("fresh_namespace" in reason for reason in binding.dependency_reasons)
    assert registry.workload("W-PIPE", config).dependency_reasons
    assert registry.workload("W-QUALITY", config).dependency_reasons


def test_composition_is_explicit_not_default(monkeypatch):
    monkeypatch.delenv("PROJECTCTL_ADAPTER_MODULE", raising=False)
    registry = default_registry()
    assert registry.missing("catalog import")
    assert registry.workload("W-IMPORT") is None


def test_failed_registration_discards_partial_actions_and_factories(monkeypatch):
    def broken(registry):
        registry.register("env up", lambda invocation: None)
        registry.register_workload_factory("W-IMPORT", lambda config: None)
        raise RuntimeError("PRIVATE credential must not appear")

    monkeypatch.setitem(
        sys.modules, "prompt3_broken_registration", SimpleNamespace(register=broken)
    )
    monkeypatch.setenv("PROJECTCTL_ADAPTER_MODULE", "prompt3_broken_registration")
    registry = default_registry()
    assert "RuntimeError" in registry.binding_failure
    assert "PRIVATE" not in registry.binding_failure
    assert registry.missing("env up")
    assert registry.workload("W-IMPORT") is None
    assert registry.missing("contracts check") is None


def test_factory_and_binding_share_duplicate_guard_and_use_trial_config():
    registry = ProviderRegistry()
    seen = []

    def factory(config):
        from benchmarks.experiment import ExperimentBindings

        seen.append(config)
        return ExperimentBindings(mode="real", driver=None)

    registry.register_workload_factory("W-IMPORT", factory)
    with pytest.raises(ValueError, match="exactly once"):
        registry.register_workload("W-IMPORT", object())
    with pytest.raises(ValueError, match="exactly once"):
        registry.register_workload_factory("W-IMPORT", factory)
    with pytest.raises(DependencyError, match="trial configuration"):
        registry.workload("W-IMPORT")
    first, second = load_config(), load_config()
    second.dataset.source_path = "data/raw/another.csv"
    registry.workload("W-IMPORT", first)
    registry.workload("W-IMPORT", second)
    assert seen == [first, second]
    assert seen[0] is first and seen[1] is second


def test_non_real_factory_result_is_rejected():
    from benchmarks.experiment import ExperimentBindings

    registry = ProviderRegistry()
    registry.register_workload_factory(
        "W-IMPORT", lambda config: ExperimentBindings(mode="stub", driver=object())
    )
    with pytest.raises(DependencyError, match="real bindings"):
        registry.workload("W-IMPORT", load_config())


def test_windows_and_linux_hashes_stay_distinct_from_text_identity(tmp_path):
    lf, crlf = tmp_path / "lf.json", tmp_path / "crlf.json"
    lf.write_bytes(b'{"colour":"blue"}\n')
    crlf.write_bytes(b'{"colour":"blue"}\r\n')
    linux, windows = text_pin(lf), text_pin(crlf)
    assert linux["raw_sha256"] != windows["raw_sha256"]
    assert linux["lf_text_sha256"] == windows["lf_text_sha256"]
    assert linux["contains_crlf"] is False and windows["contains_crlf"] is True
