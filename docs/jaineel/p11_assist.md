# P11 optional intent fallback

The user explicitly authorized this isolated P11 implementation while leaving real
DE gates incomplete: "Implement P11 now; keep real gates incomplete." This is an
exception to P11's sequencing prerequisite, not evidence that G4/G5/G6 passed.
The binding policy remains [common §6.2](../specs/02_COMMON_SPEC.md#62-m1-and-m2)
and [J05](../specs/04_JAINEEL_VORA.md#j05--optional-single-call-intent-fallback-no-planner-loop).

Fixed remains the default and calls no model. A request must select `mode=assist`,
the service must select `ASSISTANT_MODE=assist`, and `ALLOW_INTENT_LLM=true` must
also be explicit before the optional path can run. Deterministic parsing always
runs first. Missing provider configuration returns clarification with zero calls.
Structured search/cart/quote/checkout/status controls make zero model calls.

## Scope and safety

Conservative v1 eligibility is an unresolved category with an explicit supported
apparel size, such as `apparel size medium colour blue material cotton under
500 rupees`. Unsupported currencies/attributes, conflicting filters, explicit
unknown category cues and purchase text stay clarification. No model is used to
invent missing catalogue attributes or broadly resolve unsupported filters.

The provider performs one POST with strict JSON Schema, no SDK, no retry,
no redirect, no tools and no generated response composition. Its request format
follows the [official OpenAI Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat).
A dated model snapshot, prompt revision/hash, output-schema hash and dictionary
version are recorded. No model is chosen implicitly. Returned JSON is validated
locally, and the existing canonical search-request contract still validates the
downstream request. All explicitly parsed hard constraints remain exact. Model
output cannot supply prices, stock, tool actions, quotes or confirmation fields.

The maximum model timeout is 1,500 ms, reduced to the remaining turn budget.
The 3,000-ms monotonic turn budget includes the initial state/dictionary work;
the one search receives its remaining time. The search POST has no automatic
retry. Invalid output, refusal, timeout or provider error returns clarification
and a finite private diagnostic. Backend/deadline failures remain visible; a late
result is not returned as a successful recommendation. Scheduler and database
failure delays are retained in actual timings; this is not a measured latency SLO.

Only user text and its already parsed intent enter the model request. Product
titles/descriptions arrive after intent extraction and never enter a model call.
Responses are existing deterministic templates using provider facts. A purchase
still requires explicit cart/quote/checkout controls and quote/cart-version-bound
confirmation; optional intent extraction does not alter them.

## Storage and configuration

Migration `003_intent_diagnostics.sql` adds a private `turns.intent_diagnostic`
column and `intent_attempts` audit table in M1's own database. No provider database
or public DTO changes. The existing ten-connection budget is nine ordinary slots
plus one reserved audit slot, preventing a response transaction from consuming all
slots needed to record its attempt.

An attempt reservation commits before provider I/O and records namespace, run,
session, user, request identity/hash and frozen settings. Its diagnostic preserves
actual returned usage or null. It survives a later response/outbox rollback.
A retry of that logical turn never reissues a model request; if the original turn
response was not committed, it returns clarification with `MODEL_PREVIOUS_ATTEMPT`.
The historical budget remains spent, with no new model latency sample or counter
increment. A process crash after reservation may leave provider execution unknown;
the reservation is never treated as proof of usage or successful inference.
Normal completed-turn retries replay the exact durable response.

Private diagnostics retain actual model duration, provider/model/prompt/schema
provenance, usage and failure code, with cost null. No key, raw prompt/provider
exception or raw model completion is stored in diagnostics. Usage absent from the
provider remains null. Old turns retain null historical diagnostics. Metrics use
finite labels for calls, durations, clarifications and turn timing; identities and
usage stay in the private namespace-scoped audit records.

To run after the real event/outbox and canonical catalogue/Orders handoffs exist:

```powershell
uv sync --locked
# Set CONVERSATION_DATABASE_URL privately for the owned M1 database.
.venv/Scripts/python.exe -m services.conversation.database
$env:ASSISTANT_MODE = 'assist'
$env:ALLOW_INTENT_LLM = 'true'
# Set INTENT_LLM_MODEL to an actually reviewed dated snapshot supported by the API.
# Set OPENAI_API_KEY privately; do not print, paste, log or commit its value.
.venv/Scripts/python.exe -m uvicorn services.conversation.app:create_app --factory --host 127.0.0.1 --port 8001
```

Use the existing session/turn APIs, preserving request IDs and idempotency keys.
`TurnRequest.mode` must be `assist` for an eligible fallback. A fixed request still
makes zero calls even when assist is enabled globally. An absent key/model is an
unavailable optional provider, not a reason to load a test double. There is no
automatic `.env` loading. The API key is not needed for the local verifier.

## Reproducible checks and manual review

```powershell
.venv/Scripts/python.exe -m benchmarks.manual.verify_p11 --out artifacts/p11/new-check --database-file artifacts/p1-p7-audit/20261027-audit/verifier-p6/local-database.json
```

Use the actual ignored Docker connection record for your machine and a new output
directory. The verifier reads that connection privately, checks PostgreSQL 18 and
durability, and uses fresh test schemas. It strips live model credentials/config
from the child environment and registers no real-provider replacement. It retains
commands, exits, stdout/stderr, JUnit, raw 60+60 scenario traces, a six-slot F1
diagnostic, frozen fixture byte hash and `evidence-index.json`. A shorter
`--focused` run executes all M1 tests and the independent assistant-evaluation tests.
Existing database containers/volumes and unrelated working data are preserved.

The same authored 60 scenarios and synthetic backend are exercised in fixed and
assist modes. All original six slot labels remain intact. The fixture is pinned
by exact bytes for test reproduction; its **human review/final label freeze is
NOT_RUN**. Do not relabel it as reviewed. Current v1 eligibility selects none of
those 60 texts; separate additional cases exercise genuine spy attempts, malformed
output, refusals, HTTP errors/redirects, timeout, constraint changes, missing usage,
concurrent replay, rollback and product-text instructions. Synthetic timing/F1 is
diagnostic only. Live quality, latency, tokens and cost remain NOT_RUN/null.

Manual checks after providers and human review are available:

1. Submit supported explicit search in fixed and assist; verify rules source,
   zero model calls and no model latency sample. Use structured purchase/status
   controls and inspect their unchanged confirmation/idempotency behavior.
2. Submit the eligible text above in assist; verify at most one attempt, protected
   size/colour/material/price, one search, and authoritative returned product facts.
3. Use the explicit spies/HTTP doubles for invalid output, timeout, refusal and
   malicious extra fields. Inspect the diagnostic, attempted-call count, actual
   remaining timeout and absence of a repair/second call. Do not emulate a live
   integration pass with these doubles.
4. Replay the same request under the same and a new transport key. Verify one
   logical effect and one attempt reservation. In the isolated rollback test,
   verify a later event failure preserves the attempt and prevents model reissue.
5. Compare `assistant_comparison.json` with raw JUnit traces. Read recommendation,
   correct-no-result, correct/unnecessary clarification and dependency counts
   separately; trace per-slot FP/FN, sample counts and nearest-rank quantiles.
6. Have a human review all 60 scenarios and retain the approved fixture hash before
   claiming final quality. Run a live evaluation only with explicit credentials,
   frozen settings and real providers; retain missing usage/cost as null.

Harsh's canonical catalogue/dictionary/quote/search, Aditya's real transaction/
outbox/audits and Vichitr's infrastructure/event/analytics handoffs still block real
DE integration/performance. Optional P11 code and local spy correctness do not
complete those gates. No subsequent milestone is implemented.
