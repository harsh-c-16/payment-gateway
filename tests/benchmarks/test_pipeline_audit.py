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
        "run_id": context["run_id"],
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


@pytest.mark.parametrize(
    "corrupt",
    [
        "run_id",
        "extra_bronze",
        "duplicate_bronze",
        "missing_emission",
        "duplicate_emission",
        "event_time",
    ],
)
def test_reviewed_boundary_cannot_hide_missing_or_foreign_evidence(tmp_path, corrupt):
    context, raw = fixture(tmp_path)
    if corrupt == "run_id":
        raw["run_id"] = "another-run"
    elif corrupt == "extra_bronze":
        raw["bronze"].append(
            raw["bronze"][0] | {"source": raw["bronze"][0]["source"] | {"offset": 99}}
        )
    elif corrupt == "duplicate_bronze":
        raw["bronze"].append(raw["bronze"][0])
    elif corrupt == "missing_emission":
        (tmp_path / "emissions.jsonl").write_text("")
    elif corrupt == "duplicate_emission":
        path = tmp_path / "emissions.jsonl"
        path.write_text(path.read_text() * 2)
    else:
        # Alter all observed copies consistently: the frozen scheduled time still wins.
        path = tmp_path / "wire.jsonl"
        packet = json.loads(path.read_text())
        document = json.loads(base64.b64decode(packet["body"]))
        document["event_time"] = "2026-11-08T00:01:00Z"
        body = canonical_json(document)
        packet["body"] = base64.b64encode(body).decode()
        path.write_text(json.dumps(packet) + "\n")
    assert audit_pipeline(context, tmp_path, raw)["passed"] is False


def test_saved_real_projection_rebuilds_from_wire_and_raw_export(tmp_path, monkeypatch):
    from benchmarks.analytics_recheck import recheck
    from projectctl.artifacts import write_json

    context, raw = fixture(tmp_path)
    context["workload_id"] = "W-PIPE"
    raw["test_mode"] = "real"
    review = {
        "namespace": context["namespace"],
        "review_sha256": "f" * 64,
        "reviewers": ["Jaineel", "Harsh", "Aditya", "Vichitr"],
        "contracts": [
            {"path": path, "sha256": "a" * 64}
            for path in (
                "benchmarks/analytics_recheck.py",
                "benchmarks/pipeline_audit.py",
                "infra/analytics_runtime.py",
                "infra/analytics_resources.py",
                "pipelines/ingestion/adapters.py",
            )
        ],
    }
    # Explicit review double: no team receipt is produced by this unit test.
    monkeypatch.setattr("projectctl.config.ROOT", tmp_path)
    monkeypatch.setattr("benchmarks.analytics_recheck.verify_review", lambda _: review)
    result = audit_pipeline(context, tmp_path, raw, review=review)
    assert result["passed"] is True
    write_json(tmp_path / "analytics_raw_evidence.json", raw)
    expected = json.loads((tmp_path / "expected.json").read_text("utf-8"))
    assert recheck(tmp_path, context, expected)["passed"] is True
    # A later corrupted Gold fact cannot hide behind the previously saved PASS.
    raw["gold"]["rows"][0]["unique_events"] = 2
    (tmp_path / "analytics_raw_evidence.json").write_text(json.dumps(raw), encoding="utf-8")
    assert recheck(tmp_path, context, expected)["passed"] is False
