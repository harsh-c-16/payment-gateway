import asyncio
import json
import threading
from concurrent.futures import Future
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from benchmarks.collectors import (
    CgroupV2Reader,
    GoldVisibilityReader,
    KafkaLagReader,
    PrometheusReader,
    SelfResourceReader,
    collector,
)
from benchmarks.observation import ObservationConfig, ObservationSession, Series
from benchmarks.observation_summary import rebuild


def test_actual_http_metrics_scrape_does_not_invent_absent_metrics():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'outbox_pending{service="orders"} 7\n')

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    present = Series("outbox_pending", "orders", "rows", (("service", "orders"),))
    missing = Series("gold_pending_events", "gold", "events")
    try:
        reader = PrometheusReader(
            f"http://127.0.0.1:{server.server_port}/metrics", (present, missing)
        )
        result = asyncio.run(reader(0))
        assert result[present.key].value == 7 and missing.key not in result
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_actual_generator_process_collector_has_real_cpu_and_rss(tmp_path):
    reader = SelfResourceReader(allocated_cores=1)
    cfg = ObservationConfig(
        tmp_path,
        "real-process-smoke",
        "bench-test",
        "W-PIPE",
        "B0",
        (collector("generator", reader),),
        evidence_kind="test",
        interval_seconds=0.02,
        timeout_seconds=0.01,
        duration_seconds=0.061,
    )

    async def run():
        async with ObservationSession(cfg) as session:
            await session.task

    asyncio.run(run())
    summary = rebuild(tmp_path)
    assert summary["context"]["mode"] == "real"
    cpu, memory = summary["series"]
    assert cpu["sample_count"] == 4 and cpu["mean_cpu_percent"] is not None
    assert memory["peak"] > 0 and memory["missing_samples"] == 0


def completed(value):
    future = Future()
    future.set_result(value)
    return future


def test_kafka_admin_double_retains_raw_offsets_and_unknown_partition():
    from confluent_kafka import TopicPartition

    class AdminDouble:
        def list_consumer_group_offsets(self, request, **kwargs):
            assert kwargs["request_timeout"] == 0.3
            return {
                "test": completed(
                    SimpleNamespace(
                        topic_partitions=[
                            TopicPartition("test-topic", 0, 40),
                            TopicPartition("test-topic", 1, -1001),
                        ]
                    )
                )
            }

        def list_offsets(self, request, **kwargs):
            return {tp: completed(SimpleNamespace(offset=42)) for tp in request}

    reader = KafkaLagReader(AdminDouble(), "test", (("test-topic", 0), ("test-topic", 1)))
    result = asyncio.run(reader(0))
    assert result[reader.series[0].key].value == 2
    assert result[reader.series[0].key].details["committed_next_offset"] == 40
    assert reader.series[1].key not in result


def test_cgroup_file_fixture_keeps_accounting_and_missing_peak_separate(tmp_path):
    (tmp_path / "cpu.stat").write_text("usage_usec 1000000\nuser_usec 700000\n")
    (tmp_path / "memory.current").write_text("123456\n")
    reader = CgroupV2Reader(tmp_path, "fixture-worker", allocated_cores=2)
    result = asyncio.run(reader(0))
    assert result[reader.series[0].key].value == 1
    assert result[reader.series[1].key].value == 123456
    assert reader.series[2].key not in result


def snapshot(**updates):
    return dict(
        namespace="bench-test",
        generation=1,
        query_generation=1,
        manifest_sha256="a" * 64,
        query_manifest_sha256="a" * 64,
        membership_ids=["event-1"],
        **updates,
    )


def test_gold_collects_unique_active_membership_and_generation_evidence(tmp_path):
    async def read():
        return snapshot()

    reader = GoldVisibilityReader(read, tmp_path, "bench-test", mode="stub")
    asyncio.run(reader(0))
    asyncio.run(reader(1))
    visibility = [
        json.loads(line) for line in (tmp_path / "gold_visibility.jsonl").read_text().splitlines()
    ]
    assert len(visibility) == 1 and visibility[0]["generation"] == 1
    assert visibility[0]["observation_is_upper_bound"] is True
    assert (tmp_path / visibility[0]["membership_evidence"]).is_file()


@pytest.mark.parametrize(
    "change",
    [
        {"namespace": "dev"},
        {"query_generation": 2},
        {"query_manifest_sha256": "b" * 64},
        {"manifest_sha256": "not-a-hash"},
        {"membership_ids": ["event-1", "event-1"]},
    ],
)
def test_unpinned_or_invalid_gold_snapshot_never_becomes_visibility(tmp_path, change):
    async def read():
        return snapshot() | change

    reader = GoldVisibilityReader(read, tmp_path, "bench-test", mode="stub")
    with pytest.raises(ValueError):
        asyncio.run(reader(0))
    assert not (tmp_path / "gold_visibility.jsonl").exists()
    assert (tmp_path / "manifests/gold-audit-000000.json").is_file()


def test_same_gold_generation_cannot_change_hash(tmp_path):
    current = snapshot()

    async def read():
        return current

    reader = GoldVisibilityReader(read, tmp_path, "bench-test", mode="stub")
    asyncio.run(reader(0))
    current.update(manifest_sha256="b" * 64, query_manifest_sha256="b" * 64)
    with pytest.raises(ValueError):
        asyncio.run(reader(1))


def test_same_active_manifest_cannot_gain_unpublished_members(tmp_path):
    current = snapshot()

    async def read():
        return current

    reader = GoldVisibilityReader(read, tmp_path, "bench-test", mode="stub")
    asyncio.run(reader(0))
    current["membership_ids"] = ["event-1", "unpublished-event"]
    with pytest.raises(ValueError):
        asyncio.run(reader(1))
    assert "unpublished-event" not in (tmp_path / "gold_visibility.jsonl").read_text()
