"""Worker-owned consumer, bounded source buffers and fenced durable-prefix commits."""

import hashlib
import re
from collections import OrderedDict, deque
from datetime import UTC, datetime
from threading import get_ident
from time import monotonic
from uuid import uuid4

from confluent_kafka import Consumer, KafkaError, KafkaException, TopicPartition

from shared.contracts.events import CommitResult, CommittedOffset, SourceRecord

GROUP_MAX_RECORDS = 2000
GROUP_MAX_BYTES = 16 * 1024 * 1024
MAX_SOURCE_BYTES = 1024 * 1024
TOPIC = re.compile(
    r"^(dev|(?:bench|replay)-[a-z0-9-]{1,54})\."
    r"(conversation-events|retrieval-events|order-events|inventory-events|payment-events|dead-letter)\.v1$"
)


def raw_fingerprint(key, value, headers):
    """Length-delimited original bytes; null and empty bytes have different hashes."""
    digest = hashlib.sha256(b"group3-source-bytes-v1\0")
    for item in (key, value, *(part for name, data in headers for part in (name.encode(), data))):
        digest.update((-1 if item is None else len(item)).to_bytes(8, "big", signed=True))
        if item is not None:
            digest.update(item)
    return digest.hexdigest()


def record_size(record):
    return (
        len(record.key_bytes or b"")
        + len(record.value_bytes or b"")
        + sum(len(name.encode()) + len(value or b"") for name, value in record.headers)
    )


class ConsumerBufferError(RuntimeError):
    pass


class ConsumerGroup:
    """One handle per declared worker; all methods run on that worker's thread."""

    def __init__(
        self,
        group_id,
        topics,
        bootstrap_servers,
        *,
        workers=1,
        worker_index=0,
        consumer_factory=Consumer,
    ):
        if workers not in (1, 3) or type(workers) is not int or type(worker_index) is not int:
            raise ValueError("declare one or three workers")
        if not 0 <= worker_index < workers:
            raise ValueError("worker index is outside the declared group")
        topics = tuple(topics)
        matches = [TOPIC.fullmatch(topic) for topic in topics]
        if not matches or not all(matches) or len({match[1] for match in matches}) != 1:
            raise ValueError("consumer topics must share one valid namespace")
        self.namespace = matches[0][1]
        if not isinstance(group_id, str) or not group_id.startswith(self.namespace + "."):
            raise ValueError("consumer group must share its topics' namespace")
        self.group_id, self.topics = group_id, topics
        self.record_limit = GROUP_MAX_RECORDS // workers + (
            worker_index < GROUP_MAX_RECORDS % workers
        )
        self.byte_limit = GROUP_MAX_BYTES // workers + (worker_index < GROUP_MAX_BYTES % workers)
        self.owner = get_ident()
        self.instance_token = uuid4().hex
        self.epoch = 0
        self.assignments = {}
        self.ledger = {}
        self.ready = deque()
        self.buffer_bytes = 0
        self.paused = False
        self.closed = False
        self.last_rebalance_error = None
        # A quarter-budget native queue + a fetch response leaves byte headroom
        # for the half-budget application buffer; raw bytes, not total process RSS.
        self.application_byte_limit = self.byte_limit // 2
        self.settings = {
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "group.instance.id": f"{group_id}.worker-{worker_index}",
            "group.protocol": "classic",
            "partition.assignment.strategy": "range",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
            "session.timeout.ms": 10000,
            "max.poll.interval.ms": 300000,
            "socket.timeout.ms": 5000,
            "queued.min.messages": 1,
            "queued.max.messages.kbytes": self.byte_limit // 4096,
            "fetch.max.bytes": self.byte_limit // 4,
            "max.partition.fetch.bytes": self.byte_limit // 4,
            "allow.auto.create.topics": False,
        }
        self.consumer = consumer_factory(self.settings)
        self.consumer.subscribe(
            list(topics),
            on_assign=self._on_assign,
            on_revoke=self._on_revoke,
            on_lost=self._on_lost,
        )

    def _check_thread(self):
        if self.closed or get_ident() != self.owner:
            raise RuntimeError("consumer handle is closed or used from another worker thread")

    def _on_assign(self, consumer, partitions):
        self.epoch += 1
        for partition in partitions:
            key = (partition.topic, partition.partition)
            self.assignments[key] = f"{self.instance_token}:{self.epoch}"
            self.ledger[key] = OrderedDict()
        self.paused = False
        consumer.assign(partitions)

    def _forget(self, partitions):
        for partition in partitions:
            key = (partition.topic, partition.partition)
            self.assignments.pop(key, None)
            for record, _ in self.ledger.pop(key, {}).values():
                self.buffer_bytes -= record_size(record)
        self.ready = deque(record for record in self.ready if self.is_current(record))
        self.paused = False

    def _on_revoke(self, consumer, partitions):
        prefix = self.durable_next_offsets()
        prefix = {
            key: offset
            for key, offset in prefix.items()
            if key in {(p.topic, p.partition) for p in partitions}
        }
        if prefix:
            result = self.commit_offsets(prefix)
            self.last_rebalance_error = result.error
        self._forget(partitions)

    def _on_lost(self, consumer, partitions):
        # Ownership is already lost: no broker commit is attempted.
        self._forget(partitions)

    def is_current(self, record):
        return self.assignments.get(
            (record.topic, record.partition)
        ) == record.assignment_epoch and record.offset in self.ledger.get(
            (record.topic, record.partition), {}
        )

    def mark_durable(self, record):
        """Call only after the caller's disposition transaction/file durability succeeds."""
        self._check_thread()
        if not self.is_current(record):
            raise ValueError("source record belongs to a revoked assignment")
        entry = self.ledger[(record.topic, record.partition)][record.offset]
        if entry[0] != record:
            raise ValueError("source record differs from the delivered bytes")
        entry[1] = True

    def durable_next_offsets(self):
        result = {}
        for key, records in self.ledger.items():
            for offset, (_, durable) in records.items():
                if not durable:
                    break
                result[key] = offset + 1
        return result

    def commit_offsets(self, durable_next_offsets):
        self._check_thread()
        prefix = self.durable_next_offsets()
        for key, offset in durable_next_offsets.items():
            if (
                key not in self.assignments
                or type(offset) is not int
                or offset < 0
                or key not in prefix
                or offset > prefix[key]
                or offset not in [value + 1 for value in self.ledger[key]]
            ):
                return CommitResult(self.group_id, (), False, "NON_CONTIGUOUS_OR_REVOKED_PREFIX")
        if not durable_next_offsets:
            return CommitResult(self.group_id, (), True, None)
        try:
            answers = self.consumer.commit(
                offsets=[
                    TopicPartition(*key, offset) for key, offset in durable_next_offsets.items()
                ],
                asynchronous=False,
            )
        except (KafkaException, RuntimeError):
            return CommitResult(self.group_id, (), False, "OFFSET_COMMIT_UNCONFIRMED")
        committed = []
        for answer in answers:
            key = (answer.topic, answer.partition)
            if answer.error is not None or durable_next_offsets.get(key) != answer.offset:
                continue
            committed.append(CommittedOffset(*key, answer.offset))
            for offset in list(self.ledger[key]):
                if offset < answer.offset:
                    record, _ = self.ledger[key].pop(offset)
                    self.buffer_bytes -= record_size(record)
        self.ready = deque(record for record in self.ready if self.is_current(record))
        succeeded = len(committed) == len(durable_next_offsets)
        return CommitResult(
            self.group_id,
            tuple(committed),
            succeeded,
            None if succeeded else "OFFSET_COMMIT_PARTIAL_OR_UNCONFIRMED",
        )

    def _buffered_count(self):
        return sum(len(records) for records in self.ledger.values())

    def _pause_if_needed(self):
        blocked = (
            self._buffered_count() >= self.record_limit - 1
            or self.buffer_bytes > self.application_byte_limit - MAX_SOURCE_BYTES
        )
        partitions = [TopicPartition(*key) for key in self.assignments]
        if partitions and blocked != self.paused:
            (self.consumer.pause if blocked else self.consumer.resume)(partitions)
            self.paused = blocked

    def _capture(self, message):
        key = (message.topic(), message.partition())
        if key not in self.assignments:
            raise ConsumerBufferError("received a record without an owned assignment")
        timestamp_type, millis = message.timestamp()
        broker_time = (
            None
            if timestamp_type == 0 or millis < 0
            else datetime.fromtimestamp(millis // 1000, UTC).replace(
                microsecond=millis % 1000 * 1000
            )
        )
        headers = tuple(message.headers() or ())
        record = SourceRecord(
            self.namespace,
            *key,
            message.offset(),
            message.key(),
            message.value(),
            headers,
            broker_time,
            datetime.now(UTC),
            raw_fingerprint(message.key(), message.value(), headers),
            self.assignments[key],
        )
        size = record_size(record)
        if (
            size > MAX_SOURCE_BYTES
            or self._buffered_count() >= self.record_limit
            or self.buffer_bytes + size > self.application_byte_limit
        ):
            self.consumer.seek(TopicPartition(*key, message.offset()))
            self.consumer.pause([TopicPartition(*owned) for owned in self.assignments])
            self.paused = True
            raise ConsumerBufferError("source buffer limit reached; record rewound without commit")
        records = self.ledger[key]
        if record.offset in records or (records and record.offset <= next(reversed(records))):
            raise ConsumerBufferError("unexpected repeated/backward offset in one assignment")
        records[record.offset] = [record, False]
        self.buffer_bytes += size
        self.ready.append(record)

    def consume_records(self, topics, max_records, max_wait_ms):
        self._check_thread()
        if set(topics) != set(self.topics):
            raise ValueError("use the handle's fixed topic subscription")
        if type(max_records) is not int or not 0 <= max_records <= self.record_limit:
            raise ValueError("max_records must fit this worker's allocation")
        if type(max_wait_ms) is not int or not 0 <= max_wait_ms <= 1000:
            raise ValueError("max_wait_ms must be between zero and 1000")
        result = []
        deadline = monotonic() + max_wait_ms / 1000
        while True:
            while self.ready and len(result) < max_records:
                record = self.ready.popleft()
                if self.is_current(record):
                    result.append(record)
            if max_records and len(result) == max_records:
                break
            self._pause_if_needed()
            message = self.consumer.poll(max(0, min(0.1, deadline - monotonic())))
            if message is not None:
                if message.error():
                    if message.error().code() != KafkaError._PARTITION_EOF:
                        raise KafkaException(message.error())
                else:
                    self._capture(message)
            if monotonic() >= deadline or (max_records == 0 and message is None):
                while self.ready and len(result) < max_records:
                    result.append(self.ready.popleft())
                break
        return [record for record in result if self.is_current(record)]

    def close(self):
        self._check_thread()
        try:
            self.consumer.close()
        finally:
            self.closed = True
            self.assignments.clear()
            self.ledger.clear()
            self.ready.clear()
            self.buffer_bytes = 0
