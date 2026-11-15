# Load, stress and failure tests on the running prototype

**Result.** On one laptop the prototype completes **about 2.2 to 2.7 purchases per second** at most,
end to end, with no failed purchase at any load level. Beyond 4 concurrent shoppers only waiting
time grows. Every correctness check passed after the load: 818 orders, stock on 288 products and
416 analytical rows reconcile exactly, with no oversell, double debit or lost order. All 8
failure and recovery tests passed (97 of 97 independent checks). The weak points are capacity:
PostgreSQL (0.5 CPU) is saturated in every phase, the store search box loses throughput under
concurrency, events wait about 47 s in the outbox under sustained load, and the conversation
container was killed once for running out of memory (128 MiB).

This is an **owner-run measurement on one machine** (Harsh's laptop, 15-16 November 2026; runs at
18:29-18:56 UTC on 15 November). It is not the evaluation-spec stress protocol (§8 of
[03_EVALUATION_SPEC.md](../specs/03_EVALUATION_SPEC.md): W-PIPE at 500/1,000/2,000 events/s, three
repetitions), it is not on the Windows presentation machine, and each load level ran once, so no
confidence interval is claimed. The load generator runs on the same host as the services.

## Setup

| Item | Value |
|---|---|
| Code revision | `2d467c669f2fbeb9062739cd165318555bcb875e` (`main`, PR #29 merge), clean worktree |
| Deployment | The 12-container prototype from [infra/DEPLOYMENT_INFO.md](../../infra/DEPLOYMENT_INFO.md), namespace `dev`, retained data (19,920 active products, each seeded with 10,000 units), hybrid retrieval provisioned |
| Container limits | 8 CPUs and 4,224 MiB in total; PostgreSQL 0.5 CPU / 512 MiB, conversation 1 CPU / 128 MiB, catalogue 1 CPU / 768 MiB (retrieval image), others 0.5-1 CPU / 128-1,024 MiB |
| Software | Docker Engine 29.1.3, Compose 2.40.3, PostgreSQL 18.2 (container), Kafka 4.1.2 |
| Host | AMD Ryzen 7 7840HS (8 cores / 16 threads), 15.4 GB RAM, NVMe SSD, Ubuntu 26.04.1, Linux 7.0.0-43 |
| Client | Python 3.11 with `httpx` (already a project dependency), asyncio, same host over loopback |
| Readiness before the test | `env verify` exit 0, `projection wait` exit 0 (19,920 / 19,920), `demo-check` PASS, `infra.retrieval verify` PASS |

## Method

- **Closed loop.** N simulated shoppers each send their next request as soon as the previous one
  returns. Each level runs 3 s of warm-up and then 30 s of measurement. Latency percentiles are
  nearest-rank over successful requests only; failures are counted separately.
- **Only public APIs.** The client uses the same store endpoints as the browser (`/v1/sessions`,
  `/v1/store/products`, `/v1/carts/...`, `shopping-turns` in fixed mode), plus the catalogue's
  `/v1/search` directly with the 50 frozen W-SEARCH queries
  ([queries.json](../../contracts/fixtures/catalog/queries.json)). Every purchase is simulated;
  there is no real payment.
- **A purchase** is: create a session, add one unit of a product to the cart, request a quote,
  confirm checkout, then poll the order every 100 ms until it is CONFIRMED or CANCELLED. Products
  are drawn from a fixed random pool of 200. Payments declines 5% of payments on purpose
  (`SIMULATED_FAILURE_RATE` in `services/payments/authorize.py`); a declined and compensated
  order counts as a correct outcome, not an error.
- **Resources.** CPU, memory and Kafka consumer lag come from the dashboard helper's
  `/infrastructure` readings (cgroup counters, every 3 s). CPU is a percentage of each container's
  own allocation, so PostgreSQL at 100% means half a CPU.
- **Correctness** is checked after the load drains, from the owners' read-only audit APIs and active
  Gold, not from the client's own records (see below).

## Load results

### Full purchase (session, cart, quote, checkout, until CONFIRMED)

| Shoppers | Purchases/s (run 2) | p50 ms | p95 ms | p99 ms | Failed | Purchases/s (run 1) |
|---|---|---|---|---|---|---|
| 1 | 1.33 | 721 | 997 | 1,107 | 0 of 41 | 1.19 |
| 4 | 2.68 | 1,476 | 1,850 | 2,105 | 0 of 84 | 2.39 |
| 16 | 2.46 | 5,593 | 7,134 | 7,673 | 0 of 80 | 2.15 |
| 32 | 2.17 | 9,780 | 10,624 | 10,931 | 0 of 78 | 2.34 |

Time inside a purchase, p50 / p95 ms (run 2):

| Shoppers | Session | Add to cart | Quote | Checkout accepted | Checkout to CONFIRMED |
|---|---|---|---|---|---|
| 1 | 13 / 67 | 18 / 96 | 134 / 207 | 122 / 264 | 539 / 736 |
| 4 | 77 / 202 | 116 / 239 | 400 / 582 | 402 / 623 | 861 / 1,096 |
| 16 | 722 / 1,278 | 711 / 1,397 | 1,843 / 2,381 | 2,002 / 2,610 | 2,343 / 3,435 |
| 32 | 1,386 / 2,085 | 1,370 / 1,830 | 3,557 / 3,898 | 3,119 / 3,948 | 3,383 / 4,175 |

Of the 283 purchases in run 2, 269 were confirmed and 14 (4.9%) were declined by the simulator and
correctly cancelled, which matches the configured 5%.

### Catalogue search API, direct (`POST /v1/search`, lexical)

| Clients | Searches/s | p50 ms | p95 ms | p99 ms | Failed |
|---|---|---|---|---|---|
| 1 | 7.25 | 106 | 294 | 508 | 0 of 219 |
| 8 | 8.67 | 806 | 1,312 | 1,997 | 0 of 268 |
| 32 | 7.66 | 2,385 | 2,903 | 3,900 | 178 of 426 (HTTP 503) |
| 64 | 8.23 | 3,988 | 4,999 | 5,774 | 285 of 562 (HTTP 503) |

Throughput stays level at about 8 searches/s. The extra requests are refused rather than queued for
ever: the catalogue holds 4 database connections in the prototype (`CATALOG_MAX_CONNECTIONS=4` in
`infra/compose.prototype.yaml`), waits at most 2 s for one, and limits each statement to 2 s, then
answers a retryable 503 (`services/catalog/database.py:40-58`).

### Store search box (`GET /v1/store/products?q=...`, conversation service then hybrid search)

| Clients | Searches/s | p50 ms | p95 ms | Failed |
|---|---|---|---|---|
| 1 | 1.56 | 613 | 1,176 | 0 of 47 |
| 8 | 0.65 | 2,998 | 3,804 | 54 of 76 (HTTP 503) |
| 32 | 0.18 | 3,627 | 6,871 | 181 of 187 (HTTP 503) |
| 64 | 0.24 | 7,408 | 9,857 | 193 of 202 (HTTP 503) |

Unlike the direct API, throughput here **falls** as load rises. The 503s come from the conversation
service, not the catalogue: in the 10 minutes covering that phase the catalogue logged 571
successful responses and 2 errors (both facet reads). Each store search makes two catalogue calls (facet dictionary, then hybrid search;
`services/conversation/shopping.py:309-357`), and the conversation service gives each call at most
2 s (`services/conversation/clients.py:43,118-128`). When a call runs out of time the shopper gets
503, but the catalogue still finishes the work, so wasted work grows with load. The conversation
container reached 97% of its CPU and PostgreSQL 100%.

### Chat turn, fixed mode (no language-model call)

| Clients | Turns/s | p50 ms | p95 ms | Failed |
|---|---|---|---|---|
| 1 | 1.21 | 721 | 1,506 | 0 of 37 |
| 4 | 2.11 | 1,793 | 3,015 | 0 of 67 |
| 16 | 1.84 | 2,972 | 3,192 | 152 of 212 (HTTP 503) |

Gemini (assist mode) was not load-tested: it is an external, rate-limited service.

## Stress cases

| Case | What happened | Correctness |
|---|---|---|
| Retry storm: 50 identical checkout requests (same idempotency key) at once | 39 returned the order, 11 returned a retryable 503; **one** order exists; stock 10,000 to 9,999 | PASS |
| Double click: 50 checkout clicks on one cart, a new key each, at once | 8 returned the same order, 42 returned `409 IDEMPOTENCY_CONFLICT`; **one** order exists | PASS |
| 25 shoppers buy the same product at the same instant | 18 orders (17 confirmed, 1 declined); 7 got 503 at the quote; p95 7.4 s; stock dropped by exactly 17 | PASS |
| 50 shoppers, same product | 25 orders (24 confirmed, 1 declined); 26 got 503 (22 at quote, 3 at checkout, 1 at cart); p95 12.5 s; stock dropped by exactly 24 | PASS |
| 100 shoppers, same product | 33 orders (32 confirmed, 1 declined); 69 got 503 (58 at quote, 9 at checkout, 2 at cart); p95 19.6 s; stock dropped by exactly 32 | PASS |

**A 503 on checkout does not always mean the purchase failed.** In the 50- and 100-shopper cases,
3 of the 12 checkouts answered with 503 had in fact been accepted and confirmed (24 and 32
confirmed orders, against 23 and 30 seen by the client). The orders exist exactly once and were
charged once. The conversation service marks a timed-out write as outcome-unknown
(`services/conversation/clients.py:241`), and the store keeps the same idempotency key for its
Retry button, so retrying returns the real order, as the retry-storm case shows.

## Correctness after the load drained

All checks below read the owners' audit APIs (`/internal/v1/audit/orders`, `/reservations`,
`/ledger`, inventory stock) and active Gold. They cover **every order in namespace `dev`**,
including earlier demonstration orders, not only this test's.

| Check | Result |
|---|---|
| Orders | 818: 768 CONFIRMED, 50 CANCELLED, none stuck in between |
| Every CONFIRMED order | has a COMMITTED reservation and exactly one debit equal to its total |
| Every CANCELLED order | nets 0 in the ledger and has no committed stock (770 debits in total: 768 confirmed orders plus 2 debits that were reversed) |
| Stock conservation | on 288 products, on hand = 10,000 seeded minus committed units (775); 0 units left reserved; no negative stock |
| Active Gold | all 416 load-test orders present exactly once, with the same status as Orders; 0 missing, 0 duplicates |
| Problems found | none |

## Pipeline: how long until an order is queryable

| Condition | Event created to queryable Gold |
|---|---|
| Light load (scheduled `duplicate` lab fixture, 2 events) | 2.8 s and 3.1 s |
| Sustained checkout load (1,200 events, pipeline's own clock-qualified timing) | **p50 34.6 s, p95 57.5 s, p99 64.4 s** |
| Client view under the same load (384 orders, 1 s Gold polling) | p50 33.4 s, p95 55.2 s |
| After the last request | everything terminal, in Gold and Kafka lag 0 within **18.5 s** |

Stage breakdown for the last 120 events under load, the stress bursts (p50): creation to arrival in
Kafka, which is the outbox wait plus the send, **46.6 s**; Kafka to Silver 2.6 s; Silver to Gold 3.1 s. Almost all the delay is the outbox relay.
It sends one event at a time, waits for the broker's acknowledgement, then commits one Postgres
update per event (`shared/outbox/__init__.py:193-213`). The relay container sat at only 17% CPU, so
it is waiting, not computing, and its commits are slow because PostgreSQL is saturated. Peak Kafka
consumer lag was 1,516 records.

## Failure and recovery tests

Run after the load test through the dashboard's controller, the same consent-gated path as its
buttons. Each one checks the exact order, stock, payment ledger and active Gold independently.

| Scenario | Result | Checks passed | Duration |
|---|---|---|---|
| Analytics paused, then catch-up | Passed | 14 / 14 | 9.5 s |
| Duplicate checkout and lost response | Passed | 14 / 14 | 7.4 s |
| Payment decline and compensation | Passed | 13 / 13 | 9.8 s |
| Saga crash and restart | Passed | 14 / 14 | 16.1 s |
| Payment after reservation expiry (35 s delay) | Passed | 17 / 17 | 38.8 s |
| Successful debit, then reversal | Passed | 15 / 15 | 38.7 s |
| Two shoppers, one unit (isolated lab) | Passed | 6 / 6 | - |
| Duplicate Kafka delivery (isolated lab) | Passed | 4 / 4 | 6.1 s |

The race fixture's checks: exactly one confirmed sale, the competing order cancelled, no
overselling with the last unit consumed, one debit, an unchanged total, and both orders reconciled in
Gold.

## Resources: idle and peak

| Container | CPU idle | CPU peak | Memory peak / limit (MiB) |
|---|---|---|---|
| postgres | 35% | 103% | 510 / 512 |
| conversation | 8% | 97% | 128 / 128 |
| analytics-worker | 19% | 78% | 177 / 320 |
| orders | 13% | 34% | 85 / 128 |
| analytics | 22% | 30% | 90 / 192 |
| inventory | 13% | 24% | 84 / 128 |
| payments | 13% | 23% | 78 / 128 |
| prototype-relays | 8% | 17% | 56 / 128 |
| catalog | 6% | 16% | 349 / 768 |
| schema-registry | 4% | 16% | 419 / 640 |
| catalog-worker | 10% | 16% | 69 / 128 |
| kafka | 5% | 12% | 433 / 1,024 |

Idle was measured with no traffic and nothing pending (PostgreSQL 32-37% over a separate minute of
samples). Container memory includes page cache, so PostgreSQL's 510 MiB is not all process memory.

## Incident: the conversation service ran out of memory

In run 1 the conversation container was killed by the kernel (exit 137, `OOMKilled=true`, 128 MiB
limit) during the 50-request retry storm that followed straight after the 100-shopper case. Its
restart policy is `no`, so the store stayed down until `projectctl env up` brought it back (exit 0,
then `env verify` exit 0). Run 2 repeated the same cases with the container peaking at 126-128 of
128 MiB, and it survived. The orders from run 1 were included in the final reconciliation above.

## What limits capacity

1. **PostgreSQL CPU.** All five service databases share one PostgreSQL limited to 0.5 CPU. It is at
   100% of that in every phase and already at a third of it when idle.
2. **Conversation memory.** 128 MiB is reached under bursts and caused the one crash; with
   `restart: no` the store does not come back on its own.
3. **Outbox relay.** One broker acknowledgement and one commit per event make events wait about
   47 s under sustained load, even though the relay is mostly idle.
4. **Store search path.** Two catalogue calls per search and a 2 s per-call limit in the
   conversation service make throughput fall under load instead of levelling off.

Each of these belongs to a teammate's module or to the shared deployment, so they are reported
here, not changed.

## Operational notes

- After `projectctl env up` restarts services, the dashboard's failure scenarios fail with
  `payments POST /internal/v1/demo-control: HTTP 403` until
  `python -m benchmarks.failure_demo.setup enable` is run again.
- `benchmarks.manual.dashboard_activity --simulate-purchases` answered 503 ("another desktop failure
  run holds the local scenario lease") right after a lab fixture finished; the same command
  succeeded a few seconds later. It then reconciled one checkout and found all 6 searches' events in
  Gold.

## Evidence

Raw results are in the git-ignored `artifacts/loadtest-20261115/` on Harsh's laptop: the client
(`load_test.py`, `failure_suite.py`, `lab_suite.py`), per-step results (`run1/results.json`,
run `9d714290-88bc-4293-b136-22b66c8591dd`; `run2/results.json`, run
`a23ada55-24ca-4fa1-8f2a-ccae4846dc4e`), resource samples, the pipeline snapshot after the load,
each failure and lab run, and the generated `REPORT.md`. Run 1 measured the search, chat and
checkout phases and crashed in the stress cases; run 2 repeated the checkout phase and ran every
stress case and the reconciliation.
