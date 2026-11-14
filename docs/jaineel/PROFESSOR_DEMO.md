# Browser prototype demonstration

The dashboard now includes **Failure Demo**, with real worker pause/recovery,
committed-response loss and exact retry, deterministic decline, a precise saga
crash and a persisted 35-second payment delay. Start it with
`./start-failure-demo.ps1`, connect from `/dashboard#failure-demo`, and follow
[the failure operating guide and measured evidence](FAILURE_DEMOS_2026_11_14.md).
For the primary live case, add a product to the store cart before Prepare, pause
analytics, place the order through normal review/confirmation, Watch its new ID,
Recover and Verify. Other cases require explicit scripted-purchase consent.
Use `./stop-failure-demo.ps1` before the normal prototype shutdown.

Run from `payment-gateway` on the prepared Windows machine. The retained volumes,
credentials, catalogue and local embedding model are reused. No import or seed
is required after removing the containers.

## Start

```powershell
.\start-prototype.ps1
```

The script starts Docker Desktop if necessary, starts PostgreSQL, delegates
repeatable migrations to M1/M2/M3, starts the 12-container prototype, and checks
health, stock-projection readiness, fixed-mode searches and the provisioned hybrid retriever.
It stops on a failed command and prints its evidence location. It never submits
a purchase. Once it reports ready, open http://127.0.0.1:8001/.

## Five-minute demonstration

1. Explain the source: 20,000 historical Flipkart observations, 19,998 canonical
   listings and 19,920 active products. Prices are historical INR amounts;
   inventory and payments are simulated. No real payment information is needed.
2. Browse/filter/sort products. Select **AI conversation**. Try `I need a gift`,
   answer `a shirt under 1000 rupees`, then `could you show me other choices?`,
   `what material is the second one?` and `something cheaper than that`.
   Gemini sees bounded session history and preferences. Product facts come
   from validated catalogue tools. Hybrid is automatic for both chat and the top
   search bar; there is no search-method selector. Unsupported hard attributes
   require clarification. The conversation scrolls above the message controls.
3. Open a product, inspect its details, add an available product, and
   open **Cart**. Change quantity if desired, then **Review order**.
   Read the amount and expiry. The purchase button remains disabled until the
   review checkbox is checked. Closing this dialog does not buy anything.
4. Check the box and click **Place demo order** once. Observe the
   durable order status. A simulated decline can legitimately end in CANCELLED;
   do not present that as a successful sale. MANUAL REVIEW needs investigation.
5. Expand **Order processing and analytics**. Reservation/payment IDs come from
   Orders. The analytics indicator appears only after the exact owned order
   version, status, amount and identity match a fact in active Gold. Explain the
   path: local transaction/outbox, Kafka, Bronze, deduplicated Silver, published
   Gold. An API success alone does not establish publication.
6. Refresh, open Cart and show the same order. Refresh/status observation never
   submits another purchase. Chat results/preferences are retained too. After an
   uncertain mutation, use **Retry saved request** to preserve its identity.
   A completed failed search instead has **Retry search**, which makes a fresh
   attempt and preserves the preceding results.

7. Click **Dashboard** in the header or open http://127.0.0.1:8001/dashboard.
   The separate page refreshes every five seconds while visible. Show event
   throughput, response-time charts, producer/type breakdowns, outbox backlog,
   six service readiness checks, order outcomes, the latest owned order's exact
   Gold match, source receipt samples, active Silver/Gold manifests, source
   positions and catalogue attribute coverage. Pause updates or export the
   observed snapshot as JSON when presenting a fixed set of numbers.
   Session quantiles cover the latest 500 turns; the chart shows the latest 60.
   Model attempts cover the whole session. Gold charts cover the namespace and
   displayed UTC day. Receipt statistics deduplicate source positions within the
   first 200 journal observations and indicate when more may exist. Dataset totals span active manifest files across
   dates. Missing providers show Unavailable; missing timings show No samples.
   These observations are not a controlled optimization benchmark.

The store uses AI conversation without a mode selector. The fixed mode remains
available through the API for deterministic evaluation. Search automatically uses
hybrid when ready, with keyword search available during hybrid maintenance.
Search pages show up to twenty ranked matches, with sorting
within that set. Private model settings belong only in the ignored
`artifacts/infra/prototype-local/shopping-llm.env` (`SHOPPING_LLM_ENABLED=true`,
`GEMINI_API_KEY=...`, `SHOPPING_LLM_MODEL=gemini-3.5-flash-lite`). Startup reads
them without displaying them. No key belongs in HTML, JavaScript or Git.

One model HTTP attempt per turn, no automatic retry, an 18-second provider
timeout and a 25-second total budget apply. An outage is shown explicitly;
Retry search starts a new attempt. Retry saved request replays an uncertain
response with its original identity. Chat has no purchase/cart mutation tools.
The original evaluation workflow retains its limits.

Try `only white ones` to show honest no-results handling: this retained CSV has
896 ordinary shirts, all without recorded colour. We cannot label them white.
`Any colour` explicitly removes that constraint. Taxonomy filters exclude bras
and trousers whose descriptions happen to mention shirts.

## Finish and clear containers

```powershell
.\stop-prototype.ps1
```

This removes only this Compose project's containers/network. PostgreSQL, Kafka
and lakehouse volumes, model files, images, private bindings and evidence remain.
Use the same start command next time. No global Docker prune or volume removal
is needed.

The opt-in automated browser rehearsal is documented in the
[integration acceptance record](PROTOTYPE_INTEGRATION_2026_11_13.md). It performs
a labelled scripted simulated purchase; it is separate from startup checks.

Current Windows conversation, metrics and integration evidence is recorded in
[the desktop integration check](WINDOWS_DESKTOP_INTEGRATION_2026_11_13.md).
With the prepared Playwright installation, the following checks use real services:

```powershell
# Real Gemini conversation and metrics; never submits a purchase.
$env:RUN_AI_BROWSER_LIVE = '1'
node tests/conversation/storefront.ai.live.cjs

# Explicit scripted simulated purchase, retries, resume and Gold visibility.
$env:RUN_BROWSER_LIVE = '1'
node tests/conversation/storefront.live.cjs
```

The first check needs the server's private Gemini configuration. Both save their
own evidence under ignored artifacts. Neither is part of normal startup or CI.


For viva questions, measured alternatives and their limits, use
[Professor questions and results](PROFESSOR_QUESTIONS_AND_RESULTS.md). It separates
new component measurements, reused real edge-case evidence, owner-host findings
and unexecuted formal performance claims.
