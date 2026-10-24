# Team Ownership and Service Boundaries

Version 1.0 — 24 October 2026 | Team: Group 3

This document is the authoritative record of component ownership, directory responsibility, and service boundaries for the Group 3 Data Engineering project: **Agentic Shopping Assistant with a Distributed, Fault-Tolerant E-Commerce Data Platform**.

Refer to [01_PROJECT_CONTEXT.md](../docs/specs/01_PROJECT_CONTEXT.md) and [02_COMMON_SPEC.md](../docs/specs/02_COMMON_SPEC.md) for full context and interface contracts.

---

## 1. Primary Module Ownership

| Member | Roll Number | Primary Module | Evaluation Ownership | Brief Link |
|---|---|---|---|---|
| **Jaineel Vora** | B24CM1080 | **M1**: Session, Cart, Assistant, Fixed Workflow, Tool Adapters | **M0**: Load generation, independent oracle, experiment runner, monitoring/dashboard, and integrated comparison | [04_JAINEEL_VORA.md](../docs/specs/04_JAINEEL_VORA.md) |
| **Harsh Chaudhari** | B24CM1027 | **M2**: CSV ingestion & normalization, catalogue, authoritative prices, retrieval, quotes, stock read model; optional vector branch | Index/query plans, ANN recall, filter selectivity, Parquet compaction, and analytical query benchmarks | [05_HARSH_CHAUDHARI.md](../docs/specs/05_HARSH_CHAUDHARI.md) |
| **Aditya Gaurav** | B24CM1003 | **M3**: Orders, Inventory, simulated Payments, durable saga orchestrator, shared outbox implementation | Reservation races, duplicate commands, expiry, relay and saga recovery | [06_ADITYA_GAURAV.md](../docs/specs/06_ADITYA_GAURAV.md) |
| **Vichitr Arora** | B24CM1067 | **M4**: Kafka, schema registry, durable streaming ingestion, Silver/Gold, active manifests, DLQ, replay | Batching, partition/consumer scaling, freshness, lineage; publication support for Harsh's file-layout experiments | [07_VICHITR_ARORA.md](../docs/specs/07_VICHITR_ARORA.md) |

---

## 2. Service and Database Boundaries

| Boundary | Owner | Consumers | Sole Write Authority |
|---|---|---|---|
| Conversation, sessions, cart, workflow | Jaineel | Demo client, benchmark runner | `conversation_db` |
| CSV ingestion, normalization, catalogue, authoritative price, quotes, retrieval | Harsh | M1, Orders | `catalog_db` |
| Stock read model used by search | Harsh | Retrieval | `catalog_db` (fed by Inventory events) |
| Orders and saga orchestrator | Aditya | M1, benchmark runner | `orders_db` |
| Inventory and reservations | Aditya | Saga | `inventory_db` |
| Simulated payment attempts and ledger | Aditya | Saga | `payments_db` |
| Generic outbox storage/relay library | Aditya | M1, M2, M3, M4 quarantine notification | Only caller's local database |
| Event builder, schema validation, Kafka transport SDK | Vichitr | All producers and relays | Kafka transport only |
| Bronze, Silver, Gold staging, DLQ, manifest publication, replay | Vichitr | Analytics API, compactor, benchmarks | `analytics_db` and dataset file store |
| Snapshot compaction and DuckDB scan benchmark | Harsh | M4 publication adapter, benchmark runner | New candidate files only |
| Load generator, independent oracle, monitoring, dashboard, CI/integration harness | Jaineel | Whole team | Benchmark artifacts (no business writes except APIs) |

> [!IMPORTANT]
> **Database Isolation:** No operational service reads or writes another service's tables. Cross-service relationships use public IDs over HTTP APIs or Kafka events. Foreign keys exist only within an owning database.

---

## 3. Directory Responsibility

| Owner | Assigned Directories | Description |
|---|---|---|
| **Jaineel** (Application) | `services/conversation/`, `migrations/conversation/` | M1 Conversation service, session/cart state, migrations |
| **Jaineel** (Measurement & Harness) | `projectctl/`, `benchmarks/`, `benchmarks/manual/`, `dashboards/`, `shared/telemetry/`, `tests/oracles/`, `tests/integration/` | Unified CLI runner, workload generator, oracle, dashboard, integration tests |
| **Jaineel** (Personal Tests) | `tests/conversation/`, `tests/projectctl/`, `tests/benchmarks/`, `tests/telemetry/`, `tests/contracts/` | Test suites for M1 and harness components |
| **Jaineel** (Coordinated Fixtures) | `contracts/fixtures/`, `contracts/fixtures/catalog/`, `contracts/evaluation/` | Offline fixtures, expected oracle targets, evaluation schemas |
| **Harsh** | `pipelines/catalog/`, `services/catalog/`, `analytics/compaction/`, `analytics/queries/`, `migrations/catalog/`, `tests/catalog/`, `tests/analytics/` | M2 Catalogue pipeline, search service, compaction, analytical queries, tests |
| **Harsh** (Contracts) | `contracts/data/catalog/`, `contracts/dictionaries/catalog/` | Frozen source/category/facet dictionaries and catalog manifests |
| **Aditya** | `services/orders/`, `services/inventory/`, `services/payments/`, `shared/outbox/`, `migrations/orders/`, `migrations/inventory/`, `migrations/payments/`, `tests/transactions/` | M3 Transaction services, shared outbox library, saga engine, migrations, tests |
| **Vichitr** | `pipelines/ingestion/`, `pipelines/curation/`, `pipelines/gold/`, `pipelines/replay/`, `pipelines/storage/`, `shared/event_transport/`, `shared/local_diagnostics/`, `infra/`, `migrations/analytics/`, `tests/pipelines/` | M4 Data pipelines, event transport SDK, Docker Compose/Kafka infra, lakehouse manifests, tests |
| **Vichitr** (Contracts) | `contracts/events/`, `contracts/dictionaries/events/` | JSON Schemas for 5 event topics, event code dictionaries |
| **Split by Owner** | `contracts/http/`, `shared/contracts/`, `configs/` | OpenAPI specs, typed DTOs, service/evaluation configs |
| **Coordinated Documentation & Plumbing** | `docs/specs/`, `docs/jaineel/`, `docs/decisions/`, `.github/workflows/`, `data/raw/` | Specifications, ADRs, CI workflows, local raw dataset staging |

---

## 4. Shared Files and Maintainers After Scaffold

| Shared File or Area | Maintainer After Scaffold | Notes |
|---|---|---|
| `contracts/http/conversation.yaml` | Jaineel | Conversation & Cart OpenAPI contract |
| `contracts/http/catalog.yaml` | Harsh | Search, product, quotes OpenAPI contract |
| `contracts/http/transactions.yaml` | Aditya | Orders, inventory, payments OpenAPI contract |
| `contracts/http/analytics.yaml` | Vichitr | Manifest, Gold, DLQ/replay inspection OpenAPI contract |
| `shared/contracts/conversation.py` | Jaineel | Typed DTOs for M1 |
| `shared/contracts/catalog.py` | Harsh | Typed DTOs for M2 |
| `shared/contracts/transactions.py` | Aditya | Typed DTOs for M3 |
| `shared/contracts/events.py`, `analytics.py` | Vichitr | Typed event envelopes & analytics DTOs |
| `shared/contracts/common.py` | Neutral DTO file | Jaineel coordinates initial extraction; all affected owners review |
| `contracts/events/`, `contracts/dictionaries/events/` | Vichitr | Payload producers review |
| `contracts/fixtures/` | Jaineel coordinates | Providers review expectations |
| `configs/evaluation.yaml`, `configs/core_matrix.yaml` | Jaineel | Experiment configurations |
| Other component/infra configs, Compose | Relevant Owner / Vichitr | Vichitr maintains infrastructure configs |
| `pyproject.toml`, application lock, CI, root `README.md`, `.gitignore`, `.env.example` | Jaineel coordinates | Single team dependency lock and shared tooling |
| `docs/specs/00`–`10` | Canonical specifications | Changes require affected-owner review |

---

## 5. Working Rules and Invariants

1. **Scaffold Exception Over:** Creating teammates' empty directories is a one-time setup action. No developer may implement business logic, migrations, or schemas owned by another teammate.
2. **Read Universally, Write Locally:** Developers may read any project file. Changes must only be committed to the developer's owned paths.
3. **Explicit Test Doubles:** When a dependency or service is not yet available, write an explicit test double within your own test directory. Never commit stubs masquerading as real services, and never claim a real integration pass based on a stub.
4. **Contract Changes Require Consumer Review:** Public API and event contracts cannot be unilaterally altered to fix local test failures.
5. **Preserve Truth in Evidence:** Incomplete, skipped, or unmeasured benchmarks must be explicitly marked as `null` or `NOT_RUN`, never fabricated or populated with old sample numbers.
