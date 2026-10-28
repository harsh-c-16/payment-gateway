# Jaineel's Codex implementation playbook

Version 1.0 — 24 October 2026  
Companion to the current Group 3 version-2 specifications. This guide organizes implementation; it does not replace their contracts.

**Start here:** put files 00–09 and this file together in **docs/specs/**, open the cloned repository in Codex, run Prompt 0, inspect the scaffold, then run Prompt 0B to publish it. After that, use the session prompt and one numbered implementation prompt at a time.

## 1. Context to give Codex

Codex needs the files inside the repository it can access. A GitHub URL identifies the repository but does not supply the specifications or grant access to your local checkout. Open the actual cloned folder and state the repository URL in the first prompt. Never supply a GitHub password or token in a prompt.

| Context | Repository location | When needed |
|---|---|---|
| Navigation | docs/specs/00_README.md | Initial orientation |
| Scope, decisions, technology families | docs/specs/01_PROJECT_CONTEXT.md | Each new milestone/session |
| API, DTO, event and ownership authority | docs/specs/02_COMMON_SPEC.md | Relevant sections for every implementation |
| Metrics, workloads and correctness definitions | docs/specs/03_EVALUATION_SPEC.md | Harness, oracle, telemetry, experiments |
| Your responsibility and J01–J07 tasks | docs/specs/04_JAINEEL_VORA.md | Every Jaineel milestone |
| Harsh's brief | docs/specs/05_HARSH_CHAUDHARI.md | Catalogue, quote, retrieval and compaction handoffs |
| Aditya's brief | docs/specs/06_ADITYA_GAURAV.md | Transactions, inventory, payments and shared outbox handoffs |
| Vichitr's brief | docs/specs/07_VICHITR_ARORA.md | Infrastructure, transport, ingestion and Gold handoffs |
| Exact CSV identity and normalization rules | docs/specs/08_DATASET_PROFILE_AND_RULES.md | Fixtures, catalogue checks, search constraints |
| CLI commands, suites, matrix and artifacts | docs/specs/09_EVALUATION_RUNBOOK.md | CLI, tests, integration and measurements |
| This execution sequence | docs/specs/10_JAINEEL_CODEX_PLAYBOOK.md | Current prompt and checkpoint |
| Persistent working rules | AGENTS.md and docs/OWNERSHIP.md | Every session |
| Current implementation state | docs/jaineel/progress.md | Resume work without relying on chat history |

Keep one canonical copy of each numbered specification. Component README files link to the appropriate brief and common files; do not duplicate the complete specifications into several service folders.

You do not need to paste the full conversation, obsolete tracker progress, or sample lab metrics into every coding session. The current specifications are the implementation source. At the first session, read the overview and your brief, then the relevant normative sections. In later sessions, read the current progress and changed/relevant sections instead of blindly rereading the entire pack.

Place the unchanged CSV at **data/raw/flipkart_com-ecommerce_sample.csv** when data checks are needed. Leave it untracked. Initial scaffolding and most fixture-based unit tests do not require the full CSV. Exact-file data gates must be visibly unexecuted if it is absent.

The established technology families are in file 01 §6: Python 3.11, FastAPI/Pydantic 2, psycopg 3, PostgreSQL, Kafka, JSON Schema, PyArrow, DuckDB, Prometheus/Grafana and Docker Compose. The exact compatible application lock is your G0 deliverable; infrastructure versions/digests are Vichitr's. Do not make Codex choose a different architecture in each session.

### Model choice

Use **GPT-6.1 Sol / Extra High** if it is available in your Codex client. My recommendation is to keep Extra High for contract interpretation, concurrent state changes, reconciliation and experiment design. Folder creation and straightforward documentation usually need less effort. Using Extra High throughout is also reasonable if you prefer it; allow time for the extra reasoning.

This is your development model choice. It does not add runtime LLM calls to the application. The application remains fixed-mode, zero generative calls by default.

Official guidance: [model and reasoning selection](https://learn.chatgpt.com/docs/models) and [repository instructions with AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md). Availability and labels depend on the client/account. AGENTS.md supplies persistent guidance; it is not a Git permission mechanism.

## 2. Repository ownership and exact scaffold

The skeleton is a one-time team setup. Creating a teammate's empty directory does not authorize implementing that teammate's code.

| Owner | Directories to create |
|---|---|
| Jaineel — application | services/conversation/, migrations/conversation/ |
| Jaineel — measurement | projectctl/, benchmarks/, benchmarks/manual/, dashboards/, shared/telemetry/, tests/oracles/, tests/integration/ |
| Jaineel — own tests | tests/conversation/, tests/projectctl/, tests/benchmarks/, tests/telemetry/, tests/contracts/ |
| Jaineel — coordinated fixtures | contracts/fixtures/, contracts/fixtures/catalog/, contracts/evaluation/ |
| Harsh | pipelines/catalog/, services/catalog/, analytics/compaction/, analytics/queries/, migrations/catalog/, tests/catalog/, tests/analytics/ |
| Harsh — contracts | contracts/data/catalog/, contracts/dictionaries/catalog/ |
| Aditya | services/orders/, services/inventory/, services/payments/, shared/outbox/, migrations/orders/, migrations/inventory/, migrations/payments/, tests/transactions/ |
| Vichitr | pipelines/ingestion/, pipelines/curation/, pipelines/gold/, pipelines/replay/, pipelines/storage/, shared/event_transport/, shared/local_diagnostics/, infra/, migrations/analytics/, tests/pipelines/ |
| Split by file owner | contracts/http/, shared/contracts/, configs/ |
| Coordinated documentation/plumbing | docs/specs/, docs/jaineel/, docs/decisions/, .github/workflows/, data/raw/ |

The extra test/documentation subdirectories here are organizational conventions. They do not change any public API or evaluation meaning.

| Shared file or area | Maintainer after scaffold |
|---|---|
| contracts/http/conversation.yaml | Jaineel |
| contracts/http/catalog.yaml | Harsh |
| contracts/http/transactions.yaml | Aditya |
| contracts/http/analytics.yaml | Vichitr |
| shared/contracts/conversation.py | Jaineel |
| shared/contracts/catalog.py | Harsh |
| shared/contracts/transactions.py | Aditya |
| shared/contracts/events.py, analytics.py | Vichitr |
| shared/contracts/common.py | Proposed neutral request/error DTO file; Jaineel coordinates initial extraction, affected owners review |
| contracts/events/, contracts/dictionaries/events/ | Vichitr, event producers review |
| contracts/fixtures/ | Jaineel coordinates; providers review expectations |
| configs/evaluation.yaml, configs/core_matrix.yaml | Jaineel |
| Other component/infra configs, Compose | Relevant owner; Vichitr maintains infra |
| pyproject.toml, one application lock, CI, root README, .gitignore, .env.example | Jaineel coordinates |
| Root/package initialization files | Jaineel coordinates initial packaging; avoid shared automatic re-exports that everyone must edit |
| docs/specs/00–09 | Existing normative documents; changes require affected-owner review |

Create **contracts/events/** and **contracts/dictionaries/events/** as part of Vichitr's scaffold too.

Jaineel may read every tracked project file. During personal implementation, write only his owned paths and the exact coordinated files needed for that milestone. In particular:

- Do not implement catalogue parsing/ranking/quotes, inventory, payments, saga, event transport, outbox relay, Silver/Gold reducers or compaction.
- Do not modify another owner's API/DTO just to make your client test pass.
- Do not edit infra/ or another domain's migrations to hide an integration failure.
- If a dependency is absent, use explicit test doubles in your own tests; record the pending provider handoff. Real mode must fail visibly when the provider is unavailable.
- Share executable contracts early. Teammates should first deliver their schemas/DTOs and minimal testable provider behavior, rather than wait for complete services.

### AGENTS.md content to create during Prompt 0

Keep this file team-neutral. Do not make the root file say that every developer is Jaineel.

~~~markdown
# Repository working rules

This is Group 3's data-engineering project. Prioritize a correct measurable
baseline, pipeline optimization, reproducibility and independent reconciliation.

## Context and authority
- Read docs/OWNERSHIP.md, the current owner's brief and the relevant sections
  of docs/specs/01_PROJECT_CONTEXT.md, 02_COMMON_SPEC.md,
  03_EVALUATION_SPEC.md, 08_DATASET_PROFILE_AND_RULES.md and
  09_EVALUATION_RUNBOOK.md.
- The common spec defines interfaces; file 08 defines source mapping;
  files 03/09 define evaluation. Personal briefs assign implementation.
- Do not silently resolve a contract conflict by changing public behavior.
  Record exact conflicting requirements and the required owner/consumer review.
- Never treat old lab sample numbers as measured results.

## Scope
- Read across the repo as needed; edit only the active task owner's paths.
- Creating the initial scaffold is a one-time exception for directories,
  placeholders and ownership documentation, not business implementations.
- Do not replace another owner's implementation or canonical DTO.
- Keep shared specifications canonical in docs/specs; use links elsewhere.

## Implementation
- Use the frozen technology families and one reproducible application lock.
- Services communicate through documented APIs/events, not cross-service
  database writes or imports of service internals.
- Reuse the shared outbox, event transport and canonical DTOs.
- Fixed assistant mode makes zero generative calls. Optional assist follows
  the documented single-call policy. Purchase actions require explicit controls.
- Use integer minor units, UTC wire timestamps and monotonic elapsed timings.
- Preserve request identity, idempotency, cart versions and provenance.

## Evidence
- Implement one requested milestone, run appropriate checks and stop at its
  checkpoint. Fix failures within the milestone before reporting completion.
- Test doubles must be explicit. A stub pass is not a real integration pass.
- Missing providers, missing data and unexecuted checks must remain visible.
- Preserve raw evidence. Unmeasured results are null/NOT_RUN, not fabricated.
- Do not weaken assertions or skip required tests merely to obtain a green run.
- Record changed paths, exact commands, actual outcomes, evidence locations,
  remaining handoffs and manual verification steps in the owner's progress file.

## Git
- Preserve existing work. Inspect branch/status/diff before editing or committing.
- Never force-push, rewrite shared history or reset/delete unrelated work.
- Do not commit credentials, .env, raw datasets, generated data or benchmark
  result directories. Small deterministic test fixtures belong in Git.
- Commit and push only when the current task explicitly requests it.
- Use small feature branches and PRs after the initial shared scaffold.
~~~

AGENTS.md should be read alongside actual checks. Ownership instructions alone cannot guarantee that every generated edit is correct.

## 3. Prompt 0 — create the team scaffold

First manually create **docs/specs/** and copy the ten existing files plus this guide there. This is the only setup directory you must create yourself. Then open the repository root in Codex and paste:

~~~text
I am Jaineel, the initial repository coordinator for Group 3.
Repository: <paste the actual GitHub repository URL>.
This is my cloned working copy. Work inside this checkout.

Read docs/specs/10_JAINEEL_CODEX_PLAYBOOK.md sections 1–3 and the ownership/
repository sections of 01_PROJECT_CONTEXT.md and 02_COMMON_SPEC.md.
Inspect the existing Git status, branch and origin; preserve any existing files.
Do not assume that the remote is empty just because application code is absent.

Implement only the one-time repository scaffold:
1. Create every directory listed in section 2 of the playbook.
2. Use .gitkeep where needed so otherwise-empty directories are tracked.
   Do not add empty invalid YAML/JSON schemas or fake implementation files.
3. Keep all numbered specifications together in docs/specs without rewriting them.
4. Create root AGENTS.md from the team-neutral rules in this playbook,
   docs/OWNERSHIP.md with the ownership tables, and a root README linking to
   the shared files and each person's brief.
5. Add small owner/brief links in the main component README files.
6. Create docs/jaineel/progress.md with milestones P1–P11, all not started.
   This local progress document is separate from the academic tracker.
7. Add .gitignore for .env/secrets, virtual environments, caches, local databases,
   downloaded models, raw data, generated Parquet, artifacts/ and
   benchmarks/results/. Retain small fixtures and .env.example.
   Do not ignore every CSV or JSON globally.
8. Create .env.example with placeholder configuration names from common §2.
   Do not write real credentials.
9. Do not implement services, dependency installation, Docker Compose,
   migrations, provider schemas, test suites or benchmark results yet.
10. Verify document links, intended tracked folders, ignore behavior and diff.

Creating all owners' empty folders is authorized for this task only.
Do not commit or push yet. Report files created, any pre-existing work,
the intended initial branch, and the exact checks I should inspect.
Stop at the scaffold checkpoint.
~~~

**Manual checkpoint 0 — 5 minutes**

- Open the root README and AGENTS.md. Confirm all four owners are represented.
- Look at services/, pipelines/, shared/ and tests/. Other owners should have placeholders/READMEs, not generated business implementations.
- Confirm files 00–09 have their original content.
- Run these in your repository terminal:

~~~bash
git status --short
git diff --stat
git diff --check
git check-ignore -v .env data/raw/flipkart_com-ecommerce_sample.csv benchmarks/results/probe.json
~~~

For the final command, all three paths should match an ignore rule. These paths need not exist. Inspect newly created/untracked files too: an ordinary git diff does not display their contents. A small fixture under contracts/fixtures/ must remain trackable.

Do not accept "all tests passed" here: no implementation tests exist yet. The correct result is a verified scaffold.

## 4. Prompt 0B — commit and push the scaffold

After you inspect checkpoint 0:

~~~text
The scaffold is reviewed. Commit and push this scaffold now.

Recheck the repository root, current branch, origin and staged diff. Stage only
the reviewed scaffold/spec/documentation files; exclude secrets and generated data.
Use the commit message "chore: initialize team structure and coding specifications".

If origin genuinely has no existing branches, establish main as the shared initial
branch and push it with upstream tracking. If main already exists or is protected,
preserve its history and push a chore/repository-bootstrap branch for a PR instead.
Do not force-push, bypass protection, overwrite remote work, or change origin.

Report the commit hash, remote branch and push result. If authentication or branch
protection blocks the push, retain the local commit and report the exact blocker.
Stop after publishing the scaffold.
~~~

**Manual checkpoint 0B**

Open the GitHub repository and confirm the files appear on the intended branch. If a bootstrap PR was necessary, get it merged into main before teammates branch from it. A commit existing only on your laptop is not a shared handoff.

Then everyone pulls the same main. Teammates can start H01/A01/V01 contract work. Ask Aditya for A02 shared outbox and Vichitr for V02 event transport early; your real event-producing service depends on those libraries.

Create your next branch from current main, for example:

~~~bash
git switch main
git pull --ff-only
git switch -c jaineel/j01-foundation
~~~

These commands assume main exists and your working tree is clean. If pull refuses because of divergent work, inspect it; do not run a hard reset as a shortcut.

## 5. Session prompt — use when starting a new Jaineel session

Replace the milestone placeholder. In the same continuing session you can just paste the next implementation prompt.

~~~text
I am Jaineel. Implement only milestone <P-number and title> in
docs/specs/10_JAINEEL_CODEX_PLAYBOOK.md.

Read root AGENTS.md, docs/OWNERSHIP.md, docs/jaineel/progress.md,
docs/specs/01_PROJECT_CONTEXT.md and 04_JAINEEL_VORA.md.
Read the relevant normative sections of 02_COMMON_SPEC.md,
03_EVALUATION_SPEC.md, 08_DATASET_PROFILE_AND_RULES.md and
09_EVALUATION_RUNBOOK.md. Inspect existing implementations/tests before editing.

You may read the whole repository. Write only Jaineel-owned paths and the exact
root/coordinator files needed for this milestone. The scaffold exception is over.
Do not implement or refactor teammates' modules, edit their DTOs/contracts, or
change public paths, fields, money units, event keys or metric definitions.

Before editing, briefly identify the files to change, contracts consumed,
available/missing providers and acceptance checks. Then implement the milestone
and fix its relevant failures without waiting for approval of routine choices.
If a provider is missing, use an explicit test-only double where appropriate,
keep real-mode checks visibly incomplete, and record the provider handoff.
Do not silently replace real providers with mocks.

At completion give:
- files changed and why;
- exact commands actually run and outcomes, including skipped/unrun cases;
- test mode: stub, local real dependencies, or real integrated services;
- evidence paths;
- 3–6 concrete manual actions with expected results;
- remaining blockers and next milestone.

Update docs/jaineel/progress.md. Do not claim completion without evidence.
Do not commit/push or proceed to the next milestone in this implementation turn.
~~~

Progress file convention: for each milestone record state, branch, relevant commit/base, commands, evidence, test mode, pending owner handoffs and next action. Use labels such as not started / in progress / stub verified / real verified / blocked. These are planning labels, not replacements for the specified result-schema statuses.

## 6. Implementation sequence

The P-numbers below split the existing J-tasks into smaller checkpoints. They do not create extra project scope.

| Prompt | Existing brief mapping | Deliverable | Dependency level |
|---|---|---|---|
| P1 | J01 | Python tooling, CLI/config/artifact foundation | No running providers needed |
| P2 | J01 | Conversation contract, clients, explicit stubs | Provider contracts reviewed before real compatibility claims |
| P3 | J01 + early J06 | Independent fixtures, oracle and metric math | Small offline fixtures; full CSV when available |
| P4 | J02 | Open-loop workload generation and experiment lifecycle | Stubs first; real provider adapters as merged |
| P5 | J03 | Telemetry, raw collectors, dashboard | Fake samples for tests; real samples for evidence |
| P6 | J04 | Durable sessions, cart and idempotency | Real PostgreSQL; shared outbox for real event path |
| P7 | J04 | Zero-call search, quote and checkout workflow | Stubs first, then catalogue/Orders |
| P8 | J06 | Real G1/G3 integration, failures, reconciliation | All relevant provider handoffs |
| P9 | J07 | Correct B0 and controlled performance matrix | Real correctness gates and locked environment |
| P10 | J07 | Reproducible report and clean setup rehearsal | Valid measured run artifacts |
| P11 | J05, optional last | One-call intent fallback | Core work complete; live provider optional |

**Do G1 as soon as Vichitr's one-event path is ready and your P3/P4 harness can drive it. Do G3 as soon as P7 and transaction/catalogue providers are ready.** Do not postpone these thin integration slices until every feature is finished.

### P1 — development environment, CLI and artifact foundation

~~~text
Implement P1 only: the J01 development and runner foundation.

Read common §§2–3, my J01 brief, evaluation §9 and runbook §1.
Set up the Python 3.11 package/test/lint workflow in pyproject.toml with one
generated application dependency lock and a documented reproducible install.
Use the specified library families; do not install an LLM/vector stack now.

Implement python -m projectctl with the exact documented subcommand/flag surface.
Register provider actions through explicit adapters. An unavailable/unimplemented
adapter must produce dependency failure and nonzero exit, never dummy success.
Implement --help and strict option/config validation.

Implement contracts/evaluation/{config,run,summary,fixture}.schema.json,
configs/evaluation.yaml and configs/core_matrix.yaml from the runbook.
Define complete resolved configurations, namespace/run identity, hashes, result
statuses and exit codes 0/2/3/4/5 with their documented meanings.
Do not fill unknown hashes or performance fields with plausible values.
Missing hashes may exist in an explicitly incomplete draft, but must block a real run.

Add focused tests under tests/projectctl and CI for implemented offline checks.
Keep pending real-provider checks visible without claiming they ran.
Do not write infra/ or provider business logic.
~~~

**Manual checkpoint P1**

Run the documented locked install in a new terminal, activate that environment, then:

~~~bash
python --version
python -m projectctl --help
python -m projectctl eval run --help
python -m projectctl benchmark run --help
python -m pytest tests/projectctl -q
~~~

Python should be the agreed 3.11 environment, help must work, and tests must actually execute. Try an unknown CLI flag: it should fail with exit 2. With no provider adapter, an environment/provider command should return exit 4, not report successful startup. Inspect a generated draft summary: unmeasured values are null/NOT_RUN.

### P2 — conversation contracts and provider stubs

~~~text
Implement P2 only: J01 conversation contracts, dependency clients and stubs.

Use common §§3–6 and Appendix A. Own contracts/http/conversation.yaml and
shared/contracts/conversation.py. Coordinate neutral RequestContext/error types
without taking ownership of catalogue/transaction/event DTOs.

Build clients for the documented catalogue search/product/facets/quote APIs,
Orders create/status/SSE, and analytics inspection interfaces required by the
harness. Preserve exact fields, headers, timeout/deadline and idempotency semantics.

Use canonical provider DTOs/schemas when merged. Until then, keep provisional
spec-shaped JSON examples/test doubles in contracts/fixtures and tests only;
record the missing owner contract and do not publish a rival canonical DTO.
Once provider contracts arrive, validate both examples and clients against them.

Implement explicit stub and real transport configurations. Cover success,
no results, fewer-than-five results, missing/null facets, 409, 503, timeout,
changed price, duplicate idempotency key and lost response.
Stubs must be impossible to activate accidentally in a real benchmark.

Implement contract checks and tests under tests/contracts. Demonstrate that
a deliberately misspelled required field and a wrong money type are rejected.
Keep missing provider contracts visible in contracts check --all; a partial
consumer test pass does not mean G0 is complete.
~~~

**Manual checkpoint P2**

Run tests/contracts. Inspect one request/response pair in each client. Confirm money uses integer minor units and nullable facets remain nullable. Run a negative-schema test and ensure it detects the corruption. Switch to real mode with the provider stopped: it must fail, not return a stored successful fixture.

Ask the provider owners to review their consumed field names and examples. Full G0 also requires the dataset and environment locks/smoke evidence; four YAML files alone do not complete G0.

### P3 — independent fixtures, oracle and metric math

~~~text
Implement P3 only: independent expectations and reconciliation primitives.

Use dataset §§2–7, evaluation §§2/5/7/9 and runbook §§3/4/6/7.
Create deterministic dirty-catalogue fixtures and expected dispositions,
W-QUALITY expectations, and the 60-scenario assistant fixture structure.
Do not import Harsh's production normalizer or Vichitr's production reducer
to calculate the expected answer. Do not generate relevance ground truth with
an LLM. Draft human-reviewable labels and mark them awaiting review until reviewed.

Implement reconcile_run and metric helpers in tests/oracles/ and benchmarks/ with
tests that deliberately supply missing events, duplicate effects, bad totals,
false Gold visibility, stale manifests and illegal stock/payment states.
The oracle reads evidence and never repairs the system.

Use nearest-rank quantiles, declared cohort/window denominators, separate
offered/admitted/goodput, and unresolved counts. Handle zero denominators and
missing samples explicitly. Test fixed six-slot F1 including wrong non-null values.

For the exact CSV, verify the file08 checksum before exact-count assertions:
20,000 source records = 19,920 active + 78 inactive + 2 superseded + 0 rejected.
This does not mean all 19,920 are currently in stock. Do not implement a second
production ingestion pipeline.
~~~

**Manual checkpoint P3**

Run tests/oracles and the relevant tests/benchmarks. Check these tiny examples yourself:

| Input | Expected |
|---|---|
| Durations 10, 20, 30, 40, 100 ms | nearest-rank p50=30, p95=100, p99=100 |
| Kafka log-end next offset 25; committed next offset 20 | lag=5 |
| Latency 100 ms baseline, 80 ms candidate | 20% reduction |
| Throughput 100/s baseline, 125/s candidate | 25% gain |
| No observed timing sample | null/incomplete, not 0 ms |

Look at at least one real dirty-fixture input/expected output for price, missing price, duplicate pid and absent size. Review all labels before freezing the final evaluation set; inspect representative groups now. Confirm the corruption tests fail reconciliation for the intended reason.

### P4 — open-loop generator and experiment lifecycle

~~~text
Implement P4 only: J02 workloads and the reusable runner lifecycle.

Implement generate_workload and run_experiment using file03 and runbook §§1/5/7.
Start with W-PIPE and a deliberately slow explicit test publisher. Schedule
arrivals independently of sink completion, with bounded pending count/bytes.
Record planned, attempted, acknowledged, failed and unresolved emissions,
queue pressure, scheduling delay, event IDs and broker coordinates.

Implement isolated prepare -> validate -> warmup -> measure -> drain ->
reconcile -> persist, retaining artifacts even after failures.
Create fresh benchmark namespaces; never reset dev/live or unrelated data.
Reconcile against the frozen workload manifest, not only acknowledged records.
Implement the finite-job and sustained-workload distinctions exactly.

Add W-IMPORT by delegating to Harsh, W-SEARCH/W-CHECKOUT/W-INTEGRATED through
public APIs, W-ANALYTICS through the agreed query adapter and W-AGENT through
the workflow adapter. Missing adapters are explicit pending dependencies.
Integrated transactions must produce their own business events; do not inject
fake confirmed-order events to make integration appear complete.

Preserve configured intentional duplicates exactly. Implement recorded paired
ordering, repetitions and configuration-difference checks. Do not run the full
performance matrix yet.
~~~

**Manual checkpoint P4**

Run tests/benchmarks. Use the slow-publisher demo Codex supplies. The offered schedule must remain the requested schedule while lateness, failed/missed sends or bounded backlog become visible. It must not silently reduce the target and claim success.

Open emissions.jsonl and compare counts with the workload manifest and summary. A short test run must be labeled smoke/test evidence, not a 600-second performance run. When Vichitr is ready, perform the real G1 valid/duplicate/invalid slice now.

### P5 — telemetry, collectors and dashboard

~~~text
Implement P5 only: J03 shared telemetry, observers and dashboard definitions.

Use common §14, evaluation §5 and runbook §7. Implement observe_run,
structured context propagation, raw timing retention and 1-second collectors.
Keep outbox backlog, Kafka lag and pending Gold publication separate.
Collect Gold visibility against active-manifest membership/generation.

Use the specified metric names, elapsed clocks, histogram buckets and safe
low-cardinality labels. Keep per-event/run details in artifacts/logs, not
new high-cardinality Prometheus labels. No fabricated zero samples.

Create dashboard definitions and an offline summary that can be reconstructed
from artifacts. Display run/variant/workload context and evidence status.
Add provider instrumentation instructions; owners add instrumentation to their
own code. Coordinate Grafana/Prometheus startup with Vichitr instead of editing
his Compose files.

Test collector gaps and a publisher stall. Test/sample data must remain
separate from real measured results.
~~~

**Manual checkpoint P5**

Run tests/telemetry. With a test or real publisher stalled, verify that low Kafka lag and growing pending Gold are shown as different facts. Stop a collector and confirm a visible missing-data condition. Verify an offline table can be rebuilt without Grafana.

Real CPU/RAM/lag claims require the actual collector path; a mocked dashboard screenshot does not establish them.

### P6 — durable sessions, cart, versions and idempotency

~~~text
Implement P6 only: J04 persistent conversation state.

Implement session creation, cart reads/updates, turn/idempotency storage and
conversation migrations using common §§3–5/8 and the acceptance vectors.
Persist locally in conversation_db with the documented principal/namespace
isolation. Cart quantity zero removes a line; other bounds follow the spec.

Store the idempotency request hash/response with the mutation. Same key and
same input returns the same logical result; changed input conflicts.
Enforce expected_cart_version under concurrent edits.

Use Aditya's append_outbox in the same database transaction and Vichitr's event
builder for real conversation/cart events. Test doubles are allowed for local
unit tests, but do not implement another outbox or publish directly after commit.
If shared libraries are missing, finish the independent code/tests and explicitly
leave the real event-path gate incomplete.

Use real PostgreSQL for transaction/restart/concurrency claims. An in-memory
store or SQLite-only test is insufficient for those claims.
~~~

**Manual checkpoint P6**

Use the generated local request examples or a small scripted smoke client:

1. Create a session, add one SKU, then repeat the identical request/key. There is one effect.
2. Reuse that key with changed quantity. Expect an idempotency conflict.
3. Send an old cart version. Expect HTTP 409.
4. Restart the service. The cart remains.
5. Try another user's cart. Access must be rejected according to the contract.
6. In the real DB test, roll back a mutation and verify that neither cart effect nor outbox event survives.

Run tests/conversation. Confirm which cases used real PostgreSQL and which used doubles. Do not mark the outbox handoff complete until the shared implementation is wired and tested.

### P7 — deterministic search, quote and checkout

~~~text
Implement P7 only: the required zero-generative-call J04 workflow.

Implement dispatch_turn, deterministic extract_intent, compose_response,
request_quote and checkout_cart using common §§5/6.2 and Appendix A/B.
Use Harsh's versioned dictionary and one search maximum per search turn.
Retain explicit hard filters. Unknown/ambiguous constraints need clarification;
known but unavailable constraints may legitimately return no results.
Structured controls bypass intent extraction.

Use deterministic templates and authoritative products/quotes/order status.
Bind explicit confirmed=true and confirmation_id to the exact quote/cart version.
A cart edit invalidates the previous quote confirmation. Forward stable mutation
keys; lost checkout responses must not create a second order.
Never treat a timeout as proof of cancellation.

Keep ASSISTANT_MODE=fixed and ALLOW_INTENT_LLM=false. Prove zero model calls
for all required fixed/structured flows. Implement the overall 3000-ms search
turn budget and pass remaining time downstream.

Create a replayable manual smoke example that captures returned IDs rather than
hard-coding invented IDs. Implement the fixed-mode T-10/D-05 cases. Keep optional
live assist results NOT_RUN. Do not build an elaborate frontend.
~~~

**Manual checkpoint P7**

Use Postman, a local API docs page if enabled, or the generated smoke client:

- Search with a supported fixture/query. Product fields match the provider response.
- Ask for a missing/unsupported hard attribute. It clarifies or returns honest no-results; it does not silently remove the constraint.
- Add an item and obtain a quote. The displayed total matches Quote.total_amount_minor.
- Edit the cart after quoting, then try the old confirmation. It is rejected.
- Checkout explicitly; repeat with the same key. It returns the same order reference.
- Stop Orders or inject response loss. The client reports the appropriate unavailable/pending state and does not fabricate a final status.

Inspect assistant_turns.jsonl or equivalent test evidence: fixed-mode model attempts are zero. A displayed HTTP 202 means accepted/pending, not necessarily confirmed. Run tests/conversation, contract checks and the applicable T-10/D-05 cases.

### P8 — real integration, failures and independent reconciliation

~~~text
Implement P8 only: J06 real integration and recovery verification.

First inventory the actual provider handoffs and reviewed contracts. Replace
test transports with real adapters explicitly. Do not run with silent stubs.
Use real PostgreSQL/Kafka and the locked environment for integrated claims.

Run the runbook §2 setup/data gates in order. Verify source/import/active-SKU
manifests, simulator seed and complete stock projection before checkout.
Run G1: valid/duplicate/invalid event to Bronze, Silver, quarantine and active Gold.
Run G3: search -> cart -> quote -> simulated success/decline -> stock projection
-> matching Gold, reconciled independently.

Implement and drive the required T/D coverage, particularly duplicate delivery,
100-buyer stock race, response loss, compensation, late/older versions, publication
recovery and isolated replay. Fault injections require acknowledged named barriers.
Use namespace-scoped read-only audits, not corrective writes.

Run T-11 analytics and Kafka outages separately with their specified timing.
Collect accepted work, finality, lag/outbox/pending-export and recovery evidence.

If a teammate's code violates a contract, provide the exact failing request,
expected/actual response, fixture, evidence and owner. Fix only Jaineel-owned code.
Keep that gate failed/incomplete until the provider fix is merged and rerun.
~~~

**Manual checkpoint P8**

Use the exact setup commands in file09 §2. Once providers are present:

~~~bash
python -m projectctl contracts check --all
python -m projectctl eval run --suite contracts,data,smoke --config configs/evaluation.yaml
python -m projectctl eval run --suite correctness --config configs/evaluation.yaml
python -m projectctl eval run --suite T-10,D-05 --config configs/evaluation.yaml
python -m projectctl eval run --suite T-11 --config configs/evaluation.yaml
~~~

Check one successful and one declined transaction by following the same IDs through cart, quote, order, inventory, signed payment ledger and active Gold. Read correctness.json and tests.jsonl, not just terminal "passed."

For a duplicate-event test, confirm multiple deliveries but one logical effect. For a fault test, confirm the barrier receipt and retained-volume restart; a random process kill is not proof of the intended boundary. Confirm replay did not modify operational stock/payment state.

If required tests were skipped or unavailable, G4 is not complete. Independent module work can continue, but full performance claims wait.

### P9 — baseline and controlled optimization experiments

~~~text
Implement/execute P9 only: J07 baseline and required experiment matrix.

Confirm the required real correctness gates, complete locked configs, exact
dataset/fixture hashes and enforceable resource profile. Identify a clean code
commit for measurements; if preparation changes code, finish it and hand off for
review/commit before recording a final baseline.

Complete core_matrix.yaml and the real adapters for all required runbook §5
rows. Keep B0 and each candidate selectable from the same frozen experiment
revision where possible, with only declared treatment differences.
Do not disable durability, validation, indexes needed for integrity, outboxes
or instrumentation in the baseline.

First run a small smoke and one complete B0 repetition to validate all collectors
and reconciliation. Inspect the actual bottleneck before launching candidates.
Then run the recorded randomized paired matrix with three repetitions.
Use the 60/600/120-second protocol for sustained jobs and the documented finite/
query exceptions. Do not run both the example command list and the same matrix
twice by accident.

Cover I0/I1, B0/O1, B0/O2, P10/P30/P33 with skew, compaction and partition-only
comparisons, transaction faults and B0/O3 integrated runs. Select C-BEST only from
measured results, then complete stress and recovery trials.
Coordinate provider optimization implementations with their owners.

Preserve failed/incomplete trials. Expose generator saturation, missing samples,
unresolved cohorts and resource costs. Negative or insignificant improvements are
valid outcomes. Do not fill target numbers or declare a winner in advance.
~~~

**Manual checkpoint P9**

First confirm the full B0 run directory has real emissions, timings, lag, resources, manifests, correctness and summary files. Check source/fixture/config hashes, code identity and actual resource settings.

Then launch the matrix once:

~~~bash
python -m projectctl benchmark matrix --matrix configs/core_matrix.yaml --config configs/evaluation.yaml
~~~

Check at least one paired comparison yourself:

- Same source/rules, fixture, cache state, resource budget and relevant semantics.
- Only the registered optimization differs.
- Three retained repetitions are present, not just the fastest.
- Offered rate and actual admissions are both reported.
- Missing completions are visible beside latency quantiles.
- Finite imports use actual elapsed time, not a 600-second denominator.
- Partition-only results compare equal target file sizes/codecs.

These experiments can take substantial time. Do not replace them with short smoke runs and retain the performance labels. If the host cannot enforce the proposed local4c8g profile, agree and freeze a feasible profile and use it for every comparator.

### P10 — report, reproducibility and release check

~~~text
Implement/execute P10 only: J07 evidence validation and report.

Finish benchmark reconcile, benchmark compare and report build exactly as the
runbook specifies. Validate evidence references, schemas, all paired repetitions
and comparison controls. Build every required table from saved measurements.

Reject a report that presents missing/failed evidence as a successful measurement,
mixes mock and real results, or uses only the best run. Use correct improvement
directions, zero-baseline handling, units and sample counts. Preserve limitations,
negative findings and costs.

Update docs/integration_runbook.md and docs/jaineel/progress.md with the actual
setup/test commands and status. Do not rewrite academic tracker progress.

Perform a clean-checkout rehearsal in an isolated directory and benchmark namespace:
locked install, owner-supplied infrastructure setup, migrations, unchanged data,
seed, projection barrier, contract/data/smoke checks and report rebuild.
Do not reuse hidden local files or reset other development data.

Provide the final evidence index and remaining NOT_RUN items. Optional live
LLM/ANN work must be separated from required-core completion.
~~~

**Manual checkpoint P10**

Replace capitalized placeholders with actual paths emitted by the runner:

~~~bash
python -m projectctl benchmark reconcile --run-dir benchmarks/results/RUN_ID
python -m projectctl benchmark compare --baseline benchmarks/results/BASELINE_RUN --candidate benchmarks/results/CANDIDATE_RUN --out artifacts/comparisons/pair
python -m projectctl report build --matrix-results artifacts/core_matrix_results.json --out artifacts/final_report
~~~

Pick one reported metric and trace it to raw observations. Rebuild the report without rerunning the workloads and confirm the values match. Remove an evidence file only from a disposable copied artifact bundle: validation must detect it. Ask a teammate to reproduce setup and one small integrated flow using the documented commands.

### P11 — optional one-call intent fallback, last

~~~text
Implement P11 only if the required data-engineering work is complete.

Implement J05 exactly under common §6.2. Fixed mode remains the default.
Assist invokes a model only after deterministic parsing requires help and
ALLOW_INTENT_LLM=true. Enforce at most one schema-constrained attempt,
1500-ms model timeout, no SDK retry/repair/composition call, one search and
3000-ms overall turn deadline. Preserve explicitly parsed hard constraints.

Model output may provide validated intent only; it cannot purchase, select tools,
invent attributes/prices/stock, change confirmation or execute product text.
Invalid output/timeout returns clarification and a diagnostic.

Run provider-spy tests counting attempted calls including failures. Complete
applicable T-10/D-05 coverage and six-slot F1 reporting. Freeze the human-reviewed
60-scenario fixture. Compare the same backend/fixtures across fixed and assist.

Live provider access is optional. Without it, spy correctness runs but live quality,
latency, tokens and cost remain NOT_RUN/null. Do not invent usage from mock text.
~~~

**Manual checkpoint P11**

Try explicit supported search, ambiguous text, invalid model output, a model timeout, product-text instructions, and cart/quote/checkout actions. Inspect the attempt count: fixed and purchase actions are always zero; eligible assist fallback is at most one even on failure. No provider retry may hide behind the client library. Confirm a correct no-result/clarification is counted separately from a successful recommendation.

## 7. Checkpoint rhythm and Git routine

**After every numbered prompt:** run its focused checks, inspect changed files and perform the listed small manual demonstration. Do not wait five prompts before testing.

**Broader checkpoints:** after P3 (contract/harness foundation), after P7 (your working application), after P8 (real integration), and after P10 (reproducibility). Rerun affected contract tests when a provider contract changes or a teammate's implementation is merged.

At every checkpoint inspect:

~~~bash
git branch --show-current
git status --short
git diff --name-only
git diff --stat
git diff --check
git diff --cached --name-only
~~~

Also open untracked files and staged diffs. Verify that no teammate-owned implementation has changed without the agreed handoff. In the test report, check collected/passed/failed/skipped counts. "No tests collected" or "all skipped" is not verification.

A simple manual review is enough: make the example work yourself, try one failure case, and read the corresponding evidence. Codex should automate exhaustive checks; you need to verify that the reported behavior matches what you observe.

### Reusable bug-fix prompt

~~~text
Stay on the current milestone. Do not start the next one.

Command/action I ran:
<paste exact command or manual action>

Expected behavior:
<paste expectation>

Actual result:
<paste relevant traceback/response, with secrets removed>

Reproduce this failure, identify the root cause and make the smallest correct
change within Jaineel-owned paths. Add/update a meaningful regression check,
then run the failing check and affected contract/tests. Do not weaken the
assertion, replace real services with mocks or change another owner's contract
to hide the issue.

If the root cause belongs to another owner, provide a minimal reproduction,
contract citation, evidence and owner handoff; keep the gate incomplete.
Update progress with actual results and give me the manual recheck.
~~~

### Reusable review prompt

Use after P3, P7 and P8, preferably in a fresh Codex conversation against the actual working tree:

~~~text
Review the current milestone changes against AGENTS.md, the active owner brief,
the common specification and the evaluation runbook.

Check contract drift, out-of-scope edits, incorrect idempotency/concurrency,
lost failure evidence, mocks in real execution, unbounded queues, fabricated or
miscomputed metrics, and untested assumptions. Run targeted checks where useful.
Report concrete findings with file references, consequences and reproductions.
Do not edit code in this review pass. A passing merge is not proof of integration.
~~~

A second model review supplements your checks; it is not proof by itself.

### Reusable commit/PR prompt

Use after the checkpoint passes and fixes are verified:

~~~text
The milestone has passed my manual checkpoint. Commit and push the reviewed
changes on the current Jaineel feature branch. Stage only the intended source,
tests, small fixtures, config and documentation. Exclude secrets/raw/generated data.

Recheck the staged diff and summarize validation in the commit/PR description.
Create a PR to main if the tooling is available; otherwise provide its compare
link and a ready description. Do not merge automatically, force-push or rewrite
other people's work. Identify any provider/consumer reviewer required.
~~~

Use a new small branch for the next merged milestone; do not keep one isolated personal branch until the end. If you must continue before a PR merges, record the dependent branch/base and keep the dependency explicit.

## 8. What must be true before moving on

| Situation | What you do |
|---|---|
| Scaffold checked, no implementation yet | Publish scaffold; no claim that services work |
| Your unit/stub checks pass, provider absent | Mark stub verified; continue independent tasks, keep real gate incomplete |
| Your implementation test fails | Fix and rerun before the next dependent milestone |
| Provider violates agreed contract | Send owner reproduction; do not quietly rewrite their component |
| Test suite silently skips real cases | Correct the reporting/configuration; do not call integration passed |
| G1/G3 and required real correctness pass | Establish a measured B0 |
| Trial misses targets or saturates generator | Retain evidence, diagnose and report the limitation |
| Missing raw evidence | Affected metric/report is incomplete |
| Core work complete, live LLM unavailable | Finish DE deliverables; optional live-model results remain NOT_RUN |

The first day's practical target is the shared scaffold plus a small, testable J01 foundation. Your first application milestone is a deterministic workflow against explicit stubs. Your first team milestone is a real thin slice with independent reconciliation. Each has a different meaning, and the progress file should say which one has actually passed.

## 9. Status and provenance of this guide

This playbook was checked against the current ten version-2 Markdown files. It adds repository organization, smaller prompts and human checkpoints. It does not assert that any application code, GitHub scaffold, benchmark or integration test has already been executed.

The current code repository URL/path was not supplied to this conversation; the prompts deliberately use your actual clone and origin rather than assuming another repository from earlier projects.

Application implementation commands in the original runbook are contracts to implement. They become runnable as the relevant milestones and provider adapters are completed. The setup, contract, correctness and performance checks above must never be reported as passed merely because this guide lists their commands.

