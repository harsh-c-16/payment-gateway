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

Docker Compose is now the default and required path for the P6 checkpoint.
`verify_p6.py` creates a dedicated PostgreSQL 18.6 container and named volume
through `benchmarks/manual/p6_docker.py`. A missing CLI, unavailable daemon or
wrong engine fails with retained `INCOMPLETE` evidence; there is no native
fallback, even if `P6_TEST_DATABASE_URL` already points to a native instance.
The earlier native Windows runs remain historical evidence only.

```powershell
uv sync --locked
docker info
docker compose version
uv run --locked python benchmarks/manual/verify_p6.py
```

The harness pins the observed official image digest
`postgres:18.6@sha256:edb0c08dc33befd0262ab3b5cf1c4f3f8cfd8b09e88c05b45adee29d6761ddb6`.
Its volume mounts at `/var/lib/postgresql`, following the
[official PostgreSQL 18 image layout](https://github.com/docker-library/docs/blob/master/postgres/README.md#pgdata).
Each run has a fresh `p6-<uuid>` project, loopback-only random host port, generated
test password, health check and named volume outside OneDrive. The DB test budget
is one CPU / 512 MiB, with 128 MiB shared memory and 128 PIDs. This is a test
fixture budget, not the full team's `local4c8g` measurement profile. The Python
runner and temporary service processes use the locked host environment; the
database runs in Docker. No team infra/Compose implementation is replaced.

The harness checks real server version and `fsync`, `synchronous_commit`, and
`full_page_writes`; all durability settings must be on. It runs the complete
P1–P6 verifier and scripted smoke, restarts only its own labeled container, checks
the same named volume and changed startup time, then replays the persisted cart
and original operation key. The inspected live host port is refreshed after
restart because Docker may remap an automatically allocated port. The child
environment and retained local connection file both receive the refreshed URL.
Containers/volumes remain available for inspection;
no global reset, prune or volume deletion is performed. Each test uses its own
`p6_test_<uuid>` schema and cleans only that schema; smoke state stays retained.

Raw evidence is under the printed `artifacts/p6-docker/<run>/` directory:
`docker-checks.json`, `docker-summary.json`, generated `compose.json`, and
`checkpoint/{checks.json,pytest.xml,smoke/}`. The generated Compose file and
`local-database.json` contain local test credentials; they remain ignored and
must not be committed. Command journals redact the generated password. A failed
or timed-out command retains available output and leaves the checkpoint incomplete.

The inner `--external-database` option is for the owning Docker harness to supply
its verified DB URL; it is never selected automatically. Direct pytest without
a DB still skips with `NOT_RUN`, and the inner verifier exits 4 without one.
Global provider contracts currently return expected exit 4: their gate stays
incomplete. GitHub's P6 job invokes the same default Docker entry point, including
the restart check. There is no second independently configured CI database.

If Docker Desktop is stopped on Windows, run `docker desktop start`, select
`docker context use desktop-linux` when that is the intended local engine, and
repeat `docker info`. The follow-up found Desktop already running and the engine
healthy; no daemon reset, WSL reset or speculative machine setting change was
needed. Previous daemon-start failure and native results are not rewritten.

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
5. Inspect the Docker restart evidence: the same container/volume remains, its
   startup time changes, all durability settings stay on, and
   `checkpoint/smoke/database-restart.json` records three passing persistence
   checks. To repeat the smoke against a retained Docker run, substitute its
   actual printed path for `RUN`:

```powershell
$env:P6_TEST_DATABASE_URL = (Get-Content artifacts/p6-docker/RUN/local-database.json | ConvertFrom-Json).url
uv run --locked python -m benchmarks.manual.p6_smoke --out artifacts/p6-docker/RUN/checkpoint/smoke --resume
docker compose --file artifacts/p6-docker/RUN/compose.json ps
# Stop only this test project when finished; retained volume/data are preserved.
docker compose --file artifacts/p6-docker/RUN/compose.json stop postgres
```

The saved snapshot, original response and single test event must survive. Do not
restart a shared development database. Actual counts and evidence paths are in
[progress.md](progress.md#milestone-p6-durable-sessions-cart-and-idempotency).
