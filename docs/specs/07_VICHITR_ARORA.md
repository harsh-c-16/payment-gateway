# Vichitr Arora: personal coding brief

Module owner: M4 infrastructure, events, ingestion, curation, Gold, publication and replay  
Version 2.0. Read first: 01_PROJECT_CONTEXT.md, 02_COMMON_SPEC.md, 03_EVALUATION_SPEC.md, 08_DATASET_PROFILE_AND_RULES.md and 09_EVALUATION_RUNBOOK.md. The dataset rules and evaluation commands are required implementation inputs, not optional background.

## 1. Your final responsibility

Build a reproducible, observable data path from versioned Kafka records to raw Bronze, deduplicated Silver and queryable Gold. Own schema governance, file/manifest durability, quarantine and replay. **Your ingestion is Kafka event ingestion; Harsh owns CSV catalogue ingestion and normalization.** You provide FileStore and consume catalogue/dictionary hashes, without re-parsing or re-normalizing source product rows.

**Workload adjustment:** Jaineel owns the monitoring dashboard and general benchmark harness. Harsh owns file compaction candidates and query benchmarks. You expose stable interfaces and publication support to them. You do not own their implementations or the assistant/backend business logic.

Your engineering comparisons are sink batching and partition/consumer scaling. Your correctness obligation includes offset commits, event deduplication, late updates and replay.

## 2. Files and contracts you own

- infra/, infrastructure image/digest lock, topic/group provisioning and resource profiles.
- contracts/events/, contracts/dictionaries/events/, event reason codes and registry manifests. Harsh owns contracts/dictionaries/catalog/ and source-import schemas.
- shared/event_transport/ and shared/local_diagnostics/.
- pipelines/ingestion/, curation/, gold/, replay/ and storage/.
- migrations/analytics/, analytics API, manifest/receipt DTOs.
- T-01/02/03/05/12 module evidence, plus sink/publication portions of T-07.
- Durable schema-compatible examples for all domain payloads, reviewed by their owner.

Implement the functions and analytics endpoints specified in common §§5–7 and §§11–12. An endpoint name in this brief does not override the common specification.

## 3. What you require as black boxes

| Provider | Contract | What you may assume |
|---|---|---|
| Aditya | append_outbox(tx,event), relay_once | Local transactional persistence; acknowledged transport; possible duplicate publication |
| Aditya | Order/payment/stock payloads | Complete immutable snapshots and declared aggregate versions |
| Harsh | Catalogue/SKU/facet/rules manifests; optional embedding manifest | Latest-pid listing IDs, source hashes, nullable attributes and dictionary revision; active count 19,920 for this source |
| Harsh | compact_snapshot → ManifestCandidate | Candidate is immutable; you must still verify equivalence and generation |
| Jaineel | WorkloadManifest and expected oracle | Known logical record classes, open-loop rates and scenario identities |
| Jaineel | Telemetry helpers and observer | Fixed metric names/units, independent run timings and resource collection |
| All owners | Domain event contracts | Valid producers in the normal path; deliberately invalid raw bytes exist in tests |

Never trust producer validation as your only validation. Never assume Kafka producer idempotence suppresses a business event republished after a process restart.

## 4. Ordered coding tasks

### V01 — Reproducible environment and schemas

Provision local Kafka KRaft, PostgreSQL with pgvector capability, real Schema Registry and the shared file volume. Use the specified service ports/DNS, health checks and fixed resource profiles. Coordinate application locks with Jaineel and model revision with Harsh.

Create the five business topics plus DLQ notification topic, independent consumer groups, retention and explicit partition counts. Register the JSON Schemas and record subject/ID/hash mappings. The wire payload remains plain JSON with the schema ID in a Kafka header; do not use a binary serializer accidentally.

Acceptance: a teammate can start the environment, verify schema readiness and consume one valid event without knowing your infrastructure internals. Exact versions/digests are recorded after a real smoke test.

### V02 — Shared event transport and diagnostics

Implement build_event, validate_event, publish_event, consume_records and commit_offsets. Pin producer semantics across all variants: enable.idempotence=true, acks=all, max.in.flight.requests.per.connection<=5; set and record compression/linger/buffer limits once. Single-broker acks=all still means only that broker’s in-sync replica in this profile.

publish_event returns broker delivery acknowledgement, never merely a queued future. The adapter can manage bounded concurrent requests; callers must not create unbounded tasks to hide backpressure.

Implement a local diagnostic/quarantine helper callable with each service’s own transaction. It persists a diagnostic record and a DLQ notification outbox entry without writing another service’s database. This handles M1 invalid model output and M2 projection conflicts. M4’s raw quarantine continues to use Kafka source coordinates.

Acceptance: invalid schema/key/version errors have stable reason codes; cached registered schemas avoid per-event registry calls; transport uncertainty is explicit.

### V03 — One-event vertical slice

Write exact bytes into durable Bronze. Implement analytical receipts, unique Silver insertion, one Gold count and active-manifest publication. Wire the analytics read API to actual manifest-listed files.

Run Jaineel’s minimal valid/invalid/duplicate fixtures. A consumer offset cannot advance ahead of durable source disposition. Do not postpone manifest publication correctness until after the benchmark: it defines the measured endpoint.

Acceptance: one valid event is queryable, one duplicate changes no total, and one malformed record is recoverable from its raw locator.

### V04 — Cleaning, deduplication and Gold reducers

Add all event schemas and normalized typed Silver fields, including nullable category/brand/size/colour/material and dataset_revision. Harsh's canonical catalogue facets must not be guessed or overwritten by event cleaning. Never use historical crawl_timestamp as live event_time or producer-to-Gold latency origin. All simulated stock/payment/order facts carry explicit simulation provenance.

Add complete event validation. Preserve original raw bytes; use versioned dictionaries; keep missing optional values null. Reject rather than guess impossible mandatory values.

Write source disposition, Silver insert, contribution identity, Gold staging update, dirty/export markers and quarantine notification atomically in analytics_db. Batch-size=1 is B0; batching changes transaction grouping only.

Implement latest-version order/payment state and distinct funnel sets. Out-of-order payment/inventory facts must wait for or reconcile with the parent order. Do not add counters twice on replay or count multi-SKU rejection facts as multiple failed reservations.

Acceptance: W-QUALITY yields the exact independent expected counts; altered-content duplicates and same-version conflicts are quarantined; all valid IDs reach active Gold.

### V05 — Immutable files and publication recovery

Implement FileStore and full manifest generations. Gold/Silver exporters freeze exact included event-ID sets using a consistent database snapshot. They publish pointers only after files are durable and verified.

Keep a single publisher per namespace. Compare-and-swap expected generation. Capture post-commit visibility observations and expose missing timing honestly. Readers use one manifest generation; never glob active plus retired files.

Implement candidate validation/publication for Harsh’s compactor. A stale base generation must not overwrite newly ingested data.

Acceptance: all publication crash points leave either the old or new complete dataset queryable; no half-published manifest, lost pending event or double-counted replacement.

### V06 — Late data, DLQ and replay

Implement watermark/idle-partition rules, provisional publication and late revisions. A two-minute allowance must not delay every fresh event by two minutes.

Store raw quarantines with source locators/reasons and notify through a durable outbox. Infrastructure outages cause retry/backpressure, not a misleading dirty-record classification.

Replay unmodified Bronze into an isolated effective namespace, preserving original bytes/IDs/timestamps and lineage. Do not call operational services. Repeat replay must be idempotent. Repair changes content only under a new event ID with a repair reference.

Acceptance: a late event revises the correct window; repeated replay preserves totals; original Orders/Inventory/Payments remain unchanged; failed replay does not replace the current live manifest.

### V07 — Batching and consumer scaling

Instrument sink transactions, batch sizes, stage delays, lag and pending exports. Run B0/O1 through Jaineel’s runner. Report memory/latency trade-offs rather than assuming batches always help.

For P10/P30/P33, use newly created topics and fixed total worker resources. Add the 80% hot-key workload and pause/restart/rebalance trials. A single publisher or database can become the bottleneck even when consumers scale; show that in stage evidence.

Acceptance: every variant passes the same count/invariant/replay tests and preserves schemas/keying/durability.

### V08 — Integration, operational limits and shared CLI adapters

Implement the environment/provision/reset/receipt/replay adapters for Jaineel's projectctl CLI in runbook §1; do not invent a competing CLI. Harsh owns catalog import, Aditya inventory seed. Publish readiness conditions and failure limitations. Namespace resets must be scoped. Explain the single-broker/single-volume limits and monitor unpublished outbox accumulation.

Give Jaineel receipts and metrics, not manually transcribed sample numbers. Give Harsh pinned manifests and the candidate-publication API, not unrestricted analytics database write credentials.

## 5. Functions and failure contracts to test

| Function | Failure you must handle |
|---|---|
| publish_event | Broker accepted but ack/connection lost; retry may create a delivery duplicate |
| ingest_bronze | Invalid UTF-8; disk full; crash before/after durable file |
| curate_silver | Same source offset replay, same event new offset, altered same-ID payload |
| aggregate_gold | Payment before order; duplicate terminal event; revision of provisional window |
| commit_offsets | Gap before a completed later offset; partition revoke during batch |
| publish_snapshot | Crash with orphan files, pointer transaction failure, observation timestamp missing |
| route_dlq | Notification broker unavailable after local durable quarantine |
| replay_bronze | Original namespace differs from isolated processing namespace; repeated replay |
| publish_candidate | Concurrent newer generation, wrong digest/row count, old files still referenced |

## 6. Handoffs

| Gate | Your output | Consumer |
|---|---|---|
| G0 | Compose/profile, schema mapping, event SDK, local diagnostic interface and topic contracts | All owners |
| G1 | Real one-event-to-active-Gold slice plus raw/receipt API | Jaineel |
| G2/G3 | Stable consumer adapter and inventory topic | Harsh’s projection |
| G4 | Complete correct B0 data path and recovery evidence | Benchmark runner |
| G5 | Pinned snapshots/candidate publisher | Harsh |
| G5/G6 | Batching/scaling results, replay/late-data audit and final manifests | Jaineel/evaluators |

You are done when every accepted record can be traced from source to a declared durable disposition, visible Gold survives the tested crashes, and a clean isolated replay reconstructs the same logical outputs.

## 7. Evals you must code and run

Run the one-event/duplicate/invalid smoke slice, T-01/03 and sink/publication T-07 before performance work. Implement W-QUALITY's independent expected disposition checks, T-12 isolated replay/late-data/publication cases, and the exact timestamp/lag/visibility collectors required by the evaluation spec. The input catalogue is historical; benchmark event timing remains live.

Run W-PIPE B0/O1 and P10/P30/P33 with three paired repetitions using runbook §5. Keep raw chunking, Gold cadence, schemas, durability and total worker resources fixed. Run uniform versus hot-key workloads, 500/1,000/2,000 tiers, consumer pause/rebalance and T-11 with Jaineel. Do not claim throughput improvement from dropping null-attribute products or skipping expensive validation.

Handoff raw/source dispositions, stage and Gold visibility receipts, partition lag, resources, active manifests, fault barriers, replay equality and source lineage. Give Harsh pinned data and a publication adapter for T-04; he implements compaction/query timing. No LLM calls in ingestion, cleaning, Gold or replay.

## 8. Prompt for your coding LLM

> I am Vichitr, owner of streaming, schemas, curation, publication and replay. Read all shared documents and this brief. Start V01 with reproducible infrastructure, executable event contracts and shared projectctl adapters. Respect the real-catalogue nullable fields and separate source-crawl versus runtime timestamps; Harsh owns CSV normalization. Use a real registry and plain JSON transport as specified. Do not implement the dashboard, compactor, assistant or payment saga. Commit offsets only after durable processing, preserve original bytes and use manifest-based publication. Report actual tests, missing dependencies and precise handoff artifacts.

