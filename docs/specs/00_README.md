# Group 3 coding pack

Version 2.0 | Updated for the actual Flipkart CSV and minimal model calls.

**Start with this file.** This pack defines the project before coding: one common specification, one evaluation specification, one project-context file and one work file for each teammate.

The starting state is **no implementation completed**. Lab 6–8 metrics and tracker progress claims are not used as measured evidence. Function signatures here are contracts, not application code.

## Final division of work

| Person | Main coding responsibility | Engineering/evaluation responsibility | Personal file |
|---|---|---|---|
| Jaineel Vora | Assistant, session/cart, fixed workflow and client adapters | Load generator, independent oracle, integration, monitoring/dashboard and controlled comparisons | [04_JAINEEL_VORA.md](04_JAINEEL_VORA.md) |
| Harsh Chaudhari | **CSV ingestion, normalization**, catalogue, quotes, retrieval and stock projection | Import row-vs-COPY, indexing, Parquet compaction/query benchmarks; secondary ANN | [05_HARSH_CHAUDHARI.md](05_HARSH_CHAUDHARI.md) |
| Aditya Gaurav | Simulated inventory seeding, Orders, Inventory, Payments, saga and shared outbox | Concurrency, expiry, duplicate-command and crash-recovery tests | [06_ADITYA_GAURAV.md](06_ADITYA_GAURAV.md) |
| Vichitr Arora | Kafka/schema registry, **event ingestion and analytical cleaning**, Silver/Gold, manifests, DLQ and replay | Batching, consumer scaling, freshness, late-data and replay correctness | [07_VICHITR_ARORA.md](07_VICHITR_ARORA.md) |

The two workload adjustments are **dashboard → Jaineel** and **compaction/query experiments → Harsh**. They preserve the tracker’s main module ownership while reducing the amount concentrated on Vichitr. Critical state/transaction/publication mechanisms each retain one owner.

## Reading and implementation order

1. [01_PROJECT_CONTEXT.md](01_PROJECT_CONTEXT.md): scope, assumptions, source interpretation, design rationale and references.
2. [02_COMMON_SPEC.md](02_COMMON_SPEC.md): authoritative APIs, types, functions, event schemas, state machines, ownership and integration gates.
3. [03_EVALUATION_SPEC.md](03_EVALUATION_SPEC.md): workloads, baseline/variants, metric formulas, stress/fault tests and evidence artifacts.
4. [08_DATASET_PROFILE_AND_RULES.md](08_DATASET_PROFILE_AND_RULES.md): actual full-file findings, column mapping, deterministic normalization, counts and catalogue handoffs.
5. [09_EVALUATION_RUNBOOK.md](09_EVALUATION_RUNBOOK.md): exact CLI/config/fixtures/tests/artifacts to implement and commands to run.
6. Your personal file: coding sequence, provider/consumer black boxes, owned evals and coding-LLM starter prompt.

Every coding LLM receives the context + common spec + relevant evaluation/runbook sections + dataset rules + that person’s file. Do not give it only the personal file and let it invent the missing interfaces.

## Dataset verdict and ownership

Use the supplied dataset, with the deterministic preparation in file 08. Actual analysis found 20,000 source rows, 19,998 latest-pid listings and 19,920 priced candidates. Retain 78 missing-price listings inactive. Specifications use Ruby-style syntax, categories/attributes are incomplete, and only four listings have usable explicit apparel sizes under the conservative rule. This is a historical 2015–2016 catalogue, not live inventory or transaction history.

Harsh owns source ingestion/normalization/deduplication and gives everyone a hashed catalogue/SKU/facet manifest. Aditya generates explicitly simulated inventory/payment state from the active SKU set. Vichitr owns Kafka ingestion and event-to-Silver/Gold normalization. Jaineel owns workload generation, independent evaluation, CLI/report orchestration and the assistant. No teammate implements another's cleaner.

Default runtime: deterministic parsing, lexical/filter search and template responses, with zero generative LLM calls. Optional assist mode permits at most one intent fallback; no model calls in data preparation, checkout, analytics or metric calculation. Optional embeddings are local/offline for products and measured separately for queries.

## First work to do together

At G0, each owner creates executable API/event schemas, valid/invalid fixtures and a small stub provider. Vichitr prepares the shared environment and registry; Aditya publishes the outbox interface; Harsh publishes catalogue/quote stubs and SKU manifests; Jaineel wires the contract runner and independent fixtures.

Then build one event-to-Gold slice and independent catalogue/transaction components in parallel. Integrate search → cart → quote → checkout → stock projection → Gold early. Only after correctness passes should the team optimize and report numbers.

## Navigation inside the common spec

- §§1–3: ownership, repository/runtime conventions and error/idempotency rules.
- §§4–7: types, exact HTTP endpoints, provider functions and event contracts.
- §§8–10: database invariants, saga/expiry/compensation and retrieval.
- §§11–13: durable ingestion, active-manifest Gold, replay and compaction.
- §§14–16: instrumentation, integration gates and completion conditions.
- Appendix A: auxiliary DTOs and additional runtime limits.
- Appendix B: concrete synthetic acceptance vectors with expected stock, payment and deduplication outcomes.

## Decisions to notice before coding

- The experiment compares a **correct** baseline with optimized variants.
- Search index changes are measured in retrieval/integrated workloads; streaming-only results have their own tests.
- Primary pipeline latency ends at queryable active-manifest Gold Parquet, not merely at a committed Kafka offset.
- The initial profile uses a durable local file volume for repeatability. Object-storage latency is not part of that profile.
- Payments are simulated; a single-broker profile does not prove replicated broker durability.
- The current stack families are chosen, but actual package patches, image digests, hardware limits and model revision are verified and frozen at G0.

These are explicit design choices with reasons in the context file. Targets such as 500 events/s, p95 <=1 second and search p95 <200 ms are targets to test.

## What this pack delivers

Ten Markdown files, including this index. The ZIP contains the same files for sharing. File 08 contains actual measured CSV profile observations; performance results remain NOT_RUN. Commands/signatures are specifications for later implementation, not existing application code. The original CSV and tracker are unchanged.

