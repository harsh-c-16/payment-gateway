"""SQL transaction doubles exercise grouping/rollback; no live durability claim."""

from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

import pytest

import pipelines.curation as sink
from pipelines.replay import jobs


class DatabaseDouble:
    def __init__(self):
        self.facts, self.batches = [], []

    @contextmanager
    def connect(self):
        yield self

    @contextmanager
    def transaction(self):
        before = deepcopy((self.facts, self.batches))
        try:
            yield
        except BaseException:
            self.facts, self.batches = before
            raise

    def execute(self, statement, values):
        assert "INSERT INTO sink_batches" in statement
        self.batches.append(values)
        return SimpleNamespace(fetchone=lambda: (len(self.batches),))


def pipeline_double(monkeypatch, size, rows, *, fail_at=None):
    database = DatabaseDouble()
    records = [
        SimpleNamespace(
            topic="bench-batch.inventory-events.v1",
            partition=0,
            offset=i,
            source_namespace="bench-batch",
        )
        for i in range(size)
    ]
    receipt = SimpleNamespace(capture_id="capture-double", records=[])
    monkeypatch.setattr(sink, "RawBatchReceipt", SimpleNamespace(model_validate=lambda x: x))
    monkeypatch.setattr(sink, "read_bronze", lambda *args: records)
    monkeypatch.setattr(sink, "persist_capture", lambda *args, **kwargs: None)
    monkeypatch.setattr(sink, "sink_lock", lambda *args: None)
    monkeypatch.setattr(jobs, "capture_scope", lambda *args: ("bench-batch", None, None))
    monkeypatch.setattr(sink, "observe_sink_batch", lambda *args: None)
    monkeypatch.setattr(
        sink,
        "one",
        lambda tx, statement, values: {"n": 0} if "count(*)" in statement else {"gap": None},
    )
    pipeline = sink.AnalyticsPipeline(
        database.connect,
        None,
        None,
        code_commit="a" * 40,
        sink_batch_max_rows=rows,
    )
    pipeline.recover_observations = lambda *args: None

    def curate(tx, namespace, record, config, replay_id):
        if record.offset == fail_at:
            raise OSError("injected write failure")
        tx.facts.append(record.offset)
        return ("new_valid", None, None)

    pipeline._curate_record = curate
    return pipeline, database, receipt


@pytest.mark.parametrize("rows,expected", [(1, [1] * 205), (100, [100, 100, 5])])
def test_batches_preserve_membership_counts_and_contiguous_offsets(monkeypatch, rows, expected):
    pipeline, database, receipt = pipeline_double(monkeypatch, 205, rows)
    result = pipeline.curate_silver(receipt, {"run_id": "fixture", "sink_batch_max_rows": rows})
    assert result.new_valid == result.source_records == 205
    assert result.durable_offsets_by_partition[0].offset == 205
    assert database.facts == list(range(205))
    assert [batch[7] for batch in database.batches] == expected
    assert [r["offset"] for batch in database.batches for r in batch[6].obj] == list(range(205))
    assert all(batch[8] == batch[7] and batch[9:12] == (0, 0, 0) for batch in database.batches)


@pytest.mark.parametrize("rows,surviving", [(1, [0, 1]), (100, [])])
def test_write_failure_rolls_back_the_complete_current_batch(monkeypatch, rows, surviving):
    pipeline, database, receipt = pipeline_double(monkeypatch, 5, rows, fail_at=2)
    publications = []
    pipeline.after_sink_commit = lambda ns: publications.append(list(database.facts))
    with pytest.raises(OSError, match="injected"):
        pipeline.curate_silver(receipt, {"run_id": "fixture", "sink_batch_max_rows": rows})
    assert database.facts == surviving
    assert len(database.batches) == len(surviving)
    assert len(publications) == len(surviving)


def test_mixed_dispositions_are_audited_in_the_same_transaction(monkeypatch):
    pipeline, database, receipt = pipeline_double(monkeypatch, 100, 100)
    dispositions = ("new_valid", "duplicate_delivery", "invalid", "redelivery_noop")

    def curate(tx, namespace, record, config, replay_id):
        return dispositions[record.offset % 4], None, "INVALID_TYPE"

    pipeline._curate_record = curate
    result = pipeline.curate_silver(receipt, {"run_id": "fixture", "sink_batch_max_rows": 100})
    assert (
        result.new_valid,
        result.duplicate_delivery,
        result.invalid,
        result.redelivery_noop,
    ) == (25, 25, 25, 25)
    assert len(database.batches) == 1 and database.batches[0][7:12] == (100, 25, 25, 25, 25)


@pytest.mark.parametrize("rows", [1, 100])
@pytest.mark.parametrize("fail", [False, True])
def test_ingestion_keeps_capture_controls_and_never_commits_failed_batches(monkeypatch, rows, fail):
    calls = []
    records = [object()]

    class Group:
        topics = ("bench-batch.inventory-events.v1",)

        def consume_records(self, topics, count, wait):
            assert topics == self.topics and (count, wait) == (100, 50)
            return records

        def mark_durable(self, record):
            calls.append("durable")

        def durable_next_offsets(self):
            return ["offset-double"]

        def commit_offsets(self, offsets):
            assert offsets == ["offset-double"]
            calls.append("offset")
            return SimpleNamespace(succeeded=True)

    pipeline = sink.AnalyticsPipeline(
        lambda: None, None, None, code_commit="a" * 40, sink_batch_max_rows=rows
    )
    monkeypatch.setattr(
        sink,
        "BronzeCapture",
        lambda store: SimpleNamespace(ingest_bronze=lambda data: "capture-double"),
    )

    def curate(receipt, config):
        assert receipt == "capture-double" and config["sink_batch_max_rows"] == rows
        if fail:
            raise OSError("injected")
        calls.append("commit")

    pipeline.curate_silver = curate
    if fail:
        with pytest.raises(OSError):
            pipeline.ingest_once(Group(), run_id="fixture")
        assert calls == []
    else:
        pipeline.ingest_once(Group(), run_id="fixture")
        assert calls == ["commit", "durable", "offset"]
