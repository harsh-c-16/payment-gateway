"""Open-loop pacing with bounded active+queued records/bytes and durable journals."""

import asyncio
import base64
import hashlib
import json
import math
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid5

from projectctl.artifacts import canonical_json, write_json


def utc_now():
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def journal(stream, value):
    stream.write(canonical_json(value).decode("utf-8") + "\n")
    stream.flush()


async def sleep_until(deadline):
    """Recheck the elapsed clock: event-loop timers can wake early on Windows."""
    while (remaining := deadline - time.perf_counter()) > 0:
        await asyncio.sleep(remaining)


@dataclass(frozen=True)
class Packet:
    identity: str
    body: bytes
    channel: str
    key: str | None = None
    headers: tuple = ()


@dataclass(frozen=True)
class Receipt:
    identity: str
    status: str  # accepted / rejected / unknown
    source: dict | None = None
    details: dict | None = None


class AckError(ValueError):
    """An acknowledgement violated the correlation/admission contract."""


class MissedSchedule(TimeoutError):
    """No operation was submitted before its measurement cutoff."""


@dataclass(frozen=True)
class Limits:
    concurrency: int = 32
    pending_count: int = 10000
    pending_bytes: int = 64 * 1024 * 1024

    def __post_init__(self):
        if any(
            type(v) is not int or v <= 0
            for v in (self.concurrency, self.pending_count, self.pending_bytes)
        ):
            raise ValueError("positive integer scheduler limits required")
        if self.pending_count > 10000 or self.pending_bytes > 64 * 1024 * 1024:
            raise ValueError("producer bounds exceed common Appendix A")


async def run_schedule(
    planned_path: Path,
    directory: Path,
    driver,
    context,
    *,
    kind,
    warmup_seconds,
    duration_seconds,
    drain_seconds,
    limits=None,
    boundary=None,
    telemetry=None,
):
    """Driver.send(packet, context, mark_send) must cooperate with cancellation.

    One fixed worker pool. No per-offer task, waiting for queue space, retry,
    shifted arrival, or silent catch-up after the measurement cutoff.
    """
    if not math.isfinite(drain_seconds) or not 0 < drain_seconds <= 120:
        raise ValueError("drain deadline must be in (0,120] seconds")
    limits = limits or Limits()
    queue = asyncio.Queue()
    capacity = asyncio.Event()
    pending_count = pending_bytes = peak_count = peak_bytes = 0
    counters = {phase: Counter() for phase in ("warmup", "measurement")}
    active = {}
    start, wall = time.perf_counter(), datetime.now(UTC)
    cutoff = start + warmup_seconds + duration_seconds if kind == "sustained" else None
    measured_started = None
    cutoff_snapshot = None
    phase_seen, wire_offsets = set(), {}
    operation_context = dict(context)

    def record_queue():
        if telemetry is not None:
            telemetry.record("benchmark_pending_records", pending_count)
            telemetry.record("benchmark_pending_bytes", pending_bytes)

    def stamp(offset):
        return (wall + timedelta(seconds=offset)).isoformat().replace("+00:00", "Z")

    def snapshot():
        return {
            "at": utc_now(),
            "elapsed_seconds": time.perf_counter() - start,
            "phases": {k: dict(v) for k, v in counters.items()},
            "pending_count": pending_count,
            "pending_bytes": pending_bytes,
            "peak_pending_count": peak_count,
            "peak_pending_bytes": peak_bytes,
        }

    def enter(phase):
        nonlocal measured_started
        if phase not in phase_seen:
            phase_seen.add(phase)
            if phase == "measurement":
                measured_started = time.perf_counter()
            if boundary:
                boundary(phase, snapshot())

    def finish(row, status, error=None, receipt=None):
        phase = row["phase"]
        counters[phase][status] += 1
        at = time.perf_counter()
        if telemetry is not None and status == "acknowledged":
            phase_end = start + (
                warmup_seconds if phase == "warmup" else warmup_seconds + duration_seconds
            )
            if cutoff is None or at < phase_end:
                telemetry.record("benchmark_admitted_total", 1, phase=phase)
        row |= {
            "outcome": status,
            "error": error,
            "completed_at": utc_now(),
            "completed_elapsed_seconds": at - start,
            "ack_at": utc_now() if receipt and status == "acknowledged" else None,
            "ack_elapsed_seconds": at - start if receipt and status == "acknowledged" else None,
            "source": receipt.source if receipt else None,
            "details": receipt.details if receipt else None,
        }
        journal(emissions, row)

    async def worker():
        nonlocal pending_count, pending_bytes
        while True:
            row, packet, local_context = await queue.get()
            active[row["record_id"]] = row

            def mark_send(row=row):
                if row["actual_send_at"] is not None:
                    raise ValueError("driver attempted to mark a second logical submission")
                now = time.perf_counter()
                # Quotes may be prepared first; never start a new submission after cutoff.
                if cutoff is not None and now >= cutoff:
                    raise MissedSchedule("submission missed measurement cutoff")
                counters[row["phase"]]["attempted"] += 1
                row.update(
                    actual_send_at=utc_now(),
                    actual_send_elapsed_seconds=now - start,
                    scheduling_delay_seconds=now - start - row["scheduled_elapsed_seconds"],
                )
                journal(attempts, row)

            try:
                receipt = await driver.send(packet, local_context, mark_send)
                if not isinstance(receipt, Receipt) or receipt.identity != packet.identity:
                    raise AckError("acknowledgement identity mismatch")
                if row["actual_send_at"] is None or receipt.status not in {
                    "accepted",
                    "rejected",
                    "unknown",
                }:
                    raise AckError("invalid acknowledgement contract")
                if receipt.status == "accepted" and packet.channel == "kafka":
                    source = receipt.source or {}
                    if (
                        source.get("topic") != local_context["topic"]
                        or type(source.get("partition")) is not int
                        or source["partition"] < 0
                        or type(source.get("offset")) is not int
                        or source["offset"] < 0
                    ):
                        raise AckError("broker acknowledgement missing source coordinates")
                finish(
                    row,
                    {"accepted": "acknowledged", "rejected": "failed", "unknown": "unresolved"}[
                        receipt.status
                    ],
                    receipt=receipt,
                )
            except MissedSchedule:
                finish(row, "missed", "measurement_cutoff_before_send")
            except asyncio.CancelledError:
                finish(row, "unresolved" if row["actual_send_at"] else "missed", "drain_deadline")
                raise
            except Exception as exc:
                unknown = row["actual_send_at"] is not None
                if hasattr(exc, "outcome_unknown"):
                    unknown = exc.outcome_unknown
                elif isinstance(getattr(exc, "status", None), int):
                    unknown = False  # explicit HTTP rejection response, not response loss
                finish(row, "unresolved" if unknown else "failed", type(exc).__name__)
            finally:
                active.pop(row["record_id"], None)
                pending_count -= 1
                pending_bytes -= len(packet.body)
                record_queue()
                queue.task_done()
                capacity.set()

    with (
        (directory / "attempts.jsonl").open("x", encoding="utf-8") as attempts,
        (directory / "emissions.jsonl").open("x", encoding="utf-8") as emissions,
        (directory / "wire.jsonl").open("x+", encoding="utf-8", newline="\n") as wire,
        (directory / "queue.jsonl").open("x", encoding="utf-8") as pressure,
    ):
        workers = [asyncio.create_task(worker()) for _ in range(limits.concurrency)]

        async def phase_clock():
            await sleep_until(start + warmup_seconds)
            enter("measurement")
            await sleep_until(cutoff)
            capture_cutoff()

        def capture_cutoff():
            nonlocal cutoff_snapshot
            if cutoff_snapshot is None:
                cutoff_snapshot = snapshot() | {
                    "scheduled_cutoff_elapsed_seconds": warmup_seconds + duration_seconds
                    if cutoff is not None
                    else None,
                }
                write_json(directory / "cutoff.json", cutoff_snapshot)
                enter("drain")

        if kind == "sustained":
            enter("warmup")
        phase_task = asyncio.create_task(phase_clock()) if kind == "sustained" else None
        try:
            with planned_path.open(encoding="utf-8") as planned:
                for line in planned:
                    logical = json.loads(line)
                    offset = logical["offset_seconds"]
                    if offset is not None:
                        await sleep_until(start + offset)
                    elif kind == "queries":
                        # A hanging query cannot prevent reaching a bounded failure.
                        async with asyncio.timeout(drain_seconds):
                            await queue.join()
                    else:
                        await asyncio.sleep(0)  # fair worker scheduling for finite fixtures
                    enter(logical["phase"])
                    phase = logical["phase"]
                    counters[phase]["planned"] += 1
                    if telemetry is not None:
                        telemetry.record("benchmark_planned_total", 1, phase=phase)
                    request_id = str(uuid5(UUID(context["run_id"]), logical["logical_record_id"]))
                    local = operation_context | {"request_id": request_id, "record": logical}
                    row = {
                        "record_id": logical["logical_record_id"],
                        "scenario_id": logical["scenario_id"],
                        "event_or_request_id": request_id,
                        "phase": phase,
                        "expected_disposition": logical["expected_disposition"],
                        "scheduled_at": stamp(offset) if offset is not None else utc_now(),
                        "scheduled_elapsed_seconds": offset
                        if offset is not None
                        else time.perf_counter() - start,
                        "actual_send_at": None,
                        "actual_send_elapsed_seconds": None,
                        "scheduling_delay_seconds": None,
                        "scheduling_lateness_at_offer_seconds": max(
                            0, time.perf_counter() - start - (offset or 0)
                        )
                        if offset is not None
                        else None,
                        "wire_offset": None,
                        "wire_sha256": None,
                        "pending_count_at_offer": pending_count,
                        "pending_bytes_at_offer": pending_bytes,
                    }
                    local |= {"scheduled_at": row["scheduled_at"], "produced_at": utc_now()}
                    if cutoff is not None and time.perf_counter() >= cutoff:
                        finish(row, "missed", "measurement_cutoff")
                        journal(
                            pressure,
                            snapshot()
                            | {"record_id": row["record_id"], "pressure": "measurement_cutoff"},
                        )
                        continue
                    try:
                        original = logical.get("duplicate_of")
                        if original is not None:
                            wire.seek(wire_offsets[original])
                            saved = json.loads(wire.readline())
                            packet = Packet(
                                saved["identity"],
                                base64.b64decode(saved["body"]),
                                saved["channel"],
                                saved["key"],
                                tuple(map(tuple, saved["headers"])),
                            )
                            wire.seek(0, 2)
                            wire_offset = wire_offsets[original]
                        else:
                            packet = driver.materialize(logical, local)
                            if not isinstance(packet, Packet) or not isinstance(packet.body, bytes):
                                raise ValueError("invalid materialized packet")
                            if not packet.identity or len(packet.body) > 65536:
                                raise ValueError("packet identity/64-KiB event bound violated")
                            wire_offset = wire.tell()
                            journal(
                                wire,
                                {
                                    "identity": packet.identity,
                                    "body": base64.b64encode(packet.body).decode("ascii"),
                                    "channel": packet.channel,
                                    "key": packet.key,
                                    "headers": packet.headers,
                                },
                            )
                            wire_offsets[logical["record_ordinal"]] = wire_offset
                        row |= {
                            "event_or_request_id": packet.identity,
                            "wire_offset": wire_offset,
                            "wire_sha256": hashlib.sha256(packet.body).hexdigest(),
                        }
                        if kind != "sustained" and len(packet.body) <= limits.pending_bytes:
                            # Finite jobs have no target rate; bounded waiting belongs
                            # in their actual completion denominator, not lost rows.
                            async with asyncio.timeout(drain_seconds):
                                while (
                                    pending_count >= limits.pending_count
                                    or pending_bytes + len(packet.body) > limits.pending_bytes
                                ):
                                    capacity.clear()
                                    journal(
                                        pressure, snapshot() | {"pressure": "finite_backpressure"}
                                    )
                                    await capacity.wait()
                        reason = None
                        if cutoff is not None and time.perf_counter() >= cutoff:
                            reason = "measurement_cutoff"
                        elif pending_count >= limits.pending_count:
                            reason = "pending_count_limit"
                        elif pending_bytes + len(packet.body) > limits.pending_bytes:
                            reason = "pending_bytes_limit"
                        if reason:
                            finish(row, "missed", reason)
                        else:
                            pending_count += 1
                            pending_bytes += len(packet.body)
                            peak_count, peak_bytes = (
                                max(peak_count, pending_count),
                                max(peak_bytes, pending_bytes),
                            )
                            queue.put_nowait((row, packet, local))
                            record_queue()
                        journal(
                            pressure,
                            snapshot() | {"record_id": row["record_id"], "pressure": reason},
                        )
                    except Exception as exc:
                        finish(row, "failed", "materialize:" + type(exc).__name__)
            if cutoff is not None:
                await sleep_until(cutoff)
            capture_cutoff()
            drain_start = cutoff if cutoff is not None else time.perf_counter()
            try:
                async with asyncio.timeout(
                    max(0, drain_start + drain_seconds - time.perf_counter())
                ):
                    await queue.join()
            except TimeoutError:
                pass
        finally:
            if phase_task:
                phase_task.cancel()
                await asyncio.gather(phase_task, return_exceptions=True)
            for task in workers:
                task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            while not queue.empty():
                row, packet, _ = queue.get_nowait()
                finish(row, "missed", "drain_deadline_before_send")
                pending_count -= 1
                pending_bytes -= len(packet.body)
                record_queue()
                queue.task_done()
        result = snapshot() | {
            "cutoff": cutoff_snapshot,
            "window_seconds": duration_seconds if kind == "sustained" else None,
            "job_seconds": time.perf_counter() - start if kind != "sustained" else None,
            "measured_job_seconds": time.perf_counter() - measured_started
            if kind != "sustained" and measured_started is not None
            else None,
            "remaining_drain_seconds": max(0, drain_seconds - (time.perf_counter() - drain_start)),
            "measurement_start_elapsed_seconds": warmup_seconds if kind == "sustained" else None,
            "clock_domain": "generator_perf_counter",
            "wall_anchor": stamp(0),
        }
        write_json(directory / "generator.json", result)
        return result
