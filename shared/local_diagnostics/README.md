# Service-local diagnostics (M03)

Owner: Vichitr. Authority: [common §§6.1/12 and Appendix A](../../docs/specs/02_COMMON_SPEC.md).

`quarantine_local_diagnostic(db_transaction, diagnostic)` accepts LocalDiagnostic
and the caller's **psycopg Connection already in a transaction**, matching M1's
outbox binding. It inserts into that connection's local_diagnostics table, then
calls Aditya's `append_outbox(connection, DlqNotice)`. It never connects to another
database, publishes Kafka or commits the caller.

```python
with connection.transaction():
    persist_local_domain_change(connection)
    diagnostic_id = quarantine_local_diagnostic(connection, diagnostic)
```

Each service owner applies [schema.sql](schema.sql) through its own migrations.
`diagnostic_table_ddl()` returns the template only. Aditya supplies the actual
outbox table/library. Missing binding raises OutboxUnavailable before a write.
Idle connections are rejected; explicit transactions on autocommit connections
are accepted. Cursors/psycopg Transaction wrappers are not this binding.

A savepoint rolls back the diagnostic even if the caller catches a non-SQL outbox
failure. Caller rollback rolls back both writes. Identical namespace/diagnostic-ID
retry is a no-op; altered content raises DiagnosticConflict. No repeated outbox
entry is inserted. M1's private intent_attempts/usage audit tables remain separate.

Persist only IDs, finite reasons, times, hashes, source coordinates and a restricted
content reference. Raw diagnostic storage/access belongs to the caller's service;
never store raw model output, customer text or credentials here or in DLQ notices.

`build_dlq_notice` is exported from shared.event_transport. It is pure:
event_id=diagnostic_id and produced_at=created_at. Source coordinates select
kafka_record origin; otherwise service_diagnostic uses the restricted reference.
Analytics is a valid diagnostic/DLQ service, never a business-event producer.
Generic relays accept both EventEnvelope and DlqNotice, choosing their own keys/topics.

Real PostgreSQL transaction tests use an **explicit transactional outbox double**;
they do not certify Aditya's missing library. Owners still must apply migrations
and wire helpers. See [M03 handoff](../../docs/vichitr/m03_transport_handoff.md).
