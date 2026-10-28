"""Namespace-scoped acknowledged fault boundaries; no process/shell fallback."""

import asyncio
import json
import math
import time

from benchmarks.scheduler import utc_now
from projectctl.providers import DependencyError


def validate_saved_fault(case, context, directory, row):
    """Replay the acknowledged boundary/recovery checks from retained journal facts."""
    if not (case.barrier or case.outage):
        return
    refs = row["fault_receipt_refs"]
    indexed = {ref["path"] for ref in row["artifact_refs"]}
    if len(refs) != 1 or refs[0] not in indexed:
        raise DependencyError("one indexed fault acknowledgement/recovery journal required")
    path = (directory / refs[0]).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise DependencyError("fault journal escapes the run")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if [r.get("phase") for r in records] != ["acknowledged", "injected", "recovered"]:
        raise DependencyError("fault acknowledgement/injection/recovery sequence incomplete")
    ack, injected, recovered = records
    expected = {
        "namespace": context["namespace"],
        "run_id": context["run_id"],
        "target": case.target,
        "barrier": case.barrier,
    }
    receipt = ack.get("receipt_id")
    if (
        not isinstance(receipt, str)
        or not receipt
        or ack.get("acknowledged") is not True
        or ack.get("case_id") != case.case_id
        or any(item.get(k) != v for item in (ack, injected) for k, v in expected.items())
        or any(item.get("receipt_id") != receipt for item in (injected, recovered))
    ):
        raise DependencyError("saved fault identity/acknowledgement mismatch")
    restart = recovered.get("restart", {})
    if (
        any(restart.get(k) != expected[k] for k in ("namespace", "run_id", "target"))
        or restart.get("ready") is not True
        or restart.get("retained_volume") is not True
    ):
        raise DependencyError("saved fault retained-volume recovery unavailable")
    elapsed, requested, recovery = (
        recovered.get(k)
        for k in ("outage_seconds", "restart_requested_after_seconds", "recovery_seconds")
    )
    if (
        any(
            type(v) not in {int, float} or not math.isfinite(v) or v < 0
            for v in (elapsed, requested, recovery)
        )
        or elapsed > (150 if case.outage else 120)
        or not math.isclose(elapsed, requested + recovery, abs_tol=0.01)
    ):
        raise DependencyError("saved fault recovery timing invalid")
    if case.outage:
        second = injected.get("measurement_second")
        if (
            type(second) not in {int, float}
            or not math.isfinite(second)
            or abs(second - 180) > 1
            or requested < 30
            or elapsed < 30
        ):
            raise DependencyError("saved outage must start at second 180 and last 30 seconds")


class FaultGate:
    """Owner hook methods: arm, wait, stop, restart. All receive scoped context.

    A timed outage runs concurrently with the caller's checkout workload. The
    context's measurement origin must be captured when measurement actually starts.
    Test clocks are injected explicitly, never substituted in production.
    """

    def __init__(self, case, context, hooks, emit, *, clock=time.perf_counter, sleep=asyncio.sleep):
        self.case, self.context, self.hooks, self.emit = case, context, hooks, emit
        self.clock, self.sleep = clock, sleep
        self.completed = False
        self.used = False

    async def run(self, *, measurement_origin=None):
        case, ctx = self.case, self.context
        if self.used or not (case.barrier or case.outage) or self.hooks is None:
            raise DependencyError("named fault binding unavailable or already used")
        self.used = True
        if case.outage:
            if (
                type(measurement_origin) not in {float, int}
                or not math.isfinite(measurement_origin)
                or measurement_origin > self.clock()
            ):
                raise DependencyError("actual monotonic measurement origin required")
            await self.sleep(max(0, measurement_origin + 180 - self.clock()))
            if abs(self.clock() - measurement_origin - 180) > 1:
                raise DependencyError("outage missed measurement second 180")
        receipt = await asyncio.wait_for(self.hooks.arm(ctx, case.barrier, case.target), 120)
        ack = await asyncio.wait_for(self.hooks.wait(ctx, receipt), 120)
        safe_ack = {
            key: ack.get(key)
            for key in (
                "namespace",
                "run_id",
                "case_id",
                "target",
                "barrier",
                "receipt_id",
                "acknowledged",
            )
        }
        if (
            ack.get("namespace") != ctx["namespace"]
            or ack.get("run_id") != ctx["run_id"]
            or ack.get("case_id") != case.case_id
            or ack.get("target") != case.target
            or ack.get("barrier") != case.barrier
            or ack.get("acknowledged") is not True
            or not isinstance(ack.get("receipt_id"), str)
            or not ack["receipt_id"]
        ):
            self.emit({**safe_ack, "phase": "rejected_ack", "at": utc_now()})
            raise DependencyError("fault barrier acknowledgement missing or mismatched")
        self.emit({**safe_ack, "phase": "acknowledged", "at": utc_now()})
        stopped = self.clock()
        if case.outage and abs(stopped - measurement_origin - 180) > 1:
            raise DependencyError("acknowledgement missed measurement second 180")
        try:
            # Restart is attempted even if stop loses its HTTP response.
            await asyncio.wait_for(self.hooks.stop(ctx, ack), 120)
            self.emit(
                {
                    "phase": "injected",
                    "at": utc_now(),
                    "target": case.target,
                    "barrier": case.barrier,
                    "receipt_id": ack["receipt_id"],
                    "namespace": ctx["namespace"],
                    "run_id": ctx["run_id"],
                    "measurement_second": stopped - measurement_origin
                    if measurement_origin is not None
                    else None,
                }
            )
            if case.outage:
                await self.sleep(max(0, stopped + 30 - self.clock()))
        finally:
            restart_requested = self.clock()
            restart = await asyncio.wait_for(self.hooks.restart(ctx, ack), 120)
            elapsed = self.clock() - stopped
            self.emit(
                {
                    "phase": "recovered",
                    "at": utc_now(),
                    "outage_seconds": elapsed,
                    "restart_requested_after_seconds": restart_requested - stopped,
                    "recovery_seconds": self.clock() - restart_requested,
                    "receipt_id": ack["receipt_id"],
                    "restart": restart,
                }
            )
        if (
            restart.get("namespace") != ctx["namespace"]
            or restart.get("run_id") != ctx["run_id"]
            or restart.get("target") != case.target
            or restart.get("ready") is not True
            or restart.get("retained_volume") is not True
            or not 0 <= elapsed <= (150 if case.outage else 120)
            or (case.outage and elapsed < 30)
        ):
            raise DependencyError("retained-volume recovery proof/deadline missing")
        self.completed = True
