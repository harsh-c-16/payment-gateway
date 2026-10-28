import copy
import json
from pathlib import Path

import pytest

from benchmarks.reconciliation import compare_fixture_output, reconcile_run

from .doubles import CORRUPTIONS, clean_evidence, corrupt_evidence

ROOT = Path(__file__).resolve().parents[2]


def test_clean_explicit_evidence_passes_without_mutation():
    expected, observed = clean_evidence()
    before = copy.deepcopy((expected, observed))
    result = reconcile_run(expected, observed)
    assert result["status"] == "PASS"
    assert result["reconciliation"]["passed"]
    assert result["test_mode"] == "stub"
    assert (expected, observed) == before


@pytest.mark.parametrize("name,reason", CORRUPTIONS.items())
def test_corruption_fails_for_the_intended_reason(name, reason):
    expected, observed = clean_evidence()
    result = reconcile_run(expected, corrupt_evidence(name, observed))
    assert result["status"] == "FAIL"
    assert result["reconciliation"]["passed"] is False
    assert any(
        item.split(":")[0] == reason for item in result["reconciliation"]["invariant_failures"]
    )


def test_missing_evidence_cannot_pass_as_empty_success():
    result = reconcile_run({}, {"test_mode": "stub"})
    assert result["status"] == "FAIL"
    assert result["reconciliation"]["passed"] is False


def test_unresolved_order_is_incomplete_not_confirmed():
    expected, observed = clean_evidence()
    observed["orders"][0]["status"] = "MANUAL_REVIEW"
    result = reconcile_run(expected, observed)
    assert result["status"] == "INCOMPLETE" and result["unresolved_count"] == 1
    assert not result["reconciliation"]["passed"]


def test_real_mode_cannot_claim_unavailable_owner_bindings():
    expected, observed = clean_evidence()
    observed["test_mode"] = "real"
    result = reconcile_run(expected, observed)
    assert result["status"] == "INCOMPLETE"
    assert "pending owner review" in result["dependency"]


def test_reversed_cancelled_order_reconciles():
    expected, observed = clean_evidence()
    observed["orders"][0]["status"] = "CANCELLED"
    observed["reservations"][0]["state"] = "RELEASED"
    observed["payments"][0]["status"] = "REVERSED"
    observed["payment_guards"]["fixture-order"]["quiesced"] = True
    observed["ledger"].append(
        {
            **observed["ledger"][0],
            "entry_id": "fixture-reversal",
            "kind": "REVERSAL",
            "amount_minor": -100,
        }
    )
    observed["stocks"][0].update(on_hand=10, available=10)
    result = reconcile_run(expected, observed)
    assert result["status"] == "PASS"


def test_active_held_stock_is_conserved_but_order_is_unresolved():
    expected, observed = clean_evidence()
    observed["orders"][0]["status"] = "PAYMENT_PENDING"
    observed["reservations"][0]["state"] = "ACTIVE"
    observed["payments"][0]["status"] = "PENDING"
    observed["ledger"] = []
    observed["stocks"][0].update(on_hand=10, reserved=1, available=9)
    result = reconcile_run(expected, observed)
    assert result["status"] == "INCOMPLETE"
    assert result["reconciliation"]["invariant_failures"] == []


def test_static_dirty_expectations_detect_imputation_and_wrong_selection():
    fixture = json.loads(
        (ROOT / "contracts/fixtures/catalog/dirty_catalogue.json").read_text(encoding="utf-8")
    )
    cases = {case["case_id"]: case for case in fixture["cases"]}
    for name in (
        "ordinary-price",
        "retail-is-not-sale-fallback",
        "duplicate-pid-latest",
        "absent-size-colour-material",
    ):
        expected = cases[name]["expected"]
        explicit_output_double = copy.deepcopy(expected)
        assert compare_fixture_output(expected, explicit_output_double)["passed"]
    corrupted = copy.deepcopy(cases["retail-is-not-sale-fallback"]["expected"])
    corrupted["normalized_fields"]["price_minor"] = 99900
    assert not compare_fixture_output(cases["retail-is-not-sale-fallback"]["expected"], corrupted)[
        "passed"
    ]
    corrupted = copy.deepcopy(cases["absent-size-colour-material"]["expected"])
    corrupted["normalized_fields"]["size"] = "M"
    assert not compare_fixture_output(cases["absent-size-colour-material"]["expected"], corrupted)[
        "passed"
    ]


def test_oracle_comparison_distinguishes_numeric_type_and_null():
    assert not compare_fixture_output({"price_minor": 37900}, {"price_minor": 37900.0})["passed"]
    assert not compare_fixture_output({"price_minor": None}, {"price_minor": 0})["passed"]


@pytest.mark.parametrize("field", ["silver_events", "active_gold"])
def test_malformed_event_identity_fails_visibly_without_sorting_errors(field):
    expected, observed = clean_evidence()
    if field == "silver_events":
        observed[field].append({"event_id": None, "content_sha256": "f" * 64})
    else:
        observed[field]["membership_ids"].extend([None, "unexpected-string"])
    result = reconcile_run(expected, observed)
    assert result["status"] == "FAIL"
    assert any(
        item.startswith("MISSING_OR_INVALID_EVIDENCE")
        for item in result["reconciliation"]["invariant_failures"]
    )


def test_quiesced_payment_cannot_remain_successful_and_unreversed():
    expected, observed = clean_evidence()
    observed["payment_guards"]["fixture-order"]["quiesced"] = True
    result = reconcile_run(expected, observed)
    assert result["status"] == "FAIL"
    assert (
        "QUIESCED_PAYMENT_STATE_CONFLICT:fixture-payment"
        in result["reconciliation"]["invariant_failures"]
    )


def test_payment_and_ledger_currency_must_match_the_authoritative_order():
    expected, observed = clean_evidence()
    observed["payments"][0]["currency"] = "USD"
    observed["ledger"][0]["currency"] = "USD"
    result = reconcile_run(expected, observed)
    assert result["status"] == "FAIL"
    assert (
        "PAYMENT_CURRENCY_MISMATCH:fixture-payment"
        in result["reconciliation"]["invariant_failures"]
    )
