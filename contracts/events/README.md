# Event contract proposal (M02)

Authority: [common §§7, 11.4, 12 and Appendix A](../../docs/specs/02_COMMON_SPEC.md).
Producer/consumer review is **pending**; registration is not G0 sign-off.

The five business subjects are `<domain>.v1-value`; DLQ uses the separate
`dead-letter.v1-value`. Subjects never include a run namespace. Every schema is
self-contained JSON Schema draft-07. `manifest.json` pins SHA-256 over sorted,
compact UTF-8 JSON, not over pretty-printed file bytes. The reason dictionary is
in [dictionaries/events](../dictionaries/events/reasons.v1.json).

Payloads are plain UTF-8 JSON, maximum 65,536 value bytes. Required Kafka headers
are `content-type=application/json` and decimal UTF-8 `schema-id`. There must be
exactly one of each; supplementary headers are retained. Kafka keys and topics
come from `EventEnvelope.kafka_key()` / `.topic()` or their DLQ counterparts.
No Confluent magic byte or binary framing is used.

`shared/contracts/events.py` supplies typed snapshots and semantic checks. Schemas
enforce field shape; the Python validation path additionally checks identities,
cross-field versions, inventory arithmetic, retrieval modes/counts, fixed-mode
model calls and event/state agreement. Other producers/consumers must use those
checks too. An embedded `IntentSnapshot` is an event-owned snapshot of common §4,
not a replacement for Harsh's missing canonical catalogue HTTP DTO/dictionaries.
Dictionary membership remains a Harsh handoff; unsupported facets are not guessed.

Consumers accept optional unknown properties. `SchemaCache.validate` preserves
the complete parsed wire document (including unknown fields and explicit nulls)
and hashes that immutable document, not a lossy DTO dump. Duplicate JSON members,
nonfinite numbers, coercible integer strings, fractional integers and booleans in
integer fields are rejected. Supplying `ingested_at` checks the normal-fixture
five-second future bound; replay must retain its separate time policy.

The cache contains all six mappings and definitions. It is created only after
real registry read-back agrees with repository pins. Existing runs can validate
offline without registry calls. Missing/tampered caches fail readiness. IDs not in
this build's verified cache return `UNSUPPORTED_SCHEMA`; a known ID belonging to a
different domain returns `SCHEMA_ID_MISMATCH`. Cache files and registry IDs are
environment-specific and live under ignored `artifacts/infra/streaming-local/`.
Do not copy arbitrary IDs between computers. Online verification checks actual
subject/version/ID/hash and `BACKWARD_TRANSITIVE` policy; it does not silently
accept a changed registry definition.

Rebuild owned assets from the models with:

```powershell
.venv/Scripts/python.exe -m infra.contract_assets
```

This also rebuilds the analytics OpenAPI and reason dictionary. It does not
register a schema. `env up` with `PROJECTCTL_ADAPTER_MODULE=infra.streaming`
registers and read-verifies them; `env verify` checks the cached mapping online.
Review breaking changes before regeneration/registration; registry compatibility
alone cannot approve changed business semantics or deleted required fields.

[Synthetic JSON examples](../../tests/pipelines/fixtures/events.v1.json) cover
all 24 business types plus DLQ. Executable negative cases are in
`tests/pipelines/test_event_contracts.py`. Tests explicitly label fake offline
registry IDs. The opt-in live test checks all subjects, safe optional evolution,
incompatible type changes, and the unsafe addition of a typed property to an
open content model. It then publishes/reads all 25 examples in fresh `bench-`
topics; this is a wire smoke, not durable analytical ingestion.

Registry API/content-model references:
[Confluent API](https://docs.confluent.io/platform/current/schema-registry/develop/api.html),
[JSON Schema behavior](https://docs.confluent.io/platform/current/schema-registry/fundamentals/serdes-develop/serdes-json.html).

See [M02 handoff](../../docs/vichitr/m02_contract_handoff.md) for unresolved
producer bindings and the resolved receipt agreement. The publishing/consuming SDK
and transactional local diagnostic helper remain M03.
