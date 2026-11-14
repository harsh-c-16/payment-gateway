"""Explicit Gemini HTTP doubles; never a claim of live model quality."""

import json
from time import monotonic

import httpx
import pytest

from services.conversation.intent import blank_intent
from services.conversation.intent_fallback import ModelFailure
from services.conversation.shopping_dialogue import merged_intent
from services.conversation.shopping_llm import (
    GeminiShoppingProvider,
    SearchArguments,
    validate_plan,
)
from shared.contracts.shopping import ShoppingMemory
from tests.conversation.workflow_doubles import WorkflowProviderDouble


def reply(name="search_catalog", args=None):
    return {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {
                    "parts": [{"functionCall": {"name": name, "args": args or {"query": "shirt"}}}]
                },
            }
        ],
        "usageMetadata": {"promptTokenCount": 200, "candidatesTokenCount": 20},
    }


def test_provider_sends_bounded_history_and_only_read_tools():
    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(200, json=reply())

    provider = GeminiShoppingProvider(
        "synthetic-key",
        mode="stub",
        purpose="contract_test",
        transport=httpx.MockTransport(transport),
    )
    memory = ShoppingMemory(
        messages=[{"role": "user", "text": "gift"}] * 40,
        intent={**blank_intent("shirt"), "colour": "blue"},
    )
    result = provider.plan(
        "more options", memory, WorkflowProviderDouble().facets, deadline=monotonic() + 20
    )
    assert result.name == "search_catalog" and len(requests) == 1
    body = json.loads(requests[0].content)
    data = json.loads(body["contents"][0]["parts"][0]["text"])
    assert len(data["history"]) == 12 and data["preferences"]["colour"] == "blue"
    tools = {t["name"] for t in body["tools"][0]["functionDeclarations"]}
    assert tools == {"search_catalog", "ask_question", "product_details", "respond"}
    assert "synthetic-key" not in str(body) and "synthetic-key" not in str(provider.provenance())


@pytest.mark.parametrize("kind", ["http", "timeout", "invalid", "multiple", "unknown", "large"])
def test_provider_failures_have_one_attempt_and_no_raw_leaks(kind):
    calls = []

    def transport(request):
        calls.append(request)
        if kind == "http":
            return httpx.Response(429, text="private provider body synthetic-key")
        if kind == "timeout":
            raise httpx.ReadTimeout("private provider body synthetic-key")
        if kind == "invalid":
            return httpx.Response(200, json={"candidates": [{"finishReason": "MAX_TOKENS"}]})
        if kind == "multiple":
            result = reply()
            result["candidates"][0]["content"]["parts"] *= 2
            return httpx.Response(200, json=result)
        if kind == "unknown":
            return httpx.Response(200, json=reply("checkout"))
        return httpx.Response(200, text="x" * 65537)

    p = GeminiShoppingProvider(
        "synthetic-key",
        mode="stub",
        purpose="contract_test",
        transport=httpx.MockTransport(transport),
    )
    with pytest.raises(ModelFailure) as caught:
        p.plan(
            "shirt", ShoppingMemory(), WorkflowProviderDouble().facets, deadline=monotonic() + 20
        )
    assert len(calls) == 1 and "synthetic-key" not in str(caught.value)


@pytest.mark.parametrize(
    "name,args",
    [
        ("checkout", {}),
        ("search_catalog", {"query": "shirt", "url": "http://arbitrary.test"}),
        ("search_catalog", {"filters": {"max_price_minor": True}}),
        ("product_details", {"references": [0]}),
        ("product_details", {"references": [1, 2, 3, 4]}),
        ("ask_question", {"question": "This costs INR 99. Would you like it?"}),
        ("ask_question", {"question": "It is in stock, shall we buy it?"}),
    ],
)
def test_model_cannot_invent_tools_or_product_claims(name, args):
    with pytest.raises(ModelFailure):
        validate_plan(name, args)


def test_refinement_preserves_omitted_constraints_and_strict_budget():
    dictionary = WorkflowProviderDouble().facets
    memory = ShoppingMemory(
        intent={**blank_intent("shirt"), "colour": "blue", "max_price_minor": 99999}
    )
    args = SearchArguments.model_validate({"more": True})
    assert merged_intent(args, memory, "more options", dictionary) == memory.intent
    broadened = SearchArguments.model_validate({"query": "all products", "more": True})
    assert merged_intent(broadened, memory, "more options", dictionary) == memory.intent
    args = SearchArguments.model_validate({"query": "shirt", "filters": {"max_price_minor": 50000}})
    intent = merged_intent(args, memory, "under 500 rupees", dictionary)
    assert intent["colour"] == "blue" and intent["max_price_minor"] == 49999


@pytest.mark.parametrize(
    "change,text",
    [
        ({"colour": None}, "more options"),
        ({"colour": "ultraviolet"}, "ultraviolet shirts"),
        ({"colour": "blue"}, "red shirt"),
        ({"max_price_minor": 200000}, "more options"),
    ],
)
def test_unrequested_filter_relaxation_or_unknown_facets_are_rejected(change, text):
    memory = ShoppingMemory(
        intent={**blank_intent("shirt"), "colour": "red", "max_price_minor": 99999}
    )
    with pytest.raises(ModelFailure):
        merged_intent(
            SearchArguments.model_validate({"filters": change}),
            memory,
            text,
            WorkflowProviderDouble().facets,
        )
