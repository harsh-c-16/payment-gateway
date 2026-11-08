"""W-PIPE evidence projection into the existing independent reconciliation oracle."""

import base64
import hashlib
import json
from collections import Counter
from datetime import datetime
from uuid import UUID, uuid5

from benchmarks.reconciliation import reconcile_run
from projectctl.artifacts import canonical_json
from shared.event_transport.consumer import raw_fingerprint


def rows(path):
    with path.open(encoding="utf-8") as stream:
        yield from (json.loads(line) for line in stream)


def audit_pipeline(context, directory, raw, *, review=None):
    """Expectations come from the frozen plan and emitted bytes, never Gold/Silver totals."""
    failures = []
    planned = {r["logical_record_id"]: r for r in rows(directory / "planned.jsonl")}
    emissions = list(rows(directory / "emissions.jsonl"))
    receipts = {
        (r["source"]["topic"], r["source"]["partition"], r["source"]["offset"]): r
        for r in raw["receipts"]
    }
    bronze = {
        (r["source"]["topic"], r["source"]["partition"], r["source"]["offset"]): r
        for r in raw["bronze"]
    }
    events, documents, dispositions, minutes, visibility = {}, {}, {}, Counter(), []
    complete = raw["collection_complete"] is True
    with (directory / "wire.jsonl").open(encoding="utf-8", newline="\n") as wire:
        for emission in emissions:
            if emission["outcome"] != "acknowledged":
                complete &= emission["outcome"] != "unresolved"
                continue
            logical = planned[emission["record_id"]]
            wire.seek(emission["wire_offset"])
            packet = json.loads(wire.readline())
            body = base64.b64decode(packet["body"], validate=True)
            document = json.loads(body)
            identity = str(uuid5(UUID(context["run_id"]), emission["record_id"]))
            expected_payload = {
                k: logical["payload"][k]
                for k in (
                    "sku",
                    "stock_version",
                    "on_hand",
                    "reserved",
                    "available",
                    "order_id",
                    "reservation_id",
                    "reason_code",
                )
            } | {"changed_at": emission["scheduled_at"]}
            if (
                document["event_id"] != identity
                or packet["identity"] != identity
                or document["namespace"] != context["namespace"]
                or document["run_id"] != context["run_id"]
                or document["event_type"] != "STOCK_UPDATED"
                or document["source_service"] != "benchmark"
                or document["aggregate_type"] != "sku"
                or document["aggregate_id"] != logical["payload"]["sku"]
                or document["aggregate_version"] != logical["payload"]["stock_version"]
                or document["metadata"]["synthetic"] is not True
                or document["metadata"]["scenario_source"] != "benchmark"
                or document["payload"] != expected_payload
                or hashlib.sha256(body).hexdigest() != emission["wire_sha256"]
            ):
                failures.append("WIRE_DIFFERS_FROM_PLAN:" + emission["record_id"])
            source = emission["source"]
            coordinate = (source["topic"], source["partition"], source["offset"])
            receipt, captured = receipts.get(coordinate), bronze.get(coordinate)
            if receipt is None or captured is None:
                failures.append("MISSING_ACKNOWLEDGED_SOURCE:" + identity)
                continue
            if receipt["event_id"] != identity or receipt["namespace"] != context["namespace"]:
                failures.append("WRONG_RECEIPT_IDENTITY:" + identity)
            headers = tuple((k, v.encode()) for k, v in packet["headers"])
            if (
                base64.b64decode(captured["value_base64"]) != body
                or base64.b64decode(captured["key_base64"]) != packet["key"].encode()
                or captured["headers"] != packet["headers"]
                or receipt["raw_sha256"] != raw_fingerprint(packet["key"].encode(), body, headers)
            ):
                failures.append("BRONZE_BYTES_CHANGED:" + identity)
            key = json.dumps(coordinate)
            dispositions[key] = "new_valid"
            if identity in events:
                failures.append("DUPLICATE_LOGICAL_EVENT:" + identity)
            events[identity] = hashlib.sha256(canonical_json(document)).hexdigest()
            documents[identity] = document
            minute = datetime.fromisoformat(document["event_time"]).replace(second=0, microsecond=0)
            minutes[minute.isoformat()] += 1
            if receipt["gold_visible_at"] is not None:
                visibility.append(
                    {
                        "event_id": identity,
                        "generation": raw["gold"]["generation"],
                        "manifest_sha256": raw["gold"]["manifest_sha256"],
                    }
                )
    actual_minutes = Counter()
    for row in raw["gold"]["rows"]:
        minute = datetime.fromisoformat(row["minute"]).isoformat()
        if (
            row["event_type"] != "STOCK_UPDATED"
            or row["source_service"] != "benchmark"
            or row["namespace"] != context["namespace"]
            or type(row["unique_events"]) is not int
            or row["unique_events"] <= 0
            or minute in actual_minutes
        ):
            failures.append("UNEXPECTED_GOLD_FACT")
        actual_minutes[minute] += row["unique_events"]
    if actual_minutes != minutes or raw["quarantine"]:
        failures.append("WRONG_STOCK_COUNTS_OR_QUARANTINE")
    for row in raw["silver"]:
        document = documents.get(row["event_id"])
        if document is None or (
            json.loads(row["envelope_json"]) != document
            or any(row["payload"].get(k) != v for k, v in document["payload"].items())
            or any(v is not None for k, v in row["payload"].items() if k not in document["payload"])
        ):
            failures.append("WRONG_SILVER_FACT:" + row["event_id"])
    source_ids = raw["silver_manifest"]["input_manifest_ids"]
    if raw["silver_manifest"]["generation"] != raw["gold"]["generation"]:
        failures.append("UNPAIRED_PUBLICATION")
    expected = {
        "namespace": context["namespace"],
        "events": events,
        "source_dispositions": dispositions,
        "source_manifest_ids": source_ids,
        "gold_totals_by_currency": {},
        "gold_business_rows": [],
        "orders": {},
        "opening_stock": {},
        "replenishment": {},
    }
    gold = raw["gold"] | {
        "source_manifest_ids": raw["gold"]["manifest"]["input_manifest_ids"],
        "totals_by_currency": {},
        "business_rows": [],
        "visibility_receipts": visibility,
    }
    observed = {
        "namespace": raw["namespace"],
        "test_mode": raw["test_mode"],
        "collection_complete": complete,
        "source_dispositions": [
            {
                "record_id": json.dumps(
                    (r["source"]["topic"], r["source"]["partition"], r["source"]["offset"])
                ),
                "disposition": r["disposition"],
            }
            for r in raw["receipts"]
        ],
        "silver_events": [
            {"event_id": r["event_id"], "content_sha256": r["content_hash"]} for r in raw["silver"]
        ],
        "active_gold": gold,
        "orders": [],
        "reservations": [],
        "payments": [],
        "payment_guards": {},
        "ledger": [],
        "stocks": [],
    }
    report = reconcile_run(expected, observed, binding_review=review)
    report["reconciliation"]["invariant_failures"].extend(failures)
    if failures:
        report["status"], report["reconciliation"]["passed"] = "FAIL", False
    report["passed"] = None if report["status"] == "INCOMPLETE" else report["status"] == "PASS"
    return report
