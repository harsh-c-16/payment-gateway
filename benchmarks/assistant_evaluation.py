"""Six-slot and paired workflow diagnostics; synthetic traces never establish live quality."""

import copy

from benchmarks.metrics import SLOTS, nearest_rank, ratio, slot_f1


def evaluate_intents(labelled_utterances, extractor):
    expected, observed = [], []
    for row in labelled_utterances:
        if set(row["intent_labels"]) != set(SLOTS):
            raise ValueError("every scenario must retain exactly the six original intent slots")
        result = extractor(copy.deepcopy(row))
        intent = result.get("intent") if isinstance(result, dict) else result.intent
        expected.append(row["intent_labels"])
        observed.append({slot: (intent or {}).get(slot) for slot in SLOTS})
    return {"scenario_count": len(expected), **slot_f1(expected, observed)}


OUTCOMES = {
    "display_fixture_matches": "success",
    "honest_no_results": "success",
    "clarification": "clarification",
    "clarification_no_repair_call": "clarification",
    "one_cart_effect": "one_cart_effect",
    "authoritative_quote": "authoritative_quote",
    "accepted_pending": "accepted_pending",
    "same_order_recovered_pending": "accepted_pending",
    "no_purchase": "no_purchase",
    "conflict": "conflict",
    "backend_status_only": "backend_status",
    "authoritative_status_despite_analytics_outage": "backend_status",
    "authoritative_status_after_read_retry": "backend_status",
    "catalogue_dependency_error": "dependency_error",
    "order_status_dependency_error": "dependency_error",
}


def evaluate_workflows(scenarios, fixed_adapter, assist_adapter):
    """Adapters declare identical backend identity and return actual identity-bound raw traces."""
    scenarios = list(scenarios)
    if not scenarios or len({s["scenario_id"] for s in scenarios}) != len(scenarios):
        raise ValueError("nonempty distinct scenario identities required")
    if (
        fixed_adapter.backend_identity != assist_adapter.backend_identity
        or fixed_adapter.test_mode != assist_adapter.test_mode
    ):
        raise ValueError("fixed and assist must use the same backend and test mode")
    groups = {}
    for mode, adapter in (("fixed", fixed_adapter), ("assist", assist_adapter)):
        traces, calls, successes, matched, recommendations, clarifications = [], [], 0, 0, 0, 0
        unnecessary, no_results, failures, search_calls = 0, 0, 0, []
        for scenario in scenarios:
            trace = adapter(copy.deepcopy(scenario))
            if trace["scenario_id"] != scenario["scenario_id"] or trace["mode"] != mode:
                raise ValueError("scenario/mode trace identity mismatch")
            count = trace["model_attempts"]
            if (
                type(count) is not int
                or count < 0
                or count > scenario["generative_call_budget"][mode]
            ):
                raise ValueError("actual model attempts exceed scenario budget")
            if scenario["control"] != "search" and count != 0:
                raise ValueError("purchase and structured controls must make zero model attempts")
            searches = trace["search_calls"]
            if type(searches) is not int or not 0 <= searches <= 1:
                raise ValueError("each scenario permits at most one search attempt")
            expected = OUTCOMES[scenario["expected_outcome"]]
            same = trace["outcome"] == expected
            if expected == "success":
                same = (
                    same
                    and [p["sku"] for p in trace.get("products", [])]
                    == scenario["expected_behavior"]["expected_hit_skus"]
                )
            matched += same
            failures += trace["outcome"] == "dependency_error"
            successes += same and expected != "dependency_error"
            recommendations += same and expected == "success" and bool(trace.get("products"))
            no_results += same and expected == "success" and not trace.get("products")
            clarifications += same and expected == "clarification"
            unnecessary += trace["outcome"] == "clarification" and expected != "clarification"
            calls.append(count)
            search_calls.append(searches)
            traces.append(trace)
        stages = {}
        for stage in ("parse", "llm", "search", "compose", "total"):
            samples = [
                r["timings_ms"][stage]
                for r in traces
                if r.get("timings_ms", {}).get(stage) is not None
            ]
            stages[stage] = {
                "unit": "milliseconds",
                "sample_count": len(samples),
                "missing_or_not_applicable": len(traces) - len(samples),
                "p50": nearest_rank(samples, 0.5),
                "p95": nearest_rank(samples, 0.95),
                "p99": nearest_rank(samples, 0.99),
                "quantile_method": "nearest-rank",
            }
        groups[mode] = {
            "scenario_count": len(traces),
            "expected_outcome_matches": matched,
            "task_successes": successes,
            "successful_recommendations": recommendations,
            "correct_no_results": no_results,
            "correct_clarifications": clarifications,
            "unnecessary_clarifications": unnecessary,
            "dependency_failures": failures,
            "model_attempts": sum(calls),
            "mean_calls_per_scenario": ratio(sum(calls), len(calls)),
            "calls_per_successful_task": ratio(sum(calls), successes),
            "zero_call_share": ratio(calls.count(0), len(calls)),
            "fallback_share": ratio(sum(c > 0 for c in calls), len(calls)),
            "search_calls": sum(search_calls),
            "stage_diagnostics": stages,
            "six_slot_F1_diagnostic": evaluate_intents(
                scenarios,
                lambda s, records=traces: next(
                    r for r in records if r["scenario_id"] == s["scenario_id"]
                ),
            ),
            "traces": traces,
        }
    return {
        "schema_version": 1,
        "backend_identity": fixed_adapter.backend_identity,
        "test_mode": fixed_adapter.test_mode,
        "modes": groups,
        "human_review_status": "NOT_RUN",
        "live_quality": "NOT_RUN",
        "live_latency": None,
        "live_tokens": None,
        "live_cost": None,
        "limitations": [
            "Fixture human review is pending; F1 is an unreviewed-label diagnostic.",
            "Synthetic provider timing is not a live model/SUT performance result.",
            "v1 only attempts category resolution for an explicit supported apparel size.",
            "The current 60 scenarios have no eligible v1 fallback; additional spy cases "
            "exercise actual valid, failed, invalid and timed-out attempts.",
        ],
    }
