"""Separate M1 relay entry point using Aditya's outbox and Vichitr's publisher."""

import argparse
import os
import signal
from threading import BoundedSemaphore, Event

import psycopg

from services.conversation.database import Database
from services.conversation.events import SharedEvents
from shared.event_transport import KafkaPublisher
from shared.outbox import OutboxRelay


class RelayPool:
    """One relay connection, outside the API's configured connection allocation."""

    def __init__(self, url):
        self.url, self.slot = url, BoundedSemaphore(1)

    def getconn(self):
        if not self.slot.acquire(timeout=2):
            raise RuntimeError("M1 relay connection budget exhausted")
        try:
            # The owner's relay expects tuple rows for its advisory-lock query.
            return psycopg.connect(
                self.url, connect_timeout=2, application_name="conversation-relay"
            )
        except BaseException:
            self.slot.release()
            raise

    def putconn(self, connection):
        try:
            connection.close()
        finally:
            self.slot.release()


class RelayRuntime:
    def __init__(self, url, bootstrap):
        if not url or not isinstance(bootstrap, str) or not bootstrap.strip():
            raise ValueError("M1 database URL and Kafka bootstrap servers required")
        self.url, self.bootstrap = url, bootstrap
        self.publisher = self.relay = None

    def start(self):
        if self.relay is not None:
            raise RuntimeError("M1 relay already started")
        database, events = Database(self.url), SharedEvents()
        database.ready()
        events.ready(database)
        self.publisher = KafkaPublisher(events.event_codec(), self.bootstrap)
        try:
            self.relay = OutboxRelay(
                RelayPool(self.url),
                self.publisher,
                service_name="conversation",
                poll_interval_ms=25,
                batch_limit=100,
            )
            self.relay.start()
        except BaseException:
            try:
                self.publisher.close()
            finally:
                self.publisher = self.relay = None
            raise

    def stop(self):
        try:
            if self.relay is not None:
                self.relay.stop()
        finally:
            if self.publisher is not None:
                self.publisher.close()


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    stop = Event()
    for number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(number, lambda *_: stop.set())
    runtime = None
    code = 0
    try:
        runtime = RelayRuntime(
            os.environ.get("CONVERSATION_DATABASE_URL"), os.environ.get("KAFKA_BOOTSTRAP_SERVERS")
        )
        runtime.start()
        while not stop.wait(0.5):
            pass
    except Exception as exc:
        print("M1 relay unavailable: " + type(exc).__name__ + "; outbox retained")
        code = 4
    finally:
        if runtime is not None:
            try:
                runtime.stop()
            except Exception as exc:
                print("M1 relay shutdown unconfirmed: " + type(exc).__name__)
                code = 4
    return code


if __name__ == "__main__":
    raise SystemExit(main())
