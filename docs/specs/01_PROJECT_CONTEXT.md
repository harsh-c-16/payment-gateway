# Project context for every coding session

Version: 2.0 | Prepared: 24 October 2026 | Team: Group 3

## 1. The project and its actual starting point

**Agentic Shopping Assistant with a Distributed, Fault-Tolerant E-Commerce Data Platform.**

The user explicitly states that implementation has not started. All implementation-complete labels, sprint progress claims, benchmark values and claimed improvements in the supplied tracker and Lab 6–8 report are illustrative or inconsistent. They are not evidence. Do not copy them into results, initialize dashboards with them, or tell an evaluator that they were measured.

The task now is implementation planning. This pack contains specifications, ownership, interfaces and test plans, not application code. The existing tracker is unchanged.

The academic contribution is to build a correct baseline, measure its bottlenecks, test individual pipeline optimizations, and compare them under controlled workloads. The assistant provides a realistic application and workload. Model selection and fine-tuning are not the research contribution.

## 2. What the attachments establish

| Source | Use in this plan | What must not be treated as fact |
|---|---|---|
| Lab1_3(2).pdf, p.1 | Original payment, concurrency, fault tolerance and notification problem | No implementation evidence is supplied |
| Lab2_3(2).pdf, pp.1–5 | Four-layer application scope and motivation | Industry statistics and third-party architectural claims are not project measurements |
| Lab3_3(2).pdf, pp.3–8 | Service-owned state, pgvector, five event domains, Bronze/Silver/Gold, outbox and saga | Logical cross-service relationships are not cross-database foreign keys |
| Lab45_3.docx(2).pdf, pp.1–3 | FR-01–08, NFR-01–07, M1–M4 functions, reservation expiry issue | Old progress percentages and absolute chronology are not coding status |
| Lab678_3(1).pdf, pp.1–3 | Cleaning, lineage, baseline/optimization candidates, test scenario ideas | All reported benchmark numbers and percentage gains are sample values |
| Group_3(1).xlsx, Essence Card Progression!A1:F5 | Authoritative work-division starting point | Completion/status rows elsewhere are disregarded |
| flipkart_com-ecommerce_sample.csv | Actual 20,000-row historical catalogue; full-file profile and deterministic rules in 08_DATASET_PROFILE_AND_RULES.md | No live stock, orders, customers, payment outcomes or reliable complete variant sizes |
| Group_3(1).xlsx, Requirements and Traceability Matrix | Updated freshness wording, measurable targets, T-01–T-12 labels | Acceptance targets are not achieved results |

The corrected tracker wording for FR-04 is retained: asynchronous search can be stale; measure that staleness and revalidate stock at checkout. Do not promise zero stale displays.

## 3. Final primary ownership

| Person | Primary module | Additional evaluation ownership |
|---|---|---|
| Jaineel Vora, B24CM1080 | M1: session, cart, assistant, fixed workflow, tool adapters | M0: load generation, independent oracle, experiment runner, monitoring/dashboard and integrated comparison |
| Harsh Chaudhari, B24CM1027 | M2: CSV ingestion/normalization, catalogue, retrieval, quotes, stock read model; optional vector branch | Index/query plans, ANN recall, filter selectivity, Parquet compaction and analytical query benchmarks |
| Aditya Gaurav, B24CM1003 | M3: Orders, Inventory, simulated Payments, durable saga, shared outbox implementation | Reservation races, duplicate commands, expiry, relay/saga recovery |
| Vichitr Arora, B24CM1067 | M4: Kafka, schema registry, durable ingestion, Silver/Gold, manifests, DLQ and replay | Batching, partition/consumer scaling, freshness and lineage; publication support for Harsh’s file-layout experiments |

One owner implements each component. Consumers implement adapters and tests against its contract, not a second copy of its business rules. Jaineel owns the final benchmark narrative; each module owner supplies evidence and helps review that narrative.

The user authorized small workload adjustments. Compared with the tracker, the dashboard moves from Vichitr to Jaineel, and compaction/query-scan experimentation moves from Vichitr to Harsh. Vichitr retains the manifest publication and recovery logic. Aditya retains the transaction boundary. These transfers reduce concentration of work in M4 without splitting a critical consistency mechanism across owners. The allocation aims for comparable implementation and testing effort, not a claim of identical hours. Each member must deliver code, contract tests and one measured engineering comparison.

## 4. Scope ladder

**Required for the evaluated release**

- Reproducible local environment and versioned, executable contracts.
- The supplied Flipkart catalogue, versioned deterministic normalization, checksums and independent expected outputs; separately labelled simulated inventory and traffic.
- Catalogue search, a minimal session/cart workflow, durable asynchronous checkout and simulated payments.
- Inventory reservation/expiry, idempotency, outbox, recovery and compensation.
- Five domain topics, schema registry, raw archive, durable deduplication, typed analytical outputs and queryable Gold.
- Individual optimization comparisons and a combined configuration selected from measured evidence.
- Correctness, overload, skew, recovery, late-data, replay and integration tests.
- A zero-generative-call deterministic assistant; optional one-call intent fallback only after engineering gates pass. Assistant quality remains secondary.

**Explicitly outside v1**

Real bank/payment integration, customer authentication, shipping/tax/discount engines, returns after a confirmed sale, multi-currency conversion, Kubernetes, multi-region deployment, model training, autonomous purchases, and a full retail UI.

Use synthetic user IDs and simulated money. The default deterministic assistant works without any paid model. A live model can implement the same adapter later; missing model credentials cannot block the pipeline benchmark.

## 5. Decisions and why

These are **design decisions for this implementation**, not descriptions of code that already exists.

| ID | Decision | Alternative considered | Reason and evidence to collect |
|---|---|---|---|
| D01 | One Python 3.11 monorepo; FastAPI HTTP services | Go backend plus Python analytics | Shared contracts reduce four-person integration risk. This is not a claim that Python is faster. Measure CPU and service throughput. |
| D02 | PostgreSQL 18 with separate databases and credentials per owner/service; one server in the local profile | Shared tables or multiple physical servers immediately | Preserve ownership while fitting a student machine. Shared server resources remain a measured limitation. |
| D03 | pgvector 0.8.1; exact search baseline; HNSW evaluated separately | Dedicated vector database or ANN from day one | Avoid another synchronization boundary and retain an exact quality reference. [R3] |
| D04 | Kafka KRaft with one broker for the required local profile | Managed broker, or a replicated cluster initially | Repeatable cost-free local trials. Single broker proves process recovery with retained volume, not broker/disk-loss durability. [R1] |
| D05 | Durable orchestrated saga in Orders, using HTTP participant commands | Event choreography or distributed 2PC | One inspectable state machine and explicit timeout recovery. HTTP calls run in a background worker, not in the client request. [R5] |
| D06 | State and event outbox written in one local transaction; at-least-once relay | Independent database/Kafka writes | Avoid the dual-write gap. Kafka producer idempotence does not replace consumer deduplication. [R1, R4] |
| D07 | Stock mutations serialized in Inventory; search uses versioned absolute stock snapshots | Redis lock, or authoritative stock inferred from analytics | Database checks protect the last unit. Search freshness and checkout correctness are separate properties. |
| D08 | JSON transport with registered schemas; Parquet analytical files | XML, Avro/Protobuf immediately | Inspectable small prototype; typed columnar files for analytical queries. Encoding changes would be separate experiments. |
| D09 | Analytical PostgreSQL staging/ledgers plus immutable files and an atomic manifest pointer | Append-only Parquet alone; full Iceberg/Delta/Spark stack | Durable unique keys and publication recovery are explicit. This is a medallion analytical prototype, not a claim of a full ACID lakehouse table format. |
| D10 | Durable local-volume file store in the required baseline; object-store adapter deferred | MinIO/S3 required at the start | Keeps the first benchmark reproducible without extra deployment dependencies. Preserves Bronze/Silver/Gold and Parquet. Object-storage/network latency is not evaluated in this profile. |
| D11 | Real Schema Registry plus repository schemas and compatibility tests | Repository schemas mislabeled as a registry | Satisfies the tracker’s registry requirement. JSON Schema compatibility must actually be tested. [R7] |
| D12 | No Redis query cache in the core experiments | Add caching before measuring | Prevent a second invalidation problem from hiding index effects. A cache is a later isolated experiment only. |
| D13 | Baseline already has outbox, validation, required indexes and deduplication | Intentionally unsafe or broken baseline | Optimization must preserve the same correctness guarantees. |
| D14 | Pipeline, retrieval, transaction and integrated workloads reported separately | One headline number for all effects | A search index has no necessary causal effect on a streaming-only benchmark. |
| D15 | Provisional Gold published frequently; late events revise it | Wait two minutes before every Gold publication | Separates low visibility latency from event-time completeness. |
| D16 | Zero generative LLM calls by default; at most one optional structured intent call per turn; template responses | Multi-step planner, LLM cleaning or LLM response generation | Minimizes latency and variability; measure call counts and stage latency. No model selection workstream. |
| D17 | Lexical/filter search as the default operational path; fixed-model hybrid retrieval evaluated separately | Neural inference on every request | Keeps core pipeline experiments model-independent; any quality/latency trade-off is measured, not assumed. |
| D18 | Latest crawl per pid; preserve all source observations; inactive rows for missing price | Deduplicate names, drop all incomplete rows, impute prices | 20,000 observations become 19,998 listings, with 19,920 priced candidates. Preserves useful data and honest source limitations. |
| D19 | Safe deterministic nested-field parser and nullable conservative facets | Per-row LLM extraction or fake universal size variants | Source attributes are sparse; only 4 clothing listings yield a usable explicit apparel size under the frozen rule. Missing values cannot satisfy hard filters. |
| D20 | Batch catalogue import measured separately from streaming ingestion | Put the static CSV through the operational Kafka event path | Separates offline load cost from event-processing latency; clear owners and comparable experiments. |

D09–D11 and the price-quote contract are implementation clarifications/additions to the labs. D10 is a deliberate change from the proposed object-store deployment, not an unnoticed omission. If the course later explicitly requires S3-compatible storage, replace only the file-store adapter, rerun publication/crash tests, and label that profile separately. Do not silently mix its results with local-disk results.

## 6. Technology freeze

The chosen families are Python 3.11, FastAPI/Pydantic 2, psycopg 3, PostgreSQL 18, pgvector 0.8.1, Apache Kafka 4.1.x in KRaft mode, confluent-kafka, JSON Schema validation, Confluent Schema Registry, PyArrow, DuckDB, Prometheus and Grafana. Use Docker Compose.

Optional vector branch: sentence-transformers/all-MiniLM-L6-v2, 384 dimensions, normalized vectors and cosine distance. Freeze one model; build catalogue vectors offline. The real Flipkart catalogue and human-reviewed English queries replace the earlier synthetic catalogue. Mixed Hindi/English quality is outside the reported scope. Local embedding inference is measured separately from generative LLM calls. [R9]

Exact package patches, image digests, schema registry image compatibility, model revision and hardware are **Gate G0 outputs**, not invented here. Vichitr produces the infrastructure lock, Jaineel the application dependency lock, Harsh the model lock, and Aditya verifies database/migration compatibility. After the smoke test, all experiments use those exact locks. No floating latest tags in an evaluated run.

## 7. How to feed these files to a coding LLM

Start every new coding session with this file, 02_COMMON_SPEC.md, the relevant portions of 03_EVALUATION_SPEC.md and 09_EVALUATION_RUNBOOK.md, and that person’s work file. Catalogue consumers additionally receive 08_DATASET_PROFILE_AND_RULES.md. Use the frozen contracts rather than repeated LLM design discussions. Implement and evaluate one milestone per coding session; existing test artifacts are the handoff.

Tell the model:

> Implement only the currently assigned milestone in my work file. Treat the common specification as the interface authority. Identify imported contracts, required stubs, state transitions and tests before editing. Do not invent another person’s API, bypass their database ownership, change a public name, remove correctness checks to improve timing, or fill any result with a sample number. If a contract conflicts, state the exact conflict and propose a versioned change. Report files changed, checks actually run, remaining limitations and the next handoff.

There is no application code in this planning pack. Function signatures in the specification describe interfaces only. During coding, create real OpenAPI/JSON Schema files and contract tests before implementing business logic.

## 8. Dataset and delivery priorities

Harsh owns the raw CSV import, deterministic normalization, source observations, canonical catalogue and active-SKU manifest. Vichitr owns operational Kafka ingestion and event-to-Silver/Gold transformations; he provides the shared file store but does not duplicate Harsh's CSV parser. Aditya consumes the SKU manifest and generates simulated stock/payment state. Jaineel generates workloads and independent expected outputs, implements the evaluation runner, and verifies the handoffs.

For this exact file, the profile reports 20,000 observations, 19,998 latest-pid listings, 78 inactive missing-price listings and 19,920 priced candidates. These are actual data observations. They are not throughput, latency or implementation-completion evidence. CSV crawl dates are 2015–2016; fresh simulator events use current operation time.

Implement the DE path first: contracts → profile/import/reconciliation → event-to-Gold baseline → transaction correctness → instrumentation → batching/index/scaling/file-layout experiments → stress/replay evidence. The optional intent fallback, hybrid/ANN comparison and UI polish come after those gates. Do not spend time generating product attributes, training models or comparing model providers.

The original six intent slots remain supported, but size/colour/material are optional and require evidence. Broad catalogue support replaces the fictional three-category uniform dataset. A strict size query can legitimately return nothing; claiming broad size-aware coverage would require a verified supplementary variant source. Record this limitation in the final evaluation rather than filling gaps with synthetic attributes presented as real.

## 9. Evidence and reference policy

A completed feature needs actual code plus test evidence. A performance result needs a run manifest, raw timings/counters, correctness output and configuration. Missing evidence means NOT RUN or INCOMPLETE, not zero and not pass.

The following primary sources were checked while preparing this design. They support technical constraints; they do not establish performance on this team’s machine.

- **R1 — Apache Kafka 4.1 design:** partition ordering and delivery semantics. https://kafka.apache.org/41/design/design/
- **R2 — PostgreSQL 18 locking:** row-level concurrency and lock behavior. https://www.postgresql.org/docs/18/explicit-locking.html
- **R3 — pgvector maintainers:** exact/approximate search, filtering, HNSW and iterative scans. https://github.com/pgvector/pgvector
- **R4 — AWS transactional outbox:** atomic local writes, relay duplicates and idempotent consumers. https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html
- **R5 — AWS saga orchestration:** coordination, compensation, isolation limits and recovery concerns. https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/saga-orchestration.html
- **R6 — PostgreSQL 18 multicolumn indexes:** equality/range predicates and index-column ordering. https://www.postgresql.org/docs/18/indexes-multicolumn.html
- **R7 — Confluent schema evolution:** transitive compatibility and JSON Schema content-model considerations. https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html
- **R8 — DuckDB Parquet documentation:** column/filter pushdown and partitioned data access. https://duckdb.org/docs/lts/data/parquet/overview
- **R9 — Sentence Transformers model card:** all-MiniLM-L6-v2 representation and dimensions. https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2
- **R10 — Prometheus histograms:** distribution and quantile measurement. https://prometheus.io/docs/practices/histograms/
- **R11 — W3C PROV overview:** entities, activities and agents for provenance. https://www.w3.org/TR/prov-overview/
- **R12 — PostgreSQL SELECT:** SKIP LOCKED is appropriate for queue-like work, not a general consistent read. https://www.postgresql.org/docs/18/sql-select.html

Source-specific design rationale is brief; the detailed protocols and parameter choices in the remaining files are this project’s own implementation specification. Do not reproduce the labs’ unverified industry numbers as supporting evidence.

