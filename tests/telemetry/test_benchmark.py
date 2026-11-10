"""Identity-only controls fail closed; no provider/database doubles needed."""

import pytest

from shared.telemetry.benchmark import benchmark_headers

CONTROL = {"X-Benchmark-Scenario-ID": "measurement:000001:cart", "X-Benchmark-Seed": "42"}


@pytest.mark.parametrize(
    "benchmark,faults,namespace",
    [
        ("false", "true", "bench-test"),
        ("true", "false", "bench-test"),
        ("true", "true", "dev"),
        ("true", "true", "bench-production-test"),
        ("true", "true", "bench-live-test"),
    ],
)
def test_identity_controls_fail_closed(monkeypatch, benchmark, faults, namespace):
    monkeypatch.setenv("BENCHMARK_MODE", benchmark)
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", faults)
    with pytest.raises(PermissionError):
        benchmark_headers(CONTROL, namespace)


@pytest.mark.parametrize(
    "change",
    [
        {"X-Benchmark-Seed": None},
        {"X-Benchmark-Scenario-ID": None},
        {"X-Benchmark-Seed": "-1"},
        {"X-Benchmark-Seed": str(2**63)},
        {"X-Benchmark-Scenario-ID": "success"},
        {"X-Benchmark-Scenario-ID": "measurement:1:cart"},
    ],
)
def test_invalid_or_partial_identity_cannot_silently_randomize(monkeypatch, change):
    monkeypatch.setenv("BENCHMARK_MODE", "true")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    with pytest.raises(ValueError):
        benchmark_headers(CONTROL | change, "bench-test")


def test_no_controls_need_no_benchmark_flags():
    assert benchmark_headers({}, "dev") == {}
