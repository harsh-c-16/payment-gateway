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
Snapshot publication/CAS and compactor admission remain M05/M08.
