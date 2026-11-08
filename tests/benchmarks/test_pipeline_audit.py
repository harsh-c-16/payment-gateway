"""Independent wire-to-export projection with explicit tiny harness/SUT evidence."""

import base64
import hashlib
import json
from uuid import UUID, uuid5

import pytest

from benchmarks.pipeline_audit import audit_pipeline
from projectctl.artifacts import canonical_json
from shared.event_transport.consumer import raw_fingerprint


def fixture(directory):
    context = {"namespace": "bench-wire", "run_id": "00000000-0000-4000-8000-000000000001"}
    identity = str(uuid5(UUID(context["run_id"]), "stock-1"))
    stamp = "2026-11-08T00:00:00Z"
    payload = {
        "sku": "FK-fixture",
        "stock_version": 1,
        "on_hand": 10000,
        "reserved": 0,
        "available": 10000,
        "order_id": None,
        "reservation_id": None,
        "reason_code": "SEED",
    }
    document = {
        "event_id": identity,
        "namespace": context["namespace"],
        "run_id": context["run_id"],
        "event_time": stamp,
        "event_type": "STOCK_UPDATED",
        "source_service": "benchmark",
        "aggregate_type": "sku",
        "aggregate_id": "FK-fixture",
        "aggregate_version": 1,
        "metadata": {"synthetic": True, "scenario_source": "benchmark"},
        "payload": payload | {"changed_at": stamp},
    }
    body = canonical_json(document)
    source = {"topic": "bench-wire.inventory-events.v1", "partition": 0, "offset": 0}
    encoded = base64.b64encode(body).decode()
    for name, row in {
        "planned": {"logical_record_id": "stock-1", "payload": payload},
        "emissions": {
            "record_id": "stock-1",
            "outcome": "acknowledged",
            "wire_offset": 0,
            "source": source,
            "wire_sha256": hashlib.sha256(body).hexdigest(),
            "scheduled_at": stamp,
        },
        "wire": {"identity": identity, "body": encoded, "key": "FK-fixture", "headers": []},
    }.items():
        (directory / (name + ".jsonl")).write_text(json.dumps(row) + "\n")
    raw = {
        "namespace": context["namespace"],
        "test_mode": "stub",
        "collection_complete": True,
        "receipts": [
            {
                "source": source,
                "namespace": context["namespace"],
                "event_id": identity,
                "disposition": "new_valid",
                "gold_visible_at": stamp,
                "raw_sha256": raw_fingerprint(b"FK-fixture", body, ()),
            }
        ],
        "bronze": [
            {
                "source": source,
                "value_base64": encoded,
                "headers": [],
                "key_base64": base64.b64encode(b"FK-fixture").decode(),
            }
        ],
        "quarantine": [],
        "silver": [
            {
                "event_id": identity,
                "content_hash": hashlib.sha256(body).hexdigest(),
                "envelope_json": body.decode(),
                "payload": document["payload"].copy(),
            }
        ],
        "silver_manifest": {"generation": 1, "input_manifest_ids": ["lineage"]},
        "gold": {
            "generation": 1,
            "query_generation": 1,
            "manifest_sha256": "a" * 64,
            "query_manifest_sha256": "a" * 64,
            "namespace": context["namespace"],
            "membership_ids": [identity],
            "manifest": {"input_manifest_ids": ["lineage"]},
            "rows": [
                {
                    "namespace": context["namespace"],
                    "minute": stamp,
                    "event_type": "STOCK_UPDATED",
                    "source_service": "benchmark",
                    "unique_events": 1,
                }
            ],
        },
    }
    return context, raw


def test_wire_receipts_silver_and_gold_agree(tmp_path):
    context, raw = fixture(tmp_path)
    assert audit_pipeline(context, tmp_path, raw)["passed"] is True


@pytest.mark.parametrize("corrupt", ["silver", "gold", "lineage", "receipt"])
def test_oracle_rejects_corrupted_projections_even_if_counts_look_valid(tmp_path, corrupt):
    context, raw = fixture(tmp_path)
    if corrupt == "silver":
        raw["silver"][0]["payload"]["on_hand"] = 999
    elif corrupt == "gold":
        raw["gold"]["rows"][0]["unique_events"] = 2
    elif corrupt == "lineage":
        raw["gold"]["manifest"]["input_manifest_ids"] = ["wrong"]
    else:
        raw["receipts"][0]["event_id"] = "wrong"
    assert audit_pipeline(context, tmp_path, raw)["passed"] is False


def test_unreviewed_real_mapping_is_never_declared_passed(tmp_path):
    context, raw = fixture(tmp_path)
    raw["test_mode"] = "real"
    result = audit_pipeline(context, tmp_path, raw)
    assert result["status"] == "INCOMPLETE" and result["passed"] is None
