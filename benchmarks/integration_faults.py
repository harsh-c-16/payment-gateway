"""Namespace-scoped acknowledged fault boundaries; no process/shell fallback."""

import asyncio
import math
import time

from benchmarks.scheduler import utc_now
from projectctl.providers import DependencyError


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
