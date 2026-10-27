# P6 durable conversation state

Authority: [playbook P6](../specs/10_JAINEEL_CODEX_PLAYBOOK.md#p6--durable-sessions-cart-versions-and-idempotency),
[common §§3–5/6.1/7/8 and Appendix A](../specs/02_COMMON_SPEC.md),
[personal brief J04](../specs/04_JAINEEL_VORA.md#j04--sessions-cart-and-fixed-workflow),
and [ownership](../OWNERSHIP.md). P7 workflow remains unimplemented.

## Implementation and semantics

- `services/conversation/database.py` applies checksum-verified, transactionally
  serialized M1 migrations to PostgreSQL 18. Windows/Linux line endings are
  normalized before hashing. Requests use at most ten concurrent connections
  per application state, two-second connection/lock/query bounds and UTC
  transactions. Migration DDL alone has a 60-second statement limit. Durability
  uses PostgreSQL defaults; no asynchronous commit or disabled fsync.
- `migrations/conversation/001_state.sql` defines sessions, carts, unique cart
  lines, durable turn outcomes and scoped operation keys. Composite keys and
  local foreign keys preserve namespaces and owners. Quantities, versions,
  nullable money, request hashes and quote/confirmation consistency are checked.
  `audit.sql` provides namespace-bound read-only reconciliation queries.
- `services/conversation/state.py` retains canonical business-input hashes and
  original responses with effects in the same transaction. Scope is
  `(namespace,user_id,operation,key)`; paths, SKU, quantity and expected version
  affect cart hashes. Transport IDs/headers do not. A retry returns the original
  snapshot even after later edits. Changed input returns 409
  `IDEMPOTENCY_CONFLICT`. Keys have no expiry or cleanup policy.
- Transaction advisory locks serialize a new idempotency key. Session/cart row
  locks serialize edits and coherent version/line reads. Distinct keys using an
  old version return 409 `CART_VERSION_CONFLICT`. A successful PUT sets the
  absolute quantity, increments the version once and appends one `ADD_TO_CART`
  fact, including for quantity zero and an absent-line removal. A repeated key
  creates no new version/event. The empty cart and at most 20 unique lines are
  supported. Display prices remain null; M1 does not invent catalogue facts.
- Cart edits atomically clear quote/version/confirmation references. P6 has no
  quote or confirmation creation API; the constraint/invalidation is groundwork
  for P7. Aggregate event versions belong to the session stream, independently
  of cart versions. Cart and turn events share that sequence and session key.
- `record_turn` persists a supplied validated outcome without implementing
  parsing/search/composition. `(namespace,request_id)` is unique across sessions
  and principals. Reusing it with changed business input conflicts, even with a
  new transport key; identical replay binds the new key to the existing outcome.
  Raw turn input is hashed, not stored in the turn table or emitted event.
  Fixed-mode outcomes with nonzero model-call counts are rejected.
- `app.py` exposes the P6 endpoints, safe common errors, strict input/header
  validation, metrics and context logs. A body cannot override `X-User-ID`.
  Foreign-principal resources return 403; a resource outside the namespace is
  absent (404). The synthetic user header is the existing local demo identity,
  not production authentication. P2's proposed header bindings remain pending
  provider/consumer review; no public DTO/OpenAPI/spec changed in P6.

## Shared handoffs remain incomplete

`SharedEvents` imports Vichitr's `build_event` and Aditya's `append_outbox`,
passes the caller's existing psycopg connection/transaction and never publishes
or commits it. Those packages currently contain only README files. Real cart
mutations therefore return 503 `DEPENDENCY_UNAVAILABLE` without committing an
effect; readiness fails. Durable session creation and existing cart reads can
operate independently; there is no canonical `SESSION_CREATED` event.

The following must be reviewed when providers arrive:

| Owner / consumer | Required handoff and review |
|---|---|
| Aditya / Jaineel | Public `append_outbox(tx,event)` entry point, psycopg caller-transaction binding, owner-supplied outbox DDL/template, pending indexes, readiness checks and relay. No outbox schema or relay was copied into M1. Apply the reviewed template as a new owned migration, then prove real append and rollback. |
| Vichitr / Jaineel | Public `build_event` entry point, canonical envelope/schema/cache readiness and conversation payload validation. Confirm how source_service and catalogue-linked metadata are supplied: common §6.1's signature names a RequestContext (§4), which has neither source_service nor dataset_revision, while §7 requires those envelope/metadata values. P6 does not silently extend the DTO or invent a dataset revision. Validate zero `quantity_after` for the documented removal operation. |
| All event producers / Vichitr | Common §7 requires UUID event correlation IDs; the existing P2 `RequestContext.correlation_id` accepts bounded printable identifiers. Review the HTTP-to-event validation policy. P6 preserves that DTO and never substitutes an invented correlation ID into an event. |
| Vichitr / Jaineel | `local_diagnostics` template/helper; it is not invented in P6. No diagnostic producer/model fallback is implemented here. |
| All consumers / Jaineel | P2 header bindings, namespace/principal rejection behavior, and explicit no-op PUT version/event behavior before real integration. |

The missing fields are a provider configuration/binding gap, not permission to
change a canonical signature. No real shared-event success is claimed until the
binding, metadata, DDL and registry readiness have been reviewed and tested.

`tests/conversation/doubles.py` is the only event/outbox capture implementation.
Its table is explicitly named `p6_test_event_capture`; it has no relay, Kafka,
registry or canonical event validation. `TurnOutcomeDouble` supplies storage
inputs and does not implement a workflow. The real app rejects stub bindings;
tests must select `mode="stub", purpose="contract_test"`. The subprocess test
server additionally requires `--test-double-events` and binds only to loopback.
Real HTTP turn execution remains disabled until P7 supplies canonical nested
provider validation. Quote and checkout return visible P7-unavailable errors.

## Repeat checks and manual checkpoint

Use an isolated PostgreSQL **18** database supplied by the database/infra owner.
No existing schema is reset. Tests create uniquely named `p6_test_<uuid>` schemas
and remove only their own schemas. The smoke retains a `p6_smoke_<uuid>` schema.
For native Windows PostgreSQL, keep its cluster outside OneDrive; the initial
synced-directory run encountered real query timeouts and is retained as failed
evidence. This host fallback is not a Docker/Compose/G0 deployment claim.

```powershell
uv sync --locked
# Set P6_TEST_DATABASE_URL locally to the isolated PostgreSQL 18 test database.
uv run --locked python -m pytest tests/conversation -q -ra --basetemp=artifacts/p6/manual-temp -o cache_dir=artifacts/p6/manual-cache
uv run --locked python benchmarks/manual/verify_p6.py
# Choose a fresh output directory for each first run.
uv run --locked python -m benchmarks.manual.p6_smoke --out artifacts/p6/manual-smoke
```

Without `P6_TEST_DATABASE_URL`, DB cases explicitly skip with `NOT_RUN` and the
verifier exits 4 with `INCOMPLETE`. An unreachable/configured or wrong-major
database fails; it never selects SQLite or an in-memory replacement. The full
verifier reruns P1–P5 regressions, contract/schema generation checks and Ruff,
then performs the scripted P6 checkpoint. Global provider contracts currently
return the expected exit 4; this is an incomplete gate, not a passing integration.

Inspect the smoke's `smoke.json` and `transcript.json` directly:

1. Session creation and identical key replay return the same session/cart IDs.
   The script captures returned IDs and uses them in later URLs.
2. Identical cart edit/key replay returns the same version/snapshot. Changed
   quantity under the same key returns 409 `IDEMPOTENCY_CONFLICT`; a fresh key
   with the old version returns 409 `CART_VERSION_CONFLICT`.
3. Another synthetic user receives 403. A new actual service process (different
   PID) reads the identical persisted snapshot and replays the original key.
4. A deliberate failure after a test event insert rolls back the cart change,
   event capture and operation key. This proves the local transaction boundary
   with a test double, not Aditya's real outbox.
5. If you control an isolated database process, restart **only that process with
   retained data**, then run the following against the same database URL:

```powershell
uv run --locked python -m benchmarks.manual.p6_smoke --out artifacts/p6/manual-smoke --resume
```

Inspect `database-restart.json`: the saved snapshot, original response and single
test event must survive. Do not restart a shared development database to perform
this optional check. Final milestone-specific evidence and actual counts are
recorded in [progress.md](progress.md#milestone-p6-durable-sessions-cart-and-idempotency).
