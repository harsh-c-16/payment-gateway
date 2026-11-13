"""Storefront reads against an isolated real PostgreSQL catalogue."""

from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

from services.conversation.intent import blank_intent
from tests.catalog.service_helpers import headers, search


@pytest.mark.parametrize(
    "sort,first_sku", [("price_asc", "FK-SHIRT2"), ("price_desc", "FK-SHIRT3")]
)
def test_text_browse_keeps_price_order_and_counts_across_pages(world, sort, first_sku):
    client, namespace, _ = world
    first = client.get(f"/v1/products?q=shirt&sort={sort}&limit=1", headers=headers(namespace))
    assert first.status_code == 200, first.text
    assert first.json()["items"][0]["sku"] == first_sku
    assert first.json()["total"] == 3
    second = client.get(
        f"/v1/products?q=shirt&sort={sort}&limit=1&offset=1", headers=headers(namespace)
    )
    assert second.status_code == 200, second.text
    assert second.json()["items"][0]["sku"] == "FK-SHIRT1"
    assert second.json()["total"] == 3
    beyond = client.get(
        f"/v1/products?q=shirt&sort={sort}&limit=1&offset=20", headers=headers(namespace)
    )
    assert beyond.status_code == 200, beyond.text
    assert beyond.json()["items"] == [] and beyond.json()["total"] == 3


def test_browse_filters_pagination_and_images(world, db):
    client, namespace, _ = world
    with db.transaction() as tx:
        tx.execute(
            "UPDATE products SET image_urls=%s WHERE namespace=%s AND sku='FK-SHIRT1'",
            (Jsonb(["https://example.test/product.jpg"]), namespace),
        )
    first = client.get("/v1/products?limit=2&sort=price_asc", headers=headers(namespace))
    assert first.status_code == 200, first.text
    page = first.json()
    assert len(page["items"]) == 2 and page["total"] > 2
    second = client.get(
        "/v1/products?limit=2&offset=2&sort=price_asc", headers=headers(namespace)
    ).json()
    assert not ({p["sku"] for p in page["items"]} & {p["sku"] for p in second["items"]})
    filtered = client.get(
        "/v1/products?category=clothing&max_price_minor=50000&q=shirt", headers=headers(namespace)
    ).json()
    assert filtered["items"] and all(p["price_minor"] <= 50000 for p in filtered["items"])
    assert next(p for p in filtered["items"] if p["sku"] == "FK-SHIRT1")["image_urls"]
    product = client.get("/v1/products/FK-SHIRT1", headers=headers(namespace)).json()
    assert product["product"]["image_urls"] == ["https://example.test/product.jpg"]
    assert client.get("/v1/products?sort=price;DROP", headers=headers(namespace)).status_code == 422
    assert client.get("/v1/products", headers=headers(namespace + "-other")).json()["items"] == []


def test_more_options_excludes_seen_and_model_availability_is_honest(world):
    client, namespace, _ = world
    first = search(client, namespace, mode="filter_only")
    assert first["hits"]
    seen = [p["sku"] for p in first["hits"]]
    response = client.post(
        "/v1/search",
        headers=headers(namespace),
        json={
            "request_id": str(uuid4()),
            "session_id": str(uuid4()),
            "intent": blank_intent(""),
            "mode": "filter_only",
            "top_k": 5,
            "exclude_skus": seen,
        },
    )
    assert response.status_code == 200, response.text
    response = response.json()
    assert not ({p["sku"] for p in response["hits"]} & set(seen))
    capabilities = client.get("/v1/catalog/capabilities", headers=headers(namespace)).json()
    assert capabilities["search_modes"] == ["lexical"]
    assert capabilities["hybrid_unavailable_reason"]
