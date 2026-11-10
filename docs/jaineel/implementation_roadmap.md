# Jaineel implementation roadmap

Use one prompt per coding session, in order. Each prompt ends at a checkpoint so you can review the work before moving on. This roadmap is a working sequence; `docs/specs/02_COMMON_SPEC.md` remains the interface authority, `docs/specs/08_DATASET_PROFILE_AND_RULES.md` remains the data authority, and `docs/specs/03_EVALUATION_SPEC.md` plus `docs/specs/09_EVALUATION_RUNBOOK.md` remain the evaluation authority.

## Decisions to carry into implementation

- **Relevance labels:** Keep Harsh's rule-generated labels out of certified quality claims for now. The frozen evaluation asks for manually reviewed labels, and the held-out rules were adjusted after looking at labels. If the team elects to use them as provisional diagnostics, every report must say that; their unjudged-result handling also needs review against the runbook.
- **Session reuse:** Keep `CATALOG_REUSE_CONNECTIONS=false` for the frozen baseline. Session reuse is outside the registered matrix. Evaluate it later as a separately reviewed extension with frozen controls and interaction evidence; do not silently call it C-BEST.
- **Natural-language brand parsing:** Do not turn every dictionary match into a brand constraint. Accept clearly cued brand filters; for ambiguous collisions, clarify or retain the phrase as query text. Preserve existing frozen assistant scenarios and document any intended semantic change for review.
- **Dataset hashes:** Harsh's dictionary hash is for LF-normalized text. This Windows checkout reads CRLF bytes, while evaluation preflight uses raw-byte hashes. Resolve and verify cross-platform hash policy before pinning the dictionary in evaluation config. Do not silently replace the dataset revision or published hash.
- **Current branch:** Current follow-ups use `jaineel/prototype-demo`, as explicitly requested by the user. Stay on that branch and push only when requested. Earlier `jaineel/j03-telemetry` references describe historical checkpoints.
- **Existing work:** Preserve `docs/jaineel/P1_P7_AUDIT.md` and `docs/jaineel/P1_P9_AUDIT.md`. Keep changes within Jaineel's owned paths. For a provider defect, capture the smallest failing consumer case and give the owning teammate the exact file, contract and observed behavior; do not implement their service.
- **Evidence:** For each checkpoint, record changed paths, exact commands and results, evidence locations, visible skips, unresolved owner handoffs and manual steps in `docs/jaineel/progress.md`. Never present test doubles as live integration or NOT_RUN as pass.

## Prompt 1 — Fix M1 search and intent regressions

```text
I am Jaineel. Work only on Prompt 1 in docs/jaineel/implementation_roadmap.md. Read AGENTS.md, docs/OWNERSHIP.md, docs/specs/01_PROJECT_CONTEXT.md, the relevant sections of docs/specs/02_COMMON_SPEC.md and docs/specs/04_JAINEEL_VORA.md, docs/harsh/handoff.md, services/conversation/workflow.py, services/conversation/intent.py, and their existing tests before editing.

Stay on the current branch. Preserve all existing work. Edit only services/conversation/, tests/conversation/, and my progress file. Do not edit Harsh's tests/catalog test or canonical catalogue contracts. Do not change public APIs, shared DTOs, reviewed scenario contents, fixture labels, or the dataset revision.

Fix the consumer's brand comparison using the agreed case/canonicalization rules. Make free-text extraction conservative where dictionary values collide with ordinary product words. Unknown or ambiguous hard constraints must clarify; do not silently add a brand/colour/material/size filter. Add regression coverage for mixed-case display-brand versus key, “blue cotton shirt”, “laptop skin”, explicitly cued brand, and ambiguous/unsupported constraints. Preserve zero-model-call fixed behavior and existing checkout controls.

Run the focused conversation tests and owned lint/format checks. The real-catalogue strict-xfail lives under Harsh's tests/catalog path: leave its marker untouched, report the exact result Harsh should review, and do not claim that a stub test proves live catalogue behavior. Update docs/jaineel/progress.md with commands, outcomes and limitations. Stop at this checkpoint; do not start Prompt 2.
```

**Checkpoint:** M1 regressions have owned tests and pass. The catalogue live xfail is explicitly handed back to Harsh for review/removal after the fix.

## Prompt 2 — Adopt the shared event path in M1

```text
I am Jaineel. Work only on Prompt 2 in docs/jaineel/implementation_roadmap.md. Read AGENTS.md, docs/OWNERSHIP.md, docs/specs/02_COMMON_SPEC.md §§7, 14–15, docs/specs/04_JAINEEL_VORA.md J04/J06, docs/vichitr/m02_contract_handoff.md, shared/event_transport/, shared/outbox/, services/conversation/events.py, services/conversation/database.py, and the conversation migrations/tests.

Stay on the current branch. Edit only services/conversation/, migrations/conversation/, tests/conversation/, and docs/jaineel/progress.md. The outbox implementation and shared event schemas are owned by teammates: consume their public functions and schemas; do not edit or duplicate them. Before changing an event shape or producer behavior, identify the exact contract, current consumer and required owner review. Preserve the existing migration history; add a forward migration rather than rewriting an applied migration.

Make M1 readiness establish that the pinned event schemas/cache and the shared transactional append path are actually usable, not merely importable. Ensure the conversation database installs the shared outbox DDL using the owner's documented template, within the conversation database only. Bind the required dataset revision/provenance from the approved catalogue handoff. Review which conversation facts M1 must emit and make each required state change and outbox append atomic. Keep event building and transport separate from Kafka publishing.

Add tests for missing cache/schema/outbox failure, ready behavior, schema-valid events, rollback atomicity and idempotent retries. Use explicit doubles only in tests that declare them. Run focused PostgreSQL-backed conversation tests if the documented isolated database is available; otherwise preserve the exact live check as NOT_RUN. Run owned lint/format and migration/schema checks. Record outcomes and remaining Vichitr/Aditya handoffs in docs/jaineel/progress.md. Stop at this checkpoint.
```

**Checkpoint:** M1 can fail closed when its event dependency is unavailable, and a successful M1 mutation commits its state and event together in its own database.

## Prompt 3 — Build the real projectctl composition

```text
I am Jaineel. Work only on Prompt 3 in docs/jaineel/implementation_roadmap.md. Read AGENTS.md, docs/OWNERSHIP.md, docs/specs/04_JAINEEL_VORA.md J01/J02/J06, docs/specs/08_DATASET_PROFILE_AND_RULES.md, docs/specs/09_EVALUATION_RUNBOOK.md §§1–3, docs/integration_runbook.md, projectctl/providers.py, benchmarks/experiment.py, benchmarks/integration.py, and the current owner adapters/handoffs.

Stay on the current branch. Edit only my projectctl/, benchmarks/, tests/projectctl/, tests/benchmarks/, tests/integration/, configs/evaluation.yaml, and docs/jaineel/progress.md paths. Do not modify another owner's service, adapter, migration, schema or Docker Compose configuration. Do not make up provider exports. Keep unavailable registrations visibly unavailable.

Add an explicit Jaineel composition module that connects only existing provider APIs. Compose the real available register() functions without duplicate registrations. Bind the catalogue importer, analytics query adapter and verified runner_catalog_manifest to their workload drivers. Build the lifecycle callbacks needed for one narrowly scoped real workload, including fresh namespace preparation, source/import/seed checks, projection wait after stock seeding, drain, independent audit and observer. Do not reset non-benchmark data or write across service databases.

Review evaluation config against the frozen matrix. Set the catalogue pool to the frozen four-connection cap in the appropriate owner configuration. Resolve dictionary and query hash semantics consistently across Windows/Linux before filling hashes. Fix .env.example names/values only in the Jaineel-coordinated file, retaining QUOTE_TTL_SECONDS which is already present. Do not enable session reuse or select rule labels as human-approved.

Add focused composition/registration/preflight tests. Verify missing owner callbacks yield dependency evidence instead of a stub pass. Run projectctl and owned test/lint/schema checks; do not start a full benchmark. Record changed paths, exact outcomes and missing owner registrations in docs/jaineel/progress.md. Stop at this checkpoint.
```

**Checkpoint:** the CLI composes real adapters that exist, preserves explicit missing providers, and passes a small setup/readiness path without measuring performance.

## Prompt 4 — Close the real G1 and W-QUALITY bindings

```text
I am Jaineel. Work only on Prompt 4 in docs/jaineel/implementation_roadmap.md. Read AGENTS.md, docs/specs/03_EVALUATION_SPEC.md §§7, 9, docs/specs/08_DATASET_PROFILE_AND_RULES.md, docs/specs/09_EVALUATION_RUNBOOK.md §§3, 7, docs/vichitr/m11_baseline_handoff.md, benchmarks/quality.py, benchmarks/drivers.py, pipelines/ingestion/quality.py, benchmarks/reconciliation.py, and the existing owner fixtures/tests.

Stay on the current branch. Edit only my benchmark/oracle/test/fixture paths and docs/jaineel/progress.md. Do not change Vichitr's producer/consumer, schema or raw publisher. Bind the existing QualityMaterializer to a verified Harsh SKU manifest and Vichitr EventCodec, and bind the harness's explicit raw-fixture publisher only to invalid-quality records. Normal events must still pass the SDK's validation. Reuse persisted packets for duplicate deliveries.

Implement the real setup, execution, receipt/offset observation, drain and independent audit callback using reviewed owner APIs. Expected dispositions must come from my independent fixture/oracle, not from the production cleaner or sink output. Prove all planned physical deliveries and logical outcomes are accounted for. Preserve missing timers, missing data and unexecuted checks as null/NOT_RUN. Do not weaken the 100,000-record assertions to make a partial run pass.

Add/run small deterministic offline tests first. Run the real G1/T-03 trial only when locked PostgreSQL/Kafka/registry, catalogue manifest, seed/projection and owner-approved read-only evidence are available. If any dependency is missing, retain its exact reason and stop before claiming G1. Record evidence paths and status in docs/jaineel/progress.md.
```

**Checkpoint:** the complete real T-03/G1 fixture reconciles, or the exact external blocker is evidenced and the gate remains incomplete.

## Prompt 5 — Bind G3 transactions and recovery

```text
I am Jaineel. Work only on Prompt 5 in docs/jaineel/implementation_roadmap.md. Read AGENTS.md, docs/specs/02_COMMON_SPEC.md §§5, 9, 14–15, docs/specs/03_EVALUATION_SPEC.md §§7–9, docs/specs/04_JAINEEL_VORA.md J04/J06, docs/integration_runbook.md, benchmarks/integration_cases.py, benchmarks/integration_faults.py, benchmarks/drivers.py, and docs/harsh/handoff.md.

Stay on the current branch. Edit only my benchmarks/, tests/integration/, tests/oracles/, tests/benchmarks/ and docs/jaineel/progress.md paths. Aditya owns order/inventory/payment behavior and fault hooks; Harsh owns catalogue/quote/projection behavior; Vichitr owns Kafka/Gold/replay. Do not patch their services or change public contracts unilaterally.

Implement one reviewed real G3 success/decline binding through public HTTP/event interfaces. Retain the same request/session/cart/quote/confirmation identities. Audit owner snapshots read-only and reconcile order totals, signed payment ledger, stock conservation/projection, event receipts and active Gold membership independently. Unknown outcomes remain unknown until backend evidence establishes finality.

Compare the compaction fault implementation's exact boundary (after_candidate_files_before_publish / compaction) with integration_cases.py. Add a case only after defining expected recovery facts and obtaining affected owner review; do not map it to stale-manifest rejection if that tests a different boundary. Also capture Aditya's quote-expiry/idempotency concern as an owner handoff and a consumer regression case; do not silently repair Orders in my branch.

Start with unit tests using explicit doubles, then run real G3 only with the reviewed database/audit/fault bindings. Missing hooks, active Gold, ledger or real provider evidence must block a real pass. Preserve raw receipts and update docs/jaineel/progress.md. Stop at this checkpoint.
```

**Checkpoint:** G3 is independently reconciled using real providers, or the missing owner-reviewed binding remains visibly NOT_RUN.

## Prompt 6 — Expand CI and make repository checks truthful

```text
I am Jaineel. Work only on Prompt 6 in docs/jaineel/implementation_roadmap.md. Read AGENTS.md, docs/OWNERSHIP.md, docs/specs/03_EVALUATION_SPEC.md §7, docs/specs/09_EVALUATION_RUNBOOK.md §§3, 8, .github/workflows/offline.yml, benchmarks/manual/verify_p5.py, benchmarks/manual/verify_p6.py, benchmarks/manual/verify_p7.py, benchmarks/manual/verify_p11.py, and docs/vichitr/test_skips.md.

Stay on the current branch. Edit only .github/workflows/, my benchmark verifier files, my tests and docs/jaineel/progress.md. Do not broaden a CI job into a real database/broker claim unless it provisions the pinned dependency. Separate offline tests, PostgreSQL tests, and Kafka/registry tests clearly. Keep uploads of failure logs and JUnit evidence. Tests that require unavailable real services must be reported as explicit skips/NOT_RUN; test doubles must remain labelled as doubles.

Ensure CI runs the owned conversation suite and appropriate catalogue, analytics, pipeline, transaction, contract, projectctl, benchmark, oracle, telemetry and integration coverage through correct dependency-backed jobs. Review strict xfails and verifier expected exit codes against current merged code. Fix my owned stale expectations; for another owner's existing failure, preserve the failing evidence and file the exact ownership handoff. Do not weaken assertions, delete skips or accept failures to get a green job.

Run the exact offline command locally and any safe available service-backed checks. Record per-job dependencies, executed/skipped counts and raw evidence in docs/jaineel/progress.md. Stop at this checkpoint.
```

**Checkpoint:** CI coverage reflects the merged repository and distinguishes offline checks from real PostgreSQL/Kafka execution.

## Prompt 7 — Freeze a correct baseline, then measure

```text
I am Jaineel. Work only on Prompt 7 in docs/jaineel/implementation_roadmap.md. Read AGENTS.md, docs/specs/01_PROJECT_CONTEXT.md, docs/specs/03_EVALUATION_SPEC.md §§3–4, 6, 8–10, docs/specs/08_DATASET_PROFILE_AND_RULES.md, docs/specs/09_EVALUATION_RUNBOOK.md §§2, 5–7, docs/harsh/experiments.md, docs/harsh/relevance_labels.md, docs/vichitr/team_handoff.md, and docs/jaineel/progress.md.

Stay on the current branch. Edit only my configs, benchmarks, projectctl, report/dashboard and progress paths. Do not invent missing data, locks, owner approvals, providers or metrics. Do not change core matrix behavior to admit session reuse. Do not write a human relevance-label hash until there is a reviewed human-labelled file; label-derived metrics remain diagnostic and clearly attributed.

First verify clean revision, application/infrastructure/schema locks, source and normalized manifests, dictionary/query hashes, complete seed/projection, fixed resource budget and required correctness gates. Resolve the cross-platform hash policy and obtain affected owner review for any contract/matrix change. Run setup and small smoke only after those preconditions pass. Then run the required correctness suite, freeze the B0 inputs, capture and diagnose its real baseline, and run only registered paired comparisons with three repetitions and randomized order. A full matrix is authorized only when the frozen prerequisites pass; otherwise report the exact gate and stop before expensive measurements.

Reconcile every planned offer/result after drain. Retain raw timings, resource samples, manifests, failures and skips. Select C-BEST only from measured supported choices plus reviewed interaction evidence; negative results are valid. Build the report from artifacts, not spreadsheets or Harsh's owner-run sample values. Record exact commands, actual outcomes, evidence references and next handoffs in docs/jaineel/progress.md.
```

**Checkpoint:** a reproducible, independently reconciled B0 and required comparisons exist, or the specific unmet gate remains explicit. Optional session reuse, live model trials and unreviewed relevance quality stay outside certified results until separately approved and measured.

## Starting rule

Current completion and remaining work are recorded in the
[10 November audit](PENDING_WORK_AUDIT_2026_11_10.md). Prompts above are an ordered
historical plan; do not rebuild tasks already implemented or treat a successful
prototype as the completed formal evaluation.

Begin with Prompt 1 only. At the end of each prompt, review the diff, test evidence and progress entry before starting the next. If an implementation exposes a contract conflict, stop that module, quote both requirements in the progress note, and name the owner/consumer review needed. Do not solve the conflict by changing public behavior in passing.
