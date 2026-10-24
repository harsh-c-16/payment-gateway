# P4 workload and lifecycle handoff

P4 implements J02 only. The scheduler and lifecycle can be checked offline with
explicit doubles. Real G1, provider compatibility and performance are `NOT_RUN`
until the owner bindings below exist. P5 collectors and P6/P7 application state
and workflows are separate milestones.

Run these from `payment-gateway/` with the locked Python 3.11 environment:

```powershell
uv sync --locked
uv run --locked python -m pytest tests/benchmarks -q
uv run --locked python -m benchmarks.manual.slow_publisher
uv run --locked python benchmarks/manual/verify_p4.py
```

The demo imports `tests/benchmarks/doubles.py` explicitly. Its three seconds are
one second of warmup and two seconds of measurement. It plans 400 measurement
offers at 200/s against a 50-ms publisher, with one worker and four pending
records. The demo command exits 0 when its assertions hold; the enclosed
experiment must return **5**, indicating target load was missed. No broker,
database, API, model or Gold publisher participates.

Open the printed directory's `workload_manifest.json`, `planned.jsonl`,
`emissions.jsonl`, `attempts.jsonl`, `queue.jsonl`, `cutoff.json`, `admission.json`,
`generator.json`, `execution.json`, `summary.json` and `demo_checks.json`.
`planned = acknowledged + failed + missed + unresolved` for each phase, with
attempted counted separately. A pending send whose admission is unknown stays
unresolved; an unsent queued record becomes missed at the deadline. Drain-only
acknowledgements are excluded from the measurement admitted-rate numerator.
Scheduling delay uses generator monotonic time; UTC fields are wire/log context.
These are harness admission measurements; Gold goodput stays null/`NOT_RUN`.

## Workload recipe and journals

`benchmarks.workloads.generate_workload(workload_id, seed, catalog_manifest, ...)`
returns `WorkloadManifest`. Its immutable canonical recipe freezes logical
templates, schedule, selected SKUs, expected dispositions and a fixture checksum.
`records()` streams the planned cohort; provider responses never change it.
Phase iteration is explicitly warmup then measurement, independent of JSON key
sorting. Runtime UUIDs and times are fresh in every run; logical seeds/templates
remain paired.

The catalogue argument is an explicitly documented **harness projection**:
`{"active_skus": [...], ...provenance...}`. Harsh must supply a reviewed binding
from his canonical SKU manifest; this is not a substitute provider DTO. W-PIPE
selects 10,000 keys from the sorted active set using seed 42. Uniform and hot80
series are separate controls; hot80 puts exactly eight of every ten offers on
one hot key. Stock versions increase per SKU across phases. Synthetic absolute
stock snapshots are pipeline workload inputs, not Inventory mutations.

W-QUALITY keeps P3's exact 98,500/1,000/500 recipe. Every duplicate retrieves the
original packet, identity, headers and key from the wire spool, and gets a new
delivery receipt/offset. The SDK is called only for original records, including
originals that could not be sent. Invalid bytes are delegated to reviewed wire
fixture bindings; this harness does not implement the SDK or schema registry.

`wire.jsonl` stores base64 packet bodies plus key/headers/channel. For Kafka,
these are the exact bytes handed to the publisher. For API drivers these are
the operation input; checkout's generated quote/order bodies and context are
also retained in receipt details. `api_requests.jsonl` retains exact bodies,
paths, headers and stable keys for every public HTTP step before awaiting its
response, including attempts whose responses are lost. `attempts.jsonl` is flushed before awaiting
the submission. Terminal receipts may be out of order; join by record ID.

The scheduler uses a fixed worker pool. Its pending count includes queued and
active operations; both count and value-byte limits apply before enqueueing
(maximum 10,000 records / 64 MiB, event value maximum 64 KiB). Sustained offers
never await capacity and never shift their schedule. Queue pressure or a missed
cutoff is retained as a missed offer. Finite fixtures can wait for bounded
capacity; this wait belongs in their actual elapsed denominator. An importer or
query adapter must honor cancellation and its declared operation timeout.

W-IMPORT delegates one complete 20,000-observation import to Harsh. It preserves
his raw-open-to-ready total and stage timers in `import_timings.json`; it does
not normalize rows. W-QUALITY and W-AGENT also use actual job duration rather
than 600 seconds. W-ANALYTICS runs randomized complete query rounds: three
warmups and thirty measured executions for each Q1–Q6. Its measured denominator
starts after the warmups. Search is offered at 20/s with at most 32 workers;
checkout and integrated sessions at 10/s. Sustained performance requires
60-second warmup / 600-second measurement, followed by at most 120 seconds of
drain. Short runs require explicit `test` or `smoke` evidence.

## Binding providers without hidden doubles

`benchmarks.experiment.run_experiment(...)` consumes `ExperimentBindings`.
Register a production binding with
`ProviderRegistry.register_workload(workload_id, bindings)`. The default registry
has **no** production workload registrations yet. The CLI has no mock mode.
The manual demo calls the Python API with `evidence_kind="smoke"` and explicit
`mode="stub"`; a stub performance run is rejected.

Bindings provide these operations:

| Binding | Required behavior / handoff |
|---|---|
| `catalog_manifest`, `templates` | Reviewed immutable SKU/query/cart/scenario projections. Search's 50 queries, integrated query/SKU pairs, Q1–Q6 pinned snapshots and 60 reviewed assistant scenarios must come from their owners. |
| `prepare(context, workload_manifest)` | Create **new** namespace-scoped data/topics/groups, migrate/seed/wait for stock readiness as applicable; return `namespace` and `created_new=true`. Existing namespaces fail. No reset method is invoked. |
| `validate(context, workload_manifest)` | Verify readiness, hashes, resource enforcement, initial state, dictionary/schema locks and all effective variant controls. |
| `driver.materialize(record, context)` | Return immutable `Packet`. Vichitr owns SDK encoding, schema IDs, topic/key rules and deliberately invalid-wire examples. No fixture is loaded automatically. |
| `driver.send(packet, context, mark_send)` | Call `mark_send()` immediately before the timed broker/API submission, then return correlated `Receipt`. Kafka acknowledgements require exact topic/partition/offset. Timeouts and response loss cannot become accepted receipts. |
| `drain(context, remaining_seconds)` | Observe accepted orders to terminal state and downstream publication within the **remaining shared drain deadline**. A timeout fails visibly. Retain finality observations; do not hold new submissions on finality. |
| `audit(context, directory)` | Read **all** of `planned.jsonl`, packet identities and approved read-only exports; bind P3's independent oracle to source dispositions, Silver, active-file Gold and business audits. Return explicit `passed: true/false/null` and matching `test_mode`, preserving raw evidence. A generator acknowledgement is not Gold proof. |
| `fault(context, profile, definition)` | Execute only the registered fault profile with barrier acknowledgement before a worker kill and retained state on recovery. Return the acknowledgement/barrier receipt. A missing adapter or acknowledgement invalidates the trial. |

Context includes run/namespace IDs, seed, source dataset settings, complete
workload recipe, planned-journal path and effective treatment parameters. Runtime
request IDs are derived from fresh run UUID + logical record ID, so retries keep
their key while different runs are isolated. Prepare must configure Aditya's
simulator from stable scenario ID/seed (95/5 outcome rule and 100-ms delay), never
from those runtime UUIDs. Initial stock is seeded by Aditya; it is not inferred
from the CSV.

Available consumer drivers are `PipelineDriver`, `SearchDriver`, `CheckoutDriver`,
`IntegratedDriver`, `ImportDriver`, `QueryDriver` and `AgentDriver` in
`benchmarks/drivers.py`. Search and checkout consume P2's public catalogue/Orders
clients. Quote preparation precedes checkout's submission timestamp; quote totals
are preserved as authoritative. Orders receives `quote_id`, `session_id` and
explicit `confirmation_id`. Acceptance and finality remain distinct.

The integrated driver consumes M1 public session/turn/cart/quote/checkout
operations. Its frozen SKU must occur in the search results; confirmation binds
the returned quote and cart version. M1's real public client/service is still a
P6/P7 dependency. The driver never emits order/payment/conversion events itself.
Those must come from the transaction services and shared outboxes. Query and
assistant drivers consume explicit query/workflow adapters, without implementing
SQL reducers, extraction rules or model calls here.

## Paired execution and artifact reuse

`benchmark run` now expands repetitions and fault profiles in recorded paired,
seeded variant order. The plan and its results index live beside the run
directories. All comparator inputs/resources/quality controls must match, except
registered treatment fields. Fault profiles and retrieval/skew/rate series are
separate pairs. A matrix request expands registered rows once and retains
unresolved measured-C-BEST selections as dependency failures. P4 does not choose
a winning variant or execute the performance matrix.

F-PARTITION has explicitly labelled unpartitioned/date_type children, both
compact at the same target size/codec. The unchanged P1 configuration represents
the parent variant as `file_layout=partition_comparison`; the child's complete
effective parameters are frozen in hashed `execution_order.json` and passed to
prepare/validate. Consumers must use those parameters instead of treating the
parent marker as a physical layout. This resolves the existing parent/child
representation without changing canonical specs or provider DTOs; Harsh and
Vichitr must review the binding before real layout trials.

Matrix reuse requires matching full resolved config/trial key, a completed real
performance run, passing correctness, matching clean code commit, and all
referenced artifact hashes. P4 leaves full SUT performance incomplete until P5's
collectors exist, so these harness-only runs cannot be reused as complete
performance evidence. Corrupt/incomplete/stub evidence is never skipped as
complete. `benchmark compare`, `benchmark reconcile` CLI integration and final
report generation remain later milestones; the P3 oracle itself is unchanged.

## Current dependencies and manual checkpoint

Harsh's importer, catalogue OpenAPI/DTOs, actual manifests/dictionary, reviewed
queries/cart bindings and pinned query adapter are missing. Aditya's transaction
APIs, deterministic simulator/seed and read-only audits are missing. Vichitr's
SDK, schemas/registry, Kafka/analytics/publication/audit/fault bindings and enforced
infrastructure are missing. P5 raw timing/resource/lag collectors are unexecuted;
their artifact slots stay `NOT_RUN`, with no zero samples or fake Gold values.

1. Run the commands at the top. Expect the benchmark tests to pass and the slow
   demo assertions to pass with experiment exit 5.
2. In the demo, sum terminal outcomes for measurement: exactly 400. Compare its
   offered-rate metric with its lower admitted rate and positive missed count.
3. Compare `cutoff.json` with `admission.json`: drain acknowledgements are retained
   separately. Inspect scheduling delay/pressure and the queue's peak bounds.
4. Run `uv run --locked python -m projectctl benchmark run --workload W-PIPE --variants B0,O1 --repetitions 3 --config configs/evaluation.yaml`.
   Expect exit **4**, six distinct run IDs/namespaces, a seeded paired plan,
   provider/draft reasons and null performance values. No service is started.
5. Run `uv run --locked python -m projectctl contracts check --all`; expect exit
   **4** until owner contracts arrive. Once the owner handoffs exist, review and
   register real bindings, then execute G1's valid/duplicate/invalid slice. A real
   G1 pass is currently `NOT_RUN`.

Stop at P4. Review the source diff and progress evidence before committing.
