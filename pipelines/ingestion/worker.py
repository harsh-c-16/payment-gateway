"""All-domain B0 worker; failed, uncommitted sources redeliver after restart."""

import logging
import os
from time import monotonic, sleep

import psycopg
from pydantic import TypeAdapter

from shared.contracts.common import Identifier
from shared.contracts.events import EVENTS, Namespace
from shared.event_transport.consumer import ConsumerGroup

from .runtime import pipeline_from_env


def run(pipeline, namespace, run_id, bootstrap):
    TypeAdapter(Namespace).validate_python(namespace)
    TypeAdapter(Identifier).validate_python(run_id)
    for attempt in range(4):
        group = ConsumerGroup(
            namespace + ".analytics.v1",
            [f"{namespace}.{domain}.v1" for domain in sorted({e[0] for e in EVENTS.values()})],
            bootstrap,
        )
        deadline = monotonic()
        try:
            while True:
                pipeline.ingest_once(group, run_id=run_id, max_records=1)
                if monotonic() >= deadline:
                    try:
                        pipeline.publish_snapshot(namespace)
                    except LookupError:
                        pass  # No first publication exists while the source is idle.
                    # Keep the fixed cadence; skip missed ticks when publication is slow.
                    deadline += max(1, int((monotonic() - deadline) / 0.250) + 1) * 0.250
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
            group.close()
        # Rejoin from committed offsets; never continue a group with unfinished in-flight records.
        sleep(0.250 * 2**attempt)


def main():
    run(
        pipeline_from_env(),
        os.environ["RUN_NAMESPACE"],
        os.environ["RUN_ID"],
        os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
    )


if __name__ == "__main__":
    main()
