# Jaineel pre-push audit — 8 November 2026

**Share the implementation on the feature branch through a draft PR. Jaineel's
final contribution is not finished, and whole-repository CI is not green.** The
remaining evaluated deliverables include real integration/correctness, a frozen
baseline, controlled comparisons and the artifact-built report. They follow the
team's provider handoffs; they are not a reason to withhold the implementation.

No commit or push was performed. `git fetch origin` confirmed HEAD equals
`origin/main` (`0 0`) and is 87 commits ahead of the old feature upstream
(`87 0`). The branch is `jaineel/j03-telemetry`. Modified and untracked files are
not included by a plain push: review and commit the owned changes first. Keep
`.env`, raw/generated data, models and `artifacts/` out of the commit. This audit
preserves the earlier working tree and owner implementations.

Authority: [ownership](../OWNERSHIP.md), [Jaineel's brief](../specs/04_JAINEEL_VORA.md),
[common interfaces](../specs/02_COMMON_SPEC.md),
[evaluation](../specs/03_EVALUATION_SPEC.md),
[source rules](../specs/08_DATASET_PROFILE_AND_RULES.md), and
[runbook](../specs/09_EVALUATION_RUNBOOK.md). This audit is one handoff checkpoint;
it does not start the later performance milestone.

## Implementation versus final completion

| Area | Current assessment |
|---|---|
| M1 sessions/cart/fixed workflow/confirmation/idempotency | Implemented with PostgreSQL, HTTP-double, crash/retry and explicit model-budget coverage |
| Shared event/outbox integration | M1 uses the canonical codec, transaction-local append and separate shared relay entry point; actual full-stack delivery is a separate gate |
| M0 generator/oracles/CLI/observation/dashboard/comparison/report | Implemented with owned regression coverage; all seven required workload factories are registered |
| Runtime owner operations | The explicit `RuntimeBindings` interface is available; reviewed concrete migration/fresh-storage/seed/drain/audit/observation/fault hooks remain team inputs. Jaineel owns assembling and executing them |
| Real G0/G1/G3 and required correctness | Incomplete; unit/double tests cannot certify these gates |
| J07 baseline, variants, teammate reproduction and final report | NOT_RUN; the brief's final definition of done is not met |

The detailed callable handoff and startup commands are in
[CODE_HANDOFF.md](CODE_HANDOFF.md) and [projectctl](../../projectctl/README.md#unified-runtime-composition).

## Fixes made in this audit

- `services/conversation/clients.py`: deeply nested provider JSON raised an
  uncaught `RecursionError` despite the byte-size limit. It now becomes a
  `ContractViolation`, including error responses. Existing workflow dependency
  handling can report it without an unhandled server error. Streams still close
  and no automatic extra attempt occurs.
- The same client accepted negative, signed and underscore-containing
  `Retry-After` values through Python's integer parser; a sufficiently large
  value raised `OverflowError`. Only finite nonnegative digit-form delays and
  HTTP dates are accepted now. Invalid values fail closed; valid delays still
  cannot be shortened to squeeze a retry into the deadline.
- `tests/contracts/test_clients.py`: six new consumer regressions failed before
  the fix and pass after it. The full HTTP client suite passes 81 tests.
- `.env.example`: added the required `EVENT_SCHEMA_CACHE_PATH`, pointing to
  Vichitr's actual streaming-local mapping output. API and relay must use the
  same verified mapping and approved catalogue revision.
- `benchmarks/manual/verify_transaction_boundaries.py`: added a shareable,
  explicitly invoked boundary reproducer. Its SQL/ASGI doubles do not run worker
  lifespans or contact real databases, Kafka, payments or HTTP services. It
  preserves failing consumer assertions and does not add xfails or change
  another owner's production code/tests.

## Owner findings that remain open

**Aditya — authorization and fault controls (reproduced with explicit doubles).**
Orders' public GET snapshot and SSE disclose the returned order to a different
`X-User-ID` in the same namespace. Orders/Inventory/Payments internal audit routes
accept requests with no Authorization header even when `INTERNAL_API_TOKEN` is
configured. With a valid token, the Orders fault route accepts a mutation when
fault injection is disabled and separately accepts `dev` when both flags are
enabled. Seven of eight independent probe cases return HTTP 200 where access
must be denied; the existing `BENCHMARK_MODE=false` guard correctly returns 403.
Common §§2–3/5 require
principal binding, service tokens and both fault flags in an isolated namespace.
Review all internal commands as well as the sampled audit routes. These are
route-boundary findings, not claimed live security/integration tests.

Reproduce from the pushed code, retaining a fresh output directory:

```powershell
uv run --locked python -m benchmarks.manual.verify_transaction_boundaries --out artifacts/transaction-boundary-review-NEW
```

Current expected diagnostic outcome: exit 1, seven failed assertions out of eight in
`boundaries.json`; real integration NOT_RUN. Fault probes supply a valid token
so adding token enforcement alone cannot hide missing scope/flag checks.
After owner fixes, denial must occur
before the doubled SQL/business operation. Do not weaken the assertions.

**Aditya — transaction acceptance and reproducibility (code inspection).**
`services/orders/commands.py:create_order` fetches the quote before replay lookup,
does not check its expiry/returned user, and the POST route does not consume
`Idempotency-Key`. Harsh's real quote lookup enforces its user binding but
deliberately returns expired snapshots for Orders to validate. Preserve replay of
already accepted orders while rejecting new expired quotes and conflicting key
reuse. The worker substitutes `run_id="saga-worker"`; retain originating job
provenance. Payments still use random outcomes without the frozen deterministic
scenario/delay control. These observations are distinct from the executable
route probes and do not claim new live expiry/payment trials. Whole-repo Ruff
also finds 22 existing E501 violations in M3/test paths; fix them in that branch.

**Vichitr — one current offline CI failure.**
`tests/pipelines/test_transport.py::test_m1_keyword_builder_and_existing_transaction_binding`
initializes the global SDK codec, then uses `SharedEvents()` without its pinned
cache and dataset revision. M1 correctly fails closed. Update the fixture to
pass `cache_path` and an explicit synthetic `dataset_revision`, following
`tests/conversation/test_shared_events.py`; preserve its transaction/schema
assertions. This is not permission to weaken production readiness.

**Harsh — stale strict xfail and reviewed data inputs.**
The real HTTP catalogue brand consumer now succeeds, while
`tests/catalog/test_conversation_consumer_live.py::test_workflow_accepts_a_real_brand_filter`
still marks the old M1 bug as `xfail(strict=True)`. Review/remove that marker in
Harsh's branch. Catalogue outbox migration 005 already exists. Supply/review the
actual normalized/SKU/facet manifests, complete seed/projection evidence and
catalogue/layout lifecycle hooks. Resolve the recorded raw-byte versus LF hash
policy with consumers. Human relevance claims require reviewed manual labels;
rule-derived labels remain diagnostic.

**Together.** Supply concrete scoped lifecycle/read-only exports through the
available runtime interface, run actual G0/G1/G3/correctness, and freeze approved
inputs/resources on a committed revision. Jaineel then executes/reconciles the
baseline, registered three-repetition comparisons and report. Vichitr's O1 and
scaling work follows the correct B0 gate. No approval, throughput, latency or
quality result is manufactured by this handoff.

## Fresh verification and limits

| Check | Actual result |
|---|---|
| Final owned regression, isolated PostgreSQL for M1 | **1,286 passed**, zero failures/skips |
| Locked offline repository CI | **1,541 passed / 1 failed / 522 skipped**; Vichitr's unchanged cache/revision fixture fails |
| Linux PostgreSQL M1/catalogue/transaction/contract suites | **872 passed / 1 failed / 13 skipped**; Harsh's stale strict brand xfail XPASSes |
| Linux suite details | M1 411, contracts 109, transactions 127 pass; catalogue 225 pass, one strict XPASS, 13 optional model/Kafka skips |
| Owned lint/format and schema checks | Pass; 191 Python files formatted |
| Whole-repo lint | 22 existing M3 E501 violations; owner correction required |
| Independent exact-source profile | PASS; 20,000 raw, 19,998 canonical, 19,920 active |
| Explicit M3 boundary verifier | Seven failures, one pass; all doubled, no live acceptance claim |
| Benchmark readiness | Exit 4 / INCOMPLETE; no performance run started |

Raw evidence is retained in `artifacts/jaineel/push-audit-20261108/`. The exact
commands and final outcomes are recorded in the corresponding progress entry.
The offline CI run, native PostgreSQL checks, new failing-before/passing-after
HTTP tests and explicit boundary probes are separate cohorts; overlapping counts
must not be added. Linux service checks use read-only source mounts, the locked
existing worker image and a new digest-pinned PostgreSQL 18/pgvector container.
They do not use or reset development databases.
The audit database is stopped; its data and the dedicated Linux volume/network
are retained. No teammate/development container or volume was removed.

Live Kafka/Registry/recreation, hosted GitHub CI, complete business Gold/recovery,
human label approval, enforced benchmark resources, performance comparisons and
teammate baseline/variant reproduction remain NOT_RUN. Code inspection and test
coverage do not establish that a repository is free of every possible bug.
