"""Explicit provider registration. This module never imports a fake implementation."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from projectctl.models import EvaluationConfig, ExitCode

OWNERS = {
    "env up": "Vichitr",
    "env down": "Vichitr",
    "env verify": "Vichitr",
    "env reset": "Vichitr",
    "db migrate": "database owners / Vichitr",
    "contracts check": "all contract owners",
    "catalog profile": "Harsh",
    "catalog import": "Harsh",
    "catalog verify": "Harsh",
    "inventory seed": "Aditya",
    "projection wait": "Harsh / Aditya",
    "fixtures build": "Jaineel P3",
    "eval run": "Jaineel P2-P8 / case owners",
    "benchmark run": "Jaineel P4 / workload owners",
    "benchmark matrix": "Jaineel P4 / workload owners",
    "benchmark compare": "Jaineel P3-P9",
    "benchmark reconcile": "Jaineel P3-P8",
    "report build": "Jaineel P10",
}


class DependencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class Invocation:
    action: str
    arguments: dict
    config: EvaluationConfig | None
    run_id: str
    namespace: str


@dataclass(frozen=True)
class ProviderResult:
    code: ExitCode
    reasons: tuple[str, ...]
    test_mode: Literal["offline", "stub", "real"]


class ProviderRegistry:
    def __init__(self):
        self._actions: dict[str, Callable[[Invocation], ProviderResult]] = {}
        self._workloads = {}
        self._workload_factories = {}
        self._cases = {}
        self.binding_failure = None

    def register_case(self, case_id, binding):
        from benchmarks.integration import CaseBinding
        from benchmarks.integration_cases import BY_ID

        if case_id not in BY_ID or case_id in self._cases or not isinstance(binding, CaseBinding):
            raise ValueError("case binding must be known, explicit and registered exactly once")
        self._cases[case_id] = binding

    def case(self, case_id):
        return self._cases.get(case_id)

    def register_workload(self, workload, bindings):
        from projectctl.config import WORKLOADS

        if (
            workload not in WORKLOADS
            or workload in self._workloads
            or workload in self._workload_factories
        ):
            raise ValueError("workload binding must be known and registered exactly once")
        self._workloads[workload] = bindings

    def register_workload_factory(self, workload, factory):
        """Resolve real bindings using each trial's config, never registration-time defaults."""
        from projectctl.config import WORKLOADS

        if (
            workload not in WORKLOADS
            or workload in self._workloads
            or workload in self._workload_factories
            or not callable(factory)
        ):
            raise ValueError("workload factory must be known and registered exactly once")
        self._workload_factories[workload] = factory

    def workload(self, workload, config=None):
        if workload in self._workload_factories:
            if config is None:
                raise DependencyError("resolved trial configuration required for workload factory")
            from benchmarks.experiment import ExperimentBindings

            binding = self._workload_factories[workload](config)
            if not isinstance(binding, ExperimentBindings) or binding.mode != "real":
                raise DependencyError("production workload factory must return real bindings")
            return binding
        return self._workloads.get(workload)

    def register(self, action: str, adapter: Callable[[Invocation], ProviderResult]):
        if action not in OWNERS or action in self._actions:
            raise ValueError("provider action must be known and registered exactly once")
        self._actions[action] = adapter

    def missing(self, action: str) -> str | None:
        if action not in self._actions:
            return f"adapter unavailable: {action}; required owner: {OWNERS[action]}"
        return None

    def availability(self):
        """Registration inventory only; it does not assert runtime readiness."""
        from projectctl.config import WORKLOADS

        return {
            "actions": {
                action: {"registered": action in self._actions, "owner": owner}
                for action, owner in OWNERS.items()
            },
            "workloads": {
                workload: workload in self._workloads or workload in self._workload_factories
                for workload in sorted(WORKLOADS)
            },
            "cases": sorted(self._cases),
            "binding_failure": self.binding_failure,
            "runtime_readiness": "NOT_RUN",
        }

    def invoke(self, invocation: Invocation) -> ProviderResult:
        missing = self.missing(invocation.action)
        if missing:
            raise DependencyError(missing)
        result = self._actions[invocation.action](invocation)
        if not isinstance(result, ProviderResult) or not isinstance(result.code, ExitCode):
            raise DependencyError("provider returned an invalid result contract")
        if result.test_mode not in {"offline", "stub", "real"}:
            raise DependencyError("provider did not declare a valid test mode")
        return result


def default_registry() -> ProviderRegistry:
    import importlib
    import os
    import re

    from projectctl.contract_checks import check
    from projectctl.fixture_adapter import build

    registry = ProviderRegistry()
    registry.register("contracts check", check)
    registry.register("fixtures build", build)
    # Explicit production composition entry point; no auto-discovery of test modules.
    module = os.environ.get("PROJECTCTL_ADAPTER_MODULE")
    if module:
        try:
            if not re.fullmatch(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*)*", module):
                raise ValueError("invalid module name")
            # Stage registrations: a failing composition must not leave usable partial bindings.
            candidate = ProviderRegistry()
            candidate._actions = registry._actions.copy()
            importlib.import_module(module).register(candidate)
            registry = candidate
        except Exception as exc:
            registry.binding_failure = (
                f"explicit provider registration failed: {type(exc).__name__}"
            )
    # Other actions still require their owners' explicit production registrations.
    return registry
