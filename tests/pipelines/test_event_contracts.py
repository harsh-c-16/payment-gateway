"""Real schema/model checks; synthetic registry IDs below are explicit offline doubles."""

import copy
import json
from datetime import UTC, datetime

import httpx
import pytest
from jsonschema import Draft7Validator
from pydantic import ValidationError

from infra.contract_assets import ROOT, analytics_openapi, assets
from shared.contracts import analytics
from shared.contracts.events import EVENTS, DlqNotice, EventEnvelope, ReasonCode
from shared.event_transport.schemas import (
    RecordInvalid,
    SchemaCache,
    SchemaUnavailable,
    canonical_json,
    documents,
    register_schemas,
)

from .event_examples import NOW, examples


@pytest.fixture
def cache():
    return SchemaCache(
        {
            "compatibility": "BACKWARD_TRANSITIVE",
            "schemas": [
                {**entry, "id": number, "version": 1, "schema": schema}
                for number, (entry, schema) in enumerate(documents().values(), 101)
            ],
        }
    )


def wire(cache, doc):
    record = (
        DlqNotice.model_validate(doc) if "origin_kind" in doc else EventEnvelope.model_validate(doc)
    )
    subject = record.topic().split(".", 1)[1] + "-value"
    headers = [
        ("content-type", b"application/json"),
        ("schema-id", str(cache.entries[subject]["id"]).encode()),
    ]
    return headers, record.topic(), record.kafka_key().encode()


@pytest.mark.parametrize("name", [*EVENTS, "DLQ_NOTICE"])
def test_every_example_passes_real_schema_and_model(cache, name):
    doc = examples()[name]
    checked = cache.validate(canonical_json(doc), *wire(cache, doc))
    assert checked.document == doc
    assert checked.envelope.event_id == doc["event_id"]


def test_generated_assets_are_reproducible_and_draft7():
    for path, content in assets().items():
        assert (ROOT / path).read_text(encoding="utf-8") == content, path
    for _entry, schema in documents().values():
        Draft7Validator.check_schema(schema)
        assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
        assert "$defs" not in canonical_json(schema).decode()
    durable = json.loads((ROOT / "tests/pipelines/fixtures/events.v1.json").read_text())
    assert durable["events"] == examples()
    assert len(EVENTS) == 24


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("aggregate_version", 1.0, "INVALID_TYPE"),
        ("aggregate_version", "1", "INVALID_TYPE"),
        ("aggregate_version", True, "INVALID_TYPE"),
        ("aggregate_version", 2**63, "INVALID_TYPE"),
        ("schema_version", 2, "UNSUPPORTED_SCHEMA"),
        ("schema_version", True, "UNSUPPORTED_SCHEMA"),
        ("event_type", "UNKNOWN", "UNKNOWN_EVENT_TYPE"),
        ("event_time", "2026-10-31T10:00:00+05:30", "INVALID_TIMESTAMP"),
        ("event_time", "not-a-time", "INVALID_TIMESTAMP"),
    ],
)
def test_invalid_envelope(cache, field, value, reason):
    original = examples()["CONVERSATION_TURN"]
    doc = {**original, field: value}
    with pytest.raises(RecordInvalid) as error:
        cache.validate(canonical_json(doc), *wire(cache, original))
    assert error.value.reason == reason


@pytest.mark.parametrize(
    "name,field,value",
    [
        ("PAYMENT_SUCCESS", "amount_minor", -1),
        ("PAYMENT_SUCCESS", "amount_minor", 1.25),
        ("PAYMENT_SUCCESS", "amount_minor", True),
        ("PAYMENT_SUCCESS", "amount_minor", "100"),
        ("ADD_TO_CART", "quantity_after", -1),
        ("ADD_TO_CART", "quantity_after", 11),
        ("ADD_TO_CART", "quantity_after", 1.5),
        ("INVENTORY_REJECTED", "reservation_request_id", None),
        ("STOCK_UPDATED", "available", 2),
        ("STOCK_UPDATED", "stock_version", 2),
        ("PRICE_UPDATED", "catalog_version", 2),
        ("PRODUCT_RETRIEVED", "returned_count", 1),
        ("PRODUCT_RETRIEVED", "mode", "unknown-mode"),
        ("CONVERSATION_TURN", "llm_call_count", 1),
    ],
)
def test_invalid_payload_and_cross_field_invariants(cache, name, field, value):
    original = examples()[name]
    doc = copy.deepcopy(original)
    doc["payload"][field] = value
    with pytest.raises(RecordInvalid):
        cache.validate(canonical_json(doc), *wire(cache, original))


def test_missing_required_and_owned_event_provenance(cache):
    original = examples()["INVENTORY_REJECTED"]
    for mutate in (
        lambda doc: doc["payload"].pop("reservation_request_id"),
        lambda doc: doc.update(source_service="catalog"),
        lambda doc: doc["metadata"].pop("dataset_revision"),
        lambda doc: doc["metadata"].update(synthetic=False),
    ):
        doc = copy.deepcopy(original)
        mutate(doc)
        with pytest.raises(RecordInvalid):
            cache.validate(canonical_json(doc), *wire(cache, original))


def test_cache_preserves_optional_nulls_and_hashes_entire_wire_envelope(cache):
    doc = examples()["INTENT_EXTRACTED"]
    doc["payload"].update(brand=None, category=None, size=None, colour=None, material=None)
    doc["metadata"]["optional_future_property"] = {"nullable": None}
    before = cache.validate(canonical_json(doc), *wire(cache, doc))
    assert before.document["payload"]["brand"] is None
    doc["produced_at"] = "2026-10-31T10:00:01Z"
    after = cache.validate(canonical_json(doc), *wire(cache, doc))
    assert before.canonical_content_hash != after.canonical_content_hash


@pytest.mark.parametrize(
    "raw,reason",
    [
        (b"\xff", "INVALID_UTF8"),
        (b"{", "INVALID_JSON"),
        (b'{"schema_version":1,"schema_version":1}', "INVALID_JSON"),
        (b'{"x":NaN}', "INVALID_JSON"),
        (b"[]", "INVALID_TYPE"),
        (b" " * 65537, "INVALID_TYPE"),
    ],
    ids=["invalid-utf8", "truncated-json", "duplicate-member", "nan", "array", "oversize"],
)
def test_raw_boundaries(cache, raw, reason):
    doc = examples()["CONVERSATION_TURN"]
    with pytest.raises(RecordInvalid) as error:
        cache.validate(raw, *wire(cache, doc))
    assert error.value.reason == reason


def test_headers_keys_topics_and_future_clock(cache):
    doc = examples()["CONVERSATION_TURN"]
    headers, topic, key = wire(cache, doc)
    for wrong in (
        [headers[0]],
        headers + [headers[1]],
        [headers[0], ("schema-id", b"999999")],
        [("content-type", b"application/avro"), headers[1]],
        [headers[0], ("schema-id", b"1.0")],
    ):
        with pytest.raises(RecordInvalid):
            cache.validate(canonical_json(doc), wrong, topic, key)
    with pytest.raises(RecordInvalid, match="SCHEMA_ID_MISMATCH"):
        wrong_id = cache.entries["dead-letter.v1-value"]["id"]
        cache.validate(
            canonical_json(doc), [headers[0], ("schema-id", str(wrong_id).encode())], topic, key
        )
    for wrong_topic, wrong_key in (
        (topic, b"wrong"),
        (topic.replace("bench-m02-examples", "dev"), key),
    ):
        with pytest.raises(RecordInvalid, match="KEY_MISMATCH"):
            cache.validate(canonical_json(doc), headers, wrong_topic, wrong_key)
    with pytest.raises(RecordInvalid, match="FUTURE_TIMESTAMP"):
        cache.validate(
            canonical_json(doc),
            headers,
            topic,
            key,
            ingested_at=datetime(2026, 10, 31, 9, 59, 54, tzinfo=UTC),
        )


def test_pinned_cache_runs_offline_and_rejects_tampering(cache, tmp_path):
    path = tmp_path / "mapping.json"
    manifest = {"compatibility": "BACKWARD_TRANSITIVE", "schemas": list(cache.entries.values())}
    path.write_text(json.dumps(manifest))
    loaded = SchemaCache.load(path)
    doc = examples()["CONVERSATION_TURN"]
    loaded.validate(canonical_json(doc), *wire(loaded, doc))
    manifest["schemas"][0]["schema"]["title"] = "tampered"
    path.write_text(json.dumps(manifest))
    with pytest.raises(SchemaUnavailable):
        SchemaCache.load(path)
    with pytest.raises(SchemaUnavailable):
        SchemaCache.load(tmp_path / "absent.json")


def test_missing_nested_fields_have_stable_reasons_and_facets_can_contain_spaces(cache):
    doc = examples()["INTENT_EXTRACTED"]
    doc["payload"]["intent"].update(brand="Synthetic Brand", colour="light blue")
    cache.validate(canonical_json(doc), *wire(cache, doc))
    del doc["payload"]["turn_id"]
    original = examples()["INTENT_EXTRACTED"]
    with pytest.raises(RecordInvalid, match="MISSING_REQUIRED"):
        cache.validate(canonical_json(doc), *wire(cache, original))


@pytest.mark.parametrize("headers", [None, {}, ["bad"], [("schema-id",)], [(1, b"2")]])
def test_malformed_header_shapes_are_validation_failures(cache, headers):
    doc = examples()["CONVERSATION_TURN"]
    _, topic, key = wire(cache, doc)
    with pytest.raises(RecordInvalid, match="INVALID_TYPE"):
        cache.validate(canonical_json(doc), headers, topic, key)


def test_json_overflow_and_unhashable_type_are_validation_failures(cache):
    doc = examples()["CONVERSATION_TURN"]
    headers, topic, key = wire(cache, doc)
    with pytest.raises(RecordInvalid, match="INVALID_JSON"):
        cache.validate(b'{"padding":1e999}', headers, topic, key)
    doc["event_type"] = []
    with pytest.raises(RecordInvalid, match="UNKNOWN_EVENT_TYPE"):
        cache.validate(canonical_json(doc), headers, topic, key)


def test_failed_registry_registration_does_not_replace_good_cache(tmp_path):
    path = tmp_path / "mapping.json"
    path.write_text("old verified cache")
    with httpx.Client(
        base_url="http://explicit-registry-double.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(503)),
    ) as client:
        with pytest.raises(httpx.HTTPStatusError):
            register_schemas(client, path)
    assert path.read_text() == "old verified cache"


def test_analytics_dtos_and_consumer_openapi_bindings():
    from services.conversation.provider_contracts import ENDPOINTS, OpenAPIContracts

    contracts = OpenAPIContracts(ROOT / "contracts/http")
    manifest = {
        "namespace": "dev",
        "dataset": "gold",
        "generation": 1,
        "parent_generation": None,
        "files": [],
        "source_ranges": [],
        "transform_version": "v1",
        "code_commit": "a" * 40,
        "input_manifest_ids": [],
        "created_at": NOW,
    }
    for name, payload in {
        "active_manifest": manifest,
        "gold": {"generation": 1, "rows": [], "queried_at": NOW},
        "receipts": {"receipts": [], "next_cursor": None},
        "quarantine": {"records": [], "next_cursor": None},
        "replay_create": {
            "replay_id": examples()["DLQ_NOTICE"]["event_id"],
            "status_url": "/status",
        },
        "replay_status": {"status": "PENDING", "counts": {}, "reconciliation": None, "error": None},
    }.items():
        contracts.validate(ENDPOINTS[name], "response", payload)
    analytics.DatasetManifest.model_validate(manifest)
    for target in ("dev", "prod", "replay-", "bench-../bad"):
        with pytest.raises(ValidationError):
            analytics.ReplayRequest(
                source_manifest_ids=["bronze-1"], target_namespace=target, transform_version="v1"
            )
    with pytest.raises(ValidationError):
        analytics.SourceRange(
            topic="dev.order-events.v1",
            partition=0,
            first_offset=10,
            next_offset=9,
            receipt_membership_ref="members-1",
        )
    api = analytics_openapi()
    assert len(api["paths"]) == 9
    for path, item in api["paths"].items():
        if path.startswith("/internal/"):
            assert next(iter(item.values()))["security"] == [{"ServiceToken": []}]
    assert len(ReasonCode) == 18
