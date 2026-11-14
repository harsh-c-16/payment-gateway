# Separate Windows desktop dashboard

The subsequent [Failure Demo delivery](FAILURE_DEMOS_2026_11_14.md) adds real
scoped fault controls, live manual/automated run distinction, measured timelines,
stock/ledger charts, independent assertions and evidence download to this same
page. The read-only views and original sample boundaries below remain available.

The storefront header links to http://127.0.0.1:8001/dashboard. All dashboard
charts, metric cards and analytics polling were removed from the shopping page.
No extra frontend server, JavaScript dependency or external chart CDN is needed.

## Delivered views

- Published unique event throughput over the last 60 event-time minutes, plus
  event-type and producer-service breakdowns from today's namespace Gold.
- Current-session total/model latency for the latest 60 turns; nearest-rank
  P50/P95 and counts over the latest 500, with whole-session durable model attempts.
- Namespace M1 outbox backlog, six API/storage readiness observations, Gold order
  statuses and confirmed simulated order value. Readiness is not an uptime claim.
- The browser's latest owned order and exact active Gold publication match,
  observed through existing order APIs without replaying any purchase request.
- Unique source positions within the first 200 namespace receipt-journal observations,
  their real dispositions, and observed
  ingest-to-Gold P95 excluding recovery bounds, negative and missing timings.
  The page says when additional observations may exist. Repeated journal entries
  for one source position count once. This is not a global failure rate.
- Active Silver/Gold generations, files, physical rows, bytes, transform versions
  and bounded published source offsets. These offsets are not broker-head lag.
- Catalogue revision, hybrid readiness, recorded vocabulary and real canonical
  attribute coverage, including missing values. Facet counts are owner API data.
- Pipeline/protocol architecture, consistency explanations, explicit data scopes,
  pause/manual/automatic refresh, stale/missing states and JSON snapshot export.

The dashboard reads only M1's own tables directly. Other modules are queried
through their validated APIs. Session ownership is checked before any external
probe. Internal receipt access uses an explicitly configured server-side service
token; no token, database binding or user message is exported. At most two
analytics reads run concurrently; HTTP calls and sample sizes are bounded.

CPU/RAM, broker-head consumer lag, independent ledger reconciliation and controlled
fault qualification are not collected by this page. They are not shown as zeros.
It remains a single-Windows-host prototype, not a cross-host HA demonstration.

## Changed paths

`services/conversation/{app.py,dashboard.py,gateway.py,shopping_metrics.py,
shopping_contract.py}`, `services/conversation/web/{dashboard.html,dashboard.css,
dashboard.js,index.html,store.css,store.js}`, `shared/contracts/shopping.py`,
the generated `contracts/http/shopping.yaml`, dashboard tests and existing
browser rehearsal navigation, current README/demo/spec/progress documentation.
Existing local additions were retained. No commit or push was performed.

The old metrics endpoint remains available. Existing canonical M2/M3/M4 APIs and
business implementations are reused. An additive M1 dashboard DTO documents the
new projection endpoint. Private pre-edit backup: `artifacts/dashboard-20261114/before.zip`.

## Verification and evidence

Commands run from the prepared Windows checkout:

```powershell
$env:PYTHONPATH = (Get-Location).Path
.venv/Scripts/python.exe artifacts/dashboard-20261114/run-checks.py
node --test tests/conversation/storefront.test.cjs
.venv/Scripts/python.exe -m services.conversation.shopping_contract --check
$env:RUN_DASHBOARD_BROWSER_LIVE = '1'
node tests/conversation/dashboard.live.cjs
```

The isolated PostgreSQL conversation suite passed **489 tests** in 177.69 seconds.
It includes six new checks for ownership-before-probing, projection accuracy,
missing providers, namespace isolation, valid receipt timing and UTC day bounds.
Owner HTTP/event/model doubles are explicit. Node controller checks passed 11.
Ruff, generated contract consistency, Node syntax and whitespace checks passed.
The final receipt aggregation checks passed seven focused dashboard tests after
adding journal deduplication and conflicting-source-identity rejection. Evidence:
`dashboard-final.{log,xml}` from `run-dashboard-checks.py` in the same artifacts folder.

The browser check uses real Edge and local services, checks five desktop sizes,
downloads the real snapshot, navigates store → dashboard, creates one fixed-mode
shopping turn, verifies latency/throughput charts and confirms that refresh does
not add turns or submit checkout. A separate, explicitly labelled browser-only
partial-provider projection verifies unavailable cards/chart empty states; it
does not fault the running services. Screenshots were visually inspected.

Raw records: `artifacts/dashboard-20261114/`, including `conversation.{log,xml}`
and browser subdirectories. Initial integration failures and intermediate browser
checks are retained separately. The first broad test run had one concurrency
assertion failure while browser activity was running; the unchanged full suite
passed on a subsequent run without concurrent browser checks. One browser run
also observed a temporary analytics timeout and correctly displayed unavailable
data. The dashboard now limits concurrent analytics reads and samples 200 receipts.

Manual steps: open the store, press Ctrl+F5 and follow the Dashboard link. Use
the same browser to see its session timings and latest order. Pause/export a
snapshot while presenting; resume to watch subsequent store activity. Normal
startup/shutdown remains `start-prototype.ps1` / `stop-prototype.ps1`.
