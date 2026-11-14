# Windows desktop shopping UI update

The requested changes were completed across 13–14 November. Existing local work
was preserved; no Git commit or push was performed. The pre-edit UI and affected
workflow files are retained in ignored `artifacts/ui-polish-20261113/before.zip`.

## What changed

- Chat uses a viewport-bounded desktop sidebar with a separate scrolling message
  area and fixed space for action buttons and the composer. Long messages and
  preferences scroll; the send button has its own column. Chat mode is under the
  collapsed Chat settings control; Basic chat preserves deterministic evaluation.
- The retrieval selector and algorithm wording were removed. New browser searches
  always request `hybrid_exact`, discarding obsolete saved keyword preferences.
  Missing hybrid capability is shown as unavailable; full catalogue browsing
  remains usable. Exact retries of uncertain requests retain their saved identity.
- Nonempty top-bar queries now call the existing validated M2 hybrid search rather
  than the lexical browse endpoint. M1 extracts recorded colour/material/category
  and budget constraints using the existing facet dictionary. The existing M2
  taxonomy guard excludes bras/trousers from ordinary-shirt searches. No source
  data, facet values, embeddings, prices or stock were invented or reimported.
- Query pages show up to twenty ranked products, paged by twelve; price sorting
  applies to that set, and the UI labels it “top matches.” Empty-query browsing
  retains full-catalogue pagination. The frozen original turn endpoint still
  defaults to five lexical hits. Explicit API evaluation modes remain available.
- Checkout now says Review order, Order summary, Update order summary and Place
  demo order. Internal quote IDs/cart versions were removed from the summary.
  The checked review requirement, expiry/cart-version validation, idempotency and
  explicit purchase handler remain enforced. The demo-payment explanation stays
  in the cart. The two requested promotional banner sentences were removed.
- Metrics label chat searches/embeddings explicitly; they do not count independent
  top-bar searches as conversation turns.

## Actual verification

- `node --test tests/conversation/storefront.test.cjs`: 11 passed, including exact
  retry identity, confirmation/expiry guards and automatic hybrid selection.
- `python artifacts/ui-polish-20261113/run-checks.py`: 483 conversation tests
  passed in 116.60 seconds. Storage uses a new disposable PostgreSQL database;
  owner HTTP/model/event doubles are explicit. Existing demo databases were not
  reset. Initial copy-assertion/fixture failures and the final pass are retained.
- `RUN_LAYOUT_BROWSER_LIVE=1 node tests/conversation/storefront.layout.live.cjs`:
  PASS against real local APIs in Edge at 1366×768, 1280×720, 1440×900, 1920×1080
  and 1067×600, with Chat settings both open and closed. Buttons stayed within
  the viewport, no controls overlapped and no horizontal page overflow occurred.
  Repeated DOM messages are an explicitly labelled layout stress fixture.
  Hybrid chat/top-bar search, cart and quote review were real service calls.
  Review unchecked → disabled and checked → enabled passed; zero purchases.
- `RUN_AI_BROWSER_LIVE=1 node tests/conversation/storefront.ai.live.cjs`: PASS
  against real Gemini and local APIs: eight turns, saved preferences/references,
  more options, refresh/resume, strict colour handling and metrics. Zero console
  errors and zero purchase requests. An initial attempt immediately after service
  restart hit an empty response; the run after readiness passed.
- Ruff, Node syntax and Git whitespace checks passed. Desktop screenshots were
  visually inspected. No new complete checkout or fault campaign is claimed.

Raw records: `artifacts/ui-polish-20261113/{conversation.log,conversation.xml,
browser-final/,ai-browser-ready/}`. The integration scope changes are recorded in
[the shopping specification](../specs/11_SHOPPING_EXPERIENCE.md).

Changed paths: `services/conversation/web/{index.html,store.css,store.js}`,
`services/conversation/{shopping.py,shopping_dialogue.py,workflow.py}`,
`tests/conversation/{storefront.test.cjs,storefront.live.cjs,storefront.ai.live.cjs,
storefront.layout.live.cjs,test_shopping_http.py,test_shopping_dialogue_http.py}`,
and the current shopping/demo/progress documentation. M2 provider code and its
data contracts were reused without changes in this update.

## Manual check

The application is running at http://127.0.0.1:8001/. Press Ctrl+F5 to load the
updated assets in an existing tab. Try “shirts under 1000 rupees” in chat and in
the top search bar. Open Cart, select Review order and inspect the summary.
Closing the cart does not place an order. Use `start-prototype.ps1` after a normal
shutdown; see [the demonstration guide](PROFESSOR_DEMO.md).
