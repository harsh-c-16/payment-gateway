"""Read-only collector implementations and explicit provider projection seams."""

import asyncio
import ctypes
import json
import math
import os
import platform
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from prometheus_client.parser import text_string_to_metric_families

from benchmarks.metrics import kafka_lag
from benchmarks.observation import Collector, Reading, Series
from projectctl.artifacts import write_json
from shared.telemetry.context import utc_now


class PrometheusReader:
    """One bounded HTTP scrape, exact selected label sets, no missing-to-zero rule."""

    mode = "real"

    def __init__(self, url, series, *, timeout_seconds=0.5, max_sample_age_seconds=1.0):
        parsed = urlparse(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("explicit metrics URL without credentials required")
        if not 0 < timeout_seconds < 0.8:
            raise ValueError("scrape timeout must fit one-second collector deadline")
        if not math.isfinite(max_sample_age_seconds) or max_sample_age_seconds <= 0:
            raise ValueError("positive finite sample freshness bound required")
        self.url, self.series, self.timeout = url, tuple(series), timeout_seconds
        self.max_sample_age = max_sample_age_seconds

    async def __call__(self, sequence):
        async with (
            asyncio.timeout(self.timeout),
            httpx.AsyncClient(trust_env=False, follow_redirects=False) as client,
        ):
            async with client.stream("GET", self.url, timeout=self.timeout) as response:
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 2 * 1024 * 1024:
                        raise ValueError("bounded metrics response exceeded")
        wanted = {(s.metric, s.labels): s for s in self.series}
        result = {}
        observed_at, seen = time.time(), set()
        for family in text_string_to_metric_families(body.decode("utf-8")):
            for sample in family.samples:
                series = wanted.get((sample.name, tuple(sorted(sample.labels.items()))))
                if series:
                    if series.key in seen:
                        raise ValueError("duplicate scrape series")
                    seen.add(series.key)
                    details = {"source": "http_metrics"}
                    if sample.timestamp is not None:
                        age = observed_at - float(sample.timestamp)
                        if not math.isfinite(age) or not 0 <= age <= self.max_sample_age:
                            continue  # explicitly stale/future samples remain missing
                        details.update(sample_timestamp=float(sample.timestamp), sample_age=age)
                    result[series.key] = Reading(sample.value, details)
        return result


class KafkaLagReader:
    """Admin reads only. Never subscribes, commits, resets offsets or creates topics."""

    mode = "real"

    def __init__(self, admin, group, partitions):
        self.admin, self.group = admin, group
        self.partitions = tuple(partitions)
        if not group or not self.partitions or len(set(self.partitions)) != len(self.partitions):
            raise ValueError("explicit group and distinct topic/partition targets required")
        self.series = tuple(
            Series(
                "kafka_consumer_lag",
                "analytics",
                "records",
                (("group", group), ("partition", str(p)), ("topic", t)),
            )
            for t, p in self.partitions
        )

    def read_sync(self):
        from confluent_kafka import ConsumerGroupTopicPartitions, TopicPartition
        from confluent_kafka.admin import OffsetSpec

        targets = [TopicPartition(t, p) for t, p in self.partitions]
        deadline = time.perf_counter() + 0.65
        # Launch both requests before waiting; each has its own broker timeout.
        groups = self.admin.list_consumer_group_offsets(
            [ConsumerGroupTopicPartitions(self.group, targets)], request_timeout=0.3
        )
        ends = self.admin.list_offsets(
            {tp: OffsetSpec.latest() for tp in targets}, request_timeout=0.3
        )
        result = groups[self.group].result(timeout=0.35)
        committed = {(tp.topic, tp.partition): tp for tp in result.topic_partitions}
        readings = {}
        for tp, series in zip(targets, self.series, strict=True):
            try:
                position = committed.get((tp.topic, tp.partition))
                if position is None or position.error or position.offset < 0:
                    continue  # uninitialized/unknown offset is missing, never zero
                end = ends[tp].result(timeout=max(0, deadline - time.perf_counter())).offset
                readings[series.key] = Reading(
                    kafka_lag(end, position.offset),
                    {
                        "group": self.group,
                        "topic": tp.topic,
                        "partition": tp.partition,
                        "log_end_next_offset": end,
                        "committed_next_offset": position.offset,
                        "boundary": "two bounded admin reads; inconsistent offsets are missing",
                    },
                )
            except Exception:
                continue  # one unavailable partition must not erase its peers
        return readings

    async def __call__(self, sequence):
        return await asyncio.to_thread(self.read_sync)


def current_rss_bytes():
    if os.name == "nt":
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (name, ctypes.c_size_t)
                for name in (
                    "PeakWorkingSetSize",
                    "WorkingSetSize",
                    "QuotaPeakPagedPoolUsage",
                    "QuotaPagedPoolUsage",
                    "QuotaPeakNonPagedPoolUsage",
                    "QuotaNonPagedPoolUsage",
                    "PagefileUsage",
                    "PeakPagefileUsage",
                )
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(Counters),
            wintypes.DWORD,
        ]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(
            kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        ):
            raise OSError(ctypes.get_last_error(), "process memory read failed")
        return counters.WorkingSetSize
    if platform.system() == "Linux":
        pages = int(Path("/proc/self/statm").read_text().split()[1])
        return pages * os.sysconf("SC_PAGE_SIZE")
    raise OSError("current RSS unsupported on this platform; no peak/current substitution")


class SelfResourceReader:
    """Actual generator process only. No claim of measuring SUT/container totals."""

    mode = "real"

    def __init__(self, *, allocated_cores=1.0):
        if not math.isfinite(allocated_cores) or allocated_cores <= 0:
            raise ValueError("positive allocated core denominator required")
        self.cores = allocated_cores
        self.series = (
            Series("process_cpu_seconds_total", "generator", "seconds"),
            Series("process_resident_memory_bytes", "generator", "bytes"),
        )

    async def __call__(self, sequence):
        details = {
            "pid": os.getpid(),
            "allocated_cores": self.cores,
            "resource_scope": "generator_process",
            "sample_monotonic": time.perf_counter(),
        }
        result = {self.series[0].key: Reading(time.process_time(), details)}
        try:
            result[self.series[1].key] = Reading(current_rss_bytes(), details)
        except OSError:
            pass
        return result


class CgroupV2Reader:
    """An explicitly supplied Linux cgroup directory; no automatic SUT attribution."""

    mode = "real"

    def __init__(self, directory, component, *, allocated_cores):
        self.directory, self.cores = Path(directory), allocated_cores
        if not math.isfinite(allocated_cores) or allocated_cores <= 0:
            raise ValueError("positive allocation required")
        self.series = (
            Series("process_cpu_seconds_total", component, "seconds"),
            Series("cgroup_memory_current_bytes", component, "bytes"),
            Series("cgroup_memory_peak_bytes", component, "bytes"),
        )

    async def __call__(self, sequence):
        result = {}
        try:
            events = dict(
                line.split()
                for line in (self.directory / "memory.events")
                .read_text(encoding="ascii")
                .splitlines()
            )
            oom_kills = int(events["oom_kill"])
            if oom_kills < 0:
                raise ValueError("negative OOM counter")
        except (OSError, ValueError, KeyError):
            oom_kills = None
        for series, filename in zip(
            self.series, ("cpu.stat", "memory.current", "memory.peak"), strict=True
        ):
            try:
                raw = (self.directory / filename).read_text(encoding="ascii")
                value = (
                    int(dict(line.split() for line in raw.splitlines())["usage_usec"]) / 1e6
                    if filename == "cpu.stat"
                    else int(raw.strip())
                )
                result[series.key] = Reading(
                    value,
                    {
                        "allocated_cores": self.cores,
                        "resource_scope": "cgroup_v2",
                        "sample_monotonic": time.perf_counter(),
                        "source_file": filename,
                        "oom_kill_count": oom_kills,
                    },
                )
            except (OSError, ValueError, KeyError):
                pass
        return result


class GoldVisibilityReader:
    """Consume the P3 active-Gold audit projection, never staging/receipt counts.

    The owner binding must pin the active manifest and read its membership proof
    and query at that generation. Projection checks are consumer checks, not an
    independent replacement for the P3 business/data oracle.
    """

    def __init__(self, read_active, directory, namespace, *, mode="real"):
        self.read_active, self.directory = read_active, Path(directory)
        self.namespace, self.mode, self.seen, self.generation = namespace, mode, set(), 0
        self.manifest_sha256 = None
        self.membership = None
        self.series = (
            Series("gold_generation", "gold", "generation"),
            Series("active_gold_members", "gold", "events"),
        )

    async def __call__(self, sequence):
        snapshot = await self.read_active()
        path = self.directory / "manifests"
        path.mkdir(exist_ok=True)
        # Preserve even invalid provider responses; never replace their raw evidence.
        write_json(path / f"gold-audit-{sequence:06}.json", snapshot)
        generation = snapshot["generation"]
        members = snapshot["membership_ids"]
        if (
            snapshot["namespace"] != self.namespace
            or type(generation) is not int
            or generation < max(1, self.generation)
            or generation != snapshot["query_generation"]
            or not isinstance(snapshot["manifest_sha256"], str)
            or len(snapshot["manifest_sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in snapshot["manifest_sha256"])
            or snapshot["manifest_sha256"] != snapshot["query_manifest_sha256"]
            or (
                generation == self.generation
                and self.manifest_sha256 != snapshot["manifest_sha256"]
            )
            or not isinstance(members, list)
            or any(not isinstance(m, str) or not m for m in members)
            or len(members) != len(set(members))
            or (generation == self.generation and set(members) != self.membership)
        ):
            raise ValueError("Gold active generation/membership projection invalid")
        new = set(members) - self.seen
        with (self.directory / "gold_visibility.jsonl").open("a", encoding="utf-8") as stream:
            for event_id in sorted(new):
                row = {
                    "event_id": event_id,
                    "namespace": self.namespace,
                    "generation": generation,
                    "manifest_sha256": snapshot["manifest_sha256"],
                    "gold_visible_observed_at": utc_now(),
                    "test_mode": self.mode,
                    "membership_evidence": f"manifests/gold-audit-{sequence:06}.json",
                    "observation_is_upper_bound": True,
                }
                stream.write(json.dumps(row, sort_keys=True) + "\n")
        self.seen.update(new)
        self.generation = generation
        self.manifest_sha256 = snapshot["manifest_sha256"]
        self.membership = set(members)
        return {
            s.key: Reading(
                value, {"generation": generation, "manifest_sha256": snapshot["manifest_sha256"]}
            )
            for s, value in zip(self.series, (generation, len(members)), strict=True)
        }


def collector(name, reader):
    return Collector(name, reader.series, reader, reader.mode)
