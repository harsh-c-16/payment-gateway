# Vichitr implementation plan

Prepared: 31 October 2026. Branch: `vichitr`. Status: M01–M04 infrastructure, contracts, transport and FileStore/Bronze capture foundations verified. Real outbox adoption and producer/G0 reviews remain pending. Next is M05 one-event-to-active-Gold. See [progress](progress.md), [M03 handoff](m03_transport_handoff.md) and [M04 handoff](m04_capture_handoff.md).

This divides the complete V01–V08 brief into smaller checkpoints. It adds no project scope and does not replace the canonical specifications. Implement one checkpoint at a time, verify it, record evidence, and stop before the next checkpoint.

## Project and current checkout

The project is an agentic shopping assistant backed by independently owned catalogue, transaction and analytical services. The data-engineering goal is a correct baseline followed by controlled optimization experiments, with independent reconciliation.

Your M4 path is: service-local outboxes → Kafka → exact-byte Bronze → validated/deduplicated Silver → Gold staging → immutable Parquet → active manifest → analytical readers. Kafka offset completion is not Gold visibility.

At inspection, `infra/`, the five M4 pipeline directories, `shared/event_transport/` and `shared/local_diagnostics/` contain scope READMEs; event contracts, analytics migrations and pipeline tests contain placeholders. Event/analytics DTOs and the analytics OpenAPI implementation are absent. Aditya's shared outbox implementation is also absent. Jaineel already supplies application dependencies/`uv.lock`, `projectctl`, telemetry, independent fixtures/oracles, and integration/benchmark/report machinery. His documented tests are previous evidence, not tests rerun for this plan. Real M4 integration and performance remain NOT_RUN.

Reuse the existing Python 3.11 application lock and installed dependency families. Do not restart Jaineel's P1–P11 playbook: it assigns his work, not yours.

## Scope and ownership

Implementation belongs in `infra/`, `contracts/events/`, `contracts/dictionaries/events/`, `shared/event_transport/`, `shared/local_diagnostics/`, `shared/contracts/events.py`, `shared/contracts/analytics.py`, `contracts/http/analytics.yaml`, `pipelines/{ingestion,curation,gold,replay,storage}/`, `migrations/analytics/`, and `tests/pipelines/`. Keep personal planning/evidence notes in `docs/vichitr/`.

Host the analytics application within an owned pipeline package; the repository does not assign a new `services/analytics/` directory. Use the specified analytics DNS/port and endpoints regardless of internal package placement.

Coordinate changes to application locks, evaluation configs, canonical specifications, common DTOs, CLI/harness composition and centrally maintained fixtures with their maintainers. Publish provider implementations from owned packages; do not take over consumer adapters or their tests. Keep small M4 fixtures in `tests/pipelines/`; Jaineel coordinates canonical shared fixtures.

Outside your implementation: Harsh's CSV parser/normalizer, catalogue/search/quotes/stock projection, compactor and query benchmarks; Aditya's outbox internals, Orders/Inventory/Payments and saga; Jaineel's assistant, general CLI, oracle, dashboard and report. You supply their documented interfaces and evidence.

## Module sequence

| Module | Work and deliverable | Brief | Completion checkpoint |
|---|---|---|---|
| M01 | Reproducible infrastructure and environment adapters | V01 + early V08 | Real Kafka/PostgreSQL/registry/file-volume health verified; enforceable resource profile and tested image digests recorded |
| M02 | Executable event, diagnostic and analytics contracts | V01 + contract portions of V02/V04 | Registered schemas, DTOs, reason dictionaries, analytics OpenAPI, valid/invalid examples and compatibility checks agree |
| M03 | Shared transport SDK and local diagnostics | V02 | Broker-acknowledged publishing, manual-offset consuming, stable validation and caller-local diagnostic/outbox behavior verified |
| M04 | Durable FileStore, Bronze capture and receipt foundation | V03 + minimum V05 | Exact source bytes can be recovered; storage failures cannot advance offsets |
| M05 | One-event-to-active-Gold vertical slice | V03 | Valid event is queryable through active files; duplicate has one effect; invalid bytes have a durable quarantine locator |
| M06 | Complete Silver cleaning and deduplication | V04 | All domain types supported; W-QUALITY dispositions reconcile; redelivery and identity/version conflicts behave correctly |
| M07 | Complete Gold reducers and business reconciliation | V04 | Latest states, distinct funnel stages, search metrics and cross-topic joins match independent expectations |
| M08 | Full manifest publication, crash recovery and compactor handoff | V05 | Every publication crash boundary is safe; stale/incorrect candidates cannot replace the current generation |
| M09 | Late data, watermarking and DLQ recovery | V06 | Fresh windows publish promptly; older valid facts revise them; DLQ broker outages preserve durable diagnostics |
| M10 | Isolated Bronze replay and lineage | V06 | Replaying twice into the same isolated target preserves logical results and leaves operational state unchanged |
| M11 | Correct baseline, batching and consumer-scaling experiments | V07 | Correctness-gated paired B0/O1 and P10/P30/P33 runs retain complete raw evidence, fixed controls and resource budgets |
| M12 | Final integration, operational rehearsal and handoff | V08 + integration support | Real integration/recovery gates, clean setup and reproducible evidence are reviewed with teammates; remaining limits explicit |

M01 → M02 → M03 → M04 → M05 is the first working slice. M06–M10 complete correctness and recovery. M11 starts only after the applicable real correctness gates pass. M12 closes delivery. CLI adapters, telemetry and integration hooks are added alongside their provider modules, not postponed until M12.

## Checkpoint details

### M01 — Infrastructure and environment

- Compose the specified Kafka 4.1.x KRaft single-broker, PostgreSQL 18 with pgvector 0.8.1 capability, real Schema Registry and durable shared volume. Verify exact compatible image versions/digests through an actual smoke test; do not invent locks.
- Preserve service database/credential isolation, specified DNS/ports, localhost exposure, health checks and explicit resource limits. Record actual host/WSL/Docker capabilities. The proposed 4-core/8-GiB profile must be enforceable; otherwise freeze a feasible documented profile for every comparison.
- Supply `env up/down/verify` and scoped benchmark reset providers for existing `projectctl`. Use its `ProviderRegistry`/`Invocation` and explicit `PROJECTCTL_ADAPTER_MODULE` composition seam. Coordinate database migration dispatch with all database owners; implement only analytics migrations yourself.
- Provide topic/group provisioning with namespace isolation, seven-day retention and explicit partitions. Schema-dependent readiness is completed in M02. Reset rejects dev/live namespaces and never deletes unrelated development data.
- Check: real environment startup/readiness, retained-volume restart, database isolation, topic provisioning and reset-scope rejection. Handoff: environment usage, resource profile, tested image lock and readiness limitations.

### M02 — Contracts and registry freeze

- Define schemas for five domain topics plus the separate `dead-letter.v1` notice, and the canonical event/analytics DTOs. Include every required event payload, nullable catalogue attributes, dataset/simulation provenance, and the reservation request identifier required for `INVENTORY_REJECTED` by common §11.4.
- Enforce plain UTF-8 JSON, schema-ID/content-type headers, exact topic/key/version rules, event ownership and size bounds. Register namespace-independent subjects with BACKWARD_TRANSITIVE compatibility; retain subject/ID/schema-hash mappings and verified cached schemas.
- Publish the six analytics contracts: active manifest, Gold query, receipts, replay creation, replay status and quarantine inspection; also health/readiness/metrics. Keep existing `/v1` and `/internal/v1` paths and internal token requirements.
- Check valid/invalid examples, compatibility evolution, unsupported schemas, header/key mismatch, strict integer/money/time rules and null preservation. Review payloads with producer owners and examples with Jaineel; explicit offline doubles remain labelled doubles.
- Handoff: executable contracts and registry mapping. G0 closes only when all owners' required contracts, locks and reviews exist.

### M03 — Transport and service-local diagnostics

- Export `build_event`, `validate_event`, `publish_event`, `consume_records`, `commit_offsets`, `build_dlq_notice` and `quarantine_local_diagnostic` through the agreed public packages. Preserve the existing M1 `SharedEvents` keyword-call binding.
- Allocate event identity/timestamps once. Cache verified schemas. Publish only with broker acknowledgement; report uncertain delivery as retryable without changing event identity.
- Freeze producer settings: idempotence enabled, `acks=all`, maximum in-flight requests ≤5, plus recorded compression/linger/buffer limits. Bound producer queues and group-wide consumer buffers; pause/resume while preserving heartbeats.
- Keep diagnostics and notice outbox entries in the caller's existing transaction. Supply the helper/table template; each service owner applies its own migration. Reuse Aditya's outbox interface without implementing a substitute.
- Check ack loss/retry, registry-cache behavior, queue saturation, partition revoke, contiguous durable offsets and transactional diagnostic rollback. A missing real outbox is a visible dependency; a test double cannot close real integration.

### M04 — FileStore, Bronze and receipts

- Implement the exact FileStore interface early because Harsh needs it to archive the unchanged CSV. Use immutable hash-verified paths, temporary writes, fsync and same-filesystem atomic rename on the durable volume.
- Bronze wrappers retain base64 key/value/header bytes, topic/partition/offset, broker/ingress timestamps, raw hash and file/row locator, including invalid UTF-8/JSON. Keep capture chunking fixed at 2 MiB or 50 ms across sink variants (user-approved increase, 31 October 2026).
- Add analytics migration foundations for source receipts, quarantine/outbox and processing records. Distinguish a redelivered source coordinate from a repeated event at a new offset; a coordinate with a changed raw hash is corruption.
- Check round-trip exact bytes, hash/path conflicts, bounded capture, disk/write failures and restart/orphan behavior. No Kafka acknowledgement precedes a durable disposition.

### M05 — Thin vertical slice

- Connect real consumption, Bronze, one schema's Silver fact, `pipeline_minute` count, durable source disposition, export-pending membership, immutable Silver/Gold files and atomic active manifests.
- Expose manifest/Gold/receipt/quarantine reads against actual published files. Freeze exact included IDs and record post-commit visibility observations. Readers pin one generation; never glob files.
- Quarantine invalid input and enqueue its notice atomically with the disposition using the shared outbox. Commit only contiguous durable offset prefixes.
- Check one valid record, identical event at another offset, same-offset restart redelivery and malformed bytes. Supply hashes, coordinates, dispositions, active generation and visibility evidence for Jaineel's G1 review. Full harness G1 may still need his provider/setup bindings; report that dependency honestly.

### M06 — Full Silver and quality accounting

- Extend validation/typed normalization to every domain schema, with versioned event dictionaries, explicit optional nulls, preserved immutable envelope hashes and complete provenance. Consume Harsh's canonical facets/hashes; do not infer attributes or repeat source cleaning.
- Atomically persist source disposition, unique Silver insertion, contribution identity, Gold updates/export markers, quarantine and notice outbox. Keep B0 at one source record per sink transaction.
- Handle same-ID/same-content duplicates, altered-content conflicts, same-version conflicts and durable redeliveries without duplicate effects. Retry infrastructure/transaction failures with bounded backpressure; do not classify them as dirty input.
- Check W-QUALITY: 100,000 distinct source records → 98,500 unique valid IDs + 1,000 duplicate deliveries + 500 invalid dispositions. Check altered-content and aggregate-version adversaries separately, plus nullable facets and UTC boundaries. Expected counts are fixture assertions, not measured results.

### M07 — Complete Gold semantics

- Implement common §11.4 tables: pipeline minute, latest order fact, daily conversion, distinct checkout funnel, distinct payment/inventory failures and search performance. Import intent/retrieval quality only from actual labelled evaluation artifacts; never compute invented online quality scores.
- Preserve integer/exact monetary arithmetic, latest aggregate versions and distinct contribution/stage identities. Reconcile payment/inventory facts arriving before orders; multi-SKU rejection facts count one reservation request.
- Persist pending joins and dirty keys transactionally. Keep raw duration references for exact quantiles instead of averaging p95 values.
- Check reordered/duplicate terminal events, provisional replacements, parent-late joins, multi-SKU failures, null denominators and currency totals against independent fixtures. Handoff complete business Gold for G3 when operational providers are ready.

### M08 — Publication and candidate safety

- Harden the minimal M05 publisher for full Silver/Gold exports: consistent database snapshot, exact frozen event membership, full immutable file lists, hash/schema/count validation, one publisher per namespace and compare-and-swap generations.
- Clear only included pending IDs; retain concurrent arrivals. Keep visibility membership and a retriable observation journal; missing timing remains missing or an explicitly marked recovery upper bound.
- Validate Harsh's `ManifestCandidate` for logical row digest, row count, currency totals, schema and base generation. Reject stale candidates with `STALE_MANIFEST`; never mutate his source snapshot.
- Check crashes before rename, after file durability, before pointer commit and after pointer commit; concurrent ingestion; stale/incorrect candidates; and reader-pinned retired generations. No cleanup during measured/fault runs. Supply T-07 publication/sink and T-12 evidence plus T-04 publication support.

### M09 — Late data and DLQ recovery

- Implement 60-second event-time windows, 120-second allowed lateness, per-partition maxima and 10-second idle exclusion. Validate normal-fixture future timestamps against the five-second bound.
- Publish provisional windows on the fixed 250-ms cadence; valid late events revise affected windows with `LATE_RECONCILIATION` lineage. Measure initial visibility and late correction separately.
- Complete quarantine inspection, stable reasons, durable notification retry and restricted diagnostic references. Keep DLQ notices outside business topic ingestion and outside invalid-ingress arithmetic.
- Check older-than-120-second facts, resumed idle partitions, future timestamps, DLQ broker outage/recovery and infrastructure failure classification. Never delay every new event by the lateness allowance.

### M10 — Replay and provenance

- Implement analytics replay creation/status and owned replay providers using the same validation/reducer path. A new job starts in an empty isolated target; restarting/repeating that job into its existing target must be idempotent.
- Preserve original bytes, event IDs, event/production times, original namespace/topic/headers and source references. Use a separate effective namespace for analytical keys/manifests and an explicit replay time policy.
- Compare semantic digests/counts/states/money while excluding execution-only namespace/time/generation values. Repairs require a new event ID and repair reference, first evaluated in isolation.
- Check replay twice into the same target, invalid-record replay, transform-version comparison, failure before publication and unchanged operational stock/payments/orders. Never call operational mutation APIs or republish replay to live business consumers.
- Retain Bronze/dedup/manifests/evidence for at least 30 days and through final acceptance, whichever is later; active replay/reader references prevent deletion. Lineage includes code/lock/dictionary hashes and exact source membership, not only min/max offsets.

### M11 — Baseline and measured experiments

- Instrument from earlier modules using existing telemetry: source dispositions, sink batches/flush time, one-second partition/group lag, stage/visibility receipts, export backlog, queue saturation and resources. Jaineel owns collection/orchestration and independent metric calculation; supply the real provider observations and fault hooks.
- First close applicable T-01/T-03, sink/publication T-07 and T-12 correctness. Freeze a correct B0 and diagnose its bottleneck before tuning.
- Checkpoint M11a: run W-PIPE B0 versus O1 (1-row transactions versus 100 rows or 50 ms). Keep raw capture, producer settings, validation, durability and 250-ms publication cadence identical. Follow with applicable integrated trials through Jaineel's runner.
- Checkpoint M11b: run P10/P30/P33 on fresh topics (1 partition/1 consumer, 3/1, 3/3), uniform and 80% hot-key traffic. Keep total CPU/RAM, group-wide buffers and 12 analytics sink connections fixed; three consumers split that pool to four each. Publisher pool stays at most two.
- Use three paired repetitions, 60-second warmup, 600-second measurement and 120-second drain for sustained runs. Finite W-QUALITY uses actual completion time. Save all runs, including failures and neutral results.
- Run required 500/1,000/2,000 events/s stress with Jaineel and selected configurations, plus pause/restart/rebalance trials; 5,000/s is optional only after valid lower tiers. Reconcile every admitted source record and valid event; report incomplete cohorts and missing timing honestly.
- Handoff T-02/T-05 raw results, hypotheses, memory/latency costs and bottleneck conclusions. Jaineel selects combined C-BEST from measured evidence; no configuration is assumed the winner.

### M12 — Integration and operational delivery

- Complete/review existing CLI setup, migration dispatch, provisioning, reset, receipt and replay provider wiring. Keep readiness/failure exit behavior compatible; do not add a competing CLI or invent replay CLI commands absent from the canonical surface.
- With owners, exercise search → cart → quote → confirmed/declined checkout → stock projection → matching active Gold. Supply analytics/Kafka stop/restart observers and named fault acknowledgements for separate 30-second T-11 outages.
- Finish G4/G5/G6 handoffs and a fresh-checkout setup rehearsal using the locked environment and actual evidence. Supply read-only scoped audits and pinned manifests to consumers. Harness mapping/fixture reviews require real owner review; never generate approval claims.
- Document single-broker and single-volume limits, storage/backlog bounds, missing providers and unfinished checks. Hand evidence to Jaineel for reproducible reporting and to Harsh for compaction/query checks.

## Dependencies and review points

| Provider | Needed input | First use / consequence if absent |
|---|---|---|
| Jaineel | Existing dependency lock, CLI registration, telemetry, independent fixtures/oracle and reviewed harness bindings | M01 onward; implement providers in owned packages and coordinate consumer registration |
| Aditya | `append_outbox`, acknowledged relay interface, caller-local DDL and domain snapshots | M03 onward; unit doubles are explicit, real diagnostic/DLQ and integrated gates wait for actual outbox |
| Harsh | Catalogue/SKU/facet/rules manifests and hashes | M02/M06 and benchmark setup; no guessed facets or fabricated 10,000-key SKU subset |
| Harsh | Pinned manifest compaction candidates | M08; candidate validation can have local fixtures, real T-04 needs his compactor |
| Harsh + Aditya | Real catalogue/transaction/projection APIs, seed controls and audit exports | G3/M12; pipeline-only tests cannot certify business integration |
| Producer owners + Jaineel | Payload/SDK/fixture and audit mapping reviews | Contract freeze and real harness execution; maintain exact canonical names/types |

Before implementing M02/M03, resolve any contract mismatch explicitly. In particular, common §5 requires a new replay target to be empty while §12 requires replay twice into the same target: distinguish new-job creation from repeat/resume, and obtain consumer review rather than silently weakening namespace isolation. Schema-ID/hash readiness, diagnostic/outbox record types, source-versus-effective replay namespace and M1 builder exports also need joint review.

## Working rhythm and next action

1. Start the named module by inspecting its current files, public callers, consumer fixtures, config and required exports. Recheck Git status; preserve unrelated work.
2. Implement only that module, including its failure handling, relevant tests and consumer handoff. Reuse the existing lock, telemetry and CLI seams. Coordinate shared-file changes with the maintainer.
3. Run focused unit/contract tests and appropriate real infrastructure checks. Only real Kafka/PostgreSQL/storage checks can support offset, concurrency and crash-recovery claims.
4. Record paths, exact commands/outcomes, evidence, limitations, review needs and next handoff in `docs/vichitr/progress.md` when implementation begins. Benchmark artifacts stay in the existing ignored result directories.
5. Stop at the checkpoint for review. The user has authorized committing and pushing each completed module to `vichitr`; do so after its checks pass, excluding credentials, raw data and generated artifacts. Never force-push or merge to `main` without a separate request.

Current checkpoint: **M04 FileStore/Bronze/capture-ledger foundations verified**. Exact bytes survive real Linux fsync/rename, source retries, caller rollback, an acknowledged process crash and PostgreSQL/worker restart. The user approved the 2-MiB encoded capture cap; all metadata remains inside that bound. Capture rows are not final source dispositions and cannot authorize Kafka commits. M03 transport remains available; real outbox/service adoption remains pending. Full G0/G1 remain incomplete. Next is M05 one-event-to-active-Gold. Evidence is in [progress](progress.md).

## Source documents

- [Repository rules](../../AGENTS.md), [ownership](../OWNERSHIP.md) and [root README](../../README.md).
- [Project context](../specs/01_PROJECT_CONTEXT.md), [common specification](../specs/02_COMMON_SPEC.md), [evaluation specification](../specs/03_EVALUATION_SPEC.md).
- [Vichitr V01–V08 brief](../specs/07_VICHITR_ARORA.md), [dataset rules](../specs/08_DATASET_PROFILE_AND_RULES.md), [evaluation runbook](../specs/09_EVALUATION_RUNBOOK.md).
- [Existing CLI and provider seam](../../projectctl/README.md), [integration bindings/runbook](../integration_runbook.md), [telemetry](../../shared/telemetry/README.md), [Jaineel progress and remaining handoffs](../jaineel/progress.md).

The README's V01–V07 shorthand omits V08; this plan includes the full personal brief. The older planning-pack statements that no code exists do not describe the current M1/harness checkout. No performance claims are inferred from those documents or from this plan.
