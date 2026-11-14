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
from tests.conversation.workflow_doubles import WorkflowProviderDouble, common_error, example


class OwnerSchemaDouble(OpenAPIContracts):
    mode = "stub"


class ShoppingProviderDouble(WorkflowProviderDouble):
    """Only synthetic results; validates against the actual owner schemas."""

    search_modes = ["lexical"]
    pipeline_order = None
    gold_rows = None
    analytics_down = False

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
        if request.url.path.startswith("/v1/orders/") and self.pipeline_order is not None:
            self.requests.append(request)
            order = self.pipeline_order
            if (
                request.url.path.rsplit("/", 1)[-1] != order["order_id"]
                or request.headers["X-User-ID"] != order["user_id"]
                or request.headers["X-Session-ID"] != order["session_id"]
            ):
                return httpx.Response(404, json=common_error("NOT_FOUND", False))
            return httpx.Response(200, json=order)
        if request.url.path == "/v1/analytics/gold/order_fact":
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
        if request.url.path == "/v1/catalog/capabilities":
            self.requests.append(request)
            return httpx.Response(
                200,
                json={
                    "search_modes": self.search_modes,
                    "hybrid_unavailable_reason": None
                    if "hybrid_exact" in self.search_modes
                    else "Not provisioned.",
                },
            )
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
            embedding_revision="test-encoder-revision" if body["mode"] != "lexical" else None,
        )
        if self.tamper_search:
            self.tamper_search(response)
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


def test_store_search_uses_hybrid_and_recorded_filters_before_price_sort(shop):
    client, headers, _, provider = shop
    response = client.get(
        "/v1/store/products",
        headers=headers,
        params={
            "q": "blue cotton shirt under 200 rupees",
            "max_price_minor": 10550,
            "sort": "price_desc",
            "offset": 0,
            "limit": 12,
        },
    )
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["total"] == 6
    assert [p["price_minor"] for p in page["items"]] == [10500, 10400, 10300, 10200, 10100, 10000]
    assert all(p["retrieval_mode"] == "hybrid_exact" for p in page["items"])
    request = next(r for r in provider.requests if r.url.path == "/v1/search")
    body = json.loads(request.content)
    assert body["top_k"] == 20 and body["mode"] == "hybrid_exact"
    assert body["intent"]["colour"] == "blue" and body["intent"]["material"] == "cotton"
    assert body["intent"]["max_price_minor"] == 10550
    assert provider.count("/v1/orders") == 0


def test_store_search_pages_only_the_bounded_hybrid_recommendations(shop):
    client, headers, _, _ = shop
    response = client.get(
        "/v1/store/products", headers=headers, params={"q": "shirt", "offset": 12, "limit": 12}
    )
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["total"] == 16 and len(page["items"]) == 4
    assert page["offset"] == 12


def test_store_search_keeps_colour_with_no_matches_and_clarifies_unknown_attributes(shop):
    client, headers, _, provider = shop
    provider.facets = {**provider.facets, "colours": [*provider.facets["colours"], "white"]}
    response = client.get("/v1/store/products", headers=headers, params={"q": "white shirt"})
    assert response.status_code == 200, response.text
    assert response.json()["items"] == [] and response.json()["total"] == 0
    response = client.get(
        "/v1/store/products",
        headers={**headers, "X-Request-ID": str(uuid4())},
        params={"q": "waterproof shirt"},
    )
    assert response.status_code == 422, response.text
    assert provider.count("/v1/search") == 1


def test_new_shopping_session_uses_available_retriever_and_remembers_it(shop):
    client, headers, session, provider = shop
    provider.search_modes = ["lexical", "hybrid_exact"]
    first, _, _ = say(shop, "shirts under 500 rupees")
    assert first["outcome"] == "success"
    assert all(p["retrieval_mode"] == "hybrid_exact" for p in first["products"])
    more, _, _ = say(shop, "More options")
    assert more["outcome"] == "success"
    assert not ({p["sku"] for p in first["products"]} & {p["sku"] for p in more["products"]})
    saved = client.get(f"/v1/sessions/{session}", headers=headers).json()["conversation"]
    assert saved["retrieval_mode"] == "hybrid_exact"
    assert saved["intent"]["max_price_minor"] == 49999
    assert first["llm_call_count"] == more["llm_call_count"] == 0


def test_explicit_keyword_selection_is_preserved_when_hybrid_is_available(shop):
    provider = shop[3]
    provider.search_modes = ["lexical", "hybrid_exact"]
    result, _, _ = say(shop, "shirts", retrieval_mode="lexical")
    assert result["outcome"] == "success"
    assert all(p["retrieval_mode"] == "lexical" for p in result["products"])
    assert provider.count("/v1/catalog/capabilities") == 0


@pytest.mark.parametrize("damage", ["no_inference", "no_revision", "wrong_hit_mode"])
def test_shopping_rejects_keyword_results_disguised_as_hybrid(shop, damage):
    def tamper(response):
        if damage == "no_inference":
            response["embedding_calls"] = 0
        elif damage == "no_revision":
            response["embedding_revision"] = None
        else:
            response["hits"][0]["retrieval_mode"] = "lexical"

    shop[3].tamper_search = tamper
    result, _, _ = say(shop, "shirts", retrieval_mode="hybrid_exact")
    assert result["outcome"] == "dependency_error"
    assert not result["products"] and result["search_id"] is None


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


@pytest.fixture
def pipeline(shop):
    client, headers, session, provider = shop
    order = example("order_status")
    order.update(
        order_id=str(uuid4()),
        user_id=headers["X-User-ID"],
        session_id=session,
        created_at="2026-11-12T23:59:59Z",
    )
    provider.pipeline_order = order
    provider.gold_rows = [{**order, "namespace": headers["X-Namespace"]}]
    provider.gold_rows[0]["order_status"] = provider.gold_rows[0].pop("status")
    return client, headers, provider, f"/v1/store/orders/{order['order_id']}/pipeline"


def test_order_pipeline_checks_exact_order_and_utc_creation_day(pipeline):
    client, headers, provider, path = pipeline
    response = client.get(path, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "visible" and response.json()["generation"] == 9
    assert set(response.json()) == {
        "order_id",
        "order_version",
        "status",
        "generation",
        "checked_at",
    }
    query = next(r.url.params for r in provider.requests if "/analytics/gold/" in r.url.path)
    assert query["namespace"] == headers["X-Namespace"]
    assert query["date_from"] == "2026-11-12" and query["date_to"] == "2026-11-13"


def test_cancelled_gold_matches_canonical_event_without_participant_ids(pipeline):
    client, headers, provider, path = pipeline
    provider.pipeline_order.update(
        status="CANCELLED", failure_code="DECLINED", reservation_id=str(uuid4())
    )
    provider.gold_rows[0].update(
        order_status="CANCELLED", failure_code="DECLINED", reservation_id=None, payment_id=None
    )
    assert provider.pipeline_order["reservation_id"] is not None
    assert client.get(path, headers=headers).json()["status"] == "visible"


@pytest.mark.parametrize(
    "case,expected",
    [
        ("empty", "pending"),
        ("behind", "pending"),
        ("advanced", "pending"),
        ("amount", "unavailable"),
        ("status", "unavailable"),
        ("namespace", "unavailable"),
        ("duplicate", "unavailable"),
        ("down", "unavailable"),
    ],
)
def test_pipeline_never_claims_unverified_visibility(pipeline, case, expected):
    client, headers, provider, path = pipeline
    row = provider.gold_rows[0]
    if case == "empty":
        provider.gold_rows = []
    elif case == "behind":
        row["order_version"] -= 1
    elif case == "advanced":
        row["order_version"] += 1
    elif case == "amount":
        row["total_amount_minor"] += 1
    elif case == "status":
        row["order_status"] = "CANCELLED"
    elif case == "namespace":
        row["namespace"] = "bench-other"
    elif case == "duplicate":
        provider.gold_rows.append(dict(row))
    else:
        provider.analytics_down = True
    response = client.get(path, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == expected
    assert response.json()["generation"] is None


def test_pipeline_authorizes_order_before_any_analytics_request(pipeline):
    client, headers, provider, path = pipeline
    response = client.get(path, headers={**headers, "X-User-ID": "stranger"})
    assert response.status_code == 404
    assert provider.count("/v1/analytics/gold/order_fact") == 0
