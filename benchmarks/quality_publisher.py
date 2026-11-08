"""Harness-only dirty-fixture transport; normal events retain SDK validation."""

import asyncio
import hashlib
import time
from concurrent.futures import Future

from confluent_kafka import Producer

from benchmarks.drivers import PipelineDriver
from benchmarks.quality import SUBCASES
from benchmarks.scheduler import Receipt
from shared.contracts.events import ValidationFailure
from shared.event_transport.publisher import PRODUCER_SETTINGS, KafkaPublisher


def wire_arguments(packet):
    return (
        packet.body,
        tuple((name, value.encode("utf-8")) for name, value in packet.headers),
        packet.channel,
        packet.key.encode("utf-8"),
    )


class RawFixturePublisher:
    """One in-flight raw fixture at a time, with the frozen SDK producer settings.

    Only QualityPublisher calls this after independently authorizing an invalid
    recipe row. This deliberately has no business-event or outbox registration.
    Producers are lazy: an unavailable dependency never starts a broker client.
    """

    def __init__(self, bootstrap, *, producer_factory=Producer):
        self.bootstrap, self.factory = bootstrap, producer_factory
        self.producer = None

    def publish(self, packet):
        if self.producer is None:
            self.producer = self.factory({**PRODUCER_SETTINGS, "bootstrap.servers": self.bootstrap})
        future = Future()

        def delivered(error, message):
            if error is not None:
                future.set_exception(RuntimeError("raw fixture delivery unconfirmed"))
            else:
                future.set_result(
                    dict(
                        topic=message.topic(),
                        partition=message.partition(),
                        offset=message.offset(),
                    )
                )

        raw, headers, topic, key = wire_arguments(packet)
        self.producer.produce(
            topic, value=raw, key=key, headers=list(headers), on_delivery=delivered
        )
        deadline = time.monotonic() + 15
        while not future.done():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("raw fixture acknowledgement unknown; no retry")
            self.producer.poll(min(0.05, remaining))
        return future.result()

    def close(self):
        if self.producer is not None and self.producer.flush(15):
            raise RuntimeError("raw fixture publisher close unconfirmed")


class QualityPublisher:
    def __init__(self, codec, bootstrap, *, normal=None, raw=None):
        self.codec, self.bootstrap = codec, bootstrap
        self.normal, self.raw = normal, raw or RawFixturePublisher(bootstrap)
        # Serialize identical IDs so SDK pending-ID coalescing cannot collapse
        # two planned physical deliveries. The striped lock table stays bounded.
        self.locks = tuple(asyncio.Lock() for _ in range(256))
        self.raw_lock = asyncio.Lock()

    async def __call__(self, packet, context):
        record = context["record"]
        if not context["namespace"].startswith("bench-") or not packet.channel.startswith(
            context["namespace"] + "."
        ):
            raise ValueError("quality publishing requires the isolated namespace topic")
        checked = self.codec.validate_event(*wire_arguments(packet))
        invalid = record["expected_disposition"] == "invalid"
        if invalid:
            # Row labels alone cannot authorize bypassing normal validation.
            wanted = dict(SUBCASES).get(record.get("invalid_subcase"))
            ordinal = record.get("record_ordinal")
            block = (
                SUBCASES[(ordinal - 99500) // 50][0]
                if type(ordinal) is int and 99500 <= ordinal < 100000
                else None
            )
            if (
                wanted is None
                or block != record.get("invalid_subcase")
                or record.get("duplicate_of") is not None
                or record.get("reason_code") != wanted
                or not isinstance(checked, ValidationFailure)
                or checked.reason_code != wanted
            ):
                raise ValueError("raw fixture does not match the independent invalid subcase")
            async with self.raw_lock:
                source = await asyncio.to_thread(self.raw.publish, packet)
        else:
            if (
                record["expected_disposition"] not in {"new_valid", "duplicate_delivery"}
                or isinstance(checked, ValidationFailure)
                or record.get("invalid_subcase") is not None
            ):
                raise ValueError("normal quality event failed SDK validation")
            event = checked.envelope
            if event.event_id != packet.identity:
                raise ValueError("wire event identity differs from the persisted packet")
            # Encoding again must reproduce the persisted packet exactly.
            if self.codec.encode(event, packet.channel, packet.key) != wire_arguments(packet):
                raise ValueError("SDK encoding changed persisted bytes/headers")
            stripe = int(hashlib.sha256(packet.identity.encode()).hexdigest()[:2], 16)
            async with self.locks[stripe]:
                if self.normal is None:
                    self.normal = KafkaPublisher(self.codec, self.bootstrap)
                ack = await asyncio.to_thread(
                    self.normal.publish_event, event, packet.channel, packet.key
                )
                if ack.event_id != packet.identity:
                    raise ValueError("SDK acknowledgement identity mismatch")
                source = dict(topic=ack.topic, partition=ack.partition, offset=ack.offset)
        if (
            source.get("topic") != packet.channel
            or type(source.get("partition")) is not int
            or source["partition"] < 0
            or type(source.get("offset")) is not int
            or source["offset"] < 0
        ):
            raise ValueError("quality broker acknowledgement missing actual source coordinates")
        return Receipt(packet.identity, "accepted", source=source)

    async def close(self):
        try:
            if self.normal is not None:
                await asyncio.to_thread(self.normal.close)
        finally:
            await asyncio.to_thread(self.raw.close)


class QualityDriver(PipelineDriver):
    def __init__(self, publisher):
        super().__init__(None, publisher)

    def materialize(self, record, context):
        if self.materializer is None:
            raise RuntimeError("verified quality materializer not prepared")
        return self.materializer(record, context)
