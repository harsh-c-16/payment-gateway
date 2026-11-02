"""M06 real PostgreSQL/files. Notifications use the explicit SQL outbox double."""

import base64
import json
from collections import defaultdict
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from pipelines.storage.parquet import read_verified
from pipelines.storage.readers import quarantine
from shared.contracts.events import EVENTS, EventEnvelope
from shared.event_transport.consumer import raw_fingerprint
from shared.event_transport.schemas import canonical_json

from . import test_vertical_live as live
from .event_examples import examples
from .test_vertical_live import count, curate, record

vertical = live.vertical
outbox_double = live.outbox_double
pytestmark = live.pytestmark


def domain_event(pipeline, name, version):
    document = examples()[name]
    document.update(
        namespace=pipeline.test_namespace,
        event_id=str(uuid4()),
        event_time=pipeline.test_event_time.isoformat().replace("+00:00", "Z"),
        produced_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        aggregate_version=version,
    )
    if "stock_version" in document["payload"]:
        document["payload"]["stock_version"] = version
    if "catalog_version" in document["payload"]:
        document["payload"]["catalog_version"] = version
    document["metadata"]["catalog_dictionary_sha256"] = "c" * 64
    return EventEnvelope.model_validate(document)


def test_all_24_domains_unique_duplicate_redelivery_and_active_files(vertical):
    offsets = defaultdict(int)
    events = [domain_event(vertical, name, index) for index, name in enumerate(EVENTS, 1)]

    def delivery(event):
        offset = offsets[event.topic()]
        offsets[event.topic()] += 1
        return record(vertical, event, offset)

    original = [delivery(event) for event in events]
    assert curate(vertical, original).new_valid == 24
    assert curate(vertical, [delivery(event) for event in events]).duplicate_delivery == 24
    assert curate(vertical, original).redelivery_noop == 24
    assert count(vertical, "silver_events") == 24
    manifest = vertical.publish_snapshot(vertical.test_namespace)
    silver = vertical.active_manifest(vertical.test_namespace, "silver")
    decoded = [
        row for file in silver.files for row in read_verified(vertical.store, file).to_pylist()
    ]
    assert {row["event_type"] for row in decoded} == set(EVENTS)
    assert len(decoded) == 24 and len({row["event_id"] for row in decoded}) == 24
    for row in decoded:
        assert row["dataset_revision"] == "synthetic-v1"
        assert row["event_time"] == vertical.test_event_time
        assert json.loads(row["metadata_json"])["catalog_dictionary_sha256"] == "c" * 64
    intent = next(
        row["payload"]["intent"] for row in decoded if row["event_type"] == "INTENT_EXTRACTED"
    )
    assert all(intent[key] is None for key in ("category", "brand", "size", "colour", "material"))
    with vertical.connect() as tx:
        assert tx.execute("SELECT sum(unique_events) FROM pipeline_minute").fetchone()[0] == 24
        assert tx.execute("SELECT count(*) FROM reducer_contributions").fetchone()[0] == 24
        assert (
            tx.execute(
                "SELECT count(*) FROM source_receipts WHERE disposition IS NOT NULL"
            ).fetchone()[0]
            == 48
        )
        assert (
            tx.execute(
                "SELECT count(*) FROM event_visibility WHERE observed_at IS NOT NULL"
            ).fetchone()[0]
            == 24
        )
        assert tx.execute("SELECT count(*) FROM export_pending").fetchone()[0] == 0
        assert {
            row[0] for row in tx.execute("SELECT version FROM analytics_schema_migrations")
        } == {1, 2, 3, 4, 5, 6, 7, 8}
    Path("artifacts/m06/all-domains.json").write_text(
        json.dumps(
            {
                "source_commit": vertical.code_commit,
                "namespace": vertical.test_namespace,
                "new_valid": 24,
                "duplicate_delivery": 24,
                "redelivery_noop": 24,
                "source_dispositions": 48,
                "active_gold_generation": manifest.generation,
                "active_silver_event_types": sorted(EVENTS),
                "real_outbox": "NOT_RUN; absent",
            },
            indent=2,
        )
    )


def test_cross_type_versions_conflicts_and_out_of_order_valid_facts(vertical, outbox_double):
    first = domain_event(vertical, "STOCK_UPDATED", 3)
    assert curate(vertical, [record(vertical, first)]).new_valid == 1
    conflict = domain_event(vertical, "INVENTORY_RELEASED", 3)
    assert curate(vertical, [record(vertical, conflict, 1)]).invalid == 1
    altered = first.model_copy(
        update={"produced_at": first.produced_at + timedelta(microseconds=1)}
    )
    assert curate(vertical, [record(vertical, altered, 2)]).invalid == 1
    older = domain_event(vertical, "INVENTORY_RESERVED", 2)
    assert curate(vertical, [record(vertical, older, 3)]).new_valid == 1
    assert curate(vertical, [record(vertical, first, 4)]).duplicate_delivery == 1
    first_page = quarantine(vertical.connect, vertical.test_namespace, limit=1)
    second_page = quarantine(vertical.connect, vertical.test_namespace, first_page.next_cursor, 1)
    empty_page = quarantine(vertical.connect, vertical.test_namespace, second_page.next_cursor, 1)
    assert first_page.next_cursor == first_page.records[0].quarantine_id
    assert second_page.next_cursor == second_page.records[0].quarantine_id
    assert empty_page.records == [] and empty_page.next_cursor is None
    failures = first_page.records + second_page.records
    assert [q.reason_code for q in failures] == ["AGGREGATE_VERSION_CONFLICT", "EVENT_ID_CONFLICT"]
    assert count(vertical, "test_outbox_double") == 2 and count(vertical, "silver_events") == 2
    with vertical.connect() as tx:
        assert tx.execute("SELECT sum(unique_events) FROM pipeline_minute").fetchone()[0] == 2


def test_sink_failure_rolls_back_only_failed_b0_record_and_can_resume(vertical):
    first = domain_event(vertical, "CONVERSATION_TURN", 1)
    second = domain_event(vertical, "STOCK_UPDATED", 1)
    records = [record(vertical, first), record(vertical, second)]
    with vertical.connect() as tx:
        tx.execute("""CREATE FUNCTION m06_sink_fault() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.event_type='STOCK_UPDATED' THEN RAISE EXCEPTION 'explicit reducer outage';
            END IF; RETURN NEW; END $$""")
        tx.execute("""CREATE TRIGGER m06_fault BEFORE INSERT ON pipeline_minute
            FOR EACH ROW EXECUTE FUNCTION m06_sink_fault()""")
    with pytest.raises(psycopg.Error, match="outage"):
        curate(vertical, records)
    with vertical.connect() as tx:
        assert tx.execute("SELECT count(*) FROM silver_events").fetchone()[0] == 1
        assert tx.execute("SELECT count(*) FROM reducer_contributions").fetchone()[0] == 1
        assert tx.execute("SELECT count(*) FROM export_pending").fetchone()[0] == 1
        assert tx.execute("SELECT count(*) FROM quarantine").fetchone()[0] == 0
        assert (
            tx.execute("SELECT count(*) FROM source_receipts WHERE disposition IS NULL").fetchone()[
                0
            ]
            == 1
        )
        tx.execute("DROP TRIGGER m06_fault ON pipeline_minute")
    outcome = curate(vertical, records)
    assert outcome.redelivery_noop == 1 and outcome.new_valid == 1
    assert count(vertical, "silver_events") == 2


def test_dead_letter_notices_never_enter_business_silver(vertical):
    from shared.contracts.events import DlqNotice

    document = examples()["DLQ_NOTICE"]
    document["namespace"] = vertical.test_namespace
    notice = DlqNotice.model_validate(document)
    with pytest.raises(ValueError, match="DLQ"):
        curate(vertical, [record(vertical, notice)])
    assert count(vertical, "silver_events") == 0 and count(vertical, "quarantine") == 0


def test_utc_day_boundaries_and_canonical_facets_are_preserved(vertical):
    event = domain_event(vertical, "INTENT_EXTRACTED", 1)
    event.payload["intent"].update(brand="Already Canonical", colour="Cotton Blue", size="M")
    event = event.model_copy(update={"event_time": vertical.test_event_time.replace(hour=0)})
    assert curate(vertical, [record(vertical, event)]).new_valid == 1
    vertical.publish_snapshot(vertical.test_namespace)
    manifest = vertical.active_manifest(vertical.test_namespace, "silver")
    row = read_verified(vertical.store, manifest.files[0]).to_pylist()[0]
    assert manifest.files[0].partition_values["event_date"] == event.event_time.date().isoformat()
    assert row["payload"]["intent"]["brand"] == "Already Canonical"
    assert row["payload"]["intent"]["colour"] == "Cotton Blue"
    assert row["payload"]["intent"]["size"] == "M"


def test_quality_ratio_smoke_with_all_ten_invalid_subcases(vertical, outbox_double):
    # Explicit 2,000-record synthetic smoke, not the required full W-QUALITY run.
    valid = [
        record(vertical, domain_event(vertical, "STOCK_UPDATED", i + 1), i) for i in range(1970)
    ]
    duplicates = [replace(valid[i], offset=1970 + i) for i in range(20)]
    invalid = []
    expected_reasons = [
        "INVALID_JSON",
        "INVALID_UTF8",
        "MISSING_REQUIRED",
        "MISSING_REQUIRED",
        "INVALID_AMOUNT",
        "INVALID_QUANTITY",
        "UNSUPPORTED_SCHEMA",
        "UNSUPPORTED_SCHEMA",
        "KEY_MISMATCH",
        "INVALID_TIMESTAMP",
    ]
    offsets = defaultdict(int, {valid[0].topic: 1990})
    for index in range(10):
        name = "PRICE_UPDATED" if index == 4 else "ADD_TO_CART" if index == 5 else "STOCK_UPDATED"
        source = record(vertical, domain_event(vertical, name, 10000 + index))
        source = replace(source, offset=offsets[source.topic])
        offsets[source.topic] += 1
        doc = json.loads(source.value_bytes)
        raw, key, headers = source.value_bytes, source.key_bytes, source.headers
        if index == 0:
            raw = b"{"
        elif index == 1:
            raw = b"\xff"
        elif index in (2, 3):
            del doc["event_id" if index == 2 else "payload"]
        elif index == 4:
            doc["payload"]["price_minor"] = "100"
        elif index == 5:
            doc["payload"]["quantity_after"] = -1
        elif index == 6:
            headers = tuple(
                (name, b"999999999" if name == "schema-id" else value) for name, value in headers
            )
        elif index == 7:
            doc["schema_version"] = 2
        elif index == 8:
            key = b"wrong-key"
        elif index == 9:
            doc["event_time"] = "2026-01-01T12:00:00+05:30"
        if index not in (0, 1):
            raw = canonical_json(doc)
        invalid.append(
            replace(
                source,
                key_bytes=key,
                value_bytes=raw,
                headers=headers,
                raw_sha256=raw_fingerprint(key, raw, headers),
            )
        )
    outcome = curate(vertical, valid + duplicates + invalid)
    assert (
        outcome.source_records,
        outcome.new_valid,
        outcome.duplicate_delivery,
        outcome.invalid,
    ) == (2000, 1970, 20, 10)
    failures = quarantine(vertical.connect, vertical.test_namespace).records
    assert [failure.reason_code for failure in failures] == expected_reasons
    for source, failure in zip(invalid, failures, strict=True):
        path, line = failure.source_locator.raw_locator.rsplit("#", 1)
        wrapper = json.loads(vertical.store.read(path).splitlines()[int(line) - 1])
        assert base64.b64decode(wrapper["value_base64"]) == source.value_bytes
        assert failure.raw_sha256 == source.raw_sha256
    vertical.publish_snapshot(vertical.test_namespace)
    with vertical.connect() as tx:
        actual = dict(
            tx.execute("SELECT disposition,count(*) FROM source_receipts GROUP BY disposition")
        )
        assert actual == {"new_valid": 1970, "duplicate_delivery": 20, "invalid": 10}
        assert tx.execute("SELECT count(*) FROM silver_events").fetchone()[0] == 1970
        assert tx.execute("SELECT count(*) FROM test_outbox_double").fetchone()[0] == 10
        assert (
            tx.execute(
                "SELECT count(*) FROM event_visibility WHERE observed_at IS NOT NULL"
            ).fetchone()[0]
            == 1970
        )
    gold = vertical.active_manifest(vertical.test_namespace, "gold")
    assert (
        sum(
            row["unique_events"]
            for file in gold.files
            for row in read_verified(vertical.store, file).to_pylist()
        )
        == 1970
    )
    Path("artifacts/m06/quality-smoke.json").write_text(
        json.dumps(
            {
                "source_commit": vertical.code_commit,
                "namespace": vertical.test_namespace,
                "fixture": "explicit synthetic 2000-record ratio smoke; not full W-QUALITY",
                "dispositions": actual,
                "quarantine": 10,
                "gold_unique_events": 1970,
                "notification_provider": "explicit SQL outbox double",
                "full_w_quality": "NOT_RUN",
                "reason_handoff": (
                    "wrong_money_type currently INVALID_AMOUNT; harness expects INVALID_TYPE"
                ),
            },
            indent=2,
        )
    )
