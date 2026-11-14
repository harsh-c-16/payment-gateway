"""Truth-preserving projections. All elapsed cross-process times retain clock status."""

import math
from collections import Counter
from datetime import UTC, datetime

PAYLOAD_FIELDS = {
    "order_id",
    "search_id",
    "turn_id",
    "cart_id",
    "quote_id",
    "reservation_id",
    "payment_id",
    "confirmation_id",
    "sku",
    "stock_version",
    "on_hand",
    "reserved",
    "available",
    "order_status",
    "failure_code",
    "total_amount_minor",
    "amount_minor",
    "currency",
    "created_at",
    "attempt_id",
    "duration_ms",
    "returned_count",
    "mode",
    "reason_code",
    "outcome",
    "extractor_version",
    "quantity",
    "request_id",
    "reservation_request_id",
}
META_FIELDS = {
    "synthetic",
    "scenario_source",
    "dataset_revision",
    "dictionary_version",
    "transform_version",
    "original_event_id",
    "normalization_version",
    "schema_id",
}


def timestamp(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
            return None
        return parsed
    except (TypeError, ValueError):
        return None


def elapsed(start, end):
    a, b = timestamp(start), timestamp(end)
    if a is None or b is None or b < a:
        return None
    return round((b - a).total_seconds() * 1000, 3)


def safe_event(document):
    fields = (
        "event_id",
        "event_type",
        "source_service",
        "correlation_id",
        "aggregate_id",
        "aggregate_type",
        "aggregate_version",
        "produced_at",
        "event_time",
        "schema_version",
        "run_id",
        "namespace",
        "session_id",
    )
    result = {key: document.get(key) for key in fields}
    result["payload"] = {
        k: v for k, v in document.get("payload", {}).items() if k in PAYLOAD_FIELDS
    }
    result["metadata"] = {k: v for k, v in document.get("metadata", {}).items() if k in META_FIELDS}
    return result


def quantiles(values):
    values = sorted(v for v in values if isinstance(v, (int, float)) and math.isfinite(v))
    return {
        "sample_count": len(values),
        **{
            f"p{int(q * 100)}_ms": values[math.ceil(q * len(values)) - 1] if values else None
            for q in (0.5, 0.95, 0.99)
        },
    }


def timeline(event, clock):
    receipt = event.get("receipt") or {}
    invalid = receipt.get("timing_validity", "missing")
    failed = receipt.get("disposition") == "invalid"
    stamps = [
        ("request", "Request submitted", event.get("request_submitted_at")),
        ("producer", "Producer / outbox", event.get("produced_at")),
        ("kafka", "Kafka observed", event.get("kafka_observed_at") or receipt.get("ingested_at")),
        ("bronze", "Bronze durable", receipt.get("bronze_durable_at")),
        ("silver", "Silver commit observed", receipt.get("silver_committed_observed_at")),
        ("gold", "Active Gold visible", receipt.get("gold_visible_at")),
    ]
    previous = None
    stages = []
    for key, label, at in stamps:
        status = "observed" if timestamp(at) else "unavailable"
        if key == "gold" and failed:
            status = "failed"
        elif key == "gold" and receipt and not at:
            status = "pending" if receipt.get("disposition") else "unavailable"
        elif key in {"kafka", "bronze", "silver"} and not at and event.get("outbox_pending"):
            status = "pending"
        duration = elapsed(previous, at)
        stages.append(
            {
                "key": key,
                "label": label,
                "at": at,
                "status": status,
                "since_previous_observed_ms": (
                    duration
                    if clock.get("status") == "qualified"
                    and (key not in {"bronze", "silver", "gold"} or invalid == "observed")
                    else None
                ),
                "clock_validity": clock.get("status", "unavailable"),
                "timing_validity": invalid if key in {"bronze", "silver", "gold"} else "observed",
                "ordering": "invalid_clock_order" if previous and at and duration is None else None,
            }
        )
        if at:
            previous = at
    return stages


def latency_summary(events, clock, window=None):
    # Source deliveries are distinct, logical completion is unique by immutable event ID.
    valid, excluded = {}, Counter()
    for event in events:
        receipt = event.get("receipt") or {}
        if receipt.get("disposition") == "invalid" or not event.get("event_id"):
            excluded["quarantined_or_unidentified"] += 1
            continue
        identity = event["event_id"]
        old = valid.get(identity)
        if old is None or (
            receipt.get("gold_visible_at") and not (old.get("receipt") or {}).get("gold_visible_at")
        ):
            valid[identity] = event
    completed = [e for e in valid.values() if (e.get("receipt") or {}).get("gold_visible_at")]
    producer, scheduled, breakdown = [], [], []
    for event in completed:
        receipt = event["receipt"]
        qualified = (
            clock.get("status") == "qualified" and receipt.get("timing_validity") == "observed"
        )
        value = elapsed(event.get("produced_at"), receipt.get("gold_visible_at"))
        if qualified and value is not None:
            producer.append(value)
        else:
            excluded["unqualified_or_missing_timing"] += 1
        schedule = elapsed(event.get("scheduled_at"), receipt.get("gold_visible_at"))
        if qualified and schedule is not None:
            scheduled.append(schedule)
        breakdown.append(
            {
                "event_id": event["event_id"],
                "event_type": event.get("event_type"),
                "producer_to_gold_ms": value if qualified else None,
                "relay_to_observation_ms": elapsed(
                    event.get("produced_at"), event.get("kafka_observed_at")
                )
                if qualified
                else None,
                "ingestion_ms": elapsed(
                    receipt.get("ingested_at"), receipt.get("silver_committed_observed_at")
                )
                if qualified
                else None,
                "publication_ms": elapsed(
                    receipt.get("silver_committed_observed_at"), receipt.get("gold_visible_at")
                )
                if qualified
                else None,
                "clock_validity": clock.get("status", "unavailable"),
            }
        )
    unresolved = len(valid) - len(completed)
    return {
        "producer_to_gold": quantiles(producer),
        "schedule_to_gold": quantiles(scheduled),
        "cohort_count": len(valid),
        "completed_count": len(completed),
        "unresolved_count": unresolved,
        "quantile_method": "nearest-rank ceil(q*n); completed-only",
        "cohort_p99_established": bool(valid)
        and unresolved / len(valid) <= 0.01
        and len(producer) == len(completed),
        "clock": clock,
        "excluded": dict(excluded),
        "breakdown": breakdown[-120:],
        "scope": "Bounded observed event cohort; not a sustained workload benchmark",
        "window": window,
    }


def related_events(events, kind, identity):
    field = {"order": "order_id", "search": "search_id", "event": "event_id"}[kind]
    direct = [
        e for e in events if (e if kind == "event" else e.get("payload", {})).get(field) == identity
    ]
    if not direct:
        direct = [e for e in events if e.get("aggregate_id") == identity]
    # Never follow a session-wide correlation ID into unrelated orders or searches.
    order_ids = {e.get("payload", {}).get("order_id") for e in direct} - {None}
    search_ids = {e.get("payload", {}).get("search_id") for e in direct} - {None}
    turns = {e.get("payload", {}).get("turn_id") for e in direct} - {None}
    return [
        e
        for e in events
        if e in direct
        or e.get("payload", {}).get("order_id") in order_ids
        or e.get("payload", {}).get("search_id") in search_ids
        or e.get("payload", {}).get("turn_id") in turns
    ]


def merge_observations(producers, receipts, broker):
    by_id = {p["event_id"]: p for p in producers if p.get("event_id")}
    by_source = {
        (b["source"]["topic"], b["source"]["partition"], b["source"]["offset"]): b for b in broker
    }
    output, seen = [], set()
    for receipt in receipts:
        source = receipt["source"]
        key = (source["topic"], source["partition"], source["offset"])
        if key in seen:
            continue
        seen.add(key)
        original = by_source.get(key)
        if original and original.get("raw_sha256") != receipt["raw_sha256"]:
            raise ValueError("Broker / Bronze content-hash mismatch")
        # A conflicting delivery must never inherit the first producer's payload.
        fallback = by_id.get(receipt.get("event_id"), {})
        if receipt.get("reason_code") == "EVENT_ID_CONFLICT" and original is None:
            fallback = {}
        event = {
            **fallback,
            **(original or {}),
            "receipt": receipt,
            "source": source,
            "event_id": receipt.get("event_id"),
            "key": ":".join(map(str, key)),
        }
        output.append(event)
    emitted = {e.get("event_id") for e in output}
    for event in producers:
        if event["event_id"] not in emitted:
            output.append({**event, "key": "outbox:" + event["event_id"], "receipt": None})
    for event in broker:
        key = tuple(event["source"][k] for k in ("topic", "partition", "offset"))
        if key not in seen:
            output.append({**event, "key": ":".join(map(str, key)), "receipt": None})
    return sorted(
        output,
        key=lambda e: e.get("produced_at") or (e.get("receipt") or {}).get("ingested_at") or "",
        reverse=True,
    )


def now():
    return datetime.now(UTC).isoformat()
