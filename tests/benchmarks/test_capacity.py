import copy

import pytest

from benchmarks.capacity import qualify_repetition, qualify_tier


def inputs():
    return {
        "rate": 500,
        "planned": 300000,
        "admitted": 300000,
        "unresolved": 0,
        "unexpected_effects": 0,
        "resources_within_budget": True,
        "slo_met": True,
        "generator_valid": True,
        "samples": [{"second": n, "lag": 0, "pending_export": 0, "outbox": 0} for n in range(600)],
    }


def test_all_three_tier_repetitions_required_and_slo_separate():
    good = qualify_repetition(**inputs())
    assert qualify_tier([good] * 3)["sustainable_with_slo"]
    capacity = qualify_repetition(**(inputs() | {"slo_met": False}))
    assert capacity["capacity_without_slo"] and not capacity["sustainable_with_slo"]
    with pytest.raises(ValueError):
        qualify_tier([good])


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "rising_lag",
        "rising_pending",
        "rising_outbox",
        "admission",
        "unresolved",
        "duplicate",
        "resources",
        "generator",
    ],
)
def test_invalid_tiers_keep_reasons_and_never_claim_capacity(change):
    args = copy.deepcopy(inputs())
    if change == "missing":
        args["samples"].pop(10)
    elif change.startswith("rising"):
        key = {"rising_lag": "lag", "rising_pending": "pending_export", "rising_outbox": "outbox"}[
            change
        ]
        for row in args["samples"]:
            row[key] = row["second"] * 2
    elif change == "admission":
        args["admitted"] = 296999
    elif change == "unresolved":
        args["unresolved"] = 1
    elif change == "duplicate":
        args["unexpected_effects"] = 1
    elif change == "resources":
        args["resources_within_budget"] = False
    else:
        args["generator_valid"] = False
    result = qualify_repetition(**args)
    assert not result["capacity_valid"] and result["reasons"]
