# Shopping website implementation — 13 November 2026

User-authorized scope: implement the conversational shopping product across module
boundaries, reuse the CSV-backed services, make routine decisions without waiting,
avoid benchmark campaigns, and collect changes in one combined branch commit.

## Delivered

- Buildless, same-origin storefront served by M1: product browsing, keyword search,
  category/budget filters, price sorting, pagination, recorded images/details,
  cart quantities, authoritative quote review and explicit simulated checkout.
- Contextual shopping turns: vague-request questions, answers to pending questions,
  retained filters, cheaper alternatives, selected-product similarity, excluded
  previously shown SKUs and explicit filter clearing/new searches.
- Persistent private session context in additive migration 005, protected by the
  existing ownership/session lock and atomic response/outbox/idempotency transaction.
- Same existing provider APIs, integer money, cart versions and durable checkout;
  browser retries keep their saved request identity. No provider credentials enter
  the browser. API responses remain validated against owner contracts.
- Honest model capability reporting and an actual `hybrid_exact` request path.
  The standard local deployment remains keyword-only until M2's locked model and
  embeddings are provisioned. No claimed semantic fallback or model downloads.
- Additive shopping OpenAPI, catalogue extensions and strict consumer fixture updates.
  Original fixed-turn and transaction contracts remain usable. CI selection unchanged.

Main changed paths: `services/conversation/{app,state,workflow,shopping}.py`, its
`web/` assets, `services/catalog/{app,products,search}.py`, shared catalogue/shopping
DTOs, migration 005, owner/API fixtures, and the new shopping tests. Public behaviour
is canonical in [11_SHOPPING_EXPERIENCE.md](../specs/11_SHOPPING_EXPERIENCE.md).

## Actual checks

All commands used the existing locked Python 3.11 environment. Private PostgreSQL
bindings were loaded in-process and never printed. SQL tests used isolated random
schemas, then dropped only those test schemas. Catalogue filesystem checks ran on
Linux in the existing application image, capped at 384 MiB / 1 CPU. PostgreSQL was
the only retained container started; the full application stack was not started.

Evidence stays private/git-ignored under `artifacts/shopping-20261113/`.

| Check | Result | Evidence |
|---|---|---|
| `python -m pytest tests/conversation tests/contracts/test_contracts.py tests/contracts/test_clients.py -q` with real PostgreSQL | 548 passed at the first regression checkpoint | `regression.xml` |
| Linux `python -m pytest tests/catalog/test_shopping_live.py tests/catalog/test_products_live.py tests/catalog/test_search_live.py -q` | 46 passed | `catalog-linux.xml` |
| Final shopping HTTP/rule and strict consumer contract subset | 133 passed, including atomic-memory rollback and missing-provider tests | `final.xml` |
| `python -m pytest tests/conversation/test_shopping.py -q` after short-answer handling | 17 passed | `short-answers.xml` |
| `node tests/conversation/storefront.test.cjs` | 4 passed: retry identity, explicit confirmation, expired quote, unsafe image scheme | Session output |
| Ruff lint/format, generated catalogue/shopping contract checks, Node syntax and Git whitespace | Passed | Session output |

The commands' test sets overlap; do not add these counts. The initial runs caught
test fixture mistakes (wire outcome names, JSONB adaptation, Linux source mounts)
which were corrected without weakening assertions. Initial raw results were retained.
Direct Windows catalogue import checks failed at directory fsync as designed and
were rerun successfully in Linux. Existing Starlette/httpx deprecation and JUnit
property warnings do not represent failed assertions.

## Real local service checks

Temporary native FastAPI processes used retained PostgreSQL, real owner schemas,
actual shared outboxes and the original CSV-backed catalogue. No provider/event
doubles were injected. This avoided starting Kafka/registry/analytics alongside the
8 GB Windows desktop. M1 migration 005 and repeatable M3 migrations were verified.

`real-shopping-smoke.json` records:

- Browse: 19,920 active products, pagination and source image URLs in responses.
- Product details and honest keyword-only capability response.
- `I need a gift` → clarification.
- `shirts under 1000 rupees` → five products.
- `Only blue ones` → five filtered products, retaining the budget.
- `Show more options` → five products excluding the prior set.
- Selected-product similarity → five products with the selected anchor excluded.
- Persisted session snapshot and saved dialogue.

`real-shopping-checkout.json` records **SCRIPTED_SIMULATED_PURCHASE**, not a human
browser rehearsal:

- Order `2211348f-c115-4ceb-8b24-f4f95dc2c65f`, quantity one, INR 549.
- Terminal state `CONFIRMED`; reservation `COMMITTED`.
- Exactly one successful payment attempt and one matching `DEBIT` of 54,900 minor
  units, checked through the existing payment/ledger audit APIs.
- SKU `FK-TSHEJCQ2VWZAKZJ4`: actual inventory 10,000 → 9,999; reserved returned to zero.
- Cart/status reads resume durable state; no second order was submitted.

These are real service results, but **not broker receipts or Gold ingestion proof**.
Outbox events are retained for the normal relays to publish at the next full start.
The stock projection remains advisory until its consumer catches up. No data was
reimported, reseeded, reset or deleted.

## Presentation and remaining checks

Use [PROTOTYPE.md](../../infra/PROTOTYPE.md) to start, including the M1 migration,
then open `http://127.0.0.1:8001/`. Use the existing full stack for presentation so
outboxes, projection and Gold can catch up. Keep benchmark/fault flags off.

The browser-control environment reported no available browsers and rejected creating
an in-app browser. Visual layout, mobile layout, external image loading, and a human
click-through remain unverified; Node controller checks are not a substitute for
that rehearsal. Verify them once on the presentation machine using a real browser.

Semantic model provisioning, latest-order Kafka/Gold drain verification, evaluations,
benchmarks, fault campaigns and the full repository suite were not run in this task.
Synthetic identities/simulated payments remain prototype limitations. The temporary
preview APIs and Docker Desktop were stopped afterward; all volumes were preserved.
