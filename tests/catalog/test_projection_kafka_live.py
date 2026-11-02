"""T-09 through a real Kafka broker. Skipped unless a broker is supplied, so a skip is NOT_RUN.

CATALOG_TEST_KAFKA_BOOTSTRAP=127.0.0.1:9092 with the streaming-local profile running.
"""

import os
from threading import Event, Thread
from time import monotonic, sleep
from uuid import uuid4

import pytest
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


def test_real_broker_order_redelivery_and_restart(tmp_path, database_url, db, outbox_double):
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
