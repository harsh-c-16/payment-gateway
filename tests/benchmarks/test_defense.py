"""Viva evidence guards and actual local analytical-policy experiments."""

import json
from types import SimpleNamespace

import pytest

from benchmarks.defense import fingerprint, query_cases, stats, summary_trials
from benchmarks.defense_report import aggregate, checked_record, verified_run
from benchmarks.windows.evidence import digest


def test_summary_saves_counts_and_money_but_not_history_or_replay_identity(tmp_path):
    result = summary_trials(
        SimpleNamespace(
            out=tmp_path,
            events=120,
            repetitions=3,
            samples=5,
            seed=42,
        )
    )
    # 120 seconds, two minutes, four types; no inferred averages or missing money.
    assert result["raw_rows"] == 120 and result["summary_rows"] == 8
    assert result["expected_by_type"] == [
        ("type-0", 30, 177000),
        ("type-1", 30, 180000),
        ("type-2", 30, 183000),
        ("type-3", 30, 186000),
    ]
    assert len(result["timings"]) == 30
    assert len({r["result_sha256"] for r in result["timings"]}) == 1
    assert result["histories_with_same_summary"] == {
        "a": [("E1", 100), ("E2", 200)],
        "b": [("E1", 200), ("E2", 100)],
        "count_equal": True,
        "sum_equal": True,
        "history_equal": False,
    }
    assert result["duplicate_effects_with_retained_ids"] == 1
    assert result["duplicate_effects_after_unsafe_id_retirement"] == 2
    assert result["production_policy_changed"] is False


def test_query_fixture_does_not_invent_unknown_categories():
    rows = [
        {"category": None, "price_minor": 50},
        {"category": "shirts", "price_minor": 100},
        {"category": "shirts", "price_minor": 200},
    ]
    queries = query_cases(rows)
    assert queries[0]["params"] == ["bench-defense", "shirts", 100]
    assert rows[0]["category"] is None


def series():
    return [
        {
            "layout": "shuffled",
            "query": "q",
            "variant": variant,
            "repetition": rep,
            "seconds": value,
            "result_sha256": "same",
            "plan": [{"Node Type": "Seq Scan"}],
        }
        for variant, values in (("none", [0.001, 0.002, 0.003]), ("btree", [0.002, 0.004, 0.006]))
        for rep, value in enumerate(values, 1)
    ]


def test_report_keeps_all_repetitions_and_negative_index_results():
    report = aggregate(series())
    assert report["shuffled", "q", "none"]["repetition_medians_ms"] == [1, 2, 3]
    assert report["shuffled", "q", "btree"]["median_ms"] == 4
    assert report["shuffled", "q", "none"]["median_ms"] == 2


@pytest.mark.parametrize("corruption", ["missing_rep", "unequal_samples", "wrong_result"])
def test_unfair_or_incorrect_index_comparison_cannot_be_reported(corruption):
    rows = series()
    if corruption == "missing_rep":
        rows.pop()
    elif corruption == "unequal_samples":
        rows.append(rows[0])
    else:
        for r in rows:
            if r["variant"] == "btree":
                r["result_sha256"] = "different"
    with pytest.raises(ValueError):
        aggregate(rows)


@pytest.mark.parametrize("observed", [None, False, 1, "true"])
def test_saved_pass_flag_alone_is_not_a_verified_check(tmp_path, observed):
    path = tmp_path / "result.json"
    path.write_text(
        json.dumps(
            {
                "status": "Passed",
                "checks": [
                    {"expected": True, "observed": observed, "passed": True},
                ],
            }
        )
    )
    with pytest.raises(ValueError, match="do not establish"):
        checked_record(path)


@pytest.mark.parametrize("status", ["FAILED", "SMOKE_ONLY", "RUNNING"])
def test_diagnostic_or_unfinished_runs_cannot_be_promoted(tmp_path, status):
    (tmp_path / "manifest.json").write_text(json.dumps({"status": status}))
    with pytest.raises(ValueError, match="completed component"):
        verified_run(tmp_path)


def test_evidence_hash_and_cleanup_are_required(tmp_path):
    data = tmp_path / "data.json"
    data.write_text("{}")
    cleanup = tmp_path / "cleanup.json"
    cleanup.write_text('{"container_removed":true}')
    manifest = {
        "status": "MEASURED_COMPONENT",
        "formal_p9_qualified": False,
        "files": {"data.json": digest(data), "cleanup.json": digest(cleanup)},
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    assert verified_run(tmp_path)["formal_p9_qualified"] is False
    data.write_text('{"changed":true}')
    with pytest.raises(ValueError, match="hash"):
        verified_run(tmp_path)


def test_hand_computed_nearest_rank_quantile_and_history_fingerprint():
    assert stats([0.003, 0.001, 0.002]) == {
        "n": 3,
        "median": 0.002,
        "min": 0.001,
        "max": 0.003,
        "p95": 0.003,
    }
    assert fingerprint(True) != fingerprint(1)
    with pytest.raises(ValueError):
        stats([float("nan")])
