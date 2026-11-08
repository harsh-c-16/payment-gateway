"""Bounded B0/O1 worker; failed, uncommitted sources redeliver after restart."""

import json
import logging
import os
from contextlib import nullcontext
from time import monotonic, sleep

import psycopg
from prometheus_client import start_http_server
from pydantic import TypeAdapter

from shared.contracts.common import Identifier
from shared.contracts.events import EVENTS, Namespace
from shared.event_transport.consumer import ConsumerGroup

from .notifications import notification_relay
from .runtime import pipeline_from_env, worker_allocation


def log_buffer(group, run_id, *, final=False):
    started = monotonic()
    sample = group.buffer_snapshot()
    logging.getLogger(__name__).info(
        json.dumps(
            {
                **sample,
                "schema_version": 1,
                "timestamp": sample["observed_at"],
                "service": "analytics-worker",
                "operation": "consumer_buffer",
                "run_id": run_id,
                "correlation_id": run_id,
                "event_id": None,
                "resource_id": sample.get("group_id"),
                "outcome": "final" if final else "observed",
                "duration_seconds": monotonic() - started,
                "clock_domain": "worker_monotonic",
            },
            allow_nan=False,
        )
    )


def run(pipeline, namespace, run_id, bootstrap):
    TypeAdapter(Namespace).validate_python(namespace)
    TypeAdapter(Identifier).validate_python(run_id)
    workers, worker_index = worker_allocation()
    for attempt in range(4):
        group = ConsumerGroup(
            namespace + ".analytics.v1",
            [f"{namespace}.{domain}.v1" for domain in sorted({e[0] for e in EVENTS.values()})],
            bootstrap,
            workers=workers,
            worker_index=worker_index,
        )
        deadline = monotonic()
        observation_deadline = monotonic()

        def publish_if_due(current_namespace):
            nonlocal deadline
            if current_namespace != namespace:
                raise ValueError("Worker publication scope changed")
            if worker_index == 0 and monotonic() >= deadline:
                try:
                    pipeline.publish_snapshot(namespace)
                except LookupError:
                    pass  # No first publication exists while the source is idle.
                deadline += max(1, int((monotonic() - deadline) / 0.250) + 1) * 0.250

        # B0 checks cadence after each SQL commit, even within a shared raw capture.
        # shortcut: worker zero also publishes; split roles before consumer-only pause measurements.
        pipeline.after_sink_commit = publish_if_due if worker_index == 0 else None
        try:
            while True:
                # Identical capture count/wait controls for B0 and O1; only SQL grouping changes.
                pipeline.ingest_once(group, run_id=run_id, max_records=100)
                now = monotonic()
                if now >= observation_deadline:
                    log_buffer(group, run_id)
                    observation_deadline += max(1, int(now - observation_deadline) + 1)
                publish_if_due(namespace)
        except (
            psycopg.OperationalError,
            psycopg.errors.DeadlockDetected,
            psycopg.errors.SerializationFailure,
            OSError,
        ) as exc:
            if attempt == 3:
                raise
            logging.getLogger(__name__).warning(
                "Analytics retry %s: %s", attempt + 1, type(exc).__name__
            )
        finally:
            pipeline.after_sink_commit = None
            try:
                log_buffer(group, run_id, final=True)
            finally:
                group.close()
        # Rejoin from committed offsets; never continue a group with unfinished in-flight records.
        sleep(0.250 * 2**attempt)


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    pipeline = pipeline_from_env()
    server, thread = start_http_server(8006, addr="0.0.0.0", registry=pipeline.telemetry.registry)
    try:
        bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
        with (
            notification_relay(pipeline, bootstrap)
            if worker_allocation()[1] == 0
            else nullcontext()
        ):
            run(pipeline, os.environ["RUN_NAMESPACE"], os.environ["RUN_ID"], bootstrap)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    main()
