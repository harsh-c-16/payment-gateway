"""First-source timing and existing-client regressions; real analytics SQL/files."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import httpx
import pytest
from psycopg.types.json import Jsonb

from pipelines.ingestion import BronzeCapture, SourceCorruption
from pipelines.ingestion.api import create_app
from pipelines.replay.jobs import ReplayConflict, create_replay, get_status
from services.conversation.clients import AnalyticsClient, ProviderHTTP, TransportConfig
from services.conversation.provider_contracts import ENDPOINTS, OpenAPIContracts
from shared.contracts.common import RequestContext

from . import test_vertical_live as live
from .test_vertical_live import curate, event, record

vertical = live.vertical
outbox_double = live.outbox_double
pytestmark = live.pytestmark


@pytest.mark.parametrize("selection", ["later_only", "both"])
def test_recaptured_future_invalid_keeps_first_durable_ingress(vertical, outbox_double, selection):
    at = vertical.test_event_time - timedelta(days=10)
    source = replace(
        record(vertical, event(vertical, event_time=at + timedelta(seconds=10))),
        ingested_at=at + timedelta(seconds=1),
    )
    original = BronzeCapture(vertical.store).ingest_bronze([source])
    assert vertical.curate_silver(original, {"run_id": "first-ingress-fixture"}).invalid == 1
    later = BronzeCapture(vertical.store).ingest_bronze(
        [replace(source, ingested_at=at + timedelta(seconds=30))]
    )
    assert vertical.curate_silver(later, {"run_id": "first-ingress-fixture"}).redelivery_noop == 1
    refs = (
        [later.capture_id] if selection == "later_only" else [original.capture_id, later.capture_id]
    )
    target = "replay-first-ingress-" + uuid4().hex
    result = vertical.replay_bronze(
        {
            "source_manifest_ids": refs,
            "target_namespace": target,
            "transform_version": vertical.transform_version,
        }
    )
    status = get_status(vertical, result.replay_id)
    assert result.status == "COMPLETED"
    assert status.counts["invalid"] == 1 and status.counts["new_valid"] == 0
    with vertical.connect() as tx:
        first = tx.execute(
            "SELECT ingested_at,reason_code FROM source_receipts WHERE namespace=%s", (target,)
        ).fetchone()
        assert first == (source.ingested_at, "FUTURE_TIMESTAMP")
        assert (
            tx.execute(
                "SELECT clock_at FROM replay_jobs WHERE replay_id=%s", (result.replay_id,)
            ).fetchone()[0]
            == source.ingested_at
        )
    Path(f"artifacts/m10/first-ingress-after-{selection}.json").write_text(
        json.dumps(
            {
                "source_commit": vertical.code_commit,
                "selection": selection,
                "counts": status.counts,
                "first_ingress": source.ingested_at.isoformat(),
                "recapture_ingress": later.records[0].ingested_at.isoformat(),
                "invalid_remains_invalid": True,
            },
            indent=2,
        )
    )


def test_capture_without_canonical_source_is_not_silently_dropped(vertical):
    receipt = BronzeCapture(vertical.store).ingest_bronze([record(vertical, event(vertical))])
    # Explicit corruption fixture: a registered receipt without its durable source ledger.
    with vertical.connect() as tx:
        tx.execute(
            "INSERT INTO bronze_captures VALUES (%s,%s,%s,%s)",
            (
                receipt.capture_id,
                vertical.test_namespace,
                receipt.captured_at,
                Jsonb(receipt.model_dump(mode="json")),
            ),
        )
    with pytest.raises(SourceCorruption, match="durable source"):
        create_replay(
            vertical,
            {
                "source_manifest_ids": [receipt.capture_id],
                "target_namespace": "replay-corrupt-" + uuid4().hex,
                "transform_version": vertical.transform_version,
            },
        )
    with vertical.connect() as tx:
        assert tx.execute("SELECT count(*) FROM replay_jobs").fetchone()[0] == 0


def test_existing_analytics_client_uses_source_namespace_and_separate_target(vertical):
    curate(vertical, [record(vertical, event(vertical))])
    manifest = vertical.publish_snapshot(vertical.test_namespace)
    body = {
        "source_manifest_ids": manifest.input_manifest_ids,
        "target_namespace": "replay-client-" + uuid4().hex,
        "transform_version": vertical.transform_version,
    }
    context = RequestContext(
        namespace=vertical.test_namespace,
        run_id="m10-client-fixture",
        user_id="synthetic-user",
        correlation_id="m10-client-fixture",
        request_id=str(uuid4()),
        session_id=None,
    )
    with pytest.raises(ValueError, match="selected replay source"):
        create_replay(vertical, body, source_namespace="bench-wrong-source")

    class InProcessSchemas(OpenAPIContracts):
        mode = (
            "stub"  # Explicit in-process HTTP transport; schemas are the actual analytics contract.
        )

    schemas = InProcessSchemas(Path("contracts/http"))
    schemas.validate(ENDPOINTS["replay_create"], "request", body)
    schemas.validate(
        ENDPOINTS["replay_create"],
        "response",
        {"replay_id": str(uuid4()), "status_url": "/internal/v1/analytics/replays/fixture"},
    )
    app = create_app(vertical, internal_token="explicit-client-token")

    async def run():
        config = TransportConfig("http://analytics", mode="stub", purpose="contract_test")
        async with ProviderHTTP(
            config,
            schemas,
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            internal_token="explicit-client-token",
        ) as http:
            client = AnalyticsClient(http)
            accepted = await client.replay(body, context, key="m10-existing-client")
            assert (await client.replay_status(accepted["replay_id"], context))[
                "status"
            ] == "PENDING"
            return accepted

    assert asyncio.run(run())["replay_id"]


def test_one_source_idempotency_key_cannot_create_two_targets_concurrently(vertical):
    curate(vertical, [record(vertical, event(vertical))])
    manifest = vertical.publish_snapshot(vertical.test_namespace)
    gate = Barrier(2)

    def start(index):
        body = {
            "source_manifest_ids": manifest.input_manifest_ids,
            "target_namespace": "replay-key-" + uuid4().hex,
            "transform_version": vertical.transform_version,
        }
        gate.wait(timeout=30)
        try:
            create_replay(
                vertical,
                body,
                idempotency_key="shared-key",
                source_namespace=vertical.test_namespace,
            )
            return "accepted"
        except ReplayConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(start, range(2), timeout=60))
    assert sorted(outcomes) == ["accepted", "conflict"]
    with vertical.connect() as tx:
        assert tx.execute("SELECT count(*) FROM replay_jobs").fetchone()[0] == 1
