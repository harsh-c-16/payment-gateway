"""Bounded synchronous acknowledgement; concurrent callers share one producer."""

import hashlib
import math
import threading
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic

from confluent_kafka import KafkaException, Producer

from shared.contracts.events import PublishAck

PRODUCER_SETTINGS = {
    "enable.idempotence": True,
    "acks": "all",
    "max.in.flight.requests.per.connection": 5,
    "compression.type": "zstd",
    "linger.ms": 5,
    "queue.buffering.max.messages": 10000,
    "queue.buffering.max.kbytes": 65536,
    "delivery.timeout.ms": 10000,
    "request.timeout.ms": 5000,
}
MAX_PENDING_RECORDS = 10000
MAX_PENDING_BYTES = 64 * 1024 * 1024


class RetryablePublishError(RuntimeError):
    retryable = True

    def __init__(self, event_id, reason, *, uncertain):
        self.event_id, self.reason, self.uncertain = event_id, reason, uncertain
        super().__init__(reason)


@dataclass
class Pending:
    future: Future
    digest: str
    size: int


class KafkaPublisher:
    def __init__(self, codec, bootstrap_servers, *, producer_factory=Producer):
        self.codec = codec
        self.producer = producer_factory(
            {**PRODUCER_SETTINGS, "bootstrap.servers": bootstrap_servers}
        )
        self.pending = {}
        self.pending_bytes = 0
        self.lock = threading.RLock()
        self.closed = False

    def publish_event(self, event, topic, key, *, timeout=15):
        if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("publish timeout must be finite and positive")
        raw, headers, topic, key = self.codec.encode(event, topic, key)
        identity = event.event_id
        digest = hashlib.sha256(topic.encode() + b"\0" + key + b"\0" + raw).hexdigest()
        size = len(raw) + len(key) + sum(len(name.encode()) + len(value) for name, value in headers)
        self.producer.poll(0)
        with self.lock:
            if self.closed:
                raise RuntimeError("publisher is closed")
            pending = self.pending.get(identity)
            if pending is not None and pending.digest != digest:
                raise ValueError("pending event identity cannot change content/topic/key")
            if pending is None:
                if (
                    len(self.pending) >= MAX_PENDING_RECORDS
                    or self.pending_bytes + size > MAX_PENDING_BYTES
                ):
                    raise RetryablePublishError(identity, "PUBLISH_QUEUE_FULL", uncertain=False)
                pending = Pending(Future(), digest, size)
                self.pending[identity] = pending
                self.pending_bytes += size

                def delivered(error, message):
                    with self.lock:
                        self.pending.pop(identity, None)
                        self.pending_bytes -= pending.size
                    if error is not None:
                        pending.future.set_exception(
                            RetryablePublishError(identity, "DELIVERY_UNCONFIRMED", uncertain=True)
                        )
                    else:
                        pending.future.set_result(
                            PublishAck(
                                event_id=identity,
                                topic=message.topic(),
                                partition=message.partition(),
                                offset=message.offset(),
                                broker_acked_at=datetime.now(UTC),
                            )
                        )

                try:
                    self.producer.produce(
                        topic, key=key, value=raw, headers=list(headers), on_delivery=delivered
                    )
                except (BufferError, KafkaException) as exc:
                    self.pending.pop(identity, None)
                    self.pending_bytes -= size
                    raise RetryablePublishError(
                        identity, "PUBLISH_NOT_QUEUED", uncertain=False
                    ) from exc
        deadline = monotonic() + timeout
        while not pending.future.done():
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise RetryablePublishError(identity, "ACK_TIMEOUT", uncertain=True)
            self.producer.poll(min(0.05, remaining))
        return pending.future.result()

    def close(self, timeout=15):
        with self.lock:
            self.closed = True
        remaining = self.producer.flush(timeout)
        if remaining:
            raise RetryablePublishError(None, "PUBLISHER_CLOSE_UNCONFIRMED", uncertain=True)
