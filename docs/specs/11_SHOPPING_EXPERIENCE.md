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

- Browse available products, search keywords, filter category/maximum INR price,
  sort by price and move through pages.
- Open details, view source image links and recorded attributes, and add products
  to the cart. Unreachable images use a local placeholder; ingestion downloads none.
- Describe a product in chat. A vague gift request asks what product is wanted.
  Replies preserve the budget and explicit constraints. Try `I need a gift`, then
  `shirts under 1000 rupees`, `only blue ones`, and `show more options`.
- `More options` excludes previously shown SKUs. `More like the second one` or the
  detail view's `Find similar` uses the selected product as the search reference.
  `Cheaper` uses a price below the selected or cheapest shown product. Hard filters
  remain in force; no matches never silently removes them.
- Explicitly remove a filter with `any colour`, `any brand` or `no budget limit`.
  A new product subject starts a new search; `New search: watches` resets filters.
- Update cart quantities, request an authoritative quote, inspect its amount and
  expiry, check confirmation and press **Confirm simulated purchase**. Chat text
  cannot create an order. Closing the dialog does not purchase anything.
- Refresh resumes the same browser identity, session, cart and saved order. An
  unknown mutation result retains its original request and idempotency key for retry.
  Checkout polls the existing Orders service and never buys again to resolve uncertainty.

The default assistant is deterministic and makes zero generative calls. It handles
the supported shopping refinements; it is not a general-purpose conversational model.
Unsupported, negated or ambiguous hard constraints ask for clarification. The
existing optional intent fallback remains available through the original workflow.

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
| `POST /v1/sessions/{session_id}/shopping-turns` | Contextual shopping dialogue |
| `GET /v1/store/orders/{order_id}` | Existing owned order status |

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

The prepared Windows prototype currently has no provisioned model. To provision on
a machine with sufficient memory, use the existing M2 tools:

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

## Prototype limits

Synthetic browser IDs are development identities, not secure customer login. Bind to
loopback. Payments/inventory are simulated; prices and image links are historical.
Shipping, taxes, real money, account recovery and production authentication are outside
this prototype. Keep benchmark/fault flags off and preserve all data volumes.

Startup and shutdown: [PROTOTYPE.md](../../infra/PROTOTYPE.md). Current verification:
[shopping implementation record](../vichitr/shopping_implementation.md).
