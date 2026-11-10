# M3 payment handoff checkpoint — 11 November 2026

This is Jaineel's implementation of Aditya's delegated payment and seed-audit
handoff, on `jaineel/prototype-demo`. The user explicitly authorized the M3
service, migration and transaction-test paths in the supplied handoff and delegated
design decisions. The initial checkpoint was left uncommitted; the subsequent
review explicitly authorizes commit/push on this same branch. Its additional
fixes, real prototype execution and publication receipt are recorded in
[progress.md](progress.md). This checkpoint does not declare the full M0
evaluation complete.

## Authority and verification of the pulled change

HEAD is `3be2916`, the merge of PR #19. Code inspection and a fresh boundary probe
confirm the status/SSE ownership checks, service tokens on internal routes, and
the two-flag/namespace fault guard. The original probe now passes all eight cases
using explicit ASGI/SQL doubles. This does not verify hosted CI or a deployment.
`services/orders/m3_setup.py` supplies the repeatable migration participants.
Fresh PostgreSQL 18 checks exercise migrations, repeat setup and real M3 HTTP.

The remaining payment issues were present at this HEAD: authorization completed
inside the request with a 15% random failure rate, failure codes used
`SIMULATED_*`, every failed first attempt could be retried, and saga events used
the worker's run identity. Harsh already supplied `inventory_facts` in
`pipelines/catalog/runtime.py`; the combined harness reader now independently
checks its pending/run facts alongside exact SKU membership.

The controlling requirements remain canonical:

- [Common spec §8–9](../specs/02_COMMON_SPEC.md): durable pending completion,
  same-attempt recovery, retry only after `RETRYABLE_PROVIDER_FAILURE`, no retry
  after `DECLINED`, payment guard and compensation order.
- [Evaluation §2](../specs/03_EVALUATION_SPEC.md) and
  [Aditya A04](../specs/06_ADITYA_GAURAV.md): stable scenario/seed, 95/5,
  100-ms provider delay, isolated simulator controls.
- [Dataset rules §7](../specs/08_DATASET_PROFILE_AND_RULES.md) and
  [runbook §2/7](../specs/09_EVALUATION_RUNBOOK.md): exact seeded stock/projection,
  outbox completion, immutable raw evidence and independent reconciliation.

## Decisions implemented

The optional carrier is a pair of HTTP headers:

| Header | Meaning |
|---|---|
| `X-Benchmark-Scenario-ID` | Frozen version-2 `warmup:<ordinal>:<template>` or `measurement:<ordinal>:<template>`; ordinal has 6–12 digits; total length ≤128; template uses letters, digits, `_`, `.`, `:`, `-` |
| `X-Benchmark-Seed` | Nonnegative int64 represented as decimal text |

All three ingresses (M1 checkout, Orders creation, internal payment authorization)
reject this pair unless `BENCHMARK_MODE=true`, `FAULT_INJECTION_ENABLED=true`, and
the namespace is isolated. `bench-dev`, `bench-live`, `bench-prod` and
`bench-production` and their descendants are excluded. Partial or invalid pairs
return 422; disabled controls return 403. Internal authorization still requires
`Authorization: Bearer $INTERNAL_API_TOKEN`. There is no requested-outcome or
requested-delay parameter.

The workload driver sends its already-frozen logical scenario ID and seed. M1
journals them in `workflow_commands.business_input`, includes them in the request
hash, and reuses them after response loss/restart. Orders saves them and the
original `RequestContext` on the accepted order. The saga restores that identity
for all participant commands and terminal events. A duplicate accepted quote
continues to resolve to its original order and stored plan.

Payments implements the v2 scenario rule independently of the harness: SHA-256
of canonical JSON `{seed,phase,block=ordinal//100}` seeds Python's `Random`; five
positions sampled without replacement from each block of 100 decline. Template
shuffle, runtime UUID, namespace, wall time and execution order do not affect
the result. The harness's existing v1 recipe reconstruction is retained for
historical evidence; new real requests require the v2 carrier.

Authorization holds the order-level payment guard, returns an existing immutable
attempt on retry, or writes a `PENDING` attempt with a durable due time, planned
outcome, identity and carrier. Ordinary simulator calls also use pending
completion with a 100-ms delay and a 5% random business-decline probability;
deterministic selection requires the isolated benchmark carrier.

A 25-ms polling worker completes attempts **no earlier than 100 ms** after their
creation. Scheduling/DB load can add delay; this is not a claim of exactly
100-ms observed latency. Guard lock → attempt lock → actual DB clock → state,
ledger and shared outbox transaction prevents duplicate callbacks and late
debits after reversal. Persisted work resumes after a worker restart without
reselecting its outcome. No second attempt follows pending, success, decline,
unknown failure or quiescence. The saga permits attempt two only for a definitive
retryable failure while the reservation snapshot remains ACTIVE/unexpired;
Inventory still makes the authoritative commit/expiry decision.

The independent seed reader uses `INVENTORY_AUDIT_DATABASE_URL` with the existing
role-privilege check and a repeatable-read, read-only transaction. It reads the
exact Inventory SKU list, counts **all namespace rows with `published_at IS NULL`**,
and requires exactly one nonempty original outbox run ID. Owner callback facts
that conflict with that snapshot fail. Catalogue/projection keys come from their
own SELECT-only snapshot. Equal counts with different keys cannot pass.

## Contract and audit review

Canonical DTOs are reused: `RequestContext`, `CreateOrderRequest`,
`OrderAccepted`/`OrderSnapshot`, `AuthorizePaymentRequest`, `PaymentSnapshot`,
`PaymentOrderSnapshot`, `ReservationSnapshot`, `StockSnapshot` and `PaymentEvent`.
The JSON body/response shapes, event schemas and ownership boundaries are intact.
Only new `003_*.sql` migrations are added; applied migrations are unchanged.
No operational service imports another service's implementation or accesses its
database. The shared header helper lives with context propagation in
`shared/telemetry/benchmark.py`; payment outcome logic remains in Payments.

For ledger reconciliation, `/internal/v1/audit/ledger` exposes positive magnitudes
plus `kind`. The existing `benchmarks/g3_audit.py` signs DEBIT positive and REVERSAL
negative exactly once. Its independent oracle uses those entries, not the
provider's clamped `net_debit_minor`. Order/reservation/stock audit endpoints and
their token requirements remain as reviewed in PR #19.

This document records automated implementation/consumer review under the user's
delegation. It does not manufacture human owner approvals or change the canonical
specification. Aditya's transaction OpenAPI should document the optional headers
and 403 response on internal authorization in his next contract update; the
header protocol is recorded here for that handoff. Existing required service
tokens and all normal DTOs remain the canonical contract.

## Reproduce and deploy this checkpoint

Install with the existing application lock: `uv sync --locked`.
Before restarting services against an existing deployment, supply the three
owning database URLs and run:

```powershell
uv run --locked python -m services.orders.m3_setup
```

The Orders and Payments processes must use this code and the new schemas together.
For benchmark traffic enable both flags on M1, Orders and Payments; ordinary
prototype requests need neither header. Do not reseed/reset the retained
prototype namespace merely to test this change.

Verification commands and actual outcomes are recorded in
[progress.md](progress.md). Raw logs/JUnit and boundary results are retained under
`artifacts/jaineel-m3-20261111/`; the P5 verifier writes its own UUID directory.
The test database uses the repository-pinned pgvector image, PostgreSQL 18.2,
in a disposable container and per-test schemas. Catalogue HTTP and Schema
Registry fixtures in M3 tests are explicit doubles. Shared event construction,
SQL state, locks, ledger and outbox writes are exercised; Kafka publication and
Gold visibility are not claimed by these tests.

## Remaining evaluation handoffs

This finishes the delegated payment/seed-audit checkpoint. Formal G3/T-07/T-08/T-11
bindings, reset/preflight participation, acknowledged failure barriers, retained
broker receipts, full source→Silver→Gold reconciliation and performance
repetitions still require their concrete provider composition. A 35-second
payment-delay hook for the separate expiry fixture is not implemented by this
fixed 100-ms core-control change. No full B0/matrix or hosted CI result is claimed.

Historical orders have no newly stored ingress context; their fallback remains
the worker context. New accepted orders preserve the original identity. No
historical evidence or applied migration is rewritten to invent missing identity.
