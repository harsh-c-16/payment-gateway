"""M4 raw quarantine; no substitute production outbox or independent commit."""

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from psycopg.pq import TransactionStatus

from pipelines.ingestion.bronze import SourceCorruption
from shared.contracts.events import LocalDiagnostic, SourceLocator
from shared.event_transport.codec import build_dlq_notice
from shared.local_diagnostics import OutboxUnavailable


def outbox_binding():
    try:
        from shared.outbox import append_outbox
    except ImportError as exc:
        raise OutboxUnavailable("Aditya's append_outbox(tx,event) is required") from exc
    if not callable(append_outbox):
        raise OutboxUnavailable("Aditya's append_outbox(tx,event) is required")
    return append_outbox


def route_dlq(
    source_record,
    validation_failure,
    db_transaction,
    *,
    run_id,
    transform_version="m05-conversation-v1",
):
    if db_transaction.info.transaction_status != TransactionStatus.INTRANS:
        raise ValueError("An active analytics transaction is required")
    append = outbox_binding()
    source = source_record
    stored = db_transaction.execute(
        """SELECT raw_locator,raw_sha256 FROM source_receipts
           WHERE namespace=%s AND topic=%s AND partition=%s AND offset_number=%s""",
        (source.source_namespace, source.topic, source.partition, source.offset),
    ).fetchone()
    if stored is None or stored[1] != source.raw_sha256:
        raise SourceCorruption("Quarantine source is not the durable captured source")
    raw_locator = stored[0]
    diagnostic_id = str(
        uuid5(
            NAMESPACE_URL,
            f"{source.source_namespace}:{source.topic}:"
            f"{source.partition}:{source.offset}:{source.raw_sha256}",
        )
    )
    locator = SourceLocator(
        topic=source.topic,
        partition=source.partition,
        offset=source.offset,
        raw_locator=raw_locator,
    )
    now = datetime.now(UTC)
    diagnostic = LocalDiagnostic(
        diagnostic_id=diagnostic_id,
        namespace=source.source_namespace,
        run_id=run_id,
        source_service="analytics",
        reason_code=validation_failure.reason_code,
        correlation_id=diagnostic_id,
        created_at=now,
        content_hash=source.raw_sha256,
        restricted_content_reference=raw_locator,
        source_coordinates=locator,
    )
    with db_transaction.transaction():
        inserted = db_transaction.execute(
            """INSERT INTO quarantine
               (quarantine_id,namespace,topic,partition,offset_number,raw_locator,raw_sha256,
                reason_code,validation_path,diagnostic_message,first_seen_at,schema_version,
                transform_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s)
               ON CONFLICT(quarantine_id) DO NOTHING RETURNING quarantine_id""",
            (
                diagnostic_id,
                source.source_namespace,
                source.topic,
                source.partition,
                source.offset,
                raw_locator,
                source.raw_sha256,
                validation_failure.reason_code.value,
                validation_failure.field_path,
                validation_failure.diagnostic_message,
                now,
                transform_version,
            ),
        ).fetchone()
        if inserted:
            append(db_transaction, build_dlq_notice(diagnostic))
    return diagnostic_id
