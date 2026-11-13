# Conversation service (M1)

The local shopping website is served at `/`, using this service's existing APIs
and the additive [shopping contract](../../contracts/http/shopping.yaml).
See [shopping behaviour](../../docs/specs/11_SHOPPING_EXPERIENCE.md). Run the
repeatable migration below before serving; it includes saved shopping context.

Owner: Jaineel Vora (B24CM1080). Authority:
[personal brief](../../docs/specs/04_JAINEEL_VORA.md),
[common specification](../../docs/specs/02_COMMON_SPEC.md), and
[conversation OpenAPI](../../contracts/http/conversation.yaml).

P2 supplies the contract, owned DTOs and consumer HTTP/SSE adapters.
Provider schemas remain external, with provisional examples/doubles restricted to
fixtures/tests. Real mode uses real HTTP and cannot fall back to those examples.
P6 adds PostgreSQL 18 sessions, cart mutations, durable request outcomes and
version/idempotency enforcement. Run the owned migration explicitly, then serve:

```powershell
uv sync --locked
# Set CONVERSATION_DATABASE_URL to the owner-supplied conversation database.
uv run --locked python -m services.conversation.database
uv run --locked python -m uvicorn services.conversation.app:create_app --factory --host 127.0.0.1 --port 8001
```

There is no default database and no automatic migration at service startup.
Session creation emits no invented event. Cart/turn events require the real
shared builder and transaction-local outbox; missing/invalid schema cache or
dataset configuration causes HTTP 503 and failed readiness. Tests explicitly
select test event/outbox capture, using real PostgreSQL. P7 supplies the
fixed turn/search, quote and checkout workflow; missing owner schemas/providers
remain visible failures. No generative provider or implicit purchase is enabled.

See [P7 workflow and manual replay](../../docs/jaineel/p7_workflow.md) for
confirmation binding, response-loss recovery, exact checks and provider reviews.

See [P6 persistence handoff](../../docs/jaineel/p6_persistence.md) for exact
semantics, checks, schema ownership, manual smoke and outstanding reviews.

P6 verification now starts its own Docker Compose PostgreSQL 18.6 database:
`uv run --locked python benchmarks/manual/verify_p6.py`. Docker failures remain
visible; it never falls back to a native database. The generated project and
named volume are retained under the printed Docker evidence directory for
inspection. Shared event/outbox dependencies are still explicit test doubles.

Run `python -m pytest tests/contracts -q` and
`python benchmarks/manual/verify_p2.py` from repository root.
See [P2 handoffs and manual checks](../../docs/jaineel/p2_contracts.md) for usage,
deadline/retry policy, unresolved bindings and evidence interpretation.

P11 adds an opt-in, single-attempt intent adapter. The default remains
`ASSISTANT_MODE=fixed`, `ALLOW_INTENT_LLM=false`, with zero model calls.
Apply owned migration 003 before serving the updated code. It adds private turn
diagnostics and durable attempt reservations; old usage remains null. The existing
API connection budget reserves one slot for intent audit. Configure
`CONVERSATION_MAX_CONNECTIONS` (integer 2–10; default operational cap 10).
The frozen example sets **3 API connections, including audit, plus 1 separately
composed relay connection** to fit the profile's total of four. Count all API
processes and relay connections together; more processes need a reviewed split.
See [P11 configuration and verification](../../docs/jaineel/p11_assist.md) for
explicit enablement, dated model/prompt settings, attempt-spy tests and limitations.
Required real DE gates and live quality remain incomplete; no test provider is
loaded automatically in real mode.

Roadmap Prompt 2 installs the shared outbox and diagnostic templates through
forward migration **004**; migrations 001–003 remain unchanged. Apply it with
the migration command above in the conversation database only. Before readiness,
mount Vichitr's verified schema mapping and bind the approved catalogue revision:

```powershell
$env:EVENT_SCHEMA_CACHE_PATH = 'artifacts/infra/streaming-local/registry-manifest.json'
$env:CATALOG_DATASET_REVISION = 'flipkart-v1-3a401f32ca99379f8298ce42'
```

The revision comes from `docs/harsh/handoff.md`; verify the imported catalogue
returns that exact facet revision. There is no fallback to the stale example
revision. M1 uses a process-local shared `EventCodec` and checksum-verified cache,
without creating a Kafka publisher or calling Registry per event. Readiness
also exercises the actual shared append inside a rolled-back PostgreSQL savepoint;
it commits no readiness event. An established verified cache works during
Registry downtime. A fresh process needs the complete mapping.

Cart edits, turn summaries, intent outcomes and actual turn tool facts append
through the shared library in the same transaction as their M1 state/result.
Accepted checkout records `CHECKOUT_STARTED` with the real Orders ID in the
command-completion transaction. An append failure leaves the earlier durable
command pending; retry the same identity to recover. Additional transport keys
for the same accepted quote cannot append a second checkout fact. No session or
quote event is invented, and retrieval events remain M2-owned.

Intent rejection references `m1-turn:<turn_id>` in private `turns.intent_diagnostic`.
Bounded malformed synthetic model text, when returned by the adapter, is stored
only in private `intent_rejections`; it never enters HTTP results, events or logs.
Such a rejection also uses Vichitr's local-diagnostic helper and registered DLQ
notice in the same transaction. Independently committed model-attempt audit
records still survive a later turn rollback and prevent a second model attempt.

Run `python -m pytest tests/conversation/test_shared_events.py -q -ra` with
`P6_TEST_DATABASE_URL` pointing at the documented isolated PostgreSQL 18 test
database. Each test creates/drops only its own schema. These tests use real shared
codec/outbox/diagnostic code and explicitly doubled registry IDs, catalogue,
Orders and model replies. They do not prove live Registry/Kafka delivery.
The separate M1 relay entry point below publishes the conversation outbox using
Aditya's shared worker and Vichitr's shared publisher. No relay starts in request
handling. See the progress file for actual evidence and remaining owner reviews.

Accepted checkout replays under a new transport key use the durable acceptance
without contacting Orders again. An in-flight alias may observe an advanced
status for the same order; a different returned order ID still fails closed.
Use the order-status API for current finality. Replay never appends another
`CHECKOUT_STARTED` or creates another purchase.

Start the relay in its own process after applying migrations and binding the
same verified schema cache, dataset revision and conversation database as the API:

```powershell
uv run --locked python -m services.conversation.relay
```

It needs `CONVERSATION_DATABASE_URL`, `KAFKA_BOOTSTRAP_SERVERS`,
`EVENT_SCHEMA_CACHE_PATH` and `CATALOG_DATASET_REVISION`. It checks the actual
schema/append path before constructing a publisher, uses the shared relay's
25-ms poll/100-row pass settings and one connection, and retains the durable
outbox after failure. Missing configuration exits 4 with sanitized evidence.
The existing worker owns locking, acknowledgements and redelivery; M1 does not
contain another relay algorithm. The process wraps the shared worker's public
start/stop lifecycle and handles SIGINT/SIGTERM. It is not an independent claim of
Kafka delivery or broker-loss recovery.

`projectctl.setup.migrate_conversation` is also available as the M1 migration
participant in the global coordinator. It migrates/verifies only this database;
it does not claim the other five databases have migrated.
