# Simple prototype UI — 14 November 2026

The dashboard's main view shows service readiness, activity, queues, analytics
latency and order results. The journey page shows the product and transaction
paths and lets the presenter follow an order, search or event. Empty trace panels
appear only after an action is selected. Labels and step explanations use plain
language.

Detailed measurements, CPU/memory/lag history, receipt inspection, dataset files,
attribute coverage, manual fault controls, all existing scenarios, stock projection
inspection, timestamps, record lineage, recording/export and saved playback remain
accessible in expandable sections or the linked dashboard. Nothing changes the
checkout confirmation, retry identity, saga, ledger or pipeline rules.

The store now always requests AI conversation; the chat settings/mode controls and
preference note were removed. Fixed mode remains an API/evaluation capability.
Search prefers hybrid when available and can use advertised lexical search rather
than disabling chat when hybrid alone is unavailable. An unavailable capability
endpoint still blocks search and shows an error.

## Hybrid search repair

The presentation namespace had been imported without embeddings. The existing
checksum-locked model files were valid. Ran the owner's existing preparation
command against that namespace, without reseeding products or stock:

```powershell
.venv\Scripts\python.exe -m infra.retrieval setup
.venv\Scripts\python.exe -m infra.retrieval verify
```

Prepared 19,998 product vectors, including all active products, with the locked
model/template and batch size 16. The manifest reports 905.25 seconds of encoding
and 1,844 truncated descriptions. The temporary preparation container removed
itself. Output: `artifacts/simple-prototype-retrieval-setup.log` and
`artifacts/retrieval/embedding_manifest.json`. Initial cold fixed-mode verification
hit its existing three-second budget; repeat checks passed without changing that
budget. Verified follow-up searches, strict filters and hybrid results:
`artifacts/retrieval/verify-20c8ae91f3614452bfcb799192f222ee`.

Restarted the stale local observation controller after confirming no active fault
or test. Its fresh snapshot reports no unavailable providers, 1,200 timed events,
six partition-lag readings, qualified clocks and zero pending Gold records.

## Verification

- Real Edge + existing services + Gemini: AI request uses `assist` and
  `hybrid_exact`, products return successfully, no chat settings or false search
  warning; dashboard metrics, advanced controls, tracing, export and safe playback
  pass. No purchases or faults submitted. Latest evidence:
  `artifacts/simple-prototype-browser/1794664688446`.
- `node --test tests/conversation/storefront.test.cjs`: 11 passed, including
  confirmation/idempotency and search availability handling.
- `node --test tests/conversation/journey.test.cjs`: 12 passed.
- `node tests/conversation/journey.browser.cjs`: passed with explicit HTTP doubles;
  this is rendering/playback evidence, not a live pipeline claim.
- `python -m pytest tests/conversation/test_shopping_dialogue_http.py tests/conversation/test_shopping_llm.py -q`:
  19 passed, 5 database-dependent tests skipped because the isolated test binding
  was not configured. The live browser test above uses the real running services.
- Ruff for changed Python and `git diff --check`: passed.

The retained browser rehearsals now select fixed mode through their HTTP requests
when they require deterministic operation, rather than a shopper-facing setting.
No CI/CD checks, commits or push performed. Core services remain running for use.

## Guided Journey tests and fixture repairs

The Journey page now has three primary sections: the two data paths, recent
activity to follow, and one test picker with a Run test button. Each case states
what it sends and the expected result. The browser automatically completes the
fixture's observation/publication step; presenters no longer need Finish test,
manual namespace selection, or a source dropdown. Only the two-buyer case asks
for permission to create two simulated orders. All seven test capabilities remain.

Results belong to the explicitly selected run. Choosing another case clears the
previous result. Earlier failed runs remain available under Previous test results,
with setup failures distinguished from failed verification. The UI shows short
checks instead of process logs, raw JSON, namespace identifiers or provider
preconditions. Download test report retains the complete evidence. View test
events selects that run's isolated dataset automatically; Back to store activity
restores the real store's view. Record/replay remains in an optional panel and
saved playback cannot submit mutations.

Two real integration problems were repaired without changing checkout, payment
or pipeline assertions:

- A one-row clean catalogue fixture supplied an empty issue vocabulary to
  Telemetry. `pipelines/catalog/adapter.py` now omits empty metric vocabularies;
  it does not invent issue counts or relax Telemetry validation. A regression
  test verifies that source metrics remain while issue metrics are absent.
- A new consumer can have no accepted facts before its initial Kafka assignment.
  The race fixture now tolerates that missing-publication state within its
  existing bounded observation loop. It still requires both terminal orders in
  queryable active Gold and all original debit/stock reconciliation checks.

Validation on Windows with the real services:

- Direct fixture recheck: all seven passed. Evidence:
  `artifacts/journey-fixture-recheck/` and
  `artifacts/journey-fixture-recheck.log`.
- `$env:RUN_GUIDED_JOURNEY_LIVE='1'; node tests/conversation/journey.guided.live.cjs`:
  all seven passed through the actual one-click page, including two isolated
  simulated purchases, with automatic publication/reconciliation, report export,
  test/store switching, retained failed-history isolation, recording/playback,
  zero playback mutations, zero page errors and no desktop overflow.
  Evidence: `artifacts/journey-guided-browser/1794666758168/`.
- `python -m pytest tests/benchmarks/test_journey.py tests/benchmarks/test_failure_demo.py -q`:
  48 passed; existing Starlette/httpx deprecation warning only.
- `node --test tests/conversation/journey.test.cjs`: 12 passed.
- `node tests/conversation/journey.browser.cjs`: explicit HTTP-double rendering
  and playback check passed after the final UI polish; this is separate from
  real pipeline evidence.
- Changed Python Ruff, JavaScript syntax and whitespace checks passed.

The existing `RUN_JOURNEY_LIVE=1` rehearsal entry point now delegates to the guided
rehearsal. Disposable fixture containers removed themselves after use. The twelve
core project containers remain healthy and running for the local demonstration;
PostgreSQL volumes and historical evidence are retained. No CI/CD execution,
commit or push.
