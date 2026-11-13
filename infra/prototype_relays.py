"""Development-only co-location of independent shared outbox relays."""

import os
import signal
from contextlib import ExitStack
from pathlib import Path
from threading import Event

from infra.catalog_relay import catalog_relay
from shared.event_transport import EventCodec
from shared.event_transport.schemas import SchemaCache

SERVICES = ("conversation", "catalog", "orders", "inventory", "payments")
READY = Path("/tmp/prototype-relays-ready")


def main():
    stop = Event()
    for number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(number, lambda *_: stop.set())
    try:
        cache = SchemaCache.load(os.environ["EVENT_SCHEMA_CACHE_PATH"])
        with ExitStack() as stack:
            relays = []
            try:
                for service in SERVICES:
                    relays.append(
                        stack.enter_context(
                            catalog_relay(
                                os.environ[service.upper() + "_DATABASE_URL"],
                                EventCodec(cache, source_service=service),
                                os.environ["KAFKA_BOOTSTRAP_SERVERS"],
                                service_name=service,
                                poll_interval_ms=250,
                            )
                        )
                    )
                while not stop.is_set():
                    if any(
                        relay._thread is None or not relay._thread.is_alive() for relay in relays
                    ):
                        raise RuntimeError("Shared relay thread stopped")
                    READY.touch()
                    stop.wait(1)
            finally:
                # Request all stops before joining, so broker timeouts overlap.
                for relay in relays:
                    relay._stop.set()
    except Exception as exc:
        print("Prototype relays unavailable: " + type(exc).__name__ + "; outboxes retained")
        return 4
    finally:
        READY.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
