"""Actual Docker cgroup counters; unavailable readings remain missing."""

import asyncio
import json
import re
from time import perf_counter

from benchmarks.observation import Reading, Series
from infra import postgres


class DockerResources:
    mode = "real"

    def __init__(self, container, component, *, service=None):
        if not re.fullmatch(r"[a-f0-9]{12,64}", container):
            raise ValueError("An actual Docker container ID is required")
        self.container = container
        self.service = service or component
        config = json.loads(
            postgres.command(["docker", "inspect", "--format", "{{json .HostConfig}}", container])
        )
        self.cores = config["NanoCpus"] / 1_000_000_000
        self.memory = config["Memory"]
        if self.cores <= 0 or self.memory <= 0:
            raise ValueError("SUT container requires explicit CPU/RAM limits")
        self.series = (
            Series("process_cpu_seconds_total", component, "seconds"),
            Series("cgroup_memory_current_bytes", component, "bytes"),
            Series("cgroup_memory_peak_bytes", component, "bytes"),
        )

    def read(self):
        try:
            raw = postgres.command(
                [
                    "docker",
                    "exec",
                    self.container,
                    "cat",
                    "/sys/fs/cgroup/cpu.stat",
                    "/sys/fs/cgroup/memory.current",
                    "/sys/fs/cgroup/memory.peak",
                    "/sys/fs/cgroup/memory.events",
                ],
                timeout=0.6,
            )
            counters, memory = {}, []
            for line in raw.splitlines():
                fields = line.split()
                if len(fields) == 1:
                    memory.append(int(fields[0]))
                else:
                    counters[fields[0]] = int(fields[1])
            current, peak = memory
            values = (counters["usage_usec"] / 1e6, current, peak)
            if any(value < 0 for value in values):
                raise ValueError("Negative resource counter")
            return {
                series.key: Reading(
                    value,
                    {
                        "allocated_cores": self.cores,
                        "memory_limit_bytes": self.memory,
                        "container_id": self.container,
                        "resource_scope": "cgroup_v2",
                        "service": self.service,
                        "sample_monotonic": perf_counter(),
                        "oom_kill_count": counters["oom_kill"],
                    },
                )
                for series, value in zip(self.series, values, strict=True)
            }
        except (postgres.SetupError, ValueError, KeyError, IndexError):
            return {}

    async def __call__(self, sequence):
        return await asyncio.to_thread(self.read)
