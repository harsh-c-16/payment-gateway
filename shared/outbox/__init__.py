"""Shared transactional outbox: append in the caller's transaction, relay later.

Owner: Aditya Gaurav. Each service owns its outbox table and migrations.
All services use the same library. append_outbox never commits the caller's
transaction and never calls Kafka.
"""

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row

from shared.contracts.events import DlqNotice, EventEnvelope, PublishAck, RegisteredRecord

logger = logging.getLogger(__name__)


class OutboxError(RuntimeError):
    pass


def outbox_table_ddl():
    return Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")


def _canonical_json(obj) -> bytes:
    """Deterministic JSON bytes for outbox storage."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _serialise(event: RegisteredRecord) -> tuple[bytes, list[tuple[str, bytes]], str, str, str, str]:
    """Serialise an event into outbox storage fields."""
    if not isinstance(event, (EventEnvelope, DlqNotice)):
        raise TypeError("expected EventEnvelope or DlqNotice")
    document = event.model_dump(mode="json", exclude_unset=True)
    raw = _canonical_json(document)
    topic = event.topic()
    key = event.kafka_key()
    if isinstance(event, EventEnvelope):
        agg_type = event.aggregate_type
        agg_id = event.aggregate_id
    elif isinstance(event, DlqNotice):
        agg_type = "diagnostic"
        agg_id = event.diagnostic_id
    else:
        raise TypeError("expected EventEnvelope or DlqNotice")
    headers = [
        ("content-type", b"application/json"),
    ]
    return raw, headers, topic, key, agg_type, agg_id


def append_outbox(db_transaction, event: RegisteredRecord) -> int:
    """Append an event to the caller's local outbox table within their open transaction.

    Returns the outbox_id. Never commits the caller's transaction; never calls Kafka.
    """
    if not isinstance(event, (EventEnvelope, DlqNotice)):
        raise TypeError("event must be an EventEnvelope or DlqNotice")

    tx_status = db_transaction.info.transaction_status
    if tx_status != TransactionStatus.INTRANS:
        raise OutboxError(
            f"append_outbox requires an active transaction (got {tx_status!r})"
        )

    raw, headers, topic, key, agg_type, agg_id = _serialise(event)
    event_id = event.event_id
    namespace = event.namespace
    produced_at = event.produced_at

    headers_json = json.dumps(
        [{"name": h[0], "value": h[1].decode("utf-8", errors="replace")} for h in headers],
        ensure_ascii=False,
    )

    row = db_transaction.execute(
        """
        INSERT INTO outbox
            (event_id, namespace, aggregate_type, aggregate_id,
             topic, partition_key, payload, headers, produced_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
        ON CONFLICT (event_id) DO NOTHING
        RETURNING outbox_id
        """,
        (
            event_id, namespace, agg_type, agg_id,
            topic, key, raw, headers_json, produced_at,
        ),
    ).fetchone()

    if row is None:
        existing = db_transaction.execute(
            "SELECT outbox_id FROM outbox WHERE event_id = %s",
            (event_id,),
        ).fetchone()
        if existing is None:
            raise OutboxError("event_id conflict but row not found")
        return existing[0] if not isinstance(existing, dict) else existing["outbox_id"]

    return row[0] if not isinstance(row, dict) else row["outbox_id"]


@dataclass
class RelayResult:
    scanned: int = 0
    broker_acked: int = 0
    marked_published: int = 0
    uncertain: int = 0
    retryable_failed: int = 0
    oldest_pending_age_ms: float | None = None


def relay_once(db_connection, publisher, *, limit=100, claim_id=None) -> RelayResult:
    """Read pending outbox rows, publish to Kafka, mark published after ack.

    Uses the caller's db_connection (not a transaction parameter) because we
    commit each row's published_at independently after broker confirmation.
    The advisory lock ensures one active relay per database.
    """
    from shared.event_transport import RetryablePublishError

    claim = claim_id or str(uuid4())
    result = RelayResult()

    with db_connection.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT outbox_id, event_id, namespace, aggregate_type, aggregate_id,
                   topic, partition_key, payload, headers, produced_at, created_at
            FROM outbox
            WHERE published_at IS NULL
            ORDER BY namespace, aggregate_type, aggregate_id, outbox_id
            LIMIT %s
            FOR UPDATE SKIP LOCKED
            """,
            (limit,),
        )
        rows = cur.fetchall()

    result.scanned = len(rows)
    if not rows:
        return result

    now = datetime.now(UTC)
    oldest = min(r["created_at"] for r in rows)
    result.oldest_pending_age_ms = (now - oldest).total_seconds() * 1000

    blocked_aggregates = set()
    for row in rows:
        aggregate = (row["namespace"], row["aggregate_type"], row["aggregate_id"])
        if aggregate in blocked_aggregates:
            continue
        event_id = str(row["event_id"])
        topic = row["topic"]
        key = row["partition_key"].encode("utf-8") if isinstance(row["partition_key"], str) else row["partition_key"]
        raw = bytes(row["payload"]) if not isinstance(row["payload"], bytes) else row["payload"]

        try:
            document = json.loads(raw)
            if "diagnostic_id" in document:
                event = DlqNotice.model_validate(document)
            else:
                event = EventEnvelope.model_validate(document)
        except Exception:
            logger.exception("outbox relay: cannot deserialize row %s", event_id)
            result.retryable_failed += 1
            blocked_aggregates.add(aggregate)
            continue

        try:
            ack: PublishAck = publisher.publish_event(event, topic, key)
            result.broker_acked += 1
        except RetryablePublishError as exc:
            blocked_aggregates.add(aggregate)
            if exc.uncertain:
                result.uncertain += 1
            else:
                result.retryable_failed += 1
            logger.warning("outbox relay failed for %s: %s", event_id, exc)
            continue

        with db_connection.cursor() as cur:
            cur.execute(
                """
                UPDATE outbox
                SET published_at = %s, relay_claim = %s, relay_claimed_at = %s
                WHERE event_id = %s AND published_at IS NULL
                """,
                (datetime.now(UTC), claim, datetime.now(UTC), event_id),
            )
        db_connection.commit()
        result.marked_published += 1

    return result


@dataclass
class RecoverySummary:
    service: str
    reclaimed_claims: int = 0
    remaining_pending: int = 0
    oldest_pending_at: datetime | None = None


def recover_pending_outbox(db_connection, *, service_name="unknown", stale_seconds=60) -> RecoverySummary:
    """Reclaim abandoned relay claims. No new event IDs or timestamps."""
    cutoff = datetime.now(UTC).timestamp() - stale_seconds

    with db_connection.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            UPDATE outbox
            SET relay_claim = NULL, relay_claimed_at = NULL
            WHERE published_at IS NULL
              AND relay_claim IS NOT NULL
              AND relay_claimed_at < to_timestamp(%s)
            """,
            (cutoff,),
        )
        reclaimed = cur.rowcount

        cur.execute(
            """
            SELECT count(*) AS cnt,
                   min(created_at) AS oldest
            FROM outbox
            WHERE published_at IS NULL
            """,
        )
        stats = cur.fetchone()

    db_connection.commit()

    return RecoverySummary(
        service=service_name,
        reclaimed_claims=reclaimed,
        remaining_pending=stats["cnt"],
        oldest_pending_at=stats["oldest"],
    )


class OutboxRelay:
    """Background relay worker with advisory-lock exclusion.

    One active relay per service database. A second instance waits as standby.
    """

    def __init__(
        self,
        db_pool,
        publisher,
        *,
        service_name="unknown",
        poll_interval_ms=25,
        batch_limit=100,
    ):
        self.db_pool = db_pool
        self.publisher = publisher
        self.service_name = service_name
        self.poll_interval = poll_interval_ms / 1000.0
        self.batch_limit = batch_limit
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        if self._thread is not None:
            raise RuntimeError("relay already started")
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name=f"outbox-relay-{self.service_name}", daemon=True
        )
        self._thread.start()

    def stop(self, timeout=10):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    def _run(self):
        lock_id = int(hashlib.sha256(
            f"outbox-relay-{self.service_name}".encode()
        ).hexdigest()[:15], 16)

        while not self._stop.is_set():
            try:
                conn = self.db_pool.getconn()
                try:
                    conn.autocommit = True
                    with conn.cursor() as cur:
                        cur.execute("SELECT pg_try_advisory_lock(%s)", (lock_id,))
                        acquired = cur.fetchone()[0]

                    if not acquired:
                        logger.debug("outbox relay standby for %s", self.service_name)
                        time.sleep(1.0)
                        continue

                    try:
                        self._relay_loop(conn)
                    finally:
                        with conn.cursor() as cur:
                            cur.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
                finally:
                    self.db_pool.putconn(conn)
            except Exception:
                logger.exception("outbox relay error for %s", self.service_name)
                time.sleep(1.0)

    def _relay_loop(self, conn):
        conn.autocommit = False
        while not self._stop.is_set():
            try:
                result = relay_once(
                    conn, self.publisher, limit=self.batch_limit
                )
                if result.scanned == 0:
                    time.sleep(self.poll_interval)
            except Exception:
                logger.exception("relay pass failed")
                try:
                    conn.rollback()
                except Exception:
                    pass
                time.sleep(self.poll_interval * 4)
