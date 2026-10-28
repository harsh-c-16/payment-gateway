# Agentic Shopping Assistant with a Distributed, Fault-Tolerant E-Commerce Data Platform

- **Course:** Data Engineering (Semester 5)
- **Team:** Group 3
- **Repository:** [github.com/harsh-c-16/payment-gateway](https://github.com/harsh-c-16/payment-gateway)
- **Specification Version:** 2.0 (24 October 2026)

---

## 1. Project Overview

This project implements an e-commerce platform and agentic shopping assistant with an emphasis on distributed systems engineering, fault tolerance, transaction isolation, and streaming data pipelines. The system is built around the 20,000-observation Flipkart product catalogue, using deterministic normalization, transactional outbox patterns, Kafka event streams, and an analytical lakehouse with Medallion architecture (Bronze/Silver/Gold).

### Team Members & Module Ownership

| Member | Roll Number | Module & Responsibilities | Member Brief |
|---|---|---|---|
| **Jaineel Vora** | B24CM1080 | **M1 / M0**: Assistant workflow, session/cart state, measurement harness, oracle, dashboards, integration | [04_JAINEEL_VORA.md](docs/specs/04_JAINEEL_VORA.md) |
| **Harsh Chaudhari** | B24CM1027 | **M2**: Catalogue ingestion, normalization, retrieval, stock read model, quotes, compaction & queries | [05_HARSH_CHAUDHARI.md](docs/specs/05_HARSH_CHAUDHARI.md) |
| **Aditya Gaurav** | B24CM1003 | **M3**: Orders, Inventory, simulated Payments, durable saga orchestrator, shared outbox library | [06_ADITYA_GAURAV.md](docs/specs/06_ADITYA_GAURAV.md) |
| **Vichitr Arora** | B24CM1067 | **M4**: Kafka streaming infrastructure, Schema Registry, Bronze/Silver/Gold pipelines, manifests, replay | [07_VICHITR_ARORA.md](docs/specs/07_VICHITR_ARORA.md) |

---

## 2. Documentation and Specifications

All authoritative specifications and runbooks are maintained in [`docs/specs/`](docs/specs/):

- [00_README.md](docs/specs/00_README.md) — Navigation and document index.
- [01_PROJECT_CONTEXT.md](docs/specs/01_PROJECT_CONTEXT.md) — Architectural decisions, scope, and frozen technology stack.
- [02_COMMON_SPEC.md](docs/specs/02_COMMON_SPEC.md) — Normative interface contracts, shared DTOs, and error codes.
- [03_EVALUATION_SPEC.md](docs/specs/03_EVALUATION_SPEC.md) — Workload definitions, metric math, and correctness gates.
- [04_JAINEEL_VORA.md](docs/specs/04_JAINEEL_VORA.md) — Jaineel's brief (M1 & M0 tasks J01–J07).
- [05_HARSH_CHAUDHARI.md](docs/specs/05_HARSH_CHAUDHARI.md) — Harsh's brief (M2 tasks H01–H07).
- [06_ADITYA_GAURAV.md](docs/specs/06_ADITYA_GAURAV.md) — Aditya's brief (M3 tasks A01–A07).
- [07_VICHITR_ARORA.md](docs/specs/07_VICHITR_ARORA.md) — Vichitr's brief (M4 tasks V01–V07).
- [08_DATASET_PROFILE_AND_RULES.md](docs/specs/08_DATASET_PROFILE_AND_RULES.md) — Flipkart CSV profile and deterministic normalization rules.
- [09_EVALUATION_RUNBOOK.md](docs/specs/09_EVALUATION_RUNBOOK.md) — CLI surface, operational runbook, and verification commands.
- [10_JAINEEL_CODEX_PLAYBOOK.md](docs/specs/10_JAINEEL_CODEX_PLAYBOOK.md) — Phased implementation playbook for Codex.

### Repository Policies and Governance
- [AGENTS.md](AGENTS.md) — Shared rules of engagement and constraints for coding agents.
- [docs/OWNERSHIP.md](docs/OWNERSHIP.md) — Detailed service boundaries, directory allocations, and write authorities.
- [docs/jaineel/progress.md](docs/jaineel/progress.md) — Jaineel's milestone implementation tracker.

---

## 3. Repository Structure

```
├── .github/workflows/         # CI pipelines (coordinated by Jaineel)
├── analytics/
│   ├── compaction/            # M2: Parquet compaction engine (Harsh)
│   └── queries/               # M2: Analytical DuckDB/SQL queries (Harsh)
├── benchmarks/                # M0: Workload generation and runners (Jaineel)
│   └── manual/                # M0: Manual benchmark scripts and probes (Jaineel)
├── configs/                   # Runtime and evaluation configurations (Shared)
├── contracts/
│   ├── data/catalog/          # M2: Catalog manifest schemas (Harsh)
│   ├── dictionaries/catalog/  # M2: Category/facet dictionaries (Harsh)
│   ├── dictionaries/events/   # M4: Event reason codes/dictionaries (Vichitr)
│   ├── evaluation/            # M0: Evaluation run/summary schemas (Jaineel)
│   ├── events/                # M4: JSON Schema draft-07 event definitions (Vichitr)
│   ├── fixtures/              # Small test fixtures & mock responses (Jaineel)
│   └── http/                  # OpenAPI 3.1 definitions per service domain
├── dashboards/                # M0: Prometheus/Grafana monitoring dashboards (Jaineel)
├── data/
│   └── raw/                   # Untracked raw data (Flipkart sample CSV)
├── docs/
│   ├── decisions/             # Architecture Decision Records (ADRs)
│   ├── jaineel/               # Jaineel's implementation progress and notes
│   ├── specs/                 # Version 2.0 specifications (00–10)
│   └── OWNERSHIP.md           # Authoritative team ownership matrix
├── infra/                     # M4: Docker Compose, Kafka, Schema Registry (Vichitr)
├── migrations/                # Database migrations partitioned by service
│   ├── analytics/             # Vichitr
│   ├── catalog/               # Harsh
│   ├── conversation/          # Jaineel
│   ├── inventory/             # Aditya
│   ├── orders/                # Aditya
│   └── payments/              # Aditya
├── pipelines/
│   ├── catalog/               # M2: CSV import, cleaning, normalization (Harsh)
│   ├── curation/              # M4: Silver stream processing (Vichitr)
│   ├── gold/                  # M4: Gold aggregations and manifests (Vichitr)
│   ├── ingestion/             # M4: Raw Kafka consumer / Bronze landing (Vichitr)
│   ├── replay/                # M4: Topic replay and recovery utilities (Vichitr)
│   └── storage/               # M4: Lakehouse file storage & manifest manager (Vichitr)
├── projectctl/                # M0: Unified team CLI command runner (Jaineel)
├── services/
│   ├── catalog/               # M2: Product catalogue & search service (Harsh)
│   ├── conversation/          # M1: Shopping assistant & cart service (Jaineel)
│   ├── inventory/             # M3: Stock reservation service (Aditya)
│   ├── orders/                # M3: Order management & saga orchestrator (Aditya)
│   └── payments/              # M3: Simulated payments ledger service (Aditya)
├── shared/
│   ├── contracts/             # Shared Pydantic DTOs mapped to contracts
│   ├── event_transport/       # M4: Kafka transport SDK and serializer (Vichitr)
│   ├── local_diagnostics/     # M4: Diagnostic logs and quarantine envelopes (Vichitr)
│   ├── outbox/                # M3: Transactional outbox storage and relay (Aditya)
│   └── telemetry/             # M0: Metrics, logging, and timer helpers (Jaineel)
├── tests/                     # Unit, contract, integration, and oracle test suites
├── .env.example               # Template environment configuration
├── .gitignore                 # Repository ignore rules
├── AGENTS.md                  # Neutral instructions for AI coding assistants
└── README.md                  # This file
```

---

## 4. Getting Started

The P1 Python 3.11 CLI/configuration foundation is implemented. Follow the
[locked install and offline checks](projectctl/README.md). Provider actions remain
unavailable until owner adapters are supplied; they return exit 4 and save evidence.
See [Jaineel's progress](docs/jaineel/progress.md) for the actual checkpoint results.

1. **Environment Setup:**
   Copy the example environment configuration:
   ```bash
   cp .env.example .env
   ```
2. **Review Working Rules:**
   All team members and AI coding assistants must review [AGENTS.md](AGENTS.md) and [docs/OWNERSHIP.md](docs/OWNERSHIP.md).
3. **Branching Model:**
   After the initial repository scaffold is merged to `main`, work proceeds in small feature branches:
   - Jaineel: `jaineel/j01-foundation`, etc.
   - Harsh: `harsh/h01-contracts`, etc.
   - Aditya: `aditya/a01-contracts`, etc.
   - Vichitr: `vichitr/v01-infra`, etc.
