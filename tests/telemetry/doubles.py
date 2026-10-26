"""Explicit test-only publisher-stall and collector-failure projections."""

from benchmarks.observation import Collector, Reading, Series


def stalled_publishers():
    lag = Series(
        "kafka_consumer_lag",
        "analytics",
        "records",
        (("group", "test-group"), ("partition", "0"), ("topic", "test-topic")),
    )
    gold = Series("gold_pending_events", "gold", "events")
    outbox = Series("outbox_pending", "orders", "rows", (("service", "orders"),))
    age = Series("outbox_oldest_age_seconds", "orders", "seconds", (("service", "orders"),))

    async def read(sequence):
        # The Kafka consumer has committed, while the Gold publisher is stalled.
        return {
            lag.key: Reading(
                0, {"log_end_next_offset": 100 + sequence, "committed_next_offset": 100 + sequence}
            ),
            gold.key: Reading(sequence * 10),
            outbox.key: Reading(sequence * 2),
            age.key: Reading(sequence),
        }

    return Collector("publisher_stall", (lag, gold, outbox, age), read, mode="stub")


def stopped_collector():
    series = Series("projection_age_seconds", "catalog", "seconds")

    async def read(sequence):
        if sequence:
            raise ConnectionError("explicit collector stopped")
        return {series.key: Reading(0.1)}

    return Collector("stopped", (series,), read, mode="stub")
