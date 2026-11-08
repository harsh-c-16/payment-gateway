"""M06 pure normalization and Arrow checks; these make no durability claims."""

import copy
import hashlib

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from pipelines.curation.normalization import normalize_payload
from pipelines.storage.parquet import PAYLOAD_TYPE, SILVER_EVENTS_SCHEMA
from pipelines.storage.publication import _silver_row
from shared.contracts.events import EVENTS, EventEnvelope
from shared.event_transport.schemas import canonical_json

from .event_examples import examples


@pytest.mark.parametrize("name", EVENTS)
def test_all_registered_payloads_round_trip_typed_silver(name):
    original = examples()[name]
    original["metadata"]["catalog_dictionary_sha256"] = "a" * 64
    document = copy.deepcopy(original)
    event = EventEnvelope.model_validate(document)
    normalized = normalize_payload(event)
    row = _silver_row(
        {
            "document": document,
            "namespace": event.namespace,
            "event_time": event.event_time,
            "content_hash": hashlib.sha256(canonical_json(document)).hexdigest(),
            "normalized_payload": normalized,
            "raw_locator": "bronze/source.jsonl#0",
        }
    )
    table = pa.Table.from_pylist([row], schema=SILVER_EVENTS_SCHEMA)
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink, compression="zstd")
    decoded = pq.read_table(pa.BufferReader(sink.getvalue())).to_pylist()[0]
    assert decoded["envelope_json"] == canonical_json(original).decode()
    assert decoded["event_time"] == event.event_time
    assert decoded["produced_at"] == event.produced_at
    assert decoded["dataset_revision"] == "synthetic-v1"
    assert decoded["synthetic"] is True and decoded["scenario_source"] == "simulation"
    assert decoded["content_hash"] == hashlib.sha256(canonical_json(original)).hexdigest()
    assert document == original
    for key, value in normalized.items():
        actual = decoded["payload"][key]
        if key in ("created_at", "changed_at", "attempt_created_at"):
            assert actual.isoformat().replace("+00:00", "Z") == value
        elif key == "intent":
            assert actual == value
            assert all(
                actual[field] is None
                for field in ("category", "brand", "size", "colour", "material")
            )
        else:
            assert actual == value
    assert set(normalized).issubset({field.name for field in PAYLOAD_TYPE})


def test_optional_intent_nulls_do_not_change_immutable_wire_content():
    document = examples()["INTENT_EXTRACTED"]
    del document["payload"]["intent"]["brand"]
    del document["payload"]["intent"]["category_path_prefix"]
    before = canonical_json(document)
    payload = normalize_payload(EventEnvelope.model_validate(document))
    assert payload["intent"]["brand"] is None
    assert payload["intent"]["category_path_prefix"] is None
    assert canonical_json(document) == before


def test_examples_do_not_share_mutable_intent_state():
    first = examples()
    first["INTENT_EXTRACTED"]["payload"]["intent"]["brand"] = "explicit changed fixture"
    assert first["SEARCH_REQUESTED"]["payload"]["intent"]["brand"] is None
    assert examples()["INTENT_EXTRACTED"]["payload"]["intent"]["brand"] is None


def test_worker_subscribes_to_five_business_domains_and_closes_on_failure(monkeypatch):
    from pipelines.ingestion import worker

    captured = {}
    delays = []
    groups = []

    class GroupDouble:
        def __init__(self, name, topics, bootstrap, *, workers, worker_index):
            assert (workers, worker_index) == (1, 0)
            assert all(group.closed for group in groups)
            self.closed = False
            groups.append(self)
            captured.update(name=name, topics=topics)

        def buffer_snapshot(self):
            return {"namespace": "bench-m06", "observed_at": "2026-11-02T00:00:00Z"}

        def close(self):
            self.closed = True
            captured["closed"] = True

    class PipelineDouble:
        def ingest_once(self, group, **kwargs):
            # B0/O1 share the capture bound; SQL transaction grouping is separate.
            assert kwargs["max_records"] == 100
            raise OSError("explicit sink outage")

    monkeypatch.setattr(worker, "ConsumerGroup", GroupDouble)
    monkeypatch.setattr(worker, "worker_allocation", lambda: (1, 0))
    monkeypatch.setattr(worker, "sleep", delays.append)
    with pytest.raises(OSError, match="outage"):
        worker.run(PipelineDouble(), "bench-m06", "explicit-fixture", "unused")
    assert captured["topics"] == [
        f"bench-m06.{domain}-events.v1"
        for domain in ("conversation", "inventory", "order", "payment", "retrieval")
    ]
    assert captured["closed"] is True
    assert len(groups) == 4 and delays == [0.25, 0.5, 1.0]
