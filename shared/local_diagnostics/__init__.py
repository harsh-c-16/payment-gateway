"""Caller-owned diagnostic + Aditya outbox, within a savepoint of the caller transaction."""

from collections.abc import Mapping
from pathlib import Path

from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb

from shared.contracts.events import LocalDiagnostic
from shared.event_transport.codec import build_dlq_notice
from shared.event_transport.schemas import schema_hash


class OutboxUnavailable(RuntimeError):
    pass


class DiagnosticConflict(ValueError):
    pass


def diagnostic_table_ddl():
    """The service owner applies this template through its own migration machinery."""
    return Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")


def quarantine_local_diagnostic(db_transaction, diagnostic):
    diagnostic = LocalDiagnostic.model_validate(diagnostic)
    if db_transaction.info.transaction_status != TransactionStatus.INTRANS:
        raise ValueError("an existing caller-owned PostgreSQL transaction is required")
    try:
        from shared.outbox import append_outbox
    except ImportError as exc:
        raise OutboxUnavailable("Aditya's append_outbox(tx,event) binding is unavailable") from exc
    if not callable(append_outbox):
        raise OutboxUnavailable("Aditya's append_outbox(tx,event) binding is unavailable")
    document = diagnostic.model_dump(mode="json")
    digest = schema_hash(document)
    # A savepoint rolls back the diagnostic if append raises a non-SQL exception
    # that the caller catches; the outer transaction still belongs to the caller.
    with db_transaction.transaction():
        inserted = db_transaction.execute(
            "INSERT INTO local_diagnostics "
            "(namespace,diagnostic_id,run_id,source_service,reason_code,correlation_id,"
            "created_at,content_hash,restricted_content_reference,"
            "source_coordinates,record_sha256) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT(namespace,diagnostic_id) DO NOTHING RETURNING diagnostic_id",
            (
                diagnostic.namespace,
                diagnostic.diagnostic_id,
                diagnostic.run_id,
                diagnostic.source_service,
                diagnostic.reason_code.value,
                diagnostic.correlation_id,
                diagnostic.created_at,
                diagnostic.content_hash,
                diagnostic.restricted_content_reference,
                None
                if diagnostic.source_coordinates is None
                else Jsonb(document["source_coordinates"]),
                digest,
            ),
        ).fetchone()
        if inserted is None:
            row = db_transaction.execute(
                "SELECT record_sha256 FROM local_diagnostics "
                "WHERE namespace=%s AND diagnostic_id=%s",
                (diagnostic.namespace, diagnostic.diagnostic_id),
            ).fetchone()
            stored = row["record_sha256"] if isinstance(row, Mapping) else row[0]
            if stored != digest:
                raise DiagnosticConflict("diagnostic ID cannot be reused with different content")
        else:
            append_outbox(db_transaction, build_dlq_notice(diagnostic))
    return diagnostic.diagnostic_id
