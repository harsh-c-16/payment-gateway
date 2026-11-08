"""One explicit runtime handoff for Jaineel's production composition.

This is an owned extension interface, not a claim that teammates already export
these functions. No module is discovered, no approvals are generated, and the
existing execution-time review/readiness checks remain mandatory.
"""

import importlib
import os
import re
from dataclasses import dataclass, field

from benchmarks.composition import OwnerCallbacks
from benchmarks.g3 import G3Binding
from benchmarks.integration import CaseBinding
from benchmarks.quality_binding import QualityOwners
from projectctl.providers import DependencyError, ProviderResult

CORE = {"W-IMPORT", "W-PIPE", "W-SEARCH", "W-CHECKOUT", "W-INTEGRATED", "W-ANALYTICS"}


@dataclass(frozen=True)
class RuntimeBindings:
    workloads: dict = field(default_factory=dict)  # workload -> OwnerCallbacks
    quality: QualityOwners | None = None
    g3: dict = field(default_factory=dict)  # case ID -> G3Binding
    cases: dict = field(default_factory=dict)  # remaining D/T case ID -> CaseBinding
    setup_actions: dict = field(default_factory=dict)  # reviewed global db migrate/env reset
    migrations: dict = field(default_factory=dict)  # database -> owner migration participant
    resets: dict = field(default_factory=dict)  # database -> ResetParticipant
    mode: str = "real"

    def validate(self):
        from benchmarks.integration_cases import BY_ID
        from projectctl.setup import DATABASE_OWNERS, ResetParticipant

        if self.mode != "real" or set(self.workloads) - CORE:
            raise DependencyError("runtime requires known real workload bindings")
        if any(not isinstance(value, OwnerCallbacks) for value in self.workloads.values()):
            raise DependencyError("runtime workload hooks must be OwnerCallbacks")
        if self.quality is not None and not isinstance(self.quality, QualityOwners):
            raise DependencyError("runtime quality hooks must be QualityOwners")
        if set(self.setup_actions) - {"db migrate", "env reset"} or any(
            not callable(value) for value in self.setup_actions.values()
        ):
            raise DependencyError("only reviewed migration/reset coordinator overrides are allowed")
        if set(self.g3) & set(self.cases):
            raise DependencyError("duplicate runtime case registration")
        if set(self.migrations) - set(DATABASE_OWNERS) or any(
            not callable(value) for value in self.migrations.values()
        ):
            raise DependencyError("known owner migration participants required")
        if set(self.resets) - set(DATABASE_OWNERS) or any(
            not isinstance(value, ResetParticipant) for value in self.resets.values()
        ):
            raise DependencyError("known owner ResetParticipant bindings required")
        for key, value in self.g3.items():
            if not isinstance(value, G3Binding) or value.case_id != key or value.mode != "real":
                raise DependencyError("runtime G3 binding identity/mode mismatch")
        for key, value in self.cases.items():
            if key not in BY_ID or not isinstance(value, CaseBinding) or value.mode != "real":
                raise DependencyError("runtime cases require known explicit real bindings")
        return self


def merge_runtimes(*bindings):
    """Compose independent owner handoffs without silently replacing any callback."""
    combined = {
        name: {} for name in ("workloads", "g3", "cases", "setup_actions", "migrations", "resets")
    }
    quality = None
    for binding in bindings:
        binding.validate()
        for name, values in combined.items():
            incoming = getattr(binding, name)
            if values.keys() & incoming.keys():
                raise DependencyError("duplicate owner runtime registration: " + name)
            values.update(incoming)
        if binding.quality is not None:
            if quality is not None:
                raise DependencyError("duplicate owner quality runtime")
            quality = binding.quality
    return RuntimeBindings(**combined, quality=quality).validate()


def load_runtime():
    module = os.environ.get("PROJECTCTL_RUNTIME_MODULE")
    if not module:
        return RuntimeBindings()
    if not re.fullmatch(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*)*", module):
        raise DependencyError("invalid explicit runtime module name")
    value = importlib.import_module(module).runtime_bindings()
    if not isinstance(value, RuntimeBindings):
        raise DependencyError("runtime module must return RuntimeBindings")
    return value.validate()


class SetupRegistration:
    """Keep exactly one registration while allowing the reviewed global coordinator."""

    def __init__(self, registry, overrides):
        self.registry, self.overrides, self.seen = registry, overrides, set()

    def register(self, name, adapter):
        self.seen.add(name)
        if name in self.overrides:
            actual = self.overrides[name]

            def real_only(invocation):
                result = actual(invocation)
                if not isinstance(result, ProviderResult) or result.test_mode != "real":
                    raise DependencyError("global setup refuses a test-double result")
                return result

            self.registry.register(name, real_only)
        else:
            self.registry.register(name, adapter)

    def remaining(self):
        for name in self.overrides.keys() - self.seen:
            self.register(name, self.overrides[name])
