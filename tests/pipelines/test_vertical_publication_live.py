"""Real PostgreSQL snapshot concurrency, active-only reads and HTTP contract checks."""

import asyncio
import os
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest

import pipelines.storage.publication as publication
import pipelines.storage.readers as readers
from pipelines.ingestion.api import create_app
from pipelines.storage.parquet import FileVerificationError, read_verified
from pipelines.storage.publication import PublicationConflict, SnapshotCapacityError
from shared.contracts.analytics import GoldQueryResult, ReceiptPage
from shared.contracts.common import ErrorResponse

from . import test_vertical_live as live
from .test_vertical_live import count, curate, event, query, record

vertical = live.vertical

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_VERTICAL_LIVE_TESTS") != "1",
    reason="RUN_VERTICAL_LIVE_TESTS=1 requires Linux volume and real analytics PostgreSQL",
)


def test_concurrent_arrival_survives_frozen_membership_and_stale_cas(vertical, monkeypatch):
    first = event(vertical)
    curate(vertical, [record(vertical, first)])
    vertical.publish_snapshot(vertical.test_namespace)
    second = event(vertical, 2)
    curate(vertical, [record(vertical, second, 1)])
    third = event(vertical, 3)
    original = publication._files

    def concurrent(*args, **kwargs):
        files = original(*args, **kwargs)
        curate(vertical, [record(vertical, third, 2)])
        return files

    monkeypatch.setattr(publication, "_files", concurrent)
    assert vertical.publish_snapshot(vertical.test_namespace).generation == 2
    assert query(vertical).rows[0]["unique_events"] == 2
    assert count(vertical, "export_pending") == 1
    with vertical.connect() as tx:
        frozen = set(publication.iter_membership(tx, vertical.test_namespace, "gold", 2))
        assert frozen == {first.event_id, second.event_id}
        with pytest.raises(PublicationConflict, match="STALE_MANIFEST"):
            publication._commit(vertical, tx, vertical.test_namespace, {}, {})
    assert vertical.active_manifest(vertical.test_namespace, "gold").generation == 2
    monkeypatch.setattr(publication, "_files", original)
    assert vertical.publish_snapshot(vertical.test_namespace).generation == 3
    assert query(vertical).rows[0]["unique_events"] == 3 and count(vertical, "export_pending") == 0


def test_single_publisher_and_bounded_snapshot(vertical, monkeypatch):
    curate(vertical, [record(vertical, event(vertical))])
    key = publication.lock_key(vertical.test_namespace, "publisher")
    with vertical.connect() as tx:
        tx.execute("SELECT pg_advisory_lock(%s)", (key,))
        try:
            with pytest.raises(PublicationConflict, match="publisher"):
                vertical.publish_snapshot(vertical.test_namespace)
        finally:
            tx.execute("SELECT pg_advisory_unlock(%s)", (key,))
    monkeypatch.setattr(publication, "ROW_MAX_BYTES", 1)
    with pytest.raises(SnapshotCapacityError):
        vertical.publish_snapshot(vertical.test_namespace)
    assert count(vertical, "export_pending") == 1
    with pytest.raises(LookupError):
        vertical.active_manifest(vertical.test_namespace, "gold")


def test_reader_pins_generation_reuses_untouched_files_and_checks_corruption(vertical, monkeypatch):
    old = event(vertical, event_time=vertical.test_event_time - timedelta(days=1))
    curate(vertical, [record(vertical, old)])
    first_manifest = vertical.publish_snapshot(vertical.test_namespace)
    old_paths = {file.path for file in first_manifest.files}
    curate(vertical, [record(vertical, event(vertical, 2), 1)])
    original = readers.iter_verified
    switched = False

    def switch(store, descriptor):
        nonlocal switched
        if not switched:
            switched = True
            vertical.publish_snapshot(vertical.test_namespace)
        return original(store, descriptor)

    monkeypatch.setattr(readers, "iter_verified", switch)
    pinned = query(vertical)
    assert pinned.generation == 1 and sum(row["unique_events"] for row in pinned.rows) == 1
    new = vertical.active_manifest(vertical.test_namespace, "gold")
    assert new.generation == 2 and old_paths <= {file.path for file in new.files}
    assert sum(row["unique_events"] for row in query(vertical).rows) == 2
    descriptor = new.files[-1]
    (vertical.store.root / descriptor.path).write_bytes(b"explicit-corruption-fault")
    with pytest.raises(FileVerificationError):
        read_verified(vertical.store, descriptor)


def test_http_actual_manifest_gold_receipts_auth_and_readiness(vertical):
    app = create_app(vertical, internal_token="explicit-synthetic-service-token")

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://analytics",
        ) as client:
            namespace = vertical.test_namespace
            assert (await client.get("/health/live")).status_code == 200
            assert (await client.get("/health/ready")).status_code == 503
            path = "/v1/analytics/manifests/gold/active"
            assert (await client.get(path, params={"namespace": namespace})).status_code == 404
            endpoint = "/internal/v1/analytics/receipts"
            denied = await client.get(endpoint, params={"namespace": namespace})
            assert denied.status_code == 401
            ErrorResponse.model_validate(denied.json())
            curate(vertical, [record(vertical, event(vertical))])
            vertical.publish_snapshot(namespace)
            manifest = await client.get(path, params={"namespace": namespace})
            assert manifest.status_code == 200 and manifest.json()["generation"] == 1
            today = vertical.test_event_time.date()
            response = await client.get(
                "/v1/analytics/gold/pipeline_minute",
                params={
                    "namespace": namespace,
                    "date_from": str(today),
                    "date_to": str(today + timedelta(days=1)),
                },
            )
            result = GoldQueryResult.model_validate(response.json())
            assert result.generation == 1 and result.rows[0]["unique_events"] == 1
            headers = {"Authorization": "Bearer explicit-synthetic-service-token"}
            response = await client.get(
                endpoint, params={"namespace": namespace, "limit": 1}, headers=headers
            )
            page = ReceiptPage.model_validate(response.json())
            assert page.next_cursor and len(page.receipts) == 1
            assert (
                await client.get(
                    endpoint, params={"namespace": namespace, "limit": 1001}, headers=headers
                )
            ).status_code == 422
            assert (
                await client.get(endpoint, params={"namespace": "bench-other"}, headers=headers)
            ).json()["receipts"] == []
            assert (await client.get("/metrics")).status_code == 200

    asyncio.run(check())


def test_tool_event_is_now_supported_without_dirty_classification(vertical):
    other = vertical.codec.build_event(
        "TOOL_CALLED",
        {
            "turn_id": str(uuid4()),
            "tool_call_id": str(uuid4()),
            "tool_name": "search",
            "outcome": "success",
            "duration_ms": 1.0,
        },
        {
            "namespace": vertical.test_namespace,
            "run_id": "m05-explicit-synthetic-fixture",
            "user_id": "synthetic-user",
            "session_id": vertical.test_session,
            "correlation_id": str(uuid4()),
        },
        "session",
        vertical.test_session,
        1,
        vertical.test_event_time,
    )
    assert curate(vertical, [record(vertical, other)]).new_valid == 1
    assert count(vertical, "quarantine") == 0 and count(vertical, "silver_events") == 1
    vertical.publish_snapshot(vertical.test_namespace)
    assert query(vertical).rows[0]["event_type"] == "TOOL_CALLED"
    assert query(vertical).rows[0]["unique_events"] == 1


def test_pointer_transaction_failure_rolls_back_both_datasets(vertical):
    curate(vertical, [record(vertical, event(vertical))])
    vertical.publish_snapshot(vertical.test_namespace)
    curate(vertical, [record(vertical, event(vertical, 2), 1)])
    with vertical.connect() as tx:
        tx.execute("""CREATE FUNCTION m05_fail_gold() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.dataset='gold' THEN RAISE EXCEPTION 'explicit pointer failure';
            END IF; RETURN NEW; END $$""")
        tx.execute("""CREATE TRIGGER m05_pointer_fault BEFORE INSERT OR UPDATE ON active_datasets
                      FOR EACH ROW EXECUTE FUNCTION m05_fail_gold()""")
    import psycopg

    with pytest.raises(psycopg.Error):
        vertical.publish_snapshot(vertical.test_namespace)
    assert vertical.active_manifest(vertical.test_namespace, "silver").generation == 1
    assert vertical.active_manifest(vertical.test_namespace, "gold").generation == 1
    assert count(vertical, "export_pending") == 1
    with vertical.connect() as tx:
        tx.execute("DROP TRIGGER m05_pointer_fault ON active_datasets")
    assert vertical.publish_snapshot(vertical.test_namespace).generation == 2
