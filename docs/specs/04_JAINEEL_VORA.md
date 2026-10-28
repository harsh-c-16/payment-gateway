# Jaineel Vora: personal coding brief

Module owner: M1 + M0 benchmarking, integration and monitoring  
Version 2.0. Read first: 01_PROJECT_CONTEXT.md, 02_COMMON_SPEC.md, 03_EVALUATION_SPEC.md, 08_DATASET_PROFILE_AND_RULES.md and 09_EVALUATION_RUNBOOK.md. The dataset rules and evaluation commands are required implementation inputs, not optional background.

## 1. Your final responsibility

Build the minimal assistant/session/cart application and the measurement system that makes this a data-engineering project. You own the open-loop load generator, independent oracle, experiment runner, monitoring helpers and dashboard.

**Change from tracker:** monitoring/dashboard implementation moves to you from Vichitr. Your existing benchmarking responsibility becomes the main engineering deliverable; keep agent complexity bounded. Do not spend the first week comparing LLMs while the measurement harness is missing.

You do not implement catalogue ranking, inventory rules, payment logic, Gold reducers or outbox publication logic.

## 2. Files you own

- services/conversation/ and migrations/conversation/.
- contracts/http/conversation.yaml and conversation DTOs.
- shared/telemetry/, dashboards/, benchmarks/, tests/oracles/, tests/integration/.
- projectctl/ CLI coordinator, contracts/evaluation/ schemas, configs/evaluation.yaml and configs/core_matrix.yaml; provider adapters delegate work to the named owner.
- Conversation fixtures/tests; root application dependency lock and CI orchestration.
- docs/integration_runbook.md and the final comparison report generated from actual artifacts.

Coordinate infra files with Vichitr. He owns Compose and component configuration; you own running experiments and validating readiness through its documented commands.

## 3. Your public and local contracts

Implement the conversation/session/cart endpoints in common §5 exactly. Your important local functions are dispatch_turn, extract_intent, compose_response, update_cart, request_quote and checkout_cart.

Additional functions you own:

| Function contract | Required behavior |
|---|---|
| generate_workload(workload_id, seed, catalog_manifest) → WorkloadManifest | Frozen logical scenario templates, intended schedule, expected record classes and hash |
| run_experiment(workload_id, variant_id, repetition, seed, namespace, duration_seconds, warmup_seconds, fault_profile) → RunArtifactManifest | Prepare isolated run; verify config; warm up; emit; observe; drain; reconcile; save evidence |
| observe_run(run_config) → ObservationStream | Source/client timings, Kafka group lag, outbox and pending-export backlog, resource samples |
| reconcile_run(expected, observed) → ReconciliationResult | Independent business/data oracle; no production reducer import |
| compare_runs(baseline_run_ids,candidate_run_ids) → ComparisonReport | Reject mismatched controls; actual values only; median and spread; correct percent direction |
| evaluate_intents(labelled_utterances, extractor) → IntentEvaluation | Six-slot macro F1 with explicit missing/wrong-value accounting |
| evaluate_workflows(scenarios, fixed_adapter, assist_adapter) → WorkflowComparison | Same backend and intents; fixed vs single-call assist; task/clarification outcomes, tool and model calls, stage latency and actual provider usage |

## 4. What you require from other people as black boxes

| Provider | Interface you consume | Stub behavior you need immediately |
|---|---|---|
| Harsh | SkuManifest, FacetDictionary and GET /v1/catalog/facets | 19,920 active candidates; nullable facets; 32 roots; only 4 verified apparel sizes; no invented stock or attributes |
| Harsh | POST /v1/search → SearchResponse | Five hits, no hits, fewer than five eligible, hard-filter-compliant hits, 503 |
| Harsh | GET /v1/products/{sku}; POST /v1/quotes → Product/Quote | Known/unknown SKU, changed price, 60-second quote, invalid lines |
| Aditya | POST /v1/orders → 202 same order for same key | Pending, duplicate response, different-input key conflict, 503/response loss |
| Aditya | GET order snapshot and SSE | Confirmed, cancelled, unresolved; reconnect with newer version |
| Aditya | append_outbox(tx,event) | Writes through your transaction; rollback leaves no event |
| Vichitr | build_event, schemas, transport and local diagnostic helper | Reject invalid payload; no per-event registry call |
| Vichitr | Analytics receipts, active manifests and Gold read API | Not published yet, published generation, missing timing, DLQ/replay states |
| All owners | /health/ready, /metrics, scoped fault barriers | Deterministic readiness and failure states |

Treat stock_available in search as a display hint. Do not decide whether stock can be sold. Treat Quote.total_amount_minor as authoritative; do not recalculate a price from chatbot text. Treat order status as a backend fact; a payment tool timeout is not a cancellation.

## 5. Ordered coding tasks

### J01 — Contracts, fixtures and a small runner first

Deliver the conversation OpenAPI, DTOs and stub clients. Create a registry of all required provider endpoints and a contract smoke suite. Implement namespace/run-ID propagation and canonical request IDs. Prepare the benchmark artifact schemas with values null/NOT_RUN before execution.

Create dataset checks and dirty CSV normalization expectations independently of Harsh's production parser, using file 08. Implement the projectctl/evaluation schema contract in runbook §1 and required artifacts in §7. Freeze the six-slot and optional brand/path interpretation with Harsh's dictionary.

Create the W-QUALITY expected fixture independently. Your oracle must know which IDs are valid, duplicates and malformed without reading Vichitr’s output to “learn” the expected answer.

Acceptance: the runner can call stubs, detect a deliberately wrong field name, and reject a mismatched configuration without any real services.

### J02 — Implement the deterministic workload scheduler

Implement W-PIPE first. Emit at planned times independently of sink responses, keep bounded pending sends, and record missed schedules/backpressure. Match broker acknowledgements to event IDs and source coordinates. Preserve duplicates exactly when the fixture calls for them.

Add W-IMPORT by delegating to Harsh's importer and measuring stage/total time. Add W-SEARCH, W-CHECKOUT and W-INTEGRATED drivers using public APIs; use the original catalogue manifest, not the obsolete synthetic 10,000-row catalogue. Do not publish fake “confirmed order” events in an integrated test; make real simulated transactions produce them.

Acceptance: prove offered vs actual send/ack counts under an intentionally slow stub. The harness must expose its own inability to generate the target rate.

### J03 — Monitoring and dashboard

Implement common telemetry naming, 1-second lag/resource sampling, raw duration collection and time-series exports. Dashboard panels show offered/admitted/goodput, latency distributions, lag by partition, pending Gold, outbox age, quarantine reasons, stock/saga states, CPU and memory.

Show run_id, variant, workload and status on the dashboard. No sample metrics as defaults. Offline results must be reconstructible without a running Grafana instance.

Acceptance: pause a stub stage and show the correct backlog boundary increasing. A low Kafka lag with increasing pending Gold must be visibly distinguishable.

### J04 — Sessions, cart and fixed workflow

Persist session, cart, cart_version, idempotency records and turn outcomes. Implement explicit user confirmation against a particular quote and cart version. A changed cart invalidates previous confirmation.

Fixed workflow: deterministic rules/dictionary intent → one lexical search → template display → explicit cart update → quote → explicit checkout confirmation → observe order state. Structured filter controls bypass extraction. Use a fixture-backed extractor only in explicitly labelled tests; implement actual deterministic handling for the demo. No generative model is required. Unknown hard constraints require clarification; known-but-unavailable facets produce honest no-results. Do not map Medium on every category to apparel size M.

Conversation/search work must record valid events through a local outbox. Use the shared outbox implementation rather than direct Kafka writes after a DB commit.

Acceptance: repeated HTTP requests create one cart effect/order reference; wrong cart version returns conflict; fabricated product/price from a stub composer cannot pass through as a purchase instruction.

### J05 — Optional single-call intent fallback; no planner loop

Follow common §6.2 exactly. fixed mode is the default and makes zero generative calls. In assist mode, only after deterministic parsing requires help and ALLOW_INTENT_LLM=true, make one schema-constrained intent call with 1,500-ms timeout. No automatic retry, correction call, model-selected tool loop or generative response. Preserve explicitly parsed hard filters. Invalid output/timeout returns clarification and a diagnostic. One search maximum; 3,000-ms total turn deadline with the remaining budget passed downstream.

Cart/quote/checkout/status actions remain explicit zero-model APIs, including confirmation bound to the exact quote/cart version. Product descriptions are untrusted data, never executable instructions. compose_response is a deterministic template function. Do not infer missing catalogue attributes or generate fake relevance labels.

Freeze provider/model/prompt settings if a live fallback is configured. Without it, all DE work proceeds; provider-spy tests verify call limits and live-model results stay NOT_RUN. Record all attempted calls, actual usage if returned, query embedding separately, stage durations, correct/unnecessary clarification and task success. A fast no-result/clarification cannot be presented as a successful recommendation unless the fixture expects it.

Acceptance: fixed/structured flows call the model zero times; enabled eligible fallback calls at most once even on failure; no invented price/stock/size, no implicit checkout; T-10 and D-05 pass.

### J06 — Independent reconciliation and integration

For every run reconcile emitted records, source dispositions, unique Silver IDs, active Gold membership and final outputs. For transaction runs compare immutable order totals with signed payment ledgers and inventory conservation.

Use read-only audit interfaces/snapshots approved by owners. Test fixtures may have direct read credentials for independent auditing, but production services must still respect their ownership boundaries. Your oracle does not issue corrective writes.

Drive G1 and G3 thin slices early. A missed handoff produces a failing contract test, not an ad hoc duplicate implementation inside M1.

### J07 — Run controlled experiments and prepare evidence

Freeze B0 and execute paired variants with the same controls. Each module owner explains their bottleneck and proposed change; you validate that comparisons are fair.

Report actual achieved rate, unfinished events, latency sample counts, resource cost and all three repetitions. Record why a candidate was selected or rejected. Generate final plots only after real measurements exist.

## 6. Tests you personally own

- T-10/D-05 fixed/assist workflow, exact model-call budget, intent evaluation and confirmation safety.
- D-01/02 independent dataset profile/normalization checks and D-04 comparable import measurement.
- projectctl suite/variant expansion, finite versus sustained duration accounting, result-schema validation and comparison-control checks.
- T-11 downstream-stall experiment, with Aditya/Vichitr providing hooks.
- Common contract/integration harness for T-01–T-12.
- Generator pacing and admission accounting, including coordinated-omission checks.
- Oracle tests with deliberately wrong Gold totals, duplicate debits, missing events and stale manifest references.
- Metric calculations: hand-computed tiny fixtures for p95/p99, goodput, lag and percentage changes.
- Idempotent cart/checkout delegation, timeout retry with the same key, explicit NOT_RUN handling.

You are not responsible for secretly repairing another person’s module to make the demo pass. File a failing case with the exact contract and fixture, then rerun after the owner’s fix.

## 7. Handoffs and acceptance

| Handoff | Your output | Who can proceed |
|---|---|---|
| G0 | Context propagation, contract stubs, fixture registry, runner/result schema | All owners |
| G1 | Independent one-event/invalid/duplicate oracle and smoke harness | Vichitr |
| G3 | Fixed workflow integrating quote/checkout and end-to-end assertion | Harsh and Aditya |
| G4 | Reproducible B0 run manifest/raw evidence | Optimization owners |
| G5/G6 | Controlled comparisons, dashboard and reproducible report | Whole team |

You are done when another teammate can reproduce a baseline and one variant from the runbook, your fixed workflow operates through real providers, your oracle detects intentional corruption, and every reported result resolves to saved raw evidence.

## 8. Evals you must code and run

Implement the exact projectctl commands/config schema in runbook §1 before benchmarking. Run `contracts,data,smoke`, then the full `correctness` alias, then T-10/D-05 and T-11. Orchestrate the required matrix in runbook §5; each provider supplies its domain adapters and fault barriers. You own the independent oracle and final evidence validation, not their normalization/reducer code.

Your outputs include tests.jsonl, assistant_turns.jsonl, emissions/timing/lag/resource artifacts, resolved run manifests, comparison reports and final tables. Verify all mandatory D/T cases have a status and evidence reference. Data profile counts may be asserted from the observed file; performance numbers remain null until actual execution. Use `benchmark reconcile`, `benchmark compare` and `report build`, not manual spreadsheet transcription.

Coding order is harness/data oracle → deterministic workflow → DE baseline/matrix → optional live fallback. Preserve this order to keep your workload focused on data engineering.

## 9. Prompt for your coding LLM

> I am Jaineel, owner of M1 and the benchmark/monitoring harness. Read the context, common specification, evaluation specification and this brief. Implement only task J01 first, with contract-valid provider stubs and independent expected fixtures. Do not implement inventory, payment, ranking, Gold reducers or a second outbox. Use the real dataset rules and implement the specified projectctl/evaluation artifacts. Fixed mode makes zero model calls; optional assist makes at most one. Keep performance result values NOT_RUN. List the exact contracts imported, tests executed and handoffs produced. Continue to the next numbered task only after its prerequisites pass.

