import asyncio
import io
import json
import logging
from uuid import uuid4

import pyarrow.parquet as pq
import pytest

from shared.contracts.common import RequestContext
from shared.telemetry import BUCKETS, Telemetry, TimingWriter, bind_context, log_operation
from shared.telemetry.metrics import DEFINITIONS


def context():
    identity = str(uuid4())
    return RequestContext(
        namespace="bench-test",
        run_id=identity,
        user_id="test-user",
        correlation_id=identity,
        request_id=identity,
        session_id=None,
    )


def test_context_survives_await_and_is_isolated_and_restored():
    output = io.StringIO()
    logger = logging.getLogger("p5-test")
    handler = logging.StreamHandler(output)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    contexts = [context(), context()]

    async def operation(ctx):
        with bind_context(ctx, "conversation"):
            await asyncio.sleep(0)
            assert log_operation(logger, "search", "success", 0.1)["request_id"] == ctx.request_id

    async def run():
        await asyncio.gather(*(operation(c) for c in contexts))

    try:
        asyncio.run(run())
        with pytest.raises(ValueError, match="bind"):
            log_operation(logger, "search", "success", 0.1)
        rows = [json.loads(line) for line in output.getvalue().splitlines()]
        assert {row["run_id"] for row in rows} == {c.run_id for c in contexts}
        assert all(row["timestamp"].endswith("Z") for row in rows)
        assert all("body" not in row and "authorization" not in row for row in rows)
    finally:
        logger.removeHandler(handler)


def test_metrics_are_lazy_and_use_exact_buckets_and_bounded_labels():
    metrics = Telemetry(
        label_values={"service": {"catalog"}, "route": {"/v1/products/{sku}"}, "status": {"200"}}
    )
    assert b"outbox_pending" not in metrics.exposition()
    metrics.record("requests_total", 1, service="catalog", route="/v1/products/{sku}", status="200")
    metrics.record("request_duration_seconds", 0.02, service="catalog", route="/v1/products/{sku}")
    metrics.record("gold_pending_events", 12)
    text = metrics.exposition().decode()
    assert "gold_pending_events 12.0" in text
    assert metrics.metrics["request_duration_seconds"]._kwargs["buckets"] == BUCKETS
    for bad in (
        {"event_id": "id"},
        {"service": "catalog", "route": "/v1/products/REAL-SKU"},
        {"service": "catalog", "route": "/v1/products/{sku}", "run_id": "id"},
    ):
        with pytest.raises(ValueError):
            metrics.record("request_duration_seconds", 0.1, **bad)
    with pytest.raises(ValueError):
        Telemetry(label_values={"run_id": {"id"}})


@pytest.mark.parametrize("value", [None, True, -1, float("nan"), float("inf")])
def test_metrics_do_not_turn_missing_or_invalid_samples_into_zero(value):
    with pytest.raises(ValueError):
        Telemetry().record("gold_pending_events", value)


def test_every_common_metric_can_be_recorded_without_global_registry_collisions():
    for name, (_, labels) in DEFINITIONS.items():
        metric = Telemetry(label_values={label: {"test"} for label in labels})
        metric.record(name, 1, **dict.fromkeys(labels, "test"))
        assert name.encode() in metric.exposition()
    metrics = Telemetry(series_limit=1)
    metrics.record("gold_pending_events", 1)
    with pytest.raises(ValueError, match="bound"):
        metrics.record("gold_generation", 1)


def test_raw_timings_retain_missing_and_failures_and_rebuild_parquet(tmp_path):
    writer = TimingWriter(tmp_path, "test-run", "bench-test")
    with pytest.raises(RuntimeError):
        with writer.span(
            component="catalog", event_id="event", stage="search", phase="measurement"
        ):
            raise RuntimeError("test failure")
    writer.append(
        component="catalog",
        event_id="missing",
        stage="search",
        phase="measurement",
        duration_seconds=None,
    )
    with pytest.raises(ValueError):
        writer.append(
            component="catalog",
            event_id="event",
            stage="search",
            phase="measurement",
            duration_seconds=0.1,
        )
    writer.close()
    raw = [json.loads(line) for line in (tmp_path / "timings.jsonl").read_text().splitlines()]
    assert pq.read_table(tmp_path / "timings.parquet").to_pylist() == raw
    assert raw[0]["duration_seconds"] >= 0 and raw[0]["clock_domain"] == "local_perf_counter"
    assert raw[1]["duration_seconds"] is None and raw[1]["timing_validity"] == "MISSING"
