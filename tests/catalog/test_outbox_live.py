"""Catalogue events through Aditya's real append_outbox into catalog_db's own outbox table."""

import json
from uuid import uuid4

import psycopg
import pytest
from starlette.testclient import TestClient

import shared.event_transport as sdk
from services.catalog.app import create_app
from services.catalog.events import SharedEvents
from shared.event_transport.codec import EventCodec
from shared.outbox import relay_once
from tests.catalog.helpers import import_rows, seed_stock
from tests.catalog.service_helpers import TOKEN, catalogue, price, search
from tests.pipelines.transport_doubles import offline_cache


@pytest.fixture
def real_outbox(tmp_path, database_url, db, events, monkeypatch):
    monkeypatch.setenv("INTERNAL_API_TOKEN", TOKEN)
    monkeypatch.setattr(sdk, "_codec", EventCodec(offline_cache(), source_service="catalog"))
    shared = SharedEvents()
    shared.configured = True
    namespace = "bench-h-" + uuid4().hex[:16]
    import_rows(tmp_path, database_url, namespace, catalogue())
    seed_stock(db, events.codec, namespace, ["FK-SHIRT1", "FK-WATCH1"])
    client = TestClient(create_app(db=db, events=shared), raise_server_exceptions=False)
    return client, namespace


def outbox(database_url):
    with psycopg.connect(database_url) as connection:
        rows = connection.execute(
            "SELECT payload, published_at FROM outbox ORDER BY outbox_id"
        ).fetchall()
    return [(json.loads(bytes(payload)), published) for payload, published in rows]


def test_search_writes_both_retrieval_events_to_the_real_outbox(real_outbox, database_url):
    client, namespace = real_outbox
    assert client.get("/health/ready").status_code == 200
    result = search(client, namespace, query_text="blue shirt")
    rows = outbox(database_url)
    assert [event["event_type"] for event, _ in rows] == ["SEARCH_REQUESTED", "PRODUCT_RETRIEVED"]
    assert rows[1][0]["payload"]["skus"] == [hit["sku"] for hit in result["hits"]]
    assert all(event["namespace"] == namespace and published is None for event, published in rows)


def test_price_update_is_one_event_and_a_rejected_update_writes_none(real_outbox, database_url):
    client, namespace = real_outbox
    updated = price(client, namespace, "FK-SHIRT1", 45000, 1)
    price(client, namespace, "FK-SHIRT1", 40000, 1, expect=409)
    rows = outbox(database_url)
    assert [event["event_type"] for event, _ in rows] == ["PRICE_UPDATED"]
    assert rows[0][0]["payload"]["price_minor"] == 45000
    assert rows[0][0]["payload"]["catalog_version"] == updated["catalog_version"]


def test_shared_relay_publishes_catalogue_rows_and_marks_them(real_outbox, database_url):
    client, namespace = real_outbox
    search(client, namespace, query_text="watch")
    published = []

    class Publisher:
        def publish_event(self, event, topic, key):
            published.append((event.event_type, topic, key))

    with psycopg.connect(database_url) as connection:
        result = relay_once(connection, Publisher())
    assert result.marked_published == 2
    assert [event_type for event_type, _, _ in published] == [
        "SEARCH_REQUESTED",
        "PRODUCT_RETRIEVED",
    ]
    assert all(published_at is not None for _, published_at in outbox(database_url))
