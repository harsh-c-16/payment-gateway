"""Catalogue process binding for the existing shared transactional outbox relay."""

import os
import signal
from contextlib import contextmanager
from threading import Event

import psycopg

from pipelines.ingestion.notifications import RelayConnections
from shared.event_transport import KafkaPublisher, configure_transport
from shared.outbox import OutboxRelay


@contextmanager
def catalog_relay(url, codec, bootstrap, *, service_name="catalog"):
    if service_name not in {"conversation", "catalog", "orders", "inventory", "payments"}:
        raise ValueError("Explicit operational outbox service required")

    def connect():
        return psycopg.connect(url, connect_timeout=5, application_name=service_name + "-relay")

    with connect() as tx:
        tx.execute("SELECT event_id,published_at FROM outbox LIMIT 0")
    publisher = KafkaPublisher(codec, bootstrap)
    relay = OutboxRelay(
        RelayConnections(connect),
        publisher,
        service_name=service_name,
        poll_interval_ms=25,
        batch_limit=100,
    )
    thread = None
    try:
        relay.start()
        thread = relay._thread
        yield relay
    finally:
        try:
            relay.stop(timeout=30)
        finally:
            if thread is not None and thread.is_alive():
                raise RuntimeError(service_name + " relay shutdown unconfirmed; outbox retained")
            publisher.close()


def main():
    stop = Event()
    for number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(number, lambda *_: stop.set())
    try:
        bootstrap = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
        codec = configure_transport(source_service="catalog", bootstrap_servers=bootstrap)
        with catalog_relay(os.environ["CATALOG_DATABASE_URL"], codec, bootstrap):
            stop.wait()
    except Exception as exc:
        print("Catalogue relay unavailable: " + type(exc).__name__ + "; outbox retained")
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
