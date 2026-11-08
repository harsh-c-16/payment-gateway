"""Q1-Q6 over the real publisher's manifests: file selection and empty generations."""

import os
from datetime import UTC, datetime, timedelta

import pytest

from analytics.queries import experiment, fixture
from analytics.queries.suite import (
    LAYOUT_FOR_PARAMETERS,
    QUERIES,
    build_layouts,
    open_connection,
    result_digest,
    run_query,
    runner_layout_for,
)


def active(pipeline, dataset="silver"):
    return pipeline.active_manifest(pipeline.test_namespace, dataset)


def populate(pipeline, publications=3, events=40):
    fixture.build(
        pipeline,
        pipeline.test_namespace,
        publications=publications,
        events_per_publication=events,
        days=3,
    )


def test_q5_prunes_files_only_when_a_partition_can_be_excluded(pipeline):
    populate(pipeline)
    silver = active(pipeline)
    day = (datetime.now(UTC) - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    class View:
        files = silver.files

    connection = open_connection()
    _, q5 = run_query(connection, "Q5", View, pipeline.test_root, day)
    _, q6 = run_query(connection, "Q6", View, pipeline.test_root, day)
    connection.close()
    assert q5["files_opened"] < q6["files_opened"]
    assert q5["selected_file_bytes"] < q6["selected_file_bytes"]


def test_query_suite_returns_empty_when_no_files_exist():
    class View:
        files = []

    connection = open_connection()
    rows, facts = run_query(connection, "Q2", View, "/nonexistent", None)
    connection.close()
    assert rows == [] and facts["files_opened"] == 0


@pytest.mark.skipif(not hasattr(os, "posix_fadvise"), reason="NOT_RUN: eviction needs Linux")
def test_cold_series_keeps_the_warm_results_and_stays_in_its_own_file(pipeline, tmp_path):
    # posix_fadvise alone does not establish that this kernel exposes actual
    # read-byte counters. Keep an unavailable cold measurement visibly NOT_RUN.
    try:
        experiment.storage_read_bytes()
    except OSError as error:
        pytest.skip(f"NOT_RUN: real cold-read counters unavailable ({type(error).__name__})")
    fixture.build(pipeline, pipeline.test_namespace, publications=2, events_per_publication=20)

    class Layout:
        files = list(pipeline.active_manifest(pipeline.test_namespace, "silver").files) + list(
            pipeline.active_manifest(pipeline.test_namespace, "gold").files
        )

    day = (datetime.now(UTC) - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    layouts = {"only": Layout}
    warm_rows, warm = experiment.measure(layouts, pipeline.test_root, day, tmp_path)
    cold_rows, cold = experiment.measure_cold(layouts, pipeline.test_root, day, tmp_path)
    assert {query: values["only"] for query, values in cold.items()} == {
        query: values["only"] for query, values in warm.items()
    }
    assert len(cold_rows) == len(QUERIES) * experiment.COLD_EXECUTIONS * experiment.REPETITIONS
    assert (tmp_path / "query_results_cold.parquet").is_file()
    assert (tmp_path / "query_results.parquet").is_file()
    series = experiment.summarize_cold(cold_rows, layouts)
    assert all("median_storage_read_bytes" in value for value in series.values())


def test_cold_series_is_not_run_where_eviction_cannot_be_proven(tmp_path, monkeypatch):
    def unavailable():
        raise OSError("read_bytes is missing from /proc/self/io")

    monkeypatch.setattr(experiment, "storage_read_bytes", unavailable)
    result = experiment.cold_series({}, tmp_path, None, tmp_path, {})
    assert result == {
        "cold_series": {"status": "NOT_RUN", "reason": "read_bytes is missing from /proc/self/io"}
    }
    assert not (tmp_path / "query_results_cold.parquet").exists()


def test_runner_layouts_pin_each_frozen_variant_with_identical_results(pipeline):
    populate(pipeline)
    layouts, _ = build_layouts(pipeline, pipeline.test_namespace)
    layout_for = runner_layout_for(layouts)
    assert len(layouts["compacted"].files) < len(layouts["small_files"].files)
    day = (datetime.now(UTC) - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    connection = open_connection()
    for query_id in QUERIES:
        digests = set()
        for file_layout, partitioning in LAYOUT_FOR_PARAMETERS:
            context = {"parameters": {"file_layout": file_layout, "partitioning": partitioning}}
            rows, _ = run_query(connection, query_id, layout_for(context), pipeline.test_root, day)
            digests.add(result_digest(rows))
        assert len(digests) == 1, query_id
    connection.close()
    with pytest.raises(KeyError):
        layout_for({"parameters": {"file_layout": "small", "partitioning": "unpartitioned"}})
