# Evaluation Benchmarks & Workload Harness (M0)

**Owner:** Jaineel Vora (B24CM1080)
**Specification Brief:** [04_JAINEEL_VORA.md](../docs/specs/04_JAINEEL_VORA.md)
**Evaluation Specification:** [03_EVALUATION_SPEC.md](../docs/specs/03_EVALUATION_SPEC.md) & [09_EVALUATION_RUNBOOK.md](../docs/specs/09_EVALUATION_RUNBOOK.md)

## Scope
P3 provides independent fixture expectations, checksum-gated read-only source
checks, reconciliation primitives and metric math. Real providers and the P4
open-loop scheduler/lifecycle remain unimplemented. Use
`python benchmarks/manual/verify_p3.py` for the offline checkpoint and see
[P3 manual checks and limitations](../docs/jaineel/p3_oracles.md).
