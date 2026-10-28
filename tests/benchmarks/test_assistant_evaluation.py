"""Tiny hand-computable evaluation records; never live assistant-quality evidence."""

import copy

import pytest

from benchmarks.assistant_evaluation import evaluate_intents, evaluate_workflows
from benchmarks.metrics import SLOTS


def test_six_slot_f1_counts_wrong_value_as_fp_and_fn_and_explains_empty_slots():
    rows = [
        {
            "text": "blue clothing",
            "intent_labels": {**dict.fromkeys(SLOTS), "category": "clothing", "colour": "blue"},
        }
    ]
    result = evaluate_intents(rows, lambda _: {"intent": {"category": "clothing", "colour": "red"}})
    assert result["slots"]["colour"]["fp"] == result["slots"]["colour"]["fn"] == 1
    assert result["macro_f1"] == 0.5
    assert set(result["excluded_slots"]) == {"size", "material", "max_price_minor", "occasion"}


class SavedDouble:
    backend_identity = "explicit-backend-double"
    test_mode = "stub"

    def __init__(self, mode):
        self.mode = mode

    def __call__(self, scenario):
        return {
            "scenario_id": scenario["scenario_id"],
            "mode": self.mode,
            "model_attempts": 0,
            "outcome": "clarification",
            "search_calls": 0,
            "intent": None,
        }


def scenario():
    return {
        "scenario_id": "hand-case",
        "control": "search",
        "expected_outcome": "clarification",
        "generative_call_budget": {"fixed": 0, "assist": 1},
        "intent_labels": dict.fromkeys(SLOTS),
    }


def test_expected_clarification_is_separate_from_recommendation_and_missing_usage_stays_null():
    result = evaluate_workflows([scenario()], SavedDouble("fixed"), SavedDouble("assist"))
    assert result["live_quality"] == "NOT_RUN" and result["live_tokens"] is None
    for mode in result["modes"].values():
        assert mode["correct_clarifications"] == 1 and mode["successful_recommendations"] == 0
        assert mode["stage_diagnostics"]["llm"]["sample_count"] == 0
        assert mode["stage_diagnostics"]["llm"]["p95"] is None


def test_different_backend_or_trace_mode_is_rejected():
    left, right = SavedDouble("fixed"), SavedDouble("assist")
    right.backend_identity = "another-backend"
    with pytest.raises(ValueError, match="same backend"):
        evaluate_workflows([scenario()], left, right)
    with pytest.raises(ValueError, match="identity"):
        evaluate_workflows([scenario()], left, SavedDouble("fixed"))


def test_purchase_call_budget_violation_fails_even_for_expected_outcome():
    class BadDouble(SavedDouble):
        def __call__(self, scenario):
            return {**super().__call__(scenario), "model_attempts": 1}

    row = copy.deepcopy(scenario())
    row["control"] = "quote"
    with pytest.raises(ValueError):
        evaluate_workflows([row], SavedDouble("fixed"), BadDouble("assist"))


@pytest.mark.parametrize("count", [2, -1, True, 0.5])
def test_search_attempts_are_strictly_bounded_even_when_outcome_matches(count):
    class BadDouble(SavedDouble):
        def __call__(self, scenario):
            return {**super().__call__(scenario), "search_calls": count}

    with pytest.raises(ValueError, match="search"):
        evaluate_workflows([scenario()], SavedDouble("fixed"), BadDouble("assist"))


def test_duplicate_scenario_identity_cannot_inflate_quality_or_call_denominators():
    with pytest.raises(ValueError, match="scenario"):
        evaluate_workflows([scenario(), scenario()], SavedDouble("fixed"), SavedDouble("assist"))
