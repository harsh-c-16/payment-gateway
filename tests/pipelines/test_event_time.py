"""Worker scheduling uses an explicit clock double; no live latency claim."""

import pytest

from pipelines.ingestion import worker


def test_provisional_publisher_uses_fixed_ticks_without_waiting_for_watermark(monkeypatch):
    clock = [0.0]
    publications = []
    closed = []

    class GroupDouble:
        def __init__(self, *args):
            pass

        def close(self):
            closed.append(True)

    class PipelineDouble:
        ticks = iter([0.0, 0.26, 0.51])

        def ingest_once(self, *args, **kwargs):
            try:
                clock[0] = next(self.ticks)
            except StopIteration:
                raise RuntimeError("fixture finished") from None

        def publish_snapshot(self, namespace):
            publications.append(clock[0])
            clock[0] += 0.10  # Publishing takes time; the next tick still stays fixed.

    monkeypatch.setattr(worker, "ConsumerGroup", GroupDouble)
    monkeypatch.setattr(worker, "monotonic", lambda: clock[0])
    with pytest.raises(RuntimeError, match="fixture finished"):
        worker.run(PipelineDouble(), "bench-m09", "explicit-fixture", "unused")
    assert publications == [0.0, 0.26, 0.51]
    assert closed == [True]
