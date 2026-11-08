"""Opt-in test child: actual process death after SQL COMMIT, before mark/offset COMMIT."""

import os
from time import monotonic

from services.catalog import worker
from services.catalog.database import Database
from shared.event_transport import ConsumerGroup
from shared.event_transport.codec import EventCodec
from shared.local_diagnostics import quarantine_local_diagnostic
from tests.pipelines.transport_doubles import offline_cache


def main():
    namespace = os.environ["PROJECTION_CRASH_NAMESPACE"]
    group = ConsumerGroup(
        namespace + ".catalog-projection.v1",
        [worker.topic_for(namespace)],
        os.environ["CATALOG_TEST_KAFKA_BOOTSTRAP"],
    )
    codec = EventCodec(offline_cache(), source_service="inventory")
    deadline = monotonic() + 60
    try:
        while monotonic() < deadline:
            records = group.consume_records(group.topics, 1, 50)
            if records:
                worker.process_batch(
                    Database(os.environ["CATALOG_TEST_DATABASE_URL"]),
                    records,
                    validate=codec.validate_event,
                    diagnostics=quarantine_local_diagnostic,
                    run_id="crash-before-offset",
                    metrics=worker.telemetry(),
                    mark=lambda record: os._exit(91),
                )
        raise TimeoutError("No source reached the crash boundary")
    finally:
        group.close()


if __name__ == "__main__":
    main()
