"""P5 checkpoint: explicit stall/gap doubles; separate real generator resource smoke."""

import argparse
import asyncio
import json
from pathlib import Path
from uuid import uuid4

from benchmarks.collectors import SelfResourceReader, collector
from benchmarks.observation import ObservationConfig, ObservationSession
from benchmarks.observation_summary import markdown, rebuild
from projectctl.artifacts import write_json
from tests.telemetry.doubles import stalled_publishers, stopped_collector


async def demo(out):
    out.mkdir(parents=True, exist_ok=False)
    identity = str(uuid4())
    stub_config = ObservationConfig(
        out / "stub-stall",
        identity,
        "bench-" + identity,
        "W-PIPE",
        "B0",
        (stalled_publishers(), stopped_collector()),
        mode="stub",
        evidence_kind="smoke",
        duration_seconds=3.05,
    )
    real_config = ObservationConfig(
        out / "real-generator",
        str(uuid4()),
        "bench-" + identity,
        "W-PIPE",
        "B0",
        (collector("generator", SelfResourceReader()),),
        mode="real",
        evidence_kind="smoke",
        duration_seconds=2.05,
    )

    async def observe(config):
        async with ObservationSession(config) as session:
            await session.task
        summary = rebuild(config.directory)
        write_json(config.directory / "offline_summary.json", summary)
        (config.directory / "offline_summary.md").write_text(markdown(summary), encoding="utf-8")
        return summary

    stub, real = await asyncio.gather(observe(stub_config), observe(real_config))
    series = {s["metric"]: s for s in stub["series"]}
    resources = {s["metric"]: s for s in real["series"]}
    checks = {
        "kafka_lag_remains_zero": series["kafka_consumer_lag"]["peak"] == 0,
        "pending_gold_grows_to_30": series["gold_pending_events"]["peak"] == 30,
        "outbox_grows_separately": series["outbox_pending"]["peak"] == 6,
        "stopped_collector_has_three_gaps": series["projection_age_seconds"]["missing_samples"]
        == 3,
        "missing_latest_sample_is_null": series["projection_age_seconds"]["end"] is None,
        "offline_rebuild_identical": rebuild(stub_config.directory) == stub,
        "real_generator_cpu_read": resources["process_cpu_seconds_total"]["sample_count"] == 3,
        "real_generator_rss_read": resources["process_resident_memory_bytes"]["peak"] > 0,
        "real_and_stub_evidence_separate": stub["context"]["mode"] == "stub"
        and real["context"]["mode"] == "real",
    }
    write_json(
        out / "demo_checks.json",
        {
            "checks": checks,
            "stub_dir": str(stub_config.directory),
            "real_generator_dir": str(real_config.directory),
            "real_SUT": "NOT_RUN",
            "grafana_import": "NOT_RUN",
            "performance_matrix": "NOT_RUN",
        },
    )
    print(json.dumps({"evidence_dir": str(out), "checks": checks, "real_SUT": "NOT_RUN"}))
    return 0 if all(checks.values()) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    out = args.out or Path("artifacts/p5") / ("observer-demo-" + str(uuid4()))
    return asyncio.run(demo(out))


if __name__ == "__main__":
    raise SystemExit(main())
