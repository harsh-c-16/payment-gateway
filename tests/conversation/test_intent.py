from uuid import uuid4

import pytest

from services.conversation.intent import extract_intent

from .workflow_doubles import WorkflowProviderDouble


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "blue cotton clothing size M under 500 rupees",
            {
                "category": "clothing",
                "size": "M",
                "colour": "blue",
                "material": "cotton",
                "max_price_minor": 49999,
            },
        ),
        ("clothing at most 500.01 rupees", {"max_price_minor": 50001}),
        ("clothing below 500.01 rupees", {"max_price_minor": 50000}),
        ("clothing up to 0 rupees", {"max_price_minor": 0}),
        ("furniture made of cotton lycra", {"material": "cotton lycra", "size": None}),
        ("clothing size medium", {"size": "M"}),
        ("clothing gray", {"colour": "grey"}),
        ("clothing size XXXL", {"size": "XXXL"}),
        ("clothing size:M under 1,000 rupees", {"size": "M", "max_price_minor": 99999}),
    ],
)
def test_real_rules_preserve_hard_slots(text, expected):
    result = extract_intent(text, None, WorkflowProviderDouble().facets)
    assert result.outcome == "valid"
    assert {f: result.intent[f] for f in expected} == expected
    assert result.llm_call_count == 0 and result.llm_ms is None


@pytest.mark.parametrize(
    "text",
    [
        "furniture size medium",
        "size medium",
        "clothing size XXXXXL",
        "clothing colour ultraviolet",
        "clothing material unobtainium",
        "category teleporters",
        "clothing size M or L",
        "not blue clothing",
        "waterproof clothing",
        "clothing under 1.001 rupees",
        "clothing price $10",
        "clothing under 0 rupees",
        "clothing under 9999999999999999999999 rupees",
        "clothing below -5 rupees",
        "",
        f"checkout quote {uuid4()}",
        "buy blue clothing",
        "clothing brand imaginary",
        "clothing color=ultraviolet",
        "clothing colour red blue",
        "clothing size:XXXXXL",
        "clothing under 500e3 rupees",
        "clothing under 1,00 rupees",
    ],
)
def test_ambiguous_or_unknown_explicit_constraints_clarify(text):
    result = extract_intent(text, None, WorkflowProviderDouble().facets)
    assert result.outcome == "clarification_required"
    assert result.missing_fields and result.llm_call_count == 0
