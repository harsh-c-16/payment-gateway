# Windows dashboard failure demonstrations — 14 November 2026

The existing `/dashboard` now contains **Failure Demo**. It uses the retained local
services, catalogue, PostgreSQL/Kafka/lakehouse volumes and normal shopping
checkout. Existing changes were preserved; no branch switch, reset, reseed,
commit or push was performed. Pre-edit files are in
`artifacts/failure-demo-20261114/before.zip`.

## Launch and finish

```powershell
.\start-prototype.ps1       # when the prepared prototype is stopped
.\start-failure-demo.ps1
# Open http://127.0.0.1:8001/dashboard#failure-demo, then Connect local controller.
```

The second script enables *support* for scoped hooks in Orders/Payments and starts
a hidden Windows helper on `127.0.0.1:8010`. It never purchases or arms a fault.
The normal benchmark/fault-injection flags remain false. Ordinary checkout keeps
its random simulated outcome and 100-ms payment plan; only an explicitly armed
run changes its plan. The storefront remains user friendly, and Find similar
remains removed.

```powershell
.\stop-failure-demo.ps1     # recover first, stop helper, disable hook support
.\stop-prototype.ps1        # optional normal project shutdown; retains all volumes
```

The helper accepts the exact local dashboard Origin/Host and loopback clients.
It exposes fixed scenario actions, not Docker commands, shell input, bindings or
credentials. Container labels and this checkout's read-only code mounts are
validated before actions. Port 8011 holds an exclusive run lease across browser
and CLI controllers. One active run is allowed; each trigger is single-use.

## Professor's primary live demonstration

1. Open the store and dashboard in the same browser profile. Add the intended
   product(s) to the store cart **before** preparing; this captures independent
   stock baselines for the exact SKUs. Avoid other purchases of these SKUs during
   a measured run; stock/version conflicts fail verification rather than being hidden.
2. Choose **Analytics pause & catch-up**, **Live manual demo**, then **Prepare
   baseline**. This reads owner APIs and records baseline order IDs and stock.
3. Press **Trigger fault**. Only `analytics-worker` is paused. The Analytics read
   API, Kafka, outbox relays, catalogue projection and transactional services stay
   separate. No operational outbox growth is required for this demonstration.
4. In the store, review the order, check its review checkbox and press **Place
   demo order**. The helper does not submit this purchase. Normal simulated
   payment can decline; a cancelled order is not a successful sale.
5. Back in Failure Demo, **Watch order** uses the new saved order ID or an entered
   UUID. Ownership is checked by M1/Orders. Baseline orders and SKUs without a
   captured baseline are rejected. Wait for the journal's terminal-order / paused-
   worker / pending-exact-Gold observation before recovering.
6. Press **Recover processing**, wait for catch-up, then **Verify effects**.
   Passed requires the exact order identity, version, status, amount and currency
   in active Gold, plus independent reservation, stock/version and signed ledger
   checks. The retained worker container identity must match.
7. Download **Evidence**. It contains the run identity, exact checkout/request
   identity where applicable, actual timestamps, measured samples, assertions and
   recovery facts. It contains no service tokens, database bindings or messages.

The five-step strip is Prepare → Trigger → Observe → Recover → Verify. The three
new graphs show timestamped worker/API/order/Gold samples, consumed/reserved stock
relative to the baseline, and the watched order's independently summed payment
ledger. Baseline stock is a measured sample; unknown ledger/order values remain
null. Lines connect observations for reading; they do not establish the exact
time of a transition between samples. Hover for timestamps and values.

## Remaining scenarios and automated mode

Select **Automated test**, **Prepare baseline**, review the selected product and
amount, then check the explicit consent box. Prepare creates a labelled synthetic
session/cart but never submits checkout. The quote is refreshed at Trigger; a
changed prepared amount aborts before purchase. **Run automated test** performs
the five stages with one explicitly authorized simulated checkout. Alternatively,
use Trigger, Observe, the relevant recovery control and Verify individually.

| Scenario | Fault and recovery | Required verification |
|---|---|---|
| Analytics | Pause the worker, complete checkout, observe exact Gold pending, resume the same container | One confirmed order/debit/stock commitment and exact catch-up to active Gold |
| Duplicate checkout / lost response | Trigger raises a gateway timeout **after real M1 checkout returns its committed 202**. HTTP callers receive an injected 504 without the order response. Press **Retry identical request**, preserving request ID, idempotency key and body | Original committed order returned; exactly one new purchase, one debit, one reservation commitment and two stock-version advances (reserve + commit) |
| Decline | Scoped deterministic DECLINED plan; existing saga compensates; Recover clears the plan | CANCELLED, released/expired reservation, restored on-hand/reserved stock, one failed attempt and zero signed ledger/debit entries |
| Saga crash | Orders fsyncs a run/order checkpoint acknowledgement and exits 86 at **saga.after_commit**, after Inventory HTTP 200 and before saga advancement. Recover starts that retained Orders container | Exact acknowledged checkpoint/order and process exit, durable forward recovery, one debit and no repeated stock effect |
| Delayed callback after expiry | Persist completion due at 35 seconds in Payments; reservation expires at 30 seconds; observe beyond actual stored due time | RESERVATION_EXPIRED/CANCELLED, release/expiry before completion due, pending attempt quiesced/CANCELLED, restored stock, no late debit, exact cancelled Gold |

The late case demonstrates the **current saga's suppression of a pending late
callback**. It does not claim a successful late debit was refunded. The actual
stored due/creation timestamps are exported from a restricted Payments-owned
read-only API; expiry and post-due observations are required. MANUAL_REVIEW and
stuck orders never pass. Cancellation events canonically omit participant IDs;
M1 matches their published identity/version/status/amount/failure fields and
audits participant effects separately through their owner APIs. Confirmed Gold
still requires the exact reservation/payment IDs.

Response loss is an injected **server gateway timeout**, not a claimed TCP cut or
a browser appearance change. The CLI experiences the same raised gateway failure
after commit; the HTTP rehearsal verifies the actual 504. Generic Recover never
replays checkout. Only Retry identical request, or that named stage of an
explicit automated test, replays its saved operation.

Polling and refresh only read. Automated observation has a 165-second budget;
the live monitor attempts recovery after a monotonic 240-second deadline. Each
owner HTTP call has a 10-second timeout; process actions and restart readiness
have separate 25-second bounds. Fault plans expire within
240 seconds (the owner API rejects more than 300). Docker actions and readiness
waits have finite deadlines. Interrupted controller state is retained, automatic
checkout replay is forbidden, and Recover remains available after restart.
If the helper is terminated while a worker is paused, restart it and use Recover;
there is no independent external supervisor while the helper is down.

## Actual validation and evidence

Commands from the prepared Windows checkout:

```powershell
# Explicitly authorizes five scripted simulated purchases; real services.
.venv/Scripts/python.exe -m benchmarks.manual.verify_failure_demo --simulate-purchases --out artifacts/failure-demo-20261114/real-services

# Disposable test databases; the runner creates/drops only its new DBs.
$env:PYTHONPATH = (Get-Location).Path
.venv/Scripts/python.exe artifacts/failure-demo-20261114/run-checks.py

# Explicit Edge rehearsal: five automated cases and one normal store-control path.
$env:RUN_FAILURE_DEMO_LIVE = '1'
$env:BROWSER_EVIDENCE_DIR = 'artifacts/failure-demo-20261114/browser-final'
node tests/conversation/failure-demo.live.cjs

node --test tests/conversation/storefront.test.cjs
.venv/Scripts/python.exe -m services.conversation.shopping_contract --check
```

All five CLI cases passed against real PostgreSQL, owner HTTP services, Kafka and
active Gold. Each order total was **239,800 minor units (INR 2,398)**, taken from
the prepared catalogue/quote, not a hard-coded purchase price.

| Real-service case | Order | Actual terminal result |
|---|---|---|
| Analytics | `016c2f14-b975-407c-8d19-6537c123a484` | CONFIRMED v6, exact Gold; terminal/pending proof while worker paused |
| Retry | `ac171876-d5ee-42e4-9d7d-7225d101ba3f` | CONFIRMED v6; same identity, one debit and one stock commitment |
| Decline | `4f724107-cace-4021-a0ba-dd169f374f7b` | CANCELLED v5; stock restored and zero net debit |
| Crash | `6ade04d9-10a8-4d48-8e23-18df5219b128` | CONFIRMED v6 after acknowledged saga.after_commit exit 86 and retained-container restart |
| Late | `843179c8-4f84-40a4-9514-b566c6b6daa4` | CANCELLED v5; actual persisted delay 35,000 ms; expiry, quiescence and post-due zero debit |

Raw CLI evidence: `artifacts/failure-demo-20261114/real-services/`, including
`results.json` and per-run `evidence.json`. The first Edge run passed all five
scenarios plus the manual shopping control path, downloaded evidence, checked six
viewport widths from 760 to 1920, and proved that refresh/reload emitted zero
controller mutations. The manual control path is driven by labelled scripted
test input; it is not a claim that a human placed the regression order.
Its real order was `1f8959dc-61a4-4734-b9e8-11aa2fd2d028`, CONFIRMED v6.
Screenshots were visually inspected; chart labels were subsequently enlarged and
measured baseline stock samples added. The final browser rerun is recorded in
`browser-final/{checks,controller-http}.json`, per-scenario evidence and PNGs.
That final run again passed all five cases and the normal store-control path;
its manual order is `9f209f48-713e-4137-a8e3-d2d1133074b2`, CONFIRMED v6.
After tightening the CLI gateway boundary to raise before returning success,
the final real CLI retry also passed: order
`f106d937-cb31-4454-ae4a-da29ed1490ae`; raw evidence is `real-retry-final/`.

The full isolated PostgreSQL conversation/transaction suite plus new hook/controller
tests passed **718 tests** in 181.71 seconds. Explicit catalogue/model/event/registry
doubles in these suites remain labelled; this is separate from the real-service
CLI and Edge claims. The final focused controller checks passed **23 tests**,
including corruption, cross-origin/Host refusal, arbitrary-action refusal, strict
confirmation, interrupted-state recovery, scoped hook expiry, one-shot checkpoint,
monotonic timeout recovery without checkout, and a server-side 504 after committed
acknowledgement with exact retry identity.
New real-PostgreSQL hook checks verify immutable 35-second/decline plans and
unchanged payment identity after clearing the hook. Evidence is `regression.{log,xml}`
and `controller-final-v3.{log,xml}`; overlapping test counts must not be summed.
Ruff, generated shopping-contract consistency, Node syntax, 11 storefront
controller checks, whitespace and Git-visible credential checks passed. The
final `final-health.json` records all 12 project containers healthy, all six
owner/read APIs ready, no paused analytics worker, no active owner fault plans
and normal benchmark/fault flags false.

Initial failures are retained: Docker Desktop's two mount-path spellings required
normalization; an invocation ran before restarted M1 became ready; cancellation
Gold matching required the canonical event-field correction; one new fixture
needed an explicit retained reservation ID; the existing payment unit test needed
to assert the added delay SQL parameter as well as its unchanged 100-ms default.
Raw initial suite evidence is `regression-initial.{log,xml}` and earlier CLI/browser
directories. No failing assertion was skipped to produce a pass.

## Scope and limits

No scenario remains dependent on a mock-only button. These are Windows desktop
prototype demonstrations, not formal performance trials, production HA, disk-loss
durability or exhaustive fault-tolerance qualification. Sample timestamps are
observation bounds. Order namespace audits stop at 1,000 rows; a saturated bound
is unavailable, not a correctness pass. Stock observations can detect interference
from another shopper. Broker-head lag, CPU/RAM and throughput/recovery SLOs are
not measured by these trials. Existing receipt-journal charts retain their
namespace/topic/partition/offset deduplication and publication-offset labels.

Changed paths for this task: `benchmarks/failure_demo/`,
`benchmarks/manual/verify_failure_demo.py`, `services/conversation/{app,shopping}.py`,
`services/conversation/web/{dashboard.html,failure-demo.css,failure-demo.js}`,
`shared/local_diagnostics/demo_controls.py`, narrowly scoped hooks in
`services/orders/{app,saga}.py` and `services/payments/{app,authorize}.py`,
`start-failure-demo.ps1`, `stop-failure-demo.ps1`, corresponding benchmark,
conversation/integration tests, the payment unit assertion, and current demo/progress
documentation. No owner database is read directly by an operational service or
by the controller; independent effects use owner audit APIs. Test-only temporary
database setup uses the established independent harness mechanism.
