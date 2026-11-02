"""Product lookup, facets, errors, health and metrics over real PostgreSQL and HTTP."""

from uuid import uuid4

from starlette.testclient import TestClient

from services.catalog.app import create_app
from tests.catalog.service_helpers import headers


def test_namespace_isolation(world):
    client, _, _ = world
    other = "bench-h-" + uuid4().hex[:16]
    response = client.get("/v1/products/FK-SHIRT1", headers=headers(other))
    assert response.status_code == 404


def test_product_lookup_keeps_inactive_inspectable_and_unknown_stock_null(world):
    client, namespace, report = world
    inactive = client.get("/v1/products/FK-NOPRICE", headers=headers(namespace)).json()
    assert inactive["product"]["active"] is False
    assert inactive["product"]["price_minor"] is None
    assert inactive["product"]["inactive_reason"] == "MISSING_PRICE"
    assert inactive["stock"] is None
    known = client.get("/v1/products/FK-SHIRT1", headers=headers(namespace)).json()
    assert known["stock"]["available"] == 10
    assert known["product"]["dataset_revision"] == report.dataset_revision
    assert known["product"]["attributes"]["color"] == ["Blue"]
    assert client.get("/v1/products/FK-ABSENT", headers=headers(namespace)).status_code == 404


def test_facets_come_from_the_promoted_import(world):
    client, namespace, report = world
    facets = client.get("/v1/catalog/facets", headers=headers(namespace)).json()
    assert facets["dataset_revision"] == report.dataset_revision
    assert {"id": "clothing", "label": "Clothing"} in facets["roots"]
    assert "blue" in facets["colours"] and "cotton" in facets["materials"]
    assert facets["observed_apparel_sizes"] == ["L", "M"]
    assert ["Clothing", "Shirts"] in facets["path_prefixes"]
    assert ["Clothing", "Shirts", "Formal"] not in facets["path_prefixes"]
    absent = client.get(
        "/v1/catalog/facets",
        headers=headers(namespace),
        params={"dataset_revision": "other"},
    )
    assert absent.status_code == 404


def test_common_error_object_and_context_rules(world):
    client, namespace, _ = world
    response = client.get("/v1/products/FK-ABSENT", headers=headers(namespace))
    body = response.json()
    assert set(body) == {"error", "correlation_id"}
    assert set(body["error"]) == {"code", "message", "retryable", "details"}
    assert body["error"]["retryable"] is False
    assert client.get("/v1/products/FK-A", headers={}).status_code == 401
    bad = headers(namespace)
    bad["X-Namespace"] = "not valid"
    assert client.get("/v1/products/FK-A", headers=bad).status_code == 422


def test_storage_failure_is_503_without_leaking_details(world, events):
    from services.catalog.database import Database

    _, namespace, _ = world
    broken = Database("postgresql://nobody:secret@127.0.0.1:1/none")
    client = TestClient(create_app(db=broken, events=events), raise_server_exceptions=False)
    response = client.get("/v1/products/FK-A", headers=headers(namespace))
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert "secret" not in response.text


def test_health_and_metrics(world):
    client, namespace, _ = world
    assert client.get("/health/live").json() == {"status": "live"}
    assert client.get("/health/ready").json() == {"status": "ready"}
    client.get("/v1/products/FK-SHIRT1", headers=headers(namespace))
    text = client.get("/metrics").text
    assert 'requests_total{route="/v1/products/{sku}",service="catalog",status="200"}' in text
