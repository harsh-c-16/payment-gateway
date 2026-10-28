"""One-second read-only observation stream with explicit per-series gaps."""

import asyncio
import csv
import json
import math
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from projectctl.artifacts import canonical_json, content_hash, file_hash, write_json
from shared.telemetry.context import utc_now
from shared.telemetry.timing import TimingWriter


@dataclass(frozen=True)
class Series:
    metric: str
    component: str
    unit: str
    labels: tuple = ()

    def __post_init__(self):
        if not self.metric or not self.component or not self.unit:
            raise ValueError("metric, component and unit required")
        if any(not isinstance(k, str) or not isinstance(v, str) for k, v in self.labels) or len(
            dict(self.labels)
        ) != len(self.labels):
            raise ValueError("distinct string label keys/values required")
        object.__setattr__(self, "labels", tuple(sorted(self.labels)))

    @property
    def key(self):
        return json.dumps([self.component, self.metric, sorted(self.labels)], separators=(",", ":"))


@dataclass(frozen=True)
class Reading:
    value: float | int | None
    details: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Collector:
    name: str
    series: tuple[Series, ...]
    read: object  # async read(sequence) -> dict[Series.key, Reading]
    mode: str = "real"

    def __post_init__(self):
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", self.name):
            raise ValueError("safe collector name required")
        if not self.series or len({s.key for s in self.series}) != len(self.series):
            raise ValueError("distinct expected series required")
        if self.mode not in {"real", "stub"}:
            raise ValueError("explicit collector mode required")


@dataclass(frozen=True)
class ObservationConfig:
    directory: Path
    run_id: str
    namespace: str
    workload: str
    variant: str
    collectors: tuple[Collector, ...]
    mode: str = "real"
    evidence_kind: str = "smoke"
    interval_seconds: float = 1.0
    timeout_seconds: float = 0.8
    duration_seconds: float | None = None
    stop: object = None
    shared_host_clock: bool = False
    telemetry: object = None

    def __post_init__(self):
        if self.mode not in {"real", "stub"} or self.evidence_kind not in {
            "test",
            "smoke",
            "performance",
        }:
            raise ValueError("explicit observation mode/evidence kind required")
        if self.mode == "real" and any(c.mode != "real" for c in self.collectors):
            raise ValueError("real observation cannot use test doubles")
        if self.mode == "stub" and self.evidence_kind == "performance":
            raise ValueError("stub performance evidence is forbidden")
        if self.evidence_kind != "test" and self.interval_seconds != 1:
            raise ValueError("smoke/performance collectors use one-second sampling")
        if not 0 < self.timeout_seconds < self.interval_seconds or not math.isfinite(
            self.interval_seconds
        ):
            raise ValueError("bounded polling timeout below sampling interval required")
        if self.duration_seconds is not None and (
            not math.isfinite(self.duration_seconds) or self.duration_seconds <= 0
        ):
            raise ValueError("positive duration required")
        if self.duration_seconds is None and self.stop is None:
            raise ValueError("bounded duration or lifecycle stop signal required")
        names = [c.name for c in self.collectors]
        keys = [s.key for c in self.collectors for s in c.series]
        if len(set(names)) != len(names) or len(set(keys)) != len(keys):
            raise ValueError("collectors/series must be distinct within the run")


async def observe_run(run_config):
    """Yield rows at fixed ticks. A slow/missing reader never supplies a fake zero.

    Reader calls must cooperate with cancellation. SDK operations additionally
    need their own bounded request timeout. No provider discovery or doubles.
    """
    config = run_config
    start, sequence = time.perf_counter(), 0
    stop = config.stop or asyncio.Event()
    while not stop.is_set():
        scheduled = sequence * config.interval_seconds
        if config.duration_seconds is not None and scheduled >= config.duration_seconds:
            break
        while (delay := start + scheduled - time.perf_counter()) > 0 and not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay)
            except TimeoutError:
                pass
        if stop.is_set():
            break
        late = time.perf_counter() - start - scheduled >= config.interval_seconds

        async def poll(collector, late=late, sequence=sequence, scheduled=scheduled):
            reason, readings = None, {}
            if late:
                reason = "missed_tick"
            else:
                try:
                    async with asyncio.timeout(config.timeout_seconds):
                        readings = await collector.read(sequence)
                    if not isinstance(readings, dict) or set(readings) - {
                        s.key for s in collector.series
                    }:
                        raise ValueError("unexpected observation series")
                except Exception as exc:
                    reason = "timeout" if isinstance(exc, TimeoutError) else "provider_error"
                    readings = {}
            at, elapsed = utc_now(), time.perf_counter() - start
            result = []
            for series in collector.series:
                item = readings.get(series.key)
                value = item.value if isinstance(item, Reading) else None
                valid = (
                    reason is None
                    and not isinstance(value, bool)
                    and isinstance(value, (int, float))
                    and math.isfinite(value)
                    and value >= 0
                )
                details = {}
                if valid:
                    try:
                        if not isinstance(item.details, dict):
                            raise ValueError("reading details must be a JSON object")
                        # Snapshot provider metadata before another reader can mutate
                        # it; invalid metadata must not kill unrelated observations.
                        details = json.loads(canonical_json(item.details))
                    except (ValueError, TypeError, RecursionError):
                        valid = False
                result.append(
                    {
                        "run_id": config.run_id,
                        "namespace": config.namespace,
                        "workload": config.workload,
                        "variant": config.variant,
                        "test_mode": config.mode,
                        "collector_mode": collector.mode,
                        "collector": collector.name,
                        "series_key": series.key,
                        "metric_name": series.metric,
                        "component": series.component,
                        "unit": series.unit,
                        "labels": dict(series.labels),
                        "sequence": sequence,
                        "scheduled_elapsed_seconds": scheduled,
                        "observed_elapsed_seconds": elapsed,
                        "timestamp": at,
                        "value": value if valid else None,
                        "status": "MEASURED" if valid else "MISSING",
                        "reason": None if valid else reason or "missing_or_invalid_sample",
                        "details": details if valid else {},
                    }
                )
            return result

        # Independent readers have a common bounded deadline; all results inspected.
        batches = await asyncio.gather(*(poll(c) for c in config.collectors))
        for batch in batches:
            for row in batch:
                yield row
        sequence += 1


class ObservationSession:
    """Persist observations while an experiment runs; finalize before run hashing."""

    def __init__(self, config):
        self.config = config
        self.stop = config.stop or asyncio.Event()
        from dataclasses import replace

        self.config = replace(config, stop=self.stop)
        self.files = []

    async def __aenter__(self):
        directory = Path(self.config.directory)
        directory.mkdir(parents=True, exist_ok=True)
        context = {
            key: getattr(self.config, key)
            for key in (
                "run_id",
                "namespace",
                "workload",
                "variant",
                "mode",
                "evidence_kind",
                "interval_seconds",
                "timeout_seconds",
                "duration_seconds",
                "shared_host_clock",
            )
        }
        context["collectors"] = [
            {
                "name": c.name,
                "mode": c.mode,
                "series": [
                    {
                        "key": s.key,
                        "metric": s.metric,
                        "component": s.component,
                        "unit": s.unit,
                        "labels": dict(s.labels),
                    }
                    for s in c.series
                ],
            }
            for c in self.config.collectors
        ]
        write_json(directory / "observation_context.json", context)
        self.raw = (directory / "observations.jsonl").open("x", encoding="utf-8")
        self.files.append(self.raw)
        self.csvs = {}
        columns = [
            "timestamp",
            "run_id",
            "namespace",
            "workload",
            "variant",
            "test_mode",
            "collector",
            "component",
            "metric_name",
            "unit",
            "sequence",
            "scheduled_elapsed_seconds",
            "observed_elapsed_seconds",
            "value",
            "status",
            "reason",
            "labels",
            "details",
        ]
        for name in ("lag.csv", "resources.csv", "backlogs.csv"):
            stream = (directory / name).open("x", newline="", encoding="utf-8")
            self.files.append(stream)
            writer = csv.DictWriter(stream, columns, extrasaction="ignore")
            writer.writeheader()
            self.csvs[name] = writer, stream
        self.task = asyncio.create_task(self._collect())
        self.started = time.perf_counter()
        await asyncio.sleep(0)
        return self

    async def _collect(self):
        health = {}
        last_sequence = None
        async for row in observe_run(self.config):
            if row["sequence"] != last_sequence:
                health.clear()
                last_sequence = row["sequence"]
            name = row["collector"]
            health[name] = min(health.get(name, 1), int(row["status"] == "MEASURED"))
            if self.config.telemetry is not None:
                self.config.telemetry.record(
                    "benchmark_observation_up", health[name], collector=name
                )
            self.raw.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
            self.raw.flush()
            metric = row["metric_name"]
            target = (
                "lag.csv"
                if metric == "kafka_consumer_lag"
                else (
                    "resources.csv"
                    if metric.startswith(("process_", "cgroup_"))
                    else "backlogs.csv"
                )
            )
            writer, stream = self.csvs[target]
            writer.writerow(
                row
                | {
                    "labels": json.dumps(row["labels"], sort_keys=True),
                    "details": json.dumps(row["details"], sort_keys=True),
                }
            )
            stream.flush()

    async def __aexit__(self, exc_type, exc, traceback):
        stopped = time.perf_counter() - self.started
        self.stop.set()
        failure = None
        try:
            await self.task
        except (Exception, asyncio.CancelledError) as error:
            failure = error
        finally:
            for stream in self.files:
                stream.close()
        try:
            retain_client_timings(
                Path(self.config.directory), self.config.run_id, self.config.namespace
            )
        except Exception as error:
            failure = failure or error
        write_json(
            Path(self.config.directory) / "observation_end.json",
            {
                "stop_elapsed_seconds": stopped,
                "closed_at": utc_now(),
                "status": "INCOMPLETE" if failure else "COMPLETED",
                "error_type": type(failure).__name__ if failure else None,
            },
        )
        directory = Path(self.config.directory)
        names = {
            "observation_context.json",
            "observation_end.json",
            "observations.jsonl",
            "lag.csv",
            "resources.csv",
            "backlogs.csv",
            "timings.jsonl",
            "timings.parquet",
            "gold_visibility.jsonl",
            "generator.json",
            "admission.json",
            "emissions.jsonl",
            "planned.jsonl",
        }
        files = [p for p in directory.iterdir() if p.is_file() and p.name in names]
        files.extend(p for p in (directory / "manifests").glob("gold-audit-*.json") if p.is_file())
        manifest = {
            "schema_version": 1,
            "mode": self.config.mode,
            "artifacts": [
                {"path": p.relative_to(self.config.directory).as_posix(), "sha256": file_hash(p)}
                for p in sorted(files)
            ],
        }
        manifest["content_sha256"] = content_hash(manifest)
        write_json(Path(self.config.directory) / "telemetry_manifest.json", manifest)
        if failure is not None:
            raise failure


def retain_client_timings(directory, run_id, namespace):
    """Join source/send/ack by ID using the generator's single monotonic clock."""
    if (directory / "timings.jsonl").exists():
        return  # provider/owner may have already retained richer raw timings
    writer = TimingWriter(directory, run_id, namespace)
    seen = set()
    try:
        path = directory / "emissions.jsonl"
        if not path.exists():
            return
        with path.open(encoding="utf-8") as emissions:
            for line in emissions:
                row = json.loads(line)
                seen.add(row["record_id"])
                sent, ack = row["actual_send_elapsed_seconds"], row["ack_elapsed_seconds"]
                for stage, duration in (
                    (
                        "schedule_to_ack",
                        ack - row["scheduled_elapsed_seconds"] if ack is not None else None,
                    ),
                    ("send_to_ack", ack - sent if ack is not None and sent is not None else None),
                ):
                    writer.append(
                        component="generator",
                        record_id=row["record_id"],
                        event_id=row["event_or_request_id"],
                        stage=stage,
                        phase=row["phase"],
                        duration_seconds=duration,
                        started_at=row["scheduled_at"]
                        if stage == "schedule_to_ack"
                        else row["actual_send_at"],
                        ended_at=row["ack_at"],
                        clock_domain="generator_perf_counter",
                    )
    finally:
        try:
            retain_missing_timings(directory, writer, seen)
        finally:
            writer.close()


def retain_missing_timings(directory, writer, seen):
    """Keep absent completions visible, including when the emissions read failed."""
    planned = directory / "planned.jsonl"
    if planned.exists():
        with planned.open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if row["logical_record_id"] not in seen:
                    for stage in ("schedule_to_ack", "send_to_ack"):
                        writer.append(
                            component="generator",
                            event_id=None,
                            record_id=row["logical_record_id"],
                            stage=stage,
                            phase=row["phase"],
                            duration_seconds=None,
                            clock_domain="generator_perf_counter",
                        )
