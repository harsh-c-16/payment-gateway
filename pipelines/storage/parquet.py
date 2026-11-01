"""Versioned Parquet schemas; old published files remain readable."""

import hashlib

import pyarrow as pa
import pyarrow.parquet as pq

from shared.contracts.analytics import FileDescriptor

UTC = pa.timestamp("us", tz="UTC")
SILVER_SCHEMA = pa.schema(
    [
        ("namespace", pa.string()),
        ("event_id", pa.string()),
        ("content_hash", pa.string()),
        ("event_time", UTC),
        ("produced_at", UTC),
        ("event_type", pa.string()),
        ("source_service", pa.string()),
        ("aggregate_type", pa.string()),
        ("aggregate_id", pa.string()),
        ("aggregate_version", pa.int64()),
        ("run_id", pa.string()),
        ("correlation_id", pa.string()),
        ("session_id", pa.string()),
        ("user_id", pa.string()),
        ("dataset_revision", pa.string()),
        ("turn_id", pa.string()),
        ("mode", pa.string()),
        ("outcome", pa.string()),
        ("duration_ms", pa.float64()),
        ("llm_call_count", pa.int64()),
        ("extractor_source", pa.string()),
        ("envelope_json", pa.string()),
        ("raw_locator", pa.string()),
    ]
)
GOLD_SCHEMA = pa.schema(
    [
        ("namespace", pa.string()),
        ("minute", UTC),
        ("event_type", pa.string()),
        ("source_service", pa.string()),
        ("unique_events", pa.int64()),
        ("transform_version", pa.string()),
        ("revision", pa.int64()),
        ("publication_generation", pa.int64()),
    ]
)
INTENT_TYPE = pa.struct(
    [
        (name, pa.string())
        for name in (
            "query_text",
            "category",
            "brand",
            "size",
            "colour",
            "material",
            "occasion",
            "currency",
        )
    ]
    + [("max_price_minor", pa.int64()), ("category_path_prefix", pa.list_(pa.string()))]
)
PAYLOAD_TYPE = pa.struct(
    [
        (name, pa.string())
        for name in (
            "turn_id",
            "mode",
            "outcome",
            "extractor_source",
            "extractor_version",
            "reason_code",
            "restricted_content_reference",
            "tool_call_id",
            "tool_name",
            "cart_id",
            "sku",
            "quote_id",
            "order_id",
            "confirmation_id",
            "search_id",
            "comparison_id",
            "currency",
            "order_status",
            "user_id",
            "session_id",
            "failure_code",
            "reservation_id",
            "payment_id",
            "reservation_request_id",
            "status",
            "debit_id",
            "reversal_id",
        )
    ]
    + [
        (name, pa.int64())
        for name in (
            "llm_call_count",
            "cart_version",
            "quantity_after",
            "returned_count",
            "price_minor",
            "catalog_version",
            "total_amount_minor",
            "on_hand",
            "reserved",
            "available",
            "stock_version",
            "attempt_number",
            "amount_minor",
        )
    ]
    + [(name, UTC) for name in ("created_at", "changed_at", "attempt_created_at")]
    + [
        ("duration_ms", pa.float64()),
        ("intent", INTENT_TYPE),
        ("skus", pa.list_(pa.string())),
        ("field_names", pa.list_(pa.string())),
    ]
)
# The first fifteen legacy columns are the unchanged envelope/provenance projection.
SILVER_EVENTS_SCHEMA = pa.schema(
    list(SILVER_SCHEMA)[:15]
    + [
        ("schema_version", pa.int32()),
        ("payload", PAYLOAD_TYPE),
        ("synthetic", pa.bool_()),
        ("scenario_source", pa.string()),
        ("metadata_json", pa.string()),
        ("envelope_json", pa.string()),
        ("raw_locator", pa.string()),
    ]
)
SCHEMAS = {
    "silver-conversation-turn": SILVER_SCHEMA,
    "silver-events-v1": SILVER_EVENTS_SCHEMA,
    "pipeline_minute": GOLD_SCHEMA,
}
BUSINESS_META = [
    ("namespace", pa.string()),
    ("cohort_date", UTC),
    ("transform_version", pa.string()),
    ("revision", pa.int64()),
    ("publication_generation", pa.int64()),
]
MONEY_SUM = pa.decimal128(38, 0)
SCHEMAS.update(
    {
        "order_fact": pa.schema(
            BUSINESS_META
            + [
                ("order_id", pa.string()),
                ("order_version", pa.int64()),
                ("event_id", pa.string()),
                ("order_status", pa.string()),
                ("total_amount_minor", pa.int64()),
                ("currency", pa.string()),
                ("created_at", UTC),
                ("user_id", pa.string()),
                ("session_id", pa.string()),
                ("quote_id", pa.string()),
                ("failure_code", pa.string()),
                ("reservation_id", pa.string()),
                ("payment_id", pa.string()),
            ]
        ),
        "daily_conversion": pa.schema(
            BUSINESS_META
            + [("currency", pa.string())]
            + [
                (name, pa.int64())
                for name in (
                    "created_orders",
                    "confirmed_orders",
                    "cancelled_orders",
                    "pending_orders",
                )
            ]
            + [("conversion", pa.float64())]
            + [
                (name + "_amount_minor", MONEY_SUM)
                for name in ("created", "confirmed", "cancelled", "pending")
            ]
        ),
        "checkout_funnel": pa.schema(
            BUSINESS_META
            + [("currency", pa.string())]
            + [
                (name + "_orders", pa.int64())
                for name in (
                    "created",
                    "reserved",
                    "payment_success",
                    "inventory_committed",
                    "confirmed",
                )
            ]
        ),
        "payment_failures": pa.schema(
            BUSINESS_META
            + [("currency", pa.string()), ("failure_code", pa.string())]
            + [
                (name + "_attempts", pa.int64())
                for name in ("failed", "successful", "reversed", "pending", "cancelled")
            ]
            + [
                (name + "_amount_minor", MONEY_SUM)
                for name in ("failed", "successful", "reversed", "pending", "cancelled")
            ]
        ),
        "inventory_failures": pa.schema(
            BUSINESS_META + [("reason_code", pa.string()), ("failed_reservations", pa.int64())]
        ),
        "search_performance": pa.schema(
            BUSINESS_META
            + [
                ("mode", pa.string()),
                ("unique_searches", pa.int64()),
                ("empty_results", pa.int64()),
                ("duration_sum_ms", pa.string()),
                ("duration_count", pa.int64()),
                (
                    "duration_references",
                    pa.list_(pa.struct([("event_id", pa.string()), ("duration_ms", pa.string())])),
                ),
            ]
        ),
    }
)


class FileVerificationError(RuntimeError):
    pass


def read_verified(store, descriptor):
    data = store.read(descriptor.path)
    if len(data) != descriptor.byte_size or hashlib.sha256(data).hexdigest() != descriptor.sha256:
        raise FileVerificationError("Published file size/hash mismatch")
    try:
        table = pq.read_table(pa.BufferReader(data))
    except pa.ArrowException as exc:
        raise FileVerificationError("Invalid published Parquet") from exc
    if table.schema != SCHEMAS[descriptor.schema_name] or table.num_rows != descriptor.row_count:
        raise FileVerificationError("Published file schema/row count mismatch")
    return table


def write_parquet(store, path, records, schema_name, partitions, times):
    table = pa.Table.from_pylist(records, schema=SCHEMAS[schema_name])
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink, compression="zstd", version="2.6")
    data = sink.getvalue().to_pybytes()
    base = store.write_immutable(path, data, hashlib.sha256(data).hexdigest())
    descriptor = FileDescriptor.model_validate(
        {
            **base.model_dump(),
            "row_count": len(records),
            "schema_name": schema_name,
            "partition_values": partitions,
            "min_event_time": min(times),
            "max_event_time": max(times),
        }
    )
    read_verified(store, descriptor)
    return descriptor
