"""Arithmetic and orchestration doubles are explicit; no SUT measurement executes."""

import copy

import pytest

import benchmarks.comparison as comparison
from benchmarks.comparison import compare_metrics, compare_runs
from benchmarks.planning import plan_matrix, plan_trials
from projectctl.config import InputError, load_config, load_matrix


def metric(name, value, **changes):
    return {
        "name": name,
        "value": value,
        "unit": "fixture",
        "status": "MEASURED",
        "sample_count": 100,
        "timing_validity": "VALID",
        "cohort": "measurement",
        "quantile_method": None,
        "unresolved_count": 0,
        "evidence_path": "raw.jsonl",
    } | changes


def test_repeated_medians_spread_correct_direction_zero_and_unresolved():
    a = [
        {
            "metrics": [
                metric("query_p95_ms", n, unresolved_count=2),
                metric("gold_goodput", 100),
                metric("mean_cpu_percent", 0),
            ]
        }
        for n in (100, 300, 200)
    ]
    b = [
        {
            "metrics": [
                metric("query_p95_ms", n),
                metric("gold_goodput", 125),
                metric("mean_cpu_percent", 10),
            ]
        }
        for n in (80, 240, 160)
    ]
    rows = {r["name"]: r for r in compare_metrics(a, b)}
    assert rows["query_p95_ms"]["improvement_percent"] == 20
    assert rows["query_p95_ms"]["baseline"] == {
        "median": 200,
        "min": 100,
        "max": 300,
        "values": [100, 300, 200],
    }
    assert rows["query_p95_ms"]["unresolved_counts"] == [2, 2, 2, 0, 0, 0]
    assert rows["gold_goodput"]["improvement_percent"] == 25
    assert rows["mean_cpu_percent"]["improvement_percent"] is None


def test_missing_metrics_stay_null_and_unknown_directions_are_not_guessed():
    rows = compare_metrics([{"metrics": [metric("unknown_cost", 9)]}] * 3, [{"metrics": []}] * 3)
    assert rows[0]["status"] == "INCOMPLETE"
    assert rows[0]["baseline"] is None and rows[0]["candidate"] is None
    assert rows[0]["improvement_percent"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("unit", "other"),
        ("cohort", "finite_job"),
        ("quantile_method", "different"),
        ("timing_validity", "RECOVERY_UPPER_BOUND"),
    ],
)
def test_metric_semantics_cannot_change(field, value):
    with pytest.raises(InputError, match="boundary differ"):
        compare_metrics(
            [{"metrics": [metric("query_p95_ms", 100)]}] * 3,
            [{"metrics": [metric("query_p95_ms", 80, **{field: value})]}] * 3,
        )


def test_fastest_single_run_and_duplicate_paths_are_rejected():
    with pytest.raises(InputError, match="all three"):
        compare_runs(["one"], ["two"])
    with pytest.raises(InputError, match="distinct"):
        compare_runs(["one", "two", "three"], ["one", "four", "five"])


def artifact_doubles():
    config = load_config()
    result = {}
    for trial in plan_trials(config, "W-PIPE", ["B0", "O1"], 3):
        name = f"{trial.variant}-{trial.repetition}"
        result[name] = {
            "config": trial.config,
            "order": trial.order,
            "directory": comparison.repo_path(name),
            "manifest": {
                "git": {"commit": "fixture", "dirty": False},
                "locks": {"fixture": True},
                "host": {"fixture": True},
                "workload_id": trial.workload,
                "variant_id": trial.variant,
                "repetition": trial.repetition,
                "artifacts": [{"path": "raw.jsonl"}],
            },
            "summary": {"metrics": [metric("gold_goodput", 100 if trial.variant == "B0" else 125)]},
        }
    return result


@pytest.fixture
def comparison_double(monkeypatch):
    doubles = artifact_doubles()
    monkeypatch.setattr(
        comparison, "load_performance_run", lambda p: copy.deepcopy(doubles[p.name])
    )
    monkeypatch.setattr(comparison, "file_hash", lambda p: "f" * 64)
    return doubles


def test_all_three_repetitions_are_retained_with_explicit_loader_double(comparison_double):
    result = compare_runs([f"B0-{n}" for n in (3, 1, 2)], [f"O1-{n}" for n in (2, 3, 1)])
    assert result["metrics"][0]["improvement_percent"] == 25
    assert len(result["runs"]) == 6 and result["selection"] is None


@pytest.mark.parametrize("mutation", ["seed", "hardware", "repetition", "cache", "fault"])
def test_changed_controls_or_incomplete_cohorts_are_rejected(comparison_double, mutation):
    run = comparison_double["O1-2"]
    if mutation == "seed":
        run["config"].generator.seed += 1
    elif mutation == "hardware":
        run["manifest"]["host"]["fixture"] = False
    elif mutation == "repetition":
        run["manifest"]["repetition"] = 1
    elif mutation == "cache":
        run["config"].retrieval.cache_state = "cold"
    else:
        run["order"]["fault"] = "consumer-pause"
    with pytest.raises(InputError):
        compare_runs([f"B0-{n}" for n in (1, 2, 3)], [f"O1-{n}" for n in (1, 2, 3)])


def test_selection_expands_integrated_stress_and_recovery_without_choosing_a_default():
    config = load_config()
    matrix = load_matrix("configs/core_matrix.yaml", config)
    _, pending = plan_matrix(config, matrix)
    assert len(pending) == 3
    trials, pending = plan_matrix(
        config, matrix, {"variants": {"W-PIPE": "O1", "W-INTEGRATED": "O3"}, "sha256": "a" * 64}
    )
    assert not pending
    selected = [t for t in trials if t.order.get("label") == "C-BEST"]
    assert {t.order.get("stress_tier") for t in selected} >= {500, 1000, 2000}
    assert any(t.fault == "consumer-pause" and t.variant == "O1" for t in selected)
    assert len({t.order["trial_key"] for t in trials}) == len(trials)
