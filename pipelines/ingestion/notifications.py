"""Bind analytics DLQ notifications to the existing shared outbox relay."""

from contextlib import contextmanager

from shared.event_transport import KafkaPublisher
from shared.outbox import OutboxRelay


class RelayConnections:
    """Adapt the bounded connection context to the shared relay's pool contract."""

    def __init__(self, connect):
        self.connect, self.context = connect, None

    def getconn(self):
        self.context = self.connect()
        try:
            return self.context.__enter__()
        except BaseException:
            self.context = None
            raise

    def putconn(self, connection):
        context, self.context = self.context, None
        context.__exit__(None, None, None)


@contextmanager
def notification_relay(pipeline, bootstrap):
    with pipeline.connect() as tx:
        tx.execute("SELECT event_id,published_at FROM outbox LIMIT 0")
    publisher = KafkaPublisher(pipeline.codec, bootstrap)
    relay = OutboxRelay(
        RelayConnections(getattr(pipeline, "publisher_connect", pipeline.connect)),
        publisher,
        service_name="analytics",
        batch_limit=100,
    )
    thread = None
    try:
        relay.start()
        thread = relay._thread
        yield
    finally:
        # The shared stop method clears its handle even after an unconfirmed join.
        try:
            relay.stop(timeout=30)
        finally:
            if thread is not None and thread.is_alive():
                raise RuntimeError("Analytics relay shutdown unconfirmed; pending outbox retained")
            publisher.close()
