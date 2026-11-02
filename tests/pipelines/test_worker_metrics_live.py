"""Real worker process + HTTP/Kafka/PostgreSQL/Parquet; no outbox or workload double."""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from time import monotonic, sleep

from confluent_kafka import Consumer, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic
from prometheus_client.parser import text_string_to_metric_families

from pipelines.curation.sink_observations import read_sink_batches
from shared.contracts.events import EVENTS
from shared.event_transport.publisher import KafkaPublisher

from . import test_vertical_live as live
from .test_vertical_live import event, query

vertical = live.vertical
pytestmark = live.pytestmark


def samples(text):
    return {
        (s.name, tuple(sorted(s.labels.items()))): s.value
        for family in text_string_to_metric_families(text)
        for s in family.samples
    }


def scrape():
    with urllib.request.urlopen("http://127.0.0.1:8006/metrics", timeout=2) as response:
        assert response.status == 200
        assert "text/plain" in response.headers["Content-Type"]
        return response.read().decode()


def test_real_worker_exports_committed_sink_and_published_gold_metrics(vertical):
    namespace, bootstrap = vertical.test_namespace, os.environ["KAFKA_BOOTSTRAP_SERVERS"]
    topics = [f"{namespace}.{domain}.v1" for domain in sorted({e[0] for e in EVENTS.values()})]
    admin = AdminClient({"bootstrap.servers": bootstrap})
    for future in admin.create_topics(
        [NewTopic(topic, 1, 1, config={"retention.ms": "604800000"}) for topic in topics]
    ).values():
        future.result(30)
    log_path = Path("artifacts/m11-worker/worker.log")
    with log_path.open("w") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "tests.pipelines.worker_metrics_process",
                str(vertical.store.root),
                namespace,
                vertical.store.root.name,
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = monotonic() + 40
            while True:
                assert process.poll() is None, log_path.read_text()
                try:
                    before = scrape()
                    break
                except urllib.error.URLError:
                    assert monotonic() < deadline, "worker listener did not start"
                    sleep(0.1)
            assert "sink_batch_rows_count" not in before and "source_records_total" not in before
            publisher = KafkaPublisher(vertical.codec, bootstrap)
            fact = event(vertical)
            topic = namespace + ".conversation-events.v1"
            try:
                for _ in range(2):
                    publisher.publish_event(fact, topic, fact.kafka_key())
            finally:
                publisher.close()
            deadline = monotonic() + 40
            while True:
                assert process.poll() is None, log_path.read_text()
                text = scrape()
                observed = samples(text)
                if (
                    observed.get(("sink_batch_rows_count", ())) == 2
                    and observed.get(("sink_flush_duration_seconds_count", ())) == 2
                    and observed.get(("gold_pending_events", ())) == 0
                    and observed.get(("gold_generation", ())) == 1
                    and observed.get(("gold_publication_duration_seconds_count", ()), 0) >= 1
                ):
                    break
                assert monotonic() < deadline, text
                sleep(0.1)
            for disposition in ("new_valid", "duplicate_delivery"):
                labels = tuple(sorted(dict(pipeline="analytics", disposition=disposition).items()))
                assert observed[("source_records_total", labels)] == 1
            assert observed[("silver_unique_total", ())] == 1
            assert observed[("sink_batch_rows_sum", ())] == 2
            assert observed[("sink_flush_duration_seconds_count", ())] == 2
            assert observed[("sink_flush_duration_seconds_sum", ())] >= 0
            assert observed[("gold_generation", ())] == 1
            assert observed[("gold_publication_duration_seconds_count", ())] >= 1
            assert query(vertical).rows[0]["unique_events"] == 1
            batches = read_sink_batches(vertical.connect, namespace, "m11-worker-real-fixture")
            assert len(batches) == 2 and all(b["timing_validity"] == "observed" for b in batches)
            assert (
                sum(b["new_valid"] for b in batches)
                == sum(b["duplicate_delivery"] for b in batches)
                == 1
            )
            assert b"sink_batch_rows_count" not in vertical.telemetry.exposition()
            observer = Consumer(
                {"bootstrap.servers": bootstrap, "group.id": namespace + ".analytics.v1"}
            )
            try:
                deadline = monotonic() + 10
                while True:
                    committed = observer.committed([TopicPartition(topic, 0)], timeout=2)[0].offset
                    if committed == 2:
                        break
                    assert monotonic() < deadline, f"committed next offset is {committed}"
                    sleep(0.1)
            finally:
                observer.close()
            assert committed == 2
            Path("artifacts/m11-worker/worker-metrics.txt").write_text(text)
            Path("artifacts/m11-worker/worker-proof.json").write_text(
                json.dumps(
                    {
                        "source_commit": vertical.code_commit,
                        "namespace": namespace,
                        "worker_pid": process.pid,
                        "transport": "real HTTP",
                        "pipeline": "real Kafka/PostgreSQL/Parquet",
                        "source_records": 2,
                        "sink_transactions": 2,
                        "silver_unique": 1,
                        "gold_unique": 1,
                        "broker_committed_next_offset": committed,
                        "separate_parent_registry_has_no_worker_histogram": True,
                        "performance": "NOT_RUN; correctness observation only",
                    },
                    indent=2,
                )
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
