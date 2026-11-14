# Windows desktop integration check — 13 November 2026

The user authorized cross-module integration for a Windows professor prototype,
with preservation of existing additions, real API conversation and visible metrics.
The working branch already contained PR #23 / 628abeb via merge 616d9cc. No branch
switch, reset, new import, stock seed, volume removal, commit or push was performed.
The initial 36 modified/untracked paths were backed up privately before editing
at `artifacts/conversation-integration-20261113/{before-changes.zip,before.patch}`.
Existing retrieval, browser, checkout, recovery and Gold additions were retained.

## Vichitr's requested priorities

| Priority | Delivered and checked |
|---|---|
| CI | Fixed the obsolete eleven-spec scaffold assertion. The user's Windows-only request removes the Ubuntu matrix and Linux-host PostgreSQL/Kafka jobs. Windows retains locked dependency installation, generated-contract checks, offline assertions, browser controller checks and unconditional evidence upload. A Windows OneDrive/scanner sharing-lock failure in the P5 checkpoint writer now has finite retries; permanent failures retain both old and pending evidence. |
| Actual LLM conversation | A server-only Gemini adapter makes one bounded API attempt on every `assist` shopping turn, using saved history, pending questions, preferences and displayed products. Four typed decisions cover search/refinement, clarification, fresh product details/comparison and conversational navigation. Invalid tools/arguments, invented clarification facts, unknown facets, dropped filters, provider errors and stale product identities are rejected. It executes only existing validated catalogue tools. |
| Product relevance | Ordinary shirts, T-shirts, bras and trousers use recorded whole taxonomy segments for candidate relevance. Existing colour, budget, stock and exclusion predicates stay in force. The real retained catalogue has 896 ordinary shirts and no recorded colours for them; white-shirt requests now honestly return no results. |
| Hybrid retrieval | Preserved the existing checksum-locked local encoder, semantic image, model mount, vectors and memory allocation. Real M1/M2 verification covers inference, budgets, alternatives, references, strict colour handling and saved hybrid mode. No replacement model or catalogue was introduced. |
| Windows lifecycle | Root PowerShell scripts perform Docker readiness, owner migrations, service readiness, projection wait and fixed/hybrid preflight. Private Gemini settings are read from an ignored file and injected only into Conversation. Stop/recreate/start was verified with retained data and volumes. |
| Browser rehearsal | Real Edge browser: search, cart, authoritative quote, unchecked/declined confirmation, explicit simulated purchase, terminal state, exact retry, refresh/resume, Gold match, strict empty results and live metrics. A separate real Gemini browser check covers eight conversational turns with no checkout request. |

The original fixed endpoint and optional P11 intent fallback keep their policy,
zero-call deterministic behavior and three-second budget. Desktop conversation
uses an 18-second provider bound, a 25-second turn budget, at most one selected
action and six catalogue calls including metadata. Durable model-attempt claims
prevent duplicate generation after uncertain responses or rollback. Products,
prices and advisory stock are rendered from backend facts; chat exposes no cart
or purchase mutation tool. Checkout retains its quote and idempotency controls.

## Metrics shown to the professor

`GET /v1/sessions/{session_id}/metrics` authorizes session ownership before reads.
Its browser panel refreshes every five seconds while open. It shows actual saved
turn/search/embedding/error counts, nearest-rank P50/P95 total turn latency, mean
model duration, durable session model attempts and session events awaiting Kafka.
The count/timing sample is bounded to the last 500 turns; model attempts cover
the whole session. Namespace pipeline totals come from active Gold for the
displayed UTC day. Missing samples/providers remain null/Unavailable.

The eight-turn real Gemini browser sample recorded 8 model attempts, 5 searches,
5 query embeddings, zero dependency errors, P50 **2,251.70 ms**, P95 **2,684.19 ms**
and mean model time **1,657.39 ms**. At that snapshot, this namespace's published
event count was 467 and active generation 347. These are dated demo observations,
not controlled throughput or optimization results. The existing Prometheus
`/metrics` endpoint and benchmark dashboard definitions remain available.

## Actual validation

Private raw evidence: `artifacts/conversation-integration-20261113/`.

| Exact command/check | Actual result | Evidence |
|---|---|---|
| `.venv/Scripts/python.exe -m benchmarks.manual.verify_prompt6 --job offline --out artifacts/conversation-integration-20261113/offline-verified` | PASS: 1,927 passed, 627 explicitly skipped service-dependent checks, zero failures/errors; remote GitHub Actions was not rerun | `offline-verified/{checks,summary}.json`, logs and JUnit |
| `python artifacts/conversation-integration-20261113/run-services-isolated.py` with newly created disposable test databases | 766 passed; real PostgreSQL with explicit HTTP/model/event doubles where declared | `services-isolated.{log,xml}`, `services-final-runner.log` |
| `python artifacts/conversation-integration-20261113/run-dialogue-tests.py` after final guard changes | 24 passed, including zero-call fixed mode, durable retry, actual quantile inputs, owned metrics and failure handling | `dialogue-final.{log,xml}`, `dialogue-runner-final.log` |
| `python artifacts/conversation-integration-20261113/run-catalog-checks.py` | 73 passed with the real locked encoder/PostgreSQL in Docker Desktop's existing runtime; explicit event captures | `catalog.{log,xml}` |
| `node tests/conversation/storefront.test.cjs` | 11 passed, including independent assistant/retrieval selection | Controller output |
| `RUN_BROWSER_LIVE=1 node tests/conversation/storefront.live.cjs` | PASS; one scripted simulated purchase, exact cart retry, close-without-purchasing, refresh/resume and Gold | `browser/{checks,purchase,metrics}.json`, HTTP journal and screenshots |
| `RUN_AI_BROWSER_LIVE=1 node tests/conversation/storefront.ai.live.cjs` | PASS; 8 real Gemini turns, 0 checkout requests, 0 console errors, empty-result refresh and explicit filter removal | `ai-browser/{checks,turns,metrics}.json`, screenshot |
| `python .../audit-purchase.py`; exact owned order event/receipt audit | PASS before/after recreation: committed reservation, one successful payment, one debit, matching projected stock and Gold; 6 exact Kafka receipts are durable and Gold-visible | `transaction-audit.json`, `kafka-receipts.json` |
| `./stop-prototype.ps1`; `./start-prototype.ps1` | PASS, containers removed and recreated; projection, six fixed checks and hybrid preflight passed | `stop.log`, `start-final.log` |
| `python -m infra.retrieval verify` | PASS, fixed mode with real local encoder/catalogue | `hybrid-final.log`, referenced retrieval HTTP journal |
| Ruff lint/format; both generated shopping/catalogue contracts; original conversation contract; Node syntax; `git diff --check`; Git-visible credential scan | PASS; no key in Git-visible files | Tool output and ignored key paths |

The browser purchase is order `cce5bd87-ccc7-4607-84e6-b72e872d0859`, CONFIRMED
version 6 for INR 297. Its reservation is COMMITTED and exactly one DEBIT of
29,700 minor units matches the net payment. Inventory and catalogue stock versions
agree, and the exact version/immutable facts match active Gold. Confirmation was
scripted regression input; the professor's demonstration still uses a human.

Initial failures are retained and not called passes: stale CI/scaffold assertions,
a Windows evidence sharing lock, provider 404/503 responses, a readiness race in
an early verification invocation, missing scripted Gold double behavior, and a
receipt collector's assumption that a change journal contains one row per event.
The last was corrected by locating the exact events and reading their receipt
cursor; no service assertion was weakened. Provider failures produce a clear
message and preserve preferences. The configured Flash Lite model completed both
real rehearsals; it remains configurable server-side.

Visual inspection also found assistant chat bubbles inheriting the sidebar's
sticky positioning through the shared `assistant` class. Sidebar CSS is now
scoped to the aside, and the intro collapses once messages exist. The real browser
asserts ordinary static bubble positioning. Refresh now retains an empty search
instead of replacing it with unrestricted browsing.

Formal benchmark campaigns, production authentication/payments and missing
all-owner byte-pinned review receipts remain outside this requested desktop
checkpoint. The contracts command reports the pre-existing missing-review gate as
NOT_RUN. No benchmark target or outside peer approval was fabricated.

The healthy stack is left running at http://127.0.0.1:8001/. Follow
[PROFESSOR_DEMO.md](PROFESSOR_DEMO.md) for presenting and stopping it.


During final runtime reload Docker Desktop's engine stopped answering even
container-status requests. Its graceful restart timed out. The stuck Desktop
processes and only the named docker-desktop WSL distribution were restarted;
no volumes or data were removed. The Windows launcher now bounds each engine
probe to five seconds and its readiness loop to two minutes, so an unresponsive
engine cannot hang that loop indefinitely. Recovery startup evidence is retained
in start-engine-recovered.log. Conversation timing also excludes the measured
model interval from parse time, avoiding double counting in stage breakdowns.

Final engine recovery completed: start-engine-recovered.log reports readiness, projection, fixed preflight and hybrid PASS. The latest 24 dialogue/metrics tests and independent purchase audit pass after recovery. final-health.json verifies all 12 containers healthy, AI configured, presentation flags off, key scoped to M1 and persisted session metrics available.
