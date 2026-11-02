"""HTTP helpers and the shared synthetic catalogue for service tests."""

from uuid import uuid4

import psycopg

from tests.catalog.conftest import make_context
from tests.catalog.helpers import row, spec

TOKEN = "test-internal-token"


def catalogue():
    return [
        row(
            "SHIRT1",
            product_name="Blue cotton shirt",
            discounted_price="500",
            brand="Acme",
            product_specifications=spec(Color="Blue", Fabric="Cotton", Size="M"),
        ),
        row(
            "SHIRT2",
            product_name="Red linen shirt",
            discounted_price="300",
            brand="Beta",
            product_specifications=spec(Color="Gray", Fabric="Cotton Lycra", Size="Large"),
        ),
        row(
            "SHIRT3",
            product_name="Plain formal top",
            discounted_price="900",
            description="A blue shirt in description only",
            product_specifications=spec(Color="Multicolor"),
        ),
        row(
            "DRESS1",
            product_name="Summer dress",
            discounted_price="700",
            product_category_tree='["Clothing >> Dresses"]',
        ),
        row(
            "WATCH1",
            product_name="Steel watch",
            discounted_price="5000",
            product_category_tree='["Watches >> Analog"]',
        ),
        row(
            "NOPRICE",
            product_name="Blue cotton shirt unpriced",
            discounted_price="",
            retail_price="",
        ),
        row("NOSTOCK", product_name="Blue cotton shirt unprojected", discounted_price="100"),
        row("ZEROSTOCK", product_name="Blue cotton shirt sold out", discounted_price="110"),
        row(
            "ODD1",
            product_name="Mystery object",
            discounted_price="50",
            product_category_tree='["Mystery listing"]',
        ),
    ]


def headers(namespace, *, user="h-user", key=None, internal=False, session=None):
    result = make_context(namespace, user=user, session=session).headers(key)
    if internal:
        result["Authorization"] = "Bearer " + TOKEN
    return result


def search(client, namespace, *, mode="lexical", top_k=5, expect=200, **intent):
    session = str(uuid4())
    body = {
        "request_id": str(uuid4()),
        "session_id": session,
        "intent": {
            "query_text": "",
            "category": None,
            "size": None,
            "colour": None,
            "material": None,
            "max_price_minor": None,
            "occasion": None,
            "currency": "INR",
            **intent,
        },
        "top_k": top_k,
        "mode": mode,
    }
    response = client.post("/v1/search", json=body, headers=headers(namespace, session=session))
    assert response.status_code == expect, response.text
    return response.json()


def skus(result):
    return [hit["sku"] for hit in result["hits"]]


def quote(client, namespace, lines, *, key=None, user="h-user", cart=None, version=1, expect=201):
    response = client.post(
        "/v1/quotes",
        json={"cart_id": cart or str(uuid4()), "cart_version": version, "lines": lines},
        headers=headers(namespace, user=user, key=key or str(uuid4())),
    )
    assert response.status_code == expect, response.text
    return response.json()


def lookup(client, namespace, quote_id, *, user="h-user", internal=True):
    return client.get(
        f"/internal/v1/quotes/{quote_id}",
        headers=headers(namespace, user=user, internal=internal),
    )


def price(client, namespace, sku, value, version, *, key=None, internal=True, expect=200):
    response = client.post(
        f"/internal/v1/catalog/{sku}/price",
        json={"price_minor": value, "expected_catalog_version": version},
        headers=headers(namespace, key=key or str(uuid4()), internal=internal),
    )
    assert response.status_code == expect, response.text
    return response.json()


def captured(database_url):
    with psycopg.connect(database_url) as connection:
        rows = connection.execute("SELECT event FROM test_event_capture ORDER BY position")
        return [row[0] for row in rows.fetchall()]
