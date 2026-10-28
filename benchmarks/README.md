# Evaluation Benchmarks & Workload Harness (M0)

**Owner:** Jaineel Vora (B24CM1080)
**Specification Brief:** [04_JAINEEL_VORA.md](../docs/specs/04_JAINEEL_VORA.md)
**Evaluation Specification:** [03_EVALUATION_SPEC.md](../docs/specs/03_EVALUATION_SPEC.md) & [09_EVALUATION_RUNBOOK.md](../docs/specs/09_EVALUATION_RUNBOOK.md)

## Scope
P3 provides independent fixture expectations, checksum-gated read-only source
checks, reconciliation primitives and metric math. Real providers remain pending. Use
`python benchmarks/manual/verify_p3.py` for the offline checkpoint and see
[P3 manual checks and limitations](../docs/jaineel/p3_oracles.md).

## P4 workloads and lifecycle

The P4 scheduler, consumer drivers, paired planner and isolated experiment runner
are described in [Jaineel's P4 handoff](../docs/jaineel/p4_workloads.md).
Run `python -m benchmarks.manual.slow_publisher` for the explicit slow test
publisher, or `python benchmarks/manual/verify_p4.py` for the recorded checkpoint.
Real G1 and performance results remain `NOT_RUN` pending provider adapters.
