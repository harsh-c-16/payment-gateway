# M08 incremental publication and compactor handoff

Owner: Vichitr. Authority: [common §§11–13](../specs/02_COMMON_SPEC.md) and
[V05](../specs/07_VICHITR_ARORA.md). This is the publication provider checkpoint;
Harsh's actual compactor, integrated T-04/T-12 and full W-QUALITY remain separate
handoffs. Business transforms remain m07-business-v1; their meanings did not change.

Stop API/workers for the upgrade, apply analytics migrations through
`PROJECTCTL_ADAPTER_MODULE=infra.analytics python -m projectctl db migrate --namespace bench-<run>`,
then restart the new version. Owned evidence must show versions 1–5. The command
still reports global dependency exit 4 for uncomposed service/outbox providers.
Migration 005 indexes source receipts by namespace/event_id for visibility updates;
migrations 001–004 remain immutable. Do not mix old and new publishers.

## Incremental snapshots

One publisher session owns each namespace. Repeatable read freezes exact pending
and newly visible ID sets in connection-local PostgreSQL temporary tables. Pinned
parent generations supply existing membership. New arrivals
continue in other transactions while the frozen snapshot is exported.

Silver appends files only for newly visible accepted IDs, retaining all previously
active files. Export-pending business backfills of already published events do not
append a second Silver row. Gold replaces complete dirty table/date partitions;
unaffected files retain their hashes and paths. Each replacement may use multiple
bounded files, including an empty replacement when no current rows remain.

Files are durable and verified before activation. A short transaction checks both
old generations, inserts both manifests and exact frozen memberships, swaps both
pointers, records first visibility and deletes only frozen pending IDs. Internal
manifest_members rows contain new-ID deltas; iter_membership resolves full sets
through retained parent generations, including older full-set rows. Compaction
inherits membership without copying IDs or creating new visibility. Cascading
dirty-key deletion cannot erase a concurrent arrival's membership. Visibility
observations use durable jobs of at most 512 IDs. A lost post-commit observation
is recovered as an explicit upper bound; compaction never resets first visibility.
recover_observations handles at most 100 jobs per call; repeat until drained.

The old whole-dataset limits of 10,000 facts / 8 MiB are removed. Working data is
bounded by 512 rows / approximately 4 MiB of canonical row JSON per output file.
A single projected/exported row is limited to 8 MiB before fetching/encoding it;
an oversized row fails without activating files or clearing pending IDs. The
per-row bound matters for a search cohort's nested duration references. File
metadata and dirty partition metadata still grow with file/partition counts.
Gold HTTP results remain unpaginated, so response memory grows with returned rows.
These are safety limits, not throughput or unlimited-capacity claims.

Verified file reads hash the same open handle, validate schema/version/footer
counts, and decode 32 rows at a time. Each Parquet row group must contain at most
32 MiB of uncompressed data. A 32-MiB compressed compaction file may contain
multiple row groups; Harsh should size row groups separately from target file size.
Database sorts use 4-MiB work_mem and can spill to PostgreSQL temporary storage.

## Versioned lineage

New input lineage JSON has format_version=2. membership_files lists immutable
JSON shards with path, SHA-256 and event_count. Each shard contains event_ids and
sources with exact event ID, topic, partition, offset, capture ID and raw locator/hash.
Shards have at most 512 members. parent_input_manifest_ids preserves prior roots;
the root plus parents describes full membership, including gaps in source ranges.
Compaction roots add a compaction record and reference their source roots.

Existing format-1 roots with inline event_ids/sources and existing Parquet schemas
remain retained and readable. A lineage consumer follows parent roots and verifies
shards; it must not interpret a min/max offset range as complete membership. Source
origin, dictionaries, licence/acquisition/generator metadata remain in the original
Silver envelopes and Bronze sources, without inferred provenance.

## Candidate contract for Harsh

The existing Python provider is `publish_candidate(pipeline, candidate)` in
pipelines.storage.candidates, also exposed as pipeline.publish_candidate(candidate).
Harsh supplies the canonical ManifestCandidate, built from a pinned active manifest:

- base_generation is that active generation; candidate_manifest has generation
  base+1, parent=base, the same namespace/dataset/transform and identical input
  lineage/source ranges. File paths are new and cannot reuse any published path.
- Preserve each file's registered schema/version, Zstandard codec and logical
  partition keys. Descriptor row counts, partitions and exact time bounds must
  match actual rows. Existing mixed Silver schemas remain separate physical schemas.
- Preserve every logical row value, including namespace, nulls, integer/decimal
  money, nested arrays, transform/revision and row publication lineage. Only physical
  row order and layout change. Silver event IDs and Gold logical keys stay unique.
- Compute row_count, logical_row_digest and monetary_totals_by_currency using the
  integrity format below. These totals are integrity checks across projections,
  not sales/revenue metrics.

Canonical row bytes are UTF-8 canonical JSON of `[schema_name,schema_version,row]`:
sorted object keys, no extra whitespace, literal Unicode, finite JSON numbers,
UTC timestamps with Z, and integral decimals as exact JSON integers. Nested arrays
retain order. Sort row byte strings in ascending byte order, retaining duplicates.
Start SHA-256 with `m08-logical-rows-v1\n`, then append, for each row, its decimal
byte length, `:`, row bytes and `\n`. The pure canonical_logical_row and
digest_sorted_rows helpers implement this format; the caller supplies sorted bytes.

Currency totals recursively sum every non-null field ending `_minor` in an object
with its own currency, using exact integer arithmetic. Nested payloads/intents are
included; serialized envelope/metadata JSON strings are not parsed again. Different
Gold projections can repeat an amount, deliberately, because this is a file-integrity
sum. An order amount 12,345 plus its daily created and confirmed amounts totals
37,035. The current contract permits INR only.

The provider streams base and candidate files into SQL temporary rows, independently
checks their sorted digests/counts/totals, rejects repeated keys and compares exact
row bytes by key. It also fsyncs candidate files/directories before activation.
Validation reads pinned published files, never mutable staging. Activation repeats
the generation check/CAS, advances both dataset generations atomically and copies
their source membership. The untouched dataset reuses its files. Concurrent new
ingress remains pending for the next normal publication. A stale candidate raises
PublicationConflict with STALE_MANIFEST; invalid candidates leave active data intact.

One precise contract limit remains for owner/consumer review: ManifestCandidate's
totals use Money, capped at int64, while valid Gold integrity sums can exceed it.
Such candidates fail closed with an explicit int64-contract error. No total is
rounded or truncated and the public DTO is unchanged. Harsh/Jaineel/Vichitr must
review a widened aggregate-total representation before those candidates can activate.
Harsh must adopt/review the integrity format and row-group bound before real T-04.

## Recovery and evidence

Disabled publication.boundary hooks mark after_files_durable, before_manifest_swap
(inside the pointer transaction, before COMMIT), and after_manifest_swap (after
acknowledged COMMIT). Tests additionally intercept the real before-rename boundary.
There is no arbitrary command/HTTP fault control. Test child processes print a named
barrier acknowledgement then exit without cleanup, proving the intended boundary.

Real PostgreSQL/Linux-volume tests cover normal and candidate pointer failures,
stale candidates at admission and commit, concurrent ingress, retained old readers,
exact observations, all four normal publication kill points and three candidate kill
points. Candidate construction is an explicitly labelled small compactor double.
The large publisher-only fixture uses real Bronze/receipts and 10,001 valid synthetic
snapshots staged through bulk SQL; it is not B0/Kafka ingestion or W-QUALITY evidence.
See [progress](progress.md) for source revisions, exact commands and raw results.

All source files, retired manifests/files, lineage and crash orphans remain retained.
list_orphans is read-only; preserve all retained/replay/pinned-reader references.
No garbage collection runs during these checks. Process-kill recovery does not prove
host power-loss or volume-loss durability. Next checkpoint: M09 late data/watermarks.
