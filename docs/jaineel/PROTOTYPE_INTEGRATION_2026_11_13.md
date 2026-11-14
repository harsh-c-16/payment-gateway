# Desktop prototype integration acceptance — 13 November 2026

The user authorized cross-module integration/fixes for a working professor
demonstration, including frontend work, and requested Docker container cleanup.
The final scope is desktop. Existing work from the preceding retrieval task was
preserved; no commit or push was requested or performed.

## Connected presentation flow

| Boundary | Verified behaviour |
|---|---|
| Browser → M1 → M2 | Real CSV-backed browsing, contextual hybrid searches, refinements, exclusions, product details/similarity and cart selection |
| M1 → M2 → M3 | Authoritative quote, explicit confirmation, durable accepted order, reservation and asynchronous simulated payment |
| M3 → Kafka → M2 | Purchased SKU's stock projection matches Inventory after event delivery |
| Outboxes → Kafka → M4 | Exact confirmed order version and immutable facts appear in active Gold |
| M4 → M1 → browser | New owned-order publication endpoint and processing details show verified Gold visibility |
| Retained volumes → recreated containers | One-command migration/startup/preflight and a read-only purchase audit support the prepared machine |

## Changes

- Added `GET /v1/store/orders/{order_id}/pipeline`, an M1-owned DTO and generated
  shopping OpenAPI. Orders authorizes the identity before Gold is queried. The
  consumer uses the order's UTC creation day and checks namespace, unique order
  version, `order_status`, user/session/quote, amount/currency and participant IDs.
  Missing/older facts stay pending; unavailable/conflicting facts never become
  verified publication. No namespace-wide Gold response or service token reaches
  the browser. Existing provider contracts/reducers are reused.
- Wired Analytics into M1's strict HTTP gateway and prototype environment. The
  order panel shows processing/publication and retains an expanded panel while
  polling. Terminal status refresh releases the quote control correctly.
- A completed failed search preserves preceding products/preferences and offers
  a fresh request. Unknown mutations retain their exact retry identity. Refresh
  restores chat products/session/order. Capability outages select labelled
  keyword mode and permit browsing. Unreadable responses and slow historical
  image links have bounded user-facing fallback behaviour.
- A real browser keyword search exposed temporary-file spill at PostgreSQL's
  default 4 MiB work memory. The bounded storefront text query now uses 16 MiB
  locally. Identical rows/scores/counts were checked; its plan changed from 505
  temporary blocks written to zero. Filters, ordering and timeouts are unchanged;
  the evaluated `/v1/search` path and baseline/index variants are unchanged.
  These diagnostic plans are not a controlled optimization benchmark.
- Added `start-prototype.ps1` and `stop-prototype.ps1`. Startup delegates to the
  existing owner migrators, checks all containers and runs fixed/hybrid preflight.
  Cleanup enables **all Compose profiles**, removes only this project's
  containers/network, verifies no project containers remain, and retains volumes,
  images, credentials, model files and evidence.

Implementation paths: `services/conversation/{app,gateway,shopping}.py`,
`services/conversation/web/{index.html,store.js,store.css}`,
`services/catalog/products.py`, `shared/contracts/shopping.py`,
`contracts/http/shopping.yaml`, `infra/compose.prototype.yaml`, and the two root
PowerShell scripts. Tests are in `tests/conversation/`; current instructions are
in [PROFESSOR_DEMO.md](PROFESSOR_DEMO.md), root README and `infra/PROTOTYPE.md`.
The preceding model integration has its own
[record](RETRIEVAL_INTEGRATION_2026_11_13.md).

## Actual checks and evidence

Raw logs, JUnit, scripts, HTTP journals, own synthetic purchase state and screenshots
are private/git-ignored under `artifacts/prototype-integration-20261113/`.

| Exact command/check | Actual result | Evidence |
|---|---|---|
| `pytest tests/conversation tests/transactions tests/integration -q --tb=short` with two disposable PostgreSQL databases | **743 passed**, no skips/failures; explicit provider doubles remain labelled in those tests | `run-services-isolated.py`, `services-isolated.{log,xml}` |
| Linux `pytest tests/catalog/test_shopping_live.py tests/catalog/test_products_live.py tests/catalog/test_search_live.py -q --tb=short` | **54 passed**, real PostgreSQL, explicit event capture | `catalog-tests.log`; `artifacts/retrieval/prototype-catalog-tests.xml` |
| `node tests/conversation/storefront.test.cjs` | **9 passed**: stable retries, confirmation/expiry, image scheme, retrieval modes, search failure, terminal controls and capability outage | Session output |
| `RUN_BROWSER_LIVE=1 node tests/conversation/storefront.live.cjs` with Playwright 1.65.0 and installed headless Edge | **PASS** through real services; includes explicitly injected browser response faults and one scripted simulated purchase | `browser-verified/{checks,http,purchase,accepted-order}.json`, PNGs |
| `node .../browser-resume.cjs` | PASS after panel-persistence correction: same order, no checkout request, expanded Gold details stay open | `browser-verified/resume-checks.json`, `order-gold-expanded.png` |
| `python .../audit-purchase.py` | Independent read-only API audit PASS, before and after container recreation | `transaction-audit-{before,after}-restart.json` |
| `python .../browse-plan.py` | Identical result rows/scores/count; bounded memory avoids the observed spill | `browse-plan-{4MB,16MB}.json` |
| `python -m services.conversation.shopping_contract --check`; `python -m projectctl.conversation_contract --check` | PASS | Session output |
| Ruff lint/format, Node syntax, local current-document links, `git diff --check` | PASS | Session output |
| `./start-prototype.ps1` | Prepared-machine startup, migrations, 12-container health, six fixed preflight checks and real hybrid preflight | `clean-start.log` |

The final browser order is `6939892a-aee9-4094-8525-6fdf010cd7fa`, CONFIRMED at
version 6 for INR 160.00. Its reservation is COMMITTED, one payment attempt is
SUCCESS, and exactly one DEBIT matches 16,000 minor units. Current Inventory and
catalogue projection versions/availability agree. The exact order is visible in
Gold. The browser observed one checkout request despite refresh, while a lost
cart response was retried with unchanged payload/key and one cart version change.
Confirmation was scripted regression input, not a human approval claim.

Initial failures are preserved and were not counted as passes. They exposed
completed search-error rendering, capabilities blocking initial browse, the
actual Gold `order_status` mapping, a broad text-browse spill, and profile-scoped
container teardown. An initial service test run sharing the live conversation
database failed the relay test because advisory locks are database-wide despite
isolated schemas. The complete passing run used newly created disposable test
databases, then removed only those databases. No assertion was weakened or case
skipped. Early rehearsals' separate simulated orders remain as test evidence.

## Scope and operating instructions

Use the [desktop presentation guide](PROFESSOR_DEMO.md). Automatic startup checks
create search sessions, never a purchase. The opt-in browser rehearsal requires
Playwright (`npm install --prefix artifacts/tooling/prototype-browser playwright@1.65.0`)
and `RUN_BROWSER_LIVE=1`; keep it separate from presenting.

This is prototype acceptance. Formal owner-review receipts, frozen benchmark
bindings/matrix, human relevance labels and full fault campaigns remain separate.
No real bank/payment integration, production authentication or autonomous
purchase authority was introduced. No product import, inventory reseed, volume
reset or raw-data change was needed.

`./stop-prototype.ps1` was verified to leave zero containers, then
`./start-prototype.ps1` recreated the deployment from zero containers with exit 0
(`start-from-zero.log`). All migrations were verified without a data reset;
six fixed-mode checks and hybrid preflight passed. Read-only API and browser
resume audits after recreation returned the same confirmed order, committed
reservation, single debit, stock projection and Gold fact, with zero new checkout
requests. This independently verifies the retained data required for the demo.

Final container removal is recorded in `final-cleanup.log` and
`cleanup-receipt.json` alongside the retained-volume list. The site is stopped
after this checkpoint; use the start script before presenting.
