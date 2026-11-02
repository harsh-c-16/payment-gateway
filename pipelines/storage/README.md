# Durable FileStore (M04)

Owner: Vichitr. Authority: [common §11.1](../../docs/specs/02_COMMON_SPEC.md).

```python
from hashlib import sha256
from pipelines.storage import FileStore

store = FileStore("/lakehouse")  # existing private Linux named-volume mount
descriptor = store.write_immutable(
    "raw/source.csv", original_bytes, sha256(original_bytes).hexdigest()
)
assert store.exists_with_hash(descriptor.path, descriptor.sha256)
assert store.read(descriptor.path) == original_bytes
orphans = store.list_orphans(all_retained_referenced_paths)
```

The three-argument write preserves opaque bytes. Its FileDescriptor has
schema_name=opaque-bytes, row_count=0, empty partitions and null event times:
FileStore does not interpret CSV or invent row counts. Harsh supplies known source
metadata in his manifest; Bronze supplies verified wrapper metadata.

Writes verify input hash, sync created parent directories, write a unique temporary
file, flush/fsync it, rename within its directory, fsync directories and read back
the hash before returning. Same path/hash retries also fsync file/directories;
different content raises ImmutableConflict. A volume-wide advisory file lock
serializes cooperating processes. Only FileStore writers may mutate this private
tree; external writers must not race it. Traversal, absolute paths, backslashes,
internal lock paths and symlinks are rejected.

Directory fsync is mandatory. Native Windows raises DurabilityUnavailable before
writing; use the Docker Linux named volume, not a Windows bind mount. No weaker
fallback reports success. I/O errors propagate. A crash after rename can leave an
unreferenced file; retry verifies/syncs it. A process-crash test does not prove
survival of host power loss or loss of Docker's virtual disk.

list_orphans is a **read-only inventory**. Supply all retained manifests, Bronze
receipts, replay and pinned-reader references, not just the latest active manifest.
It may list an unpublished file. Nothing deletes files or stale temporary files
automatically. Retain data at least 30 days and through final acceptance; cleanup
remains explicit and disabled during experiments.

See [M04 handoff](../../docs/vichitr/m04_capture_handoff.md) for real-volume checks.
M05 publication/CAS and generation-pinned readers are in publication.py/readers.py;
see the [M05 handoff](../../docs/vichitr/m05_vertical_handoff.md). M08 now supplies
incremental publication and compactor admission; see the
[current publication handoff](../../docs/vichitr/m08_publication_handoff.md).

M06 exports `silver-events-v1`: common typed envelope/provenance fields and a typed
payload struct covering all 24 registered business types, with UTC microsecond
timestamps, int64 amounts/counts, string lists and nullable intent facets. Original
envelope/metadata JSON preserves optional additions and supplied dictionary hashes.
The legacy `silver-conversation-turn` schema remains registered for existing M05
files; immutable files are never rewritten during migration. A current manifest
may reference both schemas. See the [M06 handoff](../../docs/vichitr/m06_silver_handoff.md).

M07 adds typed business Gold files with UTC cohort_date, transform_version,
partition revision and publication_generation. Exact integer money sums use
decimal128(38,0); JSON returns integers. Search duration sums/references remain
decimal strings. Generation-pinned queries use half-open cohort date ranges;
currency applies only to monetary tables and the currency-scoped checkout funnel.
Per-event dirty keys survive arrivals after a frozen snapshot. Migration 004
backfills existing Silver without changing its hashes or pipeline counts; see
the [M07 handoff](../../docs/vichitr/m07_business_gold_handoff.md).

M08 appends only new Silver files and replaces dirty Gold partitions in bounded
chunks, with exact frozen membership held in SQL temporary tables. Version-2
lineage uses hashed membership shards and parent roots. The former total snapshot
cap is removed; the 8-MiB single-row and 32-MiB uncompressed row-group guards remain.
publish_candidate validates pinned files, sorted logical digests, exact currency
integrity totals and key uniqueness before paired generation CAS. See the current
handoff for Harsh's format, source/visibility preservation and the outstanding
aggregate-total int64 contract limit. No cleanup or compactor implementation is
included in this provider.
