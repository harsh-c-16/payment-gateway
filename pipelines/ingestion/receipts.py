"""Caller-owned analytics transactions; capture is separate from sink disposition."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb

from shared.contracts.analytics import RawBatchReceipt

from .bronze import SourceCorruption, read_bronze

MIGRATION = Path(__file__).resolve().parents[2] / "migrations/analytics/001_capture.sql"
SLICE_MIGRATION = MIGRATION.with_name("002_vertical_slice.sql")
SILVER_MIGRATION = MIGRATION.with_name("003_full_silver.sql")
GOLD_MIGRATION = MIGRATION.with_name("004_business_gold.sql")
PUBLICATION_MIGRATION = MIGRATION.with_name("005_visibility_lookup.sql")
EVENT_TIME_MIGRATION = MIGRATION.with_name("006_event_time.sql")
REPLAY_MIGRATION = MIGRATION.with_name("007_replay.sql")
REPLAY_KEYS_MIGRATION = MIGRATION.with_name("008_replay_request_namespace.sql")
SINK_OBSERVATIONS_MIGRATION = MIGRATION.with_name("009_sink_observations.sql")
OUTBOX_MIGRATION = MIGRATION.with_name("010_shared_outbox.sql")


def _transaction(tx):
    if tx.info.transaction_status != TransactionStatus.INTRANS:
        raise ValueError("An active caller-owned analytics transaction is required")


def migrate_analytics(tx):
    """Apply only this owner's immutable migration; caller commits or rolls back."""
    _transaction(tx)
    with tx.transaction():
        tx.execute("SELECT pg_advisory_xact_lock(744031001)")
        tx.execute("""CREATE TABLE IF NOT EXISTS analytics_schema_migrations (
            version integer PRIMARY KEY, sha256 char(64) NOT NULL,
            applied_at timestamptz NOT NULL DEFAULT clock_timestamp())""")
        for version, path in (
            (1, MIGRATION),
            (2, SLICE_MIGRATION),
            (3, SILVER_MIGRATION),
            (4, GOLD_MIGRATION),
            (5, PUBLICATION_MIGRATION),
            (6, EVENT_TIME_MIGRATION),
            (7, REPLAY_MIGRATION),
            (8, REPLAY_KEYS_MIGRATION),
            (9, SINK_OBSERVATIONS_MIGRATION),
            (10, OUTBOX_MIGRATION),
        ):
            # Git checkouts may use CRLF; checksums agree across host OSes.
            data = path.read_text(encoding="utf-8").encode("utf-8")
            digest = hashlib.sha256(data).hexdigest()
            previous = tx.execute(
                "SELECT sha256 FROM analytics_schema_migrations WHERE version=%s", (version,)
            ).fetchone()
            if previous:
                if previous[0] != digest:
                    raise SourceCorruption("Applied analytics migration checksum changed")
                continue
            tx.execute(data.decode("utf-8"))
            if version == 4:
                from pipelines.gold.business import backfill_business

                backfill_business(tx)
            tx.execute(
                "INSERT INTO analytics_schema_migrations(version,sha256) VALUES (%s,%s)",
                (version, digest),
            )


@dataclass(frozen=True)
class CapturePersistence:
    new_sources: int
    redelivery_noop: int


def persist_capture(
    tx, receipt, store, *, effective_namespace=None, locators=None, replay_ingress=None
):
    """Verify bytes before SQL, preserve first locators, never mark worker durability."""
    _transaction(tx)
    receipt = RawBatchReceipt.model_validate(receipt)
    read_bronze(store, receipt)
    if not receipt.records:
        raise ValueError("Cannot persist an empty capture")
    origin_namespace = receipt.records[0].namespace
    if any(row.namespace != origin_namespace for row in receipt.records):
        raise ValueError("Capture spans namespaces")
    namespace = origin_namespace
    if effective_namespace is not None:
        from pydantic import TypeAdapter

        from shared.contracts.events import IsolatedNamespace

        namespace = TypeAdapter(IsolatedNamespace).validate_python(effective_namespace)
    selected = receipt.records
    if locators is not None:
        selected = [r for r in selected if r.source.raw_locator in locators]
        if {r.source.raw_locator for r in selected} != set(locators):
            raise SourceCorruption("Replay selection is outside the original capture")
    if replay_ingress is not None and (
        effective_namespace is None
        or set(replay_ingress) != {r.source.raw_locator for r in selected}
    ):
        raise SourceCorruption("Replay ingress must cover exactly the selected source records")
    document = receipt.model_dump(mode="json")
    fresh, redelivery = 0, 0
    with tx.transaction():
        tx.execute(
            """INSERT INTO bronze_captures(capture_id,namespace,captured_at,receipt)
               VALUES (%s,%s,%s,%s) ON CONFLICT (capture_id) DO NOTHING""",
            (receipt.capture_id, origin_namespace, receipt.captured_at, Jsonb(document)),
        )
        previous = tx.execute(
            "SELECT receipt FROM bronze_captures WHERE capture_id=%s", (receipt.capture_id,)
        ).fetchone()[0]
        if previous != document:
            raise SourceCorruption("Capture identity was reused with changed content")
        # A stable lock order avoids reversed-partition source retry deadlocks.
        for row in sorted(
            selected, key=lambda r: (r.source.topic, r.source.partition, r.source.offset)
        ):
            source = row.source
            inserted = tx.execute(
                """INSERT INTO source_receipts
                    (namespace,topic,partition,offset_number,capture_id,raw_locator,
                     raw_sha256,ingested_at,bronze_durable_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (namespace,topic,partition,offset_number) DO NOTHING
                   RETURNING raw_sha256""",
                (
                    namespace,
                    source.topic,
                    source.partition,
                    source.offset,
                    receipt.capture_id,
                    source.raw_locator,
                    row.raw_sha256,
                    row.ingested_at
                    if replay_ingress is None
                    else replay_ingress[source.raw_locator],
                    row.bronze_durable_at,
                ),
            ).fetchone()
            if inserted:
                fresh += 1
            else:
                existing = tx.execute(
                    """SELECT raw_sha256 FROM source_receipts
                       WHERE namespace=%s AND topic=%s AND partition=%s AND offset_number=%s""",
                    (namespace, source.topic, source.partition, source.offset),
                ).fetchone()[0]
                if existing != row.raw_sha256:
                    raise SourceCorruption("Existing source coordinate has different raw bytes")
                redelivery += 1
    return CapturePersistence(fresh, redelivery)


def load_capture(tx, capture_id):
    _transaction(tx)
    row = tx.execute(
        "SELECT receipt FROM bronze_captures WHERE capture_id=%s", (capture_id,)
    ).fetchone()
    return None if row is None else RawBatchReceipt.model_validate(row[0])
