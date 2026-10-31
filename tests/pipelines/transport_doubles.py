"""Explicit in-memory Kafka command doubles; never evidence of real broker delivery."""

from collections import deque
from time import sleep

from confluent_kafka import TopicPartition

from shared.event_transport.schemas import SchemaCache, documents


def offline_cache():
    return SchemaCache(
        {
            "compatibility": "BACKWARD_TRANSITIVE",
            "schemas": [
                {**entry, "id": number, "version": 1, "schema": schema}
                for number, (entry, schema) in enumerate(documents().values(), 101)
            ],
        }
    )


class MessageDouble:
    def __init__(self, topic, offset, *, partition=0, value=b"{}", key=b"key", headers=()):
        self._topic, self._offset, self._partition = topic, offset, partition
        self._value, self._key, self._headers = value, key, headers

    def topic(self):
        return self._topic

    def offset(self):
        return self._offset

    def partition(self):
        return self._partition

    def value(self):
        return self._value

    def key(self):
        return self._key

    def headers(self):
        return self._headers

    def error(self):
        return None

    def timestamp(self):
        return (1, 1793440800123)


class ProducerDouble:
    def __init__(self, settings):
        self.settings, self.records, self.callbacks = settings, [], deque()
        self.deliver = True
        self.error = None

    def produce(self, topic, *, key, value, headers, on_delivery):
        self.records.append((topic, key, value, headers))
        self.callbacks.append((on_delivery, MessageDouble(topic, len(self.records) - 1)))

    def poll(self, timeout):
        if self.deliver and self.callbacks:
            callback, message = self.callbacks.popleft()
            callback(self.error, message)
        elif timeout:
            sleep(min(timeout, 0.001))

    def flush(self, timeout):
        while self.deliver and self.callbacks:
            self.poll(0)
        return len(self.callbacks)


class ConsumerDouble:
    def __init__(self, settings, partitions=1):
        self.settings, self.partitions = settings, partitions
        self.messages, self.commits, self.seeks = deque(), [], []
        self.paused, self.polls, self.fail_commit = False, 0, False
        self.assigned = []

    def subscribe(self, topics, **callbacks):
        self.callbacks = callbacks
        callbacks["on_assign"](
            self, [TopicPartition(topic, p) for topic in topics for p in range(self.partitions)]
        )

    def assign(self, partitions):
        self.assigned = partitions

    def pause(self, partitions):
        self.paused = True

    def resume(self, partitions):
        self.paused = False

    def seek(self, partition):
        self.seeks.append(partition)

    def poll(self, timeout):
        self.polls += 1
        if self.messages and not self.paused:
            return self.messages.popleft()
        if timeout:
            sleep(min(timeout, 0.001))
        return None

    def commit(self, *, offsets, asynchronous):
        assert asynchronous is False
        if self.fail_commit:
            raise RuntimeError("explicit broker command double failure")
        self.commits.append(offsets)
        return offsets

    def close(self):
        self.callbacks["on_revoke"](self, self.assigned)
