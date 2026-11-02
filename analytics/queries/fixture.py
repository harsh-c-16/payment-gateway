"""Labelled synthetic W-ANALYTICS input built through the real Bronze/Silver/Gold publisher.

Frequent publication reproduces the small-file layout the 250-ms cadence creates. Nothing here
is real Flipkart activity; every event carries metadata.synthetic=true.
"""

import random
from datetime import UTC, datetime, timedelta
from uuid import UUID

from pipelines.ingestion import BronzeCapture
from shared.contracts.events import SourceRecord
from shared.event_transport.consumer import raw_fingerprint
from shared.event_transport.schemas import SchemaCache, documents

METADATA = {"synthetic": True, "scenario_source": "simulation", "dataset_revision": "fixture"}


def offline_cache():
    """Registered schemas with local IDs: this experiment publishes nothing to a broker."""
    return SchemaCache(
        {
            "compatibility": "BACKWARD_TRANSITIVE",
            "schemas": [
                {**entry, "id": number, "version": 1, "schema": schema}
                for number, (entry, schema) in enumerate(documents().values(), 101)
            ],
        }
    )


def _uuid(rng):
    return str(UUID(int=rng.getrandbits(128), version=4))


def _context(namespace, rng, session):
    return {
        "namespace": namespace,
        "run_id": "w-analytics-fixture",
        "user_id": "synthetic-user",
        "session_id": session,
        "correlation_id": _uuid(rng),
    }


def search_events(codec, namespace, rng, at):
    session, search_id = _uuid(rng), _uuid(rng)
    context = _context(namespace, rng, session)
    returned = rng.choice((0, 3, 5))
    skus = [f"FK-FIXTURE{number:04}" for number in rng.sample(range(1000), returned)]
    return [
        codec.build_event(
            "SEARCH_REQUESTED",
            {
                "search_id": search_id,
                "intent": {
                    "query_text": "synthetic",
                    "category": None,
                    "size": None,
                    "colour": None,
                    "material": None,
                    "max_price_minor": None,
                    "occasion": None,
                    "currency": "INR",
                },
                "mode": "lexical",
            },
            context,
            "search",
            search_id,
            1,
            at,
            metadata=METADATA,
        ),
        codec.build_event(
            "PRODUCT_RETRIEVED",
            {
                "search_id": search_id,
                "skus": skus,
                "returned_count": returned,
                "mode": "lexical",
                "duration_ms": rng.uniform(1, 50),
            },
            context,
            "search",
            search_id,
            2,
            at,
            metadata=METADATA,
        ),
    ]


def order_events(codec, namespace, rng, at):
    order_id, session, quote = _uuid(rng), _uuid(rng), _uuid(rng)
    amount = rng.randrange(100, 100000) * 100
    context = _context(namespace, rng, session)
    base = {
        "order_id": order_id,
        "total_amount_minor": amount,
        "currency": "INR",
        "created_at": at,
        "user_id": "synthetic-user",
        "session_id": session,
        "quote_id": quote,
        "failure_code": None,
    }
    built = [
        codec.build_event(
            "ORDER_CREATED",
            {**base, "order_status": "PENDING"},
            context,
            "order",
            order_id,
            1,
            at,
            metadata=METADATA,
            source_service="orders",
        )
    ]
    payment_id = _uuid(rng)
    declined = rng.random() < 0.05
    built.append(
        codec.build_event(
            "PAYMENT_FAILED" if declined else "PAYMENT_SUCCESS",
            {
                "payment_id": payment_id,
                "order_id": order_id,
                "attempt_number": 1,
                "status": "FAILED" if declined else "SUCCESS",
                "amount_minor": amount,
                "currency": "INR",
                "attempt_created_at": at,
                "failure_code": "DECLINED" if declined else None,
                "debit_id": None if declined else _uuid(rng),
                "reversal_id": None,
            },
            context,
            "payment_attempt",
            payment_id,
            1,
            at,
            metadata=METADATA,
            source_service="payments",
        )
    )
    built.append(
        codec.build_event(
            "ORDER_CANCELLED" if declined else "ORDER_CONFIRMED",
            {
                **base,
                "order_status": "CANCELLED" if declined else "CONFIRMED",
                "failure_code": "DECLINED" if declined else None,
                **({} if declined else {"reservation_id": _uuid(rng), "payment_id": payment_id}),
            },
            context,
            "order",
            order_id,
            2,
            at,
            metadata=METADATA,
            source_service="orders",
        )
    )
    return built


def records_for(codec, events, namespace, offsets):
    records = []
    for event in events:
        raw, headers, topic, key = codec.encode(event)
        key = key.encode() if isinstance(key, str) else key
        records.append(
            SourceRecord(
                namespace,
                topic,
                0,
                offsets.setdefault(topic, 0),
                key,
                raw,
                tuple(headers),
                None,
                datetime.now(UTC),
                raw_fingerprint(key, raw, tuple(headers)),
            )
        )
        offsets[topic] += 1
    return records


def build(pipeline, namespace, *, publications, events_per_publication, days=7, seed=42):
    """publications × events_per_publication synthetic events, published batch by batch."""
    rng = random.Random(seed)
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    offsets, total = {}, 0
    capture = BronzeCapture(pipeline.store)
    for _ in range(publications):
        events = []
        while len(events) < events_per_publication:
            at = (now - timedelta(days=rng.randrange(days))).isoformat().replace("+00:00", "Z")
            make = search_events if rng.random() < 0.7 else order_events
            events += make(pipeline.codec, namespace, rng, at)
        records = records_for(pipeline.codec, events, namespace, offsets)
        pipeline.curate_silver(capture.ingest_bronze(records), {"run_id": "w-analytics-fixture"})
        pipeline.publish_snapshot(namespace)
        total += len(events)
    return {"events": total, "publications": publications, "synthetic": True, "seed": seed}
