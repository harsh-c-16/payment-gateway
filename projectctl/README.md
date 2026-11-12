# Unified CLI foundation

Presentation acceptance: `python -m projectctl demo-check` checks service
readiness and Harsh's three real searches without purchasing. Use
`python -m projectctl demo-check --state PATH_TO_DEMO_STATE` for GET-only
verification of an accepted order in Orders and active Gold. Both retain raw
HTTP evidence and per-check results. See the
[Windows presentation guide](../docs/jaineel/PRESENTATION_READY.md).

Owner: Jaineel. Contracts: [runbook §1](../docs/specs/09_EVALUATION_RUNBOOK.md),
[brief J01](../docs/specs/04_JAINEEL_VORA.md), [P1](../docs/specs/10_JAINEEL_CODEX_PLAYBOOK.md).

Current completion, live-prototype evidence and remaining formal evaluation work:
[10 November audit](../docs/jaineel/PENDING_WORK_AUDIT_2026_11_10.md).
Milestone descriptions retain their original checkpoint scope.

Run commands from the repository root. Use Python 3.11 and uv 0.10.8.
`uv.lock` is the single generated application lock, including development tools.
This is an application workspace (`tool.uv.package=false`); run modules from the
checkout. No model, embedding or vector stack is installed.

```powershell
uv python install 3.11
uv sync --locked
.\.venv\Scripts\Activate.ps1
python --version
python -m projectctl --help
python -m projectctl eval run --help
python -m projectctl benchmark run --help
python -m pytest tests/projectctl -q
python -m ruff check projectctl tests/projectctl
python -m ruff format --check projectctl tests/projectctl
python -m projectctl.schemas --check
```

On Linux/macOS, activate with `source .venv/bin/activate`. Activation is optional:
use `uv run --locked python ...` or the environment's Python directly. If a corporate
policy prevents writing uv's default cache, configure an approved writable cache
with `UV_CACHE_DIR`; never disable TLS or remove package hashes.

P1 pytest runs use a unique `artifacts/pytest/<uuid>/` directory for temporary files
and pytest's cache. This avoids Windows permission errors when an earlier run used
a different account to create `%TEMP%/pytest-of-<user>` or `.pytest_cache`.
Normal `python -m pytest tests/projectctl -q` works without deleting those directories,
changing ACLs or running as administrator. Explicit `--basetemp` and `-o cache_dir=...`
overrides remain supported. New sessions leave earlier run directories intact.

The reproducible install follows [uv's project workflow](https://docs.astral.sh/uv/guides/projects/).
Update dependencies deliberately with `uv lock`, review its diff, then repeat the
offline checks. Routine installs use `uv sync --locked`, which refuses a stale lock.
Infrastructure/image locks belong to Vichitr; Aditya verifies DB compatibility.

All runbook actions and flags are parsed strictly; abbreviated/unknown flags fail.
P1 originally had no production adapters. `ProviderRegistry.register(action, adapter)` is
the explicit seam for reviewed owner adapters; `Invocation` carries the complete
arguments, resolved config, UUID run identity and namespace. Test doubles live only
in `tests/projectctl/` and always declare `test_mode=stub`. There is no automatic
mock fallback, startup implementation, domain contract implementation or benchmark
execution hidden behind the CLI.

```powershell
# Without an explicit adapter: exit 4; JSON links dependency evidence.
python -m projectctl env verify --profile local4c8g
# Expected exit 2: unknown flags cannot be silently ignored.
python -m projectctl env verify --profile local4c8g --unknown
# Expected exit 4: draft controls/hashes/providers block all six requested runs.
python -m projectctl benchmark run --workload W-PIPE --variants B0,O1 --repetitions 3 --config configs/evaluation.yaml
```

Each invocation saves `manifest.json` and `summary.json`; configuration-bearing
commands also save `resolved_config.json`. Benchmark requests use a unique
`benchmarks/results/<run_id>/` for each requested variant/repetition. P4 executes
the lifecycle only when explicit real adapters and preflight gates are ready;
otherwise it preserves NOT_RUN evidence. Commands without evaluation config save under
`artifacts/projectctl/<run_id>/`. Paths in stdout are repository-relative. P1 metrics
are null with `NOT_RUN`, and missing collectors are listed without creating fake
empty Parquet/CSV files. These ignored directories preserve failure evidence locally.

Exit codes: **0** completed/pass; **2** invalid input; **3** correctness failure;
**4** missing dependency/incomplete evidence; **5** completed measurement missing a
declared target. Metric statuses are `MEASURED`, `INCOMPLETE`, `NOT_RUN` independently
of exit codes. A passing adapter double is not a real integration or measurement.

The evaluation YAML is explicitly `draft`: source SHA is the published expectation
from file 08, while unknown provider paths/hashes are null. `local4c8g` allocations
are proposed, not verified hardware. Full frozen controls are recorded with each
request. Only registered variant differences are allowed. Finite jobs retain null
measurement-window seconds; query jobs retain 3 warmups/30 executions per Q1-Q6.
The matrix records measured-best selection requests without inventing C-BEST.
The `locks` section records the actual generated application-lock SHA; infrastructure
and event-schema lock paths/hashes remain null until their owners supply them.
Unknown actual host memory/storage/physical-core information remains null.

Schemas in `contracts/evaluation/` are generated from strict Pydantic models:

```powershell
python -m projectctl.schemas
python -m projectctl.schemas --check
```

Schema checks validate shape; `load_config` additionally validates variant semantics,
resource totals and path confinement. JSON canonicalization sorts keys, preserves
arrays, encodes UTF-8 and rejects nonfinite numbers. Manifest content hashes exclude
their own `content_sha256`; raw file/lock hashes cover exact bytes.

P2 registers the offline `contracts check --all` inventory. Current provider
paths/endpoints and consumer examples validate; the real affected-owner review
receipts remain pending, so the current configured check exits 4 (UNREVIEWED).
Merged provider schemas automatically validate the provisional consumer examples;
compatibility corruption exits 3. This check does not assert service readiness or G0.
See [P2 bindings and evidence](../docs/jaineel/p2_contracts.md) and run
`python benchmarks/manual/verify_p2.py` for the combined P1/P2 checkpoint.

P3 now registers `fixtures build` as an offline action. It writes immutable logical
W-QUALITY expectations, dirty catalogue cases, 60 draft assistant scenarios and
checksum-gated source assertions into a fresh fixture bundle. It runs no providers,
broker, model or benchmark. Human review and wire/audit bindings remain pending;
see [P3 checks and limitations](../docs/jaineel/p3_oracles.md). Reproduce with
`python benchmarks/manual/verify_p3.py`.

P4
supplies scheduling, matrix expansion/resume and random paired execution.
No real environment, exact-file data, live-model or performance gate has run at P1.

Reproduce this checkpoint and retain command/stdout/stderr/exit evidence with:

```powershell
python benchmarks/manual/verify_p1.py
```

It writes a new directory under `artifacts/p1/` and expects missing provider actions
to exit 4. Its own exit 0 means these expected checkpoint outcomes matched.

## P4 benchmark execution

`benchmark run` and `benchmark matrix` now use the isolated lifecycle and record
seeded paired plans. Missing workload adapters return dependency exit 4 with
saved evidence. See [P4 bindings and verification](../docs/jaineel/p4_workloads.md).
The default registry never loads a test double. Comparison/report execution
remains assigned to later milestones.

## Roadmap Prompt 3: real composition

Select the explicit composition with
`$env:PROJECTCTL_ADAPTER_MODULE = 'projectctl.jaineel'`. It calls the existing
`infra.analytics.register` (which registers streaming once),
`pipelines.catalog.adapter.register`, and `services.inventory.adapter.register`.
Registration is transactional: a failed import/registration discards partial
bindings, retaining the built-in contract/fixture actions and dependency evidence.

Workload factories bind each trial's own resolved configuration to Harsh's
`runner_importer`, `runner_query_adapter` and verified `runner_catalog_manifest`.
The search consumer uses the real public HTTP contracts and a client per request.
The frozen catalogue settings are `CATALOG_MAX_CONNECTIONS=4` and
`CATALOG_REUSE_CONNECTIONS=false`; apply them to the actual catalogue process.
The planned evaluation resource profile remains unverified and draft.

`benchmarks.composition.OwnerCallbacks` contains explicit harness handoff slots.
No owner module is assumed to export them. M4 supplies real pipeline/quality
callbacks; complete operational storage, seed/drain/audit and observer bindings
still need owner extensions and review. W-IMPORT has an
independent CSV/Parquet money/selection/disposition audit and generator observer;
it still needs a real fresh-namespace provider before it may write. W-SEARCH
sequences migration, import, verification, seed, projection wait (including the
owner's ANALYZE), then independent seed checks. Missing/partial results stop the
sequence. Global migration currently registers Conversation, Catalogue and
Analytics; Orders/Inventory/Payments participants remain pending. Reset has no
registered participants and cannot apply.
The unified composition below now also connects W-PIPE, W-QUALITY, W-CHECKOUT and
W-INTEGRATED. A registered driver is not a ready deployment.

Seed audits must return complete unique `catalog_skus`, `inventory_skus` and
`projected_skus` lists, each equal to the pinned active manifest. Counts alone
cannot pass. `projectctl.team_runtime` wraps the existing M4 seed callback with
`benchmarks.seed_audit.with_seed_membership`, using the existing SELECT-only
Inventory/Catalogue reader and the original seed namespace. Operational owner
extensions must supply the lists or use that wrapper. Registration opens no
connections. Review proposals pin both the new reader and team composition;
their actual mapping/role review remains required before real evaluation.

Run the bounded checkpoint without a benchmark or Docker startup:

```powershell
.venv/Scripts/python.exe -m benchmarks.manual.verify_prompt3 --out artifacts/jaineel/prompt3-NEW
```

It retains actual registrations, independent source/profile checks, CLI contract
checks, hash-policy evidence and unavailable callbacks. Exit 4 means the full
setup remains incomplete even if the real CSV profile and contracts pass.
No import/seed/measurement is attempted without the owner preparation handoff.
The generator observer does not claim SUT resource coverage.

`projectctl.input_pins.review_input_pins()` reports raw bytes and LF-text hashes
separately. Harsh's published pins match normalized LF text; the frozen runbook
requires raw-file hashes. Raw checks are unchanged, evaluation dictionary/query
pins remain null, and the approved dataset revision is preserved. Harsh/Jaineel
and the SKU consumer must review the exact policy conflict before filling pins.
Rule-generated relevance labels stay unselected; optional model/ANN runs remain
unconfigured. Docker containers created for a checkpoint should be removed after
use; retain volumes, evidence and unrelated containers.

## Roadmap Prompt 7: baseline prerequisite checkpoint

```powershell
.venv/Scripts/python.exe -m benchmarks.manual.verify_prompt7 --out artifacts/jaineel/prompt7-NEW
.venv/Scripts/python.exe -m pytest tests/benchmarks/test_prompt7.py tests/benchmarks/test_performance.py -q
```

This read-only checkpoint saves `readiness.json`, `resolved_config.json`,
`checkpoint.md` and the actual `uv sync --locked --check` logs. It inventories
the explicit Jaineel composition without calling adapters or workload factories.
It checks every required workload's preflight, current Git state, exact local
file hashes, unresolved raw/LF hash policy, missing human relevance review,
session-reuse exclusion, three repetitions and the existing correctness/resource,
smoke and baseline-diagnosis validators. `--readiness PATH` consumes an existing
owner-reviewed receipt through the runner's validator; it creates no approval.
Discovered image/schema files are observations and do not populate config pins.

Exit 4 is incomplete prerequisite evidence; exit 2 is invalid input, including
a changed frozen hash. Both leave setup, smoke, B0, comparisons and C-BEST
`NOT_RUN`, with null metrics. Use a fresh output directory on every invocation.
This command does not freeze B0 or certify service readiness. Current hash-policy
and human-label review remain external handoffs. Follow canonical runbook
[sections 2 and 5–7](../docs/specs/09_EVALUATION_RUNBOOK.md) after those gates close:
setup/smoke, real correctness, frozen B0, diagnosis, three paired randomized
repetitions, independent drain/reconciliation, measured selection and artifact
reporting. Harsh's owner-run samples and rule-derived labels cannot supply those
missing results.

## Unified runtime composition

`projectctl.jaineel` now registers all seven required workload factories. It
connects the existing SDK, HTTP drivers, owner importer/query adapter, independent
audits and optional G3/correctness bindings through one explicit runtime input.
The optional assistant workload remains outside the required matrix.

Keep `PROJECTCTL_ADAPTER_MODULE=projectctl.jaineel`. For an actual team deployment,
an explicitly selected Python module can expose `runtime_bindings()` returning
`projectctl.runtime.RuntimeBindings`. Set `PROJECTCTL_RUNTIME_MODULE` to that
module's import name. This is the harness's new input interface; it is not a claim
that a teammate already exports a function with that name. No runtime module is
automatically discovered, imported or started when this setting is empty.

The returned object supplies:

- `workloads`: workload name to the existing `OwnerCallbacks` (fresh storage,
  seed/projection audit, drain, read-only audit, observer, reviewed templates and
  layout). Checkout/integrated setup now uses the same ordered public import,
  verification, seed and projection barrier as search.
- `quality`: the existing `QualityOwners`. The legacy
  `benchmarks.quality_binding` entry point forwards to the unified composition.
- `g3`: case IDs to existing real `G3Binding` objects; `cases`: other canonical
  case IDs to real `CaseBinding` objects. Their existing independent fixture and
  execution-time review checks still apply.
- `setup_actions`: optional reviewed global `db migrate`/`env reset`
  coordinators. `projectctl.setup.MigrationCoordinator` delegates one participant
  per database and refuses partial success. `migrate_conversation` is the concrete
  M1 participant. Other owners supply their own participants; the harness does
  not execute their SQL files or implement their business migrations.

`benchmarks.runtime_observer.RuntimeObserver` connects explicit API/worker
Prometheus targets, existing Kafka lag/Gold readers and resource collectors.
Worker and API targets remain separate. Missing SUT targets or stub collectors
fail; missing individual samples stay missing. Clock sharing must be explicitly
declared from the actual deployment, and readiness/resource receipts are still
required for measurements.

W-PIPE materializes valid synthetic fixture facts through the shared codec and
publisher, with fixed source identity/provenance, 10,000 verified SKUs, immutable
timestamps and approximately 1-KiB payloads. It cannot use the invalid-quality
bypass or mutate operational Inventory. The publisher closes on normal drain and
exceptional observer exit. Required owner inputs remain explicit dependencies;
this wiring does not authorize measurements or manufacture a passing real gate.

For M1's separate shared-outbox process, see the
[service commands](../services/conversation/README.md). Current team handoff and
the latest exact test/evidence results are recorded in
[Jaineel's progress](../docs/jaineel/progress.md).

## Interactive prototype demo

After starting the [existing prototype deployment](../infra/PROTOTYPE.md), run:

```powershell
.venv/Scripts/python.exe -m projectctl demo --namespace dev --user-id demo-jaineel --query "shirt"
```

Select a result and quantity, review the quote, then explicitly type the displayed
`CONFIRM <quote-id>` to purchase. Fixed mode makes zero LLM calls. The client saves
identity, cart versions and retry keys; use `demo --resume <printed-state-path>`
after an interruption. See [the demo runbook](../docs/jaineel/PROTOTYPE_DEMO.md)
for setup, recovery, evidence and the remaining owner acceptance checks.
