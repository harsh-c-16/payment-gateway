"""Compose existing real collectors from explicit deployment targets."""

import asyncio
from dataclasses import dataclass

from benchmarks.collectors import (
    GoldVisibilityReader,
    PrometheusReader,
    SelfResourceReader,
    collector,
)
from benchmarks.observation import ObservationConfig, ObservationSession
from projectctl.providers import DependencyError


@dataclass(frozen=True)
class MetricsTarget:
    name: str
    url: str
    series: tuple


class RuntimeObserver:
    def __init__(
        self,
        targets,
        *,
        lag_factory=None,
        read_active=None,
        resource_factory=None,
        shared_host_clock=False,
    ):
        self.targets = tuple(targets)
        if any(not isinstance(t, MetricsTarget) for t in self.targets):
            raise ValueError("explicit MetricsTarget values required")
        self.lag_factory, self.read_active = lag_factory, read_active
        self.resource_factory = resource_factory
        if type(shared_host_clock) is not bool:
            raise ValueError("explicit shared-host clock statement required")
        self.shared_host_clock = shared_host_clock

    def __call__(self, context, directory, kind):
        stream = context["workload_id"] in {
            "W-PIPE",
            "W-QUALITY",
            "W-CHECKOUT",
            "W-INTEGRATED",
            "G1",
        }
        if stream and (self.lag_factory is None or self.read_active is None):
            raise DependencyError("stream observation requires actual lag and pinned Gold readers")
        if not self.targets and self.resource_factory is None:
            raise DependencyError(
                "SUT observation targets unavailable; generator alone is insufficient"
            )
        readers = [collector("generator", SelfResourceReader())]
        for target in self.targets:
            readers.append(collector(target.name, PrometheusReader(target.url, target.series)))
        if self.resource_factory is not None:
            resources = tuple(self.resource_factory(context))
            if not resources:
                raise DependencyError(
                    "declared SUT resource collector factory returned no collectors"
                )
            readers.extend(resources)
        if stream:
            readers.append(collector("kafka", self.lag_factory(context)))

            async def active():
                return await self.read_active(context)

            readers.append(
                collector("gold", GoldVisibilityReader(active, directory, context["namespace"]))
            )
        if any(reader.mode != "real" for reader in readers):
            raise DependencyError("production observer refuses test-double collectors")
        return ObservationSession(
            ObservationConfig(
                directory=directory,
                run_id=context["run_id"],
                namespace=context["namespace"],
                workload=context["workload_id"],
                variant=context["variant_id"],
                evidence_kind=kind,
                collectors=tuple(readers),
                stop=asyncio.Event(),
                shared_host_clock=self.shared_host_clock,
            )
        )
