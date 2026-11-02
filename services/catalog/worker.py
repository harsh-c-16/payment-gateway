"""Long-running stock consumer in its own group, independent of the analytics group."""

import argparse
import logging
import os
from datetime import UTC, datetime
from threading import Event
from time import monotonic

from prometheus_client import start_http_server

from services.catalog import projection
from services.catalog.database import Database
from shared.contracts.events import ValidationFailure
from shared.event_transport import (
    ConsumerGroup,
    commit_offsets,
    configure_transport,
    consume_records,
    validate_event,
)
from shared.local_diagnostics import quarantine_local_diagnostic
from shared.telemetry.metrics import Telemetry

LOGGER = logging.getLogger("catalog.projection")
OUTCOMES = {"applied", "duplicate", "stale", "conflict", "deferred", "invalid"}


def telemetry():
    return Telemetry(label_values={"outcome": OUTCOMES})


def topic_for(namespace):
    return f"{namespace}.inventory-events.v1"


def process_batch(db, records, *, validate, diagnostics, run_id, metrics, mark):
    """Each record commits before it is marked durable, so a crash only causes redelivery."""
    for record in records:
        checked = validate(
            record.value_bytes,
            record.headers,
            record.topic,
            record.key_bytes,
            source_record=record,
        )
        with db.transaction() as tx:
            if isinstance(checked, ValidationFailure):
                projection.reject_record(
                    tx, checked, record, diagnostics=diagnostics, run_id=run_id
                )
                outcome = "invalid"
            else:
                outcome = projection.apply_stock_event(
                    tx, checked, record, diagnostics=diagnostics
                ).outcome
        metrics.record("projection_apply_total", 1, outcome=outcome)
        if outcome == "applied":
            age = (datetime.now(UTC) - checked.envelope.produced_at).total_seconds()
            metrics.record("projection_age_seconds", max(age, 0.0))
        mark(record)
    if records:
        namespace = records[0].source_namespace
        with db.transaction() as tx:
            projection.mark_observed(tx, namespace, records)


def run(
    db,
    group,
    namespace,
    *,
    stop,
    run_id,
    metrics=None,
    validate=validate_event,
    diagnostics=quarantine_local_diagnostic,
    batch=100,
    reconcile_every=5.0,
):
    metrics = metrics or telemetry()
    last_reconcile = 0.0
    try:
        while not stop.is_set():
            records = consume_records(group, group.topics, batch, 50)
            process_batch(
                db,
                records,
                validate=validate,
                diagnostics=diagnostics,
                run_id=run_id,
                metrics=metrics,
                mark=group.mark_durable,
            )
            result = commit_offsets(group, group.durable_next_offsets())
            if not result.succeeded:
                LOGGER.warning("offset commit unconfirmed; retained for retry")
            if monotonic() - last_reconcile >= reconcile_every:
                with db.transaction() as tx:
                    projection.reconcile_deferred(tx, namespace)
                last_reconcile = monotonic()
    finally:
        group.close()


def open_group(namespace, bootstrap):
    return ConsumerGroup(f"{namespace}.catalog-projection.v1", [topic_for(namespace)], bootstrap)


def main():
    parser = argparse.ArgumentParser(description="Run the catalogue stock projection consumer.")
    parser.add_argument("--namespace", required=True)
    arguments = parser.parse_args()
    configure_transport(source_service="catalog")
    metrics = telemetry()
    port = os.environ.get("CATALOG_WORKER_METRICS_PORT")
    if port:
        start_http_server(int(port), registry=metrics.registry)
    run(
        Database(os.environ["CATALOG_DATABASE_URL"], max_connections=2),
        open_group(
            arguments.namespace, os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:9092")
        ),
        arguments.namespace,
        stop=Event(),
        run_id=os.environ.get("RUN_ID", "catalog-projection"),
        metrics=metrics,
    )


if __name__ == "__main__":
    main()
