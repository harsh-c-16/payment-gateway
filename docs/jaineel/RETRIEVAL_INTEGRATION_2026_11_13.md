# Retrieval integration: 13 November 2026

The user requested inspection, fixes and integration of the existing retriever,
authorizing the cross-module changes below. No commit or push was requested.

## Findings and delivered behaviour

Lexical retrieval was connected. M2 also implemented vector search and hybrid
fusion, and shopping turns could request hybrid. The retained prototype lacked
the optional runtime, model files, product embeddings and model mount. New
browser sessions also selected lexical even when hybrid was available.

`infra.retrieval setup` now verifies/downloads the three checksum-locked files,
builds a separate hash-pinned semantic image and runs the existing resumable M2
backfill. Successful configuration is retained privately. Normal prototype
launches consume the semantic overlay, mount the model read-only and account for
the catalogue's 768 MiB limit. Core locks and evaluation profiles are unchanged.
ONNX inference uses one intra/inter-op thread.

Browser chat selects provisioned hybrid, retaining an explicit Keyword choice
across refreshes. New shopping API sessions without a requested mode select
available hybrid; follow-ups retain that mode. Result labels reflect executed
retrieval. Browsing/sorting/pagination and the original fixed-turn endpoint
retain lexical behaviour.

Backfill repairs missing vectors even if their metadata looks current. Semantic
search refuses missing/mixed-revision eligible vectors. M1 refuses mismatched
hit modes or text-based semantic responses without one query embedding and a
model revision. Hard filters, exclusions and purchase controls are preserved.

The retained database also lacked existing M1 migration 005. The normal M1
migrator added shopping context without a reset. Startup now checks that
prerequisite before starting APIs. Verification retains non-JSON failures too.

Changed implementation paths: `infra/{prototype,retrieval}.py`,
`infra/{retrieval.Dockerfile,compose.retrieval.yaml}`, `pipelines/catalog/embeddings.py`,
`services/catalog/{embedding,search}.py`,
`services/conversation/{shopping,workflow}.py`, and `services/conversation/web/store.js`.
Focused tests and the shopping/prototype documentation accompany them.

## Actual validation

Evidence is private/git-ignored under `artifacts/retrieval/`.

| Command/check | Result | Evidence |
|---|---|---|
| `python -m infra.retrieval download`; `python -m infra.retrieval setup` | SHA-256 verified; successful repeat backfill encoded zero unchanged rows | Model files, `embedding_manifest.json` |
| Read-only current-revision coverage | 19,998/19,998 listings; 19,920/19,920 active products | `coverage.json` |
| `pytest tests/conversation tests/pipelines/test_retrieval.py tests/pipelines/test_prototype.py -q --tb=short` with real isolated PostgreSQL schemas | 469 passed at initial checkpoint | `conversation-tests.xml` |
| `pytest tests/conversation/test_shopping_http.py tests/contracts -q --tb=short` after adding rejection cases | 141 passed; overlaps preceding tests | `contract-tests.xml` |
| Linux semantic image: `pytest tests/catalog/test_embeddings_live.py tests/catalog/test_vector_search_live.py tests/catalog/test_shopping_live.py tests/catalog/test_search_live.py tests/catalog/test_products_live.py -q --tb=short` | 72 passed with real locked encoder/PostgreSQL and explicit event captures | `catalog-tests.xml`, `catalog-test-output.log` |
| Final `pytest tests/pipelines/test_retrieval.py tests/pipelines/test_prototype.py -q` | 27 passed | `infra-tests-final.xml` |
| `node tests/conversation/storefront.test.cjs`; `node --check services/conversation/web/store.js` | Six controller tests and syntax passed; no visual-browser claim | Session output |
| Ruff lint/format over changed Python paths; `git diff --check` | PASS | Session output |
| `python -m services.conversation.database` with retained private bindings | Migrations 1-5 applied/verified | Session output |
| `PROJECTCTL_ADAPTER_MODULE=infra.prototype python -m projectctl env up --profile prototype-local` | Exit 0 | `artifacts/infra/prototype-local/checks/1e35cb18-ebbf-46b9-a455-2d2d137fa6d1/` |
| Same adapter, `python -m projectctl env verify --profile prototype-local` | Exit 0; 12 healthy containers with declared resources | `artifacts/infra/prototype-local/checks/84bbe1df-28df-4ed9-a07e-ab908270da62/` |
| Final `python -m infra.retrieval verify` | Real M1/M2 HTTP PASS | `verify-29e09849a865481f85ea10c4882f820e/{http,checks}.json` |

The live check exercised automatic hybrid, five white shirts below INR 1,000,
five disjoint more-options results, selected-product similarity with preserved
filters/exclusions, saved hybrid context, and wristwatch query inference at
revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. M1 reported zero generative
calls. No cart or purchase command was sent.

Initial failures were not accepted as passes. The first backfill command hit
the former 600-second Docker timeout; its retained job completed and retry
verified all vectors without re-encoding. Embedding jobs now allow 1,800 seconds.
Linux test collection initially lacked benchmark mounts
(`catalog-collection-errors.xml`). A subsequent process ended without a report
while implicit deployment encoders loaded in fixtures. The passing run cleared
`EMBEDDING_MODEL_DIR`: semantic fixtures explicitly load the real encoder,
while lexical fixtures retain their intended unprovisioned-model behaviour.
The first HTTP attempt exposed migration 005; passes followed its application.

## Handoff

The full prototype remains running at http://127.0.0.1:8001/. Reload the page;
chat selects Hybrid unless the shopper explicitly chooses Keyword. Repeatable
startup and verification are in [PROTOTYPE.md](../../infra/PROTOTYPE.md).
Products, inventory seeds, carts, orders and volumes were preserved. No live
generative provider, relevance study, benchmark, fault campaign or full
repository-suite result is claimed by this checkpoint.
