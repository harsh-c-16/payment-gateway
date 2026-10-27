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
real PostgreSQL. The shared event path remains incomplete. Turn workflow,
quote and checkout endpoints return explicit P7-unavailable errors.

See [P6 persistence handoff](../../docs/jaineel/p6_persistence.md) for exact
semantics, checks, schema ownership, manual smoke and outstanding reviews.

Run `python -m pytest tests/contracts -q` and
`python benchmarks/manual/verify_p2.py` from repository root.
See [P2 handoffs and manual checks](../../docs/jaineel/p2_contracts.md) for usage,
deadline/retry policy, unresolved bindings and evidence interpretation.
