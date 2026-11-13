"""Context-aware shopping: real rules; synthetic dictionary/results are explicit doubles."""

import pytest

from services.conversation.intent import blank_intent
from services.conversation.shopping import resolve
from shared.contracts.shopping import ShoppingMemory
from tests.conversation.workflow_doubles import WorkflowProviderDouble


@pytest.fixture
def dictionary():
    return WorkflowProviderDouble().facets


def memory(**intent):
    return ShoppingMemory(
        intent={**blank_intent("shirts"), "max_price_minor": 99999, **intent},
        products=[
            {"sku": "TEST-FIRST", "title": "Cotton shirt", "price_minor": 40000},
            {"sku": "TEST-SECOND", "title": "Formal shirt", "price_minor": 60000},
        ],
        seen_skus=["TEST-FIRST", "TEST-SECOND"],
    )


def test_vague_request_asks_before_search_and_accepts_subject_later(dictionary):
    first = resolve("I need a gift under 1000 rupees", ShoppingMemory(), dictionary)
    assert first.result.outcome == "clarification_required"
    assert "query_text" in first.result.missing_fields
    assert "What kind of product" in first.question
    pending = ShoppingMemory(intent=first.result.intent, pending=first.result.missing_fields)
    second = resolve("watches", pending, dictionary)
    assert second.result.outcome == "valid"
    assert second.result.intent["query_text"] == "watches"
    assert second.result.intent["max_price_minor"] == 99999


def test_answering_budget_does_not_lose_unanswered_subject_question(dictionary):
    first = resolve("I need something", ShoppingMemory(), dictionary)
    pending = ShoppingMemory(intent=first.result.intent, pending=first.result.missing_fields)
    budget = resolve("under 1000 rupees", pending, dictionary)
    assert budget.result.outcome == "clarification_required"
    assert "query_text" in budget.result.missing_fields
    pending.intent, pending.pending = budget.result.intent, budget.result.missing_fields
    assert resolve("bluetooth speakers", pending, dictionary).result.outcome == "valid"


@pytest.mark.parametrize(
    "utterance,field,value",
    [
        ("Only blue ones", "colour", "blue"),
        ("Under 500 rupees", "max_price_minor", 49999),
        ("Material cotton", "material", "cotton"),
    ],
)
def test_explicit_refinement_keeps_previous_product_and_other_filters(
    dictionary, utterance, field, value
):
    result = resolve(utterance, memory(), dictionary).result
    assert result.outcome == "valid"
    assert result.intent["query_text"] == "shirts"
    assert result.intent[field] == value
    if field != "max_price_minor":
        assert result.intent["max_price_minor"] == 99999


def test_cheaper_and_selected_reference_preserve_hard_filters(dictionary):
    previous = memory(colour="blue")
    previous.selected_sku = "TEST-SECOND"
    result = resolve("Cheaper than this one", previous, dictionary).result
    assert result.outcome == "valid"
    assert result.intent["max_price_minor"] == 59999
    assert result.intent["colour"] == "blue"


def test_more_and_similarity_have_real_search_context(dictionary):
    previous = memory(colour="blue")
    more = resolve("Do we have more options?", previous, dictionary)
    assert more.more and more.result.intent == previous.intent
    similar = resolve("More like the second one", previous, dictionary)
    assert similar.more and similar.selected_sku == "TEST-SECOND"
    assert similar.result.intent["query_text"] == "Formal shirt"
    assert similar.result.intent["colour"] == "blue"


def test_ambiguous_product_reference_asks_instead_of_guessing(dictionary):
    result = resolve("Show similar products", memory(), dictionary)
    assert "reference" in result.result.missing_fields


def test_explicit_reset_and_removing_a_filter_are_distinct(dictionary):
    previous = memory(colour="blue")
    cleared = resolve("Any colour", previous, dictionary).result
    assert cleared.outcome == "valid" and cleared.intent["colour"] is None
    assert cleared.intent["max_price_minor"] == 99999
    new = resolve("New search: watches", previous, dictionary).result
    assert new.outcome == "valid" and new.intent["colour"] is None
    assert new.intent["max_price_minor"] is None and new.intent["query_text"] == "watches"


@pytest.mark.parametrize("utterance", ["Buy the first one", "Blue or red", "Waterproof ones"])
def test_chat_never_purchases_or_silently_drops_unsupported_constraints(dictionary, utterance):
    result = resolve(utterance, memory(), dictionary).result
    assert result.outcome == "clarification_required"


def test_option_limit_requires_refinement(dictionary):
    previous = memory()
    previous.seen_skus = [f"SEEN-{i}" for i in range(200)]
    assert "limit" in resolve("More options", previous, dictionary).result.missing_fields


def test_new_product_words_replace_subject_without_requiring_a_known_noun(dictionary):
    result = resolve("bluetooth speakers", memory(colour="blue"), dictionary).result
    assert result.outcome == "valid"
    assert result.intent["query_text"] == "bluetooth speakers"
    assert result.intent["colour"] is None


def test_cheaper_does_not_crash_on_an_unpriced_product(dictionary):
    previous = memory()
    previous.products = [{"sku": "UNPRICED", "title": "Unknown shirt", "price_minor": None}]
    result = resolve("Cheaper than this one", previous, dictionary).result
    assert "max_price_minor" in result.missing_fields


@pytest.mark.parametrize("slot,answer,expected", [("size", "M", "M"), ("brand", "Acme", "acme")])
def test_short_answer_uses_the_slot_from_the_last_question(dictionary, slot, answer, expected):
    dictionary["brands"] = [{"key": "acme", "label": "Acme"}]
    previous = memory(category="clothing")
    previous.pending = [slot]
    result = resolve(answer, previous, dictionary).result
    assert result.outcome == "valid"
    assert result.intent[slot] == expected
    assert result.intent["query_text"] == "shirts"
