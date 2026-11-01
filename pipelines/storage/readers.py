"""Generation-pinned reads and committed, namespace-ordered source observations."""

from datetime import UTC, date, datetime
from decimal import Decimal

from pydantic import TypeAdapter

from pipelines.curation.db import one, rows
from pipelines.gold.business import TABLES
from shared.contracts.analytics import (
    DatasetManifest,
    GoldQueryResult,
    QuarantinePage,
    QuarantineRecord,
    ReceiptPage,
    SourceReceipt,
)
from shared.contracts.events import Namespace, SourceLocator

from .parquet import read_verified


def active_manifest(connect, namespace, dataset):
    TypeAdapter(Namespace).validate_python(namespace)
    if dataset not in {"silver", "gold"}:
        raise ValueError("Unknown dataset")
    with connect() as tx:
        row = one(
            tx,
            """SELECT m.manifest,a.generation FROM active_datasets a
            JOIN snapshot_manifests m USING(namespace,dataset,generation)
            WHERE a.namespace=%s AND a.dataset=%s""",
            (namespace, dataset),
        )
    if row is None:
        raise LookupError("No active publication")
    manifest = DatasetManifest.model_validate(row["manifest"])
    if (
        manifest.namespace != namespace
        or manifest.dataset != dataset
        or manifest.generation != row["generation"]
    ):
        raise ValueError("Active manifest identity mismatch")
    return manifest


def query_gold(pipeline, namespace, table, date_from, date_to, currency=None):
    if table not in ("pipeline_minute", *TABLES):
        from pipelines.curation import UnsupportedEvent

        raise UnsupportedEvent("Labelled evaluation artifact/provider required for this Gold table")
    if currency is not None and table not in {
        "order_fact",
        "daily_conversion",
        "checkout_funnel",
        "payment_failures",
    }:
        raise ValueError("This Gold table has no currency dimension")
    start = TypeAdapter(date).validate_python(date_from)
    end = TypeAdapter(date).validate_python(date_to)
    if end <= start:
        raise ValueError("date_to must follow date_from")
    manifest = active_manifest(pipeline.connect, namespace, "gold")
    result = []
    for descriptor in manifest.files:
        if descriptor.schema_name != table:
            continue
        for row in read_verified(pipeline.store, descriptor).to_pylist():
            if row["namespace"] != namespace:
                raise ValueError("Published row namespace mismatch")
            timestamp = row["minute"] if table == "pipeline_minute" else row["cohort_date"]
            if start <= timestamp.date() < end and (
                currency is None or row["currency"] == currency
            ):
                result.append(_wire(row))
    return GoldQueryResult(
        generation=manifest.generation, rows=result, queried_at=datetime.now(UTC)
    )


def _wire(value):
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else str(value)
    if isinstance(value, dict):
        return {key: _wire(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_wire(item) for item in value]
    return value


def _limit(limit):
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("limit must be 1..1000")


def receipts(connect, namespace, after_cursor=None, limit=1000):
    TypeAdapter(Namespace).validate_python(namespace)
    _limit(limit)
    if after_cursor is None:
        cursor = 0
    elif (
        not isinstance(after_cursor, str)
        or not after_cursor.isascii()
        or not after_cursor.isdecimal()
        or len(after_cursor) > 19
    ):
        raise ValueError("Invalid receipt cursor")
    else:
        cursor = int(after_cursor)
        if cursor > 2**63 - 1:
            raise ValueError("Invalid receipt cursor")
    with connect() as tx:
        found = rows(
            tx,
            """SELECT j.cursor_id,s.* FROM receipt_journal j JOIN source_receipts s
            USING(namespace,topic,partition,offset_number)
            WHERE j.namespace=%s AND j.cursor_id>%s ORDER BY j.cursor_id LIMIT %s""",
            (namespace, cursor, limit),
        )
    result = []
    for row in found:
        result.append(
            SourceReceipt(
                namespace=namespace,
                source=SourceLocator(
                    topic=row["topic"],
                    partition=row["partition"],
                    offset=row["offset_number"],
                    raw_locator=row["raw_locator"],
                ),
                raw_sha256=row["raw_sha256"],
                event_id=None if row["event_id"] is None else str(row["event_id"]),
                disposition=row["disposition"],
                reason_code=row["reason_code"],
                ingested_at=row["ingested_at"],
                bronze_durable_at=row["bronze_durable_at"],
                silver_committed_observed_at=row["silver_committed_observed_at"],
                gold_visible_at=row["gold_visible_at"],
                visibility_generation=row["visibility_generation"],
                timing_validity=row["timing_validity"],
            )
        )
    return ReceiptPage(receipts=result, next_cursor=str(found[-1]["cursor_id"]) if found else None)


def quarantine(connect, namespace, cursor=None, limit=1000):
    TypeAdapter(Namespace).validate_python(namespace)
    _limit(limit)
    with connect() as tx:
        sequence = 0
        if cursor is not None:
            from shared.contracts.common import UUIDText

            cursor = TypeAdapter(UUIDText).validate_python(cursor)
            previous = one(
                tx,
                """SELECT quarantine_sequence FROM quarantine
                   WHERE namespace=%s AND quarantine_id=%s""",
                (namespace, cursor),
            )
            if previous is None:
                raise ValueError("Unknown quarantine cursor")
            sequence = previous["quarantine_sequence"]
        found = rows(
            tx,
            """SELECT * FROM quarantine WHERE namespace=%s AND quarantine_sequence>%s
                            ORDER BY quarantine_sequence LIMIT %s""",
            (namespace, sequence, limit),
        )
    return QuarantinePage(
        records=[
            QuarantineRecord(
                quarantine_id=str(row["quarantine_id"]),
                namespace=namespace,
                source_locator=SourceLocator(
                    topic=row["topic"],
                    partition=row["partition"],
                    offset=row["offset_number"],
                    raw_locator=row["raw_locator"],
                ),
                raw_sha256=row["raw_sha256"],
                reason_code=row["reason_code"],
                validation_path=row["validation_path"],
                diagnostic_message=row["diagnostic_message"],
                first_seen_at=row["first_seen_at"],
                schema_version=row["schema_version"],
                transform_version=row["transform_version"],
                repair_status=row["repair_status"],
                repair_reference=row["repair_reference"],
            )
            for row in found
        ],
        next_cursor=str(found[-1]["quarantine_id"]) if found else None,
    )
