# Parquet compaction candidates (M2)

Owner: Harsh Chaudhari. Authority: [common §13](../../docs/specs/02_COMMON_SPEC.md) and the
[publication handoff](../../docs/vichitr/m08_publication_handoff.md).

`compact_snapshot(store, manifest, config, output_prefix=...)` reads only the files of a pinned
generation and returns a `ManifestCandidate` with new immutable files: same rows, schema, Zstandard
codec and partition keys, targeting 32 MiB compressed. Vichitr's `publish_candidate` validates it and
performs the generation compare-and-swap; this code never touches the active pointer, and a stale
candidate is rejected with `STALE_MANIFEST` so the caller rebases.

`rewrite_unpartitioned` is the F-PARTITION comparator only. The publisher refuses a changed partition
layout, so that layout is never activated.
