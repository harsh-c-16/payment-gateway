"""Real analytics SQL/files replay. Outbox and operational spies are explicit doubles."""

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from pipelines.curation import AnalyticsPipeline
from pipelines.curation.db import one
from pipelines.gold.business import backfill_business
from pipelines.ingestion import BronzeCapture
from pipelines.ingestion.api import create_app
from pipelines.replay.jobs import ReplayConflict, create_replay, get_status, run_replay
from pipelines.replay.worker import run_once
from pipelines.storage import publication
from pipelines.storage.parquet import iter_verified
from shared.contracts.analytics import ReplayStatus
from shared.event_transport.consumer import raw_fingerprint
from shared.event_transport.publisher import KafkaPublisher
from shared.local_diagnostics import OutboxUnavailable

from . import test_vertical_live as live
from .test_business_gold_live import deliver, fact
from .test_vertical_live import curate, event, record

vertical = live.vertical
outbox_double = live.outbox_double
pytestmark = live.pytestmark


def request(pipeline, sources, target=None):
    return {
        "source_manifest_ids": sources,
        "target_namespace": target or "replay-m10-" + uuid4().hex,
        "transform_version": pipeline.transform_version,
    }


def source_snapshot(pipeline):
    with pipeline.connect() as tx:
        return tx.execute(
            """SELECT dataset,generation,manifest FROM snapshot_manifests
            WHERE namespace=%s ORDER BY dataset,generation""",
            (pipeline.test_namespace,),
        ).fetchall()


def test_pinned_replay_preserves_business_values_original_bytes_and_can_replay_replay(
    vertical, monkeypatch
):
    def forbidden(*args, **kwargs):
        raise AssertionError("Replay attempted an operational/network publication")

    monkeypatch.setattr(KafkaPublisher, "publish_event", forbidden)
    deliver(
        vertical,
        fact(vertical, "PAYMENT_SUCCESS"),
        fact(vertical, "INVENTORY_COMMITTED"),
        fact(vertical, "ORDER_CREATED"),
        fact(vertical, "ORDER_CONFIRMED", 2),
        fact(vertical, "PRODUCT_RETRIEVED"),
    )
    manifest = vertical.publish_snapshot(vertical.test_namespace)
    before = source_snapshot(vertical)
    body = request(vertical, manifest.input_manifest_ids)
    accepted = create_replay(vertical, body)
    assert get_status(vertical, accepted.replay_id).status == "PENDING"
    result = run_once(vertical)
    assert result.replay_id == accepted.replay_id and result.status == "COMPLETED"
    assert result.reconciliation.passed
    target = vertical.active_manifest(body["target_namespace"], "silver")
    for file in target.files:
        for row in iter_verified(vertical.store, file):
            original = json.loads(row["envelope_json"])
            assert row["namespace"] == body["target_namespace"]
            assert original["namespace"] == vertical.test_namespace
    with vertical.connect() as tx:
        assert (
            tx.execute(
                """SELECT count(*) FROM silver_events a JOIN silver_events b USING(event_id)
            WHERE a.namespace=%s AND b.namespace=%s AND a.document=b.document
            AND a.content_hash=b.content_hash AND a.event_time=b.event_time
            AND a.raw_locator=b.raw_locator""",
                (vertical.test_namespace, body["target_namespace"]),
            ).fetchone()[0]
            == 5
        )
        assert tx.execute("SELECT count(*) FROM bronze_captures").fetchone()[0] == 1
        root = json.loads(vertical.store.read(target.input_manifest_ids[0]))
        assert root["replay"]["replay_id"] == accepted.replay_id
    assert run_replay(vertical, accepted.replay_id).status == "COMPLETED"
    assert vertical.active_manifest(body["target_namespace"], "gold").generation == 1
    again = vertical.replay_bronze(request(vertical, target.input_manifest_ids))
    assert again.status == "COMPLETED" and again.reconciliation.passed
    assert source_snapshot(vertical) == before
    Path("artifacts/m10/business-replay.json").write_text(
        json.dumps(
            {
                "source_commit": vertical.code_commit,
                "source_namespace": vertical.test_namespace,
                "target_namespace": body["target_namespace"],
                "replay_id": accepted.replay_id,
                "original_bytes_and_times": "PASS",
                "second_pass_generation": 1,
                "replay_of_replay": "PASS",
                "reconciliation": result.reconciliation.model_dump(mode="json"),
                "operational_services": "NOT_RUN; absent; explicit publication spy forbids calls",
            },
            indent=2,
        )
    )


def test_pinned_membership_filters_other_records_in_same_capture_and_new_generation(
    vertical, monkeypatch
):
    first, second = event(vertical), event(vertical, 2)
    receipt = BronzeCapture(vertical.store).ingest_bronze(
        [record(vertical, first), record(vertical, second, 1)]
    )
    original = vertical._insert_valid

    def stop_second(tx, checked, *args):
        if checked.envelope.event_id == second.event_id:
            raise OSError("fixture interrupted second sink")
        return original(tx, checked, *args)

    monkeypatch.setattr(vertical, "_insert_valid", stop_second)
    with pytest.raises(OSError):
        vertical.curate_silver(receipt, {"run_id": "explicit-m10-fixture"})
    pinned = vertical.publish_snapshot(vertical.test_namespace)
    body = request(vertical, pinned.input_manifest_ids)
    accepted = create_replay(vertical, body)
    monkeypatch.setattr(vertical, "_insert_valid", original)
    vertical.curate_silver(receipt, {"run_id": "explicit-m10-fixture"})
    vertical.publish_snapshot(vertical.test_namespace)
    assert run_replay(vertical, accepted.replay_id).reconciliation.passed
    with vertical.connect() as tx:
        assert tx.execute(
            "SELECT event_id::text FROM silver_events WHERE namespace=%s",
            (body["target_namespace"],),
        ).fetchall() == [(first.event_id,)]
        assert (
            tx.execute(
                "SELECT count(*) FROM source_receipts WHERE namespace=%s",
                (body["target_namespace"],),
            ).fetchone()[0]
            == 1
        )
    assert vertical.active_manifest(vertical.test_namespace, "gold").generation == 2


def test_capture_replay_keeps_invalid_bytes_and_duplicate_dispositions(vertical, outbox_double):
    original = event(vertical)
    good = record(vertical, original)
    invalid = replace(record(vertical, event(vertical, 2), 2), value_bytes=b"\xff-original")
    invalid = replace(
        invalid, raw_sha256=raw_fingerprint(invalid.key_bytes, invalid.value_bytes, invalid.headers)
    )
    receipt = BronzeCapture(vertical.store).ingest_bronze(
        [good, record(vertical, original, 1), invalid]
    )
    vertical.curate_silver(receipt, {"run_id": "explicit-m10-fixture"})
    body = request(vertical, [receipt.capture_id])
    accepted = create_replay(vertical, body)
    assert run_replay(vertical, accepted.replay_id).status == "COMPLETED"
    status = get_status(vertical, accepted.replay_id)
    assert status.reconciliation is None  # No independent pinned Gold reference was supplied.
    assert status.counts == {
        "new_valid": 1,
        "duplicate_delivery": 1,
        "invalid": 1,
        "redelivery_noop": 0,
        "source_records": 3,
    }
    assert run_replay(vertical, accepted.replay_id).status == "COMPLETED"
    assert get_status(vertical, accepted.replay_id).counts == status.counts
    with vertical.connect() as tx:
        assert tx.execute("SELECT count(*) FROM test_outbox_double").fetchone()[0] == 2
        notice = tx.execute(
            "SELECT payload FROM test_outbox_double WHERE payload->>'namespace'=%s",
            (body["target_namespace"],),
        ).fetchone()[0]
        assert notice["source_locator"]["topic"] == invalid.topic
        assert notice["namespace"] == body["target_namespace"]
        assert tx.execute("SELECT count(*) FROM bronze_captures").fetchone()[0] == 1
    assert vertical.active_manifest(body["target_namespace"], "gold").generation == 1


def test_missing_outbox_fails_without_dirty_infrastructure_classification_then_resumes(
    vertical, outbox_double, monkeypatch
):
    import sys

    source = record(vertical, event(vertical))
    source = replace(
        source,
        value_bytes=b"\xff",
        raw_sha256=raw_fingerprint(source.key_bytes, b"\xff", source.headers),
    )
    receipt = BronzeCapture(vertical.store).ingest_bronze([source])
    with monkeypatch.context() as missing:
        missing.delitem(sys.modules, "shared.outbox")
        with pytest.raises(OutboxUnavailable):
            vertical.curate_silver(receipt, {"run_id": "explicit-m10-fixture"})
        body = request(vertical, [receipt.capture_id])
        accepted = create_replay(vertical, body)
        assert run_replay(vertical, accepted.replay_id).status == "FAILED"
        assert get_status(vertical, accepted.replay_id).error["type"] == "OutboxUnavailable"
        with vertical.connect() as tx:
            assert tx.execute("SELECT count(*) FROM quarantine").fetchone()[0] == 0
            assert (
                tx.execute(
                    "SELECT disposition FROM source_receipts WHERE namespace=%s",
                    (body["target_namespace"],),
                ).fetchone()[0]
                is None
            )
    assert create_replay(vertical, body).replay_id == accepted.replay_id
    assert run_replay(vertical, accepted.replay_id).status == "COMPLETED"
    assert get_status(vertical, accepted.replay_id).counts["invalid"] == 1
    with pytest.raises(LookupError):
        vertical.active_manifest(body["target_namespace"], "gold")


@pytest.mark.parametrize("point", ["before_manifest_swap", "after_manifest_swap"])
def test_replay_failure_retains_source_and_resumes_owned_target(vertical, monkeypatch, point):
    curate(vertical, [record(vertical, event(vertical))])
    manifest = vertical.publish_snapshot(vertical.test_namespace)
    before = source_snapshot(vertical)
    body = request(vertical, manifest.input_manifest_ids)
    accepted = create_replay(vertical, body)

    def lost(where):
        if where == point:
            raise OSError("explicit replay publication failure")

    monkeypatch.setattr(publication, "boundary", lost)
    assert run_replay(vertical, accepted.replay_id).status == "FAILED"
    assert source_snapshot(vertical) == before
    if point == "before_manifest_swap":
        with pytest.raises(LookupError):
            vertical.active_manifest(body["target_namespace"], "gold")
    monkeypatch.setattr(publication, "boundary", lambda where: None)
    assert create_replay(vertical, body).replay_id == accepted.replay_id
    result = run_replay(vertical, accepted.replay_id)
    assert result.status == "COMPLETED" and result.reconciliation.passed
    assert vertical.active_manifest(body["target_namespace"], "gold").generation == 1


def test_changed_transform_reports_semantic_difference_without_source_promotion(
    vertical, monkeypatch
):
    import pipelines.curation as curation

    curate(vertical, [record(vertical, event(vertical))])
    manifest = vertical.publish_snapshot(vertical.test_namespace)
    before = source_snapshot(vertical)
    changed = AnalyticsPipeline(
        vertical.connect,
        vertical.store,
        vertical.codec,
        code_commit=vertical.code_commit,
        transform_version="explicit-m10-transform-test-double",
    )
    normalize = curation.normalize_payload
    monkeypatch.setattr(
        curation, "normalize_payload", lambda event: dict(normalize(event), duration_ms=2.5)
    )
    body = request(changed, manifest.input_manifest_ids)
    result = changed.replay_bronze(body)
    assert result.status == "FAILED" and not result.reconciliation.passed
    assert len(result.reconciliation.conflicting_ids) == 1
    assert source_snapshot(vertical) == before
    report = json.loads(vertical.store.read(f"replays/{result.replay_id}/semantic.json"))
    assert report["reference_transform"]["silver"] == vertical.transform_version
    assert report["target_transform"] == changed.transform_version


def test_http_job_contract_ownership_and_idempotency(vertical):
    source = record(vertical, event(vertical))
    curate(vertical, [source])
    manifest = vertical.publish_snapshot(vertical.test_namespace)
    body = request(vertical, manifest.input_manifest_ids)
    app = create_app(vertical, internal_token="explicit-test-token")

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://analytics",
        ) as client:
            endpoint = "/internal/v1/analytics/replays"
            assert (await client.post(endpoint, json=body)).status_code == 401
            headers = {
                "Authorization": "Bearer explicit-test-token",
                "X-Namespace": vertical.test_namespace,
                "X-Run-ID": "explicit-m10",
                "X-Correlation-ID": "explicit-m10",
                "Idempotency-Key": "stable-m10",
            }
            assert (
                await client.post(
                    endpoint, json=body, headers={"Authorization": headers["Authorization"]}
                )
            ).status_code == 422
            response = await client.post(endpoint, json=body, headers=headers)
            assert response.status_code == 202, response.text
            accepted = response.json()
            assert (await client.post(endpoint, json=body, headers=headers)).json() == accepted
            status = await client.get(accepted["status_url"], headers=headers)
            assert ReplayStatus.model_validate(status.json()).status == "PENDING"
            changed = dict(body, source_manifest_ids=[str(uuid4())])
            assert (await client.post(endpoint, json=changed, headers=headers)).status_code == 409
            other_target = dict(body, target_namespace="replay-other-" + uuid4().hex)
            assert (
                await client.post(endpoint, json=other_target, headers=headers)
            ).status_code == 409
            assert run_once(vertical).status == "COMPLETED"
            assert (await client.get(accepted["status_url"], headers=headers)).json()[
                "status"
            ] == "COMPLETED"
            assert (await client.get(endpoint + "/bad-id", headers=headers)).status_code == 422
            assert (
                await client.get(endpoint + "/" + str(uuid4()), headers=headers)
            ).status_code == 404

    asyncio.run(check())
    with pytest.raises(ReplayConflict, match="empty isolated"):
        create_replay(
            vertical, request(vertical, manifest.input_manifest_ids, vertical.test_namespace)
        )
    candidate = event(vertical, 2).model_copy(update={"namespace": body["target_namespace"]})
    source = replace(record(vertical, candidate, 1), source_namespace=body["target_namespace"])
    with pytest.raises(ReplayConflict, match="belongs"):
        curate(vertical, [source])


def test_backfill_respects_effective_namespace_after_replay(vertical):
    deliver(vertical, fact(vertical, "ORDER_CONFIRMED", 2))
    manifest = vertical.publish_snapshot(vertical.test_namespace)
    body = request(vertical, manifest.input_manifest_ids)
    assert vertical.replay_bronze(body).reconciliation.passed
    with vertical.connect() as tx, tx.transaction():
        before = one(tx, "SELECT * FROM order_fact WHERE namespace=%s", (vertical.test_namespace,))
        for table in (
            "gold_business_contributions",
            "order_fact",
            "order_cohorts",
            "funnel_stages",
        ):
            tx.execute("DELETE FROM " + table + " WHERE namespace=%s", (body["target_namespace"],))
        backfill_business(tx)
        restored = one(
            tx, "SELECT * FROM order_fact WHERE namespace=%s", (body["target_namespace"],)
        )
        assert restored["order_status"] == "CONFIRMED"
        assert (
            one(tx, "SELECT * FROM order_fact WHERE namespace=%s", (vertical.test_namespace,))
            == before
        )


@pytest.mark.parametrize("point", ["before_manifest_swap", "after_manifest_swap"])
def test_replay_resumes_after_acknowledged_real_process_exit(vertical, point):
    curate(vertical, [record(vertical, event(vertical))])
    source = vertical.publish_snapshot(vertical.test_namespace)
    before = source_snapshot(vertical)
    body = request(vertical, source.input_manifest_ids)
    accepted = create_replay(vertical, body)
    with vertical.connect() as tx:
        schema = tx.execute("SELECT current_schema()").fetchone()[0]
    child = subprocess.run(
        [
            sys.executable,
            "-m",
            "tests.pipelines.publication_crash",
            str(vertical.store.root),
            body["target_namespace"],
            schema,
            "replay",
            point,
            accepted.replay_id,
        ],
        capture_output=True,
        text=True,
        timeout=90,
        env=os.environ.copy(),
    )
    assert child.returncode == 73, child.stderr
    assert "M08_BOUNDARY_ACK:replay:" + point in child.stdout
    assert get_status(vertical, accepted.replay_id).status == "RUNNING"
    assert source_snapshot(vertical) == before
    result = run_once(vertical)
    assert result.status == "COMPLETED" and result.reconciliation.passed
    assert vertical.active_manifest(body["target_namespace"], "gold").generation == 1
    Path(f"artifacts/m10/crash-{point}.json").write_text(
        json.dumps(
            {
                "source_commit": vertical.code_commit,
                "point": point,
                "acknowledgement": child.stdout.strip(),
                "child_exit": 73,
                "persisted_status": "RUNNING",
                "recovery_status": result.status,
                "source_unchanged": True,
                "reconciliation": result.reconciliation.model_dump(mode="json"),
            },
            indent=2,
        )
    )


def test_historical_replay_preserves_future_rejection_and_opaque_headers(vertical, outbox_double):
    at = vertical.test_event_time - timedelta(days=10)
    good = record(vertical, event(vertical, event_time=at))
    headers = good.headers + (("m10-opaque", b"\x00\xff"), ("m10-opaque", None))
    good = replace(
        good,
        headers=headers,
        ingested_at=at + timedelta(seconds=1),
        raw_sha256=raw_fingerprint(good.key_bytes, good.value_bytes, headers),
    )
    future = replace(
        record(vertical, event(vertical, 2, event_time=at + timedelta(seconds=10)), 1),
        ingested_at=good.ingested_at,
    )
    receipt = BronzeCapture(vertical.store).ingest_bronze([good, future])
    vertical.curate_silver(receipt, {"run_id": "explicit-historical-fixture"})
    body = request(vertical, [receipt.capture_id])
    result = vertical.replay_bronze(body)
    assert result.status == "COMPLETED"
    with vertical.connect() as tx:
        assert (
            tx.execute(
                "SELECT reason_code FROM source_receipts WHERE namespace=%s AND offset_number=1",
                (body["target_namespace"],),
            ).fetchone()[0]
            == "FUTURE_TIMESTAMP"
        )
        assert (
            tx.execute(
                "SELECT evaluated_at FROM event_time_watermarks WHERE namespace=%s",
                (body["target_namespace"],),
            ).fetchone()[0]
            == good.ingested_at
        )
        assert (
            tx.execute(
                "SELECT event_time FROM silver_events WHERE namespace=%s",
                (body["target_namespace"],),
            ).fetchone()[0]
            == at
        )
    from pipelines.ingestion.bronze import read_bronze

    restored = read_bronze(vertical.store, receipt)[0]
    assert restored.headers == headers and restored.value_bytes == good.value_bytes


def test_repairs_are_validated_only_in_isolation_with_durable_quarantine_reference(
    vertical, outbox_double
):
    original = event(vertical)
    source = record(vertical, original)
    bad = replace(
        source,
        value_bytes=b"\xff",
        raw_sha256=raw_fingerprint(source.key_bytes, b"\xff", source.headers),
    )
    curate(vertical, [bad])
    with vertical.connect() as tx:
        locator = tx.execute("SELECT raw_locator FROM quarantine").fetchone()[0]
    repaired = event(vertical, 2)
    document = repaired.model_dump(mode="json")
    document["metadata"].update(
        original_event_id=original.event_id,
        source_locator=locator,
        repair_reason="explicit-synthetic-byte-repair",
    )
    repaired = repaired.model_validate(document)
    receipt = BronzeCapture(vertical.store).ingest_bronze([record(vertical, repaired, 1)])
    # Register raw repair input; only the isolated replay performs its sink evaluation.
    from pipelines.ingestion.receipts import persist_capture

    with vertical.connect() as tx, tx.transaction():
        persist_capture(tx, receipt, vertical.store)
    body = request(vertical, [receipt.capture_id])
    assert vertical.replay_bronze(body).status == "COMPLETED"
    with vertical.connect() as tx:
        assert (
            tx.execute(
                "SELECT count(*) FROM silver_events WHERE namespace=%s", (vertical.test_namespace,)
            ).fetchone()[0]
            == 0
        )
        assert (
            tx.execute(
                "SELECT event_id::text FROM silver_events WHERE namespace=%s",
                (body["target_namespace"],),
            ).fetchone()[0]
            == repaired.event_id
        )
        assert (
            tx.execute(
                "SELECT repair_status FROM quarantine WHERE raw_locator=%s", (locator,)
            ).fetchone()[0]
            == "unrepaired"
        )


def test_large_money_is_exact_but_frozen_reconciliation_dto_fails_closed(vertical):
    maximum = 2**63 - 1
    deliver(
        vertical,
        fact(vertical, "ORDER_CONFIRMED", total_amount_minor=maximum),
        fact(vertical, "ORDER_CONFIRMED", order_id=str(uuid4()), total_amount_minor=maximum),
    )
    manifest = vertical.publish_snapshot(vertical.test_namespace)
    before = source_snapshot(vertical)
    result = vertical.replay_bronze(request(vertical, manifest.input_manifest_ids))
    assert result.status == "FAILED" and not result.reconciliation.passed
    assert any("int64" in failure for failure in result.reconciliation.invariant_failures)
    report = json.loads(vertical.store.read(f"replays/{result.replay_id}/semantic.json"))
    assert report["datasets"]["gold"]["target"]["money"]["INR"] > maximum
    assert source_snapshot(vertical) == before


def test_resume_rejects_changed_code_provenance_without_touching_job(vertical):
    curate(vertical, [record(vertical, event(vertical))])
    manifest = vertical.publish_snapshot(vertical.test_namespace)
    body = request(vertical, manifest.input_manifest_ids)
    accepted = create_replay(vertical, body)
    changed = AnalyticsPipeline(
        vertical.connect,
        vertical.store,
        vertical.codec,
        code_commit="explicit-other-code-test-double",
        transform_version=vertical.transform_version,
    )
    with pytest.raises(ReplayConflict, match="original code"):
        run_replay(changed, accepted.replay_id)
    with pytest.raises(ReplayConflict, match="original code"):
        create_replay(changed, body)
    assert get_status(vertical, accepted.replay_id).status == "PENDING"
    assert run_replay(vertical, accepted.replay_id).reconciliation.passed


def test_target_with_leftover_cohort_state_is_not_empty(vertical):
    curate(vertical, [record(vertical, event(vertical))])
    manifest = vertical.publish_snapshot(vertical.test_namespace)
    body = request(vertical, manifest.input_manifest_ids)
    with vertical.connect() as tx:
        tx.execute(
            "INSERT INTO order_cohorts VALUES (%s,current_date,'INR')", (body["target_namespace"],)
        )
    with pytest.raises(ReplayConflict, match="empty isolated"):
        create_replay(vertical, body)
