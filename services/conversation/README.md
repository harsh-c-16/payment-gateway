# Conversation service (M1)

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
shared builder and transaction-local outbox; missing libraries cause HTTP 503
and failed readiness. Tests explicitly select test event/outbox capture, using
real PostgreSQL. The shared event path remains incomplete. P7 supplies the
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
ten-connection budget is split into nine ordinary slots and one intent-audit slot.
See [P11 configuration and verification](../../docs/jaineel/p11_assist.md) for
explicit enablement, dated model/prompt settings, attempt-spy tests and limitations.
Required real DE gates and live quality remain incomplete; no test provider is
loaded automatically in real mode.
