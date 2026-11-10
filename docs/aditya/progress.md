# Aditya (M3) progress

## 10 November 2026 — prototype boundary fixes and repeatable M3 setup

Branch `aditya/m3-prototype-boundaries`, from main `80f6d88` (after PR #18). No M3
code had changed on main since PR #7. Scope is the prototype handoff from Jaineel,
Vichitr and Harsh: repeatable migrations, quote expiry/ownership, order/SSE ownership,
internal service tokens and fault-control isolation.

### Changes

| Path | Change |
|---|---|
| `services/orders/m3_setup.py` (new) | One repeatable setup command for orders/inventory/payments. Applies only `migrations/<db>/*.sql` with that database's URL, under an advisory lock, recording SHA-256 of LF text in `m3_schema_migrations`. Applied files are skipped; a changed applied file fails (exit 3). Verifies the tables the prototype launcher checks. Exports `runtime_bindings()` with three `RuntimeBindings.migrations` participants. |
| `migrations/{orders,inventory,payments}/*.sql` | Re-runnable: `CREATE TABLE/INDEX IF NOT EXISTS`, `CREATE OR REPLACE TRIGGER`. Table shapes are unchanged. This lets the first run adopt the prototype schemas that were applied by hand from these files (`artifacts/prototype-20261110/bootstrap.json`). |
| `services/orders/commands.py` | Order acceptance follows common §8/§9.1. A retry of an already-accepted quote returns the same order before the quote is re-fetched, so it works after expiry. Otherwise the catalogue quote is validated with the canonical `Quote` DTO; wrong user → 403 `FORBIDDEN`, `expires_at <= server now` → 409 `QUOTE_EXPIRED`, duplicate SKUs or a total that differs from the lines → 409, malformed/mismatched quote → 503. Catalogue 404 → 404 (was 400); catalogue 403 → 403 (was 503). |
| `services/orders/app.py` | `GET /v1/orders/{id}` and its SSE stream return 404 unless the caller's `X-User-ID` owns the order (checked before the stream opens). The fault-barrier body is now a strict model. |
| `services/{orders,inventory,payments}/app.py` | Every `/internal/v1` route requires `Authorization: Bearer $INTERNAL_API_TOKEN` (common §2). It fails closed when the token is unset, matching the catalogue. |
| `services/orders/saga.py` | `fault_injection_allowed(namespace)` is the team convention: `BENCHMARK_MODE=true`, `FAULT_INJECTION_ENABLED=true` **and** a `bench-` namespace. Both the barrier endpoint (403 otherwise) and `FaultBarrier.check` use it. |
| `contracts/http/transactions.yaml` | Documents the new 401/403/404/409 responses. |
| `tests/transactions/test_order_acceptance.py` (new), `test_checkout_live.py`, `test_saga_enhancements.py` | Unit tests for acceptance and catalogue status mapping. The live test now calls an explicit HTTP double of the catalogue quote contract instead of patching `_fetch_quote`, runs migrations through `m3_setup`, and covers expiry, foreign quote, unknown quote, retry after expiry, status/SSE ownership, the token on every internal route, fault gating and setup repeatability. |

### Commands and outcomes

All commands ran with uv 0.10.8 and Python 3.11 (`uv run --locked`).

- Boundary probe: `python -m benchmarks.manual.verify_transaction_boundaries --out artifacts/m3-boundaries-before` on unmodified main gave **7 of 8 failed**, matching Jaineel's report. After the changes (`--out artifacts/m3-boundaries-after`) it gives **0 failed**: foreign status/SSE → 404, audit without token → 401, fault controls → 403 in all three unsafe scopes.
- `INVENTORY_TEST_DATABASE_URL=<postgres 18.6> python -m pytest tests/transactions` → **174 passed, 0 skipped**. The live tests used `postgres:18.6@sha256:edb0c08d…` (the CI digest), run in WSL Docker because Docker Desktop would not start.
- `python -m pytest tests/integration` → 82 passed, 1 skipped. `tests/conversation tests/benchmarks tests/contracts tests/projectctl` → 984 passed, 230 skipped (live-environment skips).
- Setup against PostgreSQL 18, where each database had been migrated by hand with **main's** SQL first:
  - first `python -m services.orders.m3_setup` adopted and recorded every file;
  - a second run applied nothing;
  - an appended line in an applied file was refused (exit 3);
  - a missing URL gave exit 4.
- With `PROJECTCTL_OWNER_RUNTIME_MODULES=services.orders.m3_setup`, `projectctl.team_runtime.runtime_bindings()` registers migration participants for all six `DATABASE_OWNERS`. All three M3 participants return real `COMPLETED`.

### Prototype setup (for Vichitr's deployment)

```bash
# with ORDERS_/INVENTORY_/PAYMENTS_DATABASE_URL from artifacts/infra/prototype-local/.env
python -m services.orders.m3_setup            # all three; or name one: orders | inventory | payments
```

Safe to repeat. On the existing prototype databases the first run records the files that
were already applied by hand. All three services need the same `INTERNAL_API_TOKEN`
(the prototype compose already supplies it); the saga sends it to Inventory and Payments.

### Not done / NOT_RUN

- **Real prototype deployment:** NOT_RUN. Docker Desktop failed to start on this machine, so the compose deployment was not exercised; the evidence above is local PostgreSQL 18 plus explicit doubles. The real catalogue quote endpoint is still not exercised by an M3 test.
- **Deterministic payment controls (95/5, 100 ms):** not implemented. Spec 06 §A04 and spec 03 require durable PENDING attempts and a completion worker that picks outcome and delay from the stable scenario ID and seed in isolated benchmark mode. Nothing carries a scenario ID from checkout to Payments today (G3 expects an M3 `fresh_namespace` callback with `simulator_control_verified`). This needs an interface agreement with Jaineel before implementation.
- **Saga provenance:** the saga worker emits events with its own `run_id` (`saga-worker`), not the order's original run/correlation identity. Fixing it needs that identity stored on the order (a new migration).
- **Evaluation bindings:** G3/T-07/T-08/T-11 `CaseBinding`/`G3Binding`, `ResetParticipant(preflight, apply)`, signed-ledger snapshots, relay startup bindings and the Inventory `pending_outbox` half of Harsh's `seed_audit` remain open.

### Handoffs

- **Jaineel:** rerun the probe and review the M3 contract changes; agree how a stable scenario ID reaches Payments for 95/5 + 100 ms.
- **Vichitr:** run `python -m services.orders.m3_setup` once on the prototype databases (it adopts them), or set `PROJECTCTL_OWNER_RUNTIME_MODULES=services.orders.m3_setup` for global `db migrate`.
- **Harsh:** the quote-validity and live-test findings are fixed as described above. The hash-pin proposal (Decisions item 4 in `docs/harsh/handoff.md`) still awaits Aditya's answer. `m3_setup` hashes LF text, so it works under either outcome.
