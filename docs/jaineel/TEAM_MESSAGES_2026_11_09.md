# Messages to send after the evaluation handoff push

9 November 2026. Source branch: `jaineel/j03-telemetry` in
`harsh-c-16/payment-gateway`. Send these messages yourself; no teammate has been
messaged automatically. All paths below are repository-relative and are included
on the branch. Generated packets and private evidence remain ignored locally.

These requests close implementation/review handoffs. They do not claim that the
37 generic integration cases, final machine enforcement or benchmark matrix have
already passed. CI software checks and final measured evaluation are separate.

## Harsh

Copyable message:

> I have reviewed Vichitr's PR #12 and pushed my evaluation harness handoff on
> `jaineel/j03-telemetry`. Please review
> `docs/jaineel/HARSH_REVIEW_2026_11_09.md`, particularly the exact-byte evaluation
> hashes versus your existing LF dictionary identity. I have preserved
> `flipkart-v1-3a401f32ca99379f8298ce42` and the existing SKU/business identities.
> Please confirm the normalized/SKU manifests, dictionary and query fixtures, or
> identify the exact changes needed before we freeze the final machine's packet.
>
> Please connect the catalogue/import/search/analytics-query callbacks through
> `projectctl.team_runtime`'s owner extension. Freeze analytical layout generations
> and query day, provide independent import/query expectations, and coordinate
> seed/projection proof with Aditya. Checkout/integrated templates still need
> review, and rule-derived relevance labels remain diagnostic until human review.
>
> Review the catalogue entries in the proposed provider receipt and the analytics
> mapping with the affected owners. The implementation now consumes actual
> reviewed receipts in `contracts check`; please do not mark a proposal approved
> without the corresponding review. Return your changed paths, exact test commands,
> evidence locations and import/search/query bottleneck notes for the final report.
>
> Execution instructions: `docs/jaineel/EVALUATION_TEAMMATE_RUNBOOK.md`.

Supporting implementation paths:

- `projectctl/provider_validation.py` and `projectctl/contract_checks.py`:
  executable schema/dictionary/export validation and reviewed-byte checks.
- `projectctl/evaluation_packet.py`: generates fresh candidate configs, recipes,
  exact hashes and proposed review records on the execution machine.
- `projectctl/runtime.py`, `projectctl/team_runtime.py`,
  `benchmarks/composition.py`: explicit `RuntimeBindings`/`OwnerCallbacks` extension.
- Existing provider inputs: `data/catalog/flipkart-v1-3a401f32ca99379f8298ce42/`,
  `contracts/dictionaries/catalog/flipkart-v1.json`,
  `contracts/fixtures/catalog/queries.json`.

## Vichitr

Copyable message:

> I have reviewed PR #12 and pushed the consumer/harness handoff on
> `jaineel/j03-telemetry`. Please review
> `docs/jaineel/VICHITR_REVIEW_2026_11_09.md` and the runtime/audit changes in
> `benchmarks/analytics_recheck.py`, `benchmarks/pipeline_audit.py`,
> `benchmarks/quality_binding.py` and `benchmarks/quality_trial.py`. G1 now passes
> the runtime dataset/resource context and cleans up after setup failure. Saved
> M4 verdicts are rebuilt from raw evidence rather than trusting an earlier PASS.
>
> Please verify and enforce every actual API/worker/relay allocation from
> `configs/evaluation_profiles.json` on the chosen Linux machine. The official
> proposed profile is 9 SUT cores/8 GiB, with 8.25 cores/7,808 MiB allocated;
> P10 has 16 processes and P33 has 18. Analytics API is separate from the fixed
> 1.5-core/1,536-MiB consumer group. The smaller pipeline profile is a separate
> study, not a comparator for integrated-profile runs. Supply actual host/image/
> cgroup proof, all container IDs, a real lakehouse mount and the shared-clock
> evidence; the conservative observer currently defaults to unshared clocks.
>
> Review the SELECT-only audit role/schema mappings, scoped exports, seed
> provenance and new saved-audit mapping pins. Please connect your remaining
> real G1/T-01/T-03, sink-before-offset, publication/late/replay case bindings and
> fault receipts to the existing generic harness, coordinating shared cases with
> their owners. A separate three-record G1 or provider pytest pass does not satisfy
> full T-03 or an unregistered generic case. Analytics reset also needs a real
> read-only preflight plus its existing guarded apply; do not bypass retention.
>
> Exact execution and evidence-return instructions:
> `docs/jaineel/EVALUATION_TEAMMATE_RUNBOOK.md`. Final performance evaluation has
> not been run on my laptop; please return raw evidence and stream/scaling notes.

Supporting implementation paths:

- `projectctl/team_runtime.py`, `projectctl/runtime.py`, `projectctl/setup.py`:
  M4 composition and explicit global migration/reset participant interfaces.
- `infra/analytics_runtime.py`, `pipelines/ingestion/adapters.py`,
  `infra/analytics_resources.py`, `infra/audit_roles.py`: existing owned provider
  bindings to review; their implementations were not replaced by this handoff.
- `benchmarks/integration_cases.py` and the generated `integration_inventory.json`:
  exact generic case inventory and registration status.
- `.github/workflows/offline.yml`: includes the existing local artifact-upload
  fix to avoid recursively scanning private container pytest directories.

## Aditya

Copyable message:

> I have pushed the evaluation harness handoff on `jaineel/j03-telemetry`.
> Please review the operational handoffs in
> `docs/jaineel/EVALUATION_TEAMMATE_RUNBOOK.md` and
> `docs/jaineel/VICHITR_REVIEW_2026_11_09.md`. The team composition currently has
> Conversation/Catalogue/Analytics migration delegates; please expose your real
> Orders, Inventory and Payments migration callbacks through
> `RuntimeBindings.migrations` in an explicit owner runtime module. Missing
> participants now stop global migration before any database is changed.
>
> Please supply operational fresh-storage/seed/projection proofs, actual relay
> startup bindings and reviewed read-only order/reservation/stock/signed-ledger
> snapshots. Verify the exact Inventory SKU key set against the pinned manifest,
> as well as 19,920 rows at 10,000 on-hand/0 reserved/version 1 and drained
> outbox/projection; counts alone are insufficient. Preserve original producer
> envelopes, broker acknowledgements, run IDs and idempotency keys for the oracle.
>
> Connect the remaining real G3/T-07/T-08/T-11 callbacks, explicit payment
> controls and recovery barriers using `G3Binding`/`CaseBinding`. Coordinate
> checkout/integrated templates and seed/projection cases with Harsh. Review
> the shared-outbox provider receipt with Jaineel and the cross-owner analytics
> mapping. For any later reset, expose `ResetParticipant(preflight, apply)` with
> real quiescence/acceptance/retention checks; do not reset development data.
>
> Return changed paths, exact commands, raw evidence and transaction/recovery
> bottleneck notes. Final benchmarks remain unrun; the teammate runbook identifies
> the actual prerequisites, execution commands and evidence to send back.

Supporting implementation paths:

- `projectctl/runtime.py`: `RuntimeBindings.migrations`, `.resets`, `.g3`, `.cases`,
  and `.workloads`; these are harness interfaces, not invented exports from M3.
- `projectctl/setup.py`: `MigrationCoordinator`, `ResetParticipant`,
  `ResetCoordinator`. Every reset preflight precedes any apply. Cross-database
  apply is not atomic; failures retain completed-stage evidence.
- `benchmarks/g3.py`, `benchmarks/g3_audit.py`, `benchmarks/integration.py`,
  `benchmarks/integration_faults.py`, `benchmarks/reconciliation.py`: existing
  API/fault/audit boundaries and independent business checks.
- `projectctl/provider_validation.py`: the shared-outbox surface and its pinned
  actual owner/consumer review. No outbox algorithm or M3 DTO was replaced.

## Packet command to share with the execution teammate

Run on the final machine after integrating the reviewed code, using a **new**
output directory. These two commands start no services and run no evaluation:

```bash
uv run --locked python -m projectctl.evaluation_packet --out artifacts/evaluation-handoff/final-machine-01
uv run --locked python -m projectctl.evaluation_packet --verify artifacts/evaluation-handoff/final-machine-01
```

The original private CSV must be available at its documented staging path.
Send the generated packet separately; it is not committed. Proposed reviews
remain pending. A changed input or source revision requires a new packet and
review; preserve older evidence. Continue with actual setup/correctness/measurement
only after the prerequisite handoffs in the teammate runbook are satisfied.
