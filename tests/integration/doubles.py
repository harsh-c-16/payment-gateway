"""Small explicit event/audit/hook doubles. Never production registrations."""

import copy
import json

from benchmarks.integration import CaseBinding
from benchmarks.integration_cases import BY_ID


def event_evidence(namespace):
    expected = {
        "namespace": namespace,
        "events": {"valid": "a" * 64},
        "source_dispositions": {
            "first": "new_valid",
            "duplicate": "duplicate_delivery",
            "invalid": "invalid",
        },
        "source_manifest_ids": ["source-manifest"],
        "gold_totals_by_currency": {},
        "gold_business_rows": {"pipeline_minute": {"event_count": 1}},
        "orders": {},
        "opening_stock": {},
        "replenishment": {},
        "bronze_sha256": {"first": "a" * 64, "duplicate": "a" * 64, "invalid": "b" * 64},
    }
    audit = {
        "namespace": namespace,
        "test_mode": "stub",
        "collection_complete": True,
        "source_dispositions": [
            {"record_id": key, "disposition": value}
            for key, value in expected["source_dispositions"].items()
        ],
        "silver_events": [{"event_id": "valid", "content_sha256": "a" * 64}],
        "active_gold": {
            "namespace": namespace,
            "generation": 1,
            "query_generation": 1,
            "manifest_sha256": "c" * 64,
            "query_manifest_sha256": "c" * 64,
            "source_manifest_ids": ["source-manifest"],
            "membership_ids": ["valid"],
            "visibility_receipts": [
                {"event_id": "valid", "generation": 1, "manifest_sha256": "c" * 64}
            ],
            "totals_by_currency": {},
            "business_rows": copy.deepcopy(expected["gold_business_rows"]),
        },
        "orders": [],
        "reservations": [],
        "payments": [],
        "ledger": [],
        "stocks": [],
        "payment_guards": {},
    }
    return expected, audit


class EventCaseDouble:
    def __init__(self, directory, *, corrupt=None, mode="stub", exercise_error=None):
        self.calls, self.corrupt, self.exercise_error = [], corrupt, exercise_error
        expected, _ = event_evidence("bench-fixture")
        self.fixture_path = directory / "fixture-input.json"
        self.fixture_path.write_text(
            json.dumps({"case_id": "smoke/G1", "input": {"seed": 42}, "expected": expected}),
            encoding="utf-8",
        )
        self.binding = CaseBinding(mode, self.fixture_path, self.prepare, self.exercise, self.audit)

    async def prepare(self, context):
        self.calls.append("prepare")
        return {"namespace": context["namespace"], "created_new": True}

    async def exercise(self, context, fixture, gate):
        self.calls.append("exercise")
        # Prove fixture input is already saved and cannot change the oracle's answer.
        from pathlib import Path

        assert (Path(context["directory"]) / "fixture.json").exists()
        fixture["expected"]["events"].clear()
        if self.exercise_error:
            raise self.exercise_error("sensitive DSN must never enter exported failure text")

    async def audit(self, context):
        self.calls.append("audit")
        expected, audit = event_evidence(context["namespace"])
        result = {
            "namespace": context["namespace"],
            "run_id": context["run_id"],
            "case_id": "smoke/G1",
            "collection_complete": True,
            "facts": dict(BY_ID["smoke/G1"].checks),
            "audit": audit,
            "quarantine": [{"record_id": "invalid"}],
            "bronze": [
                {
                    "record_id": key,
                    "wire_sha256": value,
                    "topic": "fixture",
                    "partition": 0,
                    "offset": index,
                }
                for index, (key, value) in enumerate(expected["bronze_sha256"].items())
            ],
        }
        if self.corrupt:
            self.corrupt(result)
        return result


class ClockDouble:
    def __init__(self):
        self.now = 10.0

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.now += seconds


class HookDouble:
    def __init__(self, *, bad_ack=False, retained=True, stop_error=False):
        self.calls = []
        self.bad_ack, self.retained, self.stop_error = bad_ack, retained, stop_error

    async def arm(self, ctx, barrier, target):
        self.calls.append("arm")
        return {key: ctx[key] for key in ("namespace", "run_id", "case_id")} | {
            "barrier": barrier,
            "target": target,
            "receipt_id": "explicit-hook-double",
        }

    async def wait(self, ctx, receipt):
        self.calls.append("ack")
        return receipt | {
            "acknowledged": True,
            "namespace": "dev" if self.bad_ack else ctx["namespace"],
        }

    async def stop(self, ctx, receipt):
        self.calls.append("stop")
        if self.stop_error:
            raise ConnectionError("explicit response loss")

    async def restart(self, ctx, receipt):
        self.calls.append("restart")
        return {
            "namespace": ctx["namespace"],
            "run_id": ctx["run_id"],
            "target": receipt["target"],
            "ready": True,
            "retained_volume": self.retained,
        }
