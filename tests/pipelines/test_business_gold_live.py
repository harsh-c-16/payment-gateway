"""M07 real SQL and durable files; producer payloads are explicit synthetic fixtures."""

import asyncio
from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import uuid4

import httpx
import psycopg
import pytest

import pipelines.gold.business as business
import pipelines.storage.publication as publication
from pipelines.curation import UnsupportedEvent
from pipelines.ingestion.api import create_app
from pipelines.ingestion.receipts import migrate_analytics
from pipelines.storage.parquet import read_verified
from shared.contracts.events import EventEnvelope

from . import test_vertical_live as live
from .test_silver_live import domain_event
from .test_vertical_live import curate, record

vertical = live.vertical
outbox_double = live.outbox_double
pytestmark = live.pytestmark
DAY = "2026-10-31T10:00:00Z"
NEXT = "2026-11-01T10:00:00Z"


def fact(pipeline, name, version=1, *, at=DAY, **payload):
    document = domain_event(pipeline, name, version).model_dump(mode="json")
    document["event_time"] = at
    document["payload"].update(payload)
    aggregate = document["aggregate_type"]
    key = {
        "order": "order_id",
        "payment_attempt": "payment_id",
        "sku": "sku",
        "search": "search_id",
    }[aggregate]
    document["aggregate_id"] = document["payload"][key]
    return EventEnvelope.model_validate(document)


def deliver(pipeline, *events):
    if not hasattr(pipeline, "test_offsets"):
        pipeline.test_offsets = defaultdict(int)
    records = []
    for event in events:
        topic = event.topic()
        records.append(record(pipeline, event, pipeline.test_offsets[topic]))
        pipeline.test_offsets[topic] += 1
    return curate(pipeline, records)


def query(pipeline, table, start="2026-10-30", end="2026-11-03", currency=None):
    return pipeline.query_gold(pipeline.test_namespace, table, start, end, currency).rows


def scalar(pipeline, statement):
    with pipeline.connect() as tx:
        return tx.execute(statement).fetchone()[0]


def test_late_parent_resolves_distinct_funnel_and_preserves_lineage(vertical):
    events = [
        fact(vertical, "PAYMENT_SUCCESS"),
        fact(vertical, "INVENTORY_RESERVED"),
        fact(vertical, "INVENTORY_COMMITTED", 2),
    ]
    assert deliver(vertical, *events).new_valid == 3
    assert scalar(vertical, "SELECT count(*) FROM pending_order_joins") == 3
    vertical.publish_snapshot(vertical.test_namespace)
    assert query(vertical, "checkout_funnel") == []
    assert query(vertical, "payment_failures")[0]["successful_attempts"] == 1
    order = fact(vertical, "ORDER_CONFIRMED", 3)
    assert deliver(vertical, order).new_valid == 1
    assert scalar(vertical, "SELECT count(*) FROM pending_order_joins") == 0
    manifest = vertical.publish_snapshot(vertical.test_namespace)
    funnel = query(vertical, "checkout_funnel")[0]
    assert all(
        funnel[key + "_orders"] == 1
        for key in ("created", "reserved", "payment_success", "inventory_committed", "confirmed")
    )
    assert funnel["namespace"] == vertical.test_namespace
    assert funnel["publication_generation"] == manifest.generation == 2
    assert funnel["transform_version"] == "m07-business-v1" and funnel["revision"] > 0
    assert query(vertical, "order_fact")[0]["order_version"] == 3
    assert deliver(vertical, *events, order).duplicate_delivery == 4
    assert vertical.publish_snapshot(vertical.test_namespace).generation == 2
    for descriptor in manifest.files:
        assert read_verified(vertical.store, descriptor).num_rows == descriptor.row_count


def test_order_latest_state_historical_stage_and_exact_money_http(vertical):
    maximum = 2**63 - 1
    order_id = str(uuid4())
    confirmed = fact(vertical, "ORDER_CONFIRMED", 2, total_amount_minor=maximum)
    cancelled = fact(vertical, "ORDER_CANCELLED", 3, total_amount_minor=maximum)
    pending = fact(vertical, "ORDER_CREATED", total_amount_minor=maximum)
    other = fact(vertical, "ORDER_CONFIRMED", order_id=order_id, total_amount_minor=maximum)
    assert deliver(vertical, cancelled, pending, confirmed, other).new_valid == 4
    vertical.publish_snapshot(vertical.test_namespace)
    daily = query(vertical, "daily_conversion", currency="INR")[0]
    assert (
        daily["created_orders"],
        daily["confirmed_orders"],
        daily["cancelled_orders"],
        daily["pending_orders"],
        daily["conversion"],
    ) == (2, 1, 1, 0, 0.5)
    assert daily["created_amount_minor"] == 2 * maximum
    assert isinstance(daily["created_amount_minor"], int)
    assert query(vertical, "checkout_funnel")[0]["confirmed_orders"] == 2
    assert sorted(row["order_version"] for row in query(vertical, "order_fact")) == [1, 3]

    async def check():
        app = create_app(vertical, internal_token="synthetic-test-token")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://analytics"
        ) as client:
            response = await client.get(
                "/v1/analytics/gold/daily_conversion",
                params={
                    "namespace": vertical.test_namespace,
                    "date_from": "2026-10-31",
                    "date_to": "2026-11-01",
                    "currency": "INR",
                },
            )
            assert response.status_code == 200
            assert response.json()["rows"][0]["created_amount_minor"] == 2 * maximum

    asyncio.run(check())
    assert query(vertical, "daily_conversion", "2026-11-01", "2026-11-02") == []


@pytest.mark.parametrize("newest_first", [False, True])
def test_cohort_correction_rewrites_both_dates_and_zero_denominator(vertical, newest_first):
    events = [
        fact(vertical, "ORDER_CREATED"),
        fact(vertical, "ORDER_CONFIRMED", 2, created_at=NEXT),
    ]
    if newest_first:
        events.reverse()
    deliver(vertical, events[0])
    vertical.publish_snapshot(vertical.test_namespace)
    deliver(vertical, events[1])
    vertical.publish_snapshot(vertical.test_namespace)
    daily = {row["cohort_date"][:10]: row for row in query(vertical, "daily_conversion")}
    assert daily["2026-10-31"]["created_orders"] == 0
    assert daily["2026-10-31"]["conversion"] is None
    assert daily["2026-11-01"]["conversion"] == 1
    assert daily["2026-10-31"]["revision"] == (1 if newest_first else 2)
    assert len(query(vertical, "order_fact")) == 1
    assert query(vertical, "order_fact")[0]["created_at"] == NEXT


def test_payment_attempts_latest_outcomes_not_transition_counts(vertical):
    events = [
        fact(vertical, "PAYMENT_REVERSED", 3),
        fact(vertical, "PAYMENT_SUCCESS", 2),
        fact(vertical, "PAYMENT_FAILED"),
        fact(vertical, "PAYMENT_FAILED", payment_id=str(uuid4())),
        fact(vertical, "PAYMENT_PENDING", payment_id=str(uuid4())),
        fact(vertical, "PAYMENT_CANCELLED", payment_id=str(uuid4())),
    ]
    assert deliver(vertical, *events).new_valid == 6
    vertical.publish_snapshot(vertical.test_namespace)
    rows = query(vertical, "payment_failures")
    assert sum(row["failed_attempts"] for row in rows) == 1
    assert sum(row["successful_attempts"] for row in rows) == 0
    assert sum(row["reversed_attempts"] for row in rows) == 1
    assert sum(row["pending_attempts"] for row in rows) == 1
    assert sum(row["cancelled_attempts"] for row in rows) == 1
    assert sum(row["reversed_amount_minor"] for row in rows) == 439800
    assert next(r for r in rows if r["failure_code"])["failure_code"] == "SIMULATED_FAILURE"
    deliver(vertical, fact(vertical, "ORDER_CREATED"))
    vertical.publish_snapshot(vertical.test_namespace)
    assert query(vertical, "checkout_funnel")[0]["payment_success_orders"] == 1


def test_inventory_operation_dedup_utc_and_conflict_quarantine(vertical, outbox_double):
    first = fact(vertical, "INVENTORY_REJECTED", at=NEXT)
    second_sku = fact(vertical, "INVENTORY_REJECTED", sku="FK-SYNTHETIC-2")
    another = fact(vertical, "INVENTORY_REJECTED", 2, reservation_request_id=str(uuid4()))
    assert deliver(vertical, first, second_sku, another).new_valid == 3
    vertical.publish_snapshot(vertical.test_namespace)
    rows = query(vertical, "inventory_failures")
    assert len(rows) == 1 and rows[0]["failed_reservations"] == 2
    assert rows[0]["cohort_date"] == "2026-10-31T00:00:00Z"
    bad = fact(vertical, "INVENTORY_REJECTED", 3, reason_code="INVALID_QUANTITY")
    assert deliver(vertical, bad).invalid == 1
    assert scalar(vertical, "SELECT count(*) FROM quarantine") == 1
    assert scalar(vertical, "SELECT count(*) FROM test_outbox_double") == 1
    assert scalar(vertical, "SELECT count(*) FROM silver_events") == 3
    assert scalar(vertical, "SELECT count(*) FROM gold_business_contributions") == 3
    assert scalar(vertical, "SELECT sum(unique_events) FROM pipeline_minute") == 3
    assert scalar(vertical, "SELECT count(*) FROM export_pending") == 0


def test_search_unique_completions_exact_duration_references_and_quality_unavailable(vertical):
    requested = fact(vertical, "SEARCH_REQUESTED")
    first = fact(vertical, "PRODUCT_RETRIEVED", 2, duration_ms=0.1)
    second = fact(vertical, "PRODUCT_RETRIEVED", search_id=str(uuid4()), duration_ms=0.2)
    assert deliver(vertical, requested, first, second).new_valid == 3
    vertical.publish_snapshot(vertical.test_namespace)
    row = query(vertical, "search_performance")[0]
    assert row["unique_searches"] == row["empty_results"] == row["duration_count"] == 2
    assert row["duration_sum_ms"] == "0.3"
    assert sum(Decimal(r["duration_ms"]) for r in row["duration_references"]) == Decimal("0.3")
    corrected = fact(vertical, "PRODUCT_RETRIEVED", 3, at=NEXT, duration_ms=0.5)
    deliver(vertical, corrected)
    vertical.publish_snapshot(vertical.test_namespace)
    rows = query(vertical, "search_performance")
    assert len(rows) == 2 and sum(r["unique_searches"] for r in rows) == 2
    assert sum(Decimal(r["duration_sum_ms"]) for r in rows) == Decimal("0.7")
    with pytest.raises(ValueError, match="currency"):
        query(vertical, "search_performance", currency="INR")
    for table in ("intent_accuracy", "retrieval_quality"):
        with pytest.raises(UnsupportedEvent, match="Labelled"):
            query(vertical, table)


def test_frozen_business_state_keeps_concurrent_dirty_membership(vertical, monkeypatch):
    deliver(vertical, fact(vertical, "ORDER_CREATED"))
    original = publication._files

    def concurrent(*args, **kwargs):
        files = original(*args, **kwargs)
        deliver(vertical, fact(vertical, "ORDER_CONFIRMED", 2))
        return files

    monkeypatch.setattr(publication, "_files", concurrent)
    assert vertical.publish_snapshot(vertical.test_namespace).generation == 1
    assert query(vertical, "daily_conversion")[0]["pending_orders"] == 1
    assert scalar(vertical, "SELECT count(*) FROM export_pending") == 1
    assert scalar(vertical, "SELECT count(*) FROM gold_dirty_keys") == 3
    monkeypatch.setattr(publication, "_files", original)
    assert vertical.publish_snapshot(vertical.test_namespace).generation == 2
    assert query(vertical, "daily_conversion")[0]["confirmed_orders"] == 1
    assert scalar(vertical, "SELECT count(*) FROM gold_dirty_keys") == 0


def test_single_row_capacity_keeps_active_generation_and_pending(vertical, monkeypatch):
    deliver(vertical, fact(vertical, "ORDER_CREATED"))
    vertical.publish_snapshot(vertical.test_namespace)
    deliver(vertical, fact(vertical, "ORDER_CONFIRMED", 2))
    monkeypatch.setattr(publication, "ROW_MAX_BYTES", 1)
    with pytest.raises(publication.SnapshotCapacityError, match="single projected row"):
        vertical.publish_snapshot(vertical.test_namespace)
    assert vertical.active_manifest(vertical.test_namespace, "gold").generation == 1
    assert query(vertical, "daily_conversion")[0]["pending_orders"] == 1
    assert scalar(vertical, "SELECT count(*) FROM export_pending") == 1
    assert scalar(vertical, "SELECT count(*) FROM gold_dirty_keys") == 3


def test_business_sql_failure_rolls_back_whole_sink_then_retries(vertical):
    with vertical.connect() as tx:
        tx.execute("""CREATE FUNCTION explicit_business_failure() RETURNS trigger LANGUAGE plpgsql
        AS $$ BEGIN RAISE EXCEPTION 'explicit business failure'; END $$""")
        tx.execute("""CREATE TRIGGER explicit_business_failure BEFORE INSERT ON order_fact
        FOR EACH ROW EXECUTE FUNCTION explicit_business_failure()""")
    value = fact(vertical, "ORDER_CREATED")
    source = record(vertical, value)
    with pytest.raises(psycopg.errors.RaiseException, match="explicit business failure"):
        curate(vertical, [source])
    assert scalar(vertical, "SELECT count(*) FROM silver_events") == 0
    assert scalar(vertical, "SELECT count(*) FROM reducer_contributions") == 0
    assert scalar(vertical, "SELECT count(*) FROM source_receipts") == 1
    assert scalar(vertical, "SELECT count(*) FROM source_receipts WHERE disposition IS NULL") == 1
    assert scalar(vertical, "SELECT count(*) FROM gold_dirty_keys") == 0
    assert scalar(vertical, "SELECT count(*) FROM export_pending") == 0
    with vertical.connect() as tx:
        tx.execute("DROP TRIGGER explicit_business_failure ON order_fact")
    assert curate(vertical, [source]).new_valid == 1
    vertical.publish_snapshot(vertical.test_namespace)
    assert query(vertical, "daily_conversion")[0]["created_orders"] == 1


def test_legacy_backfill_adds_business_once_without_recounting_pipeline(vertical, monkeypatch):
    actual = business.apply_business
    # Explicit old-reducer double: real accepted Silver/pipeline state, no M07 side effects.
    monkeypatch.setattr(business, "apply_business", lambda *args: set())
    deliver(vertical, fact(vertical, "ORDER_CREATED"), fact(vertical, "ORDER_CONFIRMED", 2))
    old_manifest = vertical.publish_snapshot(vertical.test_namespace)
    assert query(vertical, "order_fact") == []
    monkeypatch.setattr(business, "apply_business", actual)
    for _ in range(2):
        with vertical.connect() as tx, tx.transaction():
            business.backfill_business(tx)
    assert scalar(vertical, "SELECT count(*) FROM gold_business_contributions") == 2
    assert scalar(vertical, "SELECT sum(unique_events) FROM pipeline_minute") == 2
    assert scalar(vertical, "SELECT count(*) FROM export_pending") == 2
    assert (
        vertical.publish_snapshot(vertical.test_namespace).generation == old_manifest.generation + 1
    )
    assert query(vertical, "order_fact")[0]["order_status"] == "CONFIRMED"
    assert scalar(vertical, "SELECT count(*) FROM export_pending") == 0
    assert date.fromisoformat(query(vertical, "daily_conversion")[0]["cohort_date"][:10]) == date(
        2026, 10, 31
    )


def test_migration_004_backfills_existing_silver_and_is_idempotent(vertical, monkeypatch):
    actual = business.apply_business
    monkeypatch.setattr(business, "apply_business", lambda *args: set())
    deliver(vertical, fact(vertical, "ORDER_CREATED"), fact(vertical, "ORDER_CONFIRMED", 2))
    # This fixture owns its isolated schema; restore its exact pre-004 tables.
    with vertical.connect() as tx, tx.transaction():
        tx.execute("""DROP VIEW daily_conversion,checkout_funnel,payment_failures,
                   inventory_failures,search_performance""")
        tx.execute("""DROP TABLE gold_business_contributions,gold_partition_revisions,
                   gold_dirty_keys,order_fact,order_cohorts,payment_fact,funnel_stages,
                   pending_order_joins,inventory_failure_outcomes,search_fact""")
        tx.execute("DROP INDEX source_receipts_event")
        tx.execute("DROP VIEW event_time_windows,event_time_visibility")
        tx.execute("DROP TABLE event_time_observations,event_time_partitions,event_time_watermarks")
        tx.execute("DROP TABLE replay_keys,replay_inputs,replay_references,replay_jobs")
        tx.execute("DROP TABLE sink_batches")
        tx.execute("DELETE FROM analytics_schema_migrations WHERE version>=4")
    monkeypatch.setattr(business, "apply_business", actual)
    for _ in range(2):
        with vertical.connect() as tx, tx.transaction():
            migrate_analytics(tx)
    assert scalar(vertical, "SELECT count(*) FROM analytics_schema_migrations") == 9
    assert scalar(vertical, "SELECT count(*) FROM gold_business_contributions") == 2
    assert scalar(vertical, "SELECT sum(unique_events) FROM pipeline_minute") == 2
    vertical.publish_snapshot(vertical.test_namespace)
    assert query(vertical, "order_fact")[0]["order_status"] == "CONFIRMED"
