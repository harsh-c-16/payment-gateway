"""Independent physical/logical quality accounting, without production cleaners."""

import base64
import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from functools import lru_cache
from uuid import UUID, uuid5

from benchmarks.quality import quality_expectations
from projectctl.artifacts import canonical_json
from shared.event_transport.consumer import raw_fingerprint


def fixture_rows(seed, gate="T-03"):
    if gate == "T-03":
        return quality_expectations(seed)
    if gate != "G1":
        raise ValueError("gate must be T-03 or G1; no partial T-03")
    return iter(json.loads(_g1_rows(seed)))


@lru_cache(maxsize=16)
def _g1_rows(seed):
    rows = {}
    for row in quality_expectations(seed):
        if row["record_ordinal"] in {0, 98500, 99500}:
            rows[row["record_ordinal"]] = row
    duplicate = rows[98500] | {
        "logical_event_id": rows[0]["logical_event_id"],
        "logical_content_sha256": rows[0]["logical_content_sha256"],
        "duplicate_of": 0,
    }
    return canonical_json((rows[0], duplicate, rows[99500]))


def read_jsonl(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def coordinate(source):
    topic, partition, offset = (source[name] for name in ("topic", "partition", "offset"))
    if (
        not isinstance(topic, str)
        or type(partition) is not int
        or partition < 0
        or type(offset) is not int
        or offset < 0
    ):
        raise ValueError("broker coordinate is invalid")
    return topic, partition, offset


def reconcile_quality(context, directory, observed, *, gate="T-03"):
    """Labels come exclusively from the harness recipe, never sink dispositions.

    All planned offers must have distinct physical offsets, exact archived bytes,
    one final receipt and (for invalid records) one quarantine entry. Logical
    event IDs/hashes, Silver payloads and pinned Gold counts are checked separately.
    Missing timers remain null in the source export and cannot supply latency.
    """
    failures = []

    def check(name, condition):
        if not condition:
            failures.append(name)

    report = {
        "test_mode": observed.get("test_mode"),
        "gate": gate,
        "status": "INCOMPLETE",
        "passed": None,
        "invariant_failures": failures,
        "timings": {"status": "NOT_RUN", "value": None},
    }
    try:
        check("EXPLICIT_MODE", observed["test_mode"] in {"real", "stub"})
        check("NAMESPACE", observed["namespace"] == context["namespace"])
        check("RUN_ID", observed["run_id"] == context["run_id"])
        expected = list(fixture_rows(context["seed"], gate))
        planned = read_jsonl(directory / "planned.jsonl")
        check("COMPLETE_FROZEN_PLAN", len(planned) == len(expected))
        for want, actual in zip(expected, planned, strict=True):
            check(
                "PLAN_CHANGED:" + want["logical_record_id"],
                all(actual.get(key) == value for key, value in want.items()),
            )
        emissions = read_jsonl(directory / "emissions.jsonl")
        by_id = {row["record_id"]: row for row in emissions}
        check("ONE_EMISSION_PER_OFFER", len(by_id) == len(emissions) == len(expected))
        check("EXACT_EMISSION_IDS", set(by_id) == {r["logical_record_id"] for r in expected})

        def index(rows, field="source"):
            result = {}
            for row in rows:
                key = coordinate(row[field])
                check("DUPLICATE_EXPORT_COORDINATE:" + str(key), key not in result)
                result[key] = row
            return result

        receipts = index(observed["receipts"])
        bronze = index(observed["bronze"])
        quarantine = index(observed["quarantine"], "source_locator")
        wanted_sources, invalid_sources, events, minutes = set(), set(), {}, Counter()
        dispositions = Counter()
        with (directory / "wire.jsonl").open(encoding="utf-8", newline="\n") as wire:
            for row in expected:
                identifier = row["logical_record_id"]
                emission = by_id[identifier]
                check("UNADMITTED:" + identifier, emission["outcome"] == "acknowledged")
                source = coordinate(emission["source"])
                check("PHYSICAL_DELIVERY_COLLAPSED:" + identifier, source not in wanted_sources)
                wanted_sources.add(source)
                wire.seek(emission["wire_offset"])
                packet = json.loads(wire.readline())
                raw = base64.b64decode(packet["body"], validate=True)
                digest = hashlib.sha256(raw).hexdigest()
                # The SDK's source fingerprint covers key/value/ordered headers.
                # It is distinct from the scheduler's body-only wire SHA-256.
                source_digest = raw_fingerprint(
                    packet["key"].encode(),
                    raw,
                    tuple((name, value.encode()) for name, value in packet["headers"]),
                )
                check("WIRE_HASH:" + identifier, digest == emission["wire_sha256"])
                original = row["duplicate_of"]
                ordinal = row["record_ordinal"] if original is None else original
                identity = str(uuid5(UUID(context["run_id"]), f"source-{ordinal:06}"))
                check("PACKET_IDENTITY:" + identifier, packet["identity"] == identity)
                check("ACK_IDENTITY:" + identifier, emission["event_or_request_id"] == identity)
                check("TOPIC:" + identifier, packet["channel"] == source[0])
                if original is not None:
                    prior = by_id[f"source-{original:06}"]
                    check(
                        "DUPLICATE_PACKET_CHANGED:" + identifier,
                        prior["wire_offset"] == emission["wire_offset"]
                        and prior["wire_sha256"] == digest,
                    )
                receipt = receipts[source]
                archived = bronze[source]
                check(
                    "RECEIPT_NAMESPACE:" + identifier, receipt["namespace"] == context["namespace"]
                )
                check("RECEIPT_HASH:" + identifier, receipt["raw_sha256"] == source_digest)
                check(
                    "BRONZE_BYTES:" + identifier,
                    archived["value_base64"] == packet["body"]
                    and archived["key_base64"] == base64.b64encode(packet["key"].encode()).decode()
                    and archived["headers"] == packet["headers"],
                )
                disposition = row["expected_disposition"]
                dispositions[receipt["disposition"]] += 1
                check("DISPOSITION:" + identifier, receipt["disposition"] == disposition)
                check("REASON:" + identifier, receipt["reason_code"] == row["reason_code"])
                if disposition == "invalid":
                    invalid_sources.add(source)
                    item = quarantine[source]
                    check("INVALID_EVENT_ID:" + identifier, receipt["event_id"] is None)
                    check(
                        "QUARANTINE:" + identifier,
                        item["namespace"] == context["namespace"]
                        and item["raw_sha256"] == source_digest
                        and item["reason_code"] == row["reason_code"],
                    )
                    continue
                check("RECEIPT_EVENT_ID:" + identifier, receipt["event_id"] == identity)
                document = json.loads(raw)
                sku = context["selected_skus"][ordinal % 10000]
                check(
                    "INDEPENDENT_STOCK_FACT:" + identifier,
                    document["event_id"] == identity
                    and document["namespace"] == context["namespace"]
                    and document["run_id"] == context["run_id"]
                    and document["event_type"] == "STOCK_UPDATED"
                    and document["source_service"] == "benchmark"
                    and document["aggregate_type"] == "sku"
                    and document["aggregate_id"] == sku
                    and document["aggregate_version"] == ordinal // 10000 + 1
                    and document["metadata"]["dataset_revision"] == context["dataset_revision"]
                    and document["metadata"]["synthetic"] is True
                    and document["metadata"]["scenario_source"] == "benchmark"
                    and document["payload"]
                    == {
                        "sku": sku,
                        "stock_version": ordinal // 10000 + 1,
                        "on_hand": 10000,
                        "reserved": 0,
                        "available": 10000,
                        "order_id": None,
                        "reservation_id": None,
                        "reason_code": None,
                        "changed_at": document["event_time"],
                    },
                )
                content = hashlib.sha256(canonical_json(document)).hexdigest()
                if disposition == "new_valid":
                    check("DUPLICATE_LOGICAL_ID:" + identifier, identity not in events)
                    events[identity] = (content, document)
                    minute = (
                        datetime.fromisoformat(document["event_time"])
                        .replace(second=0, microsecond=0)
                        .isoformat()
                    )
                    minutes[minute] += 1
        check("EXACT_SOURCE_RECEIPTS", set(receipts) == wanted_sources)
        check("EXACT_BRONZE_MEMBERSHIP", set(bronze) == wanted_sources)
        check("EXACT_QUARANTINE_MEMBERSHIP", set(quarantine) == invalid_sources)
        silver = observed["silver"]
        check("EXACT_SILVER_IDS", Counter(r["event_id"] for r in silver) == Counter(events.keys()))
        for row in silver:
            content, document = events[row["event_id"]]
            payload = row["payload"]
            # Arrow's shared payload struct materializes unrelated domain fields
            # as null. Check every expected stock field and reject any non-null
            # extra; do not compare it to the sparse JSON object's key set.
            payload_matches = all(
                key in payload and payload[key] == value
                for key, value in document["payload"].items()
            ) and all(
                value is None for key, value in payload.items() if key not in document["payload"]
            )
            check(
                "SILVER_CONTENT:" + row["event_id"],
                row["namespace"] == context["namespace"]
                and row["content_hash"] == content
                and json.loads(row["envelope_json"]) == document
                and payload_matches,
            )
        gold = observed["gold"]
        check(
            "PINNED_ACTIVE_GOLD",
            type(gold["generation"]) is int
            and gold["generation"] > 0
            and gold["generation"] == gold["query_generation"]
            and gold["manifest_sha256"] == gold["query_manifest_sha256"]
            and re.fullmatch(r"[0-9a-f]{64}", gold["manifest_sha256"]) is not None,
        )
        check("EXACT_GOLD_IDS", Counter(gold["membership_ids"]) == Counter(events.keys()))
        actual_minutes = Counter()
        seen_minutes = set()
        for row in gold["rows"]:
            minute = datetime.fromisoformat(row["minute"]).isoformat()
            check(
                "GOLD_ROW",
                row["namespace"] == context["namespace"]
                and row["event_type"] == "STOCK_UPDATED"
                and row["source_service"] == "benchmark"
                and type(row["unique_events"]) is int
                and row["unique_events"] > 0
                and minute not in seen_minutes,
            )
            seen_minutes.add(minute)
            actual_minutes[minute] += row["unique_events"]
        check("INDEPENDENT_GOLD_TOTALS", actual_minutes == minutes)
        offsets = {(r["topic"], r["partition"]): r for r in observed["offsets"]}
        check("DUPLICATE_OFFSET_OBSERVATION", len(offsets) == len(observed["offsets"]))
        check("EXACT_OFFSET_TARGETS", set(offsets) == {(t, p) for t, p, _ in wanted_sources})
        for topic, partition in {(t, p) for t, p, _ in wanted_sources}:
            end = max(o for t, p, o in wanted_sources if (t, p) == (topic, partition)) + 1
            offset = offsets[(topic, partition)]
            check(
                "OFFSET_NOT_DRAINED:" + str((topic, partition)),
                type(offset["committed_next_offset"]) is int
                and type(offset["log_end_next_offset"]) is int
                and offset["committed_next_offset"] == offset["log_end_next_offset"] == end,
            )
        report["expected_counts"] = dict(Counter(r["expected_disposition"] for r in expected))
        report["observed_counts"] = dict(dispositions)
        report["physical_deliveries"] = len(wanted_sources)
        report["logical_events"] = len(events)
        batches = observed["sink_batches"]
        finalized, sequences, missing_timers = Counter(), set(), 0
        for batch in batches:
            check(
                "SINK_BATCH_SCOPE",
                batch["namespace"] == context["namespace"]
                and batch["run_id"] == context["run_id"]
                and batch["replay_id"] is None,
            )
            sequence = batch["batch_sequence"]
            check("DUPLICATE_SINK_BATCH", sequence not in sequences)
            sequences.add(sequence)
            check("B0_SINK_BATCH_ROWS", batch["batch_rows"] == len(batch["sources"]) == 1)
            counts = [
                batch[name]
                for name in ("new_valid", "duplicate_delivery", "invalid", "redelivery_noop")
            ]
            check(
                "SINK_BATCH_COUNTS",
                all(type(c) is int and c >= 0 for c in counts) and sum(counts) == 1,
            )
            for source in batch["sources"]:
                coord = coordinate(source)
                check("UNPLANNED_SINK_SOURCE", coord in wanted_sources)
                if batch["redelivery_noop"] == 0:
                    finalized[coord] += 1
                    check("SINK_RECEIPT_DISPOSITION", batch[receipts[coord]["disposition"]] == 1)
            missing_timers += batch["flush_duration_seconds"] is None
        check("COMPLETE_SINK_MEMBERSHIP", finalized == Counter(wanted_sources))
        report["sink_timers"] = {
            "sample_count": len(batches) - missing_timers,
            "missing_count": missing_timers,
            "latency": None,
            "status": "INCOMPLETE" if missing_timers else "NOT_RUN",
        }
        complete = observed["collection_complete"] is True
        reviewed = observed.get("binding_review_verified") is True
        report["passed"] = (
            False
            if failures
            else True
            if complete and (observed["test_mode"] == "stub" or reviewed)
            else None
        )
        report["status"] = "FAIL" if failures else "PASS" if report["passed"] else "INCOMPLETE"
    except (KeyError, TypeError, ValueError, OSError) as error:
        failures.append("MISSING_OR_INVALID_EVIDENCE:" + type(error).__name__)
        report.update(status="FAIL", passed=False)
    return report
