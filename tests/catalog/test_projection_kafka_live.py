"""T-09 through a real Kafka broker. Skipped unless a broker is supplied, so a skip is NOT_RUN.

CATALOG_TEST_KAFKA_BOOTSTRAP=127.0.0.1:9092 with the streaming-local profile running.
"""

import os
import subprocess
import sys
from threading import Event, Thread
from time import monotonic, sleep
from uuid import uuid4

import pytest
from confluent_kafka import Consumer, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic

from services.catalog import worker
from shared.event_transport import ConsumerGroup, KafkaPublisher
from shared.event_transport.codec import EventCodec
from shared.local_diagnostics import quarantine_local_diagnostic
from tests.catalog.helpers import import_rows, row
from tests.pipelines.transport_doubles import offline_cache

BOOTSTRAP = os.environ.get("CATALOG_TEST_KAFKA_BOOTSTRAP")
pytestmark = pytest.mark.skipif(not BOOTSTRAP, reason="NOT_RUN: no real Kafka broker supplied")
CODEC = EventCodec(offline_cache(), source_service="inventory")


def snapshot(namespace, sku, version, on_hand, reserved):
    now = "2026-11-02T10:00:00Z"
    return CODEC.build_event(
        event_type="STOCK_UPDATED",
        payload={
            "sku": sku,
            "on_hand": on_hand,
            "reserved": reserved,
            "available": on_hand - reserved,
            "stock_version": version,
            "changed_at": now,
            "order_id": None,
            "reservation_id": None,
            "reason_code": None,
        },
        context={
            "namespace": namespace,
            "run_id": str(uuid4()),
            "correlation_id": str(uuid4()),
            "session_id": None,
            "user_id": None,
        },
        aggregate_type="sku",
        aggregate_id=sku,
        aggregate_version=version,
        event_time=now,
        metadata={"dataset_revision": "rev", "synthetic": True, "scenario_source": "simulation"},
        source_service="inventory",
    )


def consume_until(db, namespace, wanted):
    """Runs the real consumer until the stored version reaches wanted, then stops it."""
    stop = Event()
    group = {}

    def body():
        group["handle"] = ConsumerGroup(
            f"{namespace}.catalog-projection.v1", [worker.topic_for(namespace)], BOOTSTRAP
        )
        worker.run(
            db,
            group["handle"],
            namespace,
            stop=stop,
            run_id="kafka-live",
            validate=CODEC.validate_event,
            diagnostics=quarantine_local_diagnostic,
        )

    thread = Thread(target=body)
    thread.start()
    deadline = monotonic() + 60
    try:
        while monotonic() < deadline:
            with db.transaction() as tx:
                current = tx.execute(
                    "SELECT stock_version FROM stock_projection WHERE namespace=%s", (namespace,)
                ).fetchone()
            if current and current["stock_version"] >= wanted:
                # Leave time for the contiguous offset commit before stopping.
                sleep(2)
                return current["stock_version"]
            sleep(0.1)
    finally:
        stop.set()
        thread.join(30)
    raise AssertionError("projection did not reach the wanted version before the deadline")


def test_real_broker_order_redelivery_and_restart(tmp_path, database_url, db):
    namespace = "bench-h-" + uuid4().hex[:16]
    import_rows(tmp_path, database_url, namespace, [row("A1")])
    topic = worker.topic_for(namespace)
    admin = AdminClient({"bootstrap.servers": BOOTSTRAP})
    admin.create_topics([NewTopic(topic, num_partitions=1, replication_factor=1)])[topic].result(30)
    publisher = KafkaPublisher(CODEC, BOOTSTRAP)
    newest = snapshot(namespace, "FK-A1", 3, 10, 3)
    try:
        for event in (
            snapshot(namespace, "FK-A1", 1, 10, 0),
            newest,
            snapshot(namespace, "FK-A1", 2, 10, 2),
            newest,
        ):
            publisher.publish_event(event, topic, "FK-A1")
        assert consume_until(db, namespace, 3) == 3
        with db.transaction() as tx:
            outcomes = tx.execute(
                'SELECT outcome FROM projection_receipts WHERE namespace=%s ORDER BY "offset"',
                (namespace,),
            ).fetchall()
        assert [r["outcome"] for r in outcomes] == ["applied", "applied", "stale", "duplicate"]
        # A restart in the same group resumes after the committed offsets: nothing reapplies.
        publisher.publish_event(snapshot(namespace, "FK-A1", 4, 9, 0), topic, "FK-A1")
        assert consume_until(db, namespace, 4) == 4
        with db.transaction() as tx:
            count = tx.execute(
                "SELECT count(*) AS n FROM projection_receipts WHERE namespace=%s", (namespace,)
            ).fetchone()["n"]
        assert count == 5
    finally:
        publisher.close()


def prepare(tmp_path, database_url, partitions=1):
    namespace = "bench-h-" + uuid4().hex[:16]
    import_rows(tmp_path, database_url, namespace, [row("A1")])
    topic = worker.topic_for(namespace)
    admin = AdminClient({"bootstrap.servers": BOOTSTRAP})
    admin.create_topics([NewTopic(topic, num_partitions=partitions, replication_factor=1)])[
        topic
    ].result(30)
    return namespace, topic


def apply_available(group, db):
    records = group.consume_records(group.topics, 100, 50)
    worker.process_batch(
        db,
        records,
        validate=CODEC.validate_event,
        diagnostics=quarantine_local_diagnostic,
        run_id="kafka-fault",
        metrics=worker.telemetry(),
        mark=group.mark_durable,
    )
    assert group.commit_offsets(group.durable_next_offsets()).succeeded
    return records


def wait_until(predicate, poll, seconds=60):
    deadline = monotonic() + seconds
    while monotonic() < deadline:
        poll()
        if predicate():
            return
    raise AssertionError("Real broker boundary was not observed before the deadline")


def test_real_broker_conflicting_version_keeps_stock_and_durable_diagnostic(
    tmp_path,
    database_url,
    db,
):
    namespace, topic = prepare(tmp_path, database_url)
    group = worker.open_group(namespace, BOOTSTRAP)
    publisher = KafkaPublisher(CODEC, BOOTSTRAP)
    records = []
    try:
        for event in (
            snapshot(namespace, "FK-A1", 3, 10, 3),
            snapshot(namespace, "FK-A1", 3, 10, 4),
        ):
            publisher.publish_event(event, topic, "FK-A1")
        wait_until(lambda: len(records) == 2, lambda: records.extend(apply_available(group, db)))
        with db.transaction() as tx:
            stock = tx.execute(
                "SELECT stock_version,reserved FROM stock_projection WHERE namespace=%s",
                (namespace,),
            ).fetchone()
            outcomes = tx.execute(
                'SELECT outcome FROM projection_receipts WHERE namespace=%s ORDER BY "offset"',
                (namespace,),
            ).fetchall()
            notices = tx.execute(
                "SELECT count(*) AS n FROM outbox WHERE namespace=%s", (namespace,)
            ).fetchone()
        assert stock == {"stock_version": 3, "reserved": 3}
        assert [r["outcome"] for r in outcomes] == ["applied", "conflict"]
        assert notices["n"] == 1
    finally:
        group.close()
        publisher.close()


def test_real_broker_process_death_before_offset_commit_replays_without_second_effect(
    tmp_path,
    database_url,
    db,
):
    namespace, topic = prepare(tmp_path, database_url)
    publisher = KafkaPublisher(CODEC, BOOTSTRAP)
    try:
        publisher.publish_event(snapshot(namespace, "FK-A1", 1, 10, 0), topic, "FK-A1")
    finally:
        publisher.close()
    child = subprocess.run(
        [sys.executable, "-m", "tests.catalog.projection_crash"],
        env={
            **os.environ,
            "CATALOG_TEST_DATABASE_URL": database_url,
            "PROJECTION_CRASH_NAMESPACE": namespace,
        },
        capture_output=True,
        timeout=80,
        **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}),
    )
    assert child.returncode == 91, "Child did not reach the actual after-SQL crash boundary"
    observer = Consumer(
        {"bootstrap.servers": BOOTSTRAP, "group.id": namespace + ".catalog-projection.v1"}
    )
    try:
        assert observer.committed([TopicPartition(topic, 0)], timeout=10)[0].offset < 1
    finally:
        observer.close()
    with db.transaction() as tx:
        assert (
            tx.execute(
                "SELECT stock_version FROM stock_projection WHERE namespace=%s", (namespace,)
            ).fetchone()["stock_version"]
            == 1
        )
    group = worker.open_group(namespace, BOOTSTRAP)
    replay = []
    try:
        wait_until(lambda: len(replay) == 1, lambda: replay.extend(apply_available(group, db)))
        assert replay[0].offset == 0
        with db.transaction() as tx:
            assert (
                tx.execute(
                    "SELECT count(*) AS n FROM projection_receipts WHERE namespace=%s", (namespace,)
                ).fetchone()["n"]
                == 1
            )
            assert (
                tx.execute(
                    "SELECT stock_version FROM stock_projection WHERE namespace=%s", (namespace,)
                ).fetchone()["stock_version"]
                == 1
            )
    finally:
        group.close()


def test_real_broker_rebalance_transfers_partitions_and_preserves_projection(
    tmp_path,
    database_url,
    db,
):
    namespace, topic = prepare(tmp_path, database_url, partitions=3)
    first = ConsumerGroup(
        namespace + ".catalog-projection.v1", [topic], BOOTSTRAP, workers=3, worker_index=0
    )
    second = None
    publisher = KafkaPublisher(CODEC, BOOTSTRAP)
    records = []
    try:
        publisher.publish_event(snapshot(namespace, "FK-A1", 1, 10, 0), topic, "FK-A1")
        wait_until(
            lambda: len(first.assignments) == 3 and len(records) == 1,
            lambda: records.extend(apply_available(first, db)),
        )
        epoch = first.epoch
        second = ConsumerGroup(
            namespace + ".catalog-projection.v1", [topic], BOOTSTRAP, workers=3, worker_index=1
        )

        def poll():
            for member in (first, second):
                records.extend(apply_available(member, db))

        wait_until(lambda: first.epoch > epoch and bool(second.assignments), poll)
        assert not set(first.assignments) & set(second.assignments)
        assert set(first.assignments) | set(second.assignments) == {(topic, p) for p in range(3)}
        publisher.publish_event(snapshot(namespace, "FK-A1", 2, 9, 0), topic, "FK-A1")
        wait_until(lambda: len(records) == 2, poll)
        second.close()
        second = None
        wait_until(lambda: len(first.assignments) == 3, lambda: apply_available(first, db))
        with db.transaction() as tx:
            assert (
                tx.execute(
                    "SELECT stock_version FROM stock_projection WHERE namespace=%s", (namespace,)
                ).fetchone()["stock_version"]
                == 2
            )
            assert (
                tx.execute(
                    "SELECT count(*) AS n FROM projection_receipts WHERE namespace=%s", (namespace,)
                ).fetchone()["n"]
                == 2
            )
    finally:
        if second is not None:
            second.close()
        first.close()
        publisher.close()
