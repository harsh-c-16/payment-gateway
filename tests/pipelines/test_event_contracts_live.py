"""Opt-in real registry compatibility and plain-JSON domain wire smoke."""

import copy
import json
import os
from time import monotonic
from uuid import uuid4

import httpx
import pytest
from confluent_kafka import Consumer, Producer, TopicPartition

from infra import streaming
from shared.contracts.events import DlqNotice, EventEnvelope
from shared.event_transport.schemas import (
    SchemaCache,
    StrictValidator,
    canonical_json,
    register_schemas,
)

from .event_examples import examples


@pytest.mark.skipif(
    os.environ.get("RUN_CONTRACTS_LIVE_TESTS") != "1",
    reason="Real Kafka/registry required; RUN_CONTRACTS_LIVE_TESTS=1",
)
def test_registry_compatibility_and_all_domain_wire_examples():
    cache = SchemaCache.load(streaming.SCHEMA_CACHE)
    compatibility = []
    with httpx.Client(base_url=streaming.REGISTRY, timeout=30, trust_env=False) as client:
        first = cache.verify_online(client)
        repeated = register_schemas(client, streaming.SCHEMA_CACHE)
        assert [
            entry["id"] for entry in [*repeated["schemas"], *repeated["historical_schemas"]]
        ] == [entry["id"] for entry in first]
        for subject, entry in cache.entries.items():
            old = entry["schema"]
            compatible = copy.deepcopy(old)
            # Open content model: an unconstrained optional property accepts all old values.
            compatible["properties"]["optional_review_note"] = {}
            unsafe_optional = copy.deepcopy(old)
            unsafe_optional["properties"]["optional_review_note"] = {"type": "string"}
            incompatible = copy.deepcopy(old)
            incompatible["properties"]["schema_version"] = {"type": "string"}
            outcomes = []
            for candidate in (compatible, incompatible, unsafe_optional):
                response = client.post(
                    f"/compatibility/subjects/{subject}/versions",
                    json={"schemaType": "JSON", "schema": canonical_json(candidate).decode()},
                )
                response.raise_for_status()
                outcomes.append(response.json()["is_compatible"])
            assert outcomes == [True, False, False], (subject, outcomes)
            domain = subject.removesuffix(".v1-value")
            for doc in examples().values():
                record = (
                    DlqNotice.model_validate(doc)
                    if "origin_kind" in doc
                    else EventEnvelope.model_validate(doc)
                )
                if record.topic().split(".", 1)[1] != domain + ".v1":
                    continue
                for schema in (old, compatible):
                    StrictValidator({k: v for k, v in schema.items() if k != "$schema"}).validate(
                        doc
                    )
            compatibility.append(
                {
                    "subject": subject,
                    "compatible_optional": outcomes[0],
                    "breaking_type": outcomes[1],
                    "typed_optional_open_model": outcomes[2],
                }
            )
    namespace = "bench-m02-" + uuid4().hex
    streaming.provision_topics(namespace)
    producer = Producer(
        {
            "bootstrap.servers": streaming.BOOTSTRAP,
            "enable.idempotence": True,
            "acks": "all",
            "max.in.flight.requests.per.connection": 5,
        }
    )
    acknowledgements = []
    emitted = {}

    def delivered(error, message):
        assert error is None, str(error)
        acknowledgements.append(
            {"topic": message.topic(), "partition": message.partition(), "offset": message.offset()}
        )

    for doc in examples().values():
        doc["namespace"] = namespace
        record = (
            DlqNotice.model_validate(doc)
            if "origin_kind" in doc
            else EventEnvelope.model_validate(doc)
        )
        subject = record.topic().split(".", 1)[1] + "-value"
        headers = [
            ("content-type", b"application/json"),
            ("schema-id", str(cache.entries[subject]["id"]).encode()),
        ]
        raw = canonical_json(doc)
        cache.validate(raw, headers, record.topic(), record.kafka_key().encode())
        emitted[record.event_id] = raw
        producer.produce(
            record.topic(),
            key=record.kafka_key().encode(),
            value=raw,
            headers=headers,
            on_delivery=delivered,
        )
    assert producer.flush(45) == 0
    assert len(acknowledgements) == len(emitted) == 25
    consumer = Consumer(
        {
            "bootstrap.servers": streaming.BOOTSTRAP,
            "group.id": namespace + ".contract-smoke",
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
        }
    )
    received = set()
    try:
        consumer.assign([TopicPartition(topic, 0, 0) for topic in streaming.topic_names(namespace)])
        deadline = monotonic() + 60
        while len(received) < len(emitted) and monotonic() < deadline:
            message = consumer.poll(1)
            if message is None:
                continue
            assert not message.error(), message.error()
            checked = cache.validate(
                message.value(), message.headers(), message.topic(), message.key()
            )
            assert message.value() == emitted[checked.envelope.event_id]
            received.add(checked.envelope.event_id)
        assert received == emitted.keys()
    finally:
        consumer.close()
    evidence = streaming.ROOT / "artifacts/m02/live-contracts.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(
        json.dumps(
            {
                "test_mode": "real",
                "namespace": namespace,
                "schema_mapping": first,
                "compatibility": compatibility,
                "broker_acknowledgements": acknowledgements,
                "received_ids": sorted(received),
                "count": len(received),
                "gold_integration": "NOT_RUN; M05 required",
            },
            indent=2,
        )
    )
