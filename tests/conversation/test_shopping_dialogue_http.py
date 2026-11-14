"""Real PostgreSQL/session locking, with explicit catalogue and Gemini HTTP doubles."""

import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from services.conversation.app import create_app
from services.conversation.shopping_llm import GeminiShoppingProvider
from services.conversation.workflow import FixedWorkflow
from tests.conversation.test_shopping_http import ShoppingProviderDouble, say
from tests.conversation.test_shopping_llm import reply
from tests.conversation.workflow_doubles import common_error, example


class DetailProviderDouble(ShoppingProviderDouble):
    async def __call__(self, request):
        if request.url.path == "/v1/analytics/gold/pipeline_minute":
            self.requests.append(request)
            if self.analytics_down:
                return httpx.Response(503, json=common_error("DEPENDENCY_UNAVAILABLE", False))
            return httpx.Response(
                200,
                json={
                    "generation": 9,
                    "rows": self.gold_rows or [],
                    "queried_at": "2026-11-13T00:00:01Z",
                },
            )
        if request.url.path.startswith("/v1/products/"):
            self.requests.append(request)
            response = example("product")
            response["product"].update(
                sku=request.url.path.rsplit("/", 1)[-1],
                title="Synthetic recorded product",
                material="cotton",
            )
            if response["stock"]:
                response["stock"]["sku"] = response["product"]["sku"]
            return httpx.Response(200, json=response)
        return await super().__call__(request)


@pytest.fixture
def conversation(state, context):
    provider, calls, plans = DetailProviderDouble(), [], []

    def model(request):
        calls.append(json.loads(request.content))
        plan = plans.pop(0)
        return plan if isinstance(plan, httpx.Response) else httpx.Response(200, json=reply(*plan))

    model_provider = GeminiShoppingProvider(
        "synthetic-key", mode="stub", purpose="contract_test", transport=httpx.MockTransport(model)
    )
    app = create_app(
        state=state,
        workflow=FixedWorkflow(state, provider.gateway()),
        mode="stub",
        purpose="contract_test",
        shopping_provider=model_provider,
    )
    headers = {**context.headers(), "Idempotency-Key": str(uuid4())}
    with TestClient(app) as client:
        created = client.post("/v1/sessions", headers=headers, json={})
        assert created.status_code == 201
        session = created.json()["session_id"]
        headers["X-Session-ID"] = session
        yield (client, headers, session, provider), calls, plans


def test_llm_conversation_uses_history_tools_and_replay_without_purchase(conversation):
    shop, calls, plans = conversation
    client, headers, session, provider = shop
    plans.append(
        (
            "ask_question",
            {
                "question": "What kind of gift would you like?",
                "filters": {"max_price_minor": 100000},
            },
        )
    )
    vague, _, _ = say(shop, "I need a gift under 1000 rupees", mode="assist")
    assert vague["outcome"] == "clarification" and vague["llm_call_count"] == 1
    timing = vague["timings_ms"]
    assert sum(timing[k] or 0 for k in ("parse", "llm", "search", "compose")) <= timing["total"]
    plans.append(("search_catalog", {"query": "shirt", "filters": {"colour": "blue"}}))
    first, retry_headers, body = say(shop, "blue shirts", mode="assist")
    assert first["products"] and first["intent"]["max_price_minor"] == 99999
    replay = client.post(f"/v1/sessions/{session}/shopping-turns", headers=retry_headers, json=body)
    assert replay.json() == first and len(calls) == 2
    prompt = json.loads(calls[1]["contents"][0]["parts"][0]["text"])
    assert len(prompt["history"]) == 2 and prompt["pending"] == ["query_text"]
    plans.append(("search_catalog", {"more": True}))
    more, _, _ = say(shop, "show me other choices", mode="assist")
    assert more["products"] and not (
        {p["sku"] for p in first["products"]} & {p["sku"] for p in more["products"]}
    )
    plans.append(("product_details", {"references": [2]}))
    details, _, _ = say(shop, "what material is the second one?", mode="assist")
    assert (
        "material: cotton" in details["response_text"]
        and "not recorded" in details["response_text"]
    )
    plans.append(("respond", {"topic": "checkout"}))
    purchase, _, _ = say(shop, "buy it for me", mode="assist")
    assert "Review order" in purchase["response_text"]
    assert "Place demo order" in purchase["response_text"]
    assert provider.count("/v1/orders") == provider.count("/v1/quotes") == 0
    memory = client.get(f"/v1/sessions/{session}", headers=headers).json()["conversation"]
    assert memory["intent"]["colour"] == "blue" and len(memory["messages"]) == 10
    metrics = client.get(f"/v1/sessions/{session}/metrics", headers=headers).json()
    assert metrics["sampled_turns"] == 5 and metrics["model_attempts"] == 5
    assert metrics["searches"] == 2 and metrics["model_mean_ms"] is not None
    durations = sorted(r["timings_ms"]["total"] for r in (vague, first, more, details, purchase))
    assert metrics["turn_p50_ms"] == durations[2]
    assert metrics["turn_p95_ms"] == durations[-1]


def test_fixed_mode_has_zero_model_calls_even_when_conversation_enabled(conversation):
    shop, calls, _ = conversation
    first, _, _ = say(shop, "blue shirts")
    assert first["products"] and first["llm_call_count"] == 0 and calls == []
    assert shop[0].get("/v1/store/bootstrap").json()["conversation_available"]


def test_provider_failure_preserves_preferences_and_exact_retry(conversation):
    shop, calls, plans = conversation
    client, headers, session, provider = shop
    first, _, _ = say(shop, "blue shirts")
    plans.append(httpx.Response(429, text="private provider response"))
    failure, retry_headers, body = say(shop, "more choices", mode="assist")
    assert failure["outcome"] == "dependency_error" and failure["llm_call_count"] == 1
    assert "private" not in failure["response_text"] and "usage limit" in failure["response_text"]
    replay = client.post(f"/v1/sessions/{session}/shopping-turns", headers=retry_headers, json=body)
    assert replay.json() == failure and len(calls) == 1
    memory = client.get(f"/v1/sessions/{session}", headers=headers).json()["conversation"]
    assert memory["products"] == first["products"] and memory["intent"] == first["intent"]
    assert provider.count("/v1/search") == 1


def test_metrics_are_owned_and_missing_pipeline_stays_null(conversation):
    shop, _, _ = conversation
    client, headers, session, provider = shop
    provider.analytics_down = True
    response = client.get(f"/v1/sessions/{session}/metrics", headers=headers)
    assert response.status_code == 200
    metrics = response.json()
    assert metrics["sampled_turns"] == metrics["searches"] == metrics["model_attempts"] == 0
    assert metrics["turn_p50_ms"] is None and metrics["turn_p95_ms"] is None
    assert metrics["pipeline_status"] == "unavailable" and metrics["pipeline_events_today"] is None
    before = provider.count("/v1/analytics/gold/pipeline_minute")
    denied = client.get(
        f"/v1/sessions/{session}/metrics", headers={**headers, "X-User-ID": "other"}
    )
    assert denied.status_code == 403
    assert provider.count("/v1/analytics/gold/pipeline_minute") == before


def test_unsupported_features_never_become_unfiltered_product_claims(conversation):
    shop, calls, plans = conversation
    plans.append(("search_catalog", {"query": "waterproof shirt"}))
    result, _, _ = say(shop, "waterproof shirt", mode="assist")
    assert result["outcome"] == "clarification" and result["llm_call_count"] == 1
    assert "not reliably recorded" in result["response_text"]
    assert shop[3].count("/v1/search") == 0 and len(calls) == 1
