"""Actual pinned codec with explicit registry-ID and broker-ack doubles."""

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from benchmarks.pipeline_transport import PipelineTransport
from benchmarks.quality_publisher import QualityPublisher
from benchmarks.scheduler import Packet
from projectctl.providers import DependencyError
from shared.contracts.events import ValidEvent
from shared.event_transport import EventCodec
from tests.pipelines.transport_doubles import offline_cache


@pytest.fixture
def prepared():
    transport = PipelineTransport()
    transport.codec = EventCodec(offline_cache())
    transport.skus = frozenset({"FK-UNIT"})
    transport.revision, transport.namespace = "explicit-synthetic-revision", "bench-pipe-unit"
    record = {
        "expected_disposition": "new_valid",
        "duplicate_of": None,
        "payload": {
            "event_type": "STOCK_UPDATED",
            "source_service": "benchmark",
            "synthetic": True,
            "sku": "FK-UNIT",
            "stock_version": 7,
            "on_hand": 10000,
            "reserved": 0,
            "available": 10000,
            "order_id": None,
            "reservation_id": None,
            "reason_code": None,
            "target_event_bytes": 1024,
        },
    }
    context = {
        "namespace": transport.namespace,
        "run_id": str(uuid4()),
        "request_id": str(uuid4()),
        "scheduled_at": "2026-11-08T10:00:00Z",
        "produced_at": "2026-11-08T10:00:00Z",
        "record": record,
    }
    return transport, record, context


def test_materialized_fact_uses_sdk_identity_provenance_version_and_stable_bytes(prepared):
    transport, record, ctx = prepared
    first, second = transport.materialize(record, ctx), transport.materialize(record, ctx)
    assert first == second
    assert first.identity == ctx["request_id"] and first.key == "FK-UNIT"
    checked = transport.codec.validate_event(
        first.body,
        tuple((k, v.encode()) for k, v in first.headers),
        first.channel,
        first.key.encode(),
    )
    assert isinstance(checked, ValidEvent)
    event = checked.envelope
    assert event.aggregate_version == event.payload["stock_version"] == 7
    assert event.source_service == "benchmark" and event.metadata.synthetic is True
    assert event.metadata.dataset_revision == transport.revision
    assert len(first.body) >= 1024
    assert json.loads(first.body)["payload"]["changed_at"] == ctx["scheduled_at"]


@pytest.mark.parametrize("fault", ["namespace", "sku", "invalid", "operational", "size"])
def test_unplanned_or_operational_facts_are_refused_before_publication(prepared, fault):
    transport, record, ctx = prepared
    if fault == "namespace":
        ctx["namespace"] = "bench-another"
    elif fault == "sku":
        record["payload"]["sku"] = "FK-UNKNOWN"
    elif fault == "invalid":
        record["expected_disposition"] = "invalid"
    elif fault == "operational":
        record["payload"]["source_service"] = "inventory"
    else:
        record["payload"]["target_event_bytes"] = 64000
    with pytest.raises(ValueError):
        transport.materialize(record, ctx)


def test_only_sdk_acknowledgements_supply_actual_broker_coordinates(prepared):
    transport, record, ctx = prepared
    packet = transport.materialize(record, ctx)
    sent = []

    class NormalPublisherDouble:
        def publish_event(self, event, topic, key):
            sent.append(event)
            return SimpleNamespace(event_id=event.event_id, topic=topic, partition=0, offset=8)

        def close(self):
            pass

    class ForbiddenRawDouble:
        def publish(self, packet):
            pytest.fail("normal W-PIPE used the invalid-quality bypass")

        def close(self):
            pass

    transport.publisher = QualityPublisher(
        transport.codec,
        "explicit-broker-double",
        normal=NormalPublisherDouble(),
        raw=ForbiddenRawDouble(),
    )
    receipt = asyncio.run(transport(packet, ctx))
    assert receipt.source == {"topic": packet.channel, "partition": 0, "offset": 8}
    assert len(sent) == 1
    record["expected_disposition"] = "invalid"
    with pytest.raises(ValueError):
        asyncio.run(transport(Packet(packet.identity, b"{", packet.channel, packet.key), ctx))
    assert len(sent) == 1


def test_unprepared_transport_cannot_materialize_or_publish():
    transport = PipelineTransport()
    with pytest.raises(DependencyError):
        transport.materialize({}, {})


def test_observer_failure_still_closes_transport():
    from benchmarks.composition import ClosingObserver

    calls = []

    class ObserverDouble:
        config = object()

        async def __aenter__(self):
            raise RuntimeError("observer double failed")

    class TransportDouble:
        async def close(self):
            calls.append("closed")

    with pytest.raises(RuntimeError):
        asyncio.run(ClosingObserver(ObserverDouble(), TransportDouble()).__aenter__())
    assert calls == ["closed"]
