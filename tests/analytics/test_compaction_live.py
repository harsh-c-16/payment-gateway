"""T-04 plus the T-12 compaction cases through Vichitr's real publish_candidate."""

import random
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pyarrow.parquet as pq
import pytest

from analytics.compaction.compact import LayoutConfig, compact_snapshot, rewrite_unpartitioned
from analytics.queries import fixture
from analytics.queries.suite import QUERIES, open_connection, result_digest, run_query
from pipelines.ingestion import BronzeCapture
from pipelines.storage.publication import PublicationConflict


def populate(pipeline, publications=6, events=40):
    fixture.build(
        pipeline,
        pipeline.test_namespace,
        publications=publications,
        events_per_publication=events,
        days=3,
    )


def active(pipeline, dataset="silver"):
    return pipeline.active_manifest(pipeline.test_namespace, dataset)


def prefix(pipeline, name="silver"):
    return f"candidate/{pipeline.test_namespace}/{uuid4()}/{name}"


def results(pipeline, manifests):
    class View:
        files = [item for manifest in manifests for item in manifest.files]

    day = (datetime.now(UTC) - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    connection = open_connection()
    output = {}
    for query_id in QUERIES:
        rows, facts = run_query(connection, query_id, View, pipeline.test_root, day)
        output[query_id] = (result_digest(rows), facts["returned_rows"])
    connection.close()
    return output


def test_compaction_merges_files_and_publishes_with_identical_query_results(pipeline):
    populate(pipeline)
    silver, gold = active(pipeline), active(pipeline, "gold")
    before = results(pipeline, [silver, gold])
    assert before["Q1"][1] > 0 and before["Q6"][1] == sum(f.row_count for f in silver.files)
    candidate = compact_snapshot(pipeline.store, silver, output_prefix=prefix(pipeline))
    assert candidate.row_count == before["Q6"][1]
    assert len(candidate.candidate_manifest.files) < len(silver.files)
    published = pipeline.publish_candidate(candidate)
    assert published.generation == silver.generation + 1
    now_gold = active(pipeline, "gold")
    gold_candidate = compact_snapshot(
        pipeline.store, now_gold, output_prefix=prefix(pipeline, "gold")
    )
    assert pipeline.publish_candidate(gold_candidate).generation == now_gold.generation + 1
    after = results(pipeline, [active(pipeline), active(pipeline, "gold")])
    assert after == before
    # The old generation's files stay readable: a pinned reader is never broken.
    assert results(pipeline, [silver, gold]) == before


def test_candidate_preserves_partitions_codec_and_uses_new_paths(pipeline):
    populate(pipeline, publications=3)
    silver = active(pipeline)
    candidate = compact_snapshot(pipeline.store, silver, output_prefix=prefix(pipeline))
    old_paths = {f.path for f in silver.files}
    for descriptor in candidate.candidate_manifest.files:
        assert descriptor.path not in old_paths
        parquet = pq.ParquetFile(pipeline.test_root / descriptor.path)
        metadata = parquet.metadata
        assert metadata.row_group(0).column(0).compression == "ZSTD"
    assert {tuple(sorted(f.partition_values.items())) for f in silver.files} == {
        tuple(sorted(f.partition_values.items())) for f in candidate.candidate_manifest.files
    }
    manifest = candidate.candidate_manifest
    assert manifest.parent_generation == silver.generation
    assert manifest.source_ranges == silver.source_ranges
    assert manifest.input_manifest_ids == silver.input_manifest_ids
    assert manifest.transform_version == silver.transform_version


def test_small_target_splits_files_keeps_tail_and_publishes(pipeline):
    populate(pipeline, publications=3, events=60)
    silver = active(pipeline)
    config = LayoutConfig(target_file_bytes=2048, row_group_bytes=1024)
    candidate = compact_snapshot(pipeline.store, silver, config, output_prefix=prefix(pipeline))
    assert len(candidate.candidate_manifest.files) > len(
        {tuple(sorted(f.partition_values.items())) for f in silver.files}
    )
    assert pipeline.publish_candidate(candidate).generation == silver.generation + 1


def test_row_groups_stay_under_the_reader_bound(pipeline):
    populate(pipeline, publications=2)
    silver = active(pipeline)
    config = LayoutConfig(row_group_bytes=2048)
    candidate = compact_snapshot(pipeline.store, silver, config, output_prefix=prefix(pipeline))
    assert all(
        pq.ParquetFile(pipeline.test_root / f.path).metadata.num_row_groups >= 1
        for f in candidate.candidate_manifest.files
    )
    assert pipeline.publish_candidate(candidate)


def test_stale_candidate_is_rejected_and_new_generation_survives(pipeline):
    populate(pipeline, publications=2)
    silver = active(pipeline)
    candidate = compact_snapshot(pipeline.store, silver, output_prefix=prefix(pipeline))
    offsets = {}
    records = fixture.records_for(
        pipeline.codec,
        fixture.search_events(
            pipeline.codec,
            pipeline.test_namespace,
            random.Random(7),
            datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        ),
        pipeline.test_namespace,
        offsets,
    )
    # Fresh topic offsets would collide with the fixture's, so move them past it.
    records = [
        type(r)(
            r.source_namespace,
            r.topic,
            r.partition,
            r.offset + 100000,
            r.key_bytes,
            r.value_bytes,
            r.headers,
            r.broker_timestamp,
            r.ingested_at,
            r.raw_sha256,
        )
        for r in records
    ]
    pipeline.curate_silver(
        BronzeCapture(pipeline.store).ingest_bronze(records), {"run_id": "stale-test"}
    )
    pipeline.publish_snapshot(pipeline.test_namespace)
    newer = active(pipeline)
    assert newer.generation == silver.generation + 1
    with pytest.raises(PublicationConflict, match="STALE_MANIFEST"):
        pipeline.publish_candidate(candidate)
    assert active(pipeline).generation == newer.generation
    rebased = compact_snapshot(pipeline.store, newer, output_prefix=prefix(pipeline))
    assert pipeline.publish_candidate(rebased).generation == newer.generation + 1


def test_unpublished_candidate_leaves_original_queryable(pipeline):
    """A compactor that dies before publication changes nothing a reader can see."""
    populate(pipeline, publications=2)
    silver, gold = active(pipeline), active(pipeline, "gold")
    before = results(pipeline, [silver, gold])
    compact_snapshot(pipeline.store, silver, output_prefix=prefix(pipeline))
    assert active(pipeline).generation == silver.generation
    assert results(pipeline, [active(pipeline), active(pipeline, "gold")]) == before


def test_gold_order_revisions_do_not_concatenate_retired_snapshots(pipeline):
    """Orders are revised across publications; only the active key version may survive."""
    populate(pipeline, publications=4, events=30)
    gold = active(pipeline, "gold")
    candidate = compact_snapshot(pipeline.store, gold, output_prefix=prefix(pipeline, "gold"))
    published = pipeline.publish_candidate(candidate)
    connection = open_connection()
    paths = [
        str(pipeline.test_root / f.path) for f in published.files if f.schema_name == "order_fact"
    ]
    rows, distinct = connection.execute(
        f"SELECT count(*), count(DISTINCT order_id) FROM read_parquet({paths!r})"
    ).fetchone()
    connection.close()
    assert rows == distinct > 0


def test_empty_gold_replacement_files_are_dropped_without_losing_rows(pipeline):
    populate(pipeline, publications=2)
    gold = active(pipeline, "gold")
    empty = gold.files[0].model_copy(
        update={"row_count": 0, "min_event_time": None, "max_event_time": None}
    )
    with_empty = gold.model_copy(update={"files": [*gold.files, empty]})
    candidate = compact_snapshot(pipeline.store, with_empty, output_prefix=prefix(pipeline, "gold"))
    assert candidate.row_count == sum(f.row_count for f in gold.files)
    assert all(f.row_count > 0 for f in candidate.candidate_manifest.files)


def test_unpartitioned_layout_holds_the_same_rows_in_fewer_partitions(pipeline):
    populate(pipeline, publications=3)
    silver, gold = active(pipeline), active(pipeline, "gold")
    before = results(pipeline, [silver, gold])
    flat = {
        **rewrite_unpartitioned(pipeline.store, silver, LayoutConfig(), f"layout/{uuid4()}"),
        **rewrite_unpartitioned(pipeline.store, gold, LayoutConfig(), f"layout/{uuid4()}"),
    }

    class View:
        files = [item for group in flat.values() for item in group]

    assert all(not item.partition_values for item in View.files)
    connection = open_connection()
    day = (datetime.now(UTC) - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    for query_id in QUERIES:
        rows, _ = run_query(connection, query_id, View, pipeline.test_root, day)
        assert result_digest(rows) == before[query_id][0], query_id
    connection.close()
