# Jaineel code handoff — 8 November 2026

Latest review: [pre-push audit](PUSH_AUDIT_2026_11_08.md). The final owned suite
passes **1,286 tests** with real isolated M1 PostgreSQL; all **191 owned Python
files** pass lint/format checks. This audit fixed two additional HTTP failure
paths, added six regressions and completed the example's schema-cache setting.
Aditya also has seven reproduced route-boundary failures (explicit ASGI/SQL doubles)
covering principal access, missing internal tokens and unisolated fault controls.
Run `python -m benchmarks.manual.verify_transaction_boundaries --out artifacts/boundaries-NEW`
to retain that failing handoff. These counts overlap the historical checks below.
Whole-repository CI and final integration/evaluation remain incomplete.

The standalone M1 and M0 implementation is ready for peer integration with the
validation recorded below. Commit and push the reviewed owned changes so the
team can consume them. Full-system correctness, B0/comparisons and the final
evaluation report follow service integration; they are still NOT_RUN and are
not being claimed as completed here. No commit or push has been performed.

The latest continuation closes the remaining runner wiring: one composition
connects all seven required workload types, public catalogue/Orders/M1 clients,
normal SDK W-PIPE transport, existing W-QUALITY and G3 adapters, migration
coordination and real collector assembly. M1 now includes a separate executable
relay using the shared libraries. There is no duplicate business service,
outbox algorithm, schema, normalizer or Gold reducer in Jaineel's code.

Use `PROJECTCTL_ADAPTER_MODULE=projectctl.jaineel`. The optional
`PROJECTCTL_RUNTIME_MODULE` names the deployment's explicit module returning
`RuntimeBindings`; it is empty until concrete owner hooks are supplied. The
composition accepts the existing workload lifecycle callbacks, quality hooks,
real G3/correctness bindings and global migration/reset coordinators. Each
callback still acts only within its owner's component. Missing inputs remain
visible; no stub or approval record is manufactured.

The technical input interface and fields are documented in
[projectctl/README.md](../../projectctl/README.md#unified-runtime-composition).
The existing `OwnerCallbacks`, `QualityOwners`, `G3Owners` and `CaseBinding`
definitions remain the exact callable signatures. Owners can now supply their
real component operations through that interface without changing the runner's
registration code. `MigrationCoordinator` requires all six migration
participants before executing any. The M1 participant is implemented; other
database owners retain authority over theirs.

Run M1 with the approved database URL, pinned schema cache and catalogue
revision, plus actual catalogue and Orders origins:

```powershell
uv sync --locked
uv run --locked python -m services.conversation.database
uv run --locked python -m uvicorn services.conversation.app:create_app --factory --host 127.0.0.1 --port 8001
# A separate process, with the same M1 database/cache/revision and real Kafka:
uv run --locked python -m services.conversation.relay
```

The example allocation is three API connections including durable intent audit,
plus one relay connection. One API process is assumed by that split. The relay
checks the actual local schema/shared append path, then delegates publishing and
acknowledgement handling to the shared worker/SDK. Fixed mode remains zero-model;
purchase and confirmation controls are unchanged.

Actual continuation checks:

- **869 passed** across projectctl, benchmark, telemetry, integration, contract
  and oracle suites; no failures/skips. External I/O doubles are explicit.
- **411 passed** in the full conversation suite against isolated PostgreSQL 18;
  no failures/skips. The new relay test uses the real SQL, codec and shared relay
  thread with explicit registry-ID/broker-ack doubles. It verifies unchanged
  outbox bytes, published marking and no republish after restart; live Kafka is
  not claimed by this test.
- **39 passed** in the final targeted CI-isolation, pipeline and runtime checks;
  all **190 owned Python files** pass formatting; owned lint and schema checks
  pass. These counts overlap the broader runs.
- The existing Vichitr transport fixture was rerun: **1 failure**, still the
  missing explicit cache/revision setup. It was not skipped or patched outside
  ownership. Harsh's previously measured strict brand XPASS also needs owner
  review/removal. Whole-repository CI is not declared green.

Raw commands, logs and JUnit are in
`artifacts/jaineel/finish-20261108/`. The previous audit is historical evidence;
this document supersedes its statement that the common composition only wires
three workloads or that M1 has no relay entry point. Full benchmark prerequisites
remain draft/unapproved. No performance value or human quality approval was
filled in to declare the handoff ready.

**Harsh:** Use the updated M1 consumer and unified runner. Review/remove your
stale brand xfail, agree the dictionary/query byte-hash policy, and provide the
verified catalogue/SKU/facet manifests and stock projection/seed evidence. Supply
your concrete catalogue migration and layout/query hooks to the runtime input.
Human relevance claims require reviewed manual labels; the current rule scores
remain diagnostic. The catalogue outbox migration already exists.

**Aditya:** Use M1's shared-outbox relay command and provide your component
migration/setup/audit/fault operations to the common runtime input. Close Orders
quote ownership/expiry and idempotency while preserving accepted retries, retain
the original run identity in saga work, and add deterministic payment
success/decline/delay controls matching the frozen workload. Then we can execute
the already implemented G3 success/decline and recovery consumers. Fix the newly
reproduced public snapshot/SSE principal checks, internal service-token checks
and both-flags/isolated-namespace fault guards before integrated acceptance.
The exact probe command and assertions are in the latest audit.

**Vichitr:** Update the transport test fixture to pass M1's explicit pinned
cache and synthetic revision. Verify the real Kafka/Registry stack and projection
edge cases, then supply the worker/API metric targets and concrete scoped
setup/drain/source/active-Gold/fault operations. The existing observers and
quality/G3 consumers are connected by the runtime interface. O1 batching/scaling
comes after the correct B0 gate; the current ingestion runtime remains B0-only.

**Together after those component fixes:** execute G0/G1/G3 and required
correctness tests, agree/freeze actual inputs/resources on a committed revision,
measure and diagnose B0, run the registered three-repetition comparisons, then
reconcile and build the report from artifacts. Jaineel still coordinates these
team-dependent runs. No one needs to wait for a finished final evaluation report
before sharing their implementation branch.
