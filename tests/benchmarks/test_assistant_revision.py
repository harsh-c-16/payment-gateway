"""Independent assertions for P3 labels and synthetic workflow specifications.

These validate authored expectations, not production parser/workflow behavior.
No runtime model or provider is invoked. Provisional provider schemas are explicit.
"""

import copy
import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from shared.contracts.conversation import (
    CartQuoteRequest,
    CartSnapshot,
    CartUpdateRequest,
    CheckoutRequest,
)
from tests.contracts.provisional import CREATE_ORDER, ORDER, QUOTE, QUOTE_REQUEST, SEARCH_REQUEST

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "contracts/fixtures/assistant"
DOCUMENT = json.loads((FIXTURES / "scenarios.json").read_text(encoding="utf-8"))
ROWS = DOCUMENT["scenarios"]
BY_ID = {row["scenario_id"]: row for row in ROWS}
SLOTS = {"category", "size", "colour", "material", "max_price_minor", "occasion"}
ALLOWED_SIZES = {"XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "FREE_SIZE", "ONE_SIZE"}


def canonical_hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def validate(schema, value):
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)


def matching_skus(snapshot, view, labels):
    """Test oracle for these finite literal rows; never import a catalogue filter."""
    selected = set()
    for product in snapshot["products"]:
        if product["sku"] not in view:
            continue
        if (
            not product["active"]
            or not product["stock_available"]
            or product["price_minor"] is None
        ):
            continue
        if any(
            labels[key] is not None and labels[key] != product[key]
            for key in ("category", "size", "colour", "material")
        ):
            continue
        if (
            labels["max_price_minor"] is not None
            and product["price_minor"] > labels["max_price_minor"]
        ):
            continue
        selected.add(product["sku"])
    return selected


def test_fixture_schema_and_honest_review_metadata():
    schema = json.loads((FIXTURES / "scenario.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    validate(schema, DOCUMENT)
    assert set(BY_ID) == {f"A-{number:03}" for number in range(1, 61)}
    assert DOCUMENT["automated_llm_judge_review"] == "COMPLETE"
    assert DOCUMENT["human_label_review"] == "PENDING_NOT_PERFORMED"
    assert DOCUMENT["quality_evaluation"] == "NOT_RUN" and DOCUMENT["frozen"] is False


@pytest.mark.parametrize("row", ROWS, ids=lambda r: r["scenario_id"])
def test_every_scenario_slots_are_justified_by_request_or_structured_action(row):
    labels = row["intent_labels"]
    n = int(row["scenario_id"][2:])
    assert set(labels) == SLOTS
    assert labels["size"] is None or (
        labels["category"] == "clothing" and labels["size"] in ALLOWED_SIZES
    )
    if n >= 35:
        # Medium without category is unresolved; action quote totals are not search budgets.
        assert all(value is None for value in labels.values())
    else:
        text = row["text"]
        category = (
            "clothing"
            if "clothing" in text and "whether I mean" not in text
            else "furniture"
            if "furniture" in text
            else None
        )
        assert labels["category"] == category
        size_match = re.search(r"\bsize ([MLS])\b", text)
        assert labels["size"] == (size_match.group(1) if size_match else None)
        # Whole compound values and negations are intentionally handled explicitly.
        colour = (
            "multicolor"
            if "multicolor" in text
            else next((c for c in ("blue", "black", "grey") if c in text), None)
        )
        material = (
            "cotton lycra" if "cotton lycra" in text else "cotton" if "cotton" in text else None
        )
        assert labels["colour"] == colour
        assert labels["material"] == material
        occasion = "celebration" if "celebration" in text else "party" if "party" in text else None
        assert labels["occasion"] == occasion
        amount = re.search(r"(\d+) rupees", text)
        cap = int(amount.group(1)) * 100 if amount else None
        if cap is not None and re.search(r"\b(under|below)\b", text):
            cap -= 1
        assert labels["max_price_minor"] == cap
    assert row["optional_labels"] == {"brand": None, "category_path_prefix": None}
    assert row["reviewer"] is None and row["reviewed_at"] is None
    assert row["catalogue_binding"] is None and row["relevance_labels"] is None
    assert row["generative_call_budget"]["fixed"] == 0
    if row["control"] != "search":
        assert row["generative_call_budget"]["assist"] == 0


def test_valid_positive_counts_still_meet_original_six_slot_plan():
    counts = Counter(
        slot for row in ROWS for slot, value in row["intent_labels"].items() if value is not None
    )
    assert counts == dict(
        category=28, size=14, colour=16, material=16, max_price_minor=22, occasion=16
    )
    assert all(counts[slot] >= 10 for slot in SLOTS)


@pytest.mark.parametrize("sid", ["A-024", "A-028"])
def test_unsupported_size_is_preserved_for_clarification_without_search(sid):
    row = BY_ID[sid]
    assert row["intent_labels"]["category"] == "clothing" and row["intent_labels"]["size"] is None
    assert row["unresolved_constraints"] == [
        {"slot": "size", "raw_value": "XXXXXL", "reason": "unsupported_apparel_size"}
    ]
    assert row["expected_outcome"] == "clarification"
    assert row["expected_behavior"]["search_allowed"] is False
    assert row["expected_behavior"]["search_call_count"] == 0


def test_price_boundaries_include_paise_below_and_exclude_equality():
    assert BY_ID["A-001"]["intent_labels"]["max_price_minor"] == 49999
    assert BY_ID["A-015"]["intent_labels"]["max_price_minor"] == 49999
    assert BY_ID["A-013"]["intent_labels"]["max_price_minor"] == 50000
    assert BY_ID["A-002"]["expected_behavior"]["expected_hit_skus"] == []
    assert BY_ID["A-003"]["expected_behavior"]["expected_hit_skus"] == []
    product = copy.deepcopy(DOCUMENT["test_catalogue"]["products"][0])
    product["price_minor"] = 49999
    labels = BY_ID["A-001"]["intent_labels"]
    assert matching_skus({"products": [product]}, [product["sku"]], labels) == {product["sku"]}
    product["price_minor"] = 50000
    assert matching_skus({"products": [product]}, [product["sku"]], labels) == set()


@pytest.mark.parametrize(
    "row", [r for r in ROWS if "test_fixture_binding" in r], ids=lambda r: r["scenario_id"]
)
def test_pinned_search_expectations_match_only_supplied_eligible_rows(row):
    snapshot = DOCUMENT["test_catalogue"]
    assert canonical_hash(snapshot) == DOCUMENT["test_catalogue_sha256"]
    binding = row["test_fixture_binding"]
    assert binding["snapshot_sha256"] == canonical_hash(snapshot)
    assert binding["binding_sha256"] == canonical_hash(
        {k: v for k, v in binding.items() if k != "binding_sha256"}
    )
    expected = set(row["expected_behavior"]["expected_hit_skus"])
    assert matching_skus(snapshot, binding["view_skus"], row["intent_labels"]) == expected
    assert row["expected_outcome"] == (
        "display_fixture_matches" if expected else "honest_no_results"
    )
    assert matching_skus(snapshot, [], row["intent_labels"]) == set()
    assert (
        row["expected_behavior"]["on_unavailable_dependency"]
        == "dependency_error_not_empty_results"
    )
    assert "occasion" not in snapshot["products"][0]  # no universal occasion classification


def test_same_filters_with_empty_or_missing_facets_never_relax_intent():
    for a, b in [(21, 25), (22, 26), (23, 27)]:
        match, empty = BY_ID[f"A-{a:03}"], BY_ID[f"A-{b:03}"]
        assert match["intent_labels"] == empty["intent_labels"]
        assert match["expected_outcome"] == "display_fixture_matches"
        assert empty["expected_outcome"] == "honest_no_results"
    assert BY_ID["A-022"]["intent_labels"]["material"] == "cotton lycra"
    assert BY_ID["A-023"]["intent_labels"]["colour"] == "multicolor"


def test_malicious_descriptions_are_bound_as_data_and_never_purchase_authority():
    for number in range(29, 35):
        row = BY_ID[f"A-{number:03}"]
        assert row["untrusted_input"]["value"] == row["untrusted_product_description"]
        assert row["untrusted_input"]["sku"] in row["expected_behavior"]["expected_hit_skus"]
        assert row["untrusted_input"]["trust"] == "untrusted_data"
        assert set(row["expected_behavior"]["forbidden_actions"]) == {
            "change_price",
            "cart_update",
            "quote",
            "checkout",
            "order_create",
            "execute_product_text",
        }
        assert row["intent_labels"]["max_price_minor"] == 49999


@pytest.mark.parametrize(
    "row", [r for r in ROWS if "offline_workflow_fixture" in r], ids=lambda r: r["scenario_id"]
)
def test_workflow_fixture_hashes_requests_and_test_only_provider_shapes(row):
    fixture = row["offline_workflow_fixture"]
    assert canonical_hash(fixture) == row["offline_workflow_fixture_sha256"]
    assert fixture["synthetic"] is True and fixture["test_mode"] == "explicit_fixture"
    assert fixture["outcome_status"] == "expected_only_NOT_RUN"
    if "cart" in fixture:
        CartSnapshot.model_validate(fixture["cart"])
        validate(ORDER, fixture["order_snapshot"])
    if fixture.get("quote"):
        validate(QUOTE, fixture["quote"])
        quote = fixture["quote"]
        assert (
            datetime.fromisoformat(quote["created_at"].replace("Z", "+00:00"))
            < datetime.fromisoformat(fixture["clock_utc"].replace("Z", "+00:00"))
            < datetime.fromisoformat(quote["expires_at"].replace("Z", "+00:00"))
        )
        assert quote["total_amount_minor"] == sum(
            line["line_total_minor"] for line in quote["lines"]
        )
    if "provider_quote_request" in fixture:
        validate(QUOTE_REQUEST, fixture["provider_quote_request"])
    if "provider_order_request" in fixture:
        validate(CREATE_ORDER, fixture["provider_order_request"]["body"])
    request = fixture["request"]
    if row["control"] == "cart_add":
        CartUpdateRequest.model_validate(request["body"])
        assert (
            fixture["repeat_identical_request"]
            and row["expected_behavior"]["logical_cart_effects"] == 1
        )
    elif row["control"] == "quote":
        CartQuoteRequest.model_validate(request["body"])
        assert (
            fixture["cart"]["lines"][0]["display_price_minor"]
            != fixture["quote"]["lines"][0]["unit_price_minor"]
        )
    elif row["control"] == "checkout_unconfirmed":
        with pytest.raises(ValidationError, match="explicit confirmation"):
            CheckoutRequest.model_validate(request["body"])
        assert row["expected_behavior"]["order_create_calls"] == 0
    elif row["control"] in {"checkout_confirmed", "stale_cart_version"}:
        CheckoutRequest.model_validate(request["body"])
        confirmation, quote = fixture["confirmation"], fixture["quote"]
        assert confirmation["confirmed"] is True
        assert confirmation["quote_id"] == request["body"]["quote_id"] == quote["quote_id"]
        assert (
            confirmation["cart_version"]
            == request["body"]["expected_cart_version"]
            == quote["cart_version"]
        )
        assert request["body"]["confirmation_id"] == confirmation["confirmation_id"]
        assert fixture["displayed_quote"]["total_amount_minor"] == quote["total_amount_minor"]
        if row["control"] == "stale_cart_version":
            assert fixture["cart"]["version"] != quote["cart_version"]
            assert row["expected_behavior"]["http_status"] == 409
            assert row["expected_behavior"]["order_create_calls"] == 0
        else:
            assert fixture["cart"]["version"] == quote["cart_version"]


def test_response_loss_creation_and_status_read_are_distinct():
    create = BY_ID["A-055"]
    read = BY_ID["A-059"]
    assert create["control"] == "checkout_confirmed"
    assert create["fault"] == "order_create_response_lost"
    assert read["fault"] == "order_status_response_lost"
    for row, method in [(create, "POST"), (read, "GET")]:
        script = row["offline_workflow_fixture"]["script"]
        assert script[0]["request"] == script[1]["request"]
        assert script[0]["request"]["method"] == method
        assert script[0]["response"] == "ReadTimeout"
        assert row["dependency_failure"]["unknown_after_first_attempt"]
        assert (
            row["expected_behavior"]["reported_order_status"]
            == script[1]["response"]["body"]["status"]
        )
    validate(CREATE_ORDER, create["dependency_failure"]["operation"]["body"])
    assert create["expected_behavior"]["order_create_calls"] == 2
    assert create["expected_behavior"]["logical_order_effects"] == 1
    assert read["expected_behavior"]["order_create_calls"] == 0


def test_dependency_failures_and_analytics_isolation_do_not_invent_status():
    for sid in ("A-053", "A-057"):
        row = BY_ID[sid]
        validate(SEARCH_REQUEST, row["dependency_failure"]["operation"]["body"])
        assert row["dependency_failure"]["name"] == "catalogue"
        assert row["expected_behavior"]["expected_hit_skus"] is None
        assert row["expected_outcome"] == "catalogue_dependency_error"
    for sid in ("A-054", "A-058"):
        row = BY_ID[sid]
        assert row["dependency_failure"]["operation"]["method"] == "GET"
        assert row["dependency_failure"]["unknown_after"] == ["current_order_status"]
        assert row["expected_behavior"]["reported_order_status"] is None
    for sid, status in (("A-056", "CONFIRMED"), ("A-060", "CANCELLED")):
        row = BY_ID[sid]
        assert row["dependency_failure"]["name"] == "analytics"
        assert row["dependency_failure"]["orders_health"] == "healthy"
        assert row["expected_behavior"]["analytics_calls"] == 0
        assert row["expected_behavior"]["reported_order_status"] == status
        assert row["offline_workflow_fixture"]["script"][0]["response"]["body"]["status"] == status


def test_adjudication_preserves_history_all_rows_hashes_and_subjective_concerns():
    original_bytes = (FIXTURES / "history/scenarios-v1.json").read_bytes()
    original = json.loads(original_bytes)
    audit = json.loads((FIXTURES / "adjudication-v2.json").read_text(encoding="utf-8"))
    assert (
        hashlib.sha256(original_bytes.replace(b"\r\n", b"\n")).hexdigest()
        == audit["original_fixture_lf_sha256"]
    )
    revised = (FIXTURES / "scenarios.json").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(revised).hexdigest() == audit["revised_fixture_lf_sha256"]
    assert len(audit["scenarios"]) == 60
    assert Counter(row["llm_judge_result"] for row in audit["scenarios"]) == {
        "PASS": 29,
        "CONCERN": 31,
    }
    for before, after, decision in zip(
        original["scenarios"], ROWS, audit["scenarios"], strict=True
    ):
        assert before == decision["original_scenario"]
        assert decision["scenario_id"] == after["scenario_id"] == before["scenario_id"]
        assert decision["original_labels"] == before["intent_labels"]
        assert decision["revised_labels"] == after["intent_labels"]
        assert decision["original_outcome"] == before["expected_outcome"]
        assert decision["revised_outcome"] == after["expected_outcome"]
        assert canonical_hash(after) == decision["revised_scenario_sha256"]
        assert decision["deterministic_review_result"] == "PASS"
        assert decision["llm_judge_result"] in {"PASS", "CONCERN", "FAIL"}
        assert decision["confidence"] in {"HIGH", "MEDIUM", "LOW"}
        assert decision["source_specification_sections"] and decision["rationale"]
        assert decision["human_approval"] is False
        if decision["unresolved_ambiguity"]:
            assert decision["llm_judge_result"] == "CONCERN"
            assert decision["confidence"] == "MEDIUM"
            for ambiguity in decision["unresolved_ambiguity"]:
                assert len(ambiguity["alternatives"]) >= 2
                assert ambiguity["selected"] and ambiguity["reason"]


def test_audit_hash_domains_and_fixture_reference_contract():
    audit = json.loads((FIXTURES / "adjudication-v2.json").read_text(encoding="utf-8"))
    original = json.loads((FIXTURES / "history/scenarios-v1.json").read_bytes())
    assert canonical_hash(original) == audit["original_fixture_canonical_sha256"]
    assert canonical_hash(DOCUMENT) == audit["revised_fixture_canonical_sha256"]
    assert audit["revised_fixture_canonical_sha256"] != audit["revised_fixture_lf_sha256"]
    # Changing formatting preserves canonical content, but changes raw byte identity.
    compact = json.dumps(DOCUMENT, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert hashlib.sha256(compact.encode()).hexdigest() == audit["revised_fixture_canonical_sha256"]
    contract = audit["price_contract_verification"]
    assert contract["fixture_comparison"] == "price_minor <= max_price_minor"
    assert contract["shared_contract_explicit_comparison_operator"] is None
    assert contract["conflicting_normative_rule_found"] is False
    assert contract["unresolved_contract_clarification"]
    refs = audit["reference_verification"]
    assert refs["current_revised_bundles"] and refs["preserved_historical_bundles"]
    for reference in refs["current_revised_bundles"]:
        assert reference["artifact_raw_sha256"] == audit["revised_fixture_sha256"]
        assert reference["historical_source_raw_sha256"] == audit["revised_fixture_sha256"]
        assert reference["assistant_canonical_sha256"] == canonical_hash(DOCUMENT)
    for reference in refs["preserved_historical_bundles"]:
        assert reference["artifact_raw_sha256"] != audit["revised_fixture_sha256"]
        assert reference["assistant_canonical_sha256"] != canonical_hash(DOCUMENT)
    assert refs["configuration"]["workloads.W-AGENT.template_sha256"] is None
    assert refs["configuration"]["retrieval.label_sha256"] is None


@pytest.mark.parametrize(
    "mutation", ["invalid_size", "invented_optional_label", "false_human_approval"]
)
def test_fixture_schema_rejects_regressions(mutation):
    document = copy.deepcopy(DOCUMENT)
    if mutation == "invalid_size":
        document["scenarios"][0]["intent_labels"]["size"] = "XXXXXL"
    elif mutation == "invented_optional_label":
        document["scenarios"][0]["optional_labels"]["brand"] = "invented"
    else:
        document["human_label_review"] = "COMPLETE"
    schema = json.loads((FIXTURES / "scenario.schema.json").read_text())
    assert list(Draft202012Validator(schema).iter_errors(document))
