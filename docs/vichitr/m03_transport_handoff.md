# M03 transport and diagnostic handoff

Date: 31 October 2026. Public implementation: `shared/event_transport/`,
`shared/local_diagnostics/`; typed records: `shared/contracts/events.py`.

## Owner adoption

| Consumer | Required integration | Current boundary |
|---|---|---|
| Jaineel / M1 | Existing keyword build_event and caller Connection/outbox binding; configure_transport before readiness | Keyword call is tested unchanged. Supply actual catalogue revision for linked facts and UUID event correlation IDs. His startup wiring remains owner work |
| Aditya / outbox | Persist immutable constructed event; publish exact stored identity/content and mark only after PublishAck | Real library absent. Support EventEnvelope and DlqNotice, preserve aggregate relay ordering, and retry uncertain delivery without rebuilding identity |
| Harsh / stock projection | Independent long-lived ConsumerGroup; validate source, durably persist projection/diagnostic, mark durable, commit prefix | Do not bypass manual offsets or reuse revoked ownership tokens |
| Jaineel / harness | Bounded producer calls, actual ack/errors, frozen producer/worker settings and raw evidence | No unbounded tasks or manually invented success; receipt APIs become operational in M04/M05 |
| All diagnostic callers | Apply table template in own migration; pass existing Connection and stable LocalDiagnostic | No cross-service writes or substitute outbox. Missing binding fails before writing |

Pull/integrate vichitr's provider changes before use. Package READMEs contain usage
and resource settings. M1 readiness currently checks shared bindings; adopt explicit
cache/configuration startup when the real outbox arrives. RequestContext accepts a
bounded correlation identifier, while EventEnvelope requires UUID: propagate a
valid UUID without silently replacing identity in the builder. No consumer-owned
implementation, service migration, shared CLI or dependency lock was changed.

## Explicit signature choices for review

Common names/required arguments are preserved. These provider choices resolve
remaining underspecified bindings without overriding an existing implementation:

- `consume_records(group,topics,max_records,max_wait_ms)` takes a long-lived
  ConsumerGroup constructed from the group ID. `commit_offsets` takes that handle
  plus `{(topic,partition): next_offset}`. `mark_durable(record)` follows actual
  caller durability; the SDK cannot observe or fabricate another owner's commit.
- Four-argument validate_event cannot infer coordinates. ValidEvent.source_record
  is explicitly null then. Optional source_record binds actual raw provenance;
  tombstones require it. document preserves complete parsed immutable content.
  Replay supplies a declared ingress clock/policy, preserving source timestamps.
- The diagnostic transaction binding is the existing psycopg Connection. Nested
  savepoints preserve caller ownership even for a caught non-SQL outbox failure.

These recorded bindings still need adopting-owner review; public provider code
and a test double do not imply whole-team G0/startup integration is complete.

## Compatible schema evolution

Optional root/metadata values survive relay serialization. Schemas explicitly
state the already-open content model; known requirements/key/owner rules remain.
Diagnostic/DLQ service vocabulary adds analytics, separate from business producers.
Actual BACKWARD_TRANSITIVE checks accept evolution and still reject breaking
types and unsafe typed optional additions.

`contracts/events/supported-history.json` pins all six released M02 hashes.
Registration retrieves matching historical definitions/IDs into the verified cache,
so released retained events validate offline. Unknown/unpublished IDs are not
guessed. IDs stay environment-specific and uncommitted. A fresh registry may have
no old versions; upgraded definitions must match the explicit repository pins.

## Evidence and remaining work

Evidence: ignored `artifacts/m03/`; commands/outcomes: [progress](progress.md).
Real smoke checks acknowledgement, broker pause/retry with unchanged bytes,
durable-prefix guards, independent groups, and rebalance/exact redelivery/fencing.
Marked durability in that smoke is a transport fixture, not an actual M04 sink.

The SQL test uses real PostgreSQL and an **explicit transactional outbox double**.
It verifies caller rollback, caught outbox-failure savepoint rollback, idempotent
retry and changed-ID conflict. Real shared outbox/service integration is NOT_RUN
until Aditya supplies it and owners migrate/wire their own services.

Buffer limits concern raw in-flight controls, not full Python/native RSS. Oversized
sources rewind/fail without commit. Fixed declared worker count and unique static
indexes are required for the group budget. No performance gain, business migration,
Bronze archive or active Gold is claimed. Next: M04 FileStore/Bronze/real receipts.
