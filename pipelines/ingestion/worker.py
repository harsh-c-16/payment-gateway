"""M05 B0 worker; exit on failure so uncommitted sources redeliver after restart."""

import os
from time import monotonic

from pydantic import TypeAdapter

from shared.contracts.common import Identifier
from shared.contracts.events import Namespace
from shared.event_transport.consumer import ConsumerGroup

from .runtime import pipeline_from_env


def run(pipeline, namespace, run_id, bootstrap):
    TypeAdapter(Namespace).validate_python(namespace)
    TypeAdapter(Identifier).validate_python(run_id)
    group = ConsumerGroup(
        namespace + ".analytics.v1", [namespace + ".conversation-events.v1"], bootstrap
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
                deadline = monotonic() + 0.250
    finally:
        group.close()


def main():
    run(
        pipeline_from_env(),
        os.environ["RUN_NAMESPACE"],
        os.environ["RUN_ID"],
        os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
    )


if __name__ == "__main__":
    main()
