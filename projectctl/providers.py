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

    def register_workload(self, workload, bindings):
        from projectctl.config import WORKLOADS

        if workload not in WORKLOADS or workload in self._workloads:
            raise ValueError("workload binding must be known and registered exactly once")
        self._workloads[workload] = bindings

    def workload(self, workload):
        return self._workloads.get(workload)

    def register(self, action: str, adapter: Callable[[Invocation], ProviderResult]):
        if action not in OWNERS or action in self._actions:
            raise ValueError("provider action must be known and registered exactly once")
        self._actions[action] = adapter

    def missing(self, action: str) -> str | None:
        if action not in self._actions:
            return f"adapter unavailable: {action}; required owner: {OWNERS[action]}"
        return None

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
    from projectctl.contract_checks import check
    from projectctl.fixture_adapter import build

    registry = ProviderRegistry()
    registry.register("contracts check", check)
    registry.register("fixtures build", build)
    # Other actions still require their owners' explicit production registrations.
    return registry
