"""Common §14 names/buckets, explicit finite label vocabularies, lazy series."""

import math

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

BUCKETS = (0.001, 0.005, 0.010, 0.025, 0.050, 0.100, 0.200, 0.500, 1, 2, 5, 10, 30, 60)
# Empty metric families are deliberately not initialized to zero.
DEFINITIONS = {
    "requests_total": (Counter, ("service", "route", "status")),
    "request_duration_seconds": (Histogram, ("service", "route")),
    "outbox_pending": (Gauge, ("service",)),
    "outbox_oldest_age_seconds": (Gauge, ("service",)),
    "outbox_publish_total": (Counter, ("service", "outcome")),
    "source_records_total": (Counter, ("pipeline", "disposition")),
    "silver_unique_total": (Counter, ()),
    "quarantine_total": (Counter, ("reason",)),
    "kafka_consumer_lag": (Gauge, ("group", "topic", "partition")),
    "sink_batch_rows": (Histogram, ()),
    "sink_flush_duration_seconds": (Histogram, ()),
    "gold_pending_events": (Gauge, ()),
    "gold_publication_duration_seconds": (Histogram, ()),
    "gold_generation": (Gauge, ()),
    "projection_apply_total": (Counter, ("outcome",)),
    "projection_age_seconds": (Gauge, ()),
    "saga_orders": (Gauge, ("status",)),
    "compensation_total": (Counter, ("outcome",)),
    "reservation_race_rejections_total": (Counter, ()),
    "process_cpu_seconds_total": (Counter, ()),
    "process_resident_memory_bytes": (Gauge, ()),
    "catalog_source_rows_total": (Counter, ("disposition",)),
    "catalog_issues_total": (Counter, ("reason",)),
    "catalog_import_duration_seconds": (Histogram, ("stage",)),
    "catalog_import_rows_per_second": (Gauge, ("mode",)),
    "intent_llm_calls_total": (Counter, ("outcome",)),
    "intent_llm_duration_seconds": (Histogram, ()),
    "intent_clarifications_total": (Counter, ("reason",)),
    "turn_duration_seconds": (Histogram, ("mode",)),
    "embedding_calls_total": (Counter, ("kind",)),
    "embedding_duration_seconds": (Histogram, ("kind",)),
    # Harness metrics; bounded phase/collector vocabulary, never run/event IDs.
    "benchmark_planned_total": (Counter, ("phase",)),
    "benchmark_admitted_total": (Counter, ("phase",)),
    "benchmark_gold_visible_total": (Counter, ("phase",)),
    "benchmark_observation_up": (Gauge, ("collector",)),
    "benchmark_pending_records": (Gauge, ()),
    "benchmark_pending_bytes": (Gauge, ()),
    "benchmark_inventory_units": (Gauge, ("state",)),
}


class Telemetry:
    def __init__(self, *, label_values=None, registry=None, series_limit=1000):
        self.registry = registry if registry is not None else CollectorRegistry()
        self.allowed = {key: frozenset(values) for key, values in (label_values or {}).items()}
        known = {label for _, labels in DEFINITIONS.values() for label in labels}
        if set(self.allowed) - known or any(
            not values or len(values) > 1000 or any(not isinstance(v, str) for v in values)
            for values in self.allowed.values()
        ):
            raise ValueError("finite registered label vocabularies required")
        if type(series_limit) is not int or not 0 < series_limit <= 10000:
            raise ValueError("bounded series limit required")
        self.series_limit, self.metrics, self.series = series_limit, {}, set()

    def record(self, name, value, **labels):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("numeric observation required")
        if not math.isfinite(value) or value < 0:
            raise ValueError("finite nonnegative observation required")
        if name not in DEFINITIONS:
            raise ValueError("unregistered metric")
        kind, keys = DEFINITIONS[name]
        if set(labels) != set(keys) or any(
            labels[key] not in self.allowed.get(key, ()) for key in keys
        ):
            raise ValueError("labels must use registered names and finite values")
        series = (name, tuple(labels[key] for key in keys))
        if series not in self.series and len(self.series) >= self.series_limit:
            raise ValueError("metric series bound exceeded")
        if name not in self.metrics:
            options = {}
            if kind is Histogram:
                options["buckets"] = BUCKETS if name.endswith("seconds") else (1, 10, 100, 500)
            self.metrics[name] = kind(name, name, keys, registry=self.registry, **options)
        child = self.metrics[name].labels(**labels) if keys else self.metrics[name]
        if kind is Counter:
            child.inc(value)
        elif kind is Gauge:
            child.set(value)
        else:
            child.observe(value)
        self.series.add(series)

    def exposition(self):
        return generate_latest(self.registry)
