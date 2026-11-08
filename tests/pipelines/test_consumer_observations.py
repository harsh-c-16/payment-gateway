"""Buffer accounting with explicit Kafka/clock doubles; no broker-capacity claim."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from itertools import count

import pytest
from confluent_kafka import TopicPartition

import shared.event_transport.consumer as consumer
from pipelines.ingestion import worker

from .transport_doubles import ConsumerDouble, MessageDouble

TOPIC = "bench-buffer.conversation-events.v1"


def group(**kwargs):
    return consumer.ConsumerGroup(
        "bench-buffer.analytics.v1",
        [TOPIC],
        "explicit-double",
        consumer_factory=ConsumerDouble,
        **kwargs,
    )


def test_snapshot_is_read_only_and_counts_until_commit_or_revoke(monkeypatch):
    # Buffer accounting must not depend on the host scheduling two polls within 10 ms.
    ticks = count(step=0.001)
    monkeypatch.setattr(consumer, "monotonic", lambda: next(ticks))
    current = group()
    try:
        initial = current.buffer_snapshot()
        assert initial["pending_records"] == initial["pending_raw_bytes"] == 0
        assert initial["record_limit"] == 2000
        assert initial["application_byte_limit"] == 8 * 1024 * 1024
        current.consumer.messages.extend(MessageDouble(TOPIC, n) for n in range(2))
        records = current.consume_records([TOPIC], 2, 10)
        before = current.consumer.polls
        sample = current.buffer_snapshot()
        assert sample["pending_records"] == sample["peak_pending_records"] == 2
        assert sample["ready_records"] == 0
        assert sample["pending_raw_bytes"] == sum(consumer.record_size(r) for r in records)
        assert current.consumer.polls == before and not current.consumer.commits
        current.mark_durable(records[0])
        assert current.buffer_snapshot()["pending_records"] == 2
        assert current.commit_offsets(current.durable_next_offsets()).succeeded
        assert current.buffer_snapshot()["pending_records"] == 1
        current._on_lost(current.consumer, [TopicPartition(TOPIC, 0)])
        sample = current.buffer_snapshot()
        assert sample["pending_records"] == sample["pending_raw_bytes"] == 0
        assert sample["peak_pending_records"] == 2 and sample["peak_pending_raw_bytes"] > 0
        assert sample["consumer_instance"] == initial["consumer_instance"]
        assert sample["observed_at"].endswith("Z")
        json.dumps(sample, allow_nan=False)
    finally:
        current.close()
    with pytest.raises(RuntimeError, match="closed"):
        current.buffer_snapshot()


def test_snapshot_requires_the_consumer_owner_thread():
    current = group()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            with pytest.raises(RuntimeError, match="another worker thread"):
                pool.submit(current.buffer_snapshot).result()
    finally:
        current.close()


def test_snapshot_retains_pause_and_peak_after_drain(monkeypatch):
    ticks = count(step=0.001)
    monkeypatch.setattr(consumer, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(consumer, "GROUP_MAX_RECORDS", 3)
    current = group()
    try:
        current.consumer.messages.extend(MessageDouble(TOPIC, n) for n in range(3))
        records = current.consume_records([TOPIC], 3, 10)
        sample = current.buffer_snapshot()
        assert (
            sample["pending_records"] == 2 and sample["pause_required"] and sample["fetch_paused"]
        )
        assert sample["pause_count"] == 1 and sample["overflow_rejections"] == 0
        for record in records:
            current.mark_durable(record)
        assert current.commit_offsets(current.durable_next_offsets()).succeeded
        last = current.consume_records([TOPIC], 1, 10)[0]
        current.mark_durable(last)
        assert current.commit_offsets(current.durable_next_offsets()).succeeded
        sample = current.buffer_snapshot()
        assert sample["pending_records"] == 0 and not sample["fetch_paused"]
        assert sample["peak_pending_records"] == 2 and sample["pause_count"] == 1
    finally:
        current.close()


def test_oversize_rejection_is_observed_without_fabricating_a_buffered_record():
    current = group()
    try:
        current.consumer.messages.append(MessageDouble(TOPIC, 0, value=b"x" * (1024 * 1024 + 1)))
        with pytest.raises(consumer.ConsumerBufferError):
            current.consume_records([TOPIC], 1, 10)
        sample = current.buffer_snapshot()
        assert sample["overflow_rejections"] == sample["pause_count"] == 1
        assert sample["pending_records"] == sample["peak_pending_records"] == 0
        assert sample["fetch_paused"] and not current.consumer.commits
    finally:
        current.close()


def test_three_worker_observations_preserve_the_group_budget():
    workers = [group(workers=3, worker_index=i) for i in range(3)]
    try:
        samples = [w.buffer_snapshot() for w in workers]
        assert sum(s["record_limit"] for s in samples) == 2000
        assert sum(s["worker_raw_byte_budget"] for s in samples) == 16 * 1024 * 1024
        assert [s["worker_index"] for s in samples] == [0, 1, 2]
        assert all(s["workers"] == 3 for s in samples)
    finally:
        for current in workers:
            current.close()


def test_worker_samples_fixed_ticks_and_final_state_without_inventing_missed_ticks(
    monkeypatch, caplog
):
    clock = [0.0]
    closed = []

    class GroupDouble:
        def __init__(self, *args, **kwargs):
            pass

        def buffer_snapshot(self):
            return {
                "namespace": "bench-buffer",
                "observed_fixture_clock": clock[0],
                "observed_at": "2026-11-02T00:00:00Z",
            }

        def close(self):
            closed.append(True)

    class PipelineDouble:
        ticks = iter([0.0, 0.26, 1.01, 3.2])

        def ingest_once(self, *args, **kwargs):
            try:
                clock[0] = next(self.ticks)
            except StopIteration:
                raise RuntimeError("explicit fixture done") from None

        def publish_snapshot(self, namespace):
            pass

    monkeypatch.setattr(worker, "ConsumerGroup", GroupDouble)
    monkeypatch.setattr(worker, "monotonic", lambda: clock[0])
    caplog.set_level(logging.INFO, logger=worker.__name__)
    with pytest.raises(RuntimeError, match="fixture done"):
        worker.run(PipelineDouble(), "bench-buffer", "explicit-fixture", "unused-double")
    samples = [json.loads(r.message) for r in caplog.records]
    assert [s["observed_fixture_clock"] for s in samples] == [0.0, 1.01, 3.2, 3.2]
    assert [s["outcome"] for s in samples] == ["observed"] * 3 + ["final"]
    assert all(s["run_id"] == "explicit-fixture" for s in samples) and closed == [True]
