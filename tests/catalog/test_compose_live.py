"""Opt-in HTTP/worker/relay acceptance on a separately staged, isolated Compose namespace."""

import os
from datetime import UTC, datetime
from time import monotonic, sleep
from uuid import uuid4

import httpx
import psycopg
import pytest

from pipelines.ingestion.lifecycle import isolated_namespace
from shared.event_transport import ConsumerGroup, KafkaPublisher
from shared.event_transport.codec import EventCodec
from shared.event_transport.schemas import SchemaCache
from tests.catalog.conftest import make_context

NAMESPACE = os.environ.get("CATALOG_COMPOSE_TEST_NAMESPACE")
pytestmark = pytest.mark.skipif(
    not NAMESPACE, reason="NOT_RUN: isolated catalogue Compose deployment required"
)


def test_composed_api_stock_worker_and_catalogue_relay():
    isolated_namespace(NAMESPACE)
    bootstrap = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
    codec = EventCodec(
        SchemaCache.load(os.environ["EVENT_SCHEMA_CACHE_PATH"]), source_service="inventory"
    )
    context = make_context(NAMESPACE)
    event = codec.build_event(
        "STOCK_UPDATED",
        {
            "sku": "FK-COMPOSE1",
            "stock_version": 1,
            "on_hand": 10,
            "reserved": 0,
            "available": 10,
            "changed_at": datetime.now(UTC).isoformat(),
            "order_id": None,
            "reservation_id": None,
            "reason_code": None,
        },
        context,
        "sku",
        "FK-COMPOSE1",
        1,
        datetime.now(UTC),
        metadata={
            "dataset_revision": "compose-fixture",
            "synthetic": True,
            "scenario_source": "simulation",
        },
    )
    publisher = KafkaPublisher(codec, bootstrap)
    observer = ConsumerGroup(
        NAMESPACE + ".acceptance.v1",
        [NAMESPACE + ".retrieval-events.v1", NAMESPACE + ".order-events.v1"],
        bootstrap,
    )
    try:
        publisher.publish_event(event, event.topic(), event.kafka_key())
        with httpx.Client(
            base_url=os.environ["CATALOG_COMPOSE_TEST_BASE_URL"], timeout=10, trust_env=False
        ) as client:
            assert client.get("/health/ready").status_code == 200
            deadline = monotonic() + 60
            while monotonic() < deadline:
                product = client.get("/v1/products/FK-COMPOSE1", headers=context.headers()).json()
                if (product.get("stock") or {}).get("stock_version") == 1:
                    break
                sleep(0.1)
            else:
                pytest.fail("Real stock consumer did not project the Kafka source")
            assert product["stock"]["available"] == 10
            session = str(uuid4())
            search = client.post(
                "/v1/search",
                headers=make_context(NAMESPACE, session=session).headers(),
                json={
                    "request_id": str(uuid4()),
                    "session_id": session,
                    "intent": {
                        "query_text": "",
                        "currency": "INR",
                        "category": None,
                        "size": None,
                        "colour": None,
                        "material": None,
                        "max_price_minor": None,
                        "occasion": None,
                    },
                    "top_k": 5,
                    "mode": "filter_only",
                },
            )
            assert search.status_code == 200
            assert [hit["sku"] for hit in search.json()["hits"]] == ["FK-COMPOSE1"]
            headers = make_context(NAMESPACE).headers(str(uuid4()))
            headers["Authorization"] = "Bearer " + os.environ["INTERNAL_API_TOKEN"]
            price = client.post(
                "/internal/v1/catalog/FK-COMPOSE1/price",
                headers=headers,
                json={
                    "price_minor": 38000,
                    "expected_catalog_version": 1,
                },
            )
            assert price.status_code == 200
        delivered = []
        deadline = monotonic() + 60
        while monotonic() < deadline and len(delivered) < 3:
            batch = observer.consume_records(observer.topics, 100, 50)
            delivered.extend(
                codec.validate_event(r.value_bytes, r.headers, r.topic, r.key_bytes) for r in batch
            )
            for record in batch:
                observer.mark_durable(record)
            assert observer.commit_offsets(observer.durable_next_offsets()).succeeded
        assert sorted(item.envelope.event_type for item in delivered) == [
            "PRICE_UPDATED",
            "PRODUCT_RETRIEVED",
            "SEARCH_REQUESTED",
        ]
        with psycopg.connect(
            os.environ["CATALOG_COMPOSE_TEST_DATABASE_URL"], connect_timeout=5
        ) as tx:
            assert tx.execute(
                "SELECT count(*),count(published_at) FROM outbox WHERE namespace=%s", (NAMESPACE,)
            ).fetchone() == (3, 3)
    finally:
        observer.close()
        publisher.close()
