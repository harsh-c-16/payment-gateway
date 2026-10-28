"""P4 test-only publisher/lifecycle adapters, never production registrations."""

import asyncio
import json

from benchmarks.experiment import ExperimentBindings
from benchmarks.scheduler import Packet, Receipt
from projectctl.artifacts import canonical_json


class SlowPublisher:
    def __init__(self, delay=0.04, body_bytes=1024, outcome="accepted"):
        self.delay, self.body_bytes, self.outcome = delay, body_bytes, outcome
        self.packets, self.offset = [], 0

    def materialize(self, record, context):
        # This is deliberately NOT a canonical event or a real SDK substitute.
        body = canonical_json({"test_only": True, "record": record})
        return Packet(context["request_id"], body.ljust(self.body_bytes, b" "), "kafka", "test-key")

    async def send(self, packet, context, mark_send):
        mark_send()
        self.packets.append(packet)
        await asyncio.sleep(self.delay)
        offset = self.offset
        self.offset += 1
        return Receipt(
            packet.identity,
            self.outcome,
            source={"topic": context["topic"], "partition": 0, "offset": offset},
        )


class LifecycleDouble:
    def __init__(self, publisher=None, *, audit_passed=True, fail_stage=None):
        self.publisher = publisher or SlowPublisher(delay=0)
        self.audit_passed, self.fail_stage = audit_passed, fail_stage
        self.calls = []

    async def prepare(self, context, manifest):
        self.calls.append(("prepare", context["namespace"]))
        if self.fail_stage == "prepare":
            raise ConnectionError("explicit missing provider")
        return {"namespace": context["namespace"], "created_new": True, "test_only": True}

    async def validate(self, context, manifest):
        self.calls.append(("validate", context["namespace"]))
        if self.fail_stage == "validate":
            raise ConnectionError("explicit invalid provider")

    async def drain(self, context, deadline):
        self.calls.append(("drain", context["namespace"]))
        if self.fail_stage == "drain":
            raise TimeoutError("explicit downstream stall")

    async def audit(self, context, directory):
        self.calls.append(("audit", context["namespace"]))
        expected = [
            json.loads(line) for line in (directory / "planned.jsonl").read_text().splitlines()
        ]
        # Tests deliberately control the independent downstream verdict. This is
        # admission/lifecycle evidence, never active-Gold or business evidence.
        return {
            "passed": self.audit_passed,
            "test_mode": "stub",
            "expected_record_count": len(expected),
            "test_only": True,
        }

    def bindings(self, **kwargs):
        return ExperimentBindings(
            mode="stub",
            driver=self.publisher,
            catalog_manifest={"active_skus": ["TEST-SKU-000", "TEST-SKU-001"], "synthetic": True},
            prepare=self.prepare,
            validate=self.validate,
            drain=self.drain,
            audit=self.audit,
            **kwargs,
        )
