"""Real session storage and owner-schema validation; explicit synthetic HTTP providers."""

import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from services.conversation.app import create_app
from services.conversation.gateway import Gateway
from services.conversation.provider_contracts import OpenAPIContracts
from services.conversation.workflow import FixedWorkflow
from tests.conversation.workflow_doubles import WorkflowProviderDouble, example


class OwnerSchemaDouble(OpenAPIContracts):
    mode = "stub"


class ShoppingProviderDouble(WorkflowProviderDouble):
    """Only synthetic results; validates against the actual owner schemas."""

    def gateway(self):
        return Gateway(
            "http://catalog.test",
            "http://orders.test",
            mode="stub",
            purpose="contract_test",
            contracts=OwnerSchemaDouble(Path("contracts/http")),
            transport=httpx.MockTransport(self),
        )

    async def __call__(self, request):
        if request.url.path != "/v1/search":
            return await super().__call__(request)
        self.requests.append(request)
        body = json.loads(request.content)
        hits = []
        for number in range(16):
            hit = example("search")["hits"][0]
            hit.update(
                sku=f"TEST-SHIRT-{number}",
                product_id=f"TEST-SHIRT-{number}",
                title=f"Synthetic blue cotton shirt {number}",
                colour="blue",
                category="clothing",
                material="cotton",
                price_minor=10000 + number * 100,
                dataset_revision=self.facets["dataset_revision"],
                stock_available=10,
                retrieval_mode=body["mode"],
                image_urls=["https://example.test/shirt.jpg"],
            )
            if hit["sku"] in body.get("exclude_skus", []):
                continue
            intent = body["intent"]
            if any(
                intent.get(f) is not None and intent[f] != hit[f]
                for f in ("colour", "category", "material", "size", "brand")
            ):
                continue
            if (
                intent["max_price_minor"] is not None
                and hit["price_minor"] > intent["max_price_minor"]
            ):
                continue
            hits.append(hit)
        response = example("search")
        limited = hits[: body["top_k"]]
        for rank, hit in enumerate(limited, 1):
            hit["rank"] = rank
        response.update(
            search_id=str(uuid4()),
            mode=body["mode"],
            hits=limited,
            candidate_count=16,
            eligible_count=len(hits),
            returned_count=len(limited),
            exhausted=len(hits) <= body["top_k"],
            embedding_calls=int(body["mode"] != "lexical"),
        )
        return httpx.Response(200, json=response)


@pytest.fixture
def shop(state, context):
    provider = ShoppingProviderDouble()
    app = create_app(
        state=state,
        workflow=FixedWorkflow(state, provider.gateway()),
        mode="stub",
        purpose="contract_test",
    )
    headers = context.headers()
    headers["Idempotency-Key"] = str(uuid4())
    with TestClient(app) as client:
        created = client.post("/v1/sessions", headers=headers, json={})
        assert created.status_code == 201, created.text
        session = created.json()["session_id"]
        headers["X-Session-ID"] = session
        yield client, headers, session, provider


def say(shop, text, **extra):
    client, headers, session, _ = shop
    headers = {**headers, "X-Request-ID": str(uuid4()), "Idempotency-Key": str(uuid4())}
    body = {"request_id": headers["X-Request-ID"], "text": text, "mode": "fixed", **extra}
    response = client.post(f"/v1/sessions/{session}/shopping-turns", headers=headers, json=body)
    assert response.status_code == 200, response.text
    return response.json(), headers, body


def test_dialogue_more_options_resume_and_idempotency(shop):
    client, headers, session, provider = shop
    vague, _, _ = say(shop, "I need something under 500 rupees")
    assert vague["outcome"] == "clarification"
    assert provider.count("/v1/search") == 0
    first, retry_headers, body = say(shop, "shirts")
    assert first["outcome"] == "success" and first["products"]
    replay = client.post(f"/v1/sessions/{session}/shopping-turns", headers=retry_headers, json=body)
    assert replay.json() == first
    assert provider.count("/v1/search") == 1
    refined, _, _ = say(shop, "Only blue ones")
    assert all(p["colour"] == "blue" for p in refined["products"])
    more, _, _ = say(shop, "Do we have more options?")
    assert more["outcome"] == "success" and more["products"]
    assert not ({p["sku"] for p in more["products"]} & {p["sku"] for p in refined["products"]})
    snapshot = client.get(f"/v1/sessions/{session}", headers=headers).json()["conversation"]
    assert snapshot["intent"]["colour"] == "blue"
    assert snapshot["intent"]["max_price_minor"] == 49999
    assert len(snapshot["messages"]) == 8
    assert all(p["image_urls"] for p in more["products"])
    assert more["llm_call_count"] == 0 and provider.count("/v1/orders") == 0


def test_hybrid_is_requested_without_faking_generative_calls(shop):
    result, _, _ = say(shop, "shirts", retrieval_mode="hybrid_exact")
    assert result["outcome"] == "success", result
    assert all(p["retrieval_mode"] == "hybrid_exact" for p in result["products"])
    assert result["llm_call_count"] == 0


def test_session_ownership_and_explicit_checkout_control(shop):
    client, headers, session, provider = shop
    assert (
        client.get(
            f"/v1/sessions/{session}", headers={**headers, "X-User-ID": "stranger"}
        ).status_code
        == 403
    )
    response, _, _ = say(shop, "Buy the first one")
    assert response["outcome"] == "clarification"
    assert provider.count("/v1/orders") == 0


def test_storefront_assets_are_local_and_have_security_headers(shop):
    client = shop[0]
    response = client.get("/")
    assert response.status_code == 200 and "ShopTalk" in response.text
    assert "script-src 'self'" in response.headers["Content-Security-Policy"]
    assert client.get("/assets/store.js").status_code == 200
    assert "postgresql://" not in response.text


def test_failed_outbox_append_rolls_back_conversation_memory(shop):
    client, headers, session, _ = shop
    say(shop, "shirts")
    before = client.get(f"/v1/sessions/{session}", headers=headers).json()
    client.app.state.conversation.events.fail_after_append = True
    identity = {**headers, "X-Request-ID": str(uuid4()), "Idempotency-Key": str(uuid4())}
    response = client.post(
        f"/v1/sessions/{session}/shopping-turns",
        headers=identity,
        json={"request_id": identity["X-Request-ID"], "text": "Only blue ones", "mode": "fixed"},
    )
    assert response.status_code == 503
    assert client.get(f"/v1/sessions/{session}", headers=headers).json() == before


def test_missing_catalogue_does_not_replace_saved_preferences_with_fake_results(shop):
    client, headers, session, provider = shop
    say(shop, "shirts")
    provider.catalog_unavailable = True
    result, _, _ = say(shop, "Only blue ones")
    assert result["outcome"] == "dependency_error" and result["products"] == []
    memory = client.get(f"/v1/sessions/{session}", headers=headers).json()["conversation"]
    assert memory["intent"]["colour"] is None
    assert memory["products"]
