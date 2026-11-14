"""Consumer regressions with explicit HTTP doubles; no live catalogue claim."""

import json
from time import monotonic
from uuid import uuid4

import pytest

from services.conversation.intent import extract_intent
from services.conversation.provider_contracts import ContractViolation
from services.conversation.workflow import FixedWorkflow
from shared.contracts.conversation import TurnRequest

from .intent_doubles import IntentSpy
from .workflow_doubles import WorkflowProviderDouble


@pytest.fixture
def search_context(context):
    return context.model_copy(update={"session_id": str(uuid4())})


@pytest.fixture
def noisy_provider():
    provider = WorkflowProviderDouble()
    provider.facets["brands"] = [
        {"key": "acme", "label": "Acme"},
        {"key": "blue", "label": "Blue"},
        {"key": "skin", "label": "Skin"},
        {"key": "cotton", "label": "Cotton"},
        {"key": "café shop", "label": "Café Shop"},
    ]
    provider.facets["colours"] = [*provider.facets["colours"], "skin", "104"]
    provider.facets["materials"] = [*provider.facets["materials"], "paper", "shirt"]
    return provider


@pytest.mark.parametrize(
    "text,expected",
    [
        ("blue cotton shirt", {"brand": None, "colour": "blue", "material": "cotton"}),
        ("laptop skin", {"brand": None, "colour": None, "material": None}),
        ("paper shirt", {"brand": None, "material": None}),
        ("Acme shirt", {"brand": None}),
        ("shirt brand AcMe", {"brand": "acme"}),
        ("shirt by Acme", {"brand": "acme"}),
        ("shirt from one brand Acme", {"brand": "acme"}),
        ("clothing free size", {"size": "FREE_SIZE"}),
        ("clothing one size", {"size": "ONE_SIZE"}),
        ("shirt brand Blue", {"brand": "blue", "colour": None}),
        ("shirt brand Cotton", {"brand": "cotton", "material": None}),
        ("shirt brand Skin", {"brand": "skin", "colour": None}),
        ("shirt brand: Cafe\u0301   Shop", {"brand": "café shop"}),
        ("shirt colour skin", {"brand": None, "colour": "skin"}),
        ("shirt colour 104", {"colour": "104"}),
        ("shirt material paper", {"material": "paper"}),
        ("shirt brand Acme and colour blue", {"brand": "acme", "colour": "blue"}),
        ("shirt brand Blue and colour blue", {"brand": "blue", "colour": "blue"}),
    ],
)
def test_product_terms_and_cued_constraints(noisy_provider, text, expected):
    result = extract_intent(text, None, noisy_provider.facets)
    assert result.outcome == "valid"
    assert {field: result.intent[field] for field in expected} == expected
    assert result.intent["query_text"] == text
    assert result.llm_call_count == 0 and result.llm_ms is None


@pytest.mark.parametrize(
    "text,field",
    [
        ("shirt brand unknown", "brand"),
        ("shirt brand Acme and brand unknown", "brand"),
        ("shirt brand Acme and brand Blue", "brand"),
        ("shirt brand Acme and Blue", "brand"),
        ("shirt colour blue and colour ultraviolet", "colour"),
        ("shirt colour blue green", "colour"),
        ("shirt colour blue and ultraviolet", "colour"),
        ("shirt material cotton unknown", "material"),
        ("shirt material cotton and fabric unknown", "material"),
        ("clothing size M/L", "size"),
        ("clothing size M and L", "size"),
        ("clothing size M and size XXXXXL", "size"),
        ("shirt brand", "brand"),
        ("shirt colour:", "colour"),
        ("waterproof shirt", "unsupported_attribute"),
    ],
)
def test_unknown_or_ambiguous_constraints_never_search(noisy_provider, search_context, text, field):
    spy = IntentSpy()
    workflow = FixedWorkflow(None, noisy_provider.gateway(), intent_provider=spy)
    request = TurnRequest(request_id=search_context.request_id, text=text, mode="fixed")
    result = workflow._turn(request, search_context, "regression", monotonic())
    assert result.response.outcome == "clarification"
    assert field in result.response.response_text
    assert result.response.products == [] and result.response.search_id is None
    assert result.response.llm_call_count == 0 and result.response.timings_ms.llm is None
    assert noisy_provider.count("/v1/search") == 0 and spy.calls == []
    assert noisy_provider.count("/v1/orders") == noisy_provider.count("/v1/quotes") == 0


@pytest.mark.parametrize(
    "key,display",
    [("acme", "AcMe"), ("café shop", " Cafe\u0301   Shop ")],
)
def test_display_brand_uses_catalogue_canonicalization(
    noisy_provider, search_context, key, display
):
    noisy_provider.tamper_search = lambda response: [
        hit.update(brand=display) for hit in response["hits"]
    ]
    workflow = FixedWorkflow(None, noisy_provider.gateway())
    result = workflow.structured_search({"brand": key}, search_context, key=str(uuid4()))
    assert result["hits"] and all(hit["brand"] == display for hit in result["hits"])
    sent = next(r for r in noisy_provider.requests if r.url.path == "/v1/search")
    assert json.loads(sent.content)["intent"]["brand"] == key


def test_consumer_rejects_hit_mode_different_from_requested_mode(noisy_provider, search_context):
    noisy_provider.tamper_search = lambda response: response["hits"][0].update(
        retrieval_mode="hybrid_exact"
    )
    workflow = FixedWorkflow(None, noisy_provider.gateway())
    with pytest.raises(ContractViolation, match="rank/availability mismatch"):
        workflow.structured_search({}, search_context, key=str(uuid4()))


@pytest.mark.parametrize("display", [None, "Other", "Acme plus"])
def test_wrong_or_missing_display_brand_fails_closed(noisy_provider, search_context, display):
    noisy_provider.tamper_search = lambda response: [
        hit.update(brand=display) for hit in response["hits"]
    ]
    workflow = FixedWorkflow(None, noisy_provider.gateway())
    request = TurnRequest(
        request_id=search_context.request_id, text="shirt brand Acme", mode="fixed"
    )
    result = workflow._turn(request, search_context, "regression", monotonic())
    assert result.response.outcome == "dependency_error" and result.response.products == []
    assert noisy_provider.count("/v1/search") == 1 and result.response.llm_call_count == 0
