# Prototype integration review — 11 November 2026

The user delegated Jaineel's design and consumer-review decisions and authorized
fixes and a normal push on `jaineel/prototype-demo`. This records that delegated
review; it does not impersonate teammates or certify human relevance judgements.
The checkpoint is a working professor-facing prototype, with full evaluation
qualification tracked separately.

Aditya's PR #19 is present at `3be2916`. Fresh boundary probes pass all eight
cases with explicitly labelled ASGI/SQL doubles. Real PostgreSQL/HTTP checks also
exercise ownership, service tokens, quote expiry and retries. Repeatable setup
successfully adopts the retained prototype schemas, adds the new Orders/Payments
migrations and applies nothing on a second run. Historical migrations are intact.

The payment implementation follows common spec §9.2: durable PENDING, minimum
100-ms completion delay, one immutable attempt after response loss, DECLINED
without retry, and another attempt only after RETRYABLE_PROVIDER_FAILURE while
the hold is valid. Stable scenario/seed headers are accepted only with both
benchmark flags and an isolated namespace. New orders and worker events retain
the original context. The simulator's independent 100-attempt database test
verifies 95 successes, five declines and 95 debits.

Review found a reversal race when no payment guard was initially visible. A
concurrent first authorization could create and debit an attempt before reversal's
upsert; the old early return incorrectly reported zero without reversing it.
The new regression reproduced this. Reversal now creates/locks the common guard,
then reads all attempts and takes its timestamp from the database after locking.
The regression requires the actual debit and matching reversal, not a clamped
provider total.

M1 repeatedly parsed owner OpenAPI YAML with the Python safe loader. Real demo
searches intermittently exceeded the unchanged two-second provider/three-second
turn budgets. The owned reader now uses PyYAML's safe C loader when available,
with the safe Python fallback and unchanged validation/reference rules. Existing
contract drift, strict money and local-reference checks pass. A fresh real CLI
search subsequently returned products and declined confirmation without purchase.
These diagnostic observations are not an official optimization comparison.

The P5 verifier also crashed while decoding timeout output that was already a
string. It now retains either text or byte stdout/stderr, records failure and
continues the remaining checks. Its 240-second limit and assertions are unchanged;
regressions cover text, bytes and absent partial output.

## Decisions for Harsh and Vichitr's consumed work

- Preserve the original CSV, `flipkart-v1`, the existing dataset revision and the
  distinction between exact-byte evaluation pins and LF dictionary identity.
  Do not reimport, reseed or reset the retained demo to test this payment change.
- Accept the combined seed mapping: exact active catalogue, Inventory and stock
  projection keys; namespace-wide unpublished Inventory outbox count; and one
  original seed run ID. Use the existing restricted SELECT-only readers with
  repeatable-read snapshots. Counts alone, mixed run IDs and conflicting owner
  callback evidence fail. The real restricted-role regression verifies this.
- Use signed ledger entries as the independent money input. Keep original event
  identities and source receipts; a terminal API result does not establish Gold
  visibility. The real smoke separately queried active Gold for the same order.
- Keep Vichitr's existing prototype deployment, retained volumes and fixed-mode
  CLI. Benchmark/fault flags remain disabled for presentation. No new frontend,
  model provider, resource profile or alternate pipeline is introduced.
- Keep formal owner-review receipts and human labels distinct from this automated
  consumer review. No APPROVED record is manufactured in a teammate's name. Full
  benchmark qualification still needs the concrete provider bindings, acknowledged
  fault trials, reviewed controls and actual paired measurements. They are not
  required to describe this checkpoint truthfully as a working prototype.

## Presentation and evidence

Use [the demo runbook](PROTOTYPE_DEMO.md). Show search, product choice, quantity,
the authoritative quote, exact `CONFIRM <quote-id>`, asynchronous order states,
and the resulting backend status. Then show resume retaining the same order and
a separate session where declining confirmation submits nothing. Explain that
prices are historical and stock/payments are simulated; fixed mode calls no LLM.

This review's real order `0f2f9566-0001-4f4a-a331-d72634e9d152` is CONFIRMED,
its reservation COMMITTED and its signed debit INR 549.00. The same order appears
in active Gold (query generation 221; row publication generation 213). Replay
returned the original order; foreign status/SSE reads returned 404; tokenless
ledger audit returned 401. The stored payment completed after its 100-ms due time
and retained the checkout run identity. The smoke uses real providers; scripted
confirmation is explicitly a test fixture, not human-review evidence.

Raw logs, JUnit, failed attempts, scripts and audit JSON remain under
`artifacts/jaineel-m3-review-20261111/` and are excluded from Git. Early cold-search
failures and mistakes in the disposable smoke script's route/field assumptions
are retained; the corrected script reads the canonical endpoints/Gold fields.
Exact final commands, outcomes, cleanup and push are recorded in
[progress.md](progress.md). Full B0/matrix and hosted CI remain separately unclaimed.
