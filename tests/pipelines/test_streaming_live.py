"""Real infrastructure smoke only; this fixture is not a domain event schema."""

import hashlib
import json
import os
from time import monotonic
from uuid import uuid4

import httpx
import pytest
from confluent_kafka import Consumer, Producer, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic
from jsonschema import Draft7Validator

from infra import streaming
from projectctl.artifacts import canonical_json


def read_one(group, topic, *, replay=False):
    consumer = Consumer(
        {
            "bootstrap.servers": streaming.BOOTSTRAP,
            "group.id": group,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
        }
    )
    try:
        if replay:
            consumer.assign([TopicPartition(topic, 0, 0)])
        else:
            consumer.subscribe([topic])
        deadline = monotonic() + 60
        while monotonic() < deadline:
            message = consumer.poll(1)
            if message is None:
                continue
            assert not message.error(), message.error()
            # This is a dedicated smoke record, never an analytical sink offset.
            if not replay:
                consumer.commit(message=message, asynchronous=False)
            committed = consumer.committed([TopicPartition(topic, 0)], timeout=15)[0].offset
            return {
                "key": message.key().decode(),
                "value": json.loads(message.value()),
                "headers": dict(message.headers()),
                "offset": message.offset(),
                "committed_next_offset": committed,
            }
        pytest.fail("No smoke record consumed before deadline")
    finally:
        consumer.close()


@pytest.mark.skipif(
    os.environ.get("RUN_STREAMING_LIVE_TESTS") != "1",
    reason="Real Kafka/registry required; RUN_STREAMING_LIVE_TESTS=1",
)
def test_plain_json_registry_groups_and_retained_volume_recreation():
    before = streaming.verify()
    namespace = "bench-m01b-" + uuid4().hex
    streaming.provision_topics(namespace)
    topic = namespace + ".infra-smoke.v1"
    admin = AdminClient({"bootstrap.servers": streaming.BOOTSTRAP})
    admin.create_topics(
        [
            NewTopic(
                topic, num_partitions=1, replication_factor=1, config={"retention.ms": "604800000"}
            )
        ]
    )[topic].result(timeout=30)
    subject = "infra-smoke.v1-value"
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "additionalProperties": False,
        "required": ["event_id", "sequence"],
        "properties": {
            "event_id": {"type": "string"},
            "sequence": {"type": "integer", "minimum": 0},
        },
    }
    schemas = []
    with httpx.Client(base_url=streaming.REGISTRY, timeout=20, trust_env=False) as client:

        def register(document):
            response = client.post(
                f"/subjects/{subject}/versions",
                json={"schemaType": "JSON", "schema": canonical_json(document).decode()},
            )
            response.raise_for_status()
            identity = response.json()["id"]
            schemas.append(
                {
                    "subject": subject,
                    "id": identity,
                    "sha256": hashlib.sha256(canonical_json(document)).hexdigest(),
                }
            )
            return identity

        register(schema)
        evolved = json.loads(json.dumps(schema))
        evolved["properties"]["optional_note"] = {"type": "string"}
        schema_id = register(evolved)
        incompatible = json.loads(json.dumps(evolved))
        incompatible["properties"]["sequence"] = {"type": "string"}
        response = client.post(
            f"/compatibility/subjects/{subject}/versions/latest",
            json={"schemaType": "JSON", "schema": canonical_json(incompatible).decode()},
        )
        response.raise_for_status()
        assert response.json()["is_compatible"] is False
    value = {"event_id": str(uuid4()), "sequence": 1}
    Draft7Validator(evolved).validate(value)
    producer = Producer(
        {
            "bootstrap.servers": streaming.BOOTSTRAP,
            "enable.idempotence": True,
            "acks": "all",
            "max.in.flight.requests.per.connection": 5,
            "compression.type": "zstd",
            "linger.ms": 5,
            "queue.buffering.max.messages": 10000,
            "queue.buffering.max.kbytes": 65536,
            "delivery.timeout.ms": 30000,
        }
    )
    deliveries = []
    producer.produce(
        topic,
        key=value["event_id"].encode(),
        value=canonical_json(value),
        headers=[("content-type", b"application/json"), ("schema-id", str(schema_id).encode())],
        on_delivery=lambda error, message: deliveries.append(
            {
                "error": str(error) if error else None,
                "partition": message.partition(),
                "offset": message.offset(),
            }
        ),
    )
    assert producer.flush(35) == 0
    assert len(deliveries) == 1 and deliveries[0]["error"] is None
    group = namespace + ".analytics.v1"
    first = read_one(group, topic)
    second = read_one(namespace + ".catalog-stock.v1", topic)
    for observed in (first, second):
        assert observed["value"] == value and observed["key"] == value["event_id"]
        assert observed["headers"]["content-type"] == b"application/json"
        assert observed["headers"]["schema-id"] == str(schema_id).encode()
        assert observed["committed_next_offset"] == observed["offset"] + 1
    streaming.compose("stop", "--timeout", "30", "schema-registry", "kafka")
    streaming.compose("rm", "--force", "schema-registry", "kafka")
    streaming.compose("up", "--detach", "--wait", "--wait-timeout", "150")
    after = streaming.verify()
    for service in ("kafka", "schema-registry"):
        assert before["containers"][service]["id"] != after["containers"][service]["id"]
    replayed = read_one(group, topic, replay=True)
    assert replayed == first
    with httpx.Client(base_url=streaming.REGISTRY, timeout=20, trust_env=False) as client:
        response = client.get(f"/schemas/ids/{schema_id}")
        response.raise_for_status()
        assert json.loads(response.json()["schema"]) == evolved
    out = streaming.RUNTIME / "checks" / str(uuid4())
    out.mkdir(parents=True)
    with (out / "live-test.json").open("x", encoding="utf-8") as stream:
        json.dump(
            {
                "before": before,
                "after": after,
                "namespace": namespace,
                "schema_mappings": schemas,
                "incompatible_schema_rejected": True,
                "broker_ack": deliveries[0],
                "independent_groups_received_same_record": True,
                "record_and_group_offset_survived_recreation": True,
                "registry_schema_survived_recreation": True,
            },
            stream,
            indent=2,
        )
