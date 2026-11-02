"""Q1-Q6 over the real publisher's manifests: file selection and empty generations."""

from datetime import UTC, datetime, timedelta

from analytics.queries import fixture
from analytics.queries.suite import open_connection, run_query


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
