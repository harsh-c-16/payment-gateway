import asyncio
import json
from dataclasses import replace

import pytest

from benchmarks.observation import (
    Collector,
    ObservationConfig,
    ObservationSession,
    Reading,
    Series,
    observe_run,
)
from benchmarks.observation_summary import rebuild
from tests.telemetry.doubles import stalled_publishers, stopped_collector


def config(directory, *collectors, **kwargs):
    return ObservationConfig(
        directory,
        "test-run",
        "bench-test",
        "W-PIPE",
        "B0",
        tuple(collectors),
        mode="stub",
        evidence_kind="test",
        interval_seconds=0.02,
        timeout_seconds=0.01,
        duration_seconds=0.061,
        **kwargs,
    )


def test_stalled_publisher_and_collector_gaps_are_separate_offline(tmp_path):
    async def run():
        async with ObservationSession(
            config(tmp_path, stalled_publishers(), stopped_collector())
        ) as s:
            await s.task

    asyncio.run(run())
    summary = rebuild(tmp_path)
    series = {s["metric"]: s for s in summary["series"]}
    assert series["kafka_consumer_lag"]["peak"] == 0
    assert series["gold_pending_events"]["peak"] == 30
    assert series["outbox_pending"]["peak"] == 6
    assert series["projection_age_seconds"]["missing_samples"] == 3
    assert series["projection_age_seconds"]["end"] is None
    assert summary["status"] == "INCOMPLETE" and summary["context"]["mode"] == "stub"
    assert (tmp_path / "lag.csv").is_file() and (tmp_path / "resources.csv").is_file()
    assert rebuild(tmp_path) == summary
    (tmp_path / "lag.csv").write_text("corrupt")
    with pytest.raises(ValueError, match="hash"):
        rebuild(tmp_path)


def test_slow_collector_times_out_while_peer_values_are_retained(tmp_path):
    item = Series("gold_pending_events", "gold", "events")

    async def hang(sequence):
        await asyncio.sleep(10)

    async def run():
        rows = []
        async for row in observe_run(
            config(tmp_path, stalled_publishers(), Collector("hang", (item,), hang, "stub"))
        ):
            rows.append(row)
        return rows

    # Avoid a duplicate declared series: the hung reader has its own component.
    item = Series("gold_pending_events", "stalled-exporter", "events")
    rows = asyncio.run(run())
    assert [r["value"] for r in rows if r["collector"] == "hang"] == [None] * 4
    assert all(r["reason"] == "timeout" for r in rows if r["collector"] == "hang")
    assert len([r for r in rows if r["status"] == "MEASURED"]) == 16


@pytest.mark.parametrize("value", [None, True, -1, float("nan"), float("inf")])
def test_invalid_reader_values_are_missing(tmp_path, value):
    series = Series("gold_pending_events", "gold", "events")

    async def read(sequence):
        return {series.key: Reading(value)}

    async def run():
        return [
            r
            async for r in observe_run(
                config(tmp_path, Collector("invalid", (series,), read, "stub"))
            )
        ]

    assert all(r["value"] is None and r["status"] == "MISSING" for r in asyncio.run(run()))


def test_real_mode_cannot_import_stub_collectors_and_one_second_is_enforced(tmp_path):
    stub = config(tmp_path, stalled_publishers())
    with pytest.raises(ValueError, match="doubles"):
        replace(stub, mode="real")
    with pytest.raises(ValueError, match="one-second"):
        replace(stub, evidence_kind="smoke")
    with pytest.raises(ValueError, match="performance"):
        replace(stub, evidence_kind="performance", interval_seconds=1, timeout_seconds=0.8)


def test_empty_collectors_are_visible_as_incomplete_evidence(tmp_path):
    async def run():
        async with ObservationSession(config(tmp_path)) as s:
            await s.task

    asyncio.run(run())
    assert rebuild(tmp_path)["status"] == "INCOMPLETE"


def test_cpu_counter_reset_and_gap_do_not_become_utilization_samples(tmp_path):
    series = Series("process_cpu_seconds_total", "worker", "seconds")

    async def read(sequence):
        return {series.key: Reading([10, 1, None, 3][sequence], {"allocated_cores": 2})}

    async def run():
        async with ObservationSession(
            config(tmp_path, Collector("cpu", (series,), read, "stub"))
        ) as s:
            await s.task

    asyncio.run(run())
    cpu = rebuild(tmp_path)["series"][0]
    assert cpu["mean_cpu_percent"] is None and cpu["cpu_status"] == "INCOMPLETE"


def test_live_observer_is_finalized_and_hashed_by_p4_lifecycle(tmp_path, monkeypatch):
    import projectctl.artifacts as artifacts
    import projectctl.config as configuration
    from benchmarks.experiment import run_experiment
    from projectctl.config import load_config
    from tests.benchmarks.doubles import LifecycleDouble

    cfg = load_config()
    cfg.generator.key_count = 2
    cfg.workloads["W-PIPE"].rate_per_second = 5
    monkeypatch.setattr(configuration, "ROOT", tmp_path)
    monkeypatch.setattr(artifacts, "ROOT", tmp_path)

    def factory(ctx, directory, evidence_kind):
        return ObservationSession(
            ObservationConfig(
                directory,
                ctx["run_id"],
                ctx["namespace"],
                ctx["workload_id"],
                ctx["variant_id"],
                (stalled_publishers(),),
                mode="stub",
                evidence_kind=evidence_kind,
                stop=asyncio.Event(),
            )
        )

    from shared.telemetry import Telemetry

    metrics = Telemetry(label_values={"phase": {"measurement", "warmup"}})
    bindings = replace(LifecycleDouble().bindings(), observer_factory=factory, telemetry=metrics)
    manifest = asyncio.run(
        run_experiment(
            "W-PIPE",
            "B0",
            1,
            42,
            config=cfg,
            bindings=bindings,
            duration_seconds=1,
            warmup_seconds=0,
            evidence_kind="test",
        )
    )
    folder = tmp_path / cfg.artifacts.root / manifest["run_id"]
    assert manifest["correctness_passed"] is True
    assert {"observations.jsonl", "timings.parquet", "telemetry_manifest.json"} <= {
        ref["path"] for ref in manifest["artifacts"]
    }
    assert rebuild(folder)["rates"]["offered_rate"] == 5
    raw = [json.loads(line) for line in (folder / "timings.jsonl").read_text().splitlines()]
    assert len(raw) == 10 and all(r["timing_validity"] == "VALID" for r in raw)
    exposition = metrics.exposition().decode()
    assert 'benchmark_planned_total{phase="measurement"} 5.0' in exposition
    assert 'benchmark_admitted_total{phase="measurement"} 5.0' in exposition
    assert "benchmark_pending_records 0.0" in exposition


def test_cpu_percent_uses_actual_elapsed_and_allocation(tmp_path):
    series = Series("process_cpu_seconds_total", "worker", "seconds")

    async def read(sequence):
        return {
            series.key: Reading(
                sequence * 0.5, {"allocated_cores": 2, "sample_monotonic": sequence}
            )
        }

    async def run():
        async with ObservationSession(
            config(tmp_path, Collector("cpu", (series,), read, "stub"))
        ) as s:
            await s.task

    asyncio.run(run())
    cpu = rebuild(tmp_path)["series"][0]
    assert cpu["cpu_percent_samples"] == [25, 25, 25]
    assert cpu["cpu_missing_intervals"] == 0 and cpu["cpu_status"] == "MEASURED"


def test_collector_health_metric_reports_missing_without_zeroing_data(tmp_path):
    from shared.telemetry import Telemetry

    metrics = Telemetry(label_values={"collector": {"stopped"}})

    async def run():
        cfg = replace(config(tmp_path, stopped_collector()), telemetry=metrics)
        async with ObservationSession(cfg) as s:
            await s.task

    asyncio.run(run())
    assert 'benchmark_observation_up{collector="stopped"} 0.0' in metrics.exposition().decode()
    assert rebuild(tmp_path)["series"][0]["end"] is None


def test_uncompleted_planned_requests_get_missing_raw_timing_rows(tmp_path):
    from benchmarks.observation import retain_client_timings

    (tmp_path / "planned.jsonl").write_text(
        json.dumps({"logical_record_id": "missing", "phase": "measurement"}) + "\n"
    )
    retain_client_timings(tmp_path, "test-run", "bench-test")
    rows = [json.loads(line) for line in (tmp_path / "timings.jsonl").read_text().splitlines()]
    assert len(rows) == 2
    assert all(r["record_id"] == "missing" and r["duration_seconds"] is None for r in rows)


def test_source_pacing_rechecks_early_event_loop_wakeups(monkeypatch):
    import benchmarks.scheduler as scheduler

    clock = [0]
    sleeps = []

    async def early_sleep(delay):
        sleeps.append(delay)
        clock[0] = [0.5, 0.75, 1][len(sleeps) - 1]

    monkeypatch.setattr(scheduler.time, "perf_counter", lambda: clock[0])
    monkeypatch.setattr(scheduler.asyncio, "sleep", early_sleep)
    asyncio.run(scheduler.sleep_until(1))
    assert sleeps == [1, 0.5, 0.25] and clock[0] == 1
