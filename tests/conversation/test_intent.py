from uuid import uuid4

import pytest

from services.conversation import intent
from services.conversation.intent import extract_intent

from .workflow_doubles import WorkflowProviderDouble


@pytest.mark.parametrize("text", [
    "can we have it in black color", "can we have it in black colour?",
    "black color please", "color black", "colour: black",
])
def test_colour_value_before_or_after_cue_is_not_missing(text):
    result = extract_intent(text, None, WorkflowProviderDouble().facets)
    assert result.intent["colour"] == "black"
    assert "colour" not in result.missing_fields


@pytest.mark.parametrize("cue", ["color", "colour"])
@pytest.mark.parametrize("value", ["black", "blue", "grey"])
@pytest.mark.parametrize("pattern", [
    "can i get in {value} {cue} only", "{cue} {value} only",
    "{cue} only {value}", "only {value} {cue} please",
])
def test_facet_focus_words_work_in_both_orders(cue, value, pattern):
    result = extract_intent(
        pattern.format(cue=cue, value=value), None, WorkflowProviderDouble().facets
    )
    assert result.intent["colour"] == value
    assert "colour" not in result.missing_fields


@pytest.mark.parametrize(
    "text", [
        "red black color", "black color ultraviolet", "color ultraviolet",
        "red black color only", "black color ultraviolet only", "color only ultraviolet",
    ]
)
def test_colour_cue_still_rejects_conflicting_or_unknown_values(text):
    dictionary = WorkflowProviderDouble().facets
    dictionary["colours"] = list(dict.fromkeys([*dictionary["colours"], "red", "black"]))
    result = extract_intent(text, None, dictionary)
    assert "colour" in result.missing_fields


@pytest.mark.parametrize("text", ["not black color only", "black or blue color only"])
def test_focus_words_do_not_hide_negation_or_alternatives(text):
    result = extract_intent(text, None, WorkflowProviderDouble().facets)
    assert "constraints" in result.missing_fields


def test_phrase_matching_keeps_compounds_and_boundaries_without_scanning_absent_regexes(
    monkeypatch,
):
    mapping = {f"absent-{i}": f"absent-{i}" for i in range(2000)}
    mapping.update({"cotton lycra": "compound", "cotton": "cotton", "wool": "wool"})
    patterns = []
    search = intent.re.search

    def record(pattern, text):
        patterns.append(pattern)
        return search(pattern, text)

    monkeypatch.setattr(intent.re, "search", record)
    assert intent.phrases("cotton lycra cottonwood", mapping) == {"compound"}
    assert len(patterns) == 2
    assert not any("absent" in pattern for pattern in patterns)


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
        "clothing under 100 USD",
        "clothing under 100 euros",
        "clothing under 100 rupees and above 50 rupees",
        "clothing colour blue and colour ultraviolet",
        "clothing material cotton and fabric unobtainium",
        "clothing size M and size XXXXXL",
        "clothing size M and size L",
        "clothing up to 500 rupees and below -5 rupees",
    ],
)
def test_ambiguous_or_unknown_explicit_constraints_clarify(text):
    result = extract_intent(text, None, WorkflowProviderDouble().facets)
    assert result.outcome == "clarification_required"
    assert result.missing_fields and result.llm_call_count == 0
