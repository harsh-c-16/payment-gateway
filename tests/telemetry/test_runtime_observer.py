"""Observer composition only; actual reader sampling has separate real-HTTP tests."""

from types import SimpleNamespace

import pytest

from benchmarks.collectors import collector
from benchmarks.observation import Series
from benchmarks.runtime_observer import MetricsTarget, RuntimeObserver
from projectctl.providers import DependencyError


def context():
    return {
        "namespace": "bench-observer",
        "run_id": "fixture",
        "workload_id": "W-PIPE",
        "variant_id": "B0",
    }


def test_worker_api_generator_lag_and_gold_are_separate_targets(tmp_path):
    worker = MetricsTarget(
        "worker",
        "http://worker.test:8006/metrics",
        (Series("process_resident_memory_bytes", "worker", "bytes"),),
    )
    api = MetricsTarget(
        "api", "http://api.test:8006/metrics", (Series("gold_pending_events", "api", "events"),)
    )
    lag = SimpleNamespace(
        mode="real", series=(Series("kafka_consumer_lag", "analytics", "records"),)
    )

    async def active(ctx):
        pytest.fail("configuration sampled Gold before the observer started")

    observer = RuntimeObserver((worker, api), lag_factory=lambda ctx: lag, read_active=active)(
        context(), tmp_path, "test"
    )
    assert [c.name for c in observer.config.collectors] == [
        "generator",
        "worker",
        "api",
        "kafka",
        "gold",
    ]
    assert observer.config.shared_host_clock is False


def test_missing_sut_or_stream_targets_fail_instead_of_generator_only_pass(tmp_path):
    with pytest.raises(DependencyError):
        RuntimeObserver(())(context(), tmp_path, "test")
    with pytest.raises(DependencyError):
        RuntimeObserver((), resource_factory=lambda ctx: ())(
            {**context(), "workload_id": "W-IMPORT"}, tmp_path, "test"
        )


def test_production_observer_refuses_stub_resources(tmp_path):
    reader = SimpleNamespace(mode="stub", series=(Series("memory", "sut", "bytes"),))
    with pytest.raises(DependencyError, match="test-double"):
        RuntimeObserver((), resource_factory=lambda ctx: [collector("resource", reader)])(
            {**context(), "workload_id": "W-IMPORT"}, tmp_path, "test"
        )
