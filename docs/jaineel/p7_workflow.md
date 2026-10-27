# P7 fixed workflow checkpoint

Authority: [playbook P7](../specs/10_JAINEEL_CODEX_PLAYBOOK.md#p7--deterministic-search-quote-and-checkout),
[common §§3–6.2 and Appendices A/B](../specs/02_COMMON_SPEC.md),
[dataset §5](../specs/08_DATASET_PROFILE_AND_RULES.md), and
[evaluation runbook §§4/6](../specs/09_EVALUATION_RUNBOOK.md).

P7 supplies deterministic extraction/composition, one lexical search, explicit
quote/checkout delegation, and a durable M1 command journal. It does not implement
catalogue ranking, stock/payment rules, a saga, or event publication. P8 is not
implemented. Real G3 and the shared event gate remain incomplete.

## Runtime and safety semantics

Run `uv sync --locked`, configure `CONVERSATION_DATABASE_URL`,
`CATALOG_BASE_URL`, `ORDERS_BASE_URL`, `ASSISTANT_MODE=fixed` and
`ALLOW_INTENT_LLM=false`, then:

```powershell
uv run --locked python -m services.conversation.database
uv run --locked python -m uvicorn services.conversation.app:create_app --factory --host 127.0.0.1 --port 8001
```

Migration 001 stays byte-for-byte unchanged. Migration 002 adds M1-only quote
payloads, confirmation bindings and workflow commands. Both checksums are
verified; migration execution is explicit. Real mode requires owner OpenAPI
contracts, real HTTP, and the real shared event builder/outbox. There is no
automatic fixture fallback. Readiness fails while these handoffs are absent.

The parser consumes `GET /v1/catalog/facets` on each search turn; it never caches
price, stock or search results. There is no fixture/scenario lookup in production.
Rules retain the original text for lexical retrieval and recognize dictionary
category/brand/colour/material values, conservative apparel size aliases and
exact decimal rupee bounds. `under`/`below` are exclusive; `at most`/`up to` are
inclusive. Allowed but unobserved apparel sizes are still forwarded unchanged.
Unknown named attributes, ambiguous sizes/categories, negation/disjunction that
cannot be represented, and unsupported explicit attributes clarify. Occasion
remains semantic query text. This is a bounded English grammar, not a general
natural-language understanding claim.

A search turn has a monotonic 3-second deadline starting before M1 turn storage
and passes the remaining deadline through dictionary retrieval and its single
search. The HTTP client also enforces its existing 2-second request limit.
`timings_ms` records parse (including dictionary fetch), search, compose and
total; `llm` is null and calls are zero. Store/commit overhead is outside the
returned workflow timing sample. Database connection/lock failure is visible;
this is not a hard real-time response guarantee under storage failure.

Templates display provider fields verbatim as data. Descriptions cannot select
tools or change prices. No text turn purchases. Cart, quote, checkout and order
status are explicit controls and have no model integration. Quote totals come
directly from `Quote.total_amount_minor`; M1 does not calculate the authoritative
total or decide whether stock is sellable. HTTP 202 is acceptance, and final
status comes only from Orders snapshots/SSE.

Quote requests check principal/cart version, persist their provider request and
stable key before calling M2, then bind the returned quote only if that version
is still current. A cart edit clears the quote/confirmation. Checkout requires
`confirmed=true`, the bound quote/version, and an unused confirmation ID (or a
retry of its original binding). Confirmation IDs cannot move to another quote.

Checkout saves its downstream identity before calling Orders. Same-key replay
returns the stored response; changed business input conflicts. A second key for
the same quote uses the same provider key and resolves every pending journal
alias. No response loss or timeout is interpreted as cancellation. Pending
checkout blocks cart edits/new quotes with `409 ILLEGAL_STATE` until the original
operation is recovered. Definitive provider business rejection is saved;
unavailable/unknown outcomes remain pending. Recovery retries must continue
using the saved command; there is no background M1 saga or payment operation.

## Contract issues requiring owner/consumer review

- Common §5 defines M1 turns as `{request_id,text,mode}` only, while §6.2 requires
  structured search to bypass extraction. The canonical public schema stays
  unchanged. `FixedWorkflow.structured_search` provides the local control
  adapter, and the documented HTTP structured control is M2 `POST /v1/search`.
  Jaineel/Harsh must review any future public M1 structured field or route.
- Harsh's canonical `FacetDictionary`, search/quote schemas and versioned data
  are absent. Tests use explicitly provisional provider schemas inherited from
  P2. Harsh must review dictionary values, normalized brand-key versus displayed
  hit-brand binding, hard path filtering, and returned revision equality.
- Aditya must review durable acceptance/replay, repeated-quote deduplication,
  unchanged confirmation bodies and the relative `/v1/orders/{id}` status URL
  used by the existing consumer examples. M1 fails closed on an unexpected URL;
  it never follows a supplied arbitrary address.
- Aditya/Vichitr must provide the existing shared builder/append bindings and
  caller-transaction DDL from the [P6 handoff](p6_persistence.md). No second
  outbox, direct Kafka publish or teammate module was added.

## Repeatable verification

Use an isolated Docker PostgreSQL 18 database. If needed, provision it with the
existing P6 Docker harness first. Its generated `local-database.json` is ignored
and contains local test credentials; do not commit it. Replace the example path
with the artifact directory produced on your machine.

```powershell
.venv/Scripts/python.exe benchmarks/manual/verify_p7.py --database-file artifacts/p6-docker/checkpoint-20261027-final/local-database.json --out artifacts/p7/my-checkpoint
```

The verifier checks that the supplied URL matches a running loopback Docker
PostgreSQL 18 with durability on. Every database test creates/removes only its
own schema. It runs the conversation and P1–P6 regression suites, schema/contract
generation, lint/format, protected-path/whitespace checks, and the API smoke.
Missing providers keep `contracts check --all` at its expected exit 4. Missing
Docker/database fails, and skipped tests cannot produce a complete checkpoint.

```powershell
$env:P6_TEST_DATABASE_URL = (Get-Content artifacts/p6-docker/checkpoint-20261027-final/local-database.json | ConvertFrom-Json).url
.venv/Scripts/python.exe -m benchmarks.manual.p7_smoke --test-double-providers --confirm-checkout --out artifacts/p7/my-smoke
```

This uses the real M1 app/PostgreSQL with explicit HTTP/event capture doubles.
It captures session/cart/SKU/quote/order IDs from responses, proves stale quote
rejection, injects response loss, and compares repeated checkout references.
Inspect `smoke.json` and `http.json`; check the changed quote price/total against
the provider response and confirm pending acceptance is not final confirmation.

For real providers, after owner readiness is complete, run:

```powershell
.venv/Scripts/python.exe -m benchmarks.manual.p7_smoke --base-url http://127.0.0.1:8001 --query clothing --out artifacts/p7/real-read-and-quote
```

That command stops after quoting. `--confirm-checkout` explicitly submits the
simulated quote returned by the smoke client. Use a dedicated test namespace
and simulated user. Inspect the Orders status URL through the public API/SSE;
verify confirmed/declined results only when the backend reports them. Test an
Orders outage and retry the original checkout body/key after recovery; verify
one order ID. No mock is loaded in this mode. This real procedure is NOT_RUN
until provider handoffs exist; full G3 reconciliation belongs to P8.

The verifier preserves exact commands/outputs in `checks.json`, JUnit in
`pytest.xml`, 60 fixed cases in `assistant_turns.jsonl`/`tests.jsonl`, Docker facts
in `database.json`, and the smoke transcript. These are correctness evidence,
not performance results. Human scenario review, live assist, stock/ledger
reconciliation, Kafka publication and real G1/G3 remain NOT_RUN.
