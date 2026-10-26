"""Append-only raw JSONL; Parquet is reconstructible after an interrupted run."""

import json
import math
import time
from contextlib import contextmanager
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from shared.telemetry.context import utc_now

TIMING_SCHEMA = pa.schema(
    [
        ("run_id", pa.string()),
        ("namespace", pa.string()),
        ("component", pa.string()),
        ("event_id", pa.string()),
        ("record_id", pa.string()),
        ("stage", pa.string()),
        ("phase", pa.string()),
        ("started_at", pa.string()),
        ("ended_at", pa.string()),
        ("duration_seconds", pa.float64()),
        ("clock_domain", pa.string()),
        ("timing_validity", pa.string()),
        ("generation", pa.int64()),
    ]
)


class TimingWriter:
    def __init__(self, directory, run_id, namespace):
        self.directory = Path(directory)
        self.run_id, self.namespace = run_id, namespace
        self.stream = (self.directory / "timings.jsonl").open("x", encoding="utf-8")

    def append(
        self,
        *,
        component,
        event_id,
        stage,
        phase,
        duration_seconds,
        started_at=None,
        ended_at=None,
        clock_domain=None,
        generation=None,
        record_id=None,
    ):
        if duration_seconds is not None and (
            isinstance(duration_seconds, bool)
            or not math.isfinite(duration_seconds)
            or duration_seconds < 0
            or not clock_domain
        ):
            raise ValueError("finite elapsed time and one explicit clock domain required")
        if phase not in {"warmup", "measurement", "drain"}:
            raise ValueError("timing phase required")
        row = dict(
            run_id=self.run_id,
            namespace=self.namespace,
            component=component,
            event_id=event_id,
            record_id=record_id,
            stage=stage,
            phase=phase,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=duration_seconds,
            clock_domain=clock_domain,
            generation=generation,
            timing_validity="VALID" if duration_seconds is not None else "MISSING",
        )
        self.stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
        self.stream.flush()
        return row

    @contextmanager
    def span(self, *, component, event_id, stage, phase):
        start, wall = time.perf_counter(), utc_now()
        try:
            yield
        finally:
            self.append(
                component=component,
                event_id=event_id,
                stage=stage,
                phase=phase,
                duration_seconds=time.perf_counter() - start,
                started_at=wall,
                ended_at=utc_now(),
                clock_domain="local_perf_counter",
            )

    def close(self):
        self.stream.close()
        return rebuild_timings(self.directory)


def rebuild_timings(directory):
    """Never overwrite evidence. Bounded batches preserve nulls and exact samples."""
    directory = Path(directory)
    target = directory / "timings.parquet"
    with target.open("xb") as stream, pq.ParquetWriter(stream, TIMING_SCHEMA) as writer:
        batch = []
        with (directory / "timings.jsonl").open(encoding="utf-8") as raw:
            for line in raw:
                batch.append(json.loads(line))
                if len(batch) == 1000:
                    writer.write_table(pa.Table.from_pylist(batch, schema=TIMING_SCHEMA))
                    batch.clear()
        if batch:
            writer.write_table(pa.Table.from_pylist(batch, schema=TIMING_SCHEMA))
    return target
