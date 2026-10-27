"""Metric-source tests use explicit telemetry doubles, not target or lab values."""

import pytest

import benchmarks.performance_metrics as metrics
from projectctl.artifacts import write_json
from projectctl.config import load_config


def telemetry_double():
    return {
        "rates": {"gold_goodput": 50},
        "series": [],
        "latencies": [
            {
                "phase": "measurement",
                "component": "analytics",
                "stage": "producer_to_gold",
                "sample_count": 20,
                "completed_only": {"p50": 0.1, "p95": 0.3, "p99": 0.5},
            }
        ],
    }


def test_finite_import_uses_actual_total_and_staging_denominators(tmp_path, monkeypatch):
    monkeypatch.setattr(metrics, "rebuild", lambda p: telemetry_double() | {"latencies": []})
    write_json(
        tmp_path / "admission.json", {"phases": {"measurement": {"unresolved": 0, "planned": 1}}}
    )
    write_json(
        tmp_path / "import_timings.json",
        {"raw_to_ready_seconds": 4.0, "stages": {"staging_seconds": 2.0}},
    )
    result = {
        m.name: m
        for m in metrics.derive_metrics(
            tmp_path, load_config(), "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "W-IMPORT", []
        )
    }
    assert result["raw_rows_per_second"].value == 5000
    assert result["canonical_rows_per_second"].value == 9999
    assert result["raw_rows_per_second"].cohort == "finite_job"
    assert "gold_goodput" not in result


def test_gold_latency_uses_raw_stage_and_reports_unresolved(tmp_path, monkeypatch):
    monkeypatch.setattr(metrics, "rebuild", lambda p: telemetry_double())
    write_json(
        tmp_path / "admission.json", {"phases": {"measurement": {"unresolved": 2, "planned": 22}}}
    )
    result = {
        m.name: m
        for m in metrics.derive_metrics(
            tmp_path, load_config(), "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "W-PIPE", []
        )
    }
    assert result["producer_to_gold_p95_ms"].value == 300
    assert result["producer_to_gold_p95_ms"].unresolved_count == 2
    assert result["producer_to_gold_p95_ms"].quantile_method == "nearest-rank"


def test_import_missing_elapsed_time_is_not_replaced_by_sustained_duration(tmp_path, monkeypatch):
    monkeypatch.setattr(metrics, "rebuild", lambda p: telemetry_double() | {"latencies": []})
    write_json(
        tmp_path / "admission.json", {"phases": {"measurement": {"unresolved": 0, "planned": 1}}}
    )
    write_json(
        tmp_path / "import_timings.json",
        {"raw_to_ready_seconds": 0, "stages": {"staging_seconds": 2.0}},
    )
    with pytest.raises(ValueError, match="elapsed"):
        metrics.derive_metrics(
            tmp_path, load_config(), "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "W-IMPORT", []
        )
