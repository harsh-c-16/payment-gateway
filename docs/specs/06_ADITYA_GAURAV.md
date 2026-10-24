# Aditya Gaurav: personal coding brief

Module owner: M3 Orders, Inventory, simulated Payments, saga and shared outbox  
Version 2.0. Read first: 01_PROJECT_CONTEXT.md, 02_COMMON_SPEC.md, 03_EVALUATION_SPEC.md, 08_DATASET_PROFILE_AND_RULES.md and 09_EVALUATION_RUNBOOK.md. The dataset rules and evaluation commands are required implementation inputs, not optional background.

## 1. Your final responsibility

Build the transaction system whose correctness must survive every optimization. You own the three service databases, durable saga, reservation concurrency/expiry, simulated payment ledger, idempotency and the reusable outbox storage/relay library.

Your division stays close to the tracker. Jaineel owns the broad fault/load orchestration and independent oracle; Vichitr owns Kafka infrastructure/SDK and analytics. You provide deterministic failure hooks and service-specific correctness tests.

The CSV has no stock/orders/payments. You own the explicitly simulated inventory and payment state, not CSV parsing/normalization. Consume Harsh's verified active-SKU manifest and preserve dataset revision in events. Do not also build the assistant, catalogue ranking, streaming ETL or dashboard.

## 2. Files and public contracts you own

- services/orders/, services/inventory/, services/payments/.
- migrations/orders/, migrations/inventory/, migrations/payments/.
- shared/outbox/ and its independent tests.
- contracts/http/transactions.yaml, transaction DTOs and test fixtures.
- Transaction domain event payload definitions, reviewed and registered by Vichitr.
- Service fault hooks, read-only audit exports and transaction recovery runbook.

Expose all Order/Inventory/Payment endpoints in common §5 exactly. Implement create_order, advance_saga, reserve_inventory, commit_reservation, release_inventory, expire_reservations, authorize_payment, complete_simulated_payment, compensate, append_outbox, relay_once, recover_pending_outbox and seed_inventory. Provide the projectctl inventory-seed adapter.

## 3. What you require as black boxes

| Provider | Contract | Behavior you need |
|---|---|---|
| Harsh | Internal quote lookup → Quote | Immutable prices/lines, user/cart binding, created/expiry timestamps |
| Harsh | SkuManifest | 19,920 active listing IDs for this file; canonical source lineage/hash; 78 missing-price listings excluded. No source stock is supplied |
| Vichitr | build_event and validate_event | Frozen event schema, routing/key checks, stable IDs/timestamps |
| Vichitr | publish_event → broker-confirmed PublishAck | Explicit uncertain/retryable failure; never acknowledges only an in-memory queue |
| Jaineel | RequestContext + scoped idempotency key | Stable identity across client retries |
| Jaineel | Harness/oracle/fault barrier controller | Concurrent clients, named crash points, independent audit |
| Harsh | Projection inspection | Final SKU versions for stock propagation reconciliation |

You must not read catalogue tables. Obtain the immutable quote via its service API and copy its price snapshot into order_items. Analytics/Gold is not an input to the saga.

## 4. Ordered coding tasks

### A01 — Contracts, local schemas and state machines

Publish HTTP schemas/examples and deterministic stubs first. Implement local database migrations, constraints, operation-key tables, state enums and event payload builders.

Document the legal transitions from common §9. Represent pending/unknown/compensating states explicitly. Add read-only audit exports for order snapshots, reservation rows, stock, attempts and signed ledger entries; these are used only by the benchmark/oracle credentials.

Acceptance: invalid state transitions fail; database credentials cannot write another service’s database; monetary types are integer/exact, and constraints survive restarts.

### A02 — Shared outbox, independently testable

Implement append_outbox using a caller-supplied transaction and no internal commit. Callers in M1/M2/M3 own their business payloads. Add standard migrations/templates for each service to create its own outbox table.

Relay returns an event as published only after Kafka delivery acknowledgement. Default one active relay per database uses an advisory lock and a dedicated connection; a second instance waits. Poll every 25 ms, up to 100 pending rows per pass; preserve ordering within an aggregate. These defaults stay fixed across B0/O1/O2.

Persist immutable serialized content, event_id, produced_at, key/topic and schema mapping. Restart republishes the exact same event. Distinguish publish acknowledgement from marking the row published.

Acceptance: transaction rollback emits nothing; crash after publish-before-mark produces a duplicate delivery and one downstream effect; standby relay does not become a second active publisher.

### A02b — Idempotent simulated inventory seed

Verify Harsh's SkuManifest hash/revision/count and initialize only its active listing SKUs. Each gets on_hand=10,000, reserved=0, stock_version=1 in the performance profile, with explicitly synthetic provenance. Use bounded chunks; stock rows, seed receipts and STOCK_UPDATED outbox rows commit together. A repeated same seed/manifest is a no-op even after inventory has changed; it must never refill sold stock. A different seed requires a fresh test namespace. Test fixtures can declare one-unit stock only in their own namespaces.

Record SeedReport and initial stock digest. Let the shared runner wait for all seed outboxes and Harsh's projection barrier before timing. Do not parse source product text, infer sellers/variants or seed all 20,000 CSV observations as distinct products. Use current operation timestamps; keep 2015–2016 crawl times only in catalogue lineage. No LLM calls anywhere in these services.

Acceptance: D-03 seed checks pass; unknown/inactive SKU is not silently created by reservation; duplicate import/seed does not add stock or duplicate an event.

### A03 — Inventory reservation and expiry

Implement an order-scoped reservation with all-or-nothing SKU lines. Sort SKU locks; validate stock and quantity within the transaction. Store reservation expiry using the Inventory database clock.

Implement commit, release, expiry sweep and cancellation tombstones. Commit checks real current time after row locks are held. The expiry worker touches only ACTIVE reservations and runs every 250 ms.

Mutations update counts and emit absolute snapshots with increasing stock_version in the same transaction. Never emit only a quantity delta for the search projection.

Acceptance: 100 distinct requests for one unit produce at most one successful hold; 100 retries of one key create one hold; an unavailable item in a multi-SKU request reserves nothing.

### A04 — Simulated payment state and ledger

Implement durable PENDING attempts and a controllable completion worker. Use stable scenario ID/seed only in isolated benchmark mode to choose delay/outcome; do not let public clients request “success” or select a fault.

A SUCCESS inserts one debit. A reverse inserts at most one full reversal, cancels PENDING, and closes the order-level payment guard. No delayed callback can create a debit after quiescence.

Same-key retries return the same attempt. An HTTP timeout is unknown, so the caller queries the same attempt. At most two logical attempts are allowed, and only a definitive RETRYABLE_PROVIDER_FAILURE permits attempt two before reservation expiry. Never retry a decline or create another attempt after success.

Acceptance: response loss, repeated callbacks, delayed success and reverse races preserve one net debit for a confirmed order and zero for cancelled orders. Report these as simulated ledger guarantees.

### A05 — Durable Orders orchestrator

POST /v1/orders validates the quote and atomically commits order+items+idempotency response+saga job+outbox. Return 202; no long network saga in the request handler.

The worker persists its intended next command and stable operation key, makes the participant call outside a local transaction, then records the outcome. Recover unfinished jobs on startup. Use order-level worker exclusion and optimistic versions.

Implement normal progression through reserve, payment, stock commit and final confirmation. If the stock commit response is lost, query/retry the same operation. Once stock is COMMITTED, confirm forward after recovery.

Acceptance: killing the worker between any two steps never loses the durable job or creates a second logical participant effect.

### A06 — Compensation, expiry and uncertain states

Implement common §9’s release-before-payment-quiescence protocol. This ordering is intentional: it decides whether stock commit or cancellation won before refunding.

If release reports COMMITTED, do not refund as a generic failure response; finish forward. If release/expiry succeeds, cancel pending payments or reverse success, then record CANCELLED. If any participant state remains unknown, preserve unresolved progress and retry. MANUAL_REVIEW is visible, not a successful terminal result.

Acceptance: late payment after expiry cannot confirm an order; crash during compensation eventually reconciles; a delayed reserve cannot bypass a release tombstone.

### A07 — Status notification and fault hooks

Implement order-versioned SSE with a current-state snapshot at connect/reconnect. Use database notifications as wake-up hints and durable state for truth. No dependence on analytics for customer status.

Expose test barriers at business commit, relay publish-before-mark, payment completion and stock commit. Disable these hooks outside isolated benchmark mode. Provide reset/seed commands scoped to a declared namespace.

Acceptance: the harness demonstrates the exact intended crash boundary rather than an arbitrary process kill that might miss the race.

### A08 — Recovery evidence and handoff

Lead T-07 outbox and T-08 transaction trials. Jaineel supplies concurrent clients/oracles; you supply state/ledger audits and explain recovery. Help T-11 verify analytics stalls do not directly block business commands while durable storage has capacity.

Measure checkout acceptance latency and finality latency separately, retry amplification, compensation duration, pending outbox age and recovery time. Do not interpret a 202 response as a completed sale.

Your primary measured comparison is the same transaction workload without a fault versus with one controlled relay/saga/participant fault. Report additional finality delay, retry amplification and recovery time while verifying identical terminal invariants. Label it a recovery-cost comparison, not a throughput optimization. This gives your module a distinct engineering evaluation without adding another broad optimization subsystem to your workload.

## 5. Contract-level test checklist

- Same key + same request → same resource and no extra outbox transition.
- Same key + different amount/items → 409, no effects.
- Expired/wrong-user quote rejected; accepted order prices never rewritten by catalogue changes.
- One pending/successful payment at a time per order.
- Negative stock, reserved>on_hand and duplicate ledger entries prevented by durable constraints.
- Multi-SKU reservation atomic, lock order deterministic.
- Commit and expiry race at the exact boundary.
- Cancellation before a delayed reserve or payment callback.
- Crash after stock commit before Orders confirmation.
- Crash after business commit before publish and after publish before mark.
- Retry after uncertain HTTP response.
- Service outage exceeding recovery deadline produces explicit unresolved evidence, not a fake cancellation.
- No foreign writes across service databases.

Unit tests alone are insufficient for row-lock and crash behavior. Run these integration cases against real PostgreSQL and the broker/transport test profile.

## 6. Handoffs

| Gate | Your output | Consumer |
|---|---|---|
| G0 | Transaction OpenAPI, DTOs, state transitions, stub publisher and participant services | All owners |
| G1/G2 | Generic outbox library with rollback/retry tests | Jaineel, Harsh, Vichitr |
| G2 | Real Inventory and Payments contracts plus seed hooks | Orders, harness |
| G3 | Complete durable checkout and order notification | Jaineel |
| G4/G6 | Recovery audit, final stock/ledger invariants and raw fault evidence | Jaineel and evaluators |

You are done when another teammate can restart every participant/saga process at the documented failure boundaries and reconcile all accepted work without inspecting your implementation.

## 7. Evals you must code and run

Implement the inventory-seed/audit/fault adapters consumed by projectctl. Run D-03 seeding cases with Harsh, then T-07 outbox and all T-08 cases against real PostgreSQL/Kafka. Supply barrier acknowledgements and read-only stock/reservation/order/payment/ledger snapshots for Jaineel's independent oracle.

Run the W-CHECKOUT no-fault versus named-fault comparisons in runbook §5 with three paired repetitions, and support T-11's 30-second outages. Record acceptance and finality separately, physical/logical retry counts, compensation duration, unresolved states, backlog and recovery time. No 202 response counts as a completed sale. Reconcile stock conservation and exactly one net debit per confirmed order / zero per cancelled order after drain.

These simulated business events test the real pipeline implementation; they are not observed Flipkart transactions. Mark source/catalogue revision and simulation provenance in manifests and events. All required evidence/commands are in runbook §§4,5,7.

## 8. Prompt for your coding LLM

> I am Aditya, owner of transaction services and the reusable outbox. Read the shared context/spec/evaluation and this brief. Start A01 with exact contracts, migrations, idempotency scopes and legal state transitions; then implement active-SKU-manifest seeding and the specified evaluation/audit adapters. Do not implement a live payment gateway, read other services’ databases, or assume a timeout means failure. Preserve the commit-versus-expiry protocol and durable planned commands. Use a stub Kafka publisher until Vichitr’s adapter is ready. Report actual tests and unresolved failure cases.

