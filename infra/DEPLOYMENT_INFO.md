# Presentation deployment

The single file for starting, checking, demonstrating and stopping the prototype. It was
rehearsed end to end on 12 November 2026 on the Linux laptop below; the results are in
[Rehearsal](#rehearsal-12-november-2026). The launcher itself is described in
[PROTOTYPE.md](PROTOTYPE.md) (Windows/PowerShell commands) and the client in
[PROTOTYPE_DEMO.md](../docs/jaineel/PROTOTYPE_DEMO.md).

## Identity

| Item | Value |
|---|---|
| Code | branch `harsh` on top of `main` `348ec34`; the commit that adds this file. `CODE_COMMIT` in `artifacts/infra/prototype-local/context.json` records the HEAD the stack was started from |
| Namespace | `dev` (retained; the launcher refuses a different one) |
| Prototype run ID | `a9f8a0b8-d69f-484c-954b-6bda58e9e171` (first `env up`, retained) |
| Dataset revision | `flipkart-v1-3a401f32ca99379f8298ce42` (see [DATA_SHEET.md](../docs/harsh/DATA_SHEET.md)) |
| Catalogue | 19,998 listings, 19,920 active, imported with `--load-mode copy`, business digest `d87f57e6…2bba` |
| Stock | 19,920 SKUs × 10,000 units (`inventory seed --profile performance --seed 42`), initial stock digest `79233ffa…b070` |
| Modes | `ASSISTANT_MODE=fixed` (zero LLM calls), `BENCHMARK_MODE=false`, `FAULT_INJECTION_ENABLED=false` |

## Images

| Container | Image |
|---|---|
| postgres | `pgvector/pgvector:0.8.1-pg18-trixie@sha256:2fd905ba95f99a51be207d0ff0b8d5b8538cbce7e9083b3ccfa65b93bb28b938` |
| kafka | `apache/kafka:4.1.2@sha256:5cc2a2fd93fa2687b44015eee04fb2c3edd9e526bd64bf8bec5ff1e268772e0e` |
| schema-registry | `confluentinc/cp-schema-registry:8.1.0@sha256:385c157f9cef42aa65e5c95050d85a439bcb0c897826aeabb3e10d36127ea223` |
| 9 application containers | `group3-m04-storage:local`, built by `env up` from `infra/storage.Dockerfile` on `python:3.11.15-slim-bookworm@sha256:d29f48a3…e2e0c3` with `uv sync --locked` (uv 0.10.8). Application source is mounted read-only from the checkout |

The pins are also in [images.lock.json](images.lock.json).

## Addresses

Everything binds to `127.0.0.1` only.

| Service | Port | Used by the demo |
|---|---:|---|
| Conversation (M1) | 8001 | yes, the client talks to it |
| Catalogue (M2) | 8002 | via M1 |
| Orders (M3) | 8003 | yes, the client polls order status |
| Inventory (M3) | 8004 | internal |
| Payments (M3) | 8005 | internal |
| Analytics / Gold (M4) | 8006 | Gold read below |
| PostgreSQL | 5432 | six databases, one per owner |
| Kafka | 9092 | single broker, 1 partition per topic |
| Schema registry | 8081 | |

Workers without ports: `catalog-worker` (stock projection), `analytics-worker` (Silver/Gold),
`prototype-relays` (five outbox relays).

## Resource limits (verified by `env verify` on 12 November)

| Container | RAM | CPU |
|---|---:|---:|
| postgres | 512 MiB | 0.5 |
| kafka | 1,024 MiB | 0.75 |
| schema-registry | 640 MiB | 0.5 |
| conversation | 128 MiB | 1.0 |
| catalog | 128 MiB | 1.0 |
| catalog-worker | 128 MiB | 0.75 |
| orders, inventory, payments | 128 MiB each | 0.5 each |
| analytics | 192 MiB | 0.5 |
| analytics-worker | 320 MiB | 1.0 |
| prototype-relays | 128 MiB | 0.5 |
| **Total** | **3,584 MiB** (+256 MiB headroom checked) | **8.0** |

Host for the rehearsal: AMD Ryzen 7 7840HS (16 threads), 15.4 GB RAM, NVMe SSD, Ubuntu 26.04.1,
Docker Engine 29.1.3, Compose 2.40.3. These are low-traffic development limits, not a capacity claim.

## Private configuration (never commit or share)

All under `artifacts/` (git-ignored). Names only; never print the values.

| File | Holds |
|---|---|
| `artifacts/infra/postgres-local/secrets/*_password` | PostgreSQL admin and per-owner passwords |
| `artifacts/infra/postgres-local/.env` | `<OWNER>_DATABASE_URL` for host commands |
| `artifacts/infra/prototype-local/internal_token` | `INTERNAL_API_TOKEN` for `/internal/v1` routes |
| `artifacts/infra/prototype-local/.env` | Host bindings: `CONVERSATION_/CATALOG_/ORDERS_/INVENTORY_/PAYMENTS_/ANALYTICS_DATABASE_URL`, `INTERNAL_API_TOKEN`, `RUN_NAMESPACE`, `RUN_ID`, `CODE_COMMIT`, `CATALOG_DATASET_REVISION`, `KAFKA_BOOTSTRAP_SERVERS`, `EVENT_SCHEMA_CACHE_PATH`, `POSTGRES_SECRETS_DIR` |
| `artifacts/infra/prototype-local/.container.env` | The same names with in-network hosts, for the containers |
| `artifacts/infra/prototype-local/context.json` | Public run identity (namespace, run ID, commit, revision) |

Docker volumes hold the data and must be kept: `group3-postgres-local_postgres_data`,
`group3-postgres-local_kafka_data`, `group3-postgres-local_lakehouse_data`.

## Commands (Linux)

Run from the repository root. If `docker` says permission denied, log out and back in once
(the `docker` group was added on 12 November); until then prefix Docker-using commands with
`sg docker -c "…"`.

### Start (data already prepared; no import, no seed, no reset)

```bash
cd ~/Dev/payment-gateway
sudo systemctl start docker                        # only if Docker is not running
PROJECTCTL_ADAPTER_MODULE=infra.postgres .venv/bin/python -m projectctl env up --profile postgres-local
set -a; . artifacts/infra/prototype-local/.env; set +a
.venv/bin/python -m services.orders.m3_setup         # repeatable; applies nothing when current
PROJECTCTL_ADAPTER_MODULE=infra.prototype .venv/bin/python -m projectctl env up --profile prototype-local
```

### Verify

```bash
PROJECTCTL_ADAPTER_MODULE=infra.prototype .venv/bin/python -m projectctl env verify --profile prototype-local
PROJECTCTL_ADAPTER_MODULE=infra.prototype .venv/bin/python -m projectctl projection wait \
  --namespace dev --sku-manifest artifacts/prototype-setup/prototype-data/sku_manifest.json --timeout-seconds 600
```

Both must print `"exit_code":0`. `env verify` checks all 12 containers are healthy with the
limits above; `projection wait` checks all 19,920 SKUs are in the search read model. Healthy
containers alone do not prove the demo works, so run one search before presenting.

### Demo

```bash
.venv/bin/python -m projectctl demo --namespace dev --user-id demo-professor --query "men's formal shirt"
```

Pick a product number, a quantity, review the quote, then type exactly `CONFIRM <quote-id>`.
The order goes `PENDING` → `RESERVING` → `PAYMENT_PENDING` → `CONFIRMED` (or `CANCELLED` on the
simulated 5% decline, which is also a correct outcome). Then:

```bash
# resume: shows the same order, no new purchase
.venv/bin/python -m projectctl demo --resume artifacts/demo/<printed-id>/state.json
# a second session where you press Enter at the CONFIRM prompt: no checkout is sent
.venv/bin/python -m projectctl demo --namespace dev --user-id demo-decline --query "watches under 1000 rupees"
# the order in active Gold (today, UTC)
curl -s "http://127.0.0.1:8006/v1/analytics/gold/order_fact?namespace=dev&date_from=$(date -u +%F)&date_to=$(date -u -d tomorrow +%F)"
```

The three demo searches and their expected behaviour are in
[DEMO_SEARCHES.md](../docs/harsh/DEMO_SEARCHES.md).

### Stop (keeps all data)

```bash
PROJECTCTL_ADAPTER_MODULE=infra.prototype .venv/bin/python -m projectctl env down
```

This stops the nine application containers, then PostgreSQL, Kafka and the registry. Volumes,
topics, offsets and secrets stay. Never run `docker compose down -v` or `docker volume rm`.

## Evidence

| Folder (git-ignored) | Contents |
|---|---|
| `artifacts/rehearsal-20261112/` | This rehearsal: setup logs, `env up`/`verify`/`projection wait` results, both demo transcripts and state files with raw HTTP logs, the order evidence JSON, SKU-set check |
| `artifacts/infra/prototype-local/checks/<run-id>/` | Launcher startup checks and `prototype.json` (containers, limits, context) |
| `artifacts/prototype-setup/projectctl/` | Import, verify and seed CLI evidence |
| `artifacts/import-comparison-20261112/` | I0/I1 import timings |
| `artifacts/transaction-cases-20261112/` | Success and decline transaction cases |

## Rehearsal, 12 November 2026

On the laptop above, from an empty Docker install. This machine had no earlier deployment, so the
one-time setup ran once: owner migrations, `env up`, catalogue import (`--load-mode copy`), verify
(19 assertions), inventory seed (19,920 seeded, 0 skipped) and `projection wait`. The first
`projection wait` stopped at its 600-second deadline with 7,168 of 19,920 projected; the second
reported ready (19,920, 0 deferred). The client was driven by a script that answers its prompts, so
the confirmation below is a scripted test input, not a human review. Runtime code was `348ec34`; the
only uncommitted edits were documentation, the transaction contract (M1 loads it at runtime, so the
edited contract validated the real Orders responses) and a test.

**Data.** Active catalogue, Inventory and stock projection hold the same 19,920 SKUs (identical
sorted lists, SHA-256 `14d60b0d…6c26c2`); Inventory outbox 0 unpublished.

**Purchase (session A, user `demo-rehearsal`).**

| Step | Result |
|---|---|
| Search `men's formal shirt` | 5 real shirts (see [DEMO_SEARCHES.md](../docs/harsh/DEMO_SEARCHES.md)); 1.5 s turn, 0 LLM calls |
| Select product 2, quantity 2 | Cart version 1: `FK-SHTEJR4G5K3TAMCM` × 2 |
| Quote | `64eb7c00-1a6d-4200-b0e5-1ee3b744327c`: INR 1,259.00 each, total INR 2,518.00, expires 12:55:16 UTC |
| `CONFIRM 64eb7c00-…` | Order `5d19b678-a81d-4780-bff6-18668795fcdb` accepted `PENDING` |
| Terminal state | `PENDING` → `RESERVING` → `PAYMENT_PENDING` → `CONFIRMED` (version 6), about 2.2 s after creation |
| Reservation | `a72d97d2-c316-483d-b144-dc987f5c9aa9` `COMMITTED`, `FK-SHTEJR4G5K3TAMCM` × 2 |
| Payment | attempt 1 `7ab56b0c-4999-4428-b0b4-d462c3c611d3` `SUCCESS`, no failure code |
| Ledger | one `DEBIT` 251,800 minor (INR 2,518.00), entry `ff8de920-…` = the attempt's `debit_id` |
| Stock `FK-SHTEJR4G5K3TAMCM` | on hand / reserved 10,000 / 0 (seed, v1) → 10,000 / 2 (reserved, v2) → 9,998 / 0 (committed, v3) |
| Resume the same state | Reports `Order 5d19b678-…: CONFIRMED`; no new request with a new key |

**Declined confirmation (session B, user `demo-rehearsal-decline`).** Search `watches under 1000
rupees`, product 1, quantity 1, quote `8999027b-9cd9-4dd8-aa99-b22649c51a48` (INR 899.00), then
Enter at the `CONFIRM` prompt: "No checkout submitted." The HTTP log has session, search, cart,
quote and cart-read requests and no checkout; the Orders audit has no order for this user (one
order in `dev` in total).

**Pipeline evidence for the order.** All six events carry the checkout's original identity (run
`3bff8f3a-457f-4c95-8489-89abfeca63b9`, correlation `9e1a310e-f175-4b57-8c3a-a87156f832ca`). Broker
positions come from the analytics source receipts.

| Event | Event ID | Topic / partition / offset | Disposition | Gold generation |
|---|---|---|---|---:|
| CHECKOUT_STARTED | `49b06a47-0bc4-4264-98dc-03d4b7737b85` | `dev.conversation-events.v1` / 0 / 70 | new_valid | 206 |
| ORDER_CREATED | `f4cad224-e89c-482b-9e3c-90dfa44ca542` | `dev.order-events.v1` / 0 / 0 | new_valid | 206 |
| INVENTORY_RESERVED | `f3830252-7b5a-4b68-ab3e-9addd46459ed` | `dev.inventory-events.v1` / 0 / 19920 | new_valid | 206 |
| PAYMENT_SUCCESS | `ff184da4-a5c8-492f-aec7-657a7cafb956` | `dev.payment-events.v1` / 0 / 0 | new_valid | 206 |
| INVENTORY_COMMITTED | `3b76c5ff-3e52-4de1-ba8b-466a2f3ba83b` | `dev.inventory-events.v1` / 0 / 19921 | new_valid | 206 |
| ORDER_CONFIRMED | `11b01660-f682-4367-bb0b-32f693ed9f55` | `dev.order-events.v1` / 0 / 1 | new_valid | 206 |

Each receipt records Bronze durability, Silver commit and Gold visibility times; all six became
visible in Gold at 13:00:31 UTC, about six minutes after the order. The delay is the analytics
worker still catching up on the 19,920 initial stock events ahead of them on
`dev.inventory-events.v1` (lag 4,921 at 12:55 UTC, 0 at 13:00), a one-time setup effect. Active
Gold `order_fact` (query generation 206, and 209 after the restart below) returns the order:
`CONFIRMED`, version 6, quote `64eb7c00-…`, total 251,800 INR, publication generation 206. At
collection all five operational outboxes had 0 unpublished rows and `export_pending` was 0.

**Restart from retained data.** `env down`, then the [start](#start-data-already-prepared-no-import-no-seed-no-reset)
and [verify](#verify) commands: 55 s in total, `m3_setup` applied nothing, all 12 containers
healthy with the limits above, projection 19,920 of 19,920. The first searches afterwards returned
the same products in 1.0 s and 0.8 s, and the purchased shirt now shows 9,998 available.

Raw files are in `artifacts/rehearsal-20261112/`: `setup.log`, `data-setup.log`, `env-up-*.json`,
`projection-wait-*.json`, `sku_sets.json`, `session-a*/`, `session-b*/`, `searches/`,
`order-evidence.json`, `decline-session-check.json`, `restart-*` and `after-restart/`, with the
driver and collector scripts used.

## Known limitations

- **Simulated payments.** No real gateway; a worker completes each attempt at least 100 ms
  later, with a 5% random business decline in normal mode. Deterministic 95/5 control exists
  only in isolated `bench-` test deployments with both benchmark flags on.
- **Historical catalogue.** 2015–16 Flipkart crawl prices in INR, not current offers. Stock is
  simulated. Only 4 listings carry an apparel size, so size filters usually return nothing.
- **Single broker, local storage.** One Kafka broker with replication factor 1 and one partition
  per topic; PostgreSQL and the lakehouse are local Docker volumes. No high availability.
- **Fixed assistant mode.** Deterministic intent rules; no LLM is called.
- **Development limits.** The limits above are for a low-traffic demo, not the evaluation
  profiles. The first stock projection of 19,920 SKUs took about 30 minutes on this host. It is a
  one-time setup step and is not repeated on restart.
- **Not claimed here:** the full evaluation matrix, fault campaigns, scaling/stress trials and
  100,000-record quality runs.
