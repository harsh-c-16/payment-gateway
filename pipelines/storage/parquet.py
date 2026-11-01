"""Stable M05 Parquet schemas; files are read through verified immutable descriptors."""

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
SCHEMAS = {"silver-conversation-turn": SILVER_SCHEMA, "pipeline_minute": GOLD_SCHEMA}


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
