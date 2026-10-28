# P2 contract handoff

Jaineel owns the conversation contract and consumer adapters. This is a **stub
verified consumer checkpoint**, pending canonical provider contracts and review.
The authority remains [common §§2–6/Appendix A](../specs/02_COMMON_SPEC.md),
[the personal brief J01](../specs/04_JAINEEL_VORA.md), and
[P2](../specs/10_JAINEEL_CODEX_PLAYBOOK.md#p2--conversation-contracts-and-provider-stubs).

## Delivered interfaces

- [Conversation OpenAPI](../../contracts/http/conversation.yaml): all six M1
  operations, version/conflict/confirmation inputs, common errors, health/metrics
  contract declarations. `python -m projectctl.conversation_contract --check`
  checks the generated file against the owned models and generator. These are
  declarations; no service, persistence, workflow, model or outbox runs in P2.
- [Conversation DTOs](../../shared/contracts/conversation.py) and
  [neutral context/errors](../../shared/contracts/common.py): strict integer
  quantities/money/versions, UUID resource/request IDs, UTC timestamps, nullable
  display prices, unique cart lines, explicit Boolean confirmation. Empty carts
  are allowed; nonempty quote/order line bounds belong to their provider.
- [Consumer clients](../../services/conversation/clients.py): catalogue
  search/product/facets/quote; Orders create/status/SSE; analytics active manifests,
  Gold, receipts, quarantine and replay inspection/requests. The low-level endpoint
  registry also includes internal quote lookup and price-update test interfaces.
  [The registry/checker](../../projectctl/contract_checks.py) includes all common
  §5 participant endpoints, health/metrics, shared-library and schema handoffs.
- [Synthetic wire pairs](../../contracts/fixtures/p2/pairs.json), with schemas
  and doubles only in [tests/contracts](../../tests/contracts/). These are small
  fictional contract examples, not a catalogue substitute or dataset profile.

No catalogue, quote, transaction or event DTO is published by this milestone.
`TurnResponse.intent/products` hold opaque provider JSON at the Python boundary;
their OpenAPI schemas reference Harsh's external `ShoppingIntent`/`ProductHit`.
P6/P7 must validate nested JSON against the canonical schema before serving it.
The quote and checkout responses also reference their provider-owned schemas.

## Review required before G0 or real compatibility claims

| Owner/consumer | Frozen requirement consumed | Missing or provisional binding to review |
|---|---|---|
| All owners | `X-Correlation-ID`, `X-Run-ID`, `X-User-ID`; RequestContext fields | Proposed headers `X-Namespace`, `X-Request-ID`, nullable `X-Session-ID`, optional `X-Trace-ID`. Common §2 does not name these bindings. Request UUIDs use lowercase canonical text. Header values are bounded printable ASCII; idempotency keys allow spaces and remain 1–128 characters. |
| Harsh; M1/Orders consumers | Common Product/ProductHit/Search/Quote/FacetDictionary fields, nullability, INR minor units, 60-second quote | `contracts/http/catalog.yaml`, `shared/contracts/catalog.py`, frozen dictionaries/manifests and review of all catalogue examples. `path_prefixes` is provisionally a list of segment arrays; coverage maps are opaque pending schema. Unknown stock/facets stay null. |
| Aditya; M1/harness consumers | Orders 202 acceptance, common state names, versioned snapshots and SSE | `contracts/http/transactions.yaml`, `shared/contracts/transactions.py`. Proposed SSE `data` is an OrderSnapshot and `id` is its decimal order_version; confirm schema name/event framing. Reconnect explicitly supplies Last-Event-ID; duplicate/older updates are suppressed. Internal service-token binding is provisionally `Authorization: Bearer <token>`. |
| Vichitr; harness consumers | Active DatasetManifest, Gold wrapper, receipts/quarantine/replay endpoints | `contracts/http/analytics.yaml`, analytics/event DTOs and schema/transport/diagnostic handoffs. Common §5 does not specify receipt/quarantine page wrapper names or item schema: test-only `receipts`/`records` plus `next_cursor` require review, as do generation/coverage representations. No production wrapper is invented. |
| Jaineel; M1 consumers | Turn timing names and zero model calls when unexecuted | Proposed `timings_ms.llm=null` when no call ran; common §6.2 says no model-latency sample but does not specify its JSON representation. `proposed_action` shape is also unspecified; it remains opaque, nullable JSON with no execution semantics. |

These notes record underspecified bindings, not approved contract changes. No
canonical spec was edited. A conflicting owner schema makes compatibility checks
fail and requires provider/consumer review; clients never rename fields or coerce
money to make a response pass.

The schema reader supports OpenAPI 3.1 and local Draft 2020-12 references under
`contracts/`. Missing files, unsupported dialects or unresolved references remain
visible dependency failures. When provider files arrive, `contracts check --all`
automatically validates these examples against their request/response schemas.
An intentionally changed provider schema is tested to fail this compatibility check.
Other formats need an explicit reviewed binding; they are never guessed.

## Transport and failure behavior

`TransportConfig(mode="real", purpose="integration" or "benchmark")` creates a
real HTTPX transport, disables environment proxy inheritance/redirects and rejects
injected transports or provisional schemas. Successful JSON requires a canonical
provider schema. There is no fixture read or mock fallback in production modules.

Tests must explicitly pass `mode="stub", purpose="contract_test"`, a test
transport and provisional test schemas. The configuration rejects stub mode for
integration/benchmark use. Keep the benchmark adapter on this real configuration
when it is implemented in P4; no benchmark execution is implemented here.

The default operation budget is 2 seconds, including request/response transfer and
GET retries; a supplied monotonic absolute deadline can only shorten it. GETs make
at most two retries with 100/300-ms backoff plus seeded jitter. `Retry-After` is a
lower bound; an operation fails visibly when that delay cannot fit. Mutations have
zero automatic retries by default. Explicit opt-in retries reuse the snapshotted
body, context and key. A transport timeout/lost response exposes
`DependencyUnavailable.outcome_unknown`; callers must inspect/retry the same
operation identity, never infer cancellation. HTTP 409/404/503 and protocol errors
remain distinct. JSON buffers are capped at 2 MiB; SSE frames at 64 KiB, with bounded
observation time and explicit reconnect cursors. These bounds are consumer limits,
not measured provider performance.

## Manual checkpoint (PowerShell, repository root)

1. Run `uv sync --locked`, then use `uv run --locked python` or activate `.venv`
   and verify Python 3.11. Run `python -m pytest tests/contracts -q` and
   `python -m projectctl.conversation_contract --check`; expect exit 0.
2. Run `python benchmarks/manual/verify_p2.py`. Open the printed evidence directory.
   Expect every expected outcome to match, including `contracts check --all` exit
   **4** for the currently absent provider handoffs. Read `checks.json` and
   `pytest.xml`; collector exit 0 is an offline/stub checkpoint result.
3. Inspect `request-response.jsonl`: one wire pair per fixture scenario across
   all three clients and SSE. Verify integer `39900` authoritative quote total
   despite display price `37900`, explicit null facets/stock, context headers,
   idempotency keys, namespace queries and versioned SSE data. Internal tokens
   are omitted from evidence.
4. Inspect `negative-checks.json`: `returned_cout` and string money must both
   have `rejected=true`. Inspect `real-stopped-provider.json`: real transport
   observes a dependency failure with no fixture fallback. To repeat only that
   check: `python -m pytest tests/contracts/test_clients.py::test_real_mode_stopped_provider_never_returns_fixture -q`.
5. Run `python -m projectctl contracts check --all`; immediately inspect
   `$LASTEXITCODE` (currently 4). Its JSON reasons and saved summary list each
   missing owner/path/endpoint. Send the examples and binding table above for
   Harsh/Aditya/Vichitr review, then repeat after their canonical files merge.
   Full G0 still needs real environment smoke, dataset/profile and frozen locks.

Stop at P2. Fixtures/oracles for P3, durable M1 state for P6, workflow for P7,
and real integration/benchmarks for later milestones remain unimplemented.
