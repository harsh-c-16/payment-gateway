"""Immutable compaction candidates over a pinned manifest. Never touches the active pointer."""

import hashlib
from collections import defaultdict
from dataclasses import dataclass

import pyarrow as pa
import pyarrow.parquet as pq

from pipelines.storage.candidates import _money, canonical_logical_row, digest_sorted_rows
from pipelines.storage.parquet import SCHEMAS, verified_parquet
from shared.contracts.analytics import FileDescriptor, ManifestCandidate

MIB = 1024 * 1024
SILVER_SCHEMAS = {"silver-conversation-turn", "silver-events-v1"}


@dataclass(frozen=True)
class LayoutConfig:
    """target_file_bytes is the compressed goal; a tail file may be smaller."""

    target_file_bytes: int = 32 * MIB
    # Vichitr's reader refuses row groups above 32 MiB uncompressed.
    row_group_bytes: int = 16 * MIB
    transformation_reason: str = "compaction-v1"


def time_column(schema_name):
    if schema_name in SILVER_SCHEMAS:
        return "event_time"
    return "minute" if schema_name == "pipeline_minute" else "cohort_date"


def _row_groups(table, limit):
    """Slices whose uncompressed Arrow size stays under the decode bound."""
    rows = table.num_rows
    if not rows:
        return
    step = max(1, min(rows, int(rows * limit / max(table.nbytes, 1))))
    for start in range(0, rows, step):
        yield table.slice(start, step)


def _write_files(store, prefix, table, schema_name, partition_values, config, start_index):
    """Fills each file with row groups until its compressed size reaches the target."""
    descriptors, column = [], time_column(schema_name)
    writer = sink = None
    rows, times = 0, []

    def close():
        nonlocal writer, sink, rows, times
        writer.close()
        data = sink.getvalue().to_pybytes()
        base = store.write_immutable(
            f"{prefix}/{start_index + len(descriptors):06}.parquet",
            data,
            hashlib.sha256(data).hexdigest(),
        )
        descriptors.append(
            FileDescriptor.model_validate(
                {
                    **base.model_dump(),
                    "row_count": rows,
                    "schema_name": schema_name,
                    "schema_version": 1,
                    "partition_values": partition_values,
                    "min_event_time": min(times),
                    "max_event_time": max(times),
                }
            )
        )
        writer = sink = None
        rows, times = 0, []

    for piece in _row_groups(table, config.row_group_bytes):
        if writer is None:
            sink = pa.BufferOutputStream()
            writer = pq.ParquetWriter(sink, table.schema, compression="zstd", version="2.6")
        writer.write_table(piece)
        rows += piece.num_rows
        times += piece.column(column).to_pylist()
        if sink.tell() >= config.target_file_bytes:
            close()
    if writer is not None:
        close()
    return descriptors


def compact_snapshot(store, manifest, config=None, *, output_prefix):
    """Reads only the files this generation lists, so retired Gold revisions cannot leak in.

    Holding every logical row's canonical bytes in memory is the ceiling here: it is fine for
    the fixtures in this project; streaming through an external sort is the upgrade path.
    """
    config = config or LayoutConfig()
    groups = defaultdict(list)
    for descriptor in manifest.files:
        groups[
            (
                descriptor.schema_name,
                descriptor.schema_version,
                tuple(sorted(descriptor.partition_values.items())),
            )
        ].append(descriptor)
    documents, totals, files, row_count = [], defaultdict(int), [], 0
    for (schema_name, schema_version, partition), members in sorted(
        groups.items(), key=lambda item: str(item[0])
    ):
        tables = []
        for descriptor in members:
            if not descriptor.row_count:
                # An empty replacement holds no logical row; dropping it preserves all of them.
                continue
            with verified_parquet(store, descriptor) as parquet:
                tables.append(parquet.read())
        if not tables:
            continue
        table = pa.concat_tables(tables).combine_chunks()
        for row in table.to_pylist():
            documents.append(canonical_logical_row(schema_name, schema_version, row))
            _money(row, totals)
        row_count += table.num_rows
        files += _write_files(
            store, output_prefix, table, schema_name, dict(partition), config, len(files)
        )
    candidate_manifest = manifest.model_copy(
        update={
            "generation": manifest.generation + 1,
            "parent_generation": manifest.generation,
            "files": files,
        }
    )
    documents.sort()
    return ManifestCandidate(
        base_generation=manifest.generation,
        candidate_manifest=candidate_manifest,
        logical_row_digest=digest_sorted_rows(documents),
        row_count=row_count,
        monetary_totals_by_currency=dict(totals),
        transformation_reason=config.transformation_reason,
    )


def rewrite_unpartitioned(store, manifest, config, output_prefix):
    """F-PARTITION comparator only: same rows and target size with no date/type file split.

    The publisher deliberately refuses a changed partition layout, so this stays benchmark-only.
    Returns descriptors keyed by schema name.
    """
    by_schema, result = defaultdict(list), {}
    for descriptor in manifest.files:
        if descriptor.row_count:
            by_schema[(descriptor.schema_name, descriptor.schema_version)].append(descriptor)
    for (schema_name, _), members in sorted(by_schema.items()):
        tables = []
        for descriptor in members:
            with verified_parquet(store, descriptor) as parquet:
                tables.append(parquet.read())
        table = pa.concat_tables(tables).combine_chunks()
        assert table.schema == SCHEMAS[schema_name]
        result[schema_name] = _write_files(
            store, f"{output_prefix}/{schema_name}", table, schema_name, {}, config, 0
        )
    return result
