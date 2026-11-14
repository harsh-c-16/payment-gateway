# Conversational shopping prototype

The 13 November product request adds a browser shopping experience to the original
data-engineering release. This supplements the scope in 01; its earlier exclusion
of a full retail UI does not exclude this requested local storefront. The products
come from our imported CSV in our PostgreSQL catalogue. No external shopping API
or replacement catalogue is involved.

## User experience

Open `http://127.0.0.1:8001/` after starting the prototype. Conversation serves the
HTML, CSS and JavaScript itself; no Node server, frontend build or extra container
is required. Desktop shows products alongside chat; mobile puts chat above products.

- Browse available products, search with automatic hybrid retrieval, filter category/maximum INR price,
  sort by price and move through pages.
- Open details, view source image links and recorded attributes, and add products
  to the cart. Unreachable images use a local placeholder; ingestion downloads none.
- Describe a product in chat. A vague gift request asks what product is wanted.
  Replies preserve the budget and explicit constraints. Try `I need a gift`, then
  `shirts under 1000 rupees`, `only blue ones`, and `show more options`.
- `More options` excludes previously shown SKUs. In chat, `More like the second one`
  uses the referenced product. Product details contain no similar-product action.
  `Cheaper` uses a price below the selected or cheapest shown product. Hard filters
  remain in force; no matches never silently removes them.
- Explicitly remove a filter with `any colour`, `any brand` or `no budget limit`.
  A new product subject starts a new search; `New search: watches` resets filters.
- Update cart quantities, request an authoritative quote, inspect its amount and
  expiry via **Review order**, check confirmation and press **Place demo order**. Chat text
  cannot create an order. Closing the dialog does not purchase anything.
- Refresh resumes the same browser identity, session, cart and saved order. An
  unknown mutation result retains its original request and idempotency key for retry.
  Checkout polls the existing Orders service and never buys again to resolve uncertainty.
- Order processing details show an analytics publication only after the exact
  owned order version and immutable facts match active Gold. A missing/older fact
  remains pending; an unavailable or conflicting response never becomes a success.
- A failed completed chat turn preserves prior results and offers a fresh search
  attempt. A capabilities outage shows search unavailable and still permits
  browsing. Historical images fall back to the local placeholder within
  five seconds when they cannot load.

The configured desktop assistant uses Gemini for each conversational turn, with
bounded private history, saved preferences, clarification, refinements and product
references. One typed read-only tool decision is validated before execution.
Product facts come from catalogue responses; the model cannot mutate carts or
purchase. Credentials stay in M1. One model attempt, at most six catalogue reads
(including metadata), an 18-second provider timeout and a 25-second total budget
apply. Provider failures stay visible.

Deterministic chat is separately available as **Basic chat** in **Chat settings**,
with zero generative calls. The
original turn endpoint and optional intent fallback retain their evaluation
policy and three-second deadline. The desktop extension is authorized by the
current product request and does not change those benchmark controls.

## Boundaries and contracts

`contracts/http/shopping.yaml` describes the additive M1 APIs:

| API | Purpose |
|---|---|
| `GET /v1/store/bootstrap` | Public namespace and simulated-payment indicator |
| `GET /v1/store/products` | Namespace-scoped browse/search/filter/sort/page |
| `GET /v1/store/products/{sku}` | Recorded product and advisory stock details |
| `GET /v1/store/facets` | Existing catalogue dictionary |
| `GET /v1/store/capabilities` | Whether hybrid retrieval is provisioned |
| `GET /v1/sessions/{session_id}` | Owned session's saved conversation |
| `GET /v1/sessions/{session_id}/metrics` | Session measurements and namespace Gold totals |
| `GET /v1/sessions/{session_id}/dashboard` | Read-only dashboard projections and bounded receipt/latency samples |
| `POST /v1/sessions/{session_id}/shopping-turns` | Contextual shopping dialogue |
| `GET /v1/store/orders/{order_id}` | Existing owned order status |
| `GET /v1/store/orders/{order_id}/pipeline` | Owned-order publication check through the real Gold API |

Cart, quote and checkout continue to use `contracts/http/conversation.yaml` and the
existing M1 workflow. M1 validates catalogue and transaction responses against the
owner OpenAPI contracts. Catalogue adds `GET /v1/products`, capabilities, optional
`image_urls`, and optional `exclude_skus` (at most 200). The original turn endpoint
keeps its request and behaviour.

Migration `005_shopping_context.sql` adds private JSON session context. It preserves
existing rows and runs through the checksummed M1 migrator. Session locks serialize
turns. Context, response, idempotency and conversation outbox events commit together.
The saved history is bounded to 40 messages and the current result set to 20 products.
Raw messages stay in M1's private database, not in shared Kafka payloads.

Read-only storefront browsing emits no retrieval events. Chat search continues to
emit the existing catalogue search/retrieval events. Cart and transaction provenance,
quote ownership, versions and explicit confirmation use the existing implementation.

## Keyword and hybrid retrieval

Keyword search works with the retained catalogue immediately. Hybrid calls Harsh's
existing `hybrid_exact` keyword/vector fusion, applying hard constraints and exclusions
before ranking. It is enabled only when the locked local encoder is loaded and every
active product has an embedding for that encoder revision. An unavailable model never
silently becomes a purported hybrid result.

The desktop browser always requests hybrid; no retrieval algorithm selector is
shown. Old saved keyword preferences are discarded. Both chat and nonempty
top-bar searches use the existing hybrid service. Empty-query browsing retains
the full catalogue pages. Query pages show up to twenty ranked recommendations,
with price sorting over that set; they do not claim a global match count. The M1
adapter extracts recorded facet and budget constraints before retrieval. Existing
taxonomy restrictions apply before fusion; missing attributes stay unknown.
New shopping API sessions without a requested mode select available hybrid;
follow-ups retain their saved mode. Explicit lexical mode remains available to
API evaluation clients. Every
semantic response must report one query embedding and its model revision when
the query has text. M2 rejects missing or mixed-revision eligible vectors. The
browser uses shopper-friendly result labels. The original fixed-turn endpoint
retains its lexical behaviour.

The prototype can now provision and retain this integration with
`python -m infra.retrieval setup`; see [the deployment instructions](../../infra/PROTOTYPE.md#enable-the-existing-semantic-retriever).
For a manual deployment, use the existing M2 tools:

1. Install the hash-pinned optional runtime from
   `contracts/data/catalog/embedding_requirements.txt` in the catalogue environment.
2. Put the three files named in `contracts/data/catalog/embedding_model.lock.json`
   under `EMBEDDING_MODEL_DIR`. Fetch only the pinned repository revision and verify
   each SHA-256 against the lock; the encoder verifies them again when loading.
3. Load the private catalogue database binding and run:
   `python -m pipelines.catalog.embeddings --namespace dev --out artifacts/embeddings`.
   This adds embeddings to existing catalogue rows; it does not reimport or reseed.
4. Start catalogue with that directory and optional runtime available. For Docker,
   both the runtime dependencies and a read-only model mount must exist in the
   catalogue container. The standard 128 MiB lexical container is not a certified
   semantic allocation; budget and verify memory before using a model there.

No model download, embedding backfill, resource enlargement or evaluation is performed
by opening the website. Exact hybrid is sufficient at this catalogue size; the existing
ANN experiment remains separate.

## Separate desktop dashboard

`/dashboard` is an M1-served page linked from the storefront header. No charts,
metrics panel or analytics polling remain on the shopping page. The dashboard
authorizes the owned session before querying M1 storage or provider APIs. It
never replays shopping mutations or submits a purchase; direct first use can
create an empty session using the existing idempotent session endpoint.

The dashboard projects the existing owner APIs for Gold pipeline/order facts,
active Silver/Gold manifests, facet dictionaries, retrieval capabilities and
internal source receipts. The service token stays server-side. Readiness probes
target only configured service origins with bounded timeouts. At most two
analytics reads run together. No cross-service database access is introduced.

Charts distinguish current-session latency, today's namespace Gold activity,
dataset-wide physical file/row totals and the first 200 receipt journal entries.
Receipt observations are deduplicated by namespace/topic/partition/offset before
disposition or latency aggregation. Conflicting byte/event identities fail closed.
Journal observation and unique source-position counts are shown separately;
the resume cursor alone does not prove additional entries exist.
The last 60 saved turns form the response-time chart; the existing last-500
session summary supplies nearest-rank P50/P95. Receipt ingest-to-Gold P95 excludes
missing/recovery-bound/negative timings. Source positions are exclusive next
offsets from manifests, not broker-head lag. Attribute coverage counts come from
the canonical catalogue facet dictionary. No CPU/RAM, full-ledger audit or fault
qualification result is claimed. Unavailable sources remain null in exported
JSON and clearly unavailable in the UI. Refresh failures label old charts stale.

The standalone page has automatic/pause/manual refresh and snapshot export.
The original metrics API remains available for evaluation clients.

## Prototype limits

Synthetic browser IDs are development identities, not secure customer login. Bind to
loopback. Payments/inventory are simulated; prices and image links are historical.
Shipping, taxes, real money, account recovery and production authentication are outside
this prototype. Keep benchmark/fault flags off and preserve all data volumes.

Startup and shutdown: [PROTOTYPE.md](../../infra/PROTOTYPE.md). Current verification:
[shopping implementation record](../vichitr/shopping_implementation.md).
