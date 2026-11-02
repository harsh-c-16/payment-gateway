"""Authoritative price changes and their transactional event. The outbox is a test double."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from starlette.testclient import TestClient

from services.catalog.app import create_app
from tests.catalog.helpers import import_rows, row
from tests.catalog.service_helpers import TOKEN, captured, headers, lookup, price, quote

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads(
    (ROOT / "contracts/fixtures/catalog/dirty_catalogue.json").read_text(encoding="utf-8")
)


def test_independent_price_only_update_fixture(world, database_url):
    client, namespace, _ = world
    case = next(c for c in FIXTURE["cases"] if c["case_id"] == "price-only-update")
    results = []
    for command in case["input_api_commands"]:
        response = client.post(
            "/internal/v1/catalog/FK-SHIRT1/price",
            json={
                "price_minor": command["price_minor"],
                "expected_catalog_version": command["expected_catalog_version"],
            },
            headers=headers(namespace, key=command["idempotency_key"], internal=True),
        )
        results.append(response)
    assert [r.status_code for r in results] == [200, 200, 422]
    assert results[0].json() == results[1].json()
    final = client.get("/v1/products/FK-SHIRT1", headers=headers(namespace)).json()["product"]
    assert final["catalog_version"] == case["expected"]["final_catalog_version"]
    assert final["price_minor"] == 38000 and final["active"] is True
    price_events = [e for e in captured(database_url) if e["event_type"] == "PRICE_UPDATED"]
    assert len(price_events) == case["expected"]["logical_price_event_count"]
    event = price_events[0]
    assert event["aggregate_version"] == 2 and event["payload"]["catalog_version"] == 2
    assert event["payload"]["price_minor"] == 38000 and event["aggregate_type"] == "sku"


def test_price_update_guards(world):
    client, namespace, _ = world
    stale = price(client, namespace, "FK-SHIRT1", 38000, 9, expect=409)
    assert stale["error"]["code"] == "ILLEGAL_STATE"
    assert stale["error"]["details"]["catalog_version"] == "1"
    inactive = price(client, namespace, "FK-NOPRICE", 38000, 1, expect=409)
    assert inactive["error"]["code"] == "PRODUCT_NOT_SELLABLE"
    assert price(client, namespace, "FK-ABSENT", 38000, 1, expect=404)
    assert price(client, namespace, "FK-SHIRT1", 38000, 1, internal=False, expect=401)
    assert price(client, namespace, "FK-SHIRT1", 0, 1, expect=422)


def test_quote_keeps_its_price_after_catalogue_change(world):
    client, namespace, _ = world
    created = quote(client, namespace, [{"sku": "FK-SHIRT1", "quantity": 1}])
    price(client, namespace, "FK-SHIRT1", 99900, 1)
    assert lookup(client, namespace, created["quote_id"]).json() == created
    fresh = quote(client, namespace, [{"sku": "FK-SHIRT1", "quantity": 1}])
    assert fresh["total_amount_minor"] == 99900 and fresh["lines"][0]["catalog_version"] == 2


def test_price_update_leaves_stock_untouched(world):
    client, namespace, _ = world
    before = client.get("/v1/products/FK-SHIRT1", headers=headers(namespace)).json()["stock"]
    price(client, namespace, "FK-SHIRT1", 99900, 1)
    after = client.get("/v1/products/FK-SHIRT1", headers=headers(namespace)).json()["stock"]
    assert after == before


def test_concurrent_price_updates_cannot_mix_a_quote(world):
    client, namespace, _ = world
    lines = [{"sku": "FK-SHIRT1", "quantity": 1}, {"sku": "FK-WATCH1", "quantity": 1}]

    def writer():
        for version in range(1, 11):
            price(client, namespace, "FK-SHIRT1", 50000 + version * 100, version)

    with ThreadPoolExecutor(6) as pool:
        running = pool.submit(writer)
        quotes = list(pool.map(lambda _: quote(client, namespace, lines), range(40)))
        running.result()
    for item in quotes:
        line = next(line for line in item["lines"] if line["sku"] == "FK-SHIRT1")
        version = line["catalog_version"]
        # A price is only ever quoted with the version that wrote it.
        assert line["unit_price_minor"] == 50000 + (version - 1) * 100


def test_event_failure_rolls_back_the_price_change(world, db, events, monkeypatch):
    _, namespace, _ = world

    class Failing:
        def ready(self):
            pass

        def append(self, tx, **event):
            from services.catalog.events import unavailable

            raise unavailable()

    client = TestClient(create_app(db=db, events=Failing()), raise_server_exceptions=False)
    response = client.post(
        "/internal/v1/catalog/FK-SHIRT1/price",
        json={"price_minor": 12345, "expected_catalog_version": 1},
        headers=headers(namespace, key="k1", internal=True),
    )
    assert response.status_code == 503
    product = client.get("/v1/products/FK-SHIRT1", headers=headers(namespace)).json()["product"]
    assert product["price_minor"] == 50000 and product["catalog_version"] == 1


def test_reimport_after_live_price_change_counts_as_a_business_change(
    tmp_path, database_url, db, events, monkeypatch
):
    monkeypatch.setenv("INTERNAL_API_TOKEN", TOKEN)
    namespace = "bench-h-" + uuid4().hex[:16]
    import_rows(tmp_path, database_url, namespace, [row("A1")])
    client = TestClient(create_app(db=db, events=events))
    price(client, namespace, "FK-A1", 99900, 1)
    # A different source file, in which this listing is unchanged from the original.
    report, _ = import_rows(tmp_path, database_url, namespace, [row("A1"), row("A2")])
    product = client.get("/v1/products/FK-A1", headers=headers(namespace)).json()["product"]
    assert report.updated == 1 and product["catalog_version"] == 3
    assert product["price_minor"] == 37900


def test_same_price_key_on_two_skus_are_separate_operations(world):
    client, namespace, _ = world
    first = price(client, namespace, "FK-SHIRT1", 11100, 1, key="shared-key")
    second = price(client, namespace, "FK-SHIRT2", 22200, 1, key="shared-key")
    assert (first["sku"], second["sku"]) == ("FK-SHIRT1", "FK-SHIRT2")
    assert second["price_minor"] == 22200
