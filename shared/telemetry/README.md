# Shared telemetry (Jaineel / M0)

P5 implements the [common §14 metrics](../../docs/specs/02_COMMON_SPEC.md),
finite label vocabularies, task-local structured logs and raw JSONL/Parquet timers.
Owners instrument their own services; no service or outbox implementation lives here.

See the [P5 handoff and instrumentation examples](../../docs/jaineel/p5_telemetry.md).
Run `uv run --locked python -m pytest tests/telemetry -q` from the repository root.
