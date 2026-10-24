# Conversation service (M1)

Owner: Jaineel Vora (B24CM1080). Authority:
[personal brief](../../docs/specs/04_JAINEEL_VORA.md),
[common specification](../../docs/specs/02_COMMON_SPEC.md), and
[conversation OpenAPI](../../contracts/http/conversation.yaml).

P2 supplies the contract, owned DTOs and consumer HTTP/SSE adapters.
Provider schemas remain external, with provisional examples/doubles restricted to
fixtures/tests. Real mode uses real HTTP and cannot fall back to those examples.
No running session/cart service, database migration, outbox or workflow is supplied
at this checkpoint; those belong to P6/P7.

Run `python -m pytest tests/contracts -q` and
`python benchmarks/manual/verify_p2.py` from repository root.
See [P2 handoffs and manual checks](../../docs/jaineel/p2_contracts.md) for usage,
deadline/retry policy, unresolved bindings and evidence interpretation.
