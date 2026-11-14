# Jaineel's Implementation Progress Tracker

## 13 November 2026 — desktop presentation integration

User-authorized M1/M2/M3/M4/frontend integration is recorded in
[the prototype acceptance record](PROTOTYPE_INTEGRATION_2026_11_13.md): changed
paths, commands, actual outcomes, real browser purchase/Gold evidence, failed
attempts, remaining formal evaluation work and safe container cleanup.
The [professor guide](PROFESSOR_DEMO.md) supplies one-command start/stop.
Scope is desktop; no commit or push was performed.

## 13 November 2026 — retrieval integration

User-authorized retriever integration spans M1, M2 and prototype deployment.
The existing hybrid algorithm is now provisioned and selected by shopping chat.
All 19,920 active products have current embeddings; real M1/M2 HTTP checks and
the full prototype health/resource verification pass. Changed paths, exact
commands, test outcomes, failed attempts, raw evidence, limitations and manual
startup/verification are in [the integration record](RETRIEVAL_INTEGRATION_2026_11_13.md).
No commit or push was performed.

**Author:** Jaineel Vora (B24CM1080)
**Role:** M1 (Session, Cart, Assistant, Workflow) & M0 (Measurement Harness, Oracle, Dashboards, Benchmarks)
**Reference Playbook:** [10_JAINEEL_CODEX_PLAYBOOK.md](../specs/10_JAINEEL_CODEX_PLAYBOOK.md)
**Personal Brief:** [04_JAINEEL_VORA.md](../specs/04_JAINEEL_VORA.md)
**Status Date:** 11 November 2026 (Asia/Calcutta)

**Current status:** the connected fixed-mode prototype is real verified. The
complete formal M0 evaluation is still incomplete. See the
[current pending-work audit](PENDING_WORK_AUDIT_2026_11_10.md) for all J01–J07
obligations, implemented fixes and remaining owner handoffs. Historical counts
and absent-provider statements below describe their original checkpoints.
The [11 November M3 handoff checkpoint](M3_PAYMENT_HANDOFF_2026_11_11.md)
supersedes that audit's statements about boundary failures and missing core
payment controls; formal evaluation bindings and measurements remain incomplete.

> [!NOTE]
> This local progress document tracks technical milestone execution in Codex. It is separate from the academic Excel tracker. Status labels used: `not started`, `in progress`, `stub verified`, `real verified`, `blocked`.

---

## Milestone Summary

| Milestone | Deliverable | Associated Brief Task | Status | Branch | Test Mode |
|---|---|---|---|---|---|
| **P0** | Team repository scaffold and governance | Setup / Prompt 0 | real verified (local scaffold) | `jaineel/j01-foundation` | local files/Git |
| **P1** | Python tooling, CLI/config/artifact foundation | J01 | stub verified (offline checkpoint complete) | `jaineel/j01-foundation` | Python 3.11; explicit adapter doubles |
| **P2** | Conversation contract, clients, explicit stubs | J01 | stub verified (offline checkpoint complete) | `jaineel/j01-contracts` | 89 contract tests + 110 P1 regressions; explicit HTTP/SSE doubles |
| **P3** | Independent fixtures, oracle, and metric math | J01 + early J06 | stub verified; automated LLM-judge review complete; human review not performed | `jaineel/j01-oracles` | 153 focused fixture/schema tests; current P3 verifier 450 regressions; explicit fixtures/doubles |
| **P4** | Open-loop workload generation & experiment lifecycle | J02 | stub verified (offline checkpoint complete) | `jaineel/j02-workloads` | 329 combined tests; explicit publisher/API/lifecycle doubles |
| **P5** | Telemetry, raw collectors, dashboard | J03 | stub verified (offline checkpoint complete); local process collector real verified | `jaineel/j03-telemetry` | 37 telemetry tests; 488 combined; explicit doubles plus separate real generator/loopback checks |
| **P6** | Durable sessions, cart, and idempotency | J04 | real state and prototype shared-event path verified; formal fault gates pending | `jaineel/prototype-demo` | real PostgreSQL, Kafka, Registry and retained event evidence |
| **P7** | Zero-call search, quote, and checkout workflow | J04 | real connected prototype verified; formal G3 cases incomplete | `jaineel/prototype-demo` | real catalogue → M1 → Orders/Inventory/Payments → CONFIRMED → Gold; zero calls |
| **P8** | Real G1/G3 integration, failures, reconciliation | J06 | stub verified (owner harness); real gates INCOMPLETE | `jaineel/j03-telemetry` | 774 passed; real M1 PostgreSQL, explicit provider/audit/hook doubles |
| **P9** | Correct B0 and controlled performance matrix | J07 | stub verified (owner harness); real measurements NOT_RUN | `jaineel/j03-telemetry` | 823 regression passes; 49 P9 checks; real matrix dependency-blocked |
| **P10** | Reproducible report and clean setup rehearsal | J07 | owner implementation verified; real release INCOMPLETE | `jaineel/j03-telemetry` | saved-report rebuild and corruption checks; real setup blocked |
| **P11** | One-call intent fallback (optional last) | J05 | provider-spy verified under explicit sequencing exception; live quality NOT_RUN | `jaineel/j03-telemetry` | real M1 PostgreSQL; explicit model/provider doubles |

The [28 October cross-milestone review](#p1p11-pre-push-verification--28-october-2026)
is historical. Later entries record actual local PostgreSQL, live prototype and
Gold verification. The 10 November audit reconciles all related Markdown with
current code; formal correctness registrations, performance measurements and
human-reviewed assistant quality remain incomplete.

---

## Detailed Milestone Records

### Milestone P0: Team Repository Scaffold

- **State:** real verified for repository-local scaffold checks. This is not a running-service or remote-publication result.
- **Starting state:** clean `main`; existing scaffold commit `9dfdb8228fdc4900ce8e245361f8eaeb7c47a1ca` (`initialise project structure`). Origin is `https://github.com/harsh-c-16/payment-gateway.git`.
- **Working branch:** `jaineel/j01-foundation`, created locally while preserving the existing commit and all scaffold files. No commit or push performed.
- **Verified:** every directory in playbook §2 exists, all 11 numbered specifications remain unchanged, all four owners appear in ownership documentation, ignore rules protect secrets/raw data/results while allowing small CSV/JSON fixtures and `.env.example`.
- **Corrections:** portable relative links in root README, ownership and Jaineel-owned component READMEs; `.env.example` now uses the frozen B0 outbox/sink/publication/quote limits (25 ms, 1 row/50 ms, 250 ms, 60 s) and a UUID-format placeholder run ID.
- **Evidence:** scaffold/link/ignore assertions are included in [the final JUnit results](../../artifacts/p1/f0bcaae4-b8c9-4037-9aae-eea60acff2d5/pytest.xml). Git command results are recorded below and in the local session.
- **Commands:** `git status --short`, `git branch --show-current`, `git remote -v`, `git log -1 --format='%H %s'`, `git diff --stat`, `git diff --check`, `git diff --exit-code -- docs/specs`, `git check-ignore -v .env data/raw/flipkart_com-ecommerce_sample.csv benchmarks/results/probe.json`. Safe-directory config was supplied per invocation because the sandbox account differs from the checkout owner; no global Git configuration changed.
- **Results:** ignore probes matched all three paths; specs diff is empty; final whitespace check passes. Initial changed Markdown lines had trailing whitespace; fixed before completion.
- **Follow-up:** other owners' component READMEs still contain local `file:///c:/...` links from the original scaffold. Their owners should convert these to relative links before sharing across machines. Those files were preserved under the ownership boundary. Remote scaffold publication/merge and hosted CI were not verified; no push was requested.

---

### Milestone P1: Python Tooling, CLI and Artifact Foundation

- **State:** stub verified; P1 offline checkpoint complete. Local library installation is real; adapter behavior is tested with explicit doubles only. G0 and real integration remain incomplete.
- **Branch/base:** `jaineel/j01-foundation` / `9dfdb8228fdc4900ce8e245361f8eaeb7c47a1ca`.
- **Brief scope:** J01 foundation only. P2 contracts/clients, P3 fixtures/oracles and all later milestones remain not started.

**Changed files and purpose**

- Root coordination: `pyproject.toml`, `.python-version`, generated `uv.lock`, `.gitattributes`, `.github/workflows/offline.yml`, `.gitignore`, `.env.example`, `README.md`, `docs/OWNERSHIP.md`. One application lock, Python 3.11, test/lint tooling, stable LF lock bytes, offline Windows/Linux CI and scaffold corrections. No LLM/vector stack.
- `projectctl/{__init__,__main__,cli,config,models,providers,artifacts,schemas}.py` and `projectctl/README.md`: complete documented command/flag surface, strict argument/config validation, registered adapter seam, isolated run IDs/namespaces, immutable failure artifacts, canonical hashes, strict result schemas and reproducible setup instructions.
- `configs/evaluation.yaml`, `configs/core_matrix.yaml`: all required workloads/variants and matrix rows, planned resource budgets, declared faults, fixed zero-call default, independent variant controls and finite/query timing rules. C-BEST remains an unresolved measured-selection request. No experiment scheduling/execution implemented.
- `contracts/evaluation/{config,run,summary,fixture}.schema.json`: generated strict Draft 2020-12 evaluation schemas. These do not replace Vichitr's draft-07 event schemas.
- `tests/projectctl/{conftest,test_cli,test_config,test_artifacts,test_scaffold}.py`: offline validation, adapter doubles, schema/hash corruption checks, scaffold and ignore checks.
- `benchmarks/manual/verify_p1.py`: repeatable checkpoint command/output/exit evidence collector. `benchmarks/README.md`, `dashboards/README.md`, `shared/telemetry/README.md`: portable owner links only. This progress file records the checkpoint.

**Contracts consumed**

Playbook §§1–3/P1; common §§1–3 and Appendix A frozen timing limits/RunArtifactManifest; personal brief J01; evaluation §§2–4/9; runbook §§1/5/7; dataset §2's published source SHA. Provider OpenAPI/DTO/event implementation is absent and was not invented. New evaluation schema/adapter details need affected-owner G0 review.

**Actual commands and results**

Commands below ran from repository root. `python` here means `.\.venv\Scripts\python.exe`; bare host Python was 3.12.12 and was not used to claim a Python 3.11 pass.

| Command/check | Actual result |
|---|---|
| `uv python install 3.11` | Installed managed CPython **3.11.15** |
| `uv lock` | Generated `uv.lock`; **38 packages resolved** including the workspace |
| `uv sync --locked` | Created fresh `.venv`; **37 packages installed** successfully |
| Runtime imports: FastAPI, Pydantic, psycopg, confluent-kafka, jsonschema, PyArrow, DuckDB, prometheus_client, HTTPX, PyYAML, uvicorn | All imported successfully; no service/broker/DB was started |
| `python -m projectctl.schemas` / `python -m projectctl.schemas --check` | All four generated schemas valid/current; exit **0** |
| `python -m ruff check projectctl tests/projectctl benchmarks/manual/verify_p1.py` | All checks passed; exit **0** |
| `python -m ruff format --check projectctl tests/projectctl benchmarks/manual/verify_p1.py` | 15 files already formatted; exit **0** |
| `python -m pytest tests/projectctl -q --junitxml=artifacts/p1/f0bcaae4-b8c9-4037-9aae-eea60acff2d5/pytest.xml` | **108 passed in 6.22 s**; exit **0**; no skips |
| `python -m projectctl --help`, `eval run --help`, `benchmark run --help` | Help displayed; each exit **0**; all 18 action helps also exercised in pytest |
| `python -m projectctl env verify --profile local4c8g` | Missing Vichitr adapter reported; exit **4** |
| Same command with `--unknown`; `python -m projectctl env reset --namespace live` | Invalid input rejected and evidence saved; each exit **2** |
| `python -m projectctl contracts check --all` | Missing owner adapters reported; exit **4**, no compatibility pass claimed |
| `python -m projectctl eval run --suite contracts,data,smoke --config configs/evaluation.yaml` | Draft/missing providers/hashes; exit **4**; these real suites did not run |
| `python -m projectctl benchmark run --workload W-PIPE --variants B0,O1 --repetitions 3 --config configs/evaluation.yaml` | Six unique draft directories; each blocked before execution; exit **4** |
| `python -m projectctl benchmark run --workload W-IMPORT --variants I0,I1 --repetitions 1 --config configs/evaluation.yaml` | Two finite-job draft manifests with null duration denominator; exit **4** |
| `python -m projectctl benchmark matrix --matrix configs/core_matrix.yaml --config configs/evaluation.yaml` | Matrix validated; execution unavailable; exit **4** |
| `python benchmarks/manual/verify_p1.py` | **16/16 expected checkpoint outcomes matched**; collector exit **0** |
| `git diff --check`; `git diff --exit-code -- docs/specs`; `git check-attr eol -- uv.lock` | Clean diff; unchanged specs; `uv.lock: eol: lf` |

The default uv cache required access outside the sandbox. Installation/lock commands were rerun with approved escalation and succeeded; no TLS checks were disabled. Initial lint formatting findings were fixed and the final checks above passed. No assertions were weakened or tests skipped.

**Evidence paths**

- [Raw commands, stdout/stderr, expected/actual exits](../../artifacts/p1/f0bcaae4-b8c9-4037-9aae-eea60acff2d5/checks.json).
- [108-case JUnit report](../../artifacts/p1/f0bcaae4-b8c9-4037-9aae-eea60acff2d5/pytest.xml).
- [Final repository/ownership checks](../../artifacts/p1/f0bcaae4-b8c9-4037-9aae-eea60acff2d5/repository_checks.json): 34 changed paths, zero outside owned/coordinated scope, unchanged base commit/specifications and clean whitespace check.
- [Example W-PIPE B0 draft manifest](../../benchmarks/results/8287a08a-be49-4562-b32e-2b333138b606/manifest.json), [summary](../../benchmarks/results/8287a08a-be49-4562-b32e-2b333138b606/summary.json), [resolved configuration](../../benchmarks/results/8287a08a-be49-4562-b32e-2b333138b606/resolved_config.json). All six W-PIPE and both W-IMPORT paths are linked by raw stdout in `checks.json`.
- These directories are intentionally ignored and remain local. Preserve them for review; do not commit benchmark output. Raw earlier checkpoint attempts are retained in separate artifact directories.

**Truthfulness and remaining handoffs**

- No blocker remains for the P1 offline checkpoint. No provider integration, benchmark, data-profile gate, recovery gate, live model or hosted CI run passed in this milestone.
- All performance values are null/`NOT_RUN`; missing collector outputs are listed as `NOT_RUN` rather than created as fake CSV/Parquet files. Actual host resources are not claimed to match the planned profile. Unknown infrastructure/event/model locks and hardware details remain null.
- **Harsh:** canonical catalogue/SKU/facet dictionaries/manifests, data/OpenAPI/DTO contracts, catalogue/projection adapters and reviewed query/label hashes. Their configuration paths remain null pending handoff.
- **Aditya:** Orders/Inventory/Payments contracts, seeding/migration adapters and PostgreSQL 18 compatibility review. Shared outbox is still his implementation, not duplicated here.
- **Vichitr:** environment/migration adapters, enforced resource profile, image/infrastructure lock, event-schema lock/transport, Kafka/analytics services and fault barriers.
- **Jaineel later milestones:** P2 contracts/provider stubs, P3 fixtures/hash inputs/oracles, P4 lifecycle/matrix execution, later real correctness and measurement. The full raw CSV is absent locally; D-01/D-02 are `NOT_RUN`.

**Manual verification (PowerShell, repository root)**

1. Run `uv sync --locked`, then `.\.venv\Scripts\Activate.ps1` and `python --version`. Expect Python **3.11.15** on this machine (a compatible 3.11 environment on another machine). Do not use the host's 3.12 interpreter.
2. Run `python -m projectctl --help`, `python -m projectctl eval run --help`, `python -m projectctl benchmark run --help`. Each should display the runbook command/flags and exit 0.
3. Run `python -m pytest tests/projectctl -q` and `python -m projectctl.schemas --check`. Expect **110 tests passed** after the Windows temp/cache follow-up below, no skips, and current schemas.
4. Run `python -m projectctl env verify --profile local4c8g`; inspect `$LASTEXITCODE` immediately. Expect **4**, JSON naming Vichitr's missing adapter and an evidence directory. Add `--unknown` and rerun; expect **2**.
5. Open the example draft manifest/summary above. Expect unique UUID/bench namespace, full resolved controls, actual application-lock hash, null infrastructure locks, null metric values and `NOT_RUN`. No benchmark started.
6. Run `python benchmarks/manual/verify_p1.py` to save a fresh 16-check evidence bundle, then `git status --short` and `git diff --check`. Expect collector exit 0, only owned/coordinated files changed and no whitespace errors. CI runs only after a separately authorized commit/push.

**Windows temp/cache follow-up — 25 October 2026**

- **Reported failure:** the user's pasted run had 74 passing tests, 34 setup errors and two cache warnings. Every error came from `PermissionError [WinError 5]` accessing `%TEMP%/pytest-of-voraj`; cache warnings came from `.pytest_cache/v/cache`. Their checkpoint collector exited 3 because its pytest command failed. `env verify` exit 4 and unknown-flag exit 2 were expected and already correct.
- **Reproduced:** running the unmodified suite as `jaineel/voraj` reproduced 74 passed, 34 errors and two warnings. The earlier 108-test result above is retained as historical evidence from the previous execution context; it did not establish user-account portability.
- **Fix:** `tests/projectctl/conftest.py` sets new per-session temporary and cache paths under ignored `artifacts/pytest/<uuid>/` before pytest's plugins initialize. Explicit `--basetemp` and `-o cache_dir=...` overrides remain effective. Existing temp/cache directories, ACLs and prior evidence were left untouched. `projectctl/README.md` documents the behavior.
- **Regression tests:** added `tests/projectctl/test_pytest_workspace.py`. Both child-process cases use a deliberately unusable global temp location; default workspace selection and explicit directory overrides must still pass. Cache warnings are treated as errors in these regression runs. No application assertions were weakened, skipped or mocked away.
- **Actual verification:** `python -m pytest tests/projectctl -q --tb=short -W error::pytest.PytestCacheWarning` returned **110 passed in 11.54 s**, exit 0, with no warnings. `uv sync --locked` audited all 37 installed packages; no dependency/lock change was needed. The configured application-lock SHA still matches the actual `uv.lock` bytes.
- **Full checkpoint:** `python benchmarks/manual/verify_p1.py` returned exit **0**, **16/16 expected outcomes matched**. Its pytest subprocess returned **110 passed in 11.34 s**, exit 0. Lint, formatting, schema checks and all expected CLI exit-code probes passed. `git diff --check` also passes.
- **New evidence:** [full checkpoint commands/results](../../artifacts/p1/8f9a56cb-e8ae-4f2a-a832-7d22aca832ca/checks.json) and [110-test JUnit report](../../artifacts/p1/8f9a56cb-e8ae-4f2a-a832-7d22aca832ca/pytest.xml). The user's failed [earlier checkpoint](../../artifacts/p1/7410808e-11a6-4640-a09d-4acf96cb42a9/checks.json) remains preserved.
- **Commit readiness:** the P0/P1 checkpoint is ready for a local commit on `jaineel/j01-foundation` after reviewing the diff. This is not a G0, real-provider integration, hosted CI or benchmark pass. Provider handoffs above remain pending.

**Next action:** stop at P1. Begin P2 only when requested. No commit or push was performed; the user asked for commit guidance, not for this agent to commit.

---

### Milestone P2: Conversation Contracts, Clients, and Stubs

- **State:** stub verified; the P2 offline checkpoint is complete. Real provider integration is `NOT_RUN`; G0 remains incomplete. The stopped-provider check uses real TCP transport and proves failure without fallback, not a successful integration.
- **Branch/base:** `jaineel/j01-contracts` / `bca313f426de37982d986209f1763eaf399a893d` (P1 commit on local `jaineel/j01-foundation`). Working tree was clean at entry. This is a dependent local branch; no PR merge is assumed. No commit or push performed.
- **Brief scope:** J01/P2 only: contracts, consumer clients, explicit doubles and contract inventory. No P3 independent dataset/quality oracle, scheduler, persistence, workflow, business service or benchmark was implemented.
- **Authority read:** `AGENTS.md`, ownership, this progress file, personal brief J01, playbook P2; context technology/ownership/G0; common §§2–6/11.4/15 and Appendix A; evaluation §§2–4/7/9; dataset §§4–7; runbook §§1–4/7.

**Changed paths and purpose**

- `contracts/http/conversation.yaml`, `shared/contracts/conversation.py`, `projectctl/conversation_contract.py`: generated OpenAPI 3.1 for all six conversation/cart operations plus health/metrics declarations; strict M1 DTOs, version/quantity bounds, unique SKU lines, nullable display prices, explicit checkout confirmation. External catalogue and transaction schema references remain unresolved pending the owners' files.
- `shared/contracts/common.py`: coordinated initial neutral `RequestContext`, errors, UUID/UTC/strict money primitives and context-to-header mapping. No catalogue, quote, transaction or event DTO was defined. Header bindings not specified in common §2 are explicitly proposed for review.
- `services/conversation/{clients,provider_contracts}.py`: bounded real HTTP/SSE adapters and endpoint registry; catalogue search/product/facets/quote, Orders create/status/SSE and analytics manifest/Gold/receipt/quarantine/replay interfaces. Stable context/key/body on retries, overall monotonic deadlines, unknown mutation outcome on transport failure, bounded JSON/SSE buffers and explicit reconnect cursor. Provider schemas are consumed directly from merged local OpenAPI; real mode cannot inject a mock transport or provisional schema binding.
- `projectctl/contract_checks.py`, `projectctl/providers.py`: register the real offline `contracts check --all` inventory. Report absent HTTP/DTO/schema/library/health handoffs by owner and endpoint, check local conversation generation, and validate examples against provider schemas when present. Missing handoffs exit 4; incompatible examples exit 3. Presence is not runtime readiness or G0 proof.
- `contracts/fixtures/p2/{pairs.json,README.md}`, `tests/contracts/{__init__,conftest,doubles,provisional,probe,test_clients,test_contracts}.py`: 23 explicitly provisional synthetic wire examples; schemas/doubles only in tests; contract, transport, negative-corruption, owner-schema binding/drift, stopped-provider, deadline, conflict/lost-response and SSE checks. Windows temp/cache isolation is preserved for standalone contract tests.
- `benchmarks/manual/verify_p2.py`, `.github/workflows/offline.yml`: reproducible nine-command offline checkpoint, incremental raw command evidence and combined P1/P2 CI entry point. Hosted CI was not run here.
- `docs/jaineel/p2_contracts.md`, `services/conversation/README.md`, `projectctl/README.md`, this progress file: exact interfaces, provisional bindings, owner review and manual verification. No canonical spec, provider-owned path, dependency lock or evaluation configuration changed.

**Actual commands and outcomes**

All commands ran from repository root using `.\.venv\Scripts\python.exe` (CPython **3.11.15**). Bare host Python was not used for acceptance.

| Command/check | Actual result |
|---|---|
| `uv sync --locked` | Resolved 38 packages / audited 37 installed packages; exit **0**; lock unchanged |
| `python -m ruff check projectctl services/conversation shared/contracts tests/contracts tests/projectctl benchmarks/manual/verify_p1.py benchmarks/manual/verify_p2.py` | All checks passed; exit **0** |
| Same paths with `python -m ruff format --check` | **31 files already formatted**; exit **0** |
| `python -m projectctl.schemas --check` | Four P1 evaluation schemas current; exit **0** |
| `python -m projectctl.conversation_contract --check` | Owned OpenAPI current, external provider references pending review; exit **0** |
| `python -m pytest tests/contracts -q --tb=short` | Earlier P2-only run: **81 passed in 9.64 s**, exit **0**; later boundary/dialect regressions were added and are included in the final combined result below |
| `python -m pytest tests/contracts tests/projectctl -q --tb=short -W error::pytest.PytestCacheWarning --junitxml=artifacts/p2/5bfb3022-9ce7-4bb1-a1f5-c638e174fafb/pytest.xml` | Final: **199 passed in 19.41 s** (**89 P2 + 110 P1**), exit **0**, no skips/warnings |
| `python -m tests.contracts.probe --out artifacts/p2/5bfb3022-9ce7-4bb1-a1f5-c638e174fafb` | **23** stub wire pairs saved; **2** intentional corruptions rejected; real stopped-provider dependency failure observed; exit **0** |
| `python -m projectctl contracts check --all` | Expected exit **4**; explicit missing Harsh/Aditya/Vichitr handoffs; all metrics null/`NOT_RUN` |
| `python benchmarks/manual/verify_p2.py` | Exit **0**, **9/9 expected outcomes matched**; checkpoint `stub verified`, G0 `INCOMPLETE`, real integration `NOT_RUN` |
| `git diff --check`; `git diff --exit-code -- docs/specs uv.lock pyproject.toml` | Both exit **0**; no whitespace errors and those shared authorities/locks unchanged |

Implementation failures were fixed within P2. Initial SSE validation exposed a local-reference resolver pointing at an extracted schema instead of the OpenAPI components root. A later review found that an explicit `$schema` could make the validator accept `1.0` as an integer; validation now checks the supported dialect and preserves strict wire integer rules through inline/nullable/local-reference schemas. Targeted regression tests pass. Optional transport headers/query fields can no longer override operation identity or authorization. Assertions were retained, and no test was skipped to obtain a pass.

**Saved evidence (ignored local artifacts; preserve for review)**

- [Final exact commands, exits, stdout/stderr](../../artifacts/p2/5bfb3022-9ce7-4bb1-a1f5-c638e174fafb/checks.json).
- [Final 199-test JUnit report](../../artifacts/p2/5bfb3022-9ce7-4bb1-a1f5-c638e174fafb/pytest.xml).
- [23 inspected request/response pairs](../../artifacts/p2/5bfb3022-9ce7-4bb1-a1f5-c638e174fafb/request-response.jsonl): explicit stub mode, context/namespace/idempotency headers, exact JSON and SSE snapshots. Internal tokens are omitted.
- [Negative corruption evidence](../../artifacts/p2/5bfb3022-9ce7-4bb1-a1f5-c638e174fafb/negative-checks.json): `returned_cout` and string `total_amount_minor` both rejected.
- [Stopped real-provider result](../../artifacts/p2/5bfb3022-9ce7-4bb1-a1f5-c638e174fafb/real-stopped-provider.json): dependency failure, `fixture_fallback=false`, `real_integration_passed=false`.
- [Final scope and wire review](../../artifacts/p2/5bfb3022-9ce7-4bb1-a1f5-c638e174fafb/scope-review.json): **23** changed paths, no ownership violations, no trailing whitespace, no broken links in the new/updated component handoff documentation; saved inspections of catalogue, quote, Orders, analytics and SSE pairs.
- [Missing-contract manifest](../../artifacts/projectctl/f14bf1d1-7f3a-4ecc-8204-a4da7df71cf1/manifest.json) and [summary](../../artifacts/projectctl/f14bf1d1-7f3a-4ecc-8204-a4da7df71cf1/summary.json): full owner/endpoint reasons, exit 4, unknown correctness and null performance values.
- Earlier green [191-test checkpoint](../../artifacts/p2/83d6db3b-09d1-4ee3-85f4-383ee837f09e/checks.json) remains preserved; the final result supersedes it after the additional boundary/dialect fixes.

**Remaining dependencies and review**

- **Harsh:** canonical catalogue OpenAPI/DTOs, ProductHit/ShoppingIntent/Quote schema bindings, facet dictionary/manifests and all consumed examples. Nullable facets are preserved; no fictional complete catalogue or source attribute coverage is claimed.
- **Aditya:** transactions OpenAPI/DTOs, Orders acceptance/state/SSE contract, review of version/event framing and internal token headers, plus shared outbox handoff for later M1 persistence.
- **Vichitr:** analytics OpenAPI/DTOs, exact receipt/quarantine pagination item/envelope schemas, event/schema/transport/local-diagnostic interfaces, infrastructure/image locks and real environment smoke evidence.
- **Affected owners/consumers:** review the explicitly proposed namespace/request/session/trace header names, OpenAPI 3.1/local schema binding, missing model-latency representation and other underspecified details in [the P2 binding table](p2_contracts.md#review-required-before-g0-or-real-compatibility-claims). No approval or owner review is assumed, and no message was sent on the user's behalf.
- **G0 and later gates:** full dataset/profile/dictionaries, environment locks/smoke and provider compatibility remain incomplete. All real business integration, actual performance and live-model results remain `NOT_RUN`. Stop before P3.

**Concrete manual verification**

1. From repository root, run `uv sync --locked`, activate `.venv`, and verify `python --version` is 3.11. Run `python -m pytest tests/contracts -q`; expect **89 passed**. Run `python -m projectctl.conversation_contract --check`; expect exit 0.
2. Run `python benchmarks/manual/verify_p2.py`. Inspect the printed new evidence directory's `checks.json`/`pytest.xml`; expect **9/9** expected outcomes and **199 tests passed**. This is an offline/stub checkpoint.
3. Inspect one catalogue, Orders, analytics and SSE pair in `request-response.jsonl`. Quote total is integer **39900** although display price is **37900**; missing source facets/unknown stock remain explicit null; context, namespace and stable keys are visible.
4. Inspect `negative-checks.json` and `real-stopped-provider.json`. Both corruptions must be rejected; real mode must report dependency failure without a fixture. Repeat only the TCP check with `python -m pytest tests/contracts/test_clients.py::test_real_mode_stopped_provider_never_returns_fixture -q`.
5. Run `python -m projectctl contracts check --all`, then inspect `$LASTEXITCODE` immediately. Expect **4** while providers are absent; inspect the saved owner/path reasons. Obtain the owners' review from the binding table, rerun after canonical files merge, and keep G0 incomplete until its real data/environment evidence exists.

**Next action:** stop at P2. P3 is still not started. Changes remain uncommitted and unpushed.

---

### Milestone P3: Independent Fixtures, Oracle, and Metric Math

- **State:** stub verified for the offline P3 checkpoint; real independent CSV identity/count assertions verified locally. This is not a real provider, D-01/D-02 full gate, D-05 workflow or G0 pass. The subsequent authorized automated LLM-judge adjudication is complete: 29 PASS, 31 CONCERN, 0 FAIL after fixture corrections. Human review is not performed; integration, wire materialization, real intent quality and performance remain `NOT_RUN`.
- **Branch/base:** `jaineel/j01-oracles` / `a48ef864f148c4f5724844f1b77d957035fcad8c` (`convo contracts`, the user's P2 commit). The working tree was clean at entry. This is a dependent local feature branch; no upstream PR merge is assumed. No P3 commit or push was performed.
- **Scope:** J01 + early J06/P3 only. Read AGENTS, ownership, progress, personal brief, playbook P3, context technology/ownership, common event/money/inventory/ledger/Gold rules, dataset §§2–7, evaluation §§2/5/7/9 and runbook §§3/4/6/7. P4 scheduling, services, reducers, provider normalization, real evaluation cases and comparison/report execution remain outside this change.

**Changed paths and purpose**

- `benchmarks/{dataset_checks,quality,fixtures,metrics,reconciliation}.py`: read-only exact-source assertions, deterministic W-QUALITY logical expectations, immutable fixture bundles, nearest-rank/cohort/F1 helpers and independent reconciliation. No catalogue normalizer, operational producer or reducer is imported or implemented.
- `contracts/fixtures/catalog/dirty_catalogue.json`, `contracts/fixtures/assistant/scenarios.json`, `contracts/fixtures/quality/adversarial.json`, `contracts/fixtures/P3_README.md`: 33 authored synthetic dirty cases covering the 13 required families, 60 draft assistant scenarios and separate identity-collision cases. Expected projections are literal and independent of provider outputs. Catalogue bindings/relevance labels remain null; human review is explicitly pending.
- `projectctl/fixture_adapter.py`, `projectctl/providers.py`: register only the offline `fixtures build` action. It writes logical expectations and source-check evidence into a fresh bundle, leaves metrics null/`NOT_RUN` and never runs a provider or model. Config template/dictionary hashes are not silently frozen from unreviewed fixtures.
- `tests/oracles/{__init__,conftest,doubles,draft_fixtures,probe,test_dataset,test_reconciliation}.py`, `tests/benchmarks/{conftest,test_fixtures,test_metrics,test_pytest_cache}.py`: explicit evidence doubles, 23 deliberate corruption cases, immutable-input checks, draft-fixture structure/hash checks, checksum ordering, price arithmetic and hand-computed metric tests. Standalone tests retain Windows temp/cache isolation.
- `tests/projectctl/conftest.py`, `tests/contracts/conftest.py` and the new oracle/benchmark conftests: precreate the configured cache destination, avoiding a reproduced Windows/OneDrive cache-directory rename failure while preserving explicit cache/temp overrides and treating cache warnings as errors. No ACLs or existing evidence were changed.
- `benchmarks/manual/verify_p3.py`, `.github/workflows/offline.yml`: ten-command evidence collector, incremental preservation of command failures/timeouts, P1–P3 CI entry point. Hosted CI was not executed here.
- `docs/jaineel/p3_oracles.md`, `benchmarks/README.md`, `projectctl/README.md`, this progress file: detailed projection/binding limits, manual review and checkpoint commands. Canonical specifications, provider DTO/modules, `uv.lock`, `pyproject.toml` and evaluation config remain unchanged.

**Actual commands and outcomes**

All Python acceptance commands used `.\.venv\Scripts\python.exe`, CPython **3.11.15**, from repository root.

| Command/check | Actual result |
|---|---|
| `Get-FileHash data/raw/flipkart_com-ecommerce_sample.csv -Algorithm SHA256` | Exact file08 SHA **56f8f699c9e847356666c2eab3c3ab1244340f6a98ad08e39ea2199ebe993ad1** |
| `uv sync --locked` | Resolved **38**, audited **37** packages; exit **0**, lock unchanged |
| `python -m tests.oracles.draft_fixtures` | Created the small authored JSON fixtures; exit **0**. Regeneration is not human/provider approval |
| `python -m pytest tests/oracles tests/benchmarks -q --tb=short` | Initial **65 passed in 10.24 s**, exit **0**; additional review regressions are included below |
| `python -m pytest tests/oracles tests/benchmarks tests/projectctl tests/contracts -q --tb=short -W error::pytest.PytestCacheWarning` | Intermediate **267 passed in 27.69 s**, exit **0** |
| `python -m ruff check` on all P1–P3 owned source/test/collector paths listed in the checkpoint | All checks passed; exit **0** |
| Same paths with `python -m ruff format --check` | **49 files already formatted**; exit **0** |
| `python -m projectctl.schemas --check`; `python -m projectctl.conversation_contract --check` | All evaluation and conversation schemas current; both exit **0** |
| `python -m pytest tests/projectctl tests/contracts tests/oracles tests/benchmarks -q --tb=short -W error::pytest.PytestCacheWarning --junitxml=artifacts/p3/fedd90fe-be74-45fe-b1da-e65552c7f33b/pytest.xml` | Final **275 passed in 35.05 s** (**76 P3 + 199 P1/P2**); exit **0**, no skips/warnings |
| `python -m tests.oracles.probe --out artifacts/p3/fedd90fe-be74-45fe-b1da-e65552c7f33b` | **23/23** corruptions detected for the intended reason; tiny math/source checks pass; exit **0** |
| `python -m projectctl fixtures build --config configs/evaluation.yaml --seed 42` | Exit **0**; **100,000** logical W-QUALITY expectations, **60** unfrozen assistant drafts, source assertions `PASS`; no wire/API/Kafka/model execution |
| `python -m projectctl contracts check --all` | Expected exit **4**; missing provider contracts remain visible; G0 incomplete |
| `python benchmarks/manual/verify_p3.py` | Final exit **0**, **10/10 expected outcomes matched**; real integration `NOT_RUN`, human label review `PENDING` |
| `git diff --check`; `git diff --exit-code -- docs/specs uv.lock pyproject.toml configs` | Both exit **0**; authorities/locks/config unchanged |

Initial lint failures were corrected without ignoring rules. Review regressions additionally ensure duplicate reservation lines cannot hide behind dictionary comparison, simultaneous pending/success payment attempts fail, invented replenishment cannot mask stock loss, malformed IDs fail visibly and a quiesced payment cannot remain successful/unreversed. No assertion was removed or test skipped to obtain a pass.

A later checkpoint completed its assertions but failed session finalization with `WinError 5` while pytest renamed a temporary cache directory under OneDrive. The configured cache leaf is now created directly before the plugin initializes. `python -m pytest tests/benchmarks/test_pytest_cache.py tests/projectctl/test_pytest_workspace.py -q --tb=short -W error::pytest.PytestCacheWarning` passed **6 tests in 6.00 s**, including forced denied-rename doubles for all four standalone suites and the existing unusable-temp/explicit-override cases. The final full checkpoint then passed all **275** tests. Cache warnings remain errors; failed raw evidence was preserved.

**Verified facts and limits**

- The exact CSV is now present locally. Checksum acceptance precedes every exact-count assertion. Observed **20,000 × 15**, **20,000 unique observations**, **19,998 canonical listings**, **19,920 priced candidates + 78 inactive + 2 superseded + 0 mandatory rejections**, **323 unknown categories**. Retained observations are rows **3189/7770** with their file08 uniq_ids; superseded rows **9420/7723**. No stock is inferred. Provider normalization, normalized business digest and conservative facet coverage—including the four usable apparel sizes—remain `NOT_RUN`.
- W-QUALITY independently determines valid logical IDs, preceding duplicate targets and ten named 50-record invalid subcases. It conserves **98,500 + 1,000 + 500 = 100,000** without reading provider output. Logical IDs/content hashes are not runtime UUIDs/wire hashes. Fresh run identity, real SKU mapping, source coordinates and byte-identical SDK materialization are later handoffs.
- Nearest-rank p50/p95/p99 for **10,20,30,40,100 ms** is **30/100/100 ms**. Next-offset lag **25−20=5**; **100→80 ms** is **20% reduction**; **100→125/s** is **25% gain**. No timing sample yields null/incomplete. These are fixture arithmetic results, not SUT performance measurements.
- Rates distinguish physical offers/acknowledgements from unique valid active-Gold goodput, exclude warm-up/drain-only completions, retain unresolved/unknown/missing admission counts and reject incompatible clocks. Missing receipts cannot become a measured zero-admission claim. Wrong non-null slot values count as FP+FN; true-null labels do not inflate F1; all six original slots are fixed and unlabelled slots are explicitly excluded.
- All 60 assistant scenarios and all seven groups are drafted for review. Every original slot has at least ten positive draft labels, including **16 occasion labels**. Manual representative inspection corrected clear paraphrases that had initially been marked for clarification; clear requests now expect search/honest no-results with zero fallback calls, while ambiguous requests retain clarification. Labels remain unfrozen; no reviewed F1, NDCG, real extraction, provider-token usage or model latency is claimed. No relevance ground truth was generated.
- Oracle tests use explicit evidence doubles only. Reconciliation checks source/Silver/active-Gold membership, generations, content and business totals; quote/identity consistency; signed ledger and duplicate-debit effects even after reversal; payment/guard states; reservations and inventory conservation. It never repairs state. Real-mode evidence remains incomplete until approved audit/active-file export bindings exist.

**Evidence (ignored local artifacts; preserve for review)**

- [Final exact commands/stdout/stderr/exits](../../artifacts/p3/fedd90fe-be74-45fe-b1da-e65552c7f33b/checks.json), [275-test JUnit report](../../artifacts/p3/fedd90fe-be74-45fe-b1da-e65552c7f33b/pytest.xml).
- [Real independent source assertions](../../artifacts/p3/fedd90fe-be74-45fe-b1da-e65552c7f33b/dataset_checks.json), [hand-computed math](../../artifacts/p3/fedd90fe-be74-45fe-b1da-e65552c7f33b/tiny_math.json).
- [Clean explicit evidence double](../../artifacts/p3/fedd90fe-be74-45fe-b1da-e65552c7f33b/oracle_clean.json), [23 corruptions and actual failure reasons](../../artifacts/p3/fedd90fe-be74-45fe-b1da-e65552c7f33b/oracle_corruptions.json).
- [Raw dirty input/expected review examples](../../artifacts/p3/fedd90fe-be74-45fe-b1da-e65552c7f33b/fixture_review.json), [representative draft groups](../../artifacts/p3/fedd90fe-be74-45fe-b1da-e65552c7f33b/assistant_review_samples.json).
- [Fixture bundle index](../../benchmarks/results/fixtures/122d0031-99c8-4542-a4bc-1fbeaaec6ace/fixture_index.json), [W-QUALITY manifest](../../benchmarks/results/fixtures/122d0031-99c8-4542-a4bc-1fbeaaec6ace/w_quality_manifest.json), [invalid subcase recipe](../../benchmarks/results/fixtures/122d0031-99c8-4542-a4bc-1fbeaaec6ace/quality_recipe.json). The large expectation JSONL remains beside them, ignored by Git.
- [Fixture CLI run manifest](../../benchmarks/results/122d0031-99c8-4542-a4bc-1fbeaaec6ace/manifest.json), [missing-provider summary](../../artifacts/projectctl/06df556b-da90-45c1-850b-530caf4e3c14/summary.json). Performance values remain null/`NOT_RUN`.
- Earlier [268-test checkpoint](../../artifacts/p3/cf8996f3-4a5a-429f-b744-c90118277302/checks.json) is retained; final evidence supersedes it after boundary regressions.
- The [failed lint checkpoint](../../artifacts/p3/add86698-4b2e-4ba5-a79c-f447400036c1/checks.json) and [Windows cache-rename failure](../../artifacts/p3/8638cbf0-0a58-4050-8142-78be817ae764/checks.json) remain preserved. Both failures were fixed before the final accepted run.
- [Final scope and representative review](../../artifacts/p3/fedd90fe-be74-45fe-b1da-e65552c7f33b/scope_review.json): **30** changed paths, no ownership violations, trailing whitespace, broken new documentation links or forbidden producer/reducer imports. Four dirty examples and all seven draft scenario groups were inspected; human label review remains pending.

**Remaining handoffs**

- **Harsh:** reviewed dirty-field/issue projections, canonical normalized business digest, dictionary/SKU/facet manifests, real size-SKU bindings, human review of draft intent labels and manually judged retrieval pools. Independent source assertions do not prove his importer passes D-01/D-02/D-03.
- **Aditya:** approved read-only order/quote/reservation/stock/payment/guard/signed-ledger exports and audit provenance. No real inventory race, response-loss recovery or cancellation gate was executed.
- **Vichitr:** canonical event SDK/schema/registry and exact invalid-wire examples; source-coordinate disposition exports, active-file/receipt membership proofs, generation/hash/query row bindings and infrastructure locks. W-QUALITY has not been emitted to Kafka or reconciled against real Silver/Gold.
- **Jaineel later milestones:** bind reviewed real exports before lifting the real-mode incomplete gate; freeze labels only after actual human review; implement scheduling/lifecycle in P4. `benchmark reconcile`, comparison/report execution and the real D/T suites remain later work. G0 remains incomplete.

**Concrete manual verification and suggested commit**

1. From `payment-gateway/`, run `uv sync --locked` and `uv run --locked python -m pytest tests/oracles tests/benchmarks -q`; expect **76 passed** with the present P3 tree.
2. Run `uv run --locked python benchmarks/manual/verify_p3.py`; inspect the printed evidence directory's `checks.json`/`pytest.xml`. Expect **10/10** matched outcomes and **275 tests passed**. Missing provider contracts exit 4 as an expected dependency condition.
3. Inspect `tiny_math.json`, `fixture_review.json`, `oracle_corruptions.json` and `dataset_checks.json`. Check the exact examples/counts above and that corruptions fail for their named reason. Review all 60 source scenarios before freezing; representative samples alone do not constitute label approval.
4. Run `uv run --locked python -m projectctl fixtures build --config configs/evaluation.yaml --seed 42`. Inspect its bundle's manifest hashes/recipe and `wire_materialization=NOT_RUN`. Do not commit the generated bundle, raw CSV or evidence directories.
5. Review `git status --short`, `git diff --check` and the complete intended source diff. Suggested message: **`feat: implement P3 fixtures, oracle and metric helpers`**. Stage only the owned/coordinated P3 paths listed above; run `git diff --cached --check` and `git diff --cached --stat` before committing. No Git commit/push command was executed by this task.

**Next action:** stop at P3. P4 is not started. Changes remain uncommitted and unpushed.

---

### P3 evaluation-only follow-up: 25 October 2026

- **Scope:** evaluation and automated semantic review only. Entry tree clean on `jaineel/j02-workloads`, commit `e47de1a24ad6c1457e8ad88914f234feeb92ce61`. Existing P4 work was preserved; no P4/P5 implementation, verifier or performance experiment was started. The unchanged P3 verifier includes existing P4 regression tests in its broad suite.
- **Source change:** this progress file only. Fresh ignored evidence was written under `artifacts/p3-evaluation/8f0bbc77-d58a-4a75-875b-7f23114835b7/`, plus the verifier's fresh P3 evidence and offline fixture bundle. No production/provider code, labels, canonical specifications, config or prior fixture bundle was edited. No commit or push performed.
- `human_label_review = AUTOMATED_REVIEW_COMPLETE_PENDING_JAINEEL_APPROVAL`
- **Checkpoint interpretation:** P3's offline implementation, source accounting and explicit-double oracle are verified. The final label checkpoint is **not complete**: automated review found semantic and workflow issues; human approval, provider bindings, real D-05/integration and performance remain pending/`NOT_RUN`.

**Actual commands and results**

All Python commands used `.\.venv\Scripts\python.exe` (CPython 3.11.15) from `payment-gateway/`. Exact argument lists, stdout, stderr and exit codes are retained in [commands.json](../../artifacts/p3-evaluation/8f0bbc77-d58a-4a75-875b-7f23114835b7/commands.json).

| Command/check | Actual result |
|---|---|
| `python benchmarks/manual/verify_p3.py` | Exit **0**, **10/10** expected outcomes matched; **329 passed in 53.36 s**, **0 failed**, **0 errors**, **0 skipped** |
| `python -m pytest tests/oracles tests/benchmarks/test_fixtures.py tests/benchmarks/test_metrics.py tests/benchmarks/test_pytest_cache.py -q --tb=short -W error::pytest.PytestCacheWarning --junitxml=artifacts/p3-evaluation/8f0bbc77-d58a-4a75-875b-7f23114835b7/p3-tests.xml` | Exit **0**, **76 passed in 12.48 s**, **0 failed**, **0 skipped**; this rerun overlaps the broad suite, giving **329 distinct tests / 405 test executions** |
| Verifier's `python -m tests.oracles.probe --out artifacts/p3/87871a89-1fa6-41e4-8a7c-db2ad81bedd1` | Exit **0**; clean explicit-double control passed; **23/23** corruptions detected for their intended invariant reason |
| Verifier's `python -m projectctl fixtures build --config configs/evaluation.yaml --seed 42` | Exit **0**; new offline bundle `benchmarks/results/fixtures/2f6ecb04-90b7-41a3-a47b-9f5c7c7b7e43/`; wire/API/model execution `NOT_RUN` |
| Verifier's `python -m projectctl contracts check --all` | Expected exit **4**; actual provider contracts/bindings missing; G0 remains `INCOMPLETE` |
| `python artifacts/p3-evaluation/8f0bbc77-d58a-4a75-875b-7f23114835b7/complete_review.py` | Exit **0**; independent CSV accounting, four dirty examples, all **60 scenarios / 840 review criteria**, **19/19** metric checks, oracle-result inspection and fixture hash checks saved |

**CSV, fixtures, metrics and oracle inspection**

- Both available CSV copies match SHA-256 **`56f8f699c9e847356666c2eab3c3ab1244340f6a98ad08e39ea2199ebe993ad1`**, each **38,114,963 bytes**. Independent read-only accounting confirms **20,000 = 19,920 active + 78 inactive missing-price + 2 superseded + 0 mandatory rejected**, **19,998 canonical rows**, **15 columns**, and **20,000 unique observations**. The probe also confirms **323 unknown categories** and the exact selected duplicate observations. Full normalization/facet-coverage comparison remains `NOT_RUN`.
- Inspected `fixture_review.json`: sale 379 rupees becomes **37900**, retail 999 becomes **99900**; a missing sale price remains **null/inactive** despite retail price; the newer duplicate wins; missing size/colour/material stay **null** and do not match size M. These four examples are literal partial expectations from the **33-case** dirty fixture, not a provider normalization result.
- Inspected `tiny_math.json` and ran supplemental independent examples: nearest-rank **p50=30, p95=100, p99=100 ms** for `[10,20,30,40,100]`; descending 100..1 gives **50/95/99**; Kafka lag **25-20=5**, two-partition sum **8**; latency reduction **20%**; throughput gain **25%**. Baseline-zero percentages remain undefined/null. Missing/unresolved timing stays **null/INCOMPLETE**; actual unexecuted CLI metrics stay **null/NOT_RUN** with zero samples. No missing sample is converted to zero. The separate INR example **1,000 rupees = 100000 minor units** passes. These are arithmetic checks, not SUT measurements.
- Inspected all **23** corruption records, confirming the actual failing invariant includes the intended code. Coverage includes missing IDs, duplicate Silver/source/Gold effects, wrong dispositions/content, Gold monetary/business rows/visibility, stale generations/hashes/source references, quote/order mismatch, duplicate reversed debits, stock loss/illegal states, payment/currency/cancellation conflicts, reservation items/duplicate lines, overlapping attempts and invented replenishment. Real provider reconciliation remains `NOT_RUN`.
- Assistant fixture SHA-256 remains **`9875444a2586a0ba5ecfd8912d278a1cf591a97ad6a12fd4dfff47b0d22741bb`**. W-QUALITY logical hash remains **`e02076acd38846ab374b8717f1688348f0d4f655b7f4c20c8f5d5531ecf06cd1`**. No final fixture hash changed; original fixture review status remains `awaiting_human_review` and `frozen=false`.

**Automated semantic label review: 13 PASS / 45 SUSPICIOUS / 2 FAIL**

Every row in the [complete readable review](../../artifacts/p3-evaluation/8f0bbc77-d58a-4a75-875b-7f23114835b7/label_review.md) and [JSON review](../../artifacts/p3-evaluation/8f0bbc77-d58a-4a75-875b-7f23114835b7/label_review.json) contains the ID, exact user request, all six original expected slots, workflow outcome, result, exact reasons, unapplied suggested corrections and decision requirement. The JSON additionally records all 14 criteria per scenario. **PASS is an automated finding, not human approval.**

| Scenarios | Result and exact issue requiring review |
|---|---|
| **A-024, A-028** | **FAIL:** `XXXXXL` is outside the canonical apparel vocabulary. The user explicitly asks for clarification, while the outcome also permits no-results. Decide how to preserve the raw unresolved constraint with canonical size null and require clarification; do not silently drop the requested constraint. No correction applied. |
| **A-001–A-012, A-015** | **SUSPICIOUS:** `under`/`below` can denote a strict cap; the label records a maximum without specifying equality behavior. Amount conversion is correct. Approve an explicit boundary convention or clearer wording; this is a semantic ambiguity, not a proven money-conversion error. |
| **A-021–A-023, A-025–A-027** | **SUSPICIOUS:** concrete hard filters are labelled only `honest_no_results_or_clarification`, permitting unnecessary clarification and excluding successful search without a snapshot proving no matches. Compound material/colour labels themselves are preserved correctly. |
| **A-029–A-034** | **SUSPICIOUS:** untrusted instructions correctly confer no purchase/price authority, but verified displayable hits and the injected listing are unbound. These also use the ambiguous `under` price wording. Bind a reviewed explicit backend response before claiming display behavior. |
| **A-041–A-052** | **SUSPICIOUS:** control-marker text lacks concrete action inputs and pre-state/backend evidence. Confirmed checkout **A-043/A-049** declares confirmation and quote/version binding, but supplies no actual quote/version/confirmation IDs. Unconfirmed **A-044/A-050** correctly requires no purchase. Each row lists its missing payload/state. |
| **A-053, A-054, A-057, A-058** | **SUSPICIOUS:** generic request/outcome does not distinguish search 503 from order-status 503, identify targets, or justify a pending-state branch. Specify exact actions, failures and known state. |
| **A-055, A-059** | **SUSPICIOUS:** response loss is assigned to `order_status`; this cannot establish lost order-creation response recovery. Decide which operation is intended and bind its identity/retry/status evidence. |
| **A-056, A-060** | **SUSPICIOUS:** analytics-only outage must not itself invent an Orders dependency failure/pending status. Bind a healthy Orders snapshot and verify its authoritative status remains available, with analytics failure recorded separately. |

- Original positive counts: **category 28, size 16, colour 16, material 16, max_price_minor 22, occasion 16**. Excluding the two invalid size values leaves **14 valid size positives**. Every original slot meets the planned **10-positive numeric minimum**, but labels are not ready for final F1 until issues and human approval are resolved. There are only **33 distinct request strings**, two categories, correlated size/colour templates and repeated fault/control cases; counts alone do not establish diversity.
- Category-ambiguous `medium` appears in **A-014/A-016/A-018/A-020/A-035–A-040** and correctly retains null size with clarification. In A-018, “whether I mean clothing” is a category to confirm, not an asserted category. Unsupported-size ambiguity is **A-024/A-028**. Budget-bound ambiguities and unsupported/unverifiable outcome assumptions are enumerated in the summary.
- All **60** rows have optional brand/path fields **null**; **0** scenarios use positive optional brand/category-path labels. Optional slots are excluded from the original six-slot metric. All catalogue/relevance bindings remain null, and real extractor F1/workflow success were not run.
- Provenance review found only `copy`, `json` and `pathlib` imports in the fixture author, with no production parser import. Labels appear machine-drafted alongside template text, rather than derived from production parser output. Current static code cannot prove complete historical provenance; generator-equality tests establish consistency, not semantic correctness or independent human approval. This review used request text/specifications, never current parser behavior as proof.

**Fresh evidence and remaining dependencies**

- [Evaluation summary](../../artifacts/p3-evaluation/8f0bbc77-d58a-4a75-875b-7f23114835b7/evaluation_summary.json), [verifier output](../../artifacts/p3-evaluation/8f0bbc77-d58a-4a75-875b-7f23114835b7/verifier_output.json), [verifier commands](../../artifacts/p3-evaluation/8f0bbc77-d58a-4a75-875b-7f23114835b7/verifier_checks.json), [test counts and IDs](../../artifacts/p3-evaluation/8f0bbc77-d58a-4a75-875b-7f23114835b7/test_results.json), [329-test JUnit](../../artifacts/p3-evaluation/8f0bbc77-d58a-4a75-875b-7f23114835b7/verifier-tests.xml), [76-test JUnit](../../artifacts/p3-evaluation/8f0bbc77-d58a-4a75-875b-7f23114835b7/p3-tests.xml).
- [Label-review summary](../../artifacts/p3-evaluation/8f0bbc77-d58a-4a75-875b-7f23114835b7/label_review_summary.json), [metric checks](../../artifacts/p3-evaluation/8f0bbc77-d58a-4a75-875b-7f23114835b7/metric_checks.json), [CSV checksum/accounting](../../artifacts/p3-evaluation/8f0bbc77-d58a-4a75-875b-7f23114835b7/csv_accounting.json), [corruption results](../../artifacts/p3-evaluation/8f0bbc77-d58a-4a75-875b-7f23114835b7/oracle_corruption_results.json), [dirty-case inspection](../../artifacts/p3-evaluation/8f0bbc77-d58a-4a75-875b-7f23114835b7/fixture_inspection.json), [inspected file paths/hashes](../../artifacts/p3-evaluation/8f0bbc77-d58a-4a75-875b-7f23114835b7/inspected_references.json), [fixture hash checks](../../artifacts/p3-evaluation/8f0bbc77-d58a-4a75-875b-7f23114835b7/fixture_hash_checks.json). Raw `tiny_math.json`, `fixture_review.json`, `dataset_checks.json`, `oracle_clean.json` and `oracle_corruptions.json` are copied unchanged into this directory.
- Original fresh verifier evidence remains at `artifacts/p3/87871a89-1fa6-41e4-8a7c-db2ad81bedd1/`. Baseline tracked-file hashes and final scope/evidence validation are retained in the evaluation directory. Evidence and raw data remain ignored local files.
- **Harsh:** reviewed dictionary/facet/catalogue snapshot, canonical catalogue/quote API contracts and real normalization comparison. **Aditya:** concrete quote/order/confirmation/status and audit bindings, canonical transaction contracts/shared outbox. **Vichitr:** canonical event/transport schemas, wire materialization and real source/Silver/Gold membership evidence. **Jaineel:** all-scenario human adjudication, precise workflow fixtures and later approved label freeze. These dependencies are visible; no missing module was replaced or real integration mocked.

**Manual approval and reproducibility steps**

1. Open `label_review.md` and `label_review.json`; inspect each request, six slots, all criteria and expected outcome. Make an explicit decision on each SUSPICIOUS/FAIL suggestion. None has been applied.
2. Approve the budget-bound convention, unknown-size handling, exact no-results versus clarification expectations, confirmation/pre-state payloads, response-loss operation and analytics isolation. Verify real dictionary/snapshot facts with owners; use explicitly labelled doubles where real dependencies are unavailable.
3. Inspect the CSV hash/equation, `tiny_math.json`, all four `fixture_review.json` cases and each named corruption failure. Reproduce using the two exact verifier/pytest commands above; each verifier run creates fresh evidence.
4. Final completion requires Jaineel's actual human review and separate authorization for any fixture edits/refreeze/hash change. Keep `human_label_review` at **AUTOMATED_REVIEW_COMPLETE_PENDING_JAINEEL_APPROVAL** in the meantime. This evaluation does not set it to COMPLETE.
5. Review `git diff -- docs/jaineel/progress.md`, `git diff --check` and `git status --short`. If later committing this documentation-only result, suggested message: `docs: record P3 evaluation and automated label review`; stage only `docs/jaineel/progress.md` and inspect `git diff --cached --check` before committing. No commit/push was run here.

**Next action:** stop after this evaluation. Preserve findings and hashes; await Jaineel's label decisions. P4/P5 work was not modified or advanced.

---

### P3 authorized fixture correction and LLM-judge adjudication: 25 October 2026

The user subsequently authorized Codex to judge every scenario, choose defensible executable expectations and apply corrections without human adjudication. This supersedes the prior evaluation-only restriction on editing labels and hashes; the earlier report and its findings remain historical evidence. The current branch remains `jaineel/j02-workloads` at `e47de1a24ad6c1457e8ad88914f234feeb92ce61`; the existing progress edit was preserved at entry. No production/provider code or P4/P5 implementation was changed, and no commit/push was performed.

- `automated_llm_judge_review = COMPLETE`
- `human_label_review = PENDING_NOT_PERFORMED`
- **Actual judgment:** all **60** scenarios adjudicated; deterministic fixture consistency **60 PASS**; qualitative LLM judgment **29 PASS / 31 CONCERN / 0 FAIL**, with confidence HIGH for the 29 clear cases and MEDIUM for the 31 cases retaining alternative readings. Codex in this conversation supplied the judgment; no external model provider or runtime LLM call was added or invoked.
- **Limit:** this completes the requested automated review. It does not satisfy the runbook's separate human-reviewed final W-AGENT requirement, constitute human approval, or establish real-world intent quality. The source fixture remains `review_status=awaiting_human_review`, `frozen=false`, with null human reviewer/review timestamp/relevance labels and real catalogue binding. Real provider/dictionary review, D-05 execution and actual F1 remain pending/`NOT_RUN`.

**Corrections and documented decisions**

- **A-001–A-012, A-015, A-029–A-034:** strict `under/below R rupees` means `price_minor < R*100`. Encode it in the inclusive integer `max_price_minor` ceiling as **R*100-1**, so under 500 is **49999**, not 49900 or 50000. `At most`, `within a budget`, and `or less` remain inclusive (**50000**). No normative natural-language inclusive override was found. This changes 19 budget labels and does not change a production parser/API.
- **A-024/A-028:** replace unsupported canonical size `XXXXXL` with null, preserve its exact raw value in `unresolved_constraints`, require targeted clarification and forbid search before resolution. A valid but unavailable size remains a hard filter; it is not rewritten to null.
- **All search expectations:** bind a labelled synthetic catalogue/dictionary/view by SHA-256, preserve all hard filters, and assert literal eligible fixture SKU sets. Matching fixtures yield verified fixture facts; an empty or missing-facet view yields honest no-results. Dependency failure remains distinct from an empty response. Occasion remains semantic query text, not a universal hard catalogue field; no relevance rankings are manufactured. Pairs A-021/A-025, A-022/A-026 and A-023/A-027 now exercise matching versus missing/empty views with identical intent labels.
- **A-029–A-034:** bind the malicious description to a returned synthetic SKU as untrusted data, retaining its authoritative fixture price. Explicit expectations forbid instruction execution, price mutation and cart/quote/checkout/order actions.
- **A-041–A-052:** replace control-marker prose with explicit requests and concrete synthetic identities/state. Cover one cart effect for identical retries, authoritative quote totals despite stale display prices, valid 60-second quotes, exact cart-version and explicit confirmation bindings, rejection of unconfirmed checkout, stale-cart 409 before Orders, and authoritative status snapshots. Transaction totals remain transaction facts; they do not invent search-budget labels.
- **A-053/A-057 and A-054/A-058:** identify catalogue search 503 versus Orders status GET 503, including attempted HTTP operation, known/unknown state and safe response. Missing current status remains unknown; unavailable search does not imply an empty catalogue.
- **A-055/A-059:** split ambiguous original response-loss cases into confirmed POST creation-response loss versus GET status-read loss. Pin a two-step synthetic script: same create body/context/idempotency key recovers one PENDING order; a lost GET retries the same read without order creation. All checkout IDs/quote/cart/confirmation inputs are concrete.
- **A-056/A-060:** healthy Orders returns its pinned CONFIRMED/CANCELLED snapshot despite analytics outage, with **zero analytics calls**. Terminal status derives from that synthetic response, not from the fault.
- **All 60 audit rows** retain original request/labels/outcome and full original scenario, revised request/labels/outcome and scenario digest, changed fields with before/after values, issue categories, deterministic result, LLM result, rationale/specification references, confidence, alternative interpretations and selected decisions. No history was erased. Original author behavior remains available as `original_assistant_scenarios()`; the existing fixture author now emits the v2 expectations.

**Hashes and coverage**

| Fixture identity | SHA-256 |
|---|---|
| Original bytes at this task's entry (CRLF), archived exactly in `history/scenarios-v1.json` | `071543c610d110fb342fed757fa56320136a46fc64a2561c9692bdc3d24c8dba` |
| Original LF-normalized bytes, matching the prior evaluation hash | `9875444a2586a0ba5ecfd8912d278a1cf591a97ad6a12fd4dfff47b0d22741bb` |
| Revised v2 fixture bytes (LF) | `441c5becdcd7462972027f567c6cc419010d1b5770d21a3ae4ce85ead1f9dac9` |

The original current JSON and prior evaluated JSON are semantically identical; the different original byte hashes come only from CRLF versus LF. The audit records both byte and normalized hashes so platform checkout conversion is not confused with label changes. The W-QUALITY logical fixture is unchanged.

Valid positive counts are **category 28, size 14, colour 16, material 16, max_price_minor 22, occasion 16**: every original slot meets the minimum **10**. Optional **brand=0**, **category_path_prefix=0**, all null and excluded from six-slot F1. There are **21 scenarios with corrected slot values** and **38 revised workflow outcomes**; IDs remain exactly A-001–A-060. Repeated templates and limited categories remain a coverage limitation, not evidence of general intent quality.

**Exact changed paths for this adjudication**

- `contracts/fixtures/assistant/scenarios.json`: corrected six-slot expectations, explicit outcomes, synthetic data/bindings and workflow/fault state.
- `contracts/fixtures/assistant/history/scenarios-v1.json`: preserved original bytes and labels.
- `contracts/fixtures/assistant/adjudication-v2.json`: all 60 machine-readable decisions, before/after history, hashes and concerns.
- `contracts/fixtures/assistant/review-v2.md`: readable per-scenario LLM-judge report with original/revised slots, outcomes and rationale.
- `contracts/fixtures/assistant/scenario.schema.json`: test-only fixture envelope, allowed canonical size vocabulary, null optional labels and honest review metadata.
- `tests/oracles/assistant_revision.py`: authored v2 fixture construction and recorded judgments, independent of production parsers/providers.
- `tests/oracles/draft_fixtures.py`: retain v1 author and route current assistant-fixture generation through v2.
- `tests/benchmarks/test_assistant_revision.py`: **121** added parameterized regression checks for requests/slots, pinned matches/nulls, boundaries, size clarification, structured workflow schemas, confirmation, fault distinctions, hash/audit consistency and invalid fixture rejection.
- `docs/jaineel/progress.md`: this P3 record and P3 status only. The P4/P5 sections remain unchanged.

**Actual checks and evidence**

Commands used `.\.venv\Scripts\python.exe` from `payment-gateway/`. Fresh local evidence: `artifacts/p3-adjudication/5e39c423-52b1-41ad-a3db-859bf74e64e1/`.

| Command/check | Actual result |
|---|---|
| `python -m pytest tests/benchmarks/test_assistant_revision.py tests/benchmarks/test_fixtures.py tests/contracts/test_contracts.py -q --tb=short -W error::pytest.PytestCacheWarning --junitxml=artifacts/p3-adjudication/5e39c423-52b1-41ad-a3db-859bf74e64e1/focused-tests.xml` | **153 passed in 20.16 s**, **0 failed / 0 errors / 0 skipped**, exit **0** |
| `python -m ruff check tests/oracles/assistant_revision.py tests/oracles/draft_fixtures.py tests/benchmarks/test_assistant_revision.py` and corresponding `ruff format --check` | Final checks exit **0**; all three files formatted. Initial line-length diagnostics were fixed; initial and intermediate lint output is retained. No test assertion was weakened. |
| Inline regeneration check: `assistant_scenarios()` and all 60 `judge(original,revised)` results versus persisted JSON | Exact equality after formatting; exit **0** |
| `python benchmarks/manual/verify_p3.py` | Exit **0**, **10/10** expected outcomes; **450 passed in 57.79 s**, **0 failed / 0 errors / 0 skipped**. The unchanged verifier includes pre-existing broader regressions; no P4/P5-specific verifier was run. |
| Verifier schema commands: `python -m projectctl.schemas --check`, `python -m projectctl.conversation_contract --check` | Both exit **0**; no canonical/provider schema changed |
| Verifier probe and fixture build | Probe exit **0**: **23/23** intentional oracle corruptions detected, source accounting **PASS**, tiny math **PASS**. Fresh offline fixture bundle `benchmarks/results/fixtures/40aca189-f341-4226-bf6e-c9ad07f78596/`; wire/API/model execution remains `NOT_RUN`. |
| Verifier `python -m projectctl contracts check --all` | Expected exit **4**, missing owner contracts remain explicit; G0 `INCOMPLETE`, real integration `NOT_RUN` |

The focused 153 tests overlap the 450-test verifier suite; these are **450 distinct tests**, not 603 distinct tests. The source/provider tests use explicitly provisional consumer schemas where canonical owner contracts are unavailable. These validate authored fixture shapes and expectations, not actual provider behavior.

- [Readable report](../../contracts/fixtures/assistant/review-v2.md), [per-scenario audit](../../contracts/fixtures/assistant/adjudication-v2.json), [corrected scenarios](../../contracts/fixtures/assistant/scenarios.json), [original fixture](../../contracts/fixtures/assistant/history/scenarios-v1.json).
- [Focused command outputs](../../artifacts/p3-adjudication/5e39c423-52b1-41ad-a3db-859bf74e64e1/focused-checks.json), [153-test JUnit](../../artifacts/p3-adjudication/5e39c423-52b1-41ad-a3db-859bf74e64e1/focused-tests.xml), [final lint checks](../../artifacts/p3-adjudication/5e39c423-52b1-41ad-a3db-859bf74e64e1/lint-final.json), [verifier output](../../artifacts/p3-adjudication/5e39c423-52b1-41ad-a3db-859bf74e64e1/verifier-run.json), [all verifier commands](../../artifacts/p3-adjudication/5e39c423-52b1-41ad-a3db-859bf74e64e1/verifier-checks.json), [450-test JUnit](../../artifacts/p3-adjudication/5e39c423-52b1-41ad-a3db-859bf74e64e1/verifier-tests.xml), [test counts](../../artifacts/p3-adjudication/5e39c423-52b1-41ad-a3db-859bf74e64e1/test_results.json).
- Original verifier evidence remains at `artifacts/p3/842bfd22-7966-4bca-a19b-f19a8bf547eb/`. Prior evaluation evidence is preserved; final scope/hashes/link verification is recorded in the new adjudication evidence directory.

**Unresolved concerns and remaining limits**

- **19 budget-language concerns:** A-001–A-012, A-015, A-029–A-034. Literal strictness is selected as instructed; colloquial inclusive budget language remains a reasonable real-world reading.
- **10 intentional medium/category ambiguities:** A-014/A-016/A-018/A-020/A-035–A-040. Apparel M versus a non-apparel dimension remains unresolved; the executable expectation is targeted clarification without search.
- **2 historical operation ambiguities:** A-055/A-059. Original author intent cannot be recovered from the conflicting generic fault/control; the revised explicit wording deterministically covers POST creation loss and GET status loss separately.
- **Provider handoffs:** synthetic fixtures do not replace Harsh's actual dictionary/catalogue snapshot or canonical quote contract, Aditya's transaction/status bindings, or Vichitr's event/analytics integration. Human review and real-world intent quality remain unperformed. No runtime LLM calls, production service changes or new provider implementations were introduced.

**Next action:** stop after this P3 adjudication. No P4/P5 work, commit or push. The requested automated correction/review is complete with the concerns above retained explicitly.

---

### P3 commit finalization: 25 October 2026

- **Authorization/scope:** user requested inspection and commit of the nine P3 adjudication paths with message `test: adjudicate assistant fixtures with automated model review`. Entry branch `jaineel/j02-workloads`, HEAD `e47de1a24ad6c1457e8ad88914f234feeb92ce61`; all nine intended source paths were reviewed. Generated evidence/results and secrets are excluded from staging. No P4/P5 implementation was started.
- `automated_llm_judge_review = COMPLETE`
- `human_label_review = PENDING_NOT_PERFORMED`
- **Boundary verification:** with inclusive `price_minor <= max_price_minor`, integer `price_minor < 50000` is exactly equivalent to `price_minor <= 49999`. The affected test accepts 49999, rejects 50000 for under 500, and retains 50000 for at most 500. Common section 4 names a maximum and section 10 preserves hard filters; neither explicitly writes the comparison operator. No contradictory normative rule was found. **Remaining contract clarification:** Harsh (catalogue contract owner) and Jaineel (consumer) should confirm `<=` explicitly in the canonical catalogue handoff. This fixture interpretation does not change a shared/public contract.
- **Concerns retained:** all **31** full CONCERN records are identical to the preceding adjudication, including alternatives, selected interpretation, MEDIUM confidence and rationale. All 60 labels, outcomes, scenario payloads and their canonical digests remain unchanged by finalization.
- **Hash distinction added to the audit/report:** exact file bytes, CRLF-to-LF-normalized bytes, canonical compact/sorted UTF-8 JSON content, and manifest canonical content excluding its self-hash are separate domains. Original raw `071543c610d110fb342fed757fa56320136a46fc64a2561c9692bdc3d24c8dba` and LF `9875444a2586a0ba5ecfd8912d278a1cf591a97ad6a12fd4dfff47b0d22741bb` remain recorded; original canonical content is `682532cb6deb5f383b49a8db7ba92524a4765579310c99be83128322a9b5e3d1`. Revised raw/LF remains `441c5becdcd7462972027f567c6cc419010d1b5770d21a3ae4ce85ead1f9dac9`; revised canonical content is `f06cffbef1ed8db709640ac65cc6609a13b9949d54aed7a6599c0b99997253df`.
- **Manifest association verified:** revised bundle `benchmarks/results/fixtures/40aca189-f341-4226-bf6e-c9ad07f78596/` records the revised raw hash in its `fixture_index.json` artifact reference and `w_quality_manifest.json` source reference; the copied scenario JSON has the same canonical content as the current fixture. **Eight historical bundles** retain their own old copied scenarios, artifact/source hashes and content. Historical source paths/checksums identify bytes at the time of those runs; they must not be compared with today's mutable source path and relabelled. Existing result files were not modified.
- **Configuration verification:** `configs/evaluation.yaml` remains draft, with W-AGENT `template_sha256`, generator `template_sha256` and retrieval `label_sha256` all null; there is no stale old assistant hash to replace. W-AGENT's future frozen template hash identifies the generated logical workload recipe (including templates/seed/protocol), not the raw scenario file. Retrieval-label hashes are separate. Finalization does not falsely freeze an unreviewed benchmark configuration. Exact reference paths, hash domains and observed values are added to `reference_verification` in the audit.
- **Additional edits within the existing nine paths:** only `adjudication-v2.json` reference/hash metadata, `review-v2.md` explanatory text, `test_assistant_revision.py` concern/reference regression assertions and this P3 progress entry. The other five intended files were inspected and left unchanged by finalization.
- **Affected checks actually run:** `python -m ruff check tests/benchmarks/test_assistant_revision.py` and `python -m ruff format --check tests/benchmarks/test_assistant_revision.py`, both exit **0**. `python -m pytest tests/benchmarks/test_assistant_revision.py -q --tb=short -k "adjudication_preserves_history or audit_hash_domains or price_boundaries" --junitxml=artifacts/p3-finalization/16361b7a-26da-4c89-9336-3ef7885c0d36/affected-tests.xml`: **3 passed, 119 deselected in 0.52 s**, exit **0**, no failed/errored/skipped tests. Deselection is intentional selection of affected checks, not a skipped dependency/test. One reference/hash-domain regression was added (122 cases now in that module). The previously passing 153-test focused suite and 450-test verifier are preserved as prior evidence; neither full suite was repeated.
- **Final checks/staging:** validate original/revised/canonical hashes, all concerns and bundle/config references; ensure changes stay within the exact nine-path allowlist; run `git diff --check`, stage those paths explicitly, inspect `git diff --cached --check` and staged paths, then commit with the requested message. Staged fixture blobs are checked using LF-normalized and canonical identities because Git `core.autocrlf=true` normalizes text. Human review remains unperformed; real provider quality, real integration and performance remain `NOT_RUN`.
- **Evidence:** [affected commands/output](../../artifacts/p3-finalization/16361b7a-26da-4c89-9336-3ef7885c0d36/affected-checks.json), [affected JUnit](../../artifacts/p3-finalization/16361b7a-26da-4c89-9336-3ef7885c0d36/affected-tests.xml). The same ignored directory preserves entry hashes, final reference/scope checks and the resulting commit identity. Original adjudication and evaluation evidence remain preserved.

**Next action:** commit only the reviewed nine P3 paths as authorized, report the commit hash and the comparator clarification, then stop. No push or P5 work is authorized in this turn.

---

### Milestone P4: Open-Loop Workload Generator & Lifecycle

- **State:** stub verified; P4/J02 offline checkpoint complete. All provider integration, real G1 and performance results remain `NOT_RUN`. P5 is not started.
- **Branch/base:** `jaineel/j02-workloads` / `dce94847114fe5263e402e3fecdd8925efb22b10` (`feat: implement P3 fixtures, oracle and metric helpers`). Clean working tree at entry; created this dependent local feature branch without assuming an upstream merge. No commit, push, reset or provider startup performed.
- **Authorities read:** AGENTS, ownership, this progress file, personal brief J02, playbook P4, context/technology freeze, common IDs/money/time, HTTP/provider/event/producer bounds; evaluation workloads/protocol/metrics/artifacts; runbook §§1/5/7 and dataset identity/mapping/manifest rules. Canonical specs and teammates' implementations/contracts remain unchanged.

**Changed paths and purpose**

- `benchmarks/{__init__,workloads,scheduler,experiment,planning,drivers}.py`: immutable logical workloads, fixed open-loop scheduling, bounded pending count/value bytes, exact duplicate packet reuse, broker/API correlation, admission reconciliation of the complete frozen plan, isolated lifecycle, seeded paired repetitions, controlled matrix expansion and hash/code/config checks for reuse. Workload drivers consume SDK/public APIs/import/query/workflow adapters; no provider business logic is implemented.
- `projectctl/{benchmark_adapter,artifacts,cli,providers}.py`: register explicit workload bindings; route benchmark commands through the lifecycle; retain hashed journals, failed runs, paired order and matrix plans/results. Verify dictionary hashes. Default production registry remains empty for workloads; real mode never imports doubles.
- `tests/benchmarks/{doubles,test_workloads,test_scheduler,test_experiment,test_drivers}.py`: explicit slow publisher, lifecycle and public API doubles; scheduling/count/byte/drain/unknown-admission checks, finite/query accounting, corruption/control checks, strict artifact schemas, guarded reuse, confirmation and quote authority. Quote/order requests are additionally validated against the explicitly provisional P2 consumer schemas, pending provider review.
- `benchmarks/manual/{slow_publisher,verify_p4}.py`: repeatable slow-publisher demo and command/output/exit evidence collector. `.github/workflows/offline.yml` now runs the P1–P4 checkpoint on Windows/Linux; hosted CI was not executed here.
- `docs/jaineel/p4_workloads.md`, `benchmarks/README.md`, `projectctl/README.md`, this file: adapter handoffs, exact evidence semantics, manual checks and dependency limits. No dependency/lock/config/canonical DTO/schema change.

**Implemented behavior and limits**

- W-PIPE selects the frozen seeded 10,000-key subset from supplied active SKUs. Warmup precedes measurement explicitly, even though canonical JSON sorts object keys. Per-key synthetic stock versions continue across phases; hot80 and uniform are distinct controls. Runtime IDs/timestamps are fresh; logical plans remain paired.
- Fixed worker count; active plus queued values remain bounded by count and bytes. Sustained offers never await queue capacity or shift their schedule. Missed/failed/unknown sends remain explicit. No submission starts after cutoff; drain uses the original cutoff deadline, rather than granting a delayed generator a fresh 120 seconds.
- `planned.jsonl` freezes all logical offers before provider execution. `wire.jsonl` retains exact Kafka packet bytes/key/headers; duplicates reuse originals with new source receipts. `attempts.jsonl` flushes before submission; `api_requests.jsonl` retains each exact public HTTP request before awaiting a response, including response loss. Final receipt order may differ from schedule order; joins use physical record IDs.
- Cutoff and final admission counts are separate. Acknowledgements during drain do not enter measurement admitted rate. Unknown outcomes have no fake acknowledgement time. Gold goodput stays null/`NOT_RUN`; P5 raw timing, lag and resource collectors remain unexecuted.
- W-IMPORT delegates one whole 20,000-observation job and preserves Harsh's stage/total/digest report; no normalization occurs here. W-QUALITY retains exactly 98,500 new valid + 1,000 duplicates + 500 invalid logical records. W-AGENT uses supplied scenarios. These use actual elapsed job time. W-ANALYTICS executes 18 unmeasured warmups then 180 measured Q1–Q6 calls; no 600-second padding. `perf_counter()` provides high-resolution monotonic elapsed timing on Windows; zero/unavailable timers stay incomplete.
- Search preserves hard filters and the paired retrieval mode. Checkout prepares a fresh quote before marking the timed submission, sends the common `quote_id/session_id/confirmation_id` body and retains authoritative integer totals. The integrated driver calls M1's public workflow, verifies the frozen SKU appeared in its search results, then explicitly confirms the exact quote/cart version. Orders/Inventory/Payments must produce their own events; no business event is injected by the driver.
- Prepare must acknowledge a **new** isolated `bench-` namespace; dev/live/prod names and path-escaping IDs are rejected. No reset operation exists in this lifecycle. Prepare/validate/drain/independent audit/fault callbacks remain explicit owner bindings. Named faults require barrier acknowledgements; missing hooks/receipts invalidate the run. Missing downstream audits yield incomplete evidence, never an empty-cohort pass.
- Plans retain randomized paired order, repetition, seed, config hashes, faults and effective treatment parameters. F-PARTITION emits two labelled compact children with equal size/codec; the hashed execution envelope carries their partitioning, while canonical parent config stays unchanged. Harsh/Vichitr review remains pending. C-BEST rows remain unresolved selection requests. Reuse requires complete real performance evidence, matching clean code/config and every artifact hash; P4's incomplete SUT performance evidence cannot be reused as a full measurement.

**Actual commands and outcomes**

All Python checks used `.\.venv\Scripts\python.exe` (CPython **3.11.15**) from repository root; `uv sync --locked` resolved **38** and audited **37** packages with the lock unchanged.

| Command/check | Actual result |
|---|---|
| `git status --short`, branch/log/diff inspection; `git switch -c jaineel/j02-workloads` | Clean P3 base; new local feature branch; exit **0** |
| `python -m pytest tests/projectctl tests/benchmarks -q --tb=short -W error::pytest.PytestCacheWarning` | Initial existing regressions: **137 passed**, exit **0** |
| Combined P1–P4 suite before final boundary additions | **323 passed in 52.23 s**, exit **0** |
| First recorded `python benchmarks/manual/verify_p4.py` | **11/11** expected outcomes matched; **328 passed in 62.58 s**; exit **0**. Retained checkpoint `bab45baf-789e-495c-952e-15269f98315f` below |
| `python -m pytest tests/benchmarks/test_drivers.py -q --tb=short -W error::pytest.PytestCacheWarning` after final request-journal/nullable-field review | **5 passed in 0.29 s**, exit **0** |
| `python -m ruff check` / `python -m ruff format --check` on all owned source/test paths; evaluation and conversation schema checks | Passed in the recorded checkpoint; exit **0**; schemas unchanged |
| Final `python benchmarks/manual/verify_p4.py` | Exit **0**, **11/11** expected outcomes matched; **329 passed in 63.10 s** (**54 P4 + 275 retained P1–P3**), no skips/warnings |
| Final slow-publisher demo inside that checkpoint | Demo exit **0**, all seven assertions true; experiment exit **5**. Measurement: **400 planned**, **39 attempted/acknowledged**, **361 missed**, **0 failed**, **0 unresolved**; **38** acknowledgements within measurement and **1** after cutoff |
| Final real-mode W-PIPE B0/O1 command, three repetitions | Expected exit **4**; six fresh blocked runs with resolved configurations and recorded paired order; no provider called and no performance values measured |
| Final `python -m projectctl contracts check --all` | Expected exit **4**; provider contracts still missing; G0/G1 remain incomplete |
| Final inline Python scope/hash/link review (`python -`) | Exit **0**; **22** owned/coordinated changed paths, no ownership violations/broken local links, all content/artifact hashes valid across **7** saved runs |
| `git diff --check`; `git diff --exit-code -- docs/specs uv.lock pyproject.toml configs contracts shared services infra pipelines migrations` | Both exit **0** after fixing README EOF spacing; canonical/provider paths unchanged |

New tests found and fixed phase ordering after JSON canonicalization, Windows short-duration timer resolution, incorrect quote/order request fields, loss of per-step request evidence on response loss, and final summary handling after plan tampering. Tiny saturation tests for unknown/mismatched acknowledgements now use finite mode so their assertions examine acknowledgement semantics independently of sustained cutoff/capacity misses; all unknown outcomes still must remain unresolved. Required assertions were preserved, no test was skipped and no provider gate was weakened.

**Evidence (ignored local artifacts; preserve for review)**

- [Final exact commands/stdout/stderr/exits](../../artifacts/p4/52aba30a-e16d-4481-ba86-e030641429b5/checks.json), [329-test JUnit](../../artifacts/p4/52aba30a-e16d-4481-ba86-e030641429b5/pytest.xml).
- [Final scope, local links and artifact-hash review](../../artifacts/p4/52aba30a-e16d-4481-ba86-e030641429b5/scope_review.json): no ownership violations, unchanged canonical/provider paths, valid hashes for the demo and six blocked real-mode runs.
- [Final slow-demo checks](../../artifacts/p4/52aba30a-e16d-4481-ba86-e030641429b5/slow/773905f8-fd94-46fc-8b51-e4c71962b7e2/demo_checks.json), [all physical emission outcomes](../../artifacts/p4/52aba30a-e16d-4481-ba86-e030641429b5/slow/773905f8-fd94-46fc-8b51-e4c71962b7e2/emissions.jsonl), [admission reconciliation](../../artifacts/p4/52aba30a-e16d-4481-ba86-e030641429b5/slow/773905f8-fd94-46fc-8b51-e4c71962b7e2/admission.json), [strict summary](../../artifacts/p4/52aba30a-e16d-4481-ba86-e030641429b5/slow/773905f8-fd94-46fc-8b51-e4c71962b7e2/summary.json).
- The final checkpoint's `checks.json` contains the printed slow-demo directory, actual phase counts/pressure assertions and six blocked real-mode run directories. Each run retains its resolved config, schema-valid manifest/summary and content/artifact hashes. Its root plan/results JSON records the full paired ordering.
- [Earlier accepted 328-test checkpoint](../../artifacts/p4/bab45baf-789e-495c-952e-15269f98315f/checks.json) and [JUnit](../../artifacts/p4/bab45baf-789e-495c-952e-15269f98315f/pytest.xml) remain preserved; the final checkpoint additionally covers HTTP response-loss journaling.
- [Initial independent slow demo](../../artifacts/p4/slow-6e0433dc-5caf-41d2-8697-460dbbf0d148/30f02d54-72f0-4de7-9688-627fea0cc462/demo_checks.json): exactly **400** measurement offers at **200/s**, all physical outcomes retained, count/byte limits respected, visible missed target and experiment exit **5**. Later checkpoint demos supersede its cutoff classification after tightening the final deadline.

**Remaining handoffs**

- **Harsh:** actual importer/stage evidence, canonical catalogue/quote contracts and manifests/dictionary, reviewed 50-query/cart-SKU bindings, pinned Q1–Q6 query/snapshot adapter and layout-child review.
- **Aditya:** real Orders and deterministic 95/5 simulator/seed bindings using stable scenario IDs, public status/finality observations, read-only inventory/payment/ledger audit projections, retained-state fault barriers and shared outbox.
- **Vichitr:** SDK/schema/registry and invalid-wire materialization, actual Kafka/analytics/export bindings, active-Gold membership proofs and G1 slice, infrastructure lock/resource enforcement and fault acknowledgements. Provider directories currently contain only scaffold/README files.
- **Jaineel:** P5 collectors/dashboard next; P6/P7 real session/cart/workflow APIs; later P8 real G1/G3/audit bindings and P9 controlled performance. Human label review, full D/T gates, real integration, hosted CI and the performance matrix remain `NOT_RUN`.

**Concrete manual verification and suggested commit**

1. `uv run --locked python -m pytest tests/benchmarks -q` — expect the P4 and retained P3 benchmark-helper tests to pass.
2. `uv run --locked python -m benchmarks.manual.slow_publisher` — expect the demo command to exit **0**, every demo assertion true, and its experiment to exit **5**. Sum measurement terminal outcomes to **400**, compare 200/s offered with lower admitted rate, and inspect cutoff versus drain counts and queue peaks.
3. `uv run --locked python benchmarks/manual/verify_p4.py` — inspect its printed `checks.json`/`pytest.xml`; expected missing-provider exits are **4**, while the verifier succeeds only when every expected outcome matches. All evidence is explicitly stub/offline; Gold/CPU/RAM metrics stay unmeasured.
4. `uv run --locked python -m projectctl benchmark run --workload W-PIPE --variants B0,O1 --repetitions 3 --config configs/evaluation.yaml` — expect exit **4**, six fresh run IDs/namespaces, recorded seeded paired order, visible dependency reasons and null SUT values. `contracts check --all` also remains exit **4** until owners' contracts merge; real G1 is not a stub result.
5. Review `git status --short`, `git diff --check` and all source changes, including untracked files. Suggested commit: **`feat: implement P4 open-loop workloads and experiment lifecycle`**. Stage only `benchmarks/`, `projectctl/`, `tests/benchmarks/`, `docs/jaineel/p4_workloads.md`, this progress file and `.github/workflows/offline.yml`; inspect the staged diff/check/stat before committing. Generated results, artifacts, raw CSV and secrets remain ignored.

**Next action:** stop at P4. P5 remains not started. Changes remain uncommitted and unpushed; review the owned source diff before making the suggested commit.

---

### Milestone P5: Telemetry, Raw Collectors, and Dashboard

- **State:** stub verified; J03/P5 offline checkpoint complete. Actual local generator CPU/RSS and a loopback HTTP scrape were checked separately. Real Kafka, active Gold, SUT resources, Grafana import, G1/G3, hosted CI and performance remain `NOT_RUN`. P6 is not started.
- **Branch/base:** `jaineel/j03-telemetry`, created from clean `jaineel/j02-workloads` at `6d0a6ff6b357c6735d4282e874a8953e4da92c8a`. This is an explicit dependent branch; no merge into main is assumed. Existing P3/P4 commits and historical records were preserved.
- **Authorities:** AGENTS, ownership, progress, personal brief J03 and provider boundaries, playbook P5, context technology freeze, common §14/Appendix A and IDs/time conventions, evaluation §5, runbook §7, dataset provenance/manifest rules. No canonical specification, provider implementation/DTO, dependency or lock changed.

**Changed paths and behavior**

- `shared/telemetry/{__init__,context,metrics,timing}.py`, `shared/telemetry/README.md`: all common metric families, exact latency buckets, finite label vocabularies and series limits, lazy initialization, task-local canonical context/logging, monotonic raw durations and bounded-batch JSONL-to-Parquet retention. Missing values are not converted to zeros; IDs and raw error/request text do not become metric labels.
- `benchmarks/{observation,collectors,observation_summary}.py`: fixed one-second observations, declared series, bounded polling, explicit timeout/partial/missed-tick gaps; raw JSONL/CSV artifacts; actual HTTP metrics, Kafka Admin read-only offsets, generator process and explicit cgroup-v2 readers; pinned active-Gold audit/membership/generation checks; hashed offline reconstruction with CPU allocation/reset/gap handling and completed-only latency counts. Provider projection seams stay explicit and do not replace the independent oracle.
- `benchmarks/{experiment,scheduler}.py`: optional explicit observer/metric bindings start after validation and finalize before run hashing; live offered/admitted counters and bounded pending queue gauges. IDs/mode/directory must match. No default real binding or mock fallback was installed. SUT performance remains INCOMPLETE/NOT_RUN until actual evidence gates.
- `dashboards/{build_dashboard.py,benchmark.json,README.md}`: deterministic Grafana JSON with context/status, offered/admitted/goodput, latency, separate lag/outbox/pending-Gold, quarantine, projection, stock/saga, queues, CPU/RSS and health panels. No sample defaults, zero-fill or interpolated nulls. Stock aggregate and Gold-goodput monitoring bindings require owner review; absent series remain absent.
- `tests/telemetry/{conftest,doubles,test_instrumentation,test_observation,test_collectors,test_dashboard}.py`: **37** focused tests, explicit doubles, actual local process and loopback HTTP paths. Kafka Admin/cgroup/Gold tests use explicit doubles/file fixtures and are not real integration results.
- `benchmarks/manual/{observer_stall,verify_p5}.py`, `.github/workflows/offline.yml`: reproducible stall/gap/resource demo, exact command/output/exit/JUnit retention and Windows/Linux P1–P5 CI definition. Hosted execution is unverified.
- `docs/jaineel/p5_telemetry.md`, this file: owner instrumentation/binding examples, infrastructure handoffs, limits, evidence and manual checks.

**Failures found and fixed**

The first combined run retained **1 failure / 485 passes**. Its raw source journal showed `source-000003` scheduled at **0.600000 s**, sent at **0.585721 s** and acknowledged at **0.585807 s**. Windows' event-loop timer woke early; the strict timing writer correctly rejected a negative schedule-to-ack duration. The generator now rechecks the high-resolution monotonic deadline after waking, rather than clamping the duration or weakening assertions. Observation ticks also recheck their deadline.

The next combined run retained **1 failure / 486 passes**: eliminating the zero-delay yield exposed a zero-warmup lifecycle ordering race. The scheduler now records warmup before starting its phase task, preserving prepare → validate → warmup → measure → drain → reconcile → persist. The existing ordering assertion is unchanged. A deterministic early-wakeup regression was added under P5 tests. All final checks passed after these fixes; failed evidence was preserved.

**Actual commands and outcomes**

Commands ran at repository root with `.\.venv\Scripts\python.exe` (Python **3.11.15**); `uv` is **0.10.8**. In the table, `python` denotes that executable.

| Command | Actual outcome |
|---|---|
| `git status --short --branch`, log/diff inspection; `git switch -c jaineel/j03-telemetry` | Clean P3/P4 tree preserved; new feature branch, exit 0 |
| `uv sync --locked` | Exit 0; 38 packages resolved / 37 audited; lock unchanged |
| `python -m pytest tests/telemetry -q --tb=short -W error::pytest.PytestCacheWarning` during implementation | 31 then 35 passed; final collection contains 37 P5 tests |
| `python -m pytest tests/telemetry tests/benchmarks/test_scheduler.py tests/benchmarks/test_experiment.py -q --tb=short -W error::pytest.PytestCacheWarning` | Exit 0; **71 passed in 22.43 s**, no skips |
| `python benchmarks/manual/verify_p5.py` (final) | Exit **0**; **11/11** expected outcomes matched; combined suite **488 passed in 60.72 s**, **0 failed/errors/skipped** |
| Verifier lint/format, evaluation schema and conversation schema checks | All exit 0; schemas unchanged |
| Verifier `python -m benchmarks.manual.observer_stall --out artifacts/p5/dd60f52b-990e-411b-93b7-44e1d16a7edb/demo` | Exit 0; **9/9 assertions true**. Stub lag remains 0, pending Gold grows to 30, outbox rows to 6; stopped collector has three missing samples and null latest value. Separate real generator has three CPU/RSS readings |
| Verifier `python -m benchmarks.observation_summary --run-dir artifacts/p5/dd60f52b-990e-411b-93b7-44e1d16a7edb/demo/stub-stall --out artifacts/p5/dd60f52b-990e-411b-93b7-44e1d16a7edb/rebuilt` | Exit 0; artifact-only JSON/Markdown reconstruction, evidence status remains INCOMPLETE |
| Verifier `python -m projectctl contracts check --all` | Expected exit **4**; provider contracts/instrumentation remain missing; no replacement supplied |
| `git diff --check`; protected spec/lock/config/contracts/providers diff | Exit 0; no whitespace errors or protected-path changes |

**Evidence (ignored local artifacts, not committed)**

- [Final exact commands, stdout/stderr and exits](../../artifacts/p5/dd60f52b-990e-411b-93b7-44e1d16a7edb/checks.json), [488-test JUnit](../../artifacts/p5/dd60f52b-990e-411b-93b7-44e1d16a7edb/pytest.xml).
- [Demo assertions and source directories](../../artifacts/p5/dd60f52b-990e-411b-93b7-44e1d16a7edb/demo/demo_checks.json), [stub raw observations](../../artifacts/p5/dd60f52b-990e-411b-93b7-44e1d16a7edb/demo/stub-stall/observations.jsonl), [stub offline table](../../artifacts/p5/dd60f52b-990e-411b-93b7-44e1d16a7edb/demo/stub-stall/offline_summary.md), [real generator resource table](../../artifacts/p5/dd60f52b-990e-411b-93b7-44e1d16a7edb/demo/real-generator/offline_summary.md).
- [Independent offline rebuild](../../artifacts/p5/dd60f52b-990e-411b-93b7-44e1d16a7edb/rebuilt/telemetry_summary.md); each source directory retains context, end-of-observation metadata, CSVs, raw timings/Parquet and content/file hashes.
- [Preserved early-wakeup failure](../../artifacts/p5/2226cfd5-8b2d-4d23-ad7b-e5e11ebfac44/checks.json), [preserved zero-warmup ordering failure](../../artifacts/p5/8da929d4-0de2-4605-8046-327d10119090/checks.json). Final evidence above supersedes both.
- Publication/scope commands and actual outcomes are retained in [the Git handoff evidence](../../artifacts/p5/dd60f52b-990e-411b-93b7-44e1d16a7edb/git_publication.json). User explicitly requested a source-only commit and push; generated evidence/raw data/secrets remain excluded.

**Remaining dependencies and review**

- **Vichitr:** real Kafka/group/partition settings, locked Prometheus/Grafana startup and one-second scrape targets, active-manifest/query/membership binding, publication/lag/outbox projections and actual G1 evidence. No Compose changes were made.
- **Aditya:** Orders/Inventory/Payments instrumentation, outbox count/oldest age, saga states, approved read-only stock aggregate review and actual resource/audit bindings. The optional `benchmark_inventory_units{state}` consumer projection does not alter business/event contracts.
- **Harsh:** catalogue/projection/import/query instrumentation, real service metrics and stage timing/manifest handoffs. Source data were not replaced or inferred.
- **Jaineel/later gates:** reviewed real bindings and producer-to-Gold/Silver/publication timings, full SUT resource measurements, actual Grafana import/PromQL evaluation, G1/G3 and correctness/performance gates remain NOT_RUN. No model calls were made; no performance matrix was launched.

**Concrete manual checkpoint**

1. Run `uv run --locked python -m pytest tests/telemetry -q`; expect 37 tests to pass.
2. Run `uv run --locked python -m benchmarks.manual.observer_stall`; open its printed `demo_checks.json`. Verify nine true assertions, separate stub/real directories and NOT_RUN SUT/Grafana status.
3. Open `stub-stall/offline_summary.md` and raw observations: Kafka lag 0, pending Gold 0/10/20/30, outbox 0/2/4/6; three projection gaps and null latest value. These are distinct boundaries, not one combined backlog.
4. Run the offline command above with the actual emitted directory and a fresh output path. Compare the rebuilt table/JSON with the original. In a disposable copy only, change a CSV; reconstruction must return exit 4 for a hash mismatch.
5. Run `uv run --locked python benchmarks/manual/verify_p5.py`. Inspect all actual/expected exits and JUnit counts. Missing-provider exit 4 is expected, not an integration pass.
6. Once owners provide actual endpoints/infrastructure, follow [the P5 handoff](p5_telemetry.md) to register real readers and import `dashboards/benchmark.json`. Select matching scrape jobs/run context/time range, stall the real publisher and stop a real collector. Keep those real checks NOT_RUN until executed; do not infer them from the demo.

**Checkpoint:** stop at P5. Commit message: `feat: implement P5 telemetry collectors and dashboards`; publish on `jaineel/j03-telemetry`. P6 remains not started.

---

### P1–P5 audit and fixes — 27 October 2026

**Scope and state:** user explicitly requested inspection and fixes across P1–P5. Reviewed the CLI/config/artifact foundation, HTTP/SSE clients and contract boundaries, independent metric/oracle/fixture code, workload planning/lifecycle/scheduler, collectors and offline reconstruction against AGENTS.md, OWNERSHIP, the personal brief and shared specs 01/02/03/08/09/10. This is a regression review of the existing milestones, not P6 implementation or real integration approval.

**Git:** started from clean `jaineel/j03-telemetry` at `9fdf112bef1f5dfd68fb9c88ffbd66a2828d0f4b`; initially isolated this review on local `jaineel/p1-p5-audit`. Per the user's branch instruction, the review changes were carried back to the existing pushed `jaineel/j03-telemetry` branch and published as `adf7b035d4e54d360690b4f87f9316d9a8b3e041` (`fix: resolve P1-P5 audit findings`). `git push origin jaineel/j03-telemetry` exited 0; `git ls-remote origin refs/heads/jaineel/j03-telemetry` returned the same hash. Continue future Jaineel milestones on the last pushed branch; do not create a branch for each P milestone.

#### Reproduced findings and fixes

| Milestone | Reproduced issue | Fix / regression evidence |
|---|---|---|
| P1 | Unexpected adapter exceptions escaped the CLI without a failure manifest. | Catch ordinary exceptions at the adapter boundary, retain exit 4 evidence and only the exception type; regression checks exception text is not leaked. |
| P2 | NaN deadlines could bypass meaningful timeout arithmetic; Boolean/nonfinite deadlines were accepted inconsistently. | Validate explicit finite monotonic deadlines for HTTP and SSE before sending. |
| P2 | A shallow query snapshot allowed nested caller mutations to change retry requests. | Deep-copy query inputs before the first await; regression compares both transmitted URLs. |
| P3 | Verified Gold membership with a timestamp before the event's first planned offer could count as successful goodput. | Reject impossible chronology in the independent rate calculation; physical duplicate offers still share their earliest source time. |
| P4 | A successful audit with the wrong real/stub mode left `correctness_passed=true` even though the run failed. | Validate the audit verdict and mode before assigning correctness; rejected audit evidence retains null correctness. |
| P4 | Malformed planned/emissions journals were reparsed outside error handling, preventing the final failure manifest. | Preserve raw corruption, retain incomplete admission evidence, compute rates only from a completed reconciliation and finalize before telemetry hashes are frozen. |
| P4 | Explicit zero repetitions silently selected the default; empty variant/fault selections produced no trials. | Reject invalid or empty plans and duplicate selections at the planning boundary. |
| P4 | `order.effective_parameters` could override frozen variant controls sent to provider preparation. | Derive parameters from the resolved variant; permit only the registered F-PARTITION child treatment and reject conflicting metadata before provider calls. |
| P4 | Reuse accepted a manifest omitting the hash of a decision input such as `summary.json`. | Require hashes for the lifecycle decision evidence and reject duplicate resolved artifact references. |
| P5 | A collector returning a list caused `.get()` to fail after its result was rejected, interrupting peers. | Discard invalid collector results and emit explicit missing samples while retaining peer observations. |
| P5 | Non-JSON, nonfinite or non-object reading metadata could crash persistence or reach summary calculations. | Validate and snapshot metadata; invalid readings become missing samples with null values. |
| P5 | An observer task failure skipped the end record and telemetry manifest, losing reconstruction metadata for partial evidence. | Finalize available evidence with `INCOMPLETE` and an exception type, close timing writers even when journal parsing fails, then propagate the failure. |
| P5 | Offline reconstruction read optional and required files without requiring their presence in the hash inventory. | Require a verified hash for every consumed file; reject duplicate references and honor incomplete observer/admission status. |

No provider API, canonical DTO, shared specification, dataset rule, frozen configuration, lock or teammate module was changed. Test doubles remain explicitly labeled and confined to tests/demo bindings. No live fallback was added.

#### Changed paths

- `projectctl/cli.py`
- `services/conversation/clients.py`
- `benchmarks/{experiment,planning,metrics,observation,observation_summary}.py`
- `benchmarks/manual/verify_p5.py`: adds explicit `--review-p1-p5` mode, using the same checks and tests while allowing Jaineel's P2 client path in this review. Default P5 scope remains unchanged; teammate service paths remain protected.
- `tests/projectctl/test_cli.py`, `tests/contracts/test_clients.py`, `tests/benchmarks/{test_experiment,test_metrics}.py`, `tests/telemetry/test_observation.py`
- `docs/jaineel/progress.md`

#### Actual checks and retained evidence

| Command/check | Actual outcome |
|---|---|
| `git status --short --branch`; `git switch -c jaineel/p1-p5-audit` | Clean initial tree; new branch created, exit 0. |
| Targeted red regression runs, exact pytest argument arrays/output in the linked JSON files below | First run **17 failed / 1 passed / 148 deselected**; additional cases **5 failed / 38 deselected**; frozen-control case **1 failed / 30 deselected**. All pytest exits 1, intentionally retained before fixes. |
| `.venv/Scripts/python.exe -m pytest tests/projectctl/test_cli.py tests/contracts/test_clients.py tests/benchmarks/test_experiment.py tests/benchmarks/test_metrics.py tests/telemetry/test_observation.py -q --tb=short --junitxml=artifacts/p1-p5-review/4167ae71-dad1-4ac7-babe-0dc55e1128e5/focused.xml` | **189 passed in 33.71 s**, exit 0, before the final frozen-control regression was added. |
| `.venv/Scripts/python.exe benchmarks/manual/verify_p5.py --review-p1-p5` | Exit **0**, **11/11** expected outcomes matched; combined P1–P5 **511 passed in 62.58 s**, no skipped tests. |
| Verifier: Python family; Ruff lint/format; evaluation schemas and conversation contract drift checks | All exit **0**, Python **3.11.15**. |
| Verifier: `python -m benchmarks.manual.observer_stall --out <evidence>/demo`; offline rebuild | Both exit **0**; all nine demo assertions true. Real local generator CPU/RSS recorded separately from stub stall observations. |
| Verifier: `python -m projectctl contracts check --all` | Expected exit **4**, missing owner contracts remain visible; this is not an integration pass. |
| Verifier: `git diff --check`; protected-path diff | Both exit **0**; canonical/shared and teammate paths unchanged. |

Evidence is local and ignored by Git; no raw output, generated data or benchmark result directory is staged:

- Red/focused evidence: [red.json](../../artifacts/p1-p5-review/4167ae71-dad1-4ac7-babe-0dc55e1128e5/red.json), [red-additional.json](../../artifacts/p1-p5-review/4167ae71-dad1-4ac7-babe-0dc55e1128e5/red-additional.json), [red-controls.json](../../artifacts/p1-p5-review/4167ae71-dad1-4ac7-babe-0dc55e1128e5/red-controls.json), [focused.json](../../artifacts/p1-p5-review/4167ae71-dad1-4ac7-babe-0dc55e1128e5/focused.json); accompanying JUnit files retain individual cases.
- Full verification exact command arrays, stdout/stderr and exit codes: [checks.json](../../artifacts/p1-p5-review/f7239a25-41d5-4968-8f07-fc491ba6bb55/checks.json); [pytest.xml](../../artifacts/p1-p5-review/f7239a25-41d5-4968-8f07-fc491ba6bb55/pytest.xml).
- Demo assertions: [demo_checks.json](../../artifacts/p1-p5-review/f7239a25-41d5-4968-8f07-fc491ba6bb55/demo/demo_checks.json).
- Raw stub observations: [observations.jsonl](../../artifacts/p1-p5-review/f7239a25-41d5-4968-8f07-fc491ba6bb55/demo/stub-stall/observations.jsonl); separate real generator output: [offline_summary.md](../../artifacts/p1-p5-review/f7239a25-41d5-4968-8f07-fc491ba6bb55/demo/real-generator/offline_summary.md).
- Independently reconstructed table: [telemetry_summary.md](../../artifacts/p1-p5-review/f7239a25-41d5-4968-8f07-fc491ba6bb55/rebuilt/telemetry_summary.md).

#### Remaining dependencies and manual verification

Harsh's catalogue/import schemas and provider bindings, Aditya's transaction/inventory/payment contracts and endpoints, and Vichitr's event transport, Kafka, active Gold audit export and deployment instrumentation remain required. The actual source CSV, human query-label review, real G1/G3, real SUT resource/lag measurements, Grafana import, hosted CI and performance matrix have not been verified by this review. Existing limitations remain `NOT_RUN`; no stub result establishes those gates.

1. Run `.venv/Scripts/python.exe benchmarks/manual/verify_p5.py --review-p1-p5`. Inspect the new `checks.json` and JUnit file; expect 511 tests and the intentional owner-contract exit 4.
2. Read the retained red cases beside the regression tests, especially corrupt-journal finalization, wrong-mode audit rejection, frozen-control overrides and missing-hash rejection.
3. Open the linked reconstructed telemetry table: Kafka lag stays 0 while pending Gold grows to 30, outbox grows separately, and the stopped collector has three missing samples with a null latest value. Confirm mode is `stub`.
4. Rebuild manually into a fresh output directory: `.venv/Scripts/python.exe -m benchmarks.observation_summary --run-dir artifacts/p1-p5-review/f7239a25-41d5-4968-8f07-fc491ba6bb55/demo/stub-stall --out artifacts/p1-p5-review/manual-rebuild`. Expect successful reconstruction with `INCOMPLETE` data status because gaps are preserved. Use a new output path on each repeat.
5. Inspect `git diff --check`, `git diff --stat` and `git status --short --branch`. Only the owned paths listed above should differ; review branch is local. When actual providers are available, follow the existing P2/P4/P5 handoffs to run real contracts and collector checks.

**Checkpoint:** P1–P5 review complete for the inspected offline paths; P6 remains not started.

---

### Milestone P6: Durable Sessions, Cart, and Idempotency

- **State:** P6 independent state checkpoint complete: real PostgreSQL transaction,
  concurrency, service restart and retained-data database restart checks; explicit
  builder/outbox capture doubles. The actual shared event/outbox/registry path
  remains `NOT_RUN` and incomplete. This is not G1/G3 or a real event integration
  pass. P7 remains not started.
- **Branch/base:** existing pushed `jaineel/j03-telemetry`, base
  `bf267d9` (`docs: record P1-P5 audit publication`), preserving the recorded
  preference to continue this branch. Initial working tree was clean. User
  explicitly authorized the source commit and GitHub push for this milestone.
- **Authority consumed:** AGENTS.md; OWNERSHIP; personal brief J04;
  common §§3–5/6.1/6.2/7/8, Appendix A/B; project context technology freeze;
  dataset §4/8 listing identity and no invented stock/price; evaluation §7 and
  runbook §4's real-database/failure evidence rules; playbook P6.

**Changed paths and behavior**

- `services/conversation/{database,state,events,errors,app}.py`: PostgreSQL 18
  connections/migration checks; session/cart/turn outcomes; canonical scoped
  idempotency; stale version checks; locks and coherent reads; safe common
  errors; HTTP validation, health and bounded-label metrics/logs. Shared builder
  and append are invoked inside the same transaction, with no direct publish.
  Missing real implementations fail cart mutations/readiness visibly. Session
  creation has no invented event. P7 turn/quote/checkout workflows remain
  explicitly unavailable. No extraction/search/model/purchase logic was added.
- `migrations/conversation/{001_state,audit}.sql`: only M1 state tables,
  namespace/owner FKs, uniqueness and value checks, quote/confirmation binding,
  plus read-only namespace-bound audit queries. Cart edits invalidate prior
  quote/confirmation references. No teammate outbox or diagnostic schema copied.
- `tests/conversation/{conftest,doubles,test_state,test_http,process,server,test_process}.py`
  and `__init__.py`: explicit capture/turn doubles, real PostgreSQL isolated
  schemas, strict inputs, corruption constraints, isolation, replay/conflicts,
  rollback, 24 concurrent same/distinct-key edits, 24 session retries,
  16 turn request retries and actual subprocess restart. Real mode rejects
  stub injection. Temporary test schemas alone are cleaned; smoke schemas stay.
- `benchmarks/manual/{verify_p6,p6_smoke}.py`: exact-command evidence collector,
  P1–P5 regressions, visible incomplete provider gates and replayable smoke
  capturing actual returned IDs; optional retained-data database restart resume.
- `.github/workflows/offline.yml`: coordinated PostgreSQL 18.6 P6 CI job with
  explicit test-event labeling, retaining existing Windows/Linux offline jobs.
  Hosted execution is not claimed by the local checks.
- `services/conversation/README.md`, `docs/jaineel/p6_persistence.md`, this file:
  setup, semantics, manual verification, owner review and actual evidence.
  Canonical specs, DTOs/OpenAPI, lock/config and teammate modules are unchanged.

**Actual commands and outcomes (27 October 2026, Asia/Calcutta)**

| Command / action | Actual outcome |
|---|---|
| `git status --short --branch`; `git diff --stat`; `git remote -v` | Clean current feature branch at start; origin `https://github.com/harsh-c-16/payment-gateway.git`. |
| `docker version`; `docker ps`; hidden Docker Desktop startup, then `docker info` | Client exists; daemon unavailable. Docker/Compose/G0 checks remain `NOT_RUN`. No infra file changed. |
| Official EDB PostgreSQL 18.6 binary download; `initdb` / `pg_ctl start` | Native isolated loopback clusters created; source/archive SHA and exact native setup commands retained below. Native PostgreSQL **18.6**, `fsync` and synchronous commit defaults retained. Final cluster uses port **55487**, outside OneDrive. This is a local test fallback, not the frozen Compose profile or a performance result. |
| Initial `.venv/Scripts/python.exe -m pytest tests/conversation -q --tb=short --junitxml=artifacts/p6/initial-pytest.xml` with explicit test DB env | **56 passed, 4 failed, 10 errors**. DDL and some API queries hit real statement timeouts in the OneDrive-backed cluster. Retained evidence; no assertion weakened. Migration/capture DDL now has a separate setup limit, API bounds stay 2 s; fresh native cluster uses a nonsynced temp directory. |
| Focused repeat with port 55487, `-o cache_dir=artifacts/p6/focused-cache --junitxml=artifacts/p6/focused-pytest.xml` | **70 passed, 1 setup error**: host's existing `pytest-of-voraj` temp root was inaccessible. Verifier now uses a fresh evidence-owned `--basetemp` and cache directory. |
| `.venv/Scripts/python.exe -m pytest tests/conversation/test_process.py -q --tb=short --basetemp=artifacts/p6/process-test-temp -o cache_dir=artifacts/p6/process-cache --junitxml=artifacts/p6/process-pytest.xml` | **1 passed in 3.62 s**, actual service process restart. |
| `uv sync --locked` | Exit **0**, 38 resolved / 37 audited packages, lock unchanged. Python **3.11.15**. |
| `$env:P6_TEST_DATABASE_URL='postgresql://p6_test@127.0.0.1:55487/conversation_p6'`; `.venv/Scripts/python.exe benchmarks/manual/verify_p6.py --out artifacts/p6/checkpoint-20261027` | Exit **0**, **10/10** expected command outcomes. Combined P1–P6 **582 passed in 102.29 s**, **zero failed/errors/skipped**; smoke **13/13** assertions pass. Ruff lint/format, schema/contract generation, protected-path and whitespace checks pass. Global `contracts check --all` retains expected exit **4** for missing owner handoffs. |
| `.venv/Scripts/python.exe -m pytest tests/conversation/test_http.py::test_shared_adapter_preserves_storage_failure_classification -q -o cache_dir=artifacts/p6/storage-error-cache --junitxml=artifacts/p6/storage-error-pytest.xml` | **1 passed**, late adapter regression preserves `STORAGE_UNAVAILABLE` classification for local PostgreSQL append failures. Final affected-suite results recorded below. |
| Isolated native cluster `pg_ctl ... -m fast -w -t 30 ... restart` (exact validated target and argument array in evidence) | Exit **0**, retained data; no shared/development process restarted. |
| `.venv/Scripts/python.exe -m benchmarks.manual.p6_smoke --out artifacts/p6/checkpoint-20261027/smoke --resume` with the same explicit test DB URL | Exit **0**, all **3/3** checks pass: saved cart and original key survive the PostgreSQL restart; one captured test event remains. |
| Final `.venv/Scripts/python.exe -m pytest tests/conversation -q --tb=short --basetemp=artifacts/p6/final-test-temp -o cache_dir=artifacts/p6/final-cache --junitxml=artifacts/p6/final-pytest.xml` | **72 passed in 23.47 s**, zero failed/errors/skipped. Includes the late storage-classification regression and actual subprocess restart. Final Ruff lint/format and `git diff --check` also exit **0**. |

The combined suite ran before the final storage-classification regression was
added; that extra test passed separately and is included in the final affected
suite. The upstream locked Starlette TestClient emits one deprecation warning
about HTTPX; it is retained, not suppressed. No dependency was changed to hide it.

**Evidence (local ignored artifacts, excluded from Git)**

- [Combined exact command/output/exit log](../../artifacts/p6/checkpoint-20261027/checks.json),
  [combined JUnit](../../artifacts/p6/checkpoint-20261027/pytest.xml),
  [explicit checkpoint limits](../../artifacts/p6/checkpoint-20261027/summary.json).
- [Scripted smoke](../../artifacts/p6/checkpoint-20261027/smoke/smoke.json),
  [raw request/response transcript](../../artifacts/p6/checkpoint-20261027/smoke/transcript.json),
  [subprocess log](../../artifacts/p6/checkpoint-20261027/smoke/server.log).
  Two actual server PIDs differ; event metadata labels the double explicitly.
- [Database restart command](../../artifacts/p6/database-restart-command.json),
  [database restart observations](../../artifacts/p6/checkpoint-20261027/smoke/database-restart.json),
  [native setup](../../artifacts/p6/native-cluster.json),
  [native DB log](../../artifacts/p6/postgres-native.log).
- [Official binary acquisition URL/observed SHA-256](../../artifacts/p6/tools/download.json):
  `e2246ba91d22345bc3d017586c09ede52d9df180b1eeb480f050445f1cad84e2`.
  This is the locally observed archive hash, not a claim of a vendor checksum.
- Preserved initial failures:
  [initial JUnit](../../artifacts/p6/initial-pytest.xml),
  [focused host-temp failure](../../artifacts/p6/focused-pytest.xml);
  successful targeted
  [restart](../../artifacts/p6/process-pytest.xml) and
  [storage error](../../artifacts/p6/storage-error-pytest.xml) regressions;
  [final P6 JUnit](../../artifacts/p6/final-pytest.xml).

**Remaining dependencies / review**

Aditya: real `append_outbox`, caller-transaction compatibility, outbox migration
template/indices/relay and rollback integration. Vichitr: canonical event builder,
payload/envelope schemas/cache readiness, metadata configuration and diagnostics
template. The exact context/source_service/dataset_revision and correlation-ID
binding gaps are recorded in [the handoff table](p6_persistence.md#shared-handoffs-remain-incomplete);
no shared DTO/signature was silently extended. Confirm zero-quantity removal
events and no-op PUT event/version semantics with consumers. Harsh/Aditya/Vichitr
provider contracts and endpoints, Docker/Compose, Kafka, real event rollback,
G1/G3, complete T/D integration, hosted CI and performance remain incomplete or
`NOT_RUN`. No optional model/provider calls were made.

**Concrete manual verification**

1. Set `P6_TEST_DATABASE_URL` to an isolated PostgreSQL 18 DB, run `uv sync --locked`
   then `uv run --locked python benchmarks/manual/verify_p6.py`. Read the printed
   `checks.json` and JUnit counts; absent/unreachable DB must not become a fake pass.
2. Run `uv run --locked python -m benchmarks.manual.p6_smoke --out artifacts/p6/manual-smoke`
   with a fresh output path. Inspect captured IDs, one-effect replay, changed-input
   409, old-version 409, other-user 403 and actual restart PIDs in `smoke.json`.
3. Read the rollback assertions and event count. Their mode is explicitly
   `real-postgresql/test-double-events`; repeat against the real shared outbox
   only after its owner supplies the reviewed implementation/schema.
4. For this session's retained smoke and running isolated native cluster, use
   port 55487 and `--out artifacts/p6/checkpoint-20261027/smoke --resume` to recheck
   persistence. Cluster path/commands are in `native-cluster.json`; never reset or
   restart an unrelated database. Smoke state is deliberately retained.
5. For production-path failure visibility, set `CONVERSATION_DATABASE_URL`, apply
   `python -m services.conversation.database`, then start the README's app factory.
   With missing shared libraries, readiness/cart mutations return common 503;
   no successful cart effect is fabricated. Quote/checkout/turn workflow remains
   P7-unavailable. Check P2 header bindings in the linked handoff.

**Checkpoint:** stop at P6. P7 remains not started.

**Git publication:** implementation commit `31aa699af7ae71942946ad4e090fad5d8385fbac`
(`feat: implement P6 durable conversation state`) was pushed with
`git push origin jaineel/j03-telemetry`, exit **0**. `git ls-remote origin
refs/heads/jaineel/j03-telemetry` returned the same hash; the working tree was
clean. Only the 21 reviewed source/test/docs/CI paths were staged. Generated
evidence, native binaries/database files, raw data and secrets were excluded.
Exact publication commands/outputs are retained in
[git_publication.json](../../artifacts/p6/git_publication.json). This publication
note is a documentation-only follow-up; it does not advance P7. Hosted CI is
pending verification.
The unused initial OneDrive-backed test cluster was stopped with data retained;
the selected isolated cluster on port 55487 remains available for manual replay.
[Actual durability settings](../../artifacts/p6/durability-settings.json) confirm
`fsync=on`, `synchronous_commit=on`, and `full_page_writes=on`.

#### P6 Docker follow-up — 27 October 2026

User requested Docker diagnosis, Docker use going forward, related fixes and a
commit on the same branch. Work stays on `jaineel/j03-telemetry` from `f07d116`;
the starting tree was clean. No branch was created and P7 is not advanced.

**Daemon finding:** at the first check of this follow-up, `docker version`,
`docker info`, `docker desktop status` and `docker compose version` all succeeded.
Docker Desktop **4.97.0**, engine/CLI **29.9.2**, Compose **5.6.1**, Linux engine,
context `desktop-linux`; the engine reported no warnings. These versions differ
from the previous run's client, but this session did not upgrade Docker. The
previous missing pipe is not currently reproducible. No Docker reset, WSL reset,
service reconfiguration or speculative host change was performed. Actual image
pull, container startup, client connectivity, SQL and retained-volume restart
are checked below rather than treating version output as sufficient evidence.

**Changes**

- `benchmarks/manual/p6_docker.py`: isolated Jaineel-owned test harness using
  Docker Compose and the actually pulled official PostgreSQL 18.6 digest
  `sha256:edb0c08dc33befd0262ab3b5cf1c4f3f8cfd8b09e88c05b45adee29d6761ddb6`.
  Per-run generated project/Compose file, named PostgreSQL 18 volume, loopback
  random port, generated test credential, health/durability checks, complete
  P6 verification, container restart and persisted-key/cart replay. Journals
  retain failed/timeout output and redact the generated password. Generated
  Compose/connection files, data and evidence remain ignored.
- `benchmarks/manual/verify_p6.py`: Docker is now the default entry point even
  when a native `P6_TEST_DATABASE_URL` is present. Missing CLI/daemon, wrong
  engine, unhealthy/unreachable DB or failed checks cannot select native
  PostgreSQL. The explicit inner `--external-database` option is used by the
  owning harness after binding its Docker endpoint. The inner summary does not
  claim Docker provenance independently of the outer container evidence.
- `.github/workflows/offline.yml`: P6 now invokes the same Docker lifecycle and
  restart path as local checks; removed the independently configured CI DB.
  Existing Windows/Linux P1–P5 jobs remain. The Python runner/service subprocesses
  still use the frozen host application environment; PostgreSQL runs in Docker.
- `tests/conversation/conftest.py`, `benchmarks/manual/p6_smoke.py`: explicit
  two-second psycopg connection bounds for test schema setup/cleanup. No changes
  to business contracts, durability or correctness assertions.
- `tests/conversation/test_docker_harness.py`: explicitly doubled command-failure
  tests for missing CLI, stopped daemon, Windows engine, wrong identity/health,
  wrong/missing volume, public binding, retained timeout output, credential
  redaction, mandatory default Docker and changed host port after restart.
- `docs/jaineel/p6_persistence.md`, `services/conversation/README.md`, this file:
  Docker-first recheck and scoped resource lifecycle instructions. Team infra,
  provider implementations, shared specs/DTOs, dependencies and lock are untouched.

**Reproduced and fixed restart issue**

The first Docker run passed **595 tests with zero failed/errors/skipped**, plus
the 13-assertion P6 smoke. It then correctly stayed **INCOMPLETE**: after restarting
the same healthy container and volume, Docker changed the ephemeral published
port **32768 → 32769**, while the new harness reused the old connection URL.
This was a client binding bug, not a PostgreSQL durability failure. Evidence is
preserved in
[the first Docker summary](../../artifacts/p6-docker/checkpoint-20261027/docker-summary.json)
and [its combined JUnit](../../artifacts/p6-docker/checkpoint-20261027/checkpoint/pytest.xml).
The regression first failed as expected in
[port-red-pytest.xml](../../artifacts/p6-docker/port-red-pytest.xml).
The fix refreshes the URL, child environment and saved local connection file from
the live inspected port after restart. All **13 harness regressions** then passed
in [port-green-pytest.xml](../../artifacts/p6-docker/port-green-pytest.xml).
Only that first isolated project's container was stopped; its volume/data and
failed evidence remain intact. No unrelated Docker resources were changed.

**Commands / evidence**

- `docker version`; `docker context ls`; `docker context inspect`;
  `docker desktop status`; `docker info`; `docker compose version`;
  `docker ps -a`; `docker volume ls`: current daemon/Compose available, no
  pre-existing containers/volumes at the beginning of this follow-up.
- `docker pull postgres:18.6`; `docker image inspect postgres:18.6`: exit 0,
  actual digest above. The harness subsequently pulls that exact digest.
- Targeted harness run: **12 passed** initially; the first invocation also
  retained **7 passed / 5 temp-directory setup errors** because its newly named
  artifact parent did not exist yet. The repeated invocation after parent creation
  passed all 12. The full verifier always creates its output parent first.
- `.venv/Scripts/python.exe benchmarks/manual/verify_p6.py --out artifacts/p6-docker/checkpoint-20261027`:
  initial Docker attempt described above; **595 passing tests**, but whole
  checkpoint incomplete after the port changed. No native fallback.
- `.venv/Scripts/python.exe -m pytest tests/conversation/test_docker_harness.py::test_restart_refreshes_remapped_port_and_child_connection -q --tb=short --basetemp=artifacts/p6-docker/port-red-temp -o cache_dir=artifacts/p6-docker/port-red-cache --junitxml=artifacts/p6-docker/port-red-pytest.xml`:
  expected **1 failed** before the binding fix.
- `.venv/Scripts/python.exe -m pytest tests/conversation/test_docker_harness.py -q --tb=short --basetemp=artifacts/p6-docker/port-green-temp -o cache_dir=artifacts/p6-docker/port-green-cache --junitxml=artifacts/p6-docker/port-green-pytest.xml`:
  **13 passed** after the fix.
- `.venv/Scripts/python.exe benchmarks/manual/verify_p6.py --out artifacts/p6-docker/checkpoint-20261027-final`:
  exit **0**, final combined **596 passed in 86.10 s**, zero failed/errors/skipped;
  **13/13** smoke assertions and **3/3** post-container-restart assertions pass.
  All **14** outer Docker/lifecycle commands matched expected exit 0; all **10**
  inner verifier command outcomes matched, including the visible provider-contract
  exit **4**. Ruff lint/format, schema/contract generation and protected-path
  checks pass. The same container and volume survive; host port **32770 → 32771**
  is refreshed correctly; all three durability settings remain on.

Final ignored evidence:

- [Docker verdict / actual before-after container, volume, ports and durability](../../artifacts/p6-docker/checkpoint-20261027-final/docker-summary.json).
- [Exact Docker/child commands, outputs and exits](../../artifacts/p6-docker/checkpoint-20261027-final/docker-checks.json).
- [Inner verifier command evidence](../../artifacts/p6-docker/checkpoint-20261027-final/checkpoint/checks.json),
  [596-test JUnit](../../artifacts/p6-docker/checkpoint-20261027-final/checkpoint/pytest.xml).
- [13-assertion smoke](../../artifacts/p6-docker/checkpoint-20261027-final/checkpoint/smoke/smoke.json),
  [3-assertion container-restart replay](../../artifacts/p6-docker/checkpoint-20261027-final/checkpoint/smoke/database-restart.json).
- [Inspected resource limits](../../artifacts/p6-docker/checkpoint-20261027-final/resource-limits.json):
  1,000,000,000 NanoCPUs, 536,870,912 bytes memory, 134,217,728 bytes shared memory,
  128 PIDs. These are actual test-fixture limits, not a full application benchmark.

The final Docker project is retained, healthy, on loopback port **32771**. The
previous owned native P6 cluster on port 55487 was stopped with its data retained;
see [the scoped stop evidence](../../artifacts/p6-docker/native-cluster-stop.json).
Older native recheck commands above are historical; use the Docker instructions
below going forward. No unrelated PostgreSQL service was stopped.

**Manual recheck going forward**

1. Run `docker info` and `docker compose version`. On Windows if Desktop is
   stopped, run `docker desktop start`, select the intended local
   `desktop-linux` context and repeat the health check. No native fallback.
2. Run `uv sync --locked`, then
   `uv run --locked python benchmarks/manual/verify_p6.py`. Use a new `--out`
   directory for each run, or omit it to generate a unique directory.
3. Inspect `docker-summary.json`, `docker-checks.json`, `checkpoint/pytest.xml`,
   `checkpoint/smoke/smoke.json` and `checkpoint/smoke/database-restart.json` under
   the emitted Docker evidence path. Compare container ID, named volume, startup
   timestamps, actual before/after ports and durability settings. Test event
   capture remains explicitly doubled. Connection credentials stay local/ignored.
4. Use the handoff's exact scoped Compose `ps`/`stop` and smoke `--resume`
   instructions to inspect the retained Docker DB. Do not prune/reset Docker or
   delete volumes to obtain a green run.

Shared outbox/event builder/schema/metadata handoffs, real Kafka/Gold, full team
Compose/G0/G1/G3, performance and hosted CI remain incomplete or `NOT_RUN`.
This follow-up verifies Docker-backed P6 state, without implementing provider
modules or the P7 workflow.

---

### Milestone P7: Zero-Call Search, Quote, and Checkout Workflow

- **State:** stub verified; requested P7/J04 checkpoint complete. M1 storage,
  migration upgrade, concurrency and command replay use real Docker PostgreSQL
  **18.6**. Catalogue/Orders HTTP, event builder and transactional event capture
  are explicit doubles. This is not real G3, a shared outbox/Kafka pass, a
  performance run or a live assistant quality result. P8 remains not started.
- **Date/branch/base:** 27 October 2026 (Asia/Calcutta), existing
  `jaineel/j03-telemetry`, `3a98f343a6a0ae44f367b57b34453192570de108`.
  Starting tree was clean. User explicitly requested commit/push on this branch;
  no branch creation, force push, history rewrite or teammate implementation.
- **Authority read:** AGENTS.md, OWNERSHIP, this tracker, personal J04 brief;
  playbook P7; common §§3–6.2/8 and Appendices A/B; context/technology freeze;
  evaluation T-10; dataset §5's exact/null/size/occasion rules; runbook §§4/6/7.

**Changed paths and behavior**

- `services/conversation/{intent,gateway,workflow}.py`: dictionary-driven real
  deterministic parsing, exact decimal price bounds, clarification for unknown
  explicit/ambiguous constraints, unchanged hard filters and one lexical search
  maximum. Structured search bypasses extraction. Templates display supplied
  facts, exact quote totals and backend order status; text never purchases.
  Fixed mode has no generative provider integration. The monotonic search-turn
  deadline is 3,000 ms, passed downstream with the remaining time; provider
  transport remains bounded to 2 seconds. Stage timings retain null model time.
- `services/conversation/{app,state,database}.py` and
  `migrations/conversation/002_workflow.sql`: enable the existing turn/quote/
  checkout routes; preserve migration 001 and canonical DTOs. Persist a remote
  command/key before submission, and save results/confirmation bindings in M1
  transactions. Quote/cart/principal/version are checked, edits invalidate old
  confirmation, IDs cannot be rebound to another quote, and identical retries
  return the same resource. Response loss/503 remains unresolved rather than
  cancelled; pending checkout blocks edits until recovery. Same-quote transport
  aliases share the downstream key and resolve together. No stock/payment logic
  or independent event/outbox implementation was added.
- `tests/conversation/{test_intent,test_workflow,workflow_doubles}.py`: actual
  production parser/workflow against explicit provisional HTTP schemas/doubles,
  all 60 existing assistant fixture scenarios, malformed/unsupported constraints,
  malicious product text, no-results, provider failures, deadline exhaustion,
  quote mismatch/races/expiry, confirmation/principal isolation, concurrent
  requests, pending recovery after reopening M1 state, and P6 migration upgrade.
  Structured fixture cases replay their exact stored business inputs and a
  labelled test clock; production never imports those fixtures. Human label
  review/freeze remains incomplete; this does not certify human-reviewed quality.
- `benchmarks/manual/{p7_smoke,verify_p7}.py`: repeatable Docker-backed checks,
  explicit `--test-double-providers` opt-in and an independent real-HTTP mode.
  The smoke captures returned session/cart/SKU/quote/order IDs. It checks stale
  confirmation and response-loss recovery without hard-coded invented IDs.
  Raw command output, case/turn records, Docker facts and HTTP transcript are
  preserved in ignored artifacts. Missing DB/Docker and skipped tests cannot
  produce a completed verifier result.
- `services/conversation/README.md`, `docs/jaineel/p7_workflow.md` and this file:
  operational semantics, contract review items, reproducible commands, evidence
  and concrete manual checks. Shared specs, provider DTOs, locks/configs, infra
  and teammates' modules remain unchanged.

**Actual checks and retained evidence**

Commands ran from repository root with the existing locked Python **3.11** venv.
The verifier consumes the ignored local connection file without printing its
credentials. Only fresh per-test/per-smoke schemas are created and removed;
the existing Docker instance/volume and unrelated data are retained.

| Command | Actual result |
|---|---|
| `.venv/Scripts/python.exe benchmarks/manual/verify_p7.py --database-file artifacts/p6-docker/checkpoint-20261027-final/local-database.json --out artifacts/p7/checkpoint-20261027-final` | Exit **0**; **10/10** expected command outcomes; P7 **stub verified**. PostgreSQL server `180006`; fsync/full_page_writes/synchronous_commit all on. |
| `.venv/Scripts/python.exe -m pytest tests/conversation tests/projectctl tests/contracts tests/oracles tests/benchmarks tests/telemetry -q --tb=short -o junit_family=xunit1 -o cache_dir=artifacts/p7/checkpoint-20261027-final/cache --basetemp=artifacts/p7/checkpoint-20261027-final/test-temp --junitxml=artifacts/p7/checkpoint-20261027-final/pytest.xml` | **717 passed in 104.68 s**, zero failed/errors/skipped. One existing Starlette/httpx deprecation warning; no dependency change to suppress it. |
| `.venv/Scripts/python.exe -m benchmarks.manual.p7_smoke --test-double-providers --confirm-checkout --out artifacts/p7/checkpoint-20261027-final/smoke` | Exit **0**, **16/16 assertions**. Same order after injected response loss/retry; HTTP 202 remains PENDING; **zero model attempts**. |
| `.venv/Scripts/python.exe -m ruff check services/conversation tests/conversation benchmarks/manual/p7_smoke.py benchmarks/manual/verify_p7.py` and same paths with `ruff format --check` | Both exit **0**. |
| `.venv/Scripts/python.exe -m projectctl.schemas --check`; `.venv/Scripts/python.exe -m projectctl.conversation_contract --check` | Both exit **0**; canonical generated schemas/OpenAPI unchanged. |
| `.venv/Scripts/python.exe -m projectctl contracts check --all` | Expected exit **4**, status NOT_RUN for missing provider contracts/DTOs, event transport/outbox/local diagnostic and real readiness handoffs. This is not a full contract/integration pass. |
| `git diff --check`; protected-path `git diff --exit-code -- ...` | Exit **0**; exact protected paths and outputs retained in `checks.json`. |

The earlier full checkpoint passed 710 tests before final review added malformed
price, P6-upgrade and identity-isolation checks and kept an Orders 503 explicitly
unknown. Early failing probes caught the provisional fixture wrapper, the
string-only common error-details contract, and a case-specific fixture request
shape; fixed rather than skipped or weakened. The retained first/second/fourth
JUnit files under `artifacts/p7/` show those failures; the final result above
supersedes them. The initial successful checkpoint is retained separately.

- [Final checkpoint verdict](../../artifacts/p7/checkpoint-20261027-final/summary.json)
  and [exact commands, outputs and exits](../../artifacts/p7/checkpoint-20261027-final/checks.json).
- [717-test JUnit](../../artifacts/p7/checkpoint-20261027-final/pytest.xml).
- [60 assistant turn/control records](../../artifacts/p7/checkpoint-20261027-final/assistant_turns.jsonl)
  and [60 T-10/D-05 case records](../../artifacts/p7/checkpoint-20261027-final/tests.jsonl):
  fixed mode, explicit doubles, zero observed generative attempts, actual outcomes.
- [Docker identity/version/durability](../../artifacts/p7/checkpoint-20261027-final/database.json).
- [16-assertion smoke](../../artifacts/p7/checkpoint-20261027-final/smoke/smoke.json)
  and [captured requests, returned IDs and responses](../../artifacts/p7/checkpoint-20261027-final/smoke/http.json).

**Remaining dependencies and manual verification**

1. Reproduce the verifier with the explicit local Docker connection-file path
   and a new output directory. Inspect all 60 turn records: zero model attempts,
   null model time, honest no-results/clarification and dependency outcomes.
   Inspect the smoke transcript's search facts and exact authoritative quote.
2. Harsh supplies canonical dictionary/search/product/quote schemas/APIs and
   reviews revision, brand-key/display, and hard path-filter bindings. Common
   §5's M1 TurnRequest has no structured field despite §6.2's structured-control
   requirement: no public field/route was silently added. The local adapter
   bypasses extraction; HTTP structured controls use M2 `/v1/search`. Any future
   M1 schema extension needs Jaineel/Harsh consumer review.
3. Aditya supplies Orders acceptance/status/SSE, stable-key/repeated-quote
   deduplication and reviews the existing relative status-URL convention.
   Aditya/Vichitr supply shared builder/append bindings and caller-local DDL.
   The real application fails closed while those handoffs are absent.
4. After real providers are ready, follow [the P7 manual runbook](p7_workflow.md):
   launch M1 with fixed/false settings, run the real read/quote smoke without
   double flags, inspect the displayed quote, and explicitly select
   `--confirm-checkout` only for a simulated purchase. Verify old confirmation
   rejection after an edit; retry the exact checkout body/key; observe real
   Orders snapshots/SSE. Stop Orders or inject response loss; after recovery
   verify one order ID and no fabricated terminal state. Real execution is
   **NOT_RUN** here; full G3 stock/ledger reconciliation belongs to P8.
5. Optional live assist, human label review, real G1/G3, shared event delivery,
   hosted CI and performance remain **NOT_RUN/INCOMPLETE**. P8 is not advanced.

**Git publication:** requested commands are
`git commit -m "feat: implement P7 fixed conversation workflow"` and
`git push origin HEAD:refs/heads/jaineel/j03-telemetry` on the current branch.
The exact resulting commit, push output, remote-head check and final status are
recorded in [local publication evidence](../../artifacts/p7/checkpoint-20261027-final/publication.json).
Generated evidence/test databases/credentials are excluded from the commit.

**Checkpoint:** stop at P7. No P8 implementation or new branch.

---

### P1–P7 Audit and Fixes — 27 October 2026

- **State:** completed owner checkpoint; PostgreSQL state/restart real verified,
  catalogue/Orders/events explicitly stub verified. Real shared delivery and
  provider integration gates remain incomplete. P8–P11 were not implemented.
- **Branch/base:** `jaineel/j03-telemetry`,
  `9f1013bb7f2cdec6e9b4caa407540c4b58b2ee88`; initial tree clean. No staging,
  commit, push, merge, history rewrite, or unrelated-data cleanup.
- **Findings:** fixed dropped hard constraints, conflicting SSE versions,
  warmup duplicates counted as measurement goodput, incomplete cancellation
  journals, stale timestamped metrics, false per-case PASS exports, repeated
  draft-matrix source hashing, and host-dependent stub-test timing. The final
  timing fix preserves assertions and adds an explicit unit-test clock; real
  database/API/process/resource/manual checks retain real clocks.
- **Changed paths (22):**
  `projectctl/benchmark_adapter.py`;
  `services/conversation/{clients,intent}.py`;
  `benchmarks/{collectors,metrics,scheduler}.py`;
  `benchmarks/manual/verify_p7.py`;
  `tests/projectctl/test_cli.py`;
  `tests/contracts/test_clients.py`;
  `tests/oracles/test_reconciliation.py`;
  `tests/benchmarks/{test_metrics,test_scheduler,test_verifier_evidence,time_double}.py`;
  `tests/telemetry/{test_collectors,test_observation}.py`;
  `tests/conversation/{process,server,test_intent,test_process_workflow}.py`;
  `docs/jaineel/{P1_P7_AUDIT,progress}.md`.
- **Commands/outcomes:** clean Python 3.11.15 `uv sync --locked` installed 37
  packages; all runtime imports passed. Ran existing `verify_p1.py` through
  `verify_p7.py`. Final P1/P2/P3/P5/P6/P7 exits were 0; P5 used
  `--review-p1-p5`. P4 exited 1 solely for its original P4-only Git guard after
  its tests/schema/slow-publisher checks passed (10/11). Independent audit
  ownership passed for all 22 paths; that guard was not weakened.
- **Final command:** audit interpreter ran
  `benchmarks/manual/verify_p7.py --out artifacts/p1-p7-audit/20261027-audit/verifier-p7-final --database-file artifacts/p1-p7-audit/20261027-audit/verifier-p6/local-database.json`.
  Its complete six-directory regression suite had **737 distinct tests, all
  passed; zero failures, errors or skips**. Counts: conversation 216,
  projectctl 113, contracts 94, oracles 50, benchmarks 217, telemetry 47.
  Overlapping verifier/targeted suites are not added to that count.
- **Other checks:** Ruff lint passed; format check passed for 112 files;
  `projectctl.schemas --check`, `projectctl.conversation_contract --check`,
  `git diff --check`, protected-path checks and ownership all passed.
  `projectctl contracts check --all` correctly returned 4 for missing handoffs.
  Exact commands/output/exits are recorded in audit `checks.json`,
  `final-checks.json`, `final-verifier-command.json` and nested verifier checks.
- **Real verification:** original PostgreSQL preserved; a fresh Docker
  PostgreSQL 18.6 container used its retained volume across restart with
  durability on. Remapped loopback port 32772→32773 was refreshed correctly.
  Actual loopback M1 requests exercised session/cart creation/read/update,
  isolation, mutation replay/conflicts, search/quote, stale confirmation,
  unconfirmed checkout, lost response and recovery to one pending order.
  Catalogue/Orders/event capture are declared doubles. The 16-assertion smoke
  passed; 60 frozen scenarios produced zero model attempts. No paid/live model,
  performance matrix, SLO or real stock/ledger/Gold result is claimed.
- **Source/labels:** uploaded CSV checksum/source counts independently matched.
  Provider normalization/facet comparison remains NOT_RUN. Canonical fixtures,
  label hashes and automated LLM-adjudication history were preserved; human
  review remains NOT_RUN.
- **Evidence:** [complete audit](P1_P7_AUDIT.md),
  [final summary](../../artifacts/p1-p7-audit/20261027-audit/summary.json),
  [final JUnit](../../artifacts/p1-p7-audit/20261027-audit/verifier-p7-final/pytest.xml),
  [commands](../../artifacts/p1-p7-audit/20261027-audit/final-verifier-command.json),
  [scope](../../artifacts/p1-p7-audit/20261027-audit/ownership.json),
  [evidence index](../../artifacts/p1-p7-audit/20261027-audit/evidence-index.json).
  Raw reproductions, interrupted P1 and the initial P7 run (730 passed,
  7 timing failures) remain retained; final evidence uses a fresh directory.
- **Handoffs/manual recheck:** Harsh supplies canonical catalogue/facet/quote
  interfaces/manifests and brand/path review; Aditya supplies Orders and shared
  outbox/DDL; Vichitr supplies builder/transport/registry/analytics and environment
  bindings. Follow the audit's four manual recheck steps and inspect captured
  returned IDs/versions. Ready for the next reviewed integration stage once
  those handoffs exist; no real G0/G1/G3 completion claim.

---

### Milestone P8: Real G1/G3 Integration, Failures, and Reconciliation
- **State:** owner harness **stub verified**; real G1/G3, recovery and T-11
  **INCOMPLETE/NOT_RUN** because provider handoffs are absent. This is not a real
  integration pass. G4 is not complete; P9–P11 remain not started.
- **Dates:** 27–28 October 2026 (Asia/Calcutta).
- **Branch:** `jaineel/j03-telemetry` throughout; no new branch or PR.
- **Base Commit:** `9f1013bb7f2cdec6e9b4caa407540c4b58b2ee88`.
- **Brief Task:** J06
- **Git authorization:** user explicitly requested commit/push to this current
  branch. The 22 pre-existing P1–P7 audit paths were preserved. Only the 15 P8
  paths below are included in the P8 commit; pre-existing edits, including the
  earlier progress-file audit section, remain uncommitted. The original diff and
  status are retained in `artifacts/p8/20261027/preexisting.patch` and
  `status-before.txt`; `progress-before.md` preserves the original progress file.

**Implementation and changed paths (15)**

- `benchmarks/integration_cases.py`: 37 explicit case plans covering the frozen
  aliases, G1/G3, D-01/02/03/05 and T-01/03/07/08/09/10/11/12. Overlapping aliases
  deduplicate. Scenario execution still requires reviewed owner consumer bindings;
  a plan or a passing double does not establish domain integration coverage.
- `benchmarks/integration.py`: scoped fresh-case preparation, source/import/SKU/
  seed/projection prerequisites, explicit real/stub registration, immutable fixture
  capture before exercise, restricted runtime UUID/source-input binding, independent
  audit checks and per-case evidence. G1 checks actual physical archives versus
  logical effects; G3 requires transaction audits and bound workflow traces.
  Missing callbacks/providers remain visible. `benchmark reconcile` rechecks saved
  eval and benchmark projections, artifact hashes and admission journals without
  writing back to the original run or calling a provider.
- `benchmarks/integration_faults.py`: scoped acknowledged named barriers,
  restart attempts after lost stop responses, retained-volume recovery/deadlines,
  and separate T-11 analytics/Kafka schedules at measurement second 180 for 30 s.
  Real execution uses monotonic time; clock doubles exist only in labelled tests.
- `benchmarks/integration_clients.py`: actual M1 HTTP consumer for the existing
  integrated driver, owned OpenAPI validation, stable request/key propagation,
  explicit confirmation, bounded transport and no hidden mutation retry/fallback.
- `benchmarks/reconciliation.py`: real audits remain incomplete by default; a
  scoped reviewed binding is required before a complete real projection can pass.
  Existing independent stock, ledger, immutable quote and Gold checks are preserved.
- `projectctl/cli.py`, `projectctl/providers.py`: route evaluation/reconciliation
  to the harness, register case adapters explicitly, and optionally load the
  user-selected `PROJECTCTL_ADAPTER_MODULE`. Failed registration is evidence, not
  fallback. The existing missing-adapter diagnostic remains compatible.
- `benchmarks/manual/verify_p8.py`: locked-environment checkpoint, read-only
  provider inventory/source checks, Docker database verification, complete local
  regression, canonical setup sequencing and required evaluation commands.
- `tests/integration/{__init__,conftest,doubles,test_http,test_p8}.py`: 37 new
  tests with explicit HTTP/event/audit/fault/clock doubles. They exercise refusal
  of doubles in real mode, frozen expectations, runtime binding restrictions,
  corrupt/missing source/Gold evidence, bad acknowledgements, response loss,
  read-only rechecks and preserved failure semantics.
- `docs/integration_runbook.md`, `docs/jaineel/progress.md`: binding interface,
  pending owner review, concrete checkpoint/manual steps and actual outcomes.

**Commands actually executed and outcomes**

1. `uv sync --locked` — exit 0; Python 3.11.15, 38 resolved packages and
   37 installed packages audited. `uv.lock` was unchanged.
2. `.venv/Scripts/python.exe -m benchmarks.manual.verify_p8 --out artifacts/p8/20261028/checkpoint-02 --database-file artifacts/p1-p7-audit/20261027-audit/verifier-p6/local-database.json`
   — exit **4**, correctly signalling incomplete real providers; its harness
   checks all passed. Exact child commands/stdout/stderr/exits are in
   `checkpoint-02/checks.json` and the corresponding `.command.json` files.
3. The verifier ran `.venv/Scripts/python.exe -m pytest tests/conversation tests/projectctl tests/contracts tests/oracles tests/benchmarks tests/telemetry tests/integration -q --tb=short -o junit_family=xunit1 -o cache_dir=artifacts/p8/20261028/checkpoint-02/cache --basetemp=artifacts/p8/20261028/checkpoint-02/tmp --junitxml=artifacts/p8/20261028/checkpoint-02/pytest.xml`
   — **774 passed, 0 failures/errors/skips**, 105.78 s; 737 prior tests plus
   37 P8 tests. One upstream Starlette deprecation warning. The actual verifier
   records absolute cache/temp/JUnit paths and interpreter path in its command JSON.
4. Verifier Ruff lint/format checks over the P8 modules/tests, plus
   `python -m projectctl.schemas --check` and
   `python -m projectctl.conversation_contract --check` — all exit **0**.
   `git diff --check` also passed.
5. `python -m projectctl env up --profile local4c8g` — exit **4**, Vichitr's
   adapter unavailable. Subsequent dependent file09 §2 setup steps were recorded
   **NOT_RUN**; no migration/import/seed/projection mutation was attempted.
6. `python -m projectctl contracts check --all` — exit **4**: 3 local inventory
   checks pass, **51 required handoffs missing**. No replacement DTO was created.
7. `python -m projectctl eval run --suite contracts,data,smoke --config configs/evaluation.yaml`
   — exit **4**, 7 cases NOT_RUN. `--suite correctness` — exit **4**, 31 cases
   NOT_RUN. `--suite T-10,D-05` — exit **4**, 2 cases NOT_RUN. `--suite T-11`
   — exit **4**, separate analytics/Kafka cases NOT_RUN. Draft configuration,
   planned resources, missing infrastructure/schema locks, manifests/dictionary
   and real case bindings are retained as dependency reasons.
8. `python -m projectctl benchmark reconcile --run-dir benchmarks/results/6d1094d8-c037-4415-92ef-4bd2615b2d96`
   — exit **4**; absent original cases stay incomplete. The original evidence
   is unchanged and the new report is saved separately.
9. `git ls-remote --heads origin jaineel/j03-telemetry` confirmed the remote
   still matched the base before publication. Final staged scope and Git checks
   are retained separately in this milestone's evidence directory.

The authorized `git commit` / `git push origin HEAD:refs/heads/jaineel/j03-telemetry`
commands, return codes, resulting local/remote commit IDs and preserved dirty paths
are recorded in `artifacts/p8/20261028/publication.json` at publication time.

The final regression used actual Docker PostgreSQL 18.6 with durability enabled
for M1 state tests. Catalogue, Orders, events/outbox, audit and hook dependencies
in unit/contract tests are explicit doubles. The two existing PostgreSQL containers
were preserved. No real Kafka/registry/domain services existed to exercise.

The independent exact-source check passed: 20,000 observations, 19,998 canonical
candidates, 19,920 active, 78 inactive, 2 superseded and 323 unknown categories.
This is the existing independent source/profile check, not Harsh's complete
normalization/import verification or a completed D-01/D-02 integration gate.
Source CSV and generated evidence remain ignored. Performance values remain null.

Initial failures and skipped runs remain retained: the first regression without
the explicit database had 607 passes, 129 skips and one missing-diagnostic
compatibility failure; restoring the diagnostic fixed it without weakening that
assertion. `checkpoint-01` had 771 passes/no skips but one lint failure, fixed before
the final run. A new saved-journal test expectation was corrected to require the
existing P4 correctness exit 3 for a missing mandatory emission receipt; no
assertion was removed. The final `checkpoint-02` contains all current code tests.

**Evidence locations**

- [Final checkpoint summary](../../artifacts/p8/20261028/checkpoint-02/summary.json),
  [exact command ledger](../../artifacts/p8/20261028/checkpoint-02/checks.json),
  [JUnit](../../artifacts/p8/20261028/checkpoint-02/pytest.xml),
  [handoff inventory](../../artifacts/p8/20261028/checkpoint-02/handoffs.json),
  [independent source check](../../artifacts/p8/20261028/checkpoint-02/dataset_checks.json),
  and [evidence hashes](../../artifacts/p8/20261028/checkpoint-02/evidence_index.json).
- Real command attempts: `benchmarks/results/6d1094d8-c037-4415-92ef-4bd2615b2d96/`
  (7 smoke/data/contract cases), `benchmarks/results/e80860d1-1031-4baf-97c4-a69b712533c0/`
  (31 correctness cases), `benchmarks/results/1f4dc6b6-0fd4-4702-9927-56b5913b684d/`
  (T-10/D-05), `benchmarks/results/ab9db438-fda0-43ab-9f7a-69842b5296e4/`
  (T-11), each with `tests.jsonl`, `correctness.json` and manifests.
- Read-only recheck: `artifacts/projectctl/a59f3679-462d-4ea2-aade-b4033bbad8ee/`.
  All raw evidence is local and ignored; it is deliberately excluded from Git.

**Remaining dependencies and concrete manual verification**

1. Harsh supplies canonical catalogue/quote/facet schemas, source/normalized/SKU
   manifests, full normalization comparison, projection receipts/bootstrap and
   import/compaction barriers. Aditya supplies transaction APIs/DTOs, outbox/DDL,
   deterministic seed/payment controls and scoped stock/reservation/ledger/guard
   audits plus transaction fault hooks. Vichitr supplies the locked environment,
   Kafka/registry/events/transport, analytics publications/receipts/replay and
   retained-volume fault/observer bindings.
2. Follow [the P8 integration runbook](../integration_runbook.md) to review the
   exact export mappings and independent fixtures, register real consumer adapters,
   and freeze a ready configuration only after actual locks/manifests exist.
   Additional hook names are pending explicit owner mappings; no public endpoint
   or teammate implementation was invented to hide their absence.
3. Run file09 §2 setup in order, then rerun the verifier above with a **new** output
   directory. Inspect `tests.jsonl` and `correctness.json`; every required real
   case must execute, with no skips, before claiming P8 integration success.
4. Follow one success and one decline through the same session/cart/version,
   quote/confirmation/order, inventory/reservation, signed ledger, stock projection
   and active Gold generation. Confirm duplicates have multiple broker receipts
   but one effect. Verify named barrier acknowledgement before each crash and
   retained storage on restart; inspect each separate T-11 target's acceptance,
   finality and lag/outbox/pending-export/recovery evidence.
5. Replay into an initially empty isolated effective namespace, then repeat into
   that **same** target; compare logical totals and original operational stock/
   payment snapshots. Run `benchmark reconcile` against the actual saved run.
   Preserve exact failing requests/expected/actual responses and the named owner
   for any provider contract violation; keep the case failed/incomplete until rerun.

**Checkpoint:** stop at P8's available owner harness. Real integration depends on
the handoffs above. No baseline, performance matrix, report or live-model work was
started; P9 is not advanced.

---

### Milestone P9: Correct B0 Baseline & Controlled Performance Matrix

- **State:** stub verified for the available owner harness; real B0, G4/G5,
  optimization comparisons, C-BEST and stress/recovery measurements remain
  **NOT_RUN/INCOMPLETE**. P10 and P11 are not advanced.
- **Owner/branch:** Jaineel; existing `jaineel/j03-telemetry`, no new branch.
- **Base commit:** `165fa8cf2137d361a2eb5e0852bef7cd78ec9dd4`.
- **Brief task:** J07 / P9 only. No teammate implementation, public DTO or
  canonical shared specification was modified. No generative calls were made.
- **Preservation:** 22 pre-existing audit paths were captured before editing in
  `C:/Users/voraj/AppData/Local/Temp/payment-gateway-p9-before-ludwi0xe`.
  Unrelated work stays outside this commit; the overlapping benchmark adapter
  and progress file are staged by P9 delta. Commit/push uses the current branch
  as explicitly requested.

**Changed paths and behavior**

- `benchmarks/performance.py`, `benchmarks/experiment.py`: clean code and reviewed
  same-revision real correctness/resource/input evidence gates; short smoke
  before full B0; qualified baseline/diagnosis/hypotheses before candidates.
  Exact source/dictionary/fixture and per-series recipe hashes, actual preparation
  controls, independent audits and collectors are checked. Missing dependencies
  remain visible; stub/test artifacts cannot become final measurements.
- `benchmarks/performance_metrics.py`, `projectctl/artifacts.py`: raw finite versus
  sustained denominators, stage durations, sample/unresolved counts, actual
  resource provenance and nested raw evidence hashes. No target/sample results.
- `benchmarks/comparison.py`, `projectctl/cli.py`: all three paired repetitions,
  code/lock/resource/cache/source/quality checks, median/min/max and correct
  percent direction. Missing metrics stay null/INCOMPLETE; baseline-zero percent
  is undefined. Partition-only comparisons keep 32-MiB compact target/codec;
  I0/I1 must have equal business digests.
- `benchmarks/selection.py`, `benchmarks/planning.py`,
  `projectctl/benchmark_adapter.py`, `configs/core_matrix.yaml`: required rows,
  strict raw-verified completed-run reuse, reviewed measured C-BEST labels,
  independent O1/O2 plus O3 interaction evidence and ascending stress tiers.
  No default winner or invented provider optimization.
- `benchmarks/capacity.py`: three-repetition qualification, 99% admissions,
  complete cohorts, final-five-minute lag slope/end bounds, backlog/resource/OOM
  and generator checks, separate SLO-qualified capacity. Missing samples cannot
  establish sustainability; a failed/incomplete lower tier blocks escalation.
- `tests/benchmarks/test_{performance,performance_metrics,comparison,selection,capacity}.py`,
  `tests/projectctl/test_p9.py`: 49 P9 checks with explicit evidence/telemetry/
  callback doubles, not real performance/integration results.
- `benchmarks/manual/verify_p9.py`, [P9 handoff](p9_performance.md), this file:
  dependency checkpoint, receipt/callback contracts, actual evidence and exact
  smoke/baseline/matrix/compare/selection/manual steps. P10 is not implemented.

**Actual commands, results and retained evidence**

1. `.venv/Scripts/python.exe -m pytest -q` initially produced **509 passed,
   129 skipped, 185 setup errors**: Windows denied the default pytest temp
   directory; no PostgreSQL test URL was configured. The failed output remains
   at `artifacts/p9-full-pytest.txt`. No assertions/tests were weakened.
2. Final regression used the existing isolated Docker PostgreSQL **18.6**, port
   **32773**, with `fsync`, `full_page_writes`, and `synchronous_commit` all
   **on**. Its local URL was read without printing/committing credentials.
   Exact child command:
   `.venv/Scripts/python.exe -m pytest tests/conversation tests/projectctl tests/contracts tests/oracles tests/benchmarks tests/telemetry tests/integration -q --tb=short -o junit_family=xunit1 -o cache_dir=artifacts/p9/verification/cache --basetemp=artifacts/p9/verification/tmp --junitxml=artifacts/p9/verification/pytest.xml`.
   **823 passed, 0 failures/errors/skips**, one upstream Starlette deprecation
   warning, **1462.19 seconds**. Interpreter/command, stdout/stderr, exit, JUnit
   and sanitized database facts are retained in
   [verification evidence](../../artifacts/p9/verification/pytest.command.json).
   This is real M1 PostgreSQL with explicit provider/audit doubles, not a real
   integrated SUT pass.
3. `.venv/Scripts/python.exe -m pytest tests/benchmarks/test_performance.py tests/benchmarks/test_comparison.py tests/benchmarks/test_capacity.py tests/benchmarks/test_selection.py tests/benchmarks/test_performance_metrics.py tests/projectctl/test_p9.py -q`
   — **49 passed**, including after final eligibility/comparison corrections.
   This overlaps the 823 and is not added to that regression count.
4. `.venv/Scripts/python.exe -m benchmarks.manual.verify_p9` — exit **0** for
   expected dependency handling. Actual child exits are all **4**:
   `contracts check --all`;
   `eval run --suite correctness,smoke,T-10,T-11 --config configs/evaluation.yaml`;
   `benchmark run --workload W-PIPE --variants B0 --repetitions 1 --smoke --config configs/evaluation.yaml`;
   `benchmark run --workload W-PIPE --variants B0 --repetitions 1 --config configs/evaluation.yaml`;
   exactly **one** `benchmark matrix --matrix configs/core_matrix.yaml --config configs/evaluation.yaml`.
   All **37** evaluation cases are NOT_RUN. The matrix retained **73** result
   records including unresolved selection dependencies; no benchmark started,
   and every metric remains null/NOT_RUN. Commands/stdout/stderr and run evidence
   are linked from [checkpoint checks](../../artifacts/p9/5f5d40f9-dd4a-40cb-a8ef-7bd63d76cc32/checks.json).
5. Ruff lint/format for all P9 modules/tests, `python -m projectctl.schemas --check`,
   `python -m projectctl.conversation_contract --check`, and `git diff --check`
   passed. Canonical/provider specifications and `uv.lock` are unchanged.
   Final scope/staged-tree checks are retained under `artifacts/p9/staging/`
   and `artifacts/p9/verification/`.
6. Final staged-code snapshot (no pending audit code) ran `tests/projectctl`,
   `tests/benchmarks/test_experiment.py`, and all five new benchmark test files:
   **192 passed, 0 failures/errors/skips**, **34.76 seconds**, including the final
   P9 corrections. Exact command/snapshot/temporary paths and JUnit are in
   [staged verification](../../artifacts/p9/staging/final-command.json).
   The first snapshot attempt retained **181 passes and 11 failures** because
   the temporary snapshot lacked Git metadata for existing ignore-rule tests;
   the rerun used the existing repository metadata with the isolated staged
   working tree. No branch was created and no test was weakened. Prior output
   remains `artifacts/p9/staging/pytest.stdout.txt`.
7. `uv sync --locked` — exit **0**, 38 packages resolved and 37 audited; no
   application lock change. Final machine-readable check records are in
   `artifacts/p9/verification/final-checks.json`.

**Remaining dependencies and concrete manual verification**

- **Harsh:** reviewed canonical/active-SKU/facet/query manifests and real import,
  search, query and compaction adapters; independently expected logical results,
  digests, plans and index costs.
- **Aditya:** real transaction/simulator seed, scoped stock/ledger/finality
  exports and acknowledged retained-volume relay/saga recovery hooks.
- **Vichitr:** locked real environment/transport, enforced full service and
  generator allocations, pinned images, real collectors/active membership,
  one-second cgroup/OOM readings and consumer-pause/recovery hooks.
- **All owners:** real correctness/G1/G3/D/T coverage and frozen receipt review;
  clean same-revision B0, actual bottleneck and predeclared hypotheses. Draft
  config, absent bindings and missing receipt block every real trial. No profile,
  dictionary hash, result or C-BEST winner was fabricated. A new unregistered
  combined treatment requires its provider's implementation/review.

Follow [the exact P9 sequence](p9_performance.md): freeze revision/resources and
source/fixture hashes; execute real short smoke and one complete B0; inspect
emissions/timings/lag/resources/active Gold and independent stock/ledger audits.
Save the measured bottleneck before the matrix. Run the matrix once, manually
compare all three repetitions with equal controls (including finite import and
partition-only boundaries), review measured choices/costs, then resume verified
selected/stress/recovery rows. Retain failed trials and read missing/cohort/
capacity evidence alongside quantiles. Stop before P10.

---

### P1–P9 Audit and Fixes — 28 October 2026

- **Scope/status:** requested audit completed for available Jaineel-owned P1–P9
  code. **840 distinct tests passed**, no failures/errors/skips. Real provider
  integration/performance remains **INCOMPLETE/NOT_RUN**; P10/P11 not advanced.
- **Branch/authorization:** existing `jaineel/j03-telemetry`; no commit, push,
  merge, reset, unrelated data cleanup or model call. All 22 pre-existing dirty
  paths were captured before editing. Twenty are byte-identical; intentional
  additional edits to `benchmarks/collectors.py` and this progress file preserve
  their earlier content. HEAD/branch/staged diff remain unchanged.
- **Report/evidence:** [P1–P9 audit](P1_P9_AUDIT.md),
  `artifacts/p1-p9-audit/20261028-audit/`. Exact command arrays, raw stdout/stderr,
  UTC timings/exits and JUnit remain in `*.command.json`, `*.stdout.txt`,
  `*.stderr.txt`, `final.xml`; scope, hashes and incremental source delta are
  in `ownership.json`, `evidence-index.json`, `audit-delta.patch` and
  `source-snapshot/`.

**Additional findings/fixes**

1. High P5/P9: offline latency summaries inferred cohort size from received
   timers. Join the frozen plan/emissions, retain missing/unresolved timings,
   validate identities/namespaces/clocks and original duplicate offers, and
   block P9 promotion on incomplete primary stages.
2. High P9: stage quantiles inherited admission unresolved counts. Preserve the
   actual stage unresolved count/null and collector/CPU incompleteness.
3. High P9: the loader trusted saved metric values after checking file hashes.
   Rebuild rates/metrics from raw evidence and require agreement for comparison,
   resume and selection; recheck the plan/admission journal independently.
4. Medium P8: cancellation bypassed per-case/final manifest persistence. Retain
   the interrupted case as INCOMPLETE and remaining cases as NOT_RUN; execute no
   later callbacks. Regression covers prepare, exercise and audit cancellation.
5. Medium P5/P9: cgroup samples omitted the OOM counter their capacity consumer
   required. Read `memory.events`; absent counters remain null.
6. High P9: one memory reading per service could qualify a 600-second tier.
   Require valid per-service resource/OOM coverage at every measurement second.
7. Medium CI: neither job scheduled `tests/integration`. Add standalone lint,
   format and pytest steps to the Windows/Linux offline job; hosted CI NOT_RUN.
8. Medium P6 verification: fixed test namespaces shared PostgreSQL advisory-lock
   scopes across isolated schemas. Use fresh test namespaces; a real two-connection
   regression proves isolation without increasing production/test timeouts.

**Changed paths (15, including documentation)**

`.github/workflows/offline.yml`;
`benchmarks/{capacity,collectors,experiment,integration,observation_summary,performance,performance_metrics}.py`;
`tests/benchmarks/test_audit_evidence.py`;
`tests/conversation/{conftest,test_state}.py`;
`tests/integration/test_audit_cancellation.py`;
`docs/jaineel/{P1_P9_AUDIT,p9_performance,progress}.md`.

**Commands and actual outcomes**

- `uv sync --locked --cache-dir artifacts/p1-p9-audit/20261028-audit/uv-cache`:
  exit 0, 38 resolved/37 installed packages audited, Python 3.11.15; lock unchanged.
- Baseline full owned suite: **823 passed**, 152.59 s. Final exact command:
  `.venv/Scripts/python.exe -m pytest tests/conversation tests/projectctl tests/contracts tests/oracles tests/benchmarks tests/telemetry tests/integration -q --tb=short -o junit_family=xunit1 -o cache_dir=artifacts/p1-p9-audit/20261028-audit/final-cache --basetemp=artifacts/p1-p9-audit/20261028-audit/final-tmp --junitxml=artifacts/p1-p9-audit/20261028-audit/final.xml`:
  **840 passed, 0 failures/errors/skips**, 164.39 s. Seventeen regressions added.
  Targeted/manual/CI counts overlap these and are not added. One upstream
  Starlette deprecation warning remains.
- All `benchmarks.manual.verify_p1` through `verify_p9` exist and were executed
  using `.venv/Scripts/python.exe -m`. P1/P2/P3/P5/P7/P9 returned 0; P4 returned
  1 solely for its original P4-only protected-path guard (10/11 checks). The
  audit's ownership check verifies the actual P1–P9 authorization; guard unchanged.
- P6 first run retained **797 passed/1 failed** from cross-suite advisory-lock
  contention. The focused real PostgreSQL reproduction failed before the namespace
  fix; corrected state/workflow tests passed **124**. Final
  `verify_p6 --external-database --out artifacts/p1-p9-audit/20261028-audit/verifier-p6-final`:
  exit 0, **800 passed**, all 10 expected outcomes, real API/process-restart smoke.
- `verify_p7 --out artifacts/p1-p9-audit/20261028-audit/verifier-p7 --database-file artifacts/p1-p7-audit/20261027-audit/verifier-p6/local-database.json`:
  exit 0, **798** passes at that intermediate checkpoint, **60** fixed scenarios,
  **0** model attempts, **16/16** smoke assertions. No real provider claim.
- `verify_p8 --out artifacts/p1-p9-audit/20261028-audit/verifier-p8 --database-file artifacts/p1-p7-audit/20261027-audit/verifier-p6/local-database.json`:
  exit **4**, harness checks passed and **839** passes before the last test was
  added. Setup `env up` exited 4; ten dependent setup steps stayed NOT_RUN.
  Contract/smoke/correctness/T-10,D-05/T-11/read-only-recheck exits are 4; required
  coverage is **37 distinct NOT_RUN** cases after alias deduplication.
- `verify_p9`: checkpoint exit 0; all five real command attempts exited **4**;
  one short smoke, one full B0 and 73 matrix records stayed blocked. P1 also
  invokes a blocked matrix preflight. No performance workload or long matrix ran.
- `.venv/Scripts/python.exe -m pytest tests/integration -q --tb=short --junitxml=artifacts/p1-p9-audit/20261028-audit/ci-integration.xml`:
  exit 0, **40 passed**, standalone CI test surface.
- Broad Ruff lint and formatting over owner implementation/tests passed (136
  formatted files). `python -m projectctl.schemas --check`,
  `python -m projectctl.conversation_contract --check`, `git diff --check`,
  protected-path checks and final ownership/history checks passed. Exact arrays
  and outcomes are in the report and command ledger.

**Real execution, prior results and handoffs**

Existing isolated Docker PostgreSQL 18.6 on loopback port 32773 had fsync,
full_page_writes and synchronous_commit on. The database container was not
restarted; application service restart and persistence were exercised. Existing
containers/volumes were preserved. Tests use fresh schemas and delete only their
own schemas. Catalogue/quote/Orders/event/outbox/audit/fault/cgroup dependencies
are explicit doubles in the tests requiring them.

Actual M1 HTTP flows cover session/cart/search/quote/confirmation/checkout,
duplicate keys, changed inputs, stale versions, cross-user/namespace isolation,
unavailable catalogue, lost response/unknown outcome and same/new-key recovery
to one PENDING order. IDs/versions and all 19 requests are retained in
`final-tmp/test_network_workflow_isolatio0/http.json`; failures remain visible.

The independent exact-source check passed. Twelve tracked fixture/history files
remain unchanged; automated LLM adjudication is preserved, human review NOT_RUN.
The previous documented P9 checkpoint's **77 distinct run bundles/230 indexed
files** passed hash/schema checks. All performance metrics were null/NOT_RUN;
there are no measured results to mark stale. Original artifacts are preserved.

Harsh still supplies canonical catalogue/search/quote contracts, manifests,
normalization/import/projection and query/layout adapters. Aditya supplies real
transaction APIs, simulator/stock/ledger audits, shared outbox/DDL and fault hooks.
Vichitr supplies locked infrastructure, Kafka/registry/transport, analytics
membership/replay/deployment and observer/fault bindings. Contract inventory is
3 local passes/51 missing handoffs. G0/G1/G3/G4/G5, real T-11 outages, controlled
baseline/candidates, C-BEST and stress/recovery remain incomplete.

Manual continuation: use a new evidence directory and the locked interpreter;
read the ignored DB connection file without logging credentials, then repeat the
full regression command. After provider handoffs, follow canonical setup in order,
rerun P8 and inspect actual case/barrier/audit evidence. Review/freeze all locks,
fixtures/resources and a clean code revision before the P9 smoke/B0/paired matrix
in [the P9 handoff](p9_performance.md). The user prohibited commit/push here.

**Checkpoint:** owner-code audit complete; real integration/performance is not
certified. Stop before P10/P11.

---

### Milestone P10: Reproducible Report and Clean Setup Rehearsal
- **State:** owner report/reconciliation implementation and available clean-clone
  checks verified; real setup, performance and release **INCOMPLETE/NOT_RUN**.
  P11 is not started.
- **Owner/branch:** Jaineel; existing `jaineel/j03-telemetry`, as explicitly requested.
- **Base commit:** `aa26daf` (P9). No new branch, shared-spec/DTO/provider change,
  namespace reset, tracker update or generative call.
- **Brief task:** J07 / P10 only.
- **Preservation:** 35 initially dirty/untracked files and their bytes/diff were
  captured in `artifacts/p10/before/`. Existing raw-validation prerequisites in
  `benchmarks/{performance,performance_metrics,observation_summary}.py` are included
  because P10 must independently rebuild saved values and cohorts. Only the
  relevant raw-evidence cases of the existing untracked
  `tests/benchmarks/test_audit_evidence.py` enter the index; its other tests stay
  in the working tree. The progress file is staged from HEAD plus this P10 section,
  preserving the earlier uncommitted audit text. Other audit changes stay uncommitted.

**Changed paths and behavior**

- `benchmarks/reporting.py`, `projectctl/report_models.py`,
  `contracts/evaluation/report.schema.json`: deterministic saved-matrix report,
  required/optional tables, all repetitions, raw trace and hash index; missing,
  failed, corrupt, mixed-stub and incomparable evidence cannot establish completion.
  Exact metric DTOs preserve units, counts, cohorts, unresolved work and raw paths.
- `benchmarks/comparison.py`: three-run spreads, absolute zero-baseline changes,
  raw-emitted latency/resource directions and negative cost changes are visible.
- `benchmarks/saved_reconciliation.py`, `projectctl/cli.py`, `projectctl/schemas.py`:
  wire report building and workload-specific read-only rechecks. Import/query runs
  use their independent logical audit rather than the stream oracle. Explicit
  existing stub/evaluation checks retain their labelled compatibility path.
- `benchmarks/manual/verify_p10.py`: fresh clone, fresh locked virtual environment,
  explicit indexed evidence/source export, unique benchmark namespace, canonical
  setup chain, independent contract/data/smoke checks, identical report rebuilds,
  and corruption detection only on a disposable copy. No hidden local credentials,
  environment file, test database URL or provider adapter is copied.
- `tests/projectctl/test_p10.py` and relevant raw-evidence tests: 19 new report,
  arithmetic, provenance, identity, corruption, repetition and dispatch checks.
  Positive presentation/dispatch fixtures use explicit loader doubles and are
  not real integration/performance passes.
- `docs/integration_runbook.md`, [P10 handoff](p10_report.md), this file: exact
  command surface, source limitations, owner dependencies and manual review.

**Actual checks and evidence**

- `.venv/Scripts/python.exe -m artifacts.p10.run_checks` retains the exact child
  arrays, UTC timings/exits, raw output, database facts and JUnit in
  `artifacts/p10/verification/`. `uv sync --locked --cache-dir artifacts/p10/verification/uv-cache`
  passed; application lock unchanged.
- Full child command:
  `.venv/Scripts/python.exe -m pytest tests/conversation tests/projectctl tests/contracts tests/oracles tests/benchmarks tests/telemetry tests/integration -q --tb=short -o junit_family=xunit1 -o cache_dir=artifacts/p10/verification/cache --basetemp=artifacts/p10/verification/tmp --junitxml=artifacts/p10/verification/pytest.xml`
  — **859 passed, 0 failures/errors/skips**, 175.46 s; one upstream Starlette
  deprecation warning. Existing isolated Docker PostgreSQL 18.6, port 32773,
  durability enabled; fresh test schemas, no existing data reset. M1 database
  behavior is real; unavailable provider/outbox/transport/audit/fault dependencies
  are explicit test doubles. This is not a real full-system integration pass.
- Earlier targeted run: **31 passed**; broader projectctl/comparison/integration
  run: **188 passed**; final `tests/projectctl/test_p10.py`: **19 passed**. Counts
  overlap the full suite and are not added. Raw JUnit files remain in `artifacts/p10/`.
- Ruff lint and format checks for P10 modules/tests, generated-schema check,
  conversation-contract check and `git diff --check` all exited 0. Exact commands
  and stdout/stderr are in `verification/*.command.json` and sibling files.
- The actual preserved P9 checkpoint is supplied through
  `artifacts/p10/input/core_matrix_results.json`, with the original saved plan and
  hash-referenced independent source profile/evaluation bundle. It retains **73
  result records**, **37 NOT_RUN cases**, **300 indexed input files**, and zero
  measured performance values. `report build --matrix-results artifacts/p10/input/core_matrix_results.json --out artifacts/p10/report-1`
  returned **4** and wrote an INCOMPLETE report. Original P9 evidence is unchanged.
  No performance plot or C-BEST winner was fabricated.

**Clean rehearsal and commit verification**

- Implementation commit: `c5332aabeb579a63195e3fc76a7d6bcc469e6021`, same current
  branch. Its exact staged tree `07484f8103e93684bb19ae78664a1af14d67b7a2`
  independently ran the affected projectctl/performance/comparison/raw-evidence/
  integration suites: **206 passed, 0 failures/errors/skips**, 43.46 s.
  Command/cwd/tree hash, raw output and JUnit:
  `artifacts/p10/staged-verification/{command.json,pytest.stdout.txt,pytest.xml}`.
  This confirms P10 runs without the unrelated uncommitted audit implementation.
- Exact rehearsal command:
  `.venv/Scripts/python.exe -m benchmarks.manual.verify_p10 --revision c5332aabeb579a63195e3fc76a7d6bcc469e6021 --matrix-results artifacts/p10/input/core_matrix_results.json --source data/raw/flipkart_com-ecommerce_sample.csv --out artifacts/p10/rehearsal`.
  Actual verifier exit: **4**. Invocation/stdout/stderr are in
  `artifacts/p10/rehearsal-launch/`; exact child commands and outcomes are in
  `artifacts/p10/rehearsal/*.command.json` and `checks.json`.
- Isolated local clone and detached checkout exited **0**; its new Python 3.11
  environment installed the unchanged lock with exit **0**. The explicitly copied
  CSV matched file08 SHA-256
  `56f8f699c9e847356666c2eab3c3ab1244340f6a98ad08e39ea2199ebe993ad1`;
  independent accounting passed. No hidden local files, credentials or provider
  registration were copied. After execution, `git status --porcelain` in the
  clone was empty and its HEAD matched the implementation commit.
- Fresh namespace: `bench-p10-2a9f370467de45cebe08231b9c00e2c9`.
  `env up --profile local4c8g` returned **4** (real adapter unavailable);
  **10 dependent setup steps stayed NOT_RUN**. Independent contracts and
  contracts/data/smoke evaluations returned **4** with unavailable cases visible.
  Migrations, import, seed, projection and a real integrated flow did not execute.
- Both clean-clone report builds returned **4** and were byte-identical to each
  other and the original saved-input reconstruction. Removing `summary.json`
  only from a disposable copied run produced **4** and an empty accepted-run
  list. `missing_evidence_detected=true`; original/exported evidence is preserved.
  Performance-metric tracing and teammate reproduction remain **NOT_RUN**.
- Actual read-only attempts in `artifacts/p10/manual/checks.json`: one saved B0
  reconcile, all three saved B0/O1 repetitions through `benchmark compare`, and
  two report builds. Every child exited **4**; no workload ran. Reports at
  `artifacts/p10/final-report/` and `artifacts/p10/rebuilt-report/` were identical:
  raw report SHA-256 `92ef6abe69bf42b33a1cc4d45230fdb08ed90a03940270beccc780acf2d6ca37`.
  They contain **73 records, 37 NOT_RUN cases, 300 indexed input files, zero
  measured performance metrics**. The source-only quality table is INCOMPLETE
  because provider normalization/facet coverage remains NOT_RUN.
- Final local evidence inventory: `artifacts/p10/evidence-index.json`, including
  source/report references, command ledgers, JUnit, clone/source proof, refusals
  and Git/scope verification. Generated evidence and data remain ignored.
  The final documentation-only commit records these actual outcomes; push uses
  the existing `jaineel/j03-telemetry` branch without force or history rewriting.

**Remaining dependencies and manual verification**

Harsh supplies canonical catalogue/facet/quote contracts/manifests, normalization,
category quality, import/query/layout measurements and costs. Aditya supplies real
transactions, outbox/DDL, deterministic seed and independent stock/ledger/finality
audits. Vichitr supplies locked enforceable infrastructure, transport/analytics,
membership/replay, resource collectors and acknowledged faults. All owners review
same-revision correctness, B0/candidates, three paired repetitions, selection,
stress/recovery, real plots, cost conclusions and the clean setup rehearsal.

Follow [P10 commands and review](p10_report.md#commands-and-review). Reconcile each
actual run; compare all B1/B2/B3 against C1/C2/C3; rebuild the same saved report into
a new directory and check its bytes/hash. Trace a reported performance metric to
the raw observations, unit, denominator and nearest-rank sample calculation after
real measurements exist. This performance trace is currently NOT_RUN. In a new
explicit source/evidence export, run `benchmarks.manual.verify_p10` with the reviewed
committed revision and adapters. Inspect its lock/source proof, fresh namespace,
setup barriers, actual case statuses, identical rebuild and disposable corruption
refusal. Have a teammate repeat setup and one successful/declined checkout and
return the identity-linked trace/audit paths. Human review remains NOT_RUN.

**Checkpoint:** P10 owner implementation is reviewable; real P10/G4/G5/G6 release
is not certified. Stop before P11.

---

### Milestone P11: Optional One-Call Intent Fallback
- **State:** owner implementation/provider-spy correctness verified. Required real
  DE integration/performance and human-reviewed/live assistant quality remain
  **INCOMPLETE/NOT_RUN**. No subsequent milestone was started.
- **Owner/branch:** Jaineel; existing `jaineel/j03-telemetry`, as requested; no new
  branch. Base commit `98a2c0a7c6ba6c9311bf18caaf96e318c702f8a4`.
- **Brief task:** J05 / P11 only. No teammate implementation, public DTO/API,
  canonical shared specification, fixture labels, tracker or application lock changed.
- **Explicit sequencing exception:** after the playbook prerequisite was checked,
  the user answered **"Implement P11 now; keep real gates incomplete"**. This
  authorizes isolated optional-code/spy work; it does not complete G4/G5/G6. The
  actual P10 report still has `required_core_complete=false`, zero measured
  performance metrics and incomplete setup. Human review of the 60 labels remains
  `PENDING_NOT_PERFORMED`; no review/approval or live measurement was fabricated.
- **Preservation:** all 32 initially dirty/untracked paths were snapshotted in
  `artifacts/p11/before/`. The progress file is staged from HEAD plus only P11,
  preserving prior uncommitted audit text. Existing conservative parser fixes and
  their eight assertions, and the test namespace-isolation fix, are necessary P11
  safety/test prerequisites and enter this commit. Other audit work stays uncommitted.

**Changed paths and behavior**

- `services/conversation/{intent_fallback,intent,workflow,app}.py`: fixed default;
  explicit request/service/allow gates; deterministic parse first; conservative
  category-only fallback for an explicit supported apparel size. One bounded raw
  HTTP POST with strict schema, zero SDK/status/redirect retries, 1,500-ms maximum
  reduced to remaining turn time; one search inside the 3,000-ms turn budget.
  Explicit filters cannot change. Invalid/unsupported output, refusal and timeout
  return clarification/diagnostic. Product text never enters the model; templates
  and explicit purchase controls retain their existing behavior.
- `services/conversation/{state,database}.py`,
  `migrations/conversation/003_intent_diagnostics.sql`: private per-turn settings,
  actual usage/null, duration/error and separate embedding diagnostics. A durable
  attempt reservation survives later response/outbox rollback and prevents a
  second model request for that logical turn. Reused reservations clarify with no
  new latency sample/counter. Original provider settings survive configuration
  changes; execution/usage after a crash can remain unknown. The existing total
  ten-connection budget is nine ordinary slots plus one reserved audit slot.
- `tests/conversation/{intent_doubles,test_assist,test_workflow,test_intent,conftest}.py`:
  explicit spy/HTTP doubles, malformed output/extra fields, protected constraints,
  missing usage, actual timeout, remaining deadline, zero-model controls,
  identical/concurrent request replay and post-model event rollback. Same 60
  authored scenarios/backend exercised in both modes; no fixture labels changed.
- `benchmarks/assistant_evaluation.py`,
  `tests/benchmarks/test_assistant_evaluation.py`: original six-slot FP/FN/macro F1,
  separate recommendation/no-result/clarification/dependency outcomes and bounded
  call counts, actual diagnostic quantiles and missing samples. Different backend
  or trace identities and model-budget violations are rejected.
- `benchmarks/manual/verify_p11.py`: exact-command/raw-output/JUnit retention,
  explicit Docker PostgreSQL verification, same-fixture paired traces and evidence
  index. Live credentials/configuration are removed from its child environment;
  real provider cases still fail visibly. No live model call is made.
- `.env.example`, `services/conversation/README.md`,
  `docs/integration_runbook.md`, [P11 handoff](p11_assist.md), this file: explicit
  configuration, migration/provenance, sequencing exception and manual checks.

**Actual commands, results and evidence**

1. Initial read-only prerequisite evidence is retained in
   `artifacts/p11/prerequisites/`: **40 existing intent tests passed**, 0.32 s;
   real T-10/D-05 returned **4**, two NOT_RUN cases. This remains a historical
   pre-exception check, not the final implementation state.
2. The first new-test run without a database had **35 passed/67 skipped**; it was
   not accepted as full verification. `artifacts/p11/first.xml` is preserved.
   Focused runs with the explicit existing Docker DB then passed **319** and
   **321** tests with no failures/errors/skips. Their commands/raw outputs/JUnit
   are in `artifacts/p11/{focused,focused-durable}/`.
3. The first full run retained **965 passed/1 failed**, 202.43 s, in
   `artifacts/p11/full/`. A new assertion compared a monotonic-clock subtraction
   against literal 0.2 and failed on `0.200000000011...`. It now verifies the exact
   interval of the actual absolute deadline supplied to the adapter. No timeout
   or policy assertion was removed, widened or skipped. The two focused timeout
   checks then passed; `artifacts/p11/deadline.xml` remains available.
4. Final full verifier command:
   `.venv/Scripts/python.exe -m benchmarks.manual.verify_p11 --out artifacts/p11/final --database-file artifacts/p1-p7-audit/20261027-audit/verifier-p6/local-database.json`.
   Harness exit **0**; full child suite **966 passed, 0 failures/errors/skips**,
   **198.69 s**, one upstream Starlette deprecation warning. The exact child
   pytest array (all seven owned test directories), interpreter/cwd, UTC timings,
   stdout/stderr, JUnit and sanitized database facts are in
   `artifacts/p11/final/{pytest.command.json,pytest.stdout.txt,pytest.xml,database.json}`.
   Counts from earlier focused runs overlap and are not added.
5. PostgreSQL is the existing isolated Docker **18.6**, loopback port **32773**,
   with durability enabled. Tests create/delete only their own fresh schemas;
   existing containers/volumes and development data were preserved. M1 SQL is
   real. Catalogue/Orders/event/outbox/model dependencies are explicit doubles in
   tests requiring them. No full-system or live-model integration pass is claimed.
6. `uv sync --locked --cache-dir artifacts/p11/uv-cache` exited **0**; lock unchanged.
   Ruff lint/format, generated-schema and conversation-contract checks exited
   **0** in the verifier. Canonical specifications/public DTOs remain unchanged.
   The real `eval run --suite T-10,D-05 --config configs/evaluation.yaml` child
   still exited **4**, with both unavailable fixed cases NOT_RUN. Its actual
   run directory is named in `final/real-assistant-cases.stdout.txt`.
7. `final/assistant_comparison.json` retains **60 fixed + 60 assist** raw traces,
   each with **60 expected-outcome matches**, **56 non-dependency task outcomes**,
   **23 recommendations**, **5 correct no-results**, **12 correct clarifications**,
   **4 dependency failures**, and **0 model attempts**. None of these 60 texts is
   eligible under conservative v1; additional spy tests exercise actual attempts
   and failures. Original six-slot macro F1 is **0.9532163742690059**, explicitly an
   **unreviewed-label/synthetic diagnostic**, not certified or live quality.
   The fixture byte hash is pinned for reproduction; human label freeze is NOT_RUN.
   Live quality/latency/tokens/cost remain NOT_RUN/null; live calls **0**.

**Commit-source verification and checkpoint**

- Implementation commit: `3de86a9` on the same current branch. The exact tested
  tree was `74aaac3851f120900613bf38f4cc2062805408f7`.
- A new isolated archive of that staged tree ran all conversation, projectctl,
  contract and assistant-evaluation tests using the existing Docker database:
  **549 passed, 0 failures/errors/skips**, **108.35 s**, one upstream warning.
  This independently verifies P11 without unrelated uncommitted audit code,
  including the final private provenance/embedding fields. Exact command, cwd,
  tree hash, sanitized DB facts, raw output and JUnit are retained in
  `artifacts/p11/staged-verification/{command.json,database.json,pytest.stdout.txt,pytest.xml}`.
- Staged-source Ruff lint/format, generated schemas and conversation-contract
  checks also all exited **0**. `staged-verification/checks.json` records each
  exact command/exit. The checked tree matches the implementation commit exactly.
- `artifacts/p11/precommit/checks.json` verifies the 20-path ownership scope,
  empty whitespace errors, no generated data/results/credentials in the index,
  and unchanged application lock, public DTOs/contracts, fixtures and canonical
  specifications. Thirty original dirty/untracked files are byte-identical;
  the intentionally edited parser preserves all earlier content apart from its
  two new diagnostic type annotations. Earlier audit progress text is preserved
  outside the P11 section and remains uncommitted.
- Final evidence inventory: `artifacts/p11/evidence-index.json`; publication and
  preservation facts: `artifacts/p11/git-final.json`. Generated data, raw traces
  and benchmark results stay ignored. The final documentation-only commit records
  these outcomes; push is a normal fast-forward on `jaineel/j03-telemetry`.

**Remaining dependencies and manual continuation**

- Harsh: canonical catalogue/facet/quote contracts and manifests, independent
  normalization/query/import/layout evidence and costs.
- Aditya: real transaction/outbox/seed interfaces, stock/ledger/finality audits
  and acknowledged recovery controls.
- Vichitr: locked enforceable infrastructure, real transport/analytics/replay,
  membership, resource observations and fault bindings.
- All owners: execute/review the required correctness, measured baseline/paired
  variants, selection, stress/recovery and clean reproduction. Repeat the P10
  report and verify actual required-core completion from its raw evidence.
- Before certified assistant quality, have a human review/freeze the 60 existing
  scenarios and retain the reviewed hashes. Missing live access remains optional;
  live quality, latency, tokens and cost stay NOT_RUN/null.

Follow [the P11 manual checks](p11_assist.md#reproducible-checks-and-manual-review).
Run the verifier into a fresh directory with your own ignored Docker connection
record. After real handoffs, migrate M1, explicitly configure assist/allow and a
reviewed dated model privately. Compare fixed and eligible assist requests, inspect
protected filters, attempt rows and actual remaining deadlines. Recheck invalid/
timeout/injection cases with labelled doubles; replay the same request and the
isolated rollback case to confirm no second attempt. Inspect the two 60-scenario
trace sets and per-slot FP/FN; have a human review/freeze their hashes before final
quality claims. Keep live usage/cost null when unavailable. Restore fixed/false
for the required DE experiments and complete the outstanding real DE gates.

**Checkpoint:** isolated P11 code and spy correctness are reviewable under the
explicit sequencing exception. Real DE release and human-reviewed/live assistant
quality are not certified. Stop here; no subsequent milestone was started.

---

### P1–P11 Pre-push Verification — 28 October 2026

- **Scope:** audit/fix all implemented P1–P11 owner code, including the existing
  uncommitted harness fixes; no new milestone. P10/P11 summary rows now match
  their implemented checkpoints. Current branch remains `jaineel/j03-telemetry`;
  the user explicitly authorized commit and normal push on this branch.
- **Preservation:** canonical specs, public DTOs/contracts, migrations, fixture
  labels/adjudication history and the application lock are unchanged. Existing
  `P1_P7_AUDIT.md` and `P1_P9_AUDIT.md` remain untouched/untracked. No new audit
  document was created. Generated evidence stays in the existing ignored P11
  verifier directories; no credentials, raw data or results enter Git.

**Corrections verified**

- HTTP/SSE order responses must match requested order, user and supplied session;
  optional identity headers cannot be injected when absent from context. Conflicting
  payloads for the current SSE version are rejected.
- Search rejects duplicate SKUs, invalid rank order and unavailable hits. Paired
  assistant evaluation rejects duplicate scenario IDs and invalid/multiple search
  attempts. P7 selects only fixed traces from combined P7/P11 JUnit. P11 refuses
  unexpected real-evaluation exits, skipped tests and changed fixture bytes.
- P8 archives original reviewed fixture/review bytes so P10 can revalidate them;
  saved rechecks bind the execution fixture and repeat setup validation. Fault
  rechecks validate acknowledged identity/target/barrier, receipt continuity,
  retained-volume recovery and outage timing, not just a nonempty reference.
- Reviewed earlier fixes retain every scheduled operation and selected case on
  cancellation, separate warmup duplicates from measurement goodput, share live/
  rebuilt admission math, reject stale telemetry, retain actual OOM evidence and
  require per-service memory coverage each measurement second. Blocked matrix
  preflight avoids repeatedly scanning old results. CI includes integration tests.
- Migration CLI output now accurately names all three existing migrations.

**Changed paths (36)**

`services/conversation/{clients,database,workflow}.py`;
`projectctl/benchmark_adapter.py`;
`benchmarks/{assistant_evaluation,capacity,collectors,experiment,integration,integration_faults,metrics,reporting,scheduler}.py`;
`benchmarks/manual/{verify_p7,verify_p11}.py`;
`tests/benchmarks/{test_assistant_evaluation,test_audit_evidence,test_metrics,test_scheduler,test_verifier_evidence,time_double}.py`;
`tests/contracts/test_clients.py`;
`tests/conversation/{process,server,test_state,test_workflow,test_process_workflow}.py`;
`tests/integration/{test_p8,test_audit_cancellation}.py`;
`tests/oracles/test_reconciliation.py`; `tests/projectctl/test_cli.py`;
`tests/telemetry/{test_collectors,test_observation}.py`;
`.github/workflows/offline.yml`; `docs/jaineel/{p9_performance,progress}.md`.

**Actual verification and retained evidence**

- Baseline full verifier: **966 passed**. Reproductions of order/header identity,
  assistant budgets, review persistence, saved fault corruption and search-result
  defects failed before their fixes. Red/green JUnit files remain in
  `artifacts/p11/prepush-baseline-20261028/`; focused counts overlap the final suite.
- Final command:
  `.venv/Scripts/python.exe -m benchmarks.manual.verify_p11 --out artifacts/p11/prepush-verified-20261028 --database-file artifacts/p1-p7-audit/20261027-audit/verifier-p6/local-database.json`.
  Harness checks passed; **993 tests passed, zero failures/errors/skips, 190.32 s**.
  Ruff, generated schemas and conversation contract checks exited **0**. One
  upstream Starlette/httpx deprecation warning remains. The verifier retained exact
  commands, outputs, JUnit, sanitized DB facts, fixture hash and paired traces.
- `uv sync --locked` also passed with a fresh environment selected through
  `UV_PROJECT_ENVIRONMENT=artifacts/p11/prepush-clean-env-20261028`; Python 3.11.15,
  38 resolved/37 installed packages, all runtime imports passed. Broad Ruff lint
  and format checks passed for all 145 owner implementation/test files. Commands
  and exits are retained as `clean-*.command.json`, `lint-all.command.json` and
  `format-all.command.json` in the baseline directory.
- `.venv/Scripts/python.exe -m benchmarks.manual.p6_smoke --out artifacts/p11/prepush-baseline-20261028/p6-smoke-rerun`
  passed against the explicit isolated PostgreSQL URL. The first concurrent smoke
  returned 503/exit 1; PostgreSQL logged an `operation_keys` statement timeout.
  Its raw failed transcript/log is preserved. The standalone rerun passed without
  relaxing timeouts, and the final full suite ran without concurrent DB smoke.
- `.venv/Scripts/python.exe -m benchmarks.manual.p7_smoke --test-double-providers --confirm-checkout --out artifacts/p11/prepush-baseline-20261028/p7-smoke`
  exited **0**. `benchmarks.manual.slow_publisher --out artifacts/p11/prepush-baseline-20261028/slow`
  and `benchmarks.manual.observer_stall --out artifacts/p11/prepush-baseline-20261028/stall`
  (same interpreter and `-m`) exited **0**; the slow publisher's deliberate
  target-miss experiment remained exit **5**, with every operation accounted for.
- Actual TCP M1 requests cover session/cart read/write, search, quote, explicit
  checkout, duplicate/changed keys, stale versions/confirmations, cross-user and
  namespace access, response loss and recovery to one PENDING order, plus visible
  catalogue failure. Returned IDs/versions are in final verifier
  `tmp/test_network_workflow_isolatio0/http.json`. Process restart and rollback
  tests use real PostgreSQL 18.6, with all durability flags on. Existing Docker
  containers/volumes were preserved; no database restart was performed this time.
- Catalogue/Orders, event/outbox, model, fault and analytics dependencies are
  explicit doubles. Status/SSE identity/reconnect checks use HTTP transport
  doubles; no live Orders/Kafka/replay/stock/ledger/Gold pass is claimed. Fixed
  and assist traces retain the same 60 scenarios; fixed calls are zero and live
  model calls are zero. Provider spies cover eligible one-call fallback failures.
- Independent source checksum and 20,000-row disposition assertions passed;
  provider normalization/facet comparison remains NOT_RUN. Saved P10 report
  rebuilding twice reproduced the original exactly: **73 runs, 300 indexed
  inputs, 37 correctness cases, zero measured runs/performance values**,
  `required_core_complete=false` (`saved-report-check.json`). No workload rerun
  or new report document was generated for this check.

**Remaining handoffs and required reruns**

The following exact commands, prefixed with `.venv/Scripts/python.exe -m`, each
returned **4** and preserved missing-dependency evidence:

- `projectctl contracts check --all`;
- `projectctl eval run --suite correctness,smoke,T-10,T-11 --config configs/evaluation.yaml`;
- `projectctl benchmark run --workload W-PIPE --variants B0 --repetitions 1 --smoke --config configs/evaluation.yaml`.

Harsh must supply canonical catalogue/search/quote DTOs, manifests and import/
projection adapters; Aditya must supply Orders, shared outbox/DDL, seed, independent
stock/ledger audits and fault hooks; Vichitr must supply enforceable locked
infrastructure, Kafka/transport, analytics/replay, collectors and fault bindings.
Repeat these commands after their handoffs and inspect actual namespace-bound
receipts. Then complete same-revision real correctness, B0/paired variants,
selection and stress/recovery under the canonical runbook. No long matrix ran.

Earlier diagnostics produced before the cohort, cancellation, resource or evidence
validation fixes cannot certify the corrected implementation. Preserve originals
and regenerate relevant evidence after real handoffs. The inspected P10 report
contains no measured performance result to carry forward or invalidate. Real DE
release, human label review/freeze, live assistant quality/cost and hosted CI remain
unverified. Rebuild/reconcile new real results with P10; do not relabel old blocked
or synthetic runs as passing. The final local ownership, whitespace, index and
publication checks are recorded alongside the verifier evidence.

## Roadmap Prompt 1 — M1 search and intent regressions (7 November 2026)

Checkpoint: **implemented and tested**. Stopped at Prompt 1; Prompt 2 was not
started. Branch remains `jaineel/j03-telemetry`; no commit or push was requested
or performed. Existing untracked roadmap and P1–P7/P1–P9 audits were preserved.

### Changed paths and consumer behavior

- `services/conversation/workflow.py`: compare a displayed brand with the
  dictionary key using the file 08 NFC/whitespace/casefold rule. Missing or
  genuinely different brands still fail closed. Other whole-value facet,
  price, provenance, rank and availability checks remain strict.
- `services/conversation/intent.py`: version `rules-p7-v2`. Bind brands only
  with `brand` or `by` cues. Recognize explicit whole dictionary values before
  uncued terms, and mask those spans from unrelated slots: `brand Blue` must
  not additionally mean `colour=blue`. An unsupported suffix, conflicting
  values, an empty cue, or a partial compound such as `size M/L` or `size M
  and L` requires clarification before any search.
- Uncued colour/material extraction now intersects the provider's whole-value
  dictionary with a bounded modifier grammar. No new catalogue values are
  invented. Noisy values such as `skin`, `104`, `paper` and product nouns stay
  in the original `query_text` unless explicitly cued. `blue cotton shirt`
  retains its colour/material and has no brand; `laptop skin` remains text
  without an invented brand/colour. Uncued brand names also remain query text.
  Harsh/Jaineel should review this explicit free-text policy at the checkpoint;
  expanding the grammar later requires regression review, not dictionary edits.
- `tests/conversation/test_search_regressions.py`: **38 regression cases**
  using explicit synthetic HTTP/model doubles. Covers display/key case and
  Unicode normalization, word collisions, cued brands/facets, compounds,
  unknown/ambiguous constraints, zero-call fixed behavior, no search on
  clarification, and rejection of wrong/null provider brands.
- `docs/jaineel/progress.md`: this checkpoint and evidence/handoff record.

No canonical DTO, API, reviewed scenario, fixture label, dataset revision,
teammate implementation or catalogue test was changed. SHA-256 checks verify
the frozen 60-scenario file, application lock, both preserved audits and Harsh's
consumer test are byte-for-byte unchanged (`preserved-files-check.json`).

### Exact checks and retained evidence

Evidence root: `artifacts/jaineel/prompt1-20261107/` (ignored). Each test/check
has its exact argument array and exit code in `<label>.command.json`, raw
output in `<label>.log`, and JUnit XML where applicable. Here `PY` denotes
`.venv/Scripts/python.exe` and `OUT` denotes that evidence root; the command
JSON records the expanded executable and paths.

| Command | Actual outcome / evidence |
|---|---|
| `uv sync --locked` | Exit 0; Python 3.11.15, 38 resolved / 37 audited; `uv.lock` unchanged |
| `PY -m pytest tests/conversation/test_intent.py tests/conversation/test_search_regressions.py -q --tb=short -o cache_dir=OUT/pytest-cache --junitxml=OUT/red-corrected.xml` (before implementation) | Exit 1; **20 failed, 52 passed**; `red-corrected.*` |
| `PY -m pytest tests/conversation -q -ra --tb=short -o junit_family=legacy -o cache_dir=OUT/pytest-cache --basetemp=OUT/conversation-checkpoint-tmp --junitxml=OUT/conversation-checkpoint.xml` | Exit 0; **361 passed, 0 failed/errors/skipped**, 73.72 s; `conversation-checkpoint.*` |
| `PY -m ruff check services/conversation tests/conversation` | Exit 0; `lint-checkpoint.*` |
| `PY -m ruff format --check services/conversation tests/conversation` | Exit 0; all 28 files formatted; `format-checkpoint.*` |
| `PY -m projectctl.schemas --check` | Exit 0; no schema mismatches; `schemas.*` |
| `PY -m projectctl.conversation_contract --check` | Exit 0; current conversation OpenAPI; `conversation-contract.*` |
| `PY -m pytest tests/catalog/test_conversation_consumer_live.py -q -ra --tb=short -o cache_dir=OUT/pytest-cache --basetemp=OUT/catalogue-consumer-tmp --junitxml=OUT/catalogue-consumer.xml` (native Windows) | Exit 1; **5 setup errors**, `DurabilityUnavailable: Directory fsync requires the Linux data volume`; `catalogue-consumer.*` |
| `docker build --file infra/storage.Dockerfile --tag jaineel-prompt1-tests:20261107 OUT/linux-build-context` | Build exit 0; existing owner Dockerfile, unchanged copied application lock, pinned Python 3.11.15 base and uv 0.10.8; `linux-build.*` |
| Linux worker: `python -m pytest tests/catalog/test_conversation_consumer_live.py -q -ra --tb=short -o cache_dir=/testdata/cache --basetemp=/testdata/linux-catalogue-consumer --junitxml=/out/linux-catalogue-consumer.xml` | Exit 1; **4 passed + 1 XPASS(strict)**; `linux-catalogue-consumer.*` |
| Linux worker: `python -m pytest tests/catalog/test_conversation_consumer_live.py::test_workflow_accepts_a_real_brand_filter --runxfail -q -ra --tb=short -o cache_dir=/testdata/cache --basetemp=/testdata/linux-catalogue-brand-runxfail --junitxml=/out/linux-catalogue-brand-runxfail.xml` | Exit 0; **1 passed**; `linux-catalogue-brand-runxfail.*` |

Docker was initially stopped (`docker ps` could not reach the Linux engine);
`docker desktop start` succeeded. A new isolated test container was provisioned
from the exact PostgreSQL/pgvector image in `infra/images.lock.json`; existing
containers/databases were untouched. `database.json` records PostgreSQL **18.2**,
pgvector **0.8.1**, the pinned digest and all three durability settings **on**.
Tests used fresh `p6_test_` / `h_test_` schemas and cleaned only their own schemas.
The Linux worker mounted repository source read-only and used its own named
Linux data volume; its full Docker argument arrays, image ID and runtime names
are retained in `linux-*.command.json` and `linux-runtime.json`.

Earlier red/intermediate/full transcripts were retained, including the initial
test-harness session-ID omission, corrected pre-fix run, formatter corrections,
native Windows catalogue errors and successful reruns. The build command exited
0; an initial host-wrapper print hit a cp1252 UnicodeEncodeError after saving
its logs. The resulting image was verified and both Linux test runs executed.
Final pytest retains one upstream Starlette/httpx deprecation warning; no
assertion, timeout or dependency requirement was weakened to pass.

`summary.json` and `assistant_turns.jsonl` were derived from final JUnit evidence:
all **60 fixed + 60 assist frozen scenarios passed**, with **zero model attempts
for each frozen scenario**. Other eligible-assist tests exercise explicit model
spies; no live generative call was made. Scenario SHA-256 remains
`441c5becdcd7462972027f567c6cc419010d1b5770d21a3ae4ce85ead1f9dac9`.

### Harsh handoff, limits and manual verification

Harsh should review
`tests/catalog/test_conversation_consumer_live.py::test_workflow_accepts_a_real_brand_filter`
and remove its strict-xfail marker after reviewing this fix. Its exact unchanged
marker result is `[XPASS(strict)] workflow compares the brand key with the
displayed brand; see docs/harsh/handoff.md`. This causes the original suite's
exit 1; it is not reported as a green suite. Running that same test with
`--runxfail` passed. **The marker/file were left untouched.** After Harsh's
change, rerun the ordinary five-test consumer suite on Linux without
`--runxfail` and expect all five assertions to pass.

The Linux binding exercised real M1 Gateway/FixedWorkflow, real catalogue HTTP,
import/search/quote logic and PostgreSQL against Harsh's **small synthetic row
fixture**. Its event/outbox captures and schema cache are explicit test doubles;
this is not a full historical-catalogue, Kafka, real outbox or end-to-end
checkout integration claim. Those checks and live model quality remain
**NOT_RUN** here. The owned conversation suite uses real PostgreSQL with
explicit catalogue/Orders/event/model doubles and preserves checkout controls.
No benchmark or performance result was produced. Dictionary hash policy,
frozen W-SEARCH label/key questions and later roadmap prompts remain outside
this checkpoint.

For manual review, inspect `summary.json`, both Linux logs/XML files and the
120 `assistant_turns.jsonl` records. The isolated PostgreSQL container is stopped
after verification; its data and Linux test volume are retained. To rerun, use
the exact commands in the command JSON files, restart only the container named
in `database.json`, inspect `docker port <container> 5432` and refresh the saved
local port if Docker remaps it. `local-database.json` contains ignored local test
credentials and must not be committed. Reuse neither these synthetic fixtures
nor earlier owner sample measurements as certified quality/performance results.
## Roadmap Prompt 2 — contract review before implementation (7 November 2026)

Scope: M1 only, on `jaineel/j03-telemetry`; preserve Prompt 1 and both audits.
Common §7, the six conversation payloads in `shared/contracts/events.py`, and
Vichitr's pinned conversation schema define the existing wire shapes. Current
consumers are M4's ingestion/Silver/Gold path and Jaineel's reconciliation.
M02's producer review asks Jaineel to confirm UUID tool-call IDs and restricted
intent diagnostic references. This implementation accepts those existing shapes;
Vichitr/Jaineel should review emitted examples at this checkpoint. No schema,
DTO, topic, or M2-owned retrieval fact changes are authorized or needed.

`ADD_TO_CART` and `CONVERSATION_TURN` already have local transaction boundaries.
Add existing `INTENT_EXTRACTED` / `INTENT_REJECTED` and actual turn `TOOL_CALLED`
facts to that same transaction. `CHECKOUT_STARTED` requires `order_id`: emit on
validated Orders acceptance, with the local command-completion transaction;
before acceptance retain the pending command/confirmation, never invent an ID.
No canonical SESSION_CREATED or QUOTE_CREATED fact exists. Shared outbox DDL
and local diagnostic DDL are owner-supplied templates, to be installed by a
new forward migration in conversation storage only. Aditya owns relay behavior;
Kafka publishing is outside M1 request handling. Approved catalogue handoff
identifies `flipkart-v1-3a401f32ca99379f8298ce42`; runtime must explicitly bind
`CATALOG_DATASET_REVISION` and verify returned facet revisions rather than use
the stale `.env.example` revision. No dataset/hash policy is changed here.

### Prompt 2 checkpoint — implemented and tested

Stopped at Prompt 2. Branch remains `jaineel/j03-telemetry`; no commit/push or
work on Prompt 3. Existing Prompt 1 changes, roadmap and audits are preserved.
`preserved-files-check.json` verifies both audits, frozen assistant scenarios,
application lock, Harsh's consumer test and migrations 001–003 are unchanged.

Changed paths for this milestone:

- `services/conversation/events.py`: use Vichitr's public `EventCodec` and
  `SchemaCache.load`, with conversation producer identity and an explicit
  dataset revision. Load/check all pinned schemas once under a lock. Missing,
  malformed, incomplete or tampered mappings fail with dependency 503. Cached
  verified schemas continue working without Registry or cache-file access.
  `ready(database)` builds a schema-valid probe and calls Aditya's actual
  `append_outbox` inside a rolled-back savepoint; unusable outbox storage fails
  readiness. No probe is committed and no Kafka publisher is constructed.
  Real SQL errors retain `STORAGE_UNAVAILABLE`; other append/schema failures
  remain `DEPENDENCY_UNAVAILABLE`. Normal facts include dataset revision,
  `synthetic=true` and benchmark/simulation provenance.
- `migrations/conversation/004_shared_events.sql`: forward-only snapshot of
  the exact shared outbox and local-diagnostic templates, plus the M1-private
  bounded `intent_rejections` table. No earlier migration was rewritten.
- `services/conversation/database.py`: register migration 004, verify it and
  the required tables/columns at readiness, and update migration CLI output.
- `services/conversation/workflow.py`: collect actual turn tool calls with
  UUID identity, outcome and monotonic duration; emit the existing intent
  outcome shapes with private diagnostic references. Bind event provenance to
  returned facet revision before extraction/search. Record accepted checkout
  once, including the original request correlation, quote, cart, confirmation
  and Orders ID. Session locking and the durable downstream operation key
  prevent duplicate facts across concurrent/repeated transport keys. If append
  fails after remote acceptance, completion rolls back and the original command
  remains pending for recovery. Quote/session creation invent no domain event;
  M2 retains ownership of retrieval facts.
- `services/conversation/state.py`: commit turn response, tool/intent facts,
  event versions, private rejection storage, diagnostic/DLQ append and operation
  key in the same caller-owned transaction. Existing cart atomicity is retained.
  The deliberately separate model-attempt audit survives rollback as before.
- `services/conversation/intent.py`, `intent_fallback.py`: carry bounded
  malformed reply text privately, excluded from representations; retain it only
  in M1 diagnostic storage, never in responses/events/logs. `MODEL_OUTPUT_INVALID`
  uses Vichitr's helper and registered DLQ notice; private content hashes match
  retained content. Provider protocol failures with no returned reply retain
  finite diagnostics, without inventing unavailable raw bytes or usage.
- `services/conversation/README.md`: migration, cache/revision configuration,
  retry semantics, private references and exact test scope.
- `tests/conversation/doubles.py`: explicitly labelled capture double accepts
  the six existing M1 facts and declares its revision/diagnostic test bindings.
- `tests/conversation/test_shared_events.py`: 27 cases against the real shared
  codec, append, diagnostic helper and isolated PostgreSQL. Registry IDs and
  catalogue/Orders/model inputs are explicitly doubled. Tests cover missing
  schema/cache/configuration, checksum failure, ready/unready HTTP behavior,
  real insert rejection, schema validation, full rollback, private diagnostic
  atomicity, idempotency, checkout recovery, and upgrade from migrations 001–003
  while preserving existing carts, responses and historical migration hashes.
- `docs/jaineel/progress.md`: producer review and this evidence/handoff record.

### Executed checks and raw evidence

Evidence: `artifacts/jaineel/prompt2-20261107/` (ignored). `PY` below is
`.venv/Scripts/python.exe`; `OUT` is that absolute evidence directory. Each
named check retains exact expanded argument arrays/exit code in
`<label>.command.json`, raw output in `<label>.log`, and JUnit XML for tests.

| Exact command | Actual outcome / evidence |
|---|---|
| `docker start jaineel-prompt1-6bc91382e721` | Exit 0; restarted only the existing isolated Prompt 1 database |
| `uv sync --locked` | Exit 0, lock unchanged; `uv-sync.*` |
| `PY -m pytest tests/conversation/test_http.py tests/conversation/test_intent.py tests/conversation/test_search_regressions.py -q --tb=short` (exploratory, before DB binding) | Exit 1: 18 failed, 93 passed, 4 skipped. The new revision check assumed persistence state in standalone workflow tests; corrected it to check configured state. Raw output is in this session's tool transcript; final checks below supersede this exploratory run |
| `PY -m pytest tests/conversation/test_shared_events.py tests/conversation/test_http.py tests/conversation/test_search_regressions.py -q -ra --tb=short -o cache_dir=OUT/pytest-cache --basetemp OUT/focused-tmp --junitxml OUT/focused.xml` | Exit 1: **1 failed, 95 passed**; retained `focused.*` proves the duplicate-checkout-fact regression before the operation-key fix |
| `PY -m pytest tests/conversation -q -ra --tb=short -o cache_dir=OUT/pytest-cache --basetemp OUT/conversation-checkpoint-tmp --junitxml OUT/conversation-checkpoint.xml` | Exit 0: **386 passed, 0 failures/errors/skips**, 71.95 s; `conversation-checkpoint.*` |
| `PY -m pytest tests/conversation/test_shared_events.py -q -ra --tb=short -o cache_dir=OUT/pytest-cache --basetemp OUT/shared-events-final-tmp --junitxml OUT/shared-events-final.xml` | Exit 0: **27 passed, 0 failures/errors/skips**, 11.47 s; final focused run includes two subsequently added migration/HTTP checks; `shared-events-final.*` |
| `PY -m ruff check services/conversation tests/conversation` | Exit 0; `lint.*` |
| `PY -m ruff format --check services/conversation tests/conversation` | Exit 0; 29 files formatted; `format.*` |
| `PY -m projectctl.schemas --check` | Exit 0, no mismatches; `schemas.*` |
| `PY -m projectctl.conversation_contract --check` | Exit 0, OpenAPI current; `conversation-contract.*` |
| `PY OUT/capture_examples.py` with `PYTHONPATH` set to repo root | Exit 0; real M1/codec/outbox writes, explicit mapping/provider/model doubles. `capture-examples.*`, `review-examples/events.json`, `review-examples/summary.json` |
| `git diff --check` | Final exit 0; `diff-check.*`. An earlier trailing blank line in this progress entry was corrected |

`summary.json` reconciles the JUnit test identities: **388 distinct tests** passed
across the full suite and final focused run; overlapping tests are not counted
twice. Full-suite JUnit used the default xunit2 family, producing 120 existing
`record_property` compatibility warnings; the focused run has the one upstream
Starlette/httpx deprecation warning. No assertions or dependency checks were
weakened and no strict-xfail was removed. Intermediate lint findings were fixed.

PostgreSQL is **18.2**, from the exact `infra/images.lock.json` pgvector image
digest, with `fsync`, `synchronous_commit`, and `full_page_writes` all **on**.
`container.json` and `database-and-smoke.json` retain image/runtime evidence.
Tests created/dropped only their own `p6_test_` schemas; the example capture
created/dropped only its own `p2_smoke_` schema. No production database was
migrated or reset. The restarted container is stopped after verification and
its data volume is retained. Ignored `local-database.json` contains test
credentials; do not commit it or any generated evidence/cache.

The review capture retains all six existing M1 event types plus one registered
DLQ notice: 1 cart fact, 1 checkout fact, 2 turn summaries, 3 tool facts, 1 valid
intent and 1 rejected intent. All 10 original outbox payloads validate with the
shared pinned codec and remain unpublished. There are zero fixed-mode model
calls; the malformed-assist case uses one explicit model spy, no live model.
The earlier `event-examples.json`, `outbox-packets.json` and migration history
are also retained. These synthetic examples are owner-review evidence, not
catalogue quality, throughput, live Registry or end-to-end integration results.

### Owner handoffs, visible limits and manual verification

- **Vichitr/Jaineel:** review `review-examples/events.json` against common §7
  and M02/M03, including UUID tool IDs, `m1-turn:<turn_id>` restricted references
  and the producer's existing enum values. Supply/mount a real complete verified
  schema mapping for deployment. The default runtime cache is absent here:
  **fresh-service readiness with live Registry mapping = NOT_RUN**. The tests'
  schema definitions and hashes are real pins; their registry IDs are doubles.
- **Aditya/Jaineel:** compose the existing shared relay for conversation storage
  outside requests, then verify original stored identity/content on retries.
  **Real conversation outbox → Kafka → M4/Gold = NOT_RUN**. No relay or teammate
  code was implemented/edited here. Kafka downtime alone does not prevent local
  append with a verified cache and usable database.
- **Harsh/Jaineel:** bind `CATALOG_DATASET_REVISION` to the approved imported
  revision documented above; real catalogue provenance binding is **NOT_RUN**
  in this milestone. The stale root `.env.example`, dictionary hash review,
  relevance labels and provider concerns from Prompt 1 are untouched.
- Forward migration does not fabricate missing historical turn/checkout facts.
  Existing completed commands remain completed; accepted-checkout event coverage
  applies to new completions after deployment. Optional upstream HTTP/model
  protocol failures do not expose or invent raw bodies.

Manual replay: restart only the isolated container in `container.json`, refresh
the port in ignored `local-database.json` if Docker remaps it, set
`P6_TEST_DATABASE_URL` from its `url`, and rerun the final focused command above.
For emitted examples, set `PYTHONPATH` to repo root and run the retained
`capture_examples.py`. Inspect `review-examples/events.json`, migration history,
the rollback/idempotency JUnit cases and `summary.json`. For deployment, follow
the owned README: explicitly run the conversation migration CLI against its own
database, mount the real cache and set the approved revision, then check
`/health/ready`; removing required cache before a fresh process must yield 503.
Live provider/relay checks remain incomplete until the named handoffs are bound.

## Roadmap Prompt 3 — real projectctl composition (7 November 2026)

Implemented only roadmap Prompt 3 on the existing `jaineel/j03-telemetry`
branch. No commit, push, branch change, full benchmark, service startup, stock
seed, operational import, namespace reset or cross-service database write was
performed. Existing Prompt 1/2 work, both audit documents and the roadmap were
preserved. The `.env.example` edit is the explicit exception named inside Prompt 3.

**Code/setup checkpoint:** real existing registrations compose successfully;
all owned checks below pass. The actual original CSV profile passes. **Complete
live setup/readiness remains INCOMPLETE**, with unexecuted work NOT_RUN, because
owner namespace/migration/audit handoffs and the hash-policy review are missing.
Registration and explicit test doubles are not full-service integration passes.

### Changed paths and behavior

- `projectctl/jaineel.py`: explicit `register(registry)` composes
  `infra.analytics.register` (already calls streaming),
  `pipelines.catalog.adapter.register` and `services.inventory.adapter.register`.
  It does not additionally register postgres/streaming and cause duplicates.
- `projectctl/providers.py`, `projectctl/benchmark_adapter.py`: factories resolve
  workload bindings from each trial's config. Binding/factory duplicates are
  rejected; production factories must return real bindings. Failed module
  registration discards partial registrations. Factory failures retain dependency
  evidence without copying arbitrary exception text. Registration inventory is
  explicitly separate from runtime readiness.
- `benchmarks/composition.py`, `benchmarks/experiment.py`: actual importer,
  public HTTP search and Q1–Q6 query adapters are connected to their drivers.
  The catalogue projection uses Harsh's `runner_catalog_manifest` hash check,
  canonical owner DTO validation and consumer checks for source/rules, 19,920
  sorted unique active SKUs, listing identity, dataset revision and matching
  normalized-manifest digest. Missing explicit lifecycle slots are saved as
  dependencies before preparation, rather than filled by no-op callbacks.
  Source validation precedes fresh namespace acknowledgement. The search setup
  sequence is migrate → import → verify → seed → projection wait/ANALYZE →
  independent seed proof. Deferred records, wrong versions/counts, pending outbox
  and boolean values substituted for integer stock fields are rejected.
- `benchmarks/import_audit.py`: independent read-only CSV/Parquet reconciliation
  for selected observation identity, integer prices, activity, all exclusive
  source dispositions, active membership and hashes. No production normalizer
  or reducer is imported by the oracle. Facet normalization remains separately
  NOT_RUN. Import drain delegates to the actual owner verification adapter;
  the observer measures only the generator process, with no claim of SUT coverage.
- `projectctl/input_pins.py`: reports raw and LF-text hashes separately. It does
  not normalize the existing raw-file preflight or replace dataset identity.
- `.env.example`, `configs/evaluation.yaml`: evaluation already had four catalogue
  connections; the owner runtime example now also has `CATALOG_MAX_CONNECTIONS=4`
  and `CATALOG_REUSE_CONNECTIONS=false`. The approved catalogue revision, B0 row
  load mode, Orders' actual URL setting names, lakehouse root and optional model
  directory are reflected in the example. Existing `QUOTE_TTL_SECONDS=60` stays.
  Frozen matrix values and null dictionary/query/label pins remain unchanged;
  the draft/resource limitations are documented instead of declaring readiness.
- `projectctl/README.md`, `benchmarks/manual/verify_prompt3.py`: bounded checkpoint
  procedure, actual registration inventory, source/profile, contract/schema and
  dependency evidence. The verifier starts no Docker services or workloads.
- `tests/projectctl/test_composition.py`,
  `tests/benchmarks/test_real_composition.py`,
  `tests/benchmarks/test_import_source_audit.py`,
  `tests/integration/test_prompt3_setup.py`: explicit registration, factory,
  preflight, lifecycle ordering, seed/barrier failure, provenance, cross-platform
  hashing and corruption tests. Lifecycle/provider effects in unit tests are
  explicit doubles. The integration test calls the real catalogue profile
  adapter on the actual CSV and compares the independent source check; its scope
  is source/profile only, with no PostgreSQL/Kafka/service claim.

### Executed checks and evidence

Evidence root: `artifacts/jaineel/prompt3-20261107/` (ignored).
`PY` below is `.venv/Scripts/python.exe`. The checkpoint retains per-command
argument arrays, exit codes and separate stdout/stderr. The final check driver
also retains raw output, exact commands and JUnit. No evidence is committed.

| Command | Actual outcome / evidence |
|---|---|
| `uv sync --locked` | Exit 0; 38 packages resolved /37 audited; lock unchanged; tool transcript |
| `PY -m pytest tests/projectctl tests/benchmarks tests/integration -q -ra --tb=short --junitxml artifacts/jaineel/prompt3-20261107/owned-tests.xml` | Exit 0: **503 passed, no skips**, 131.28 s; `owned-tests.xml`, `owned-tests.tool-output.log` |
| `PY artifacts/jaineel/prompt3-20261107/run_checks.py` | Exit 0; exact expanded check argv and raw output in `*-final.command.json`, `*.stdout.log`, `*.stderr.log` |
| `PY -m pytest tests/projectctl/test_composition.py tests/benchmarks/test_real_composition.py tests/benchmarks/test_import_source_audit.py tests/integration/test_prompt3_setup.py -q -ra --tb=short --junitxml artifacts/jaineel/prompt3-20261107/focused-final.xml` | Exit 0: **41 passed, no skips**, 8.52 s; `focused-final.*`. This final run includes the subsequently tightened integer-money/stock-proof checks; counts overlap the broader run and must not be added |
| `PY -m ruff check projectctl benchmarks tests/projectctl tests/benchmarks tests/integration` | Exit 0; `lint-final.*` |
| `PY -m ruff format --check projectctl benchmarks tests/projectctl tests/benchmarks tests/integration` | Exit 0; 99 files already formatted; `format-final.*` |
| `PY -m projectctl.schemas --check` | Exit 0; all five schemas current; `schemas-final.*` |
| `PY -m benchmarks.manual.verify_prompt3 --out artifacts/jaineel/prompt3-20261107/checkpoint` | Expected dependency result **4/INCOMPLETE**; `checkpoint/summary.json`, `readiness.json`, `registrations.json`, `hash-review.json`, source checks and command logs |
| Checkpoint `PY -m projectctl --help` | Exit 0; `checkpoint/help.*` |
| Checkpoint `PY -m projectctl contracts check --all` | Exit **4**, not pass: available OpenAPI endpoints/examples validate, but shared outbox/transport/diagnostic/schema handoff review remains UNREVIEWED and real G0 smoke NOT_RUN; `checkpoint/contracts.*` links the original CLI evidence directory |
| Checkpoint `PY -m projectctl catalog profile --source data/raw/flipkart_com-ecommerce_sample.csv --rules flipkart-v1 --out artifacts/jaineel/prompt3-20261107/checkpoint/profile` | Exit 0; actual 20,000 observations, 19,998 canonical, 19,920 active, 78 inactive and 2 superseded; `checkpoint/catalog-profile.*`, `checkpoint/profile/` |
| Checkpoint `PY -m projectctl env reset --namespace bench-prompt3` | Expected dependency exit **4**, no reset; `checkpoint/missing-reset.*` |
| `git diff --check` | Exit 0; `diff-final.*`; rechecked after this progress entry |

Exploratory focused tests first encountered a duplicate test basename during
collection, then **6 fixture failures /17 passes**: the new fixture omitted
canonical descriptor fields and attempted to overwrite an exclusive evidence
file. The test file was renamed and the fixtures corrected without weakening
schema checks. The next run passed **32 tests**. Final focused coverage adds
strict integer/boolean and seed/pool cases. Early formatting/lint findings were
fixed. Exploratory output remains in the tool transcript; final saved runs above
are the reproducible checkpoint. No required assertion or provider check was skipped.

### Exact conflicts and remaining owner handoffs

1. **Harsh/Jaineel and affected SKU/provenance consumers:** file09 §1 says raw-file
   hashes cover exact bytes. `pipelines/catalog/normalize.py:load_dictionary`
   instead hashes universal-newline UTF-8 text and uses that value in
   dataset_revision. On this Windows checkout dictionary raw SHA is
   `7de194b5f49538e84a43ce91e734acae2182a0c96e3b743d668695ad6c6c2a02`,
   while LF-text/published SHA is
   `a7d381e90986b23f801eca537a689f2d3e056fa0b58040ecb7c182e2be2f9943`.
   Query raw SHA is
   `14733547c0ce5690a79e3ea633d2b5ecdb0b5a133fd30e3fffcc175cf0ffcd63`,
   while LF-text/published SHA is
   `89d89ac030f10d23e85d6e5084caa125017b5f927a1ed94854aadc3be4762410`.
   The cross-platform test proves raw hashes differ while text identity matches.
   Review a canonical-byte distribution policy or an explicitly versioned split
   between raw artifact hashes and semantic identity before filling pins. No
   unilateral raw-preflight/spec/dictionary/revision change was made. Rule labels
   are not selected or certified as human-reviewed; session reuse stays disabled.
2. **All storage owners/Jaineel:** supply reviewed fresh benchmark namespace
   preparation and owner-local migration coordination. `infra.analytics.migrate`
   still reports only analytics migrated and exit 4. There is no global reset
   provider. Missing implementations were not invented or replaced with SQL.
3. **Aditya/Harsh:** expose/adopt complete initial stock, version, deferred and
   relay acknowledgement audits. The current catalogue projection adapter counts
   projected rows; it does not by itself prove every initial value/version or
   reject a nonzero deferred backlog. The consumer therefore requires the
   independent seed proof after the owner's real projection barrier.
4. **Harsh/Vichitr/Jaineel:** supply reviewed frozen snapshot/layout/query-day,
   downstream drain, independent read-only service audit and SUT collectors.
   W-PIPE/W-QUALITY publisher composition and all real integration case bindings
   remain unavailable. W-ANALYTICS uses the actual query adapter only after these
   bindings exist; it does not choose an empty snapshot or infer the query day
   from a publication timestamp. The current adapter's DuckDB connection lifetime
   and complete query evidence still need lifecycle review before execution.
5. **Infrastructure/config owners:** the environment adapter accepts
   `streaming-local`, while frozen evaluation names planned `local4c8g`.
   No alias pretending resources were enforced was added. Freeze/verify the real
   profile, schema cache and exact locks before marking evaluation config ready.

Manual reproduction: run the bounded verifier into a **new** output directory,
inspect the registration/hash/readiness files and real profile. Run the final
focused command above and inspect JUnit. After owner callbacks/reviews arrive,
compose them explicitly using the documented harness slots; apply the pool/env
settings to the actual catalogue process, use a fresh `bench-*` namespace and
follow file09 §2 in order. Retain each setup result and stop at the first missing
dependency. Independent audit failures must remain failures. Real import/seed,
stock projection, PostgreSQL/Kafka smoke, full correctness and all performance
measurements remain **NOT_RUN** in this checkpoint. Stop before Prompt 4.

### Docker cleanup and continuing preference

The user requested removing containers no longer needed after this and later
prompts. No new container was needed here. After the tests, re-inspected the
three remaining, stopped Jaineel Prompt 1/2 containers and saved safe metadata
plus their stdout/stderr. Ran `PY artifacts/jaineel/prompt3-20261107/cleanup_containers.py`,
which executed `docker rm` only for these exact verified stopped containers:

- `jaineel-prompt1-7660a7233f0c-linux-catalogue-brand-runxfail`
- `jaineel-prompt1-7660a7233f0c-linux-catalogue-consumer`
- `jaineel-prompt1-6bc91382e721`

Exit 0. `docker-before.json`, `docker-cleanup.json`, `docker-rm.*` and
`docker-after.log` retain evidence. Final `docker ps -a` is empty. Both mounted
data volumes were independently verified retained: the named
`jaineel-prompt1-7660a7233f0c-data` and PostgreSQL volume
`ec6e8327617d0e19d7f19999c7da412abdd70ffa6b1ae6c2f58bc6c6a73b14e7`.
No volume/image prune ran. Three older P6 containers from the first inventory
were already absent on reinspection; they were not removed by this command.
Earlier instructions to `docker start` the deleted database container are now
superseded: recreate it with the retained volume and original pinned image/local
credential record when a later database test needs it. For later prompts remove
only verified obsolete task containers, retain data/evidence and leave unrelated
containers alone.

## Roadmap Prompt 4 — quality bindings checkpoint (7 November 2026)

**Harness/offline checks passed; real G1, T-03/W-QUALITY and performance remain
NOT_RUN. Checkpoint INCOMPLETE, dependency exit 4.** Stopped before Prompt 5.

Stayed on `jaineel/j03-telemetry`, inspected status/diff first, and preserved all
pre-existing dirty work, the roadmap and both audit documents. No commit/push,
branch change, provider implementation, public contract, schema, dataset revision,
evaluation config, application lock or Docker configuration was changed here.

### Changed paths

- `benchmarks/quality_binding.py`: explicit owner callback slots; real lifecycle
  checks for verified Harsh manifests, frozen 10,000-SKU selection, exact source,
  complete scoped seed/projection, fresh empty quality namespace/topics, locked
  PostgreSQL/Kafka/registry and actual resources/parameters. Adopts Vichitr's
  `QualityMaterializer`, online-verified `SchemaCache` and actual B0 group/topic
  offsets. Observer reuses existing generator/lag/Gold collectors and requires
  declared owner SUT collectors. Registration composes Prompt 3 and W-QUALITY
  once. Missing callbacks have no fabricated implementations.
- `benchmarks/quality_publisher.py`: normal events retain SDK validation and
  `KafkaPublisher.publish_event`. Only independently identified invalid fixture
  ordinals/subcases with the expected SDK rejection may use the explicit raw
  publisher. Both retain frozen producer settings. Persisted bytes/headers/key,
  identity and actual broker coordinates are checked; same-ID concurrent sends
  cannot collapse through SDK pending-ID coalescing. Uncertain sends are not retried.
- `benchmarks/quality_sources.py`: bounded public owner receipt/quarantine/sink
  readers, `load_capture`/`read_bronze`, verified Parquet and pinned-generation
  membership. Requires a default-read-only analytics connection; no corrective
  write, reducer, cleaner, publication or offset commit. Re-reads post-drain
  evidence from zero; preserves missing timers and restart-capture consistency.
- `benchmarks/quality_audit.py`: independent fixture labels/counts, complete frozen
  plan, physical delivery/source accounting, persisted duplicates, original Bronze
  key/value/headers, dispositions/reasons/quarantine, logical content/Silver,
  pinned active Gold IDs/minute totals, offsets and sink membership/dispositions.
  Distinguishes SDK key/value/header fingerprints from body-only wire hashes.
  Arrow's unrelated payload fields must be null; expected stock fields must match.
- `benchmarks/quality_trial.py`: separately named three-delivery real G1 path with
  its own recipe hash, using the same setup/transport/audit controls. It cannot
  reduce or pass the separate 100,000-record T-03 assertions.
- `benchmarks/manual/verify_prompt4.py`: bounded readiness checkpoint with locked
  environment and read-only Docker probes; never starts a partial live fixture.
- `tests/benchmarks/test_quality_binding.py`,
  `tests/benchmarks/test_quality_sources.py`,
  `tests/benchmarks/test_quality_lifecycle.py`: **52 new offline checks**. Explicit
  transport/registry/SQL/setup doubles; every invalid subcase, scheduler duplicate
  reuse, deliberately wrong evidence, actual Arrow type conversion with synthetic
  values, read-only/paging bounds, setup/seed guards, drain and missing dependencies.
- `docs/jaineel/progress.md`: this evidence and handoff record.

### Exact commands and actual results

`PY` means `.venv/Scripts/python.exe`. Evidence root:
`artifacts/jaineel/prompt4-20261107/`. Each final command has exact argv/exit-code
JSON plus raw stdout/stderr. Results and generated evidence remain ignored by Git.

| Command | Actual result / evidence |
|---|---|
| `PY artifacts/jaineel/prompt4-20261107/run_final_checks.py` | Exit 0; orchestrates final checks below, `final/checks.json` |
| `PY -m pytest tests/benchmarks/test_quality_binding.py tests/benchmarks/test_quality_sources.py tests/benchmarks/test_quality_lifecycle.py tests/pipelines/test_quality_materializer.py -q -ra --tb=short --junitxml artifacts/jaineel/prompt4-20261107/final/focused.xml` | Exit 0: **68 passed, no skips**, 9.98 s; `final/focused.*`; includes Vichitr's unchanged 16 offline wire checks |
| `PY -m pytest tests/benchmarks tests/projectctl tests/oracles tests/integration -q -ra --tb=short --junitxml artifacts/jaineel/prompt4-20261107/final/owned.xml` | Exit 0: **614 passed, no skips**, 146.96 s; `final/owned.*`; overlaps focused tests, counts must not be added |
| `PY -m ruff check benchmarks tests/benchmarks tests/projectctl tests/integration tests/oracles` | Exit 0; `final/lint.*` |
| `PY -m ruff format --check benchmarks tests/benchmarks tests/projectctl tests/integration tests/oracles` | Exit 0; 100 files formatted; `final/format.*` |
| `PY -m projectctl.schemas --check` | Exit 0; all five schemas current; `final/schemas.*` |
| `PY -m benchmarks.manual.verify_prompt4 --out artifacts/jaineel/prompt4-20261107/final/checkpoint` | Expected **4 / INCOMPLETE**; correctness null; G1/T-03/performance NOT_RUN; `final/checkpoint/{summary,readiness}.json`, `g1/summary.json` |
| Checkpoint `uv sync --locked --check` | Exit 0; 38 resolved /37 audited, would make no changes; `final/checkpoint/lock.*` |
| Checkpoint `docker ps -a --format "{{.Names}} {{.Status}}"` | Exit 0, empty inventory; `final/checkpoint/docker.*`; no container created or cleanup needed |
| `PY artifacts/jaineel/prompt4-20261107/probe_eval.py` | Wrapper exit 0 verifies the next command's expected child exit 4; `eval-t03.command.json`, `eval-t03.stdout.log`, `eval-t03.stderr.log` |
| With `PROJECTCTL_ADAPTER_MODULE=benchmarks.quality_binding`: `PY -m projectctl eval run --suite T-03 --config configs/evaluation.yaml` | **4 / NOT_RUN**; draft prerequisites and no selected reviewed evaluation case binding; `benchmarks/results/7cd1280b-0bfb-4baa-bc30-4a51627b4179/`. Earlier equivalent direct-shell evidence retained at `benchmarks/results/a774bfce-0a30-403e-a1d9-4e8dba4fea0d/` |
| `git diff --check` | Exit 0; `final/diff.*`; repeated after this entry |

The earlier owned run (611 passed) and focused logs are retained at the evidence
root. Review tightened source fingerprints, the actual conversation topic, Arrow
nullable payload projection and batch/receipt agreement before the final runs.
Initial lint/format findings were fixed. No required assertion/test/provider
marker was weakened. None of these offline checks proves real broker/SQL G1.

### Blockers, conflict and owner handoffs

1. Config remains `draft`, with planned resources. Infrastructure/event-schema
   lock path/hash, dictionary path/hash, canonical/SKU manifests and generator/
   W-QUALITY recipe pins are missing. Prompt 3's exact-byte versus LF dictionary
   hash-policy review remains open; no pin or revision was invented.
2. This harness has no configured schema-cache path, registry URL or Kafka
   bootstrap; Docker has no containers. Online registry, PostgreSQL/Kafka trial,
   import/seed/projection and performance checks are NOT_RUN. The application
   lock check alone does not establish a ready locked environment.
3. **All affected owners/Jaineel:** supply reviewed fresh namespace/resource
   setup, complete independent seed/projection audit, read-only `QualitySources`
   factory and declared SUT collectors. `QualityOwners` are harness slots, not
   claimed teammate exports. The mapping/API/code-byte review requires Jaineel,
   Harsh, Aditya and Vichitr; no approval file was fabricated. Existing generic
   `T-03/quality` and `smoke/G1` evaluation case bindings remain unregistered until
   their independent fixture/export mapping is reviewed. Separate adversarial
   conflict/null/version/UTC cases remain unexecuted; their facts must not be set
   true merely because the finite recipe passed offline checks.
4. **Seed/quality collision — Aditya/Vichitr/Harsh/Jaineel review required.**
   File03 §5.3 requires "all 98,500 unique valid events accepted" and "all 1,000
   duplicate deliveries suppressed"; file09 §2 requires import, seed and complete
   initial projection before fixture evaluation. The materializer uses
   `version = ordinal // 10000 + 1`, starting at 1 per SKU.
   `services/inventory/seed.py` emits a distinct `STOCK_UPDATED` event with stock/
   aggregate version 1; `pipelines/curation/__init__.py` rejects a new event ID at
   an existing aggregate version with `AGGREGATE_VERSION_CONFLICT`. Processing
   both in one analytics namespace can violate the frozen counts. These exact
   producer/consumer paths and values are a code-level handoff, not a claimed
   live failure. Review namespace/cohort setup before providing callbacks. The
   harness requires empty quality topics/analytics and retains seed proof scope;
   it does not choose a new namespace policy, skip seed events, renumber facts,
   change counts or patch an owner's producer/consumer to hide the conflict.

Manual continuation: rerun the verifier into a **new** output directory. After
reviewed manifests, locks, seed namespace policy and callbacks exist, supply
`QualityOwners` explicitly to `build_quality_bindings(config, owners=...)` or
`run_g1(config, new_directory, owners=...)`. A reviewed deployment adapter can
register that factory. The default `benchmarks.quality_binding` registration
currently exposes dependency evidence, not callback discovery. Retain G1's three
physical deliveries/one logical effect separately; then run all 100,000 W-QUALITY
records with unchanged 98,500/1,000/500 assertions. Missing source, archive,
offset, disposition, active membership or audit evidence must block a real pass.
Keep NULL timers and unexecuted stages visible. Stop here before Prompt 5.

## Roadmap Prompt 5 — G3 transaction binding and recovery checkpoint (7 November 2026)

**Status:** G3 consumer binding and offline regression checkpoint implemented.
Real `smoke/G3-success`, `smoke/G3-decline`, quote-expiry regression and recovery
trials remain **NOT_RUN**. There is no owner-reviewed real composition/fixture,
and no live transaction or fault was attempted. No performance claim. Stop at
Prompt 5; Prompt 6 was not started.

Stayed on `jaineel/j03-telemetry`. Preserved all pre-existing dirty work, both
audit documents and the roadmap. No branch switch, commit, push, service patch,
contract change, dataset change or implicit reset. Initial status/diff and
preservation evidence are under `artifacts/jaineel/prompt5-20261107/`.

### Changed paths and implementation

- `benchmarks/g3.py`: `G3Binding` implements the existing `CaseBinding` interface
  for the existing success/decline cases. `register_g3(registry, bindings)` is
  called explicitly by a reviewed deployment composition. No real bindings are
  registered by default. `G3Owners` contains named, currently unavailable
  fresh-namespace/simulator, drain, producer-receipt and analytics-audit callback
  slots; these are harness requirements, not claimed exports from owner modules.
- The flow uses public M1 session/fixed turn/cart/quote/explicit checkout APIs,
  followed by public Orders status. It freezes request/user/session/cart/version,
  quote and confirmation identity. A lost checkout response retries exactly the
  same body/key; after two lost responses, read-only Orders audit may establish
  admission. An absent/ambiguous backend match remains UNKNOWN. Pending and
  MANUAL_REVIEW cannot become cancellation or success because a deadline elapsed.
  Unresolved finality timing stays null. Every state transition, request, response
  and observed order snapshot is retained before later validation.
- `benchmarks/g3_http.py`: bounded HTTP, canonical owner DTO response validation,
  no automatic mutation retry, explicit real/test transports, safe identity
  headers and exact base64 response bytes with SHA-256. Tokens remain outside
  journals. There are no imports of service implementations or cross-database
  writes in these new modules.
- `benchmarks/g3_audit.py`: consumes documented read-only Orders, Inventory,
  Payments and Catalogue HTTP snapshots. Namespace lists catch extra transaction
  effects; capped/truncated lists cannot pass. Reads immutable order lines and
  totals, reservation state, payment attempts/guard, individual ledger entries,
  authoritative stock and catalogue projection. The current ledger export uses
  positive magnitudes for DEBIT and REVERSAL: this reviewed mapping candidate
  converts reversals to negative exactly once and ignores the clamped aggregate
  `net_debit_minor`. The existing independent oracle checks totals, signed ledger,
  inventory conservation, source dispositions, exact Silver/active-Gold membership,
  manifest generation, monetary totals and frozen Gold business rows. Projection
  counts, version and change time must match Inventory. A decline needs an actual
  FAILED/DECLINED payment, not just any cancelled order.
- Producer expectations are bound before the separate sink audit. Raw outbox
  envelopes and broker coordinates establish immutable event IDs/hashes;
  independently frozen logical counts and order/quote identities constrain the
  cohort. Physical duplicates retain the identical envelope and separate source
  coordinates. Replenishment must have explicit independent evidence. The sink
  callback never receives the expected fixture and cannot overwrite transaction
  snapshots or business expectations. Missing ledger, receipts or active Gold
  blocks a pass.
- `benchmarks/g3_recovery.py`: HTTP consumer regression for original-key and
  new-key retries of an already accepted quote after expiry, new/unconsumed
  expired quote rejection, and changed-input conflict on the original key. It
  requires backend expired quotes; it does not rewrite service clocks or fix Orders.
- `benchmarks/manual/verify_prompt5.py`: read-only dependency checkpoint, raw
  Docker/lock probe logs, separate NOT_RUN status for both G3 cases and the two
  recovery handoffs. It returns exit 4 and attempts no transaction writes.
- `tests/integration/g3_double.py`, `tests/integration/test_g3.py`: explicitly
  scripted HTTP/producer/analytics doubles. Cover success and decline; one/two
  lost checkout responses; unchanged identities/keys; saved-evidence recheck;
  corrupt totals, duplicate debits, stock/projection mismatch; missing evidence;
  unresolved finality; frozen quote safety; producer count/hash/scope conflicts;
  signed reversal mapping; exact invalid response byte retention; and the expiry
  regression. These fixtures are **not** real catalogue or transaction fixtures.

Imported canonical contracts: `shared.contracts.common.RequestContext/ErrorResponse`,
M1 `SessionCreated/TurnResponse/CartSnapshot`, catalogue `Quote/ProductResponse`,
transaction `CreateOrderRequest/OrderAccepted/OrderSnapshot/PaymentOrderSnapshot/
StockSnapshot`, and `events.EventEnvelope`. Runtime mapping review must pin the
four HTTP contracts, these DTOs, the harness/oracle files and the concrete owner
callback implementations, plus the exact independent fixture bytes. Existing
`validate_review` requires actual Jaineel/Harsh/Aditya/Vichitr review; no approval
record was generated here.

### Exact commands and actual outcomes

`PY` below is `.venv/Scripts/python.exe`; `OUT` is
`artifacts/jaineel/prompt5-20261107`. `checks.json` records the exact executable,
argument arrays, exit codes and elapsed times. Named stdout/stderr logs and JUnit
are retained next to it.

| Command | Actual result / evidence |
|---|---|
| `uv sync --locked --check` | Exit 0; 38 resolved, 37 audited, would make no changes; `lock.*.log` |
| `PY -m pytest tests/integration tests/oracles tests/benchmarks tests/projectctl -q -ra --tb=short --junitxml=OUT/regression.xml --basetemp=OUT/test-tmp -o cache_dir=OUT/pytest-cache` | Exit 0; **644 passed, 0 skips**, 142.07 s; `regression.xml`, `regression.*.log`. Explicit offline/double coverage, not live G3 |
| `PY -m pytest tests/integration/test_g3.py -q -ra --tb=short --junitxml=OUT/focused-final.xml --basetemp=OUT/focused-tmp -o cache_dir=OUT/focused-cache` | Exit 0; **33 passed, 0 skips**, 14.85 s. Includes the last three invalid-byte cases and the less timing-sensitive test deadline; overlaps the broader run, do not add counts |
| `PY -m ruff check benchmarks/g3.py benchmarks/g3_http.py benchmarks/g3_audit.py benchmarks/g3_recovery.py benchmarks/manual/verify_prompt5.py tests/integration/g3_double.py tests/integration/test_g3.py` | Exit 0; `lint-final.*.log` |
| `PY -m ruff format --check benchmarks/g3.py benchmarks/g3_http.py benchmarks/g3_audit.py benchmarks/g3_recovery.py benchmarks/manual/verify_prompt5.py tests/integration/g3_double.py tests/integration/test_g3.py` | Exit 0; seven files formatted; `format-final.*.log` |
| `PY -m benchmarks.manual.verify_prompt5 --out OUT/readiness-final` | Actual subprocess exit **4**; both G3 cases NOT_RUN, correctness null; `readiness-final/readiness.json`, `readiness.*.log` |
| Verifier's `docker ps -a --format "{{.Names}} {{.Status}}"` | Exit 0, empty output: Docker reachable, no containers reported. No PostgreSQL/Kafka/registry trial |
| SHA-256 preservation check | All five unchanged: both audits, roadmap, `benchmarks/integration_cases.py`, `uv.lock`; `preservation.json` |

Initial focused development execution recorded 11 failures/16 passes in
`focused-initial.xml`: the new binding reused the exclusive-create artifact writer
for changing state views. Fixed that by retaining append-only state/order journals
and updating only the latest convenience views. The second and third focused runs
each passed 27 tests (`focused-second.xml`, `focused-third.xml`). Final results
above supersede those runs without deleting their evidence. No assertions were
weakened. Extra final checks independently cover raw signed reversals, source/order
binding, genuine decline evidence and invalid JSON/UTF-8 bytes.

### Remaining owner review and manual continuation

1. **Real G3 setup and exports — all owners.** Current preflight records draft
   config, unenforced resource profile, missing infrastructure/event-schema locks,
   unpinned dictionary, absent canonical/SKU manifests and absent logical fixture
   hash. All six `G3Owners` fields are unavailable. Harsh supplies the verified
   catalogue/quote/seed-projection binding; Aditya supplies deterministic SUCCESS
   and DECLINED simulator controls, namespace workers and reviewed transaction/
   response-loss/fault evidence; Vichitr supplies broker/outbox delivery, complete
   source/active Silver/Gold exports and publication/replay/fault bindings. Existing
   `services/payments/authorize.py` uses `random.random()`; no deterministic real
   outcome control is inferred from unit-test monkeypatches. Normal domain facts
   must be emitted by actual transactions, never fabricated by this binding.
   Audit row shapes/sign conventions and complete producer cohort (including seed
   facts) need explicit review. In particular, source `run_id` must be preserved:
   the Orders background worker currently constructs `run_id="saga-worker"` in
   `services/orders/app.py`; do not relabel its envelopes in the harness to pass.

2. **Compaction — Harsh/Vichitr/Jaineel.** Read
   `analytics/compaction/faults.py`: boundary
   `after_candidate_files_before_publish`, target `compaction`; its child creates
   candidate files, acknowledges, then waits to be killed before publication.
   `T-12/stale-compaction` instead uses `before_manifest_swap` /
   `compaction-publisher` while ingestion advances. Common §13 requires
   STALE_MANIFEST for an advanced base; these are different trials. The proposed
   crash-recovery case must prove candidate absence from active membership,
   unchanged active generation after the killed attempt, retained volume/files,
   equal logical digest/row count/currency totals for a replacement, and exactly
   one successor generation from the unchanged pinned base. Those proposed facts
   are captured in readiness evidence. Affected owner review is unavailable, so
   **no case was added and no existing case was remapped**. Candidate recovery,
   stale-generation rejection and any real retained-volume fault remain NOT_RUN.

3. **Quote-expiry/idempotency handoff — Aditya, Harsh and Jaineel.** Exact existing
   requirements: common §5 says Orders checks quote "binding and validity";
   common §8 says "Check prior idempotency/quote consumption before rejecting a
   retry because the original quote has since expired." Common Appendix A says
   repeated accepted quotes resolve to the existing order and bind a new transport
   key; a new expired quote is rejected. Common §3 requires same key/different
   input to return 409. `services/orders/commands.py:create_order` currently calls
   `_fetch_quote` before consulting existing quote consumption, checks no expiry/
   user binding after that fetch, and resolves conflict only on
   `(namespace,user_id,quote_id)`. The Orders HTTP route does not consume the
   Idempotency-Key. These are **code-level findings**, not a real regression trial.
   Merely adding an expiry check before replay lookup would break the accepted
   retry rule. Consumer scripts detect expired retry rejection, fresh expired
   acceptance and changed-input key reuse independently. Aditya must review/fix
   Orders and its canonical behavior; Harsh reviews real internal quote lookup.
   No owner service or contract was edited here.

After those handoffs, author an independent one-SKU fixture for each G3 outcome
with frozen prices, quantity, opening stock, full logical event counts and Gold
aggregates; use runtime `@id:order`, `@id:quote`, `@id:session` tokens only for
generated identities. Supply real reviewed `G3Owners` and a real `G3HTTP` factory
to `G3Binding`, register with `register_g3` in the approved composition, and run
the existing `projectctl eval run --suite smoke --config REVIEWED_CONFIG` in fresh
namespaces after the canonical setup sequence. Preserve G1 separately. Inspect
`http.jsonl`, `state.jsonl`, `order_snapshots.jsonl`, `producer_receipts.json`,
`drain.json`, `analytics_raw.json`, `observed.json`, `bound_fixture.json` and
`correctness.json`; then use `projectctl benchmark reconcile --run-dir RUN_DIR`.
Run the expiry probe only with actual previously accepted and fresh-unconsumed
expired quotes and the original request/key evidence. Run recovery trials only
after exact hooks, recovery invariants and owner acknowledgements are reviewed.
No missing provider, ledger, Gold membership, timer, hook or review may become a
real pass. **Prompt 5 checkpoint reached with the external real gate still open.**

## Roadmap Prompt 6 — truthful repository CI (7 November 2026)

Stayed on `jaineel/j03-telemetry`; no commit, push, branch change, provider-code
edit, contract change or benchmark measurement. Initial status and tracked diff
are retained in `artifacts/jaineel/prompt6-20261107/{initial-status.txt,initial.diff}`.
All prior work, both audits and the roadmap are preserved. This checkpoint is
repository coverage, **not** a G0/G1/G3 or performance certification.

### Changes and job dependencies

- `.github/workflows/offline.yml`: Ubuntu/Windows offline jobs now collect all
  eleven suites: conversation, catalogue, analytics, pipelines, transactions,
  contracts, projectctl, benchmarks, oracles, telemetry and integration. Owned
  lint/format and schema checks run too. Service opt-ins/URLs are removed for
  offline execution; missing real dependencies remain JUnit skips with reasons.
- The separate PostgreSQL job provisions the exact pgvector/PostgreSQL 18 image
  from `infra/images.lock.json`, initializes vector in its disposable database,
  and runs M1/catalogue/transaction suites. Each owner fixture retains its isolated
  schemas and declared HTTP/model/registry-ID/event doubles. These tests do not
  establish six-service database-role isolation or broker delivery.
- The Kafka job provisions and verifies the owner's `streaming-local` profile
  through `infra.streaming`: digest-pinned PostgreSQL, Kafka and registry, real
  roles/topics/schema cache. Native PostgreSQL/Kafka recreation, registry, SDK and
  catalogue projection tests run serially. After re-verification, the owner's
  pinned storage worker runs all pipeline and analytics suites with real SQL,
  Kafka and a Linux named volume. Independent job failures are never suppressed.
  The two external broker-pause controller cases remain explicitly unavailable;
  CI supplies no fabricated outage controller. Raw dataset/model-dependent tests
  skip when their actual inputs are absent; CI does not download substitute data
  or install a second embedding dependency lock.
- `benchmarks/manual/verify_prompt6.py`: exact command/exit/time logs, JUnit counts
  (pass/fail/error/skip/xfail), complete skip reasons, dependency probes and a
  separate NOT_RUN status for DE gates. PostgreSQL probes require major 18,
  durability on, and installed pgvector 0.8.1 for catalogue. Exit 4 from contract
  inventory is accepted only with matching NOT_RUN/MISSING/UNREVIEWED evidence and
  no FAIL; it never becomes a provider pass. Malformed evidence, correctness
  failures, strict XPASS, absent XML and timeouts fail the checker.
- `benchmarks/manual/prompt6_services.py`: bind the actual owner-generated CI
  catalogue URL and extend the existing storage-check Compose configuration with
  read-only benchmark/analytics sources and writable evidence. Build context holds
  only the existing Dockerfile, pyproject and uv.lock. Worker failures propagate.
  Credentials/overlays stay ignored and are excluded from artifact uploads.
- `benchmarks/manual/verifier_state.py` and `verify_p5.py`, `verify_p6.py`,
  `verify_p7.py`: replace the obsolete clean-HEAD protected-path expectation with
  an invocation-time tracked-diff snapshot. Pre-existing edits are preserved;
  changes during verification fail. Tests still require their original exit codes.
  `verify_p6` now labels its added real local shared-codec/outbox coverage correctly
  while keeping Kafka NOT_RUN. Reviewed `verify_p11.py`: exit 0/4 for optional real
  bindings and rejection of executed correctness exit 3 remain appropriate; no
  change needed. The fixed-only P7 extraction already handles combined fixed/assist
  traces; its failure-verdict tests are retained.
- `tests/benchmarks/test_prompt6_ci.py`: explicit subprocess/database/Compose/XML
  doubles test dependency rejection, skip/xfail/strict-XPASS counting, malformed
  contract evidence, timeout logs, URL redaction, dirty-work preservation, real
  volume bindings and worker failure propagation. Workflow checks verify pinned
  provisioning and always-uploaded logs/JUnit. These are labelled offline tests.
- Every CI job uploads logs/JUnit/summary even on failure, including nested server
  logs. Generated credentials, `.env` and private Compose overlays are excluded.
  No `continue-on-error`, removed strict marker or weakened assertion was added.

### Executed checks and retained evidence

Below, `OUT=artifacts/jaineel/prompt6-20261107`, `PY=.venv/Scripts/python.exe`.
The new verifiers retain argument arrays, exit codes and elapsed durations in
`checks.json`; stdout/stderr and JUnit are adjacent. Counts overlap across runs.

| Command | Actual result / evidence |
|---|---|
| `uv sync --locked --check` | Exit 0; 38 resolved / 37 audited, no changes |
| `PY -m pytest tests -q -ra --tb=short --junitxml=OUT/baseline.xml --basetemp=OUT/baseline-tmp -o cache_dir=OUT/baseline-cache` | Exit 1; **1,454 passed, 1 failed, 515 skipped**; `baseline.log`, `baseline.xml`. Failure is Vichitr's stale M1 codec fixture below |
| `uv run --locked python -m benchmarks.manual.verify_prompt6 --job offline --out OUT/offline` | Exit 1; **1,422 passed, 32 failed, 12 errors, 515 skipped**; `offline/{checks.json,pytest.xml,pytest.stdout.log,summary.json}`. Besides the same transport failure, writes encountered ENOSPC; this run is not relabelled as pass |
| `uv run --locked python -m pytest tests/conversation tests/catalog tests/analytics tests/pipelines tests/transactions tests/contracts tests/projectctl tests/benchmarks tests/oracles tests/telemetry tests/integration --lf --last-failed-no-failures=none -q -ra --tb=short --junitxml=OUT/offline-recheck.xml --basetemp=artifacts/p6-recheck-tmp -o cache_dir=OUT/offline/cache` | Exit 1; **43 passed, 1 failed** in 9.23 s. All ENOSPC-affected cases passed using shorter scratch; transport failure reproduces. Original failures remain in XML/logs. No confirmed storage root cause is claimed; drive snapshot reported about 1.67 GB free after the run |
| `PY -m pytest tests/benchmarks/test_prompt6_ci.py tests/benchmarks/test_verifier_evidence.py -q --tb=short --junitxml=OUT/verifier-final.xml` | Exit 0; **28 passed**, zero skips; `verifier-final.log`, `verifier-final.xml` |
| `PY -m ruff check benchmarks projectctl services/conversation shared/telemetry dashboards tests/conversation tests/contracts tests/projectctl tests/benchmarks tests/oracles tests/telemetry tests/integration` | Exit 0; `owned-lint-final.log` |
| Same owned paths with `PY -m ruff format --check` | Exit 0; `owned-format-final.log` |
| Schema and conversation contract checks from offline verifier | Both exit 0; `offline/{schemas,conversation-contract}.{stdout,stderr}.log` |
| `PY -m projectctl contracts check --all` | Exit **4**, NOT_RUN; actual inventory reports six unreviewed shared/schema bindings, not an executed correctness failure. Raw JSON in `offline/contracts.stdout.log`; the old verifiers' expected 4 is still current |
| `PY -m benchmarks.manual.p6_smoke --out OUT/legacy-p6-smoke` with explicit Docker test URL | Exit 0; `legacy-p6-smoke/{smoke.json,server.log}`, `legacy-p6-smoke.log`; real PostgreSQL, event capture double |
| `PY -m benchmarks.manual.p7_smoke --test-double-providers --confirm-checkout --out OUT/legacy-p7-smoke` | Exit 0; **16/16 assertions**, real PostgreSQL and explicit providers/events doubles; `legacy-p7-smoke/smoke.json`, `legacy-p7-smoke.log` |
| Local Kafka and volume readiness invocations (`--job kafka`, `--job volume`) | Each exit **4**, NOT_RUN: respective catalogue/analytics test URL is absent; `kafka-readiness/summary.json`, `volume-readiness/summary.json`. No Kafka, registry or volume execution is claimed |

Local PostgreSQL uses the workflow's exact digest-pinned image in a newly created
container `jaineel-prompt6-pg-20261107`, loopback ephemeral port and disposable test
credentials; `postgres-container.json` stores selected non-secret provenance.
The first port-discovery template failed; `postgres/summary.json` correctly records
ConnectionTimeout/NOT_RUN and no tests. Corrected discovery used `docker port`.
The first real PostgreSQL job produced **628 passed, 113 errors, 13 skipped**
(`postgres-real/pytest.xml`): the image had vector installed but the new database
lacked `CREATE EXTENSION`. Fixed CI provisioning with
`CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public`; local exact command
was `docker exec jaineel-prompt6-pg-20261107 psql -U ci_test -d ci_test -c 'CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public'`
(`pgvector-setup.log`, exit 0). Added fail-closed extension readiness coverage.
The corrected-extension rerun, exact command
`uv run --locked python -m benchmarks.manual.verify_prompt6 --job postgres --out OUT/postgres-final`,
returned exit **1**: **630 passed, 25 failed, 86 errors, 13 skipped** in 266.81 s.
Per-suite JUnit counts: M1 **387 passed / 1 failed**, transactions **127 passed**,
catalogue **116 passed / 24 failed / 86 errors / 13 skipped**. Raw evidence:
`postgres-final/{checks.json,summary.json,pytest.xml,pytest.stdout.log}`.
Catalogue ingestion uses the real FileStore and requires Linux directory fsync;
Windows correctly raises `pipelines.storage.DurabilityUnavailable`. Import fault
children also exit before the barrier for that reason. No fake Windows durability
or skipped provider assertion was added. The Linux-only workflow is configured
correctly; this host cannot certify its catalogue/volume job. Added an explicit
Linux precondition to all service-job selections and a regression test: the final
local `--job postgres --out OUT/platform-readiness` returns **4 / NOT_RUN**, with
the platform dependency recorded instead of starting unsupported fixtures.
Earlier failed attempts remain evidence, not passes.

M1's single later failure was
`test_search_receives_remaining_total_deadline_and_never_retries`: elapsed 3.797 s
exceeded its unchanged 3.5-s ceiling while the broad checks ran. Its isolated exact
rerun, `uv run --locked python -m pytest tests/conversation/test_assist.py::test_search_receives_remaining_total_deadline_and_never_retries -q --tb=short --junitxml=OUT/m1-timing-recheck.xml --basetemp=artifacts/p6-timing-tmp -o cache_dir=OUT/timing-cache`,
passed (**1 passed**, 9.95 s including fixture/setup). Original failure and warning
remain in `postgres-final/pytest.xml`; rerun evidence is `m1-timing-recheck.{xml,log}`.
No deadline, assertion or implementation was changed. The first real PostgreSQL
run already executed all **388 M1 tests** and **127 transaction tests** successfully;
only catalogue setup errored in that earlier run. These runs overlap; do not sum
them into a new full-suite pass.

### Owner handoffs and manual continuation

1. **Vichitr / M1 test consumer:**
   `tests/pipelines/test_transport.py::test_m1_keyword_builder_and_existing_transaction_binding`
   line 95 injects `sdk._codec` and an outbox double, then calls `SharedEvents()`.
   Prompt 2's M1 adapter deliberately owns a pinned `SchemaCache`/`EventCodec` and
   requires catalogue provenance; the global codec injection no longer configures
   it. Observed `services/conversation/events.py:44` validates null
   `CATALOG_DATASET_REVISION`, then returns DEPENDENCY_UNAVAILABLE. Common spec
   event provenance/readiness and Prompt 2 require fail-closed behavior. Update
   the owned fixture to supply an explicit synthetic revision and real schema
   cache fixture (registry IDs may remain labelled doubles), retaining the same
   transaction identity and schema/encode assertions. Do not loosen production
   M1 readiness to satisfy this obsolete fixture. Its smallest exact reproducer
   is `uv run --locked python -m pytest tests/pipelines/test_transport.py::test_m1_keyword_builder_and_existing_transaction_binding -q --tb=short`.
2. **Harsh / Jaineel:** strict brand xfail remains untouched in
   `tests/catalog/test_conversation_consumer_live.py`. PostgreSQL rerun determines
   whether its current assertion XPASSes; only Harsh may review/remove that marker.
   On this host the live fixture errors on Linux durability before reaching the
   assertion, so its actual post-fix verdict remains **NOT_RUN**, not XPASS or pass.
   Run it in the workflow's Linux PostgreSQL job and preserve strict XPASS evidence
   for Harsh if the marker is stale. No consumer contract was changed here.
3. **Infrastructure/runtime:** GitHub-hosted workflow and local Linux-volume/
   Kafka jobs have not executed in this session. Review uploaded per-job skips,
   particularly optional ONNX/model/raw CSV and externally controlled broker
   outages. Those skips and the whole-business gates remain open. No historical
   `docs/vichitr/test_skips.md` pass was imported as current evidence.

After owner changes, run the same offline command with a fresh `--out`, then the
PostgreSQL workflow on its pinned disposable database. Native Kafka recreation
tests require the dedicated CI stack; do not point them at ongoing application
work. The workflow provisions/validates the reviewed owner stack before selecting
live flags and revalidates after recreation before running the volume worker.
Inspect all JUnit failures/skips and `summary.json`, not only the workflow badge.

## Roadmap Prompt 7 — baseline prerequisite checkpoint (7 November 2026)

**Checkpoint: blocked before setup/measurement; B0 and comparisons NOT_RUN.**
Stayed on `jaineel/j03-telemetry`, preserving the dirty working tree, roadmap,
both audits and other owners' implementations. No commit, push, branch change,
service startup, reset, import, seed, smoke, live correctness trial or performance
run was attempted. Initial tracked changes and status are retained in
`artifacts/jaineel/prompt7-20261107/{initial.diff,initial-status.txt}`.
This follows Prompt 7's explicit alternative checkpoint: report the specific
unmet gate and stop before expensive measurements. It is not a completed G4/G5.

### Changed paths

- `benchmarks/manual/verify_prompt7.py`: repeatable read-only prerequisite
  inventory. Reuses `projectctl.cli.preflight`, `review_input_pins` and the
  existing performance receipt validators, including real correctness/resources,
  B0 smoke and baseline/diagnosis requirements. Records all required workload
  preflights, Git state, actual local file hashes, provider registration gaps,
  session-reuse exclusion and three repetitions. It never invokes registered
  providers or workload factories, generates approvals, changes pins or selects
  C-BEST. Stores resolved config, JSON/Markdown checkpoint and the actual
  read-only application-environment probe/logs. Failure output remains immutable;
  each rerun requires a new directory. Metrics and correctness remain null.
- `benchmarks/manual/test_prompt7.py`: offline regression tests with explicit
  Git/process/receipt fixtures. Test missing dependencies, zero provider/factory
  invocation, null results, unchanged config, session-reuse/repetition exclusion,
  rejection of a changed application lock, observed-versus-pinned owner locks,
  diagnostic-only rule labels, subprocess failures/timeouts and evidence retention.
  Tests live within the prompt's allowed `benchmarks/` scope; the exact manual
  pytest command is documented rather than expanding the prior CI milestone.
- `projectctl/README.md`: commands, evidence scope, exit semantics and ordered
  continuation through the canonical runbook. Prior composition documentation is
  preserved.
- `docs/jaineel/progress.md`: this record. Evaluation config, core matrix,
  canonical contracts, application lock and provider code were not changed.

### Actual prerequisite evidence

`OUT=artifacts/jaineel/prompt7-20261107`; `PY=.venv/Scripts/python.exe` below.
Authoritative current inventory: `OUT/readiness-final/readiness.json` and
`checkpoint.md`; local files are observations, not approval receipts.

- The code revision is dirty. No authorization to commit was given; existing
  work was not committed or discarded to satisfy the gate.
- Actual source CSV raw SHA-256 matches spec 08:
  `56f8f699c9e847356666c2eab3c3ab1244340f6a98ad08e39ea2199ebe993ad1`.
  Actual `uv.lock` bytes match the configured
  `05d066056e90caf4733415f7cbfb80cba30f99b211a27eaaf665544e3150b2dd`.
  `uv sync --locked --check` exits 0, resolves 38/audits 37 packages and reports
  no changes. These checks establish local input identity, not service readiness.
- `infra/images.lock.json` and `contracts/events/manifest.json` exist, with
  observed raw hashes in the inventory. Evaluation infrastructure/event-schema
  lock references remain null; neither discovery nor historical SMOKE_TESTED
  strings certify current runtime or affected-owner approval.
- Evaluation config remains draft; resources are planned, not verified/enforced.
  Configured normalized/SKU manifests, dictionary pins, generator/workload hashes,
  query hash and human relevance-label hash are absent. Complete current
  seed/outbox/projection proof and owner-reviewed correctness/resource receipt
  are unavailable. No missing quantity is represented as zero.
- Explicit Jaineel composition registers import/search/analytics factories but
  has no global reset, W-PIPE/W-QUALITY/W-CHECKOUT/W-INTEGRATED binding or real
  registered mandatory correctness cases. Registration alone proves no runtime
  readiness; factories are not called by this checker. Prior lifecycle/audit,
  deterministic payment, active Gold and recovery handoffs remain open.
- Frozen controls observed: three repetitions and session reuse disabled. No
  new variant or optional session reuse, live model or unreviewed relevance
  result entered the core matrix. Harsh's sample owner runs were not imported.

### Exact hash-policy conflict and required review

Runbook 09 §1: **“raw-file hashes always cover exact bytes.”** Existing catalogue
handoff/`projectctl.input_pins` identifies the provider dictionary using
universal-newline UTF-8 text. This checkout has CRLF. The actual dictionary raw
hash is `7de194b5f49538e84a43ce91e734acae2182a0c96e3b743d668695ad6c6c2a02`,
while its LF-text/published identity is
`a7d381e90986b23f801eca537a689f2d3e056fa0b58040ecb7c182e2be2f9943`.
Queries likewise have raw
`14733547c0ce5690a79e3ea633d2b5ecdb0b5a133fd30e3fffcc175cf0ffcd63`
versus published LF-text
`89d89ac030f10d23e85d6e5084caa125017b5f927a1ed94854aadc3be4762410`.
The checker preserves both meanings; it does not normalize files, replace raw
hash checks or recalculate the published dataset revision. **Harsh/Jaineel and
Aditya as SKU consumer must review** the exact-byte evaluation artifacts versus
dictionary identity and a cross-platform reproduction policy. A contract/matrix
change requires the canonical affected-owner process, not a local workaround.

Runbook 09 §6 requires **“Label relevance 0–3 manually”** and says unjudged
candidates are not automatically irrelevant. `docs/harsh/relevance_labels.md`
explicitly says its labels are rule-derived, changed after held-out inspection,
and ANN unjudged results count as zero. No reviewed human-labelled replacement
or row-level human review exists in this handoff. Human relevance certification
therefore stays NOT_RUN; the checker identifies the existing scores as diagnostic
and never copies their hash into evaluation config. Harsh/Jaineel must supply the
reviewed file/pool and agree unjudged handling before certified quality claims.

### Commands, outcomes and continuation

| Exact command (using PY/OUT above) | Actual outcome / evidence |
|---|---|
| `PY -m benchmarks.manual.verify_prompt7 --out OUT/readiness` | Exit 4, INCOMPLETE, performance NOT_RUN; initial checker evidence/log retained |
| `PY -m benchmarks.manual.verify_prompt7 --out OUT/readiness-final` | Exit 4, INCOMPLETE; final exact file observations, null B0/C-BEST, zero service writes; `readiness-final.log`, `readiness-final/{readiness.json,resolved_config.json,checkpoint.md,lock.stdout.log,lock.stderr.log}` |
| Internal `uv sync --locked --check` | Exit 0, no changes; command/exit in readiness JSON and raw lock logs |
| `PY -m pytest benchmarks/manual/test_prompt7.py tests/benchmarks/test_performance.py tests/benchmarks/test_experiment.py tests/benchmarks/test_comparison.py tests/benchmarks/test_selection.py -q -ra --tb=short --junitxml=OUT/focused-second.xml --basetemp=artifacts/p7-tmp2 -o cache_dir=OUT/cache` | Exit 0; **75 passed**, zero skips; `focused-second.{log,xml}`. Before final added local-file observation regression |
| `PY -m pytest benchmarks/manual/test_prompt7.py tests/benchmarks tests/projectctl tests/oracles tests/telemetry tests/integration -q -ra --tb=short --junitxml=OUT/regression.xml --basetemp=artifacts/p7-reg-tmp -o cache_dir=OUT/reg-cache` | Exit 0; **726 passed**, zero failures/errors/skips, 145.13 s; `regression.{log,xml}`. Includes final local-file regression; suites overlap the focused run, so do not sum counts. Offline evidence/doubles, not a live G1/G3 pass |
| `PY -m ruff check --no-cache benchmarks projectctl dashboards` | Exit 0; `lint-final.log`. Earlier cached pass logged a cache permission warning; no-code-change no-cache run is clean |
| `PY -m ruff format --check benchmarks projectctl dashboards` | Exit 0; 80 files formatted; `format.log` |
| `PY -m projectctl.schemas --check` | Exit 0; config/run/summary/fixture/report schemas match; `schemas.log` |
| `git diff --check` | Exit 0; existing CRLF conversion warnings only |

Initial focused invocation mistakenly named nonexistent
`tests/benchmarks/test_planning.py`: no tests ran (pytest input exit 4), retained
in `focused.log`/`focused.xml`. Corrected selection uses the existing experiment
suite; no assertion was weakened and no failed input invocation is called pass.

Continue only after the recorded prerequisites close: use runbook 09 §2 setup
on a fresh namespace, run real contracts/data/smoke and the full required
correctness suite (including T-10/D-05/T-11), obtain the reviewed resource/input
receipt, then commit/freeze the approved B0 revision through a separately
authorized Git action. Capture and reconcile real B0 after drain, diagnose its
stage/resource evidence, and run registered paired comparisons with three
repetitions and recorded random order. Preserve every offer/failure/timing and
collector gap. Use existing `benchmark reconcile`, `benchmark compare`, measured
selection/interaction checks and `report build` to generate results from artifacts.
Do not start the full matrix, stress escalation or optional trials from this
checkpoint. The specific unmet gates remain explicit and B0 is not frozen.

## Jaineel scope, bug and push audit — 8 November 2026

The user authorized an audit of Jaineel's complete contribution and repairs in
owned paths. This is one audit checkpoint, not authorization to commit/push or
change another owner's implementation/contracts. Stayed on
`jaineel/j03-telemetry`, preserved existing work and both old audits. The detailed
findings/completion assessment are in [AUDIT_2026_11_08.md](AUDIT_2026_11_08.md);
copyable paragraphs are in [TEAM_HANDOFF_2026_11_08.md](TEAM_HANDOFF_2026_11_08.md).

After a successful read-only `git fetch origin`, HEAD equals `origin/main`:
`git rev-list --left-right --count origin/main...HEAD` returns `0 0`. The old
feature upstream is 87 commits behind HEAD. New work remains modified/untracked;
it will not be included by `git push` until committed. Sharing reviewed code as a
draft feature branch is reasonable; two owner test corrections and real
integration/evaluation gates prevent a green merge/release/completion claim.
There was no commit, push, force operation, branch change, production namespace
reset or benchmark matrix execution.

### Repairs and changed paths in this audit

- `services/conversation/workflow.py`: durable accepted checkout aliases now
  replay locally without depending on Orders availability or its advanced status.
  Concurrent aliases retain the persisted acceptance for the same order; a
  different in-flight order ID fails closed. No second checkout event/purchase.
  `tests/conversation/test_workflow.py` adds outage/finality and controlled
  interleaving/identity regressions. Initial two-case red result is preserved.
- `services/conversation/database.py`: configurable integer API connection cap
  2–10 with one reserved audit connection *inside* that cap. Default operational
  cap remains ten. `tests/conversation/test_database_budget.py` checks invalid
  budgets and real PostgreSQL ordinary-slot saturation, audit availability and
  recovery. `.env.example` uses three API connections plus one separately
  composed relay to fit the frozen total of four, and corrects the invalid event
  namespace `local-dev` to `dev`. `services/conversation/README.md` documents the
  process/relay allocation and durable acceptance semantics.
- `benchmarks/selection.py` and `tests/benchmarks/test_selection.py`: selected
  C-BEST comparisons must match current Git and frozen study controls, including
  seed/resources. Three previously accepted foreign-study cases were reproduced
  before fixing them. Existing evidence recomputation and interaction/cost
  requirements remain in place.
- `benchmarks/integration_clients.py`, `benchmarks/g3_http.py`,
  `tests/integration/test_http.py`, `tests/integration/test_g3.py`: whole-response
  deadlines, bounded streamed M1 response bodies and JSON media validation;
  timeout remains unknown, finality null, stream closed, no implicit retry.
  Four red boundary cases were retained before the fix.
- Move `benchmarks/manual/test_prompt7.py` to
  `tests/benchmarks/test_prompt7.py`, so the normal CI benchmark suite collects
  these regressions. `projectctl/README.md` uses the new path.
  `tests/projectctl/test_composition.py` validates the example namespace against
  the canonical event type and verifies API plus relay connection allocation.
- This progress entry and the two new audit/handoff documents. No business
  provider, canonical DTO/event/data contract, dictionary/query/label, historical
  migration, application lock or evaluation/core matrix was changed.

### Commands, actual outcomes and evidence

`OUT=artifacts/jaineel/audit-20261108`, `PY=.venv/Scripts/python.exe`.
Counts overlap across checks; do not add them into a new combined pass.

| Exact command | Outcome / raw evidence |
|---|---|
| `uv run --locked python -m benchmarks.manual.verify_prompt6 --job offline --out OUT/offline-baseline` | Exit 1: 1,472 passed, 1 failed, 515 skipped; all eleven suites collected. Initial working-tree audit, not a frozen revision; edits continued during this run. `offline-baseline/{checks.json,summary.json,pytest.xml,pytest.stdout.log}` |
| `uv run --locked python -m benchmarks.manual.verify_prompt6 --job offline --out OUT/offline-final` | Exit 1: **1,503 passed, 1 failed, 520 skipped**, 258.48 s. All executed owned tests pass; the failure is Vichitr's stale M1 codec fixture. Complete skip reasons/logs/JUnit in `offline-final/`. The last standalone example-contract test was added after collection and passed below |
| `PY -m pytest tests/conversation tests/contracts -q -ra --tb=short --junitxml=OUT/m1-postgres.xml --basetemp=artifacts/a8-m1-tmp -o cache_dir=OUT/m1-cache` with explicit isolated test URL | Exit 0: **505 passed**, zero skips; real PostgreSQL with declared HTTP/model/registry-ID doubles. `m1-postgres.{log,xml}`. Before final two interleaving regressions |
| `PY -m pytest tests/conversation/test_workflow.py::test_new_checkout_key_replays_durable_acceptance_without_backend tests/conversation/test_workflow.py::test_inflight_checkout_alias_keeps_accepted_identity_and_allows_finality tests/conversation/test_database_budget.py -q --tb=short -o junit_family=xunit1 --junitxml=OUT/m1-regressions-final.xml --basetemp=artifacts/a8-m1-reg-tmp -o cache_dir=OUT/m1-cache` with explicit isolated test URL | Exit 0: **16 passed**; `m1-regressions-final.{log,xml}` |
| `PY -m pytest tests/benchmarks/test_selection.py tests/benchmarks/test_prompt7.py -q --tb=short --junitxml=OUT/selection-checkpoint.xml --basetemp=artifacts/a8-unit-tmp -o cache_dir=OUT/cache` | Exit 0: **23 passed**, no skips; `selection-checkpoint.{log,xml}` |
| `PY -m pytest tests/integration/test_http.py tests/integration/test_g3.py -q --tb=short --junitxml=OUT/http-final.xml --basetemp=artifacts/a8-http-tmp -o cache_dir=OUT/cache` | Exit 0: **41 passed**, no skips; `http-final.{log,xml}` |
| `PY -m pytest tests/projectctl/test_composition.py -q --tb=short --junitxml=OUT/composition-final.xml --basetemp=artifacts/a8-compose-tmp -o cache_dir=OUT/cache` | Exit 0: **7 passed**, no skips; `composition-final.{log,xml}` |
| `PY -m ruff check --no-cache benchmarks projectctl services/conversation shared/telemetry dashboards tests/conversation tests/contracts tests/projectctl tests/benchmarks tests/oracles tests/telemetry tests/integration` | Exit 0; `owned-lint-final.log` plus the offline verifier's lint log |
| Same owned paths with `PY -m ruff format --check` | Exit 0; **179 files** formatted; `owned-format-final.log` |
| `PY -m projectctl.schemas --check`, `PY -m projectctl.conversation_contract --check` | Both exit 0 in final verifier; raw logs under `offline-final/` |
| `PY -m benchmarks.manual.verify_prompt7 --out OUT/readiness-final` | Exit **4 / INCOMPLETE**; performance NOT_RUN, null B0/C-BEST, exact prerequisite reasons and actual application lock check. This does not freeze/approve any inputs |
| `inspect_source(Path('data/raw/flipkart_com-ecommerce_sample.csv'))` using `benchmarks.dataset_checks` and exclusive `write_json` | Actual independent source-profile **PASS**; `source-profile.json`. Original source bytes/rules retained; no performance or provider-normalization claim |
| `PY OUT/check_scope.py`, `git diff --check`, `git ls-files .env 'data/raw/*' 'data/catalog/*' 'benchmarks/results/*' '*.pem' '*.key'` | No unexpected tracked-path changes since audit start, no scanned credential-pattern matches, no whitespace errors; only raw `.gitkeep` tracked. `scope-and-secret-check.json`, `diff-check.log`. Pattern scan is narrow and not proof of secret absence |

The red commands use the same pytest/evidence options with the targeted new test
IDs: checkout replay **2 failures** (`checkout-red.{xml,log}`), foreign selection
**3 failures** (`selection-red.{xml,log}`), HTTP bounds **4 failures**
(`http-red.{xml,log}`). After the fixes, the unchanged assertions pass. All failed
evidence remains; no test was weakened or skipped to manufacture a green result.

### Real Linux and ownership evidence

Started only a new audit PostgreSQL container, loopback ephemeral port 59363,
using Vichitr's exact `pgvector/pgvector:0.8.1-pg18-trixie` digest from
`infra/images.lock.json`. The earlier `jaineel-prompt6-pg-20261107` container was
already stopped and was not reused. Test credentials are disposable and private
service credentials were not read/copied. The database extension command was
`docker exec jaineel-audit-pg-20261108 psql -U audit_test -d audit_test -c 'CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public'` (exit 0).

`PY OUT/run_linux.py` creates its own network/named data volume and uses the
already built, lock-matching owner storage-worker image
`sha256:285a497c4237cd65cbfc7c02bcb560d6df7c718e02be2e5461c21f5e97a67766`.
Source is mounted read-only; temporary data uses the Linux named volume, avoiding
fake Windows directory durability. Complete Docker argv and exit codes are in
`postgres-linux.command.json` and the helper script, stdout/stderr and XML.
Inner exact pytest command:

`python -m pytest tests/conversation tests/catalog tests/transactions tests/contracts -q -ra --tb=short -o junit_family=xunit1 --junitxml=/out/postgres-linux.xml --basetemp=/testdata/pytest -o cache_dir=/testdata/cache`

Actual result: exit 1, **851 passed / 2 failed / 20 skipped** in 223.01 s. Per-suite:
M1 **404 passed**, contracts **103 passed**, transactions **127 passed**, catalogue
217 passed/2 failed/20 skipped. One failure is the strict brand XPASS below; the
other is **my audit mount omission** (`/app/infra/compose.catalog.yaml` absent).
The worker omitted `infra/`; this is not a provider defect. Original logs remain.
`PY OUT/run_linux_catalog.py` repeats the catalogue suite with the missing mount
corrected and the unchanged actual source CSV explicitly mounted read-only.
The final catalogue command/skip/output evidence is stored separately, preserving
the original failed run. No optional embedding lock/model was installed to hide
the ONNX skips; no Kafka broker was substituted.

Corrected exact inner command:
`python -m pytest tests/catalog -q -ra --tb=short -o junit_family=xunit1 --junitxml=/out/catalogue-linux-final.xml --basetemp=/testdata/catalogue-final -o cache_dir=/testdata/catalogue-cache`.
Actual exit **1**, **225 passed / 1 failed / 13 skipped**, 339.64 s. The only
failure is the preserved strict brand XPASS. The missing-mount case and all
actual-source cases execute successfully; remaining skips are optional
ONNX/model dependencies and the unconfigured real broker. Evidence:
`catalogue-linux-final.{command.json,stdout.log,stderr.log,xml}`. Counts overlap
the original Linux job. `PY OUT/summarize.py` writes `junit-summary.json` from
all raw JUnit files with per-suite counts and failed IDs.

Current exact external failures/handoffs:

1. **Vichitr** owns
   `tests/pipelines/test_transport.py::test_m1_keyword_builder_and_existing_transaction_binding`.
   Global codec injection does not initialize M1's own cache/revision binding;
   missing revision fails at `services/conversation/events.py:_bindings` with
   DEPENDENCY_UNAVAILABLE. Update the owned fixture with pinned schema mapping
   and explicit synthetic revision, as in the shared-event M1 test fixture. Do
   not weaken readiness. Final offline CI remains failed for this exact case.
2. **Harsh** owns
   `tests/catalog/test_conversation_consumer_live.py::test_workflow_accepts_a_real_brand_filter`.
   Actual Linux HTTP catalogue execution yields **XPASS(strict)**, because M1's
   brand comparison is fixed. Only Harsh reviews/removes the stale marker; it was
   preserved and is not a passing job or an unresolved brand-search failure.
3. **Aditya** must close quote validity/user binding and transport idempotency,
   original saga run identity and controlled payment scenario behavior. These
   remain current code-inspection findings; transaction unit/live tests double
   quote/payment controls and cannot certify real G3. Exact files/contracts and
   executable owned consumer expiry probes are linked in the audit/handoff.
4. **All owners/Jaineel** must review the dictionary/raw-byte policy, manual
   labels, actual manifests, migrations/fresh-storage/audit/observation/fault
   lifecycle. The current B0-only ingestion runtime rejects O1. No new provider
   exports/approvals were invented, and catalogue outbox migration 005 is already
   present, superseding that older missing-table handoff.

The remaining Jaineel work is real composition/case registration and execution,
correctness, baseline, controlled comparisons and the artifact-built report.
Ownership of that glue has not been transferred to teammates. Human reproduction,
hosted CI, native Kafka/registry/recreation and whole-business Gold/recovery
evidence remain NOT_RUN. A plain code/test pass is not the final contribution.

After test completion, `docker stop jaineel-audit-pg-20261108` stops only this
audit's disposable database. Worker containers use `--rm` and have exited; retain
the audit's named Linux data volume/network and stopped database for inspection.
No previous container, development data or raw CSV was deleted. Final tracked
scope/whitespace inspection remains clean, and no source change followed the
final passing checks except documentation and the separately passed example test.

## Finish Jaineel's code-side handoff — 8 November 2026

The user clarified the scope: complete Jaineel's implementation/tests, then hand
it over so the other three owners can continue. This is separate from declaring
the later full-team evaluation finished. The current handoff is
[CODE_HANDOFF.md](CODE_HANDOFF.md). No new owner inputs were assumed, and no
commit/push was authorized or performed. Stayed on `jaineel/j03-telemetry` and
preserved prior working-tree changes, both audits, contracts and owner code.
Initial status/diff: `artifacts/jaineel/finish-20261108/{initial-status.txt,initial.diff}`.

### Implemented in owned paths

- `projectctl/jaineel.py`, new `projectctl/runtime.py`: one production composition
  now registers all seven required workload factories. Explicit `RuntimeBindings`
  supplies existing per-workload callbacks, `QualityOwners`, real G3/correctness
  adapters and reviewed migration/reset coordinators. A named optional runtime
  module is loaded only when configured; bad types, unknown cases/workloads,
  duplicate cases and stub results fail closed. Default missing owner operations
  remain dependencies; factories are not executed at registration. The old
  quality composition forwards to this one and cannot double-register.
- New `projectctl/setup.py`: a concrete M1 migration participant and an ordered
  six-database coordinator. Missing participants cause no partial writes. Each
  actual migration delegates to its owning participant, preserves failures and
  requires real typed results. It never reads/executes another owner's SQL file.
- `benchmarks/composition.py`, new `benchmarks/http_adapters.py`: real public
  quote/order and full M1 HTTP adapters now connect CheckoutDriver and
  IntegratedDriver. Search/checkout/integrated lifecycle uses migration, import,
  verification, stock seed, projection barrier and independent seed checks.
  Reviewed templates, fault hook and performance-review path propagate to the
  runner. Clients close after each operation, preserving the no-reuse baseline.
- New `benchmarks/pipeline_transport.py`: W-PIPE materialization/publishing through
  the real shared codec and SDK. Frozen valid synthetic stock facts use only the
  verified 10,000-SKU set; identity/version/time/provenance remain stable.
  The approximately 1-KiB payload is padded without truncating an envelope.
  Invalid-quality and operational facts are refused; no Inventory tables are
  written. Publisher closes on drain, observer failure and exceptional exit.
- New `benchmarks/runtime_observer.py`: actual collector composition from declared
  worker/API metrics, Kafka lag, pinned Gold and SUT resource targets; uses the
  existing readers. Missing SUT/stream inputs and stub collectors fail. Clock
  sharing is explicit and missing samples remain missing.
- New `services/conversation/relay.py`, `events.py:event_codec`: separate M1 relay
  process using the shared `OutboxRelay` and `KafkaPublisher`, with one connection
  and frozen 25-ms/100-row pass controls. Real local schema/append readiness runs
  before publisher construction. SIGINT/SIGTERM shutdown delegates to the shared
  lifecycle. There is no second relay algorithm or publisher in HTTP handling.
- `.env.example` names the optional runtime module. Offline CI explicitly scrubs
  `PROJECTCTL_RUNTIME_MODULE` so developer deployment hooks cannot leak into an
  offline test. Existing core matrix, dependency lock, public contracts and data
  pins were preserved. Documentation in projectctl/benchmarks/conversation now
  describes the current commands and interface rather than the old missing code.
- Tests: new `tests/projectctl/test_runtime.py`,
  `tests/benchmarks/test_pipeline_transport.py`, `test_http_adapters.py`,
  `tests/telemetry/test_runtime_observer.py`, `tests/conversation/test_relay.py`;
  extend composition/CI-isolation tests. Doubles are explicitly labelled. The
  real PostgreSQL relay/migration checks use an isolated M1 schema and actual
  shared library code, with registry-ID and broker acknowledgements doubled.

### Exact checks and evidence

`OUT=artifacts/jaineel/finish-20261108`; `PY=.venv/Scripts/python.exe`.
Counts overlap; no new combined pass count is fabricated.

| Command | Actual outcome |
|---|---|
| `PY -m pytest tests/projectctl/test_runtime.py tests/projectctl/test_composition.py tests/benchmarks/test_pipeline_transport.py tests/benchmarks/test_real_composition.py tests/conversation/test_relay.py -q --tb=short --junitxml=OUT/focused.xml --basetemp=artifacts/f8-tmp -o cache_dir=OUT/cache` | Exit 0, **57 passed**; `focused.{log,xml}` |
| `PY -m pytest tests/projectctl tests/benchmarks tests/telemetry tests/integration tests/contracts tests/oracles -q -ra --tb=short --junitxml=OUT/regression.xml --basetemp=artifacts/f8-reg-tmp -o cache_dir=OUT/cache` | Exit 0, **869 passed**, zero skips, 153.79 s; `regression.{log,xml}` |
| `PY -m pytest tests/conversation -q -ra --tb=short -o junit_family=xunit1 --junitxml=OUT/conversation-postgres.xml --basetemp=artifacts/f8-pg-tmp -o cache_dir=OUT/pg-cache` with explicit isolated test URL | Exit 0, **411 passed**, zero skips, 78.26 s; `conversation-postgres.{log,xml}`. Includes real shared relay SQL/thread/restart checks with explicit broker-ack double |
| `PY -m pytest tests/projectctl/test_runtime.py tests/benchmarks/test_pipeline_transport.py tests/benchmarks/test_http_adapters.py tests/telemetry/test_runtime_observer.py -q --tb=short --junitxml=OUT/new-final.xml --basetemp=artifacts/f8-new-tmp -o cache_dir=OUT/cache` | Exit 0, **32 passed** after final strict-result/padding adjustments; `new-final.{log,xml}` |
| `PY -m pytest tests/benchmarks/test_prompt6_ci.py tests/benchmarks/test_pipeline_transport.py tests/projectctl/test_runtime.py -q --tb=short --junitxml=OUT/final-safety.xml --basetemp=artifacts/f8-safe-tmp -o cache_dir=OUT/cache` | Exit 0, **39 passed**, including the final runtime-env isolation change; `final-safety.{log,xml}` |
| `PY -m ruff check --no-cache benchmarks projectctl services/conversation shared/telemetry dashboards tests/conversation tests/contracts tests/projectctl tests/benchmarks tests/oracles tests/telemetry tests/integration` | Exit 0; `lint-final.log` |
| Same owned paths with `PY -m ruff format --check` | Exit 0, **190 files** formatted; `format.log` |
| `PY -m projectctl.schemas --check`, `PY -m projectctl.conversation_contract --check` | Both exit 0; `schemas.log`, `conversation-contract.log` |
| `PY -m services.conversation.relay --help` | Exit 0; no producer/runtime startup |
| `PY -m benchmarks.manual.verify_prompt7 --out OUT/team-run-readiness-final` | Exit **4 / INCOMPLETE**, performance NOT_RUN, null baseline/C-BEST; `team-run-readiness-final.log` and its saved JSON/Markdown/lock logs. This is the later team-run gate, not a failed implementation unit test |
| `PY -m pytest tests/pipelines/test_transport.py::test_m1_keyword_builder_and_existing_transaction_binding -q --tb=short --junitxml=OUT/peer-fixture.xml --basetemp=artifacts/f8-peer-tmp -o cache_dir=OUT/cache` | Exit 1, **1 failure** in Vichitr's unchanged fixture: missing explicit M1 cache/revision. Raw failure retained; no skip or readiness weakening |

PostgreSQL used only the new `jaineel-finish-pg-20261108` container, loopback
ephemeral port 64925, disposable test credentials and the exact digest-pinned
pgvector/PostgreSQL image in `infra/images.lock.json`. The earlier audit/developer
containers were not reused. Tests create/drop only their own M1 schemas; no
full-team database reset or source-data change occurred. Runtime metadata and
final JUnit summaries are retained alongside the logs. The container is stopped
after testing, retaining its database for inspection.

### Handoff checkpoint

Jaineel's standalone implementation and its tested runtime connections are ready
to share as an implementation branch. Peers can supply their component-specific
operations through the documented input interface; no additional registration
glue is required for those supplied bindings. This does not certify missing
deployments, owner approvals, full-system correctness or performance.

Harsh's stale strict brand xfail and Vichitr's old codec fixture remain owner
corrections; Aditya's actual quote/idempotency, worker provenance and payment
scenario controls remain required for integrated runs. Their exact next tasks
are in CODE_HANDOFF.md. Full-team G0/G1/G3, reviewed hashes/manual relevance,
enforced resources, committed B0, measured comparisons and the reproducible final
report follow integration. Metrics stay null until they actually execute.
Do not start Prompt 7 or performance runs from this checkpoint.

Final owned lint/format and `git diff --check` pass. The dedicated local test
container is stopped after retaining its PostgreSQL log; no container, volume,
schema evidence or unrelated filesystem work is deleted. **Prompt 6 implementation
checkpoint reached with the reproduced Vichitr fixture failure and unexecuted
Linux/Kafka jobs visibly open.** GitHub execution itself remains NOT_RUN until the
user publishes this existing branch through their normal process; no push was made.

## Pre-push repository audit and owned bug fixes — 8 November 2026

User request: audit the repository, determine whether Jaineel can share his work,
fix owned bugs and provide concise team handoffs. This is the audit/handoff
checkpoint; no later performance milestone was started. Read ownership, Jaineel's
brief, relevant context/common/evaluation/source/runbook requirements and current
owner handoffs. No subagents, commit, push or teammate messages were used.

Initial branch/status/diff were retained before edits in
`artifacts/jaineel/push-audit-20261108/{initial-status.txt,initial.diff}`.
`git fetch origin` succeeded; `git rev-list --left-right --count HEAD...origin/main`
returned **0 0** and the corresponding old feature upstream returned **87 0**.
The branch is still `jaineel/j03-telemetry`. Existing modified/untracked work was
preserved. A plain push would omit that uncommitted work.

### Changes in owned/coordinated paths

- `services/conversation/clients.py`: convert JSON decoder recursion failures
  into canonical consumer contract failures; reject malformed/unbounded
  `Retry-After` values without extra attempts, retaining valid delay/date and
  absolute-deadline behavior.
- `tests/contracts/test_clients.py`: six failing-before/passing-after consumer
  regressions cover deeply nested success/error JSON and overflow/negative/signed/
  underscore Retry-After values. Assertions also retain one-attempt and stream
  closure requirements. No public DTO or owner schema changed.
- `.env.example`: include the actual generated `EVENT_SCHEMA_CACHE_PATH` required
  by both the API and relay. No secret or generated schema mapping is committed.
- `benchmarks/manual/verify_transaction_boundaries.py`: opt-in, shareable
  ASGI/SQL-double reproducer for M3 principal/token/fault-guard failures. It does
  not start app lifespans/workers or perform real network/database/payment writes.
  Its failures remain failures; it does not add CI xfails or change owner tests.
- `docs/jaineel/PUSH_AUDIT_2026_11_08.md`: current push verdict, code versus final
  completion, exact findings and repro/handoffs. Refresh `CODE_HANDOFF.md` and
  `TEAM_HANDOFF_2026_11_08.md` with current owned results and M3 findings. Earlier
  audit documents/evidence remain historical and unchanged.

### Commands and actual outcomes

`PY=.venv/Scripts/python.exe`, `OUT=artifacts/jaineel/push-audit-20261108`.
These are shorthand for the actual argv retained in `final-commands.json`, the
offline verifier's `checks.json`, and the Linux command JSON. Counts overlap;
do not add them to manufacture a total.

| Exact command (with shorthand expanded as above) | Actual outcome / evidence |
|---|---|
| `uv sync --locked` | Exit 0; uv 0.10.8, unchanged 37 installed locked packages |
| `PY -m benchmarks.manual.verify_prompt6 --job offline --out OUT/offline` | Exit 1: **1,541 passed / 1 failed / 522 skipped**, 268.24 s; `offline.log`, `offline/{checks.json,summary.json,pytest.xml,pytest.stdout.log}`. The one failure is Vichitr's unchanged M1 cache/revision fixture. This run preceded the new client regressions |
| `PY -m pytest tests/conversation tests/contracts -q -ra --tb=short -o junit_family=xunit1 --junitxml=OUT/conversation-postgres.xml --basetemp=artifacts/pa8-pg-tmp -o cache_dir=OUT/cache` with isolated `P6_TEST_DATABASE_URL`, fixed/zero-model environment | Exit 0: **514 passed**, zero skips, 125.55 s; `conversation-postgres.{log,xml}`. Initial database-backed check before the two HTTP fixes |
| `PY -m pytest tests/contracts/test_clients.py -k 'invalid_retry_after or deep_provider' -q --tb=short --junitxml=OUT/http-before.xml` | Exit 1: **6 failed** before the fix; `http-before.{log,xml}` |
| `PY -m pytest tests/contracts/test_clients.py -q --tb=short --junitxml=OUT/http-after.xml` | Exit 0: **81 passed**, 2.29 s; `http-after.{log,xml}` |
| `PY OUT/run_owned.py` invokes `PY -m pytest tests/conversation tests/contracts tests/projectctl tests/benchmarks tests/oracles tests/telemetry tests/integration -q -ra --tb=short -o junit_family=xunit1 --junitxml=OUT/owned-regression.xml --basetemp=artifacts/pa8-owned-tmp -o cache_dir=OUT/final-cache` | Exit 0: **1,286 passed**, zero failures/skips, 249.71 s; `owned-regression.{stdout.log,stderr.log,xml}`, exact command/env-family metadata in `final-commands.json` |
| `PY OUT/run_linux.py` invokes the retained exact `docker run` argv in `OUT/postgres-linux.command.json`; inner command: `python -m pytest tests/conversation tests/catalog tests/transactions tests/contracts -q -ra --tb=short -o junit_family=xunit1 --junitxml=/out/postgres-linux.xml --basetemp=/testdata/pytest -o cache_dir=/testdata/cache` | Exit **1**: **872 passed / 1 failed / 13 skipped**, 687.16 s. M1 **411 passed**, contracts **109 passed**, transactions **127 passed**; catalogue **225 passed / 1 strict XPASS failure / 13 skipped**. Only failure is Harsh's stale brand marker. Optional ONNX/model and real Kafka requirements explain the skips. `postgres-linux.{command.json,stdout.log,stderr.log,xml}`; per-suite results in `junit-summary.json` |
| `PY -m ruff check --no-cache benchmarks projectctl services/conversation shared/telemetry dashboards tests/conversation tests/contracts tests/projectctl tests/benchmarks tests/oracles tests/telemetry tests/integration` | Exit 0; `owned-lint.stdout.log` |
| Same owned path list with `PY -m ruff format --check` | Exit 0, **191 files** formatted; `owned-format.stdout.log` |
| `PY -m projectctl.schemas --check`; `PY -m projectctl.conversation_contract --check` | Both exit 0; `schemas.*.log`, `conversation-contract.*.log` |
| `PY -c "...inspect_source(Path('data/raw/flipkart_com-ecommerce_sample.csv'))..."` (full exact argv in `final-commands.json`) | Exit 0, PASS: source SHA matches; **20,000 raw / 19,998 canonical / 19,920 active / 78 inactive / 2 superseded / 0 mandatory rejected**. Independent source checks, not performance; `source-checks.stdout.log` |
| `PY -m benchmarks.manual.verify_prompt7 --out OUT/readiness` | Exit **4 / INCOMPLETE**, B0/C-BEST/performance NOT_RUN with null metrics. Draft/missing pins, owner inputs, unenforced resources and dirty revision remain visible; `readiness/*`, `readiness.stdout.log` |
| `PY -m benchmarks.manual.verify_transaction_boundaries --out OUT/transaction-boundaries` | Exit **1**, **6 failed** explicit ASGI/SQL-double assertions, all actual HTTP 200; `transaction-boundaries/boundaries.json` plus stdout/stderr logs. A shareable failing owner handoff, not a live acceptance test |
| `PY -m benchmarks.manual.verify_transaction_boundaries --out OUT/transaction-boundaries-final` | Exit **1**, **7 failed / 1 passed** after strengthening fault probes: supply a valid token and test each flag/namespace independently. Disabling BENCHMARK_MODE correctly returns 403; missing fault-injection guard and unisolated dev access still return 200. `transaction-boundaries-final/boundaries.json`, stdout/stderr |
| `PY -m ruff check --no-cache .` | Exit **1**, **22 existing E501 errors** in Aditya-owned service/test paths; `repo-lint-final.stdout.log`. Owned lint is clean |
| `git diff --check`; `PY OUT/git_review.py` | Whitespace exit 0; scope scan finds no unexpected owner path and no narrow key-pattern matches. Only `data/raw/.gitkeep` is tracked in scanned sensitive/output roots. `git-review.json`, `push-paths.txt`; pattern scanning is not a guarantee of no secret |

The first ignored ASGI diagnostic fixture lacked the payment-ledger row's `kind`
field. Its initial raw failure is preserved in `peer-boundaries.{log,xml}`;
that KeyError was a probe-double error, not a provider defect. After correcting
the synthetic row, `peer-boundaries-final.{log,xml}` proves all six intended
denial assertions fail with HTTP 200. The committed manual verifier reproduces
those findings independently and records explicit `test_mode=stub`. The final
eight-case version separates fault flag/scope checks with valid authorization,
so a future token-only fix cannot hide a missing guard. Seven fail; the existing
benchmark-disabled case passes. Earlier evidence is retained unchanged.

### Scope, handoff and manual verification

The canonical final definition of done is not met: real G0/G1/G3/correctness,
reviewed concrete deployment hooks, frozen inputs/resources, B0, three paired
comparisons, teammate reproduction and final report remain team-dependent work
coordinated by Jaineel. The implementation is ready to share through a draft
feature PR; this does not assert green CI or complete J06/J07. Neither raw owner
experiment numbers nor test doubles were promoted to integrated evidence.

Aditya must fix public snapshot/SSE user binding, internal token enforcement and
both-flags/isolated-namespace fault guards; the exact routes and normative common
§§2–3/5 conflicts are in the audit. Also retain accepted quote retries while
adding fresh quote expiry/user validation and scoped HTTP idempotency, original
saga run identity and deterministic payment outcome/delay controls. Harsh's real
quote getter already enforces user binding and deliberately returns expiry for
Orders to check. His strict brand xfail needs removal/review, not another M1 brand
fix. Vichitr must update the cache/revision fixture and supply verified actual
Kafka/registry and scoped M4 lifecycle/observer/fault inputs. All owners review
hash policy, manifests, manual labels and resource receipts; Jaineel assembles
the supplied runtime bindings and runs the gates. See the updated copyable team
paragraphs; none was sent automatically.

Manual verification: commit/review only owned changes including new files; rerun
the locked offline and Linux PostgreSQL commands after owner fixes; expect the
boundary verifier to deny all eight disallowed accesses. Configure actual cache/revision and
database/HTTP origins, migrate M1, start API plus its separate shared relay, then
verify readiness and replay the explicit quote/cart confirmation scenario. Run
real setup/smoke/correctness only with owner-reviewed scoped bindings. Do not
start performance or fill result values while readiness is incomplete. Hosted
CI, native Kafka/registry/recreation, live complete business Gold/recovery and
human reproduction remain NOT_RUN in this audit.

Final Linux checks finish with the known strict brand XPASS only. The full-file
row/COPY import and real-source search-strata checks both finish successfully;
their intermediate duration was not treated as a pass or a measured performance
result. No assertion or owner code was changed to accelerate the run. The worker
uses the existing locked image
`sha256:285a497c4237cd65cbfc7c02bcb560d6df7c718e02be2e5461c21f5e97a67766`
and read-only service/shared/pipeline/analytics/contracts/config/tests/migrations/
docs/infra/source mounts; actual state and fsync work use the new Linux volume.
PostgreSQL is the exact digest-pinned pgvector image from `infra/images.lock.json`
(observed server 18.2), new container `jaineel-push-audit-pg-20261108`, loopback
test port 60651, disposable credentials and new test database only. `CREATE
EXTENSION IF NOT EXISTS vector WITH SCHEMA public` was applied only there.
Native M1 and Linux provider tests create/drop their isolated per-test schemas.

After the final verifier refinement, owned lint and formatting were rerun and
pass (`owned-lint-final.log`, `owned-format-final.log`, 191 files); the verifier
also passes its focused lint/format checks. Source changes after the full owned
regression were confined to that independently executed diagnostic verifier and
documentation. No tests were rerun merely to change the known peer outcomes.

`docker logs jaineel-push-audit-pg-20261108` was saved to `OUT/postgres.log`, then
`docker stop jaineel-push-audit-pg-20261108` stopped only this new database. Its
data, the dedicated `jaineel-push-audit-20261108-data` volume/network and all raw
evidence are retained. The `--rm` Linux worker has exited. Earlier/development
containers and volumes were not touched. Final scope/whitespace review was
repeated after the documentation updates: **81 changed paths**, no unexpected
owner path, no narrow credential-pattern match, and `git diff --check` exit 0.
Only `.env.example` is tracked among `.env*`; only `.gitkeep` is tracked in the
raw/output roots scanned. Retain `final-status.txt`, `final-git-review.*.log` and
`final-whitespace.*.log`. The audit/handoff checkpoint is complete; no
commit/push was made. Full-team correctness and evaluation remain open.

## Repair the four existing CI jobs — 8 November 2026

The user explicitly requested repairing the failed checks, validating **locally
only**, adding no CI tests/jobs, then committing/pushing to the **current branch**.
Initial working tree was clean on `jaineel/j03-telemetry`, HEAD
`a994f01cbd81daa4687722e7994d39a51a84e61f` (`integrations`), matching its upstream.
This request authorizes the narrow cross-owner fixture/infrastructure corrections
needed by these checks; no teammate business implementation or public contract
was replaced. No manual hosted rerun/dispatch or new test case/job was added.

Historical GitHub run **42455183438** supplies the four actual failure traces:
both offline OS jobs fail the same M1 event fixture; PostgreSQL fails the stale
strict brand xfail; streaming startup fails service-role authentication. Logs,
job metadata and original uploaded evidence were downloaded read-only into
`artifacts/jaineel/ci-fix-a994f01-20261108/` (`OUT` below). GitHub CLI was absent;
the read-only REST requests used the existing Git credential helper in memory.
No credential was printed or persisted by that helper.

### Corrections, preserving existing coverage

- `tests/pipelines/test_transport.py`: the existing transaction-binding case now
  supplies a temporary, checksum-pinned registry mapping and explicit synthetic
  dataset revision to M1's process-local codec. Retain transaction identity and
  wire checks; additionally assert the revision and real codec validation. The
  required production readiness checks remain strict.
- `tests/catalog/test_conversation_consumer_live.py`: remove only the stale
  strict-xfail marker for the repaired brand comparison. The existing test now
  requires nonempty real HTTP results with the requested brand. No test is
  deleted, skipped or converted to an expected failure.
- `infra/postgres/entrypoint.sh`, `infra/compose.yaml`: stage root-readable
  Compose secrets into a private tmpfs as postgres-owned **0600** files before
  delegating to the official image entrypoint. The original host-owned **0600**
  files remain unchanged. Compose explicitly keeps the postgres command, pinned
  image, init, resources, loopback port, health probe and retained data volume.
  This fixes Linux bind-mount UID permissions without making secrets public.
- `infra/postgres/10-databases.sh`: consume the staged paths and read each secret
  in a separate fail-fast assignment. Previously `cat` failed inside a psql
  argument, initialization continued, and PostgreSQL cleared the empty role
  passwords. The original CI log explicitly contains both Permission denied and
  User has no password assigned. Failed/empty reads now stop initialization.
- `benchmarks/manual/prompt6_services.py`: the existing volume job needs the
  whole read-only migration tree, because its existing analytical tests import
  catalogue migration descriptors during collection. Mount it through the
  existing CI overlay. Strengthen the existing overlay assertion in
  `tests/benchmarks/test_prompt6_ci.py`; no new test function or parametrization
  is introduced. This hidden collection failure was reached only after fixing
  the earlier streaming startup error.

`.github/workflows/offline.yml` is unchanged. The same four jobs remain: offline
Windows, offline Ubuntu, PostgreSQL, and Kafka/Registry/Linux volume. All
existing suites and opt-in/live-test conditions remain in place.

### Local environment and evidence integrity

Docker's local metadata filesystem became read-only when C: had roughly 250 MiB
free. The first full Windows attempt could not complete and Docker downloads
were incomplete. Clear only rebuildable uv/pip download caches through their
own cache commands (verified cache directories), then restart Docker normally;
pip reported 4,951 MB removed. No installed environment, source, raw dataset,
model, saved evidence or database volume was deleted. Reacquire the affected
new Kafka/Registry/tool images at the original SUT pins. Earlier failed attempts
and diagnostic logs remain in OUT and are not counted as passing checks.

The isolated Linux permission reproduction creates **UID 1001 / mode 0600**
source files on a new named volume and first proves postgres cannot read them.
The real entrypoint then authenticates all six non-superuser roles using its
private copies; originals keep UID 1001 and mode 0600. Evidence:
`secret-permissions.{json,log}`, command JSON and PostgreSQL log. Only that
diagnostic database container is stopped afterward; its volumes are retained.

Local Linux mirrors use a disposable worker derived from the existing locked
image, read-only source, Linux-volume temporary evidence, the actual pinned
services and explicit private test URLs. Correct two mirror-only environmental
issues without changing repo behavior: put Ruff's cache on writable storage and
clear the storage image's inherited `LAKEHOUSE_ROOT` for ordinary host-style
jobs. Preserve the earlier cache/missing-directory errors as harness errors.
An overlapping initial database/recreation trial was stopped and invalidated:
recovery recreates PostgreSQL. Final recovery completes before starting the
database-backed suites. These intermediate attempts are not provider failures
or acceptance evidence.

### Executed checks so far

- `PY=.venv/Scripts/python.exe`; `PY -m pytest tests/pipelines/test_transport.py
  tests/pipelines/test_postgres.py tests/benchmarks/test_prompt6_ci.py -q
  --tb=short --junitxml=OUT/focused.xml`: **66 passed**, exit 0.
- After the migration-overlay fix, `PY -m pytest
  tests/benchmarks/test_prompt6_ci.py -q --tb=short
  --junitxml=OUT/plumbing.xml`: **18 passed**, exit 0. Counts overlap.
- `PY -m benchmarks.manual.verify_prompt6 --job offline --out
  OUT/offline-windows-final`: **1,548 passed / 522 skipped / zero failures/errors**,
  **2,070 collected**, exit 0. `offline-windows-final.log` and its JUnit/checks.
- `PY -m projectctl env up --profile streaming-local` with
  `PROJECTCTL_ADAPTER_MODULE=infra.streaming`: exit 0 after environment recovery;
  all pinned services, roles, schemas/topics and resources verified.
  `streaming-up-final.log` and its actual referenced infrastructure receipt.
- Local Linux invocation of the existing
  `python -m benchmarks.manual.verify_prompt6 --job kafka --out ...`:
  **7 passed / zero failures/skips**, exit 0. Includes real PostgreSQL isolation
  and recreation, Kafka/Registry recreation, schema compatibility, SDK and stock
  projection. `local-kafka-final/{summary.json,pytest.xml,checks.json}` plus
  `kafka-final-linux.*`; no live DE/performance gate is inferred from this job.

Linux offline/PostgreSQL/volume final results, final whitespace/scope review and
the resulting commit/push receipt are recorded in the continuation below once
their checks complete. The user requires validation before pushing; no push has
been made during this repair checkpoint yet.

### Completed local validation and cleanup

The continuation supersedes the pending results above. Three further existing
test fixtures needed corrections exposed by the complete local runs:

- `tests/catalog/test_search_live.py`: removing `shared.outbox` from the module
  cache allowed a real re-import and made the missing-provider case depend on
  suite order. Explicitly block the import with the standard `sys.modules`
  sentinel. Keep all 503, search and readiness assertions.
- `tests/contracts/test_clients.py`: perform real request-schema validation
  before starting this transport-only timing probe, then use an explicitly
  named prevalidated-request double. Retain the original 25 ms deadline,
  200 ms slow response, 150 ms elapsed bound and exactly-one-request assertion.
  This fixes schema setup consuming the deadline before any HTTP request.
- `tests/analytics/test_query_suite_live.py`: the existing optional cold-read
  case now checks the actual read-byte counter as well as `posix_fadvise`.
  This local WSL kernel lacks `/proc/self/io`; report an explicit NOT_RUN skip
  when counters are unavailable, matching the production measurement policy.
  No fabricated read counters or measured cold results are substituted. The
  existing unavailable-counter contract test continues to execute.

Final existing job results, all exit 0 with **zero failures and errors**:

| Local execution | Passed | Skipped | Collected | Evidence under OUT unless stated |
|---|---:|---:|---:|---|
| Windows offline verifier | 1,548 | 522 | 2,070 | `offline-windows-final/` |
| Linux offline verifier | 1,565 | 505 | 2,070 | `local-offline-checked/` |
| Linux PostgreSQL verifier | 757 | 20 | 777 | `local-postgres-ci-checkout/` |
| Native Kafka/Registry verifier | 7 | 0 | 7 | `local-kafka-final/` |
| Linux volume verifier | 408 | 10 | 418 | `artifacts/ci-volume/` |

These are overlapping job counts, not a combined unique-test total. Exact local
commands retained in the ignored helpers and command receipts:

- `PY OUT/run_linux_job.py offline -checked` with
  `CI_FIX_CLEAN_CHECKOUT=1`; inner command is
  `python -m benchmarks.manual.verify_prompt6 --job offline --out
  artifacts/local-ci-runs/ci-fix-offline-checked`.
- `PY OUT/run_isolated_postgres.py`; inner command invokes the unchanged
  `benchmarks.manual.verify_prompt6 --job postgres` against a dedicated
  digest-pinned PostgreSQL replica. Full argv, bindings and stdout/stderr are
  retained in `postgres-ci-checkout-linux.*`.
- `PY -m benchmarks.manual.prompt6_services volume`; stdout/stderr in
  `volume-verified.*`, with the actual existing verifier evidence above.
- `PY -m pytest tests/contracts/test_clients.py tests/integration/test_g3.py
  -q --tb=short --junitxml=OUT/http-final.xml`: **115 passed**, exit 0, after
  the final timing-fixture correction. The full Windows job predates that last
  fixture edit; these affected suites and the final full Linux job validate it.
- `PY OUT/final_summary.py`: exit 0; `verified-summary.json` records all five
  PASS summaries, zero failures/errors and SHA256 evidence hashes, confirms the
  workflow is unchanged and that no new test cases were introduced.
- `PY -m ruff check --no-cache` and `PY -m ruff format --check --no-cache`,
  listing all seven changed Python files: both exit 0, seven files formatted.
  `git diff --check` and
  `git diff --exit-code HEAD -- .github/workflows/offline.yml`: exit 0.

The final PostgreSQL replica mirrors the GitHub checkout: ignored raw CSV files
are absent only inside the disposable container, using a temporary mount. Host
source data is untouched and no tests are deselected. A prior full-source run
completed **763 passed / 1 failed / 13 skipped**; its only failure was the
missing-outbox fixture above, and its raw evidence remains preserved. Earlier
volume missing-migration/counter and deadline-setup failures also remain in OUT.
Existing source/model/provider/platform prerequisites explain visible skips;
these are not claims of full-team correctness or performance completion.

Stop the repair stack with `PROJECTCTL_ADAPTER_MODULE=infra.streaming
PY -m projectctl env down` (exit 0); retain data volumes and actual logs in
`streaming-down.log`, `final-services.log` and `postgres-service.log`. The user
then explicitly requested removing images/containers no longer needed.
`PY OUT/cleanup_docker.py` and `PY OUT/finish_cleanup.py` removed the two stopped
local offline workers, four disposable images (`jaineel-ci-local-tests`,
`jaineel-prompt1-tests`, `docker:29-cli`, `postgres:18.6`) and 1.115 GB of
rebuildable build cache. A redundant digest-alias removal found the alias already
removed with its tag; the continuation verified completion. Receipt:
`docker-cleanup.json`. Final inventory: **zero containers, zero build cache**;
retain only the current project storage worker and digest-pinned Kafka/pgvector
images. **No data volume was removed**; all 23 volumes and saved evidence remain.
The earlier disk recovery also cleared only rebuildable npm download cache.

Changed paths are the seven Python files named above, `infra/compose.yaml`,
`infra/postgres/{entrypoint.sh,10-databases.sh}`, this progress file and the owned
`TEAM_HANDOFF_2026_11_08.md` / `PUSH_AUDIT_2026_11_08.md` status notes. No
credentials, raw source, generated data or benchmark result directories are
staged. The user authorized committing/pushing to `jaineel/j03-telemetry` after
local validation. The actual resulting commit and remote synchronization receipt
are recorded after push in ignored `OUT/git-receipt.json`; an ordinary push may
automatically trigger the existing GitHub workflow. No manual hosted test run is
requested or used as local validation.

Jaineel's code-side handoff can be shared. Remaining work is the reviewed owner
bindings, security/transaction repairs and actual integration/evaluation listed
in the team handoff, followed by Jaineel's real gates, B0, paired comparisons,
independent reconciliation and report. A green local CI repair does not complete
those deliverables. Manual continuation: pull this branch, provide the reviewed
owner bindings, and execute the existing runbook gates with real resources.

## Merge Harsh's main update and repair CI bootstrap - 8 November 2026

The user explicitly requested inspecting the still-failing CI, then merging
Harsh's new `main` into the current branch before final checks and push. Keep
the existing four checks and run validation locally; add no CI jobs/tests.
Initial branch was `jaineel/j03-telemetry`, HEAD
`a0d6d239295e723ed5e3ecbf152003f0aec0279f`. The only uncommitted change was the
in-progress workflow bootstrap repair, preserved before merging.

### Actual hosted failure diagnosis

Read-only inspection of run **42471550974**, for exactly `a0d6d23`, finds
**Ubuntu offline and PostgreSQL passed**. Windows offline and Kafka/Registry
failed in `astral-sh/setup-uv@v6`, before dependency sync or any test ran:
both repeatedly received **HTTP 504** downloading uv **0.10.8** release assets
from GitHub. Kafka log retention and teardown then failed secondarily because
`uv` did not exist. This is distinct from the earlier repaired fixture and
PostgreSQL permission errors. Preserve jobs, logs and uploaded artifacts in
`artifacts/jaineel/ci-followup-a0d6d23-20261108/` (`FOLLOWUP`).
`FOLLOWUP/diagnosis.json` records the exact failed steps. No manual hosted
rerun/dispatch was requested or performed.

### Main integration and preserved contracts

- `git fetch origin` obtained `origin/main` at
  `fc6b85b545b3736324f37f12a4995be1dba88652` (Harsh's PR #10).
- `git stash push -m "ci-bootstrap-fix-before-main-merge-20261108" --
  .github/workflows/offline.yml` preserved the single local change.
- `git merge --no-edit origin/main` exposed one content conflict in
  `tests/catalog/test_conversation_consumer_live.py`. Keep both sides' checks:
  nonempty hits, matching canonical brand and exactly SKU `FK-SHIRT1`.
  `git add -- tests/catalog/test_conversation_consumer_live.py` and
  `git commit --no-edit` created merge
  `7f1b50b1c2643f99a0fff79e0616fe97325ac79b`, with both original parents intact.
- `git stash apply "stash@{0}"` restored the workflow fix without conflict;
  drop only that successfully applied task stash afterward.
- Preserve Harsh's migration/seed-audit hooks, analytics layout bindings,
  manifests and tests from main. No catalogue business implementation or public
  DTO/contract was replaced. His tracked `quality_by_category.csv` uses CRLF;
  the merge whitespace diagnostic reports its line endings. Keep those pinned
  incoming bytes unchanged instead of rewriting owner evidence to silence it.

### Bootstrap correction and validation scope

`.github/workflows/offline.yml` now sets up Python **3.11** through
`actions/setup-python@v5` and installs the exact **uv==0.10.8** binary wheel
from PyPI with no dependencies, five retries and a 60-second request timeout.
This removes the failing uv GitHub release-asset download path. PyPI installation
is documented by [Astral](https://docs.astral.sh/uv/getting-started/installation/#pypi);
Python setup inputs are verified against the official action definition.
All existing test commands, matrices, image pins, opt-ins, assertions and timeouts
are retained. There is no continue-on-error around bootstrap or tests.

The existing Kafka log/teardown steps require successful dependency setup so a
missing tool cannot obscure the original setup error. They still run after an
infrastructure attempt or test fails, retaining the established cleanup path.
No new tests are authored here; preserve the tests already merged from main.

Local evidence for the merged checkpoint is
`artifacts/jaineel/merge-main-fc6b85b-20261108/` (`MERGEOUT`). Explicit isolated
PostgreSQL/Kafka services and the existing locked Linux worker are used, with
read-only source and writable test evidence. The dedicated PostgreSQL job has
its own disposable database/volume so native recreation cannot interrupt it.
Linux offline/PostgreSQL mirrors hide only the ignored raw CSV inside the
container, matching a real CI checkout; the host dataset is untouched.

Already executed local setup checks:

- Fresh Windows and Linux Python environments installed **uv 0.10.8** from PyPI
  successfully; exact argv/versions in `FOLLOWUP/{windows,linux}-bootstrap.json`.
  The interrupted earlier Windows full run is not counted as completion.
- The first fresh Linux mirror reached pytest but its read-only artifacts mount
  stopped pytest configuration. Retain `FOLLOWUP/linux-initial-readonly/`.
  A later fresh dependency download timed out on the locked PyArrow wheel; its
  raw failure remains in `FOLLOWUP/linux-sync-locked.stderr.log`, not a pass.
- `PY MERGEOUT/local_jobs.py linux-sync` audits the actual existing locked Linux
  image with `uv sync --locked --offline --project /repo` and explicit
  `UV_PROJECT_ENVIRONMENT=/app/.venv`: **exit 0**, 38 resolved / 35 audited.
  It does not fabricate a fresh external-package download acceptance result.
- `PY FOLLOWUP/validate_workflow.py`: **exit 0**; structural comparison verifies
  the same four checks and unchanged test/service settings beyond bootstrap
  and unavailable-tool guards. `FOLLOWUP/workflow-validation.json`.
- Checksum-verified **actionlint v1.7.12**, invoked locally with
  `-shellcheck= -pyflakes= .github/workflows/offline.yml`: **exit 0**.
  The optional external shellcheck/pyflakes tools are unavailable and explicitly
  disabled; actionlint's workflow/expression validation executes.
- `PY -m ruff check` and `PY -m ruff format --check` on the merged brand test,
  query-suite test, analytics suite and catalogue adapter: **exit 0**, four files
  already formatted. `git diff --check` for the remaining repair: exit 0.

Full post-merge job results and push/cleanup receipt follow after completion.

### Native rebalance/shutdown defect found during post-merge validation

Windows offline first completed **1,548 passed / 525 skipped**, zero failures.
The first Linux offline mirror completed **1,554 passed / 11 failed / 508
skipped**: every failure was `FileNotFoundError: git` in the existing ignore-rule
tests. GitHub runners provide Git; the temporary base worker did not. Add Git
only to a disposable local validation image, keep the original failed evidence
in `MERGEOUT/offline/`, and rerun the identical verifier. The corrected local
mirror completed **1,565 passed / 508 skipped**, zero failures. No repository
assertion was removed or weakened. An initial PostgreSQL worker name collided
with the dedicated database container before pytest started; the corrected
isolated invocation is retained separately as `postgres-final`.

The native Kafka job exposed an intermittent **real SDK shutdown defect**.
The broker recorded a stalled rebalance; the job exceeded its prior 96-second
runtime substantially. Save raw broker/PostgreSQL logs in
`hung-native-{broker,postgres}.log`, then intentionally abort only that hung
local pytest process to collect its enabled faulthandler trace. It reports
`ConsumerGroup.close -> _on_assign -> consumer.assign`, stuck inside native
assignment while native close is draining queued rebalance callbacks.
`native-hang-abort.json` records the diagnostic action. The resulting exit -6
and null JUnit count in `MERGEOUT/kafka/` are an intentionally aborted diagnostic,
**not a provider acceptance pass**.

Narrow corrections required by this CI-repair request:

- `shared/event_transport/consumer.py`: mark shutdown in progress before native
  close and ignore newly queued assignment callbacks during shutdown. Retain
  durable-prefix revoke/commit behavior, thread ownership, closed-handle checks
  and final buffer cleanup. No API, DTO or event contract changes.
- Extend the **existing** revoke/fencing unit case in
  `tests/pipelines/test_transport.py` with an explicit native-command double
  that drains a queued assignment while closing. Before the implementation fix,
  it fails because the closed worker reacquires assignment state:
  `close-before.xml`. After the fix, the whole existing transport file passes
  **27 tests**, `transport-after.xml`. This is double evidence only.
- `tests/pipelines/test_transport_live.py`: keep the second real consumer on its
  own single-owner executor thread and poll both workers concurrently during
  rebalance. Run that consumer's read/durable/commit/close calls on its owner
  thread. Preserve all old-owner fencing, exact source bytes/offsets, assignment
  epoch and confirmed durable-offset assertions. No new test case or relaxed
  deadline is introduced.

The complete existing native verifier rerun then passes **7/7 real tests** in
`MERGEOUT/kafka-fixed/`, with actual PostgreSQL/Kafka/Registry recreation.
`PY MERGEOUT/local_jobs.py verify` returns exit 0 after recreation. The separate
PostgreSQL verifier passes **759 / 20 skips / 779 collected**, zero failures or
errors (`MERGEOUT/postgres-final/`). The two full offline verifiers are rerun
after the SDK change, followed by the existing Linux volume check. Vichitr should
review the SDK callback/shutdown correction as part of the normal branch review;
it does not require a public-interface decision or replacement owner implementation.

### Final post-merge local acceptance

All existing job suites finish with **zero failures and errors**:

| Existing check/phase | Passed | Skipped | Collected | Evidence |
|---|---:|---:|---:|---|
| Windows offline, after SDK fix | 1,548 | 525 | 2,073 | `MERGEOUT/offline-windows-final/` |
| Ubuntu/Linux offline, after SDK fix | 1,565 | 508 | 2,073 | `MERGEOUT/offline-after-sdk/` |
| PostgreSQL 18, dedicated CI replica | 759 | 20 | 779 | `MERGEOUT/postgres-final/` |
| Kafka/Registry native and recreation | 7 | 0 | 7 | `MERGEOUT/kafka-fixed/` |
| Linux SQL/files/publication/replay/analytics volume | 409 | 10 | 419 | `artifacts/ci-volume/` |

These phases overlap and must not be summed as unique tests. The four GitHub
checks remain the same; Kafka's native and volume phases are listed separately
to show both executed. Existing missing-source/model/provider/platform skips
remain explicit; optional cold reads are NOT_RUN on this WSL kernel without
`/proc/self/io`. No full-team DE gate or performance result is inferred.

Exact final local commands (`PY=.venv/Scripts/python.exe`):

- `uv run --locked python -m benchmarks.manual.verify_prompt6 --job offline
  --out artifacts/jaineel/merge-main-fc6b85b-20261108/offline-windows-final`.
- With `CI_LOCAL_WORKER_IMAGE=jaineel-merge-ci-worker:20261108`,
  `PY MERGEOUT/local_jobs.py offline -after-sdk`,
  `PY MERGEOUT/local_jobs.py postgres -final` and
  `PY MERGEOUT/local_jobs.py kafka -fixed`. Each invokes the original
  `python -m benchmarks.manual.verify_prompt6 --job JOB --out ...` inside the
  Linux mirror. Exact Docker argv (test URLs redacted), exit codes, raw logs,
  JUnit and summary/check JSON are retained per phase in MERGEOUT.
- `PY MERGEOUT/local_jobs.py verify`: exit 0 after native recreation.
- `PY MERGEOUT/local_jobs.py volume`: invokes unchanged
  `python -m benchmarks.manual.prompt6_services volume`, rebuilding the locked
  pinned worker and executing the actual existing Compose/volume job; exit 0.
  `volume.{stdout,stderr}.log`. Preserve the earlier volume receipt by moving it
  to `MERGEOUT/previous-ci-volume/` before this invocation; do not overwrite it.
- `PY MERGEOUT/final_summary.py`: exit 0; `verified-summary.json` checks every
  final PASS, records counts/evidence hashes and the exact validated source
  Git blob IDs, and confirms `origin/main` is an ancestor of HEAD.
- `PY FOLLOWUP/validate_workflow.py`: final exit 0, same four checks and test
  commands/services, unchanged application lock and unchanged collected test
  function names in the two edited transport files. Workflow changes are
  confined to bootstrap and missing-tool cleanup guards.
- `PY -m ruff check` / `ruff format --check` on the three changed transport
  Python files: exit 0. Final full owned offline lint/format/schema/contract
  checks also pass their existing acceptance policy. `git diff --check` passes
  for the repair diff; incoming pinned CSV bytes remain as committed on main.

Only `.github/workflows/offline.yml`, `shared/event_transport/consumer.py`,
the two existing transport test files and this owned progress record are changed
after the merge. Do not stage temporary helpers, credentials, raw data, images,
test output or benchmark artifacts. Final commit/push is explicitly authorized
on the current `jaineel/j03-telemetry` branch after these local checks. The
post-push ignored `MERGEOUT/git-receipt.json` records the actual SHA and remote
sync result; an ordinary push triggers the existing workflow automatically.
No manual hosted rerun/dispatch is performed.

Cleanup completes through `PY MERGEOUT/cleanup.py` after the all-PASS receipt.
Save real service logs, run `PROJECTCTL_ADAPTER_MODULE=infra.streaming
PY -m projectctl env down`, stop/remove only the dedicated CI PostgreSQL
container, and remove the temporary Git-equipped worker, superseded worker
image and unused build cache. Remove only verified task-local bootstrap/cache
and copied Docker-tool directories; keep all raw evidence. An initial cleanup
invocation incorrectly supplied `--profile` to `env down` and was rejected with
exit 2 before stopping anything; retain `cleanup-initial.json` and its stdout,
then use the supported command above. Final cleanup exits 0 and records
**zero containers, zero build cache, four current project images retained and
all 34 data volumes preserved** in `MERGEOUT/cleanup.json`. No volume is deleted.

Checkpoint: merged code and all existing local job phases are ready to push.
Whole-team evaluation, reviewed bindings and benchmark results remain separate
unfinished deliverables. Manual continuation is the ordinary existing workflow
on the final push and Vichitr's normal review of the SDK shutdown fix; no new
CI job, test-case expansion or automatic owner approval is introduced.

## Evaluation handoff after Vichitr PR #12 — 9 November 2026

User requested inspection of the pulled changes and implementation of the
evaluation-profile, analytics/oracle, provider-validation and input/report
handoffs. User then explicitly requested **no evaluation now**, and asked for
instructions to give the executing teammate and a decision/review document for
Harsh. This checkpoint implements the owned harness changes and prepares those
handoffs; it does not claim the final whole-team evaluation is ready or passed.

Initial branch `jaineel/j03-telemetry`, HEAD `6e1e633`. The pre-existing change in
`.github/workflows/offline.yml` is preserved and was not edited here. No other
owner implementation, shared DTO, canonical specification, application lock,
Compose file, database, Kafka topic or volume was changed. No commit/push.

Changed paths:

- `projectctl/contract_checks.py`, new `projectctl/provider_validation.py`:
  execute six provider compatibility validators; consume real byte-pinned
  owner/consumer receipts instead of unconditional UNREVIEWED. Pending receipts
  remain UNREVIEWED; stale/malformed approval or failed validation fails.
- `projectctl/runtime.py`, `projectctl/setup.py`, new `projectctl/team_runtime.py`:
  lazy M4/operational runtime composition, duplicate guards, concrete M1/M2/M4
  migration delegates, required owner migration/reset participants and global
  all-participant preflight. No replacement M3 migration/reset implementation.
- `benchmarks/quality_binding.py`, `benchmarks/quality_trial.py`: G1 dataset and
  resource context, topics before deployment, teardown on failure, separate G1
  module command and performance-review forwarding.
- `benchmarks/pipeline_audit.py`, `benchmarks/performance.py`, new
  `benchmarks/analytics_recheck.py`: stricter independent wire/Bronze scope and
  membership checks; persist M4 audit mappings; rederive saved W-PIPE/W-QUALITY
  verdicts from raw exports and the actual pinned mapping review. Reject stub
  exports and changed raw/projection bytes; no fabricated fixture approval.
- `projectctl/input_pins.py`, new `projectctl/evaluation_packet.py`,
  `configs/evaluation_profiles.json`: exact-byte evaluation hashes kept separate
  from Harsh's LF dictionary identity; verified manifests, five available
  logical recipes, individual worker/process budgets, candidate configs,
  proposed reviews and explicit missing-case inventory. Everything stays
  draft/planned/review-pending and performance remains null/NOT_RUN.
- Tests: new `tests/contracts/test_provider_validation.py`,
  `tests/projectctl/test_team_handoff.py`,
  `tests/benchmarks/test_analytics_recheck.py`; extend existing
  `tests/benchmarks/test_pipeline_audit.py` and `test_quality_lifecycle.py`.
  Runtime/SQL/registry/review/clock doubles are explicitly labelled; these are
  software checks, not real service or benchmark acceptance.
- Documents: `docs/jaineel/VICHITR_REVIEW_2026_11_09.md`,
  `HARSH_REVIEW_2026_11_09.md`, `EVALUATION_TEAMMATE_RUNBOOK.md`, and this record.

### Commands and actual evidence

All commands from the repo root; `PY` below means `.venv/Scripts/python.exe`.

| Command/check | Actual outcome | Evidence |
|---|---|---|
| `git status --short`, `git branch --show-current`, `git log -8 --oneline`, diff inspection | Read pulled Vichitr commits and existing workflow edit before changes | Session transcript; review document |
| `Get-CimInstance Win32_ComputerSystem` and `Win32_OperatingSystem`, selected nonsecret fields | 12 logical CPUs, 16,802,910,208 bytes RAM, observed free 867,056 KiB | Session transcript; review document. No machine feasibility claim |
| `PY -m pytest -q tests/contracts/test_provider_validation.py tests/projectctl/test_team_handoff.py tests/projectctl/test_runtime.py tests/benchmarks/test_quality_lifecycle.py tests/benchmarks/test_quality_binding.py tests/benchmarks/test_pipeline_audit.py --basetemp=artifacts/pytest-evaluation-handoff-first --junitxml=artifacts/evaluation-handoff-first.xml` | **102 passed**, zero failures/skips | `artifacts/evaluation-handoff-first.xml` |
| `PY -m pytest -q tests/projectctl tests/contracts tests/benchmarks tests/oracles tests/integration --basetemp=artifacts/pytest-evaluation-handoff-regression --junitxml=artifacts/evaluation-handoff-regression.xml` | **875 passed**, zero failures/skips, 376.36 s; broad regression before the final saved-audit follow-up | `artifacts/evaluation-handoff-regression.xml` |
| `PY -m pytest -q tests/contracts/test_provider_validation.py tests/projectctl/test_team_handoff.py tests/projectctl/test_runtime.py tests/benchmarks/test_quality_lifecycle.py tests/benchmarks/test_quality_binding.py tests/benchmarks/test_pipeline_audit.py tests/benchmarks/test_analytics_recheck.py tests/benchmarks/test_performance.py tests/pipelines/test_team_runtime.py tests/pipelines/test_analytics_adapter.py --basetemp=artifacts/pytest-evaluation-handoff-final --junitxml=artifacts/evaluation-handoff-final.xml` | **131 passed**, zero failures/skips, 20.66 s; covers final mapping/recheck code and M4 adapter compatibility | `artifacts/evaluation-handoff-final.xml` |
| `PY -m projectctl.evaluation_packet --out artifacts/evaluation-handoff/20261109-review` then `--verify artifacts/evaluation-handoff/20261109-review` | Both exit 0; 71 frozen input references, 14 packet files; `INPUTS_PINNED_REVIEW_PENDING`, evaluation NOT_RUN | `artifacts/evaluation-handoff/20261109-review/input_lock.json`, content SHA `0911a658b9c8ac61d358bc3ff11e381d3498668f1a8bc3f4f3eb625809572442` |
| `PY -m projectctl contracts check --all` | Actual CLI exit/status **4 / NOT_RUN**: all six compatibility validators pass, actual owner review receipts absent. This is expected missing review evidence, not G0 acceptance | `artifacts/projectctl/3778cbe5-de21-4981-a56f-c01604e067f7/{manifest,summary}.json` |
| `PY -m projectctl.schemas --check`; `PY -m projectctl.conversation_contract --check` | Exit 0; generated contracts current | Session transcript |

The phases overlap; do not sum their counts as unique tests. Earlier formatting
checks reported line wrapping, corrected before final checks. The first offline
draft packet `artifacts/evaluation-handoff/20261109-draft-01/` is preserved; its
pins predate subsequent code edits and it must not be used for execution.
No live test opt-in, source import, benchmark, generic evaluation suite, Docker
startup, fault injection, reset or measured report was executed for this task.

Final static commands (the following exact path list is shared by Ruff check
and format check): `PY -m ruff check projectctl benchmarks/analytics_recheck.py
benchmarks/performance.py benchmarks/pipeline_audit.py benchmarks/quality_binding.py
benchmarks/quality_trial.py tests/contracts/test_provider_validation.py
tests/projectctl/test_team_handoff.py tests/benchmarks/test_pipeline_audit.py
tests/benchmarks/test_quality_lifecycle.py tests/benchmarks/test_analytics_recheck.py`
and `PY -m ruff format --check` with that same list; plus `git diff --check`.
Final outcomes are recorded after the closing verification below.

### Remaining owner handoffs and manual checks

The proposed official integrated budget counts 16 processes at P10 / 18 at P33,
8.25 allocated cores and 7,808 MiB within a 9-core/8,192-MiB SUT budget. Separate
pipeline profile: five/seven processes, 3.75 cores/4,096 MiB. Consumer-group total
is fixed at 1.5 cores/1,536 MiB with API counted separately. Actual machine and
enforcement remain NOT_RUN; prefer a dedicated >=12-logical-CPU/32-GiB Linux SSD
host, with separate generator budget. Pair only within the same enforced profile.

The actual packet records three migration participants (conversation/catalog/
analytics), zero reset participants and **37 unregistered generic integration
cases**, all NOT_RUN. Existing M4 W-PIPE/quality callbacks and the separate G1
CLI are connected; missing business/G3/fault/data case bindings are not supplied
by pretending provider pytest results are whole-team evaluation receipts.
Orders/Inventory/Payments must supply their migration delegates and operational
relay/runtime bindings. All owners must provide read-only reset preflights and
guarded apply callbacks if an explicit reset is later required.

Actual owner mapping approvals, exact seed SKU membership, shared clock proof,
operational fresh-storage/seed/projection composition, reviewed checkout/integrated
templates and human relevance labels remain handoffs. Final measurement uses a
clean committed revision and genuine correctness/resource/readiness evidence.
The current packet pins this dirty working tree for review only. The executing
teammate must regenerate/review the final machine's exact-byte pins once, preserve
them for every comparator, run required gates, and return the raw bundles for
Jaineel's existing reconcile/compare/report path. No performance conclusion exists.

Give Harsh `HARSH_REVIEW_2026_11_09.md` and the generated packet. Give the executing
teammate `EVALUATION_TEAMMATE_RUNBOOK.md`, the packet and the eventual reviewed
commit. It contains exact commands, private deployment input names, prerequisites,
failure handling and evidence to return. Public contract changes still require
affected-owner review; no canonical hash/dataset behavior was silently changed.

Closing verification: Ruff check **exit 0**, format check **exit 0** (31 Python
files already formatted), generated evaluation schemas/OpenAPI **exit 0** and
`git diff --check` **exit 0**. Packet verification repeats **exit 0** with the
same content hash above. Final diff inspection confirms the pre-existing workflow
edit is unchanged and `git diff --quiet -- uv.lock pyproject.toml services
shared/contracts infra migrations contracts/events contracts/data/catalog
contracts/dictionaries/catalog configs/evaluation.yaml` returns **exit 0**.
No owned implementation check is failing at this checkpoint. External approvals,
37 generic case bindings, full operational setup and measured evaluation remain
explicit unfinished team deliverables; no false whole-team completion is claimed.

## Reviewed branch push — 9 November 2026

User explicitly authorized review/fixes and commit/push to the current branch,
then clarified that waiting for CI before pushing is optional. Continue on
`jaineel/j03-telemetry`, initially `6e1e633`; ordinary `git fetch origin` confirms
the branch is seven commits ahead of its remote, with no remote-only commits.
Do not rewrite history or push another teammate's branch.

Review fixes in this pass:

- `projectctl/provider_validation.py`: reject non-object receipts/surfaces/entries,
  non-integer schema versions and non-list reviewer declarations as explicit FAIL
  results instead of allowing a malformed file to escape the compatibility check.
  Extend the existing approval-corruption test with six malformed-shape cases.
- `configs/evaluation_profiles.json`, `projectctl/evaluation_packet.py`, and the
  existing team-handoff test: record SQL caps on each process and derive service
  totals from them. Preserve M1's existing three API/audit plus one relay split
  (four total), catalogue 4+2+1, M3 4+1 each and M4 12 sink+2 publisher/relay+2 API.
  P33 worker caps are 6/4/4; API remains two. CPU/RAM allocations are unchanged.
- `benchmarks/manual/verify_prompt6.py` and its existing environment-isolation
  test: scrub the new owner-runtime, contract-review, analytics-review and
  performance-review variables so local deployment inputs cannot affect CI.
- Add `docs/jaineel/TEAM_MESSAGES_2026_11_09.md` with copyable messages and paths
  for Harsh, Vichitr and Aditya. Update the teammate runbook's committed-source
  instructions and exact SQL environment caps; preserve historical evidence.
- Include the pre-existing `.github/workflows/offline.yml` artifact-upload fix
  in this authorized push. Its four-line diff is unchanged from the start of
  the task: collect direct volume logs without traversing private pytest trees.

Verification commands (`PY=.venv/Scripts/python.exe`, all from repo root):

| Exact command/check | Actual outcome | Evidence |
|---|---|---|
| `PY -m benchmarks.manual.verify_prompt6 --job offline --out artifacts/jaineel/push-review-20261109/offline-windows` | **PASS, exit 0: 1,700 passed / 529 skipped / 2,229 collected, zero failures/errors.** This complete Windows offline run started before the follow-up review fixes; final changes are covered by the focused run below | `artifacts/jaineel/push-review-20261109/offline-windows/{checks,summary}.json`, raw logs and `pytest.xml` |
| `PY -m pytest -q tests/contracts/test_provider_validation.py tests/projectctl/test_team_handoff.py tests/projectctl/test_runtime.py tests/benchmarks/test_prompt6_ci.py tests/benchmarks/test_analytics_recheck.py tests/benchmarks/test_pipeline_audit.py tests/benchmarks/test_quality_lifecycle.py --basetemp=artifacts/pytest-push-review-final-20261109 --junitxml=artifacts/jaineel/push-review-20261109/focused-final.xml` | **95 passed**, zero failures/skips, 11.37 s, on the final reviewed code. Earlier overlapping focused pass: 95 passed, `focused.xml` | `artifacts/jaineel/push-review-20261109/focused-final.xml` |
| `PY -m ruff check projectctl benchmarks services/conversation shared/telemetry dashboards tests/conversation tests/contracts tests/projectctl tests/benchmarks tests/oracles tests/telemetry tests/integration` | Exit 0 | Session transcript |
| `PY -m ruff format --check` with that same path list | Exit 0, **200 files already formatted** | Session transcript |
| `PY -m projectctl.schemas --check`; `PY -m projectctl.conversation_contract --check`; `git diff --check` | All exit 0; schemas/current OpenAPI unchanged | Session transcript |
| `git diff --quiet -- uv.lock pyproject.toml services shared/contracts infra migrations contracts/events contracts/data/catalog contracts/dictionaries/catalog configs/evaluation.yaml` | Exit 0; no provider implementation, public DTO, canonical config/specification or dependency lock changed | Session transcript |

Counts overlap; do not sum them as unique tests. The 529 skips are retained
service/platform/source/model opt-ins, not new exclusions. Contract review still
reports dependency NOT_RUN until actual owner receipts exist. No assertions were
weakened and no fake owner approval, real integration or performance pass is claimed.

No Linux/PostgreSQL/Kafka/volume job was run locally in this follow-up: Docker
Desktop remains stopped and the laptop had about 2 GiB free RAM. The user explicitly
allowed pushing without waiting for those CI phases. The existing workflow runs
automatically on push; a hosted result is not inferred from local software checks.
No final evaluation, performance matrix, live fault, reset or deployment was run.

Commit only the reviewed source/tests/config/docs and the retained workflow fix;
do not stage ignored evidence, packets, raw CSV or credentials. The actual commit
and remote branch equality are recorded after the ordinary push in
`artifacts/jaineel/push-review-20261109/git-receipt.json`. Fresh packet generation
and verification after committing use a new ignored directory, preserving the
older now-stale packets. None of these packets approves the remaining owner gates.

Send the three copyable messages from `docs/jaineel/TEAM_MESSAGES_2026_11_09.md`.
Harsh reviews source/dictionary/manifests/queries and supplies catalogue/layout
bindings; Vichitr reviews runtime/audit mappings and enforces counted deployment/
clock/collector inputs; Aditya supplies M3 migration/runtime/seed/snapshot/fault
bindings. All required remaining cases stay explicit until real callbacks and
owner-reviewed evidence exist. The final measured report remains NOT_RUN.

## Connected prototype client checkpoint — 10 November 2026

**Status: client implemented and verified; real prototype/provider acceptance
NOT_RUN.** User requested Vichitr's connected demonstration handoff: search →
selection → cart → authoritative quote display → explicit confirmation → checkout
→ final order status. The current checkout already contains merged PR #15 at
`453a190111b3eb257073404032364a2c11ce6559`. Starting status/diff was clean on
`jaineel/j03-telemetry`; created the small feature branch
`jaineel/prototype-demo`. No commit or push was requested or performed.

Read ownership, Jaineel's brief and relevant common/context/dataset/evaluation
specifications. This checkpoint implements the M1/M0 client only. Harsh's search
repair and Aditya's transaction/setup/authentication work remain with their
owners. No canonical DTO, public API, frozen deadline, dependency lock, provider
implementation or infrastructure configuration changed.

Changed paths:

- `projectctl/demo.py`: runnable interactive fixed-mode client, also exposed
  through `python -m projectctl demo`. Uses canonical OpenAPI validation and
  RequestContext. Displays numbered real hits, selection/quantity, exact quoted
  lines/total, cart version and UTC expiry. Only `CONFIRM <quote-id>` records
  explicit purchase confirmation. There is no auto-confirm/model option.
- `projectctl/cli.py`: adds the demo entry point without changing provider or
  evaluation command dispatch. M1 calls use a 5-second **client** response timeout
  so its existing 3-second turn budget can finish; Orders reads use 2 seconds.
  Backend catalogue and turn limits remain 2 and 3 seconds respectively.
- `tests/projectctl/test_demo.py`: explicit HTTP doubles with canonical schemas;
  success/cancellation, missing confirmation, no results/clarification, stable
  retries across session/cart/quote/checkout response loss, resume after expiry,
  stale cart, changed principal, malformed hits, zero-model policy, conflict,
  definitive expiry rejection and manual-review coverage.
- `tests/conversation/test_demo_process.py`: the client runs through an actual
  loopback M1 process and isolated PostgreSQL schemas, including accepted-provider
  response loss. Catalogue/Orders acceptance and order finality are explicitly
  doubled. Both terminal statuses, one durable confirmation, one checkout command
  and a persisted zero-call turn are asserted; this is not a real M3 saga pass.
- `docs/jaineel/PROTOTYPE_DEMO.md`, `projectctl/README.md`, root `README.md`:
  copyable startup/demo/resume instructions, failure interpretation and owner
  acceptance checks. This progress entry records the checkpoint and limitations.

Client state is atomically replaced/flushed before mutation dispatch. It retains
namespace/user/run/correlation/session identity, cart version, quote, confirmation,
exact business input, request ID and key. At most two automatic retries preserve
that same input/identity. Pending checkout recovery does not reinterpret expiry
as proof that no purchase occurred. Only a definitive `409 QUOTE_EXPIRED` permits
requote plus fresh human confirmation. Completed dependency-error turns use a new
turn identity for the next user search. Order polling validates identity, exact
immutable quote contents and monotonically increasing versions. Unresolved or
manual-review outcomes remain exit 4. Raw HTTP response bytes and timings are
retained beside the ignored local state. Exclusive locks prevent concurrent use.

Verification (all from repository root; `PY=.venv/Scripts/python.exe`):

| Exact command/check | Actual result | Evidence |
|---|---|---|
| `PY -m pytest tests/projectctl/test_demo.py tests/projectctl/test_cli.py -q -o cache_dir=artifacts/pytest-cache-demo --basetemp=artifacts/pytest-demo-client-release-20261110 --junitxml=artifacts/jaineel/demo-20261110/client-release.xml` | **71 passed**, no failures/errors/skips, 47.12 s | `artifacts/jaineel/demo-20261110/client-release.xml` |
| With isolated `P6_TEST_DATABASE_URL`: `PY -m pytest tests/conversation -q --tb=short --basetemp=artifacts/pytest-demo-postgres-20261110 --junitxml=artifacts/jaineel/demo-20261110/m1-postgres.xml` | **413 passed**, no failures/errors/skips, 91.53 s. Existing dependency/JUnit warnings and a local pytest-cache permission warning remain visible | `m1-postgres.xml`, `m1-postgres.log` in the same evidence directory |
| After the final client expiry/requote refinement, with the same isolated URL: `PY -m pytest tests/conversation/test_demo_process.py -q --tb=short -o cache_dir=artifacts/pytest-cache-demo --basetemp=artifacts/pytest-demo-process-release-20261110 --junitxml=artifacts/jaineel/demo-20261110/m1-process-release.xml` | **2 passed**, no skips, 6.51 s; overlaps the full M1 run above | `m1-process-release.xml`, `m1-process-release.log` |
| `PY -m ruff check projectctl/demo.py projectctl/cli.py tests/projectctl/test_demo.py tests/conversation/test_demo_process.py`; `PY -m ruff format --check` with the same four paths | Both exit 0; four files formatted | `final-checks.json` |
| `PY -m projectctl.conversation_contract --check`; `git diff --check` | Both exit 0; canonical M1 contract unchanged | `final-checks.json` |
| `git diff --quiet -- infra services/catalog services/orders services/inventory services/payments shared/contracts shared/outbox shared/event_transport migrations docs/specs uv.lock pyproject.toml` | Exit 0; other owners' code and shared contracts untouched | `final-checks.json` |
| `PY -m projectctl demo --help` | Exit 0; runnable command/options displayed | Session transcript |
| `PY -m projectctl demo --state artifacts/jaineel/demo-20261110/unavailable/state.json --namespace dev --user-id demo-probe --query shirt` | **Expected exit 4**: actual API connection unavailable; exactly two same-key retries, retained session request, no invented completion | `unavailable-cli.json`, `unavailable-cli.log`, `unavailable/state.json.http.jsonl` |
| `$env:PROJECTCTL_ADAPTER_MODULE='infra.prototype'`; `PY -m projectctl env verify --profile prototype-local` | Application summary **exit_code 4, NOT_RUN**: `schema-prerequisites` failed with ConnectionTimeout. This PowerShell wrapper returned 1. No real checkout inferred | `artifacts/projectctl/eee9c3f0-11e3-4648-8e0d-5a9957e5e23a/`, linked startup diagnostics |

`artifacts/jaineel/demo-20261110/verification.json` indexes the final JUnit counts
and explicit live NOT_RUN states. Earlier failed/overlapping trials were retained:
the initial new-client test run had one fixture selector counting both session
creation and its turn URL; its corrected selector still requires all four exact
same-key mutation deliveries and one effect. No product assertion was weakened.

Docker Desktop was initially stopped. Started it hidden for verification, then
created only an isolated 512-MiB PostgreSQL test container using the existing
P6 harness's generated Compose document and the existing pinned PostgreSQL 18 /
pgvector image in `infra/images.lock.json`. Setup files and credentials remain
private under `artifacts/jaineel/demo-20261110/postgres/`; never copy them into Git
or chat. Per-test owned schemas are removed by the existing fixture. The generated
test container is stopped at the end; its volume/evidence are retained. This
setup is not the complete prototype deployment.

Additional read-only diagnosis used the existing catalogue normalizer/artifact
builder on the actual local CSV to obtain the observed API facet dictionary,
then timed M1 extraction for three simple queries. Saved SHA/counts and raw
measurements in `observed-facets.json` / `intent-before.json`: roughly 31–63 ms.
This is a parser diagnostic, not search latency, catalogue-import validation,
streaming throughput or a performance result. It gives no basis for changing
M1's turn deadline. Docker VM budget inspection passed (8,141,934,592 bytes,
12 CPUs; prototype ceilings 3,584 MiB plus 256 MiB headroom); the complete local
prototype was not started. The host had about 1.2 GiB free at the last check.

Remaining handoffs / manual verification:

1. On the already prepared deployment, use the exact retained namespace and run
   the new CLI. Harsh must fix/verify the reported real eligible-count HTTP query
   failure without changing its contract or 2-second timeout. Do not hide it by
   bypassing search with a hardcoded SKU. This checkout has no running prototype
   application endpoints/private prototype bindings, so that provider result is
   **NOT_RUN**, not an observed fix or a newly measured 503.
2. Aditya must complete the repeatable M3 setup, new-order quote-expiry checks,
   status/SSE ownership and internal-token checks, then resolve any actual saga
   terminal-state blocker. M1 consumes the existing public contracts and keeps
   the original checkout identity on uncertainty; no M3 replacement was added.
3. Follow `PROTOTYPE_DEMO.md`: exercise one terminal checkout, resume the same
   completed state (same order), and decline confirmation in a fresh session
   (no checkout). Preserve the real HTTP evidence. Real transaction conservation,
   payment ledger reconciliation, event delivery and active Gold remain **NOT_RUN**
   here and require the existing G3 harness/owner evidence.

For this basic connected-demo milestone, a web UI, live LLM, real bank integration,
additional data ingestion and a benchmark matrix are unnecessary. Existing
prototype setup plus the named owner fixes and an actual live smoke are required.
Stop at this checkpoint; do not claim a full release or measured DE baseline.

## Live prototype startup and checkout correction — 10 November 2026

The user correctly requested fixing the local database/startup failure rather
than ending with doubled-provider evidence. The earlier demo-client checkpoint's
**live checkout NOT_RUN is superseded by a real CONFIRMED checkout below**. Its
earlier raw evidence remains unchanged. Full-team correctness/performance gates
are still separate.

Starting tree was clean on `jaineel/prototype-demo`, HEAD `52d8d78` (`demo entry
point`, committed between turns). Re-read ownership and the prototype runbook.
No commit/push was requested or performed in this follow-up. Changed source paths
are `projectctl/demo.py`, `tests/projectctl/test_demo.py` and these Jaineel-owned
runbook/progress documents. All provider source, migrations, canonical DTOs and
infrastructure configuration remain unchanged.

Root cause and local setup:

- The previous command was `env verify` while the prototype infrastructure was
  stopped. Verification does not start a database. Running the existing
  `infra.prototype` **env up** restored PostgreSQL, Kafka and Registry and fixed
  connectivity. It then correctly reported missing tables: every operational
  service database on this machine was empty. Read-only preflight facts are in
  `artifacts/jaineel/live-demo-20261110/prerequisites.json`.
- Applied the existing M1 `Database.migrate()` and Harsh's existing
  `migrate_catalog()` with each service's own generated connection string.
  For the verified-empty Orders, Inventory and Payments databases, executed
  their existing `migrations/<service>/*.sql` in filename order, each service's
  complete SQL set in one transaction. The one-time bootstrap refused a database
  with any existing public table. No SQL was modified or invented. SQL paths and
  exact-byte SHA-256 values are preserved in `bootstrap.json`. Aditya's requested
  repeatable migration participant remains his deliverable; this local bootstrap
  does not claim that coordinator exists or apply SQL to a nonempty database.
- Built the existing locked image with `infra.prototype.build_image()`. Used the
  documented Linux `prototype-setup` helper for real catalogue import, catalogue
  verification, Inventory seeding and the SKU-manifest copy. Import promoted
  **19,998 canonical / 19,920 active / 78 inactive** rows; catalogue verification
  passed **19 assertions**. Inventory seed completed **19,920 SKUs, zero skipped**.
  These are actual local setup facts, independent of Vichitr's earlier machine.
- Retried the normal `env up`; **all 12 containers were healthy** with their
  existing enforced limits. No reset, volume deletion, sample replacement,
  provider source edit or timeout relaxation was used. The development deployment
  is retained running for the user's demo.

The first live CLI attempt found a genuine Windows client issue. The verification
driver briefly read the saved state while the client atomically replaced it;
Windows returned `PermissionError` / `winerror=5`. A separate held-reader probe
reproduced that exact behavior and succeeded immediately after the reader closed
(`state-sharing-before.json`). `Journal.save()` now retries only that rename for
Windows sharing/access-denied codes 5/32/33 at 50/100/200 ms, keeping the identical
flushed snapshot. Permanent/non-Windows errors still fail. No HTTP mutation is
dispatched before the state save succeeds. Added a real Windows held-reader test
and a persistent-permission-failure test that asserts zero HTTP requests.

Actual connected verification:

- Ran the real CLI search `shirt` through M1, returning five actual catalogue
  hits. Its saved turn reports **0 LLM calls**, parse 583.25 ms, search 998.14 ms
  and total **1,618.50 ms**. These are one local smoke observations, not latency
  quantiles or a performance conclusion. The 2-second catalogue and 3-second
  turn limits are unchanged. Raw response is in `first-probe/state.json`.
- Resumed that actual user/session/cart, selected result 1 and quantity 1. The
  initial quote expired during diagnosis; the CLI correctly required `REQUOTE`,
  displayed a new authoritative quote for **80,500 INR minor units** and required
  `CONFIRM 1da2f9b4-f915-4ebd-8d67-132d56d5ee3e`. The subprocess driver supplied
  this explicit control only after checking the actual quote lines/currency/
  amount/cart version for the user-authorized simulated checkout test. The CLI
  still exposes no automatic-confirmation option. The quote/control are retained
  in `explicit-test-confirmation.json`.
- Real Orders accepted order **`4b028b67-1689-419b-977b-e5ba431dd60e`**. The CLI
  observed PENDING v1 → RESERVING v2 → COMMITTING_STOCK v4 → **CONFIRMED v5**;
  polling may legitimately miss an intermediate version. Exit 0, `phase=done`.
  See `checkout-cli-retry.log`, `checkout-cli-retry.json` and the full HTTP journal
  beside `first-probe/state.json`. M1/catalogue/Orders/Inventory/Payments were all
  real services; the payment provider is the project's real simulator, not a
  test replacement, external bank or real-money purchase.
- Public/internal read-only APIs independently verified the exact order identity,
  immutable quote lines/total, **COMMITTED** reservation, stock **10,000 → 9,999**
  with **reserved=0**, and **one DEBIT / net 80,500 INR minor units** for this order.
  Raw receipts: `opening-stock.json` and `transaction-receipts.json`.
- Reopened the completed CLI state: exit 0, same CONFIRMED order, no new purchase.
  Also POSTed the saved checkout body with its original request ID/key **after
  quote expiry**; M1 returned HTTP 202 with the **same order ID** (the original
  acceptance snapshot still says PENDING, correctly followed by current Orders
  status for finality). See `resume-completed.log` and `checkout-replay.json`.

Exact command/evidence record (all from repo root; `PY=.venv/Scripts/python.exe`):

| Command/check | Actual result | Evidence |
|---|---|---|
| `$env:PROJECTCTL_ADAPTER_MODULE='infra.prototype'`; `PY -m projectctl env up --profile prototype-local` | First run exit 4 naming every empty service schema; infrastructure connectivity restored | `artifacts/projectctl/957279eb-1b55-4c87-8e58-baa6837645f0/` |
| Existing `Database(...).migrate()`, `migrate_catalog(tx)` and unchanged M3 SQL, only after read-only empty-table preflight | All applied successfully through owning database credentials | `bootstrap.json` |
| Existing helper: `docker compose ... run --rm --no-deps prototype-setup python -m projectctl catalog import --source data/raw/flipkart_com-ecommerce_sample.csv --rules flipkart-v1 --load-mode copy --namespace dev --out prototype-volume/prototype-data` | Application exit 0; canonical digest `d87f57e638ee1ab75743338516c4cfc1a2acfcc68d8f5493f828e7cfeb9e2bba` | `catalog-import.log`; host setup evidence `artifacts/prototype-setup/projectctl/89db2187-dd34-4620-936e-e3effaf784a2/` |
| Same helper: `python -m projectctl catalog verify --namespace dev --manifest prototype-volume/prototype-data/normalized_manifest.json` | Exit 0; 19 assertions verified | `catalog-verify.log` |
| Same helper: `python -m projectctl inventory seed --namespace dev --sku-manifest prototype-volume/prototype-data/sku_manifest.json --profile performance --seed 42` | Exit 0; 19,920 seeded, zero skipped | `inventory-seed.log` |
| Normal prototype `env up` after existing schema/data setup | Exit 0; 12 healthy containers | `artifacts/projectctl/072723a1-4130-4120-982b-3265c8e627d1/` and linked `prototype.json` |
| `PY -m projectctl demo --state artifacts/jaineel/live-demo-20261110/first-probe/state.json --namespace dev --user-id live-demo-probe --query shirt` | Real search succeeded; deliberately left at selection before purchase | `first-probe.log`, `first-probe.json` |
| `PY -u -m projectctl demo --resume artifacts/jaineel/live-demo-20261110/first-probe/state.json --wait-seconds 120` with explicit test inputs `REQUOTE`, then exact displayed `CONFIRM <quote-id>` | **Exit 0, real CONFIRMED order**; original failed Windows-sharing attempt retained separately | `checkout-cli-retry.log`, `checkout-cli-retry.json` |
| `PY -m projectctl demo --resume artifacts/jaineel/live-demo-20261110/first-probe/state.json` | Exit 0; same CONFIRMED order | `resume-completed.log` |
| `PY -m pytest tests/projectctl/test_demo.py -q -o cache_dir=artifacts/pytest-cache-live-demo --basetemp=artifacts/pytest-live-demo-retry-20261110 --junitxml=artifacts/jaineel/live-demo-20261110/client-retry.xml` | **22 passed**, zero failures/skips, 45.32 s, including the actual Windows file-sharing regression | `client-retry.xml` |
| `PY -m pytest tests/projectctl/test_cli.py -q -o cache_dir=artifacts/pytest-cache-live-demo --basetemp=artifacts/pytest-live-demo-cli-20261110 --junitxml=artifacts/jaineel/live-demo-20261110/cli.xml` | **51 passed**, zero failures/skips, 35.41 s | `cli.xml` |

All filenames without a prefix above live in the ignored
`artifacts/jaineel/live-demo-20261110/` directory. No credential, internal token,
raw dataset or generated result is added to Git. `live-summary.json` records the
single-order real smoke and its explicit wider-pipeline limitations.

The local initial 19,920-stock event catch-up is independently tracked; the CLI
smoke selected an already-projected SKU, checked its actual opening stock and let
Inventory authoritatively recheck it. This does **not** assert full projection
readiness. At 13:17:20 UTC the read model had 8,909 stock rows, Inventory had 2,100
unpublished events and Silver had 5,344 events. The order and payment outboxes
were already empty. The first active-Gold `order_fact` read was HTTP 200,
generation 49, no rows yet. These backlog/visibility observations remain explicit
in `catchup-observation.json` and `gold-order-fact.json`; they are not a G3 Gold
pass or performance measurement. Full catch-up results are appended below once
the ongoing declared readiness check completes.

Closing live results for this follow-up:

- The original `projection wait ... --timeout-seconds 600` returned application
  exit 4 at **10,291 / 19,920** rows, deferred 0. Preserved failure:
  `artifacts/projectctl/c54ea71e-e614-45b0-9c3e-d6b0ff7ee62f/`. This initial import
  catch-up exceeded the chosen readiness window; it was not reported as a pass.
- Continued the same existing read-only readiness command with an explicitly
  declared **1,200-second setup wait**, without changing its membership assertions,
  any production timeout or service allocation. It completed **exit 0**:
  **expected=19,920, projected=19,920, deferred=0**. Evidence:
  `artifacts/projectctl/6bae562e-0611-4a2c-a1a3-9d144a99102a/`. This is an
  initialization check, not a latency/throughput experiment or changed M1 deadline.
- After full projection, ran a new actual CLI session:
  `PY -m projectctl demo --state artifacts/jaineel/live-demo-20261110/full-projection-no-confirm/state.json --namespace dev --user-id live-demo-no-confirm --query shirt`,
  supplying selection 1, quantity 1 and an empty confirmation. **Exit 0**, five
  genuine hits, a displayed INR 549.00 quote, **zero checkout requests / no order**,
  fixed **LLM calls=0**, turn total **1,340.20 ms**. The script explicitly asserts
  `phase=confirm`, search success, zero LLM calls, no checkout operation and no
  order ID, so leaving early at a failed/empty search cannot count as a pass.
  Raw log/receipt: `full-projection-no-confirm.{log,json}`.
- `PY -m projectctl env verify --profile prototype-local` now returns **exit 0**,
  with all 12 containers healthy. Evidence:
  `artifacts/projectctl/c105560c-b45c-494f-ac30-224e514527d3/`.
- Read the purchased SKU through the **public catalogue product API** after
  catch-up. Its projected stock is **on_hand=9,999, reserved=0, available=9,999,
  stock_version=3**, matching Inventory. This proves the real stock-event path
  for this checkout rather than relying only on the M3 receipt. Saved full
  product/stock response: `catalogue-stock-after-checkout.json`.
- Rechecked the payment ledger after replay: still exactly one DEBIT of 80,500
  minor units for the same order. `ledger-after-replay.json` includes the actual
  check time and expired quote timestamp.
- Closing Ruff check and format check of `projectctl/demo.py` and
  `tests/projectctl/test_demo.py`, `git diff --check`, and the protected-provider
  diff check all returned **exit 0**. The latter includes `services/conversation`
  as well as M2/M3/M4/infra/contracts/migrations/lock/spec paths; only the owned
  host CLI, its tests and documentation changed.

The basic connected demo is **real verified** for this local prototype, including
the terminal order, independent payment/stock receipts, same-key replay, complete
stock projection, current catalogue stock and no implicit purchase. The live
services and retained data are left running so the user can immediately use the
documented CLI. No additional UI, model call, service or fake provider was needed.

The broader analytics gate is still separate: the last `order_fact` Gold read
was HTTP 200 / generation **132**, with this order not yet visible while the
fresh seed's analytics backlog continued. `gold-order-fact-final.json` preserves
that actual response. `live-summary.json` explicitly records Gold as
`NOT_VISIBLE`, not passed. No claim is made that the entire initial seed is in
Gold, that the full G3 reconciliation gate passed or that a performance baseline
was measured. The existing healthy analytics worker continues catching up; no
owner reducer/publication implementation or assertion was changed to hide lag.

## Final demo review, authorized push and Docker cleanup — 10 November 2026

User explicitly requested completing any remaining fixes, pushing on the same
branch and cleaning Docker containers. Started with the four previously reviewed
modified paths on `jaineel/prototype-demo`, HEAD `52d8d78`, equal to its remote.
`git fetch origin` succeeded. `origin/main` had only merge commit `96c2784` for
PR #16; its tree already contains the existing demo commit, so no provider merge,
cherry-pick, history rewrite or branch change was needed.

Reviewed the complete client, Windows state-save retry, tests, API usage, owner
boundaries and demo instructions. No further implementation error was found.
The final change contains only `projectctl/demo.py`,
`tests/projectctl/test_demo.py`, `docs/jaineel/PROTOTYPE_DEMO.md` and this progress
file. The implementation fix is the bounded Windows atomic-rename retry already
described above, with actual sharing-failure and fail-before-dispatch coverage.

Pre-push verification (`PY=.venv/Scripts/python.exe`, repository root):

| Exact command/check | Actual outcome | Evidence |
|---|---|---|
| `PY -m benchmarks.manual.verify_prompt6 --job offline --out artifacts/jaineel/demo-push-20261110/offline-windows` | **PASS, exit 0: 1,756 passed / 542 skipped / 2,298 collected**, zero failures/errors. Pytest 262.13 s. Lint, format, generated schemas and M1 contract checks all passed | `artifacts/jaineel/demo-push-20261110/offline-windows/{checks,summary}.json`, raw logs and `pytest.xml` |
| With the separately recreated isolated PostgreSQL test database: `PY -m pytest tests/conversation -q --tb=short -o cache_dir=artifacts/pytest-cache-demo-push --basetemp=artifacts/pytest-demo-push-postgres-20261110 --junitxml=artifacts/jaineel/demo-push-20261110/m1-postgres.xml` | **413 passed**, zero failures/errors/skips, 95.86 s; existing Starlette/JUnit warnings retained | `m1-postgres.xml`, `m1-postgres.log`, `postgres-startup.log` in the same evidence root |
| `git diff --check`; protected-provider diff check from the preceding checkpoint | Exit 0; no provider implementation, canonical DTO/specification, infrastructure config, migration or dependency lock changed | Session transcript |

The offline job's 542 skips explicitly preserve service/platform/source opt-ins;
they are not real passes. The separate PostgreSQL run uses actual PostgreSQL and
declared provider/event doubles. Its cases overlap the offline collection; counts
must not be summed as unique tests. Contract compatibility remains a correctly
recognized dependency `NOT_RUN` (exit 4), without invented owner-review receipts.
The real demo/receipt/stock-projection results above remain independently valid.

The delayed analytics result also completed before shutdown. The active Gold
`order_fact` API returned the real order **CONFIRMED v5** in generation **205**.
Independently asserted order/quote/user/session identity, INR currency and exact
**80,500 minor-unit** total against the retained client quote. Silver contains
**19,920 STOCK_UPDATED**, **one ORDER_CREATED**, **one ORDER_CONFIRMED**, and
**one PAYMENT_SUCCESS** for this one-order local run. Raw API response and actual
Silver counts are in `gold-before-cleanup.json`; assertions/scope are in
`gold-reconciliation.json`. This closes the preceding `NOT_VISIBLE` observation
for this order, without rewriting its historical raw response or claiming the
complete formal G3/fault suite or a performance baseline.

Docker cleanup was restricted to this workspace's prototype Compose project
`group3-postgres-local` and the isolated test project
`demo-check-2e528e98c25c`. Captured and checked their exact container labels/names
and mounted volumes before removal (`cleanup-before.json`). Executed:

1. `$env:PROJECTCTL_ADAPTER_MODULE='infra.prototype'`; `PY -m projectctl env down`
   — **exit 0**, orderly stop; evidence
   `artifacts/projectctl/69a11d0f-5f40-481d-8cf4-1e7c3a3c1223/`.
2. Existing `infra.prototype.compose('rm','--force',*APPS)` for the already stopped
   nine app containers, then existing
   `infra.streaming.compose('down','--timeout','30')` for the infrastructure.
3. `docker compose --project-name demo-check-2e528e98c25c --file artifacts/jaineel/demo-20261110/postgres/compose.json down --timeout 10`
   — **exit 0**, isolated test container/network removed.
4. Verified **13 containers removed, zero containers remaining**, and all
   **seven original mounted volumes retained**, including PostgreSQL, Kafka,
   lakehouse and isolated-test data. No `--volumes`, image removal or global prune
   was used. Credentials, raw evidence and local bindings remain unchanged.
5. With no other containers remaining, `docker desktop stop --timeout 60`
   completed **exit 0** to release the Docker VM's resources.

Exact cleanup outputs and retention assertions are in `cleanup-commands.json`
and `cleanup-after.json`. The runbook now records the successful Gold result and
current stopped state. For the next demo, start Docker Desktop and run the
documented prototype `env up`, `env verify`, then `projectctl demo`; do not repeat
import/seed/reset on the retained prepared data.

Commit/push only the four reviewed paths to `jaineel/prototype-demo`. The actual
new commit, normal push result and final local/remote equality are recorded after
publication in `artifacts/jaineel/demo-push-20261110/git-receipt.json`, avoiding a
self-referential commit hash in this file. No ignored evidence, dataset,
generated runtime file or credential is staged. Hosted CI is separate from these
local results and is not claimed as passed before observing it.

## Related-Markdown audit and remaining owned fixes — 10 November 2026

User requested checking all related Markdown for unfinished personal work,
implementing the remaining work and pushing on the same branch. Started from
clean `jaineel/prototype-demo`, local/remote HEAD `9446c80`. The newer
`origin/main` revision `b6fda7c` only adds the PR #17 merge of that work; no
provider source change or branch switch was needed.

Reviewed **42 tracked related Markdown sources / 12,339 original lines**, the
current implementation and retained evidence. The exact source inventory,
byte hashes, headings and pending references are saved in
`artifacts/jaineel/pending-audit-20261110/markdown-inventory.json`.
[PENDING_WORK_AUDIT_2026_11_10.md](PENDING_WORK_AUDIT_2026_11_10.md) records the
J01–J07 responsibility register, interpretation of historical checkpoints and
the exact remaining handoffs. This audit does not turn historical absent-provider
claims into instructions to rebuild existing services.

Implemented two independent owned gaps:

- **Transaction workload identity/outcomes:** repeated named templates previously
  produced only two scenario IDs across 6,600 purchases and could plan 100%
  successes. Version-2 recipes use distinct phase/ordinal/template IDs and seeded
  95-success/5-decline blocks, retaining 100-ms delay. The default plan now has
  **6,600 distinct IDs, 6,270 successes and 330 declines** for both transaction
  workloads. Seeded materialization repeats exactly. Historical v1 recipes
  reconstruct their original bytes/records; new logical hashes prevent silent
  comparison of old and corrected controls. This is a workload-input check, not
  execution of M3's still-pending deterministic payment controls.
- **Exact seed membership:** quality and operational preparation now require
  complete unique catalogue, Inventory and projection SKU lists equal to the
  frozen active manifest. A same-count substituted SKU fails before namespace
  setup or broker creation. A new lazy owned reader reuses the existing
  SELECT-only provider connection with namespace-bound statements and a five-second
  local SQL timeout. Team composition extends the original M4 seed callback,
  preserving its seed namespace, run identity and provenance. Raw snapshots and
  membership proofs are separate artifacts. Review proposals pin the new reader
  and composition; no approval or actual evaluation-role execution is invented.

Changed paths: `benchmarks/{workloads,seed_audit,composition,quality_binding}.py`,
`projectctl/{team_runtime,evaluation_packet}.py`, their component READMEs,
`tests/benchmarks/{test_workloads,test_seed_audit,test_real_composition,test_quality_lifecycle}.py`,
`tests/projectctl/test_team_handoff.py`, `docs/integration_runbook.md`, and owned
`docs/jaineel/{PENDING_WORK_AUDIT_2026_11_10,CODE_HANDOFF,EVALUATION_TEAMMATE_RUNBOOK,implementation_roadmap,p9_performance,progress}.md`.
Provider implementations, canonical DTOs/specifications, migrations, resource
controls and the application lock are unchanged.

Verification uses `PY=.venv/Scripts/python.exe`, from the repository root. Evidence
root below is `artifacts/jaineel/pending-audit-20261110/`:

| Exact command / check | Actual outcome | Evidence |
|---|---|---|
| `PY -m pytest tests/benchmarks/test_workloads.py tests/benchmarks/test_seed_audit.py -q --tb=short -o cache_dir=artifacts/pytest-cache-pending-audit --basetemp=artifacts/pytest-pending-mixture-20261110 --junitxml=artifacts/jaineel/pending-audit-20261110/exact-mixture.xml` | **41 passed**, zero failures/errors/skips, 1.83 s | `exact-mixture.xml` |
| Focused workload, membership, lifecycle, real-composition and team-handoff regression checkpoint | **96 passed**, zero failures/errors/skips, 8.87 s; before the final exact-block mixture refinement above; the full offline job below reruns the final versions | `seed-and-workloads-final.xml` |
| `PY -m benchmarks.manual.verify_prompt6 --job offline --out artifacts/jaineel/pending-audit-20261110/offline-windows` | **PASS, exit 0: 1,784 passed / 542 skipped / 2,326 collected**, zero failures/errors; pytest 262.86 s. Lint, format, generated schemas and M1 contract checks pass | `offline-windows/{checks,summary}.json`, raw logs and `pytest.xml` |
| `PY -m benchmarks.manual.verify_transaction_boundaries --out artifacts/jaineel/pending-audit-20261110/transaction-boundaries` | **exit 1**, seven existing M3 route-policy assertion failures; explicit ASGI/SQL doubles, real integration NOT_RUN | `transaction-boundaries/boundaries.json` |
| With `PROJECTCTL_ADAPTER_MODULE=projectctl.jaineel`, `PROJECTCTL_RUNTIME_MODULE=projectctl.team_runtime`: `PY -m projectctl contracts check --all` | **exit 4**, schemas/endpoints/examples compatible; all six surfaces UNREVIEWED | `artifacts/projectctl/322ff9b9-c106-45fb-9700-7df00213e3ad/` |
| `PY -m projectctl.evaluation_packet --out artifacts/jaineel/pending-audit-20261110/packet-final`; same module with `--verify artifacts/jaineel/pending-audit-20261110/packet-final` | Both **exit 0**, INPUTS_PINNED_REVIEW_PENDING; evaluation NOT_RUN. Packet hash `4928a71453d5ae8c888b291e6fc98e3406b10d5c3cc244535c70df823f32dccb` | `packet-final/` |

The first membership test attempt found a local hash-helper type error (a
dict-only helper received a list); corrected it to SHA-256 of canonical sorted
SKU-list bytes and reran the tests. The original **9 failures / 85 passes** remain
in `seed-and-workloads.xml`. An earlier unstratified payment-plan diagnostic also
remains preserved; `payment-plan-final.json` records the final exact 95/5 plan
with synthetic input clearly labelled. No assertion or required skip was weakened.

The 542 skips retain their explicit service/platform/source opt-in requirements;
they are not integration passes. Prior real PostgreSQL/prototype evidence is
recorded separately above. Repository review confirms **20 changed owned paths**,
`git diff --check` exit 0 and protected provider/specification/DTO/migration/lock
diff exit 0 (`repository-review.json`).

The new packet finds **0/37 generic cases registered**, only
Conversation/Catalogue/Analytics migration participants and no reset participants.
The boundary probe still exposes M3's missing order-status/SSE ownership, internal
audit-token enforcement and fault guards. Aditya owns those provider changes;
the exact failing paths/statuses are retained. Formal correctness, full quality
and benchmark runs remain NOT_RUN until actual provider hooks, input reviews and
the enforced evaluation host are available. Jaineel still owns binding the real
consumer cases and producing measurements/report after those prerequisites. The
full matrix is not authorized by the canonical roadmap before those gates pass.

The earlier real confirmed checkout, single debit, stock/projection and Gold
reconciliation remain valid prototype evidence. Docker was not restarted for this
audit; no container or volume was created or removed. The prior cleanup and stopped
Desktop state are preserved. Manual next verification: affected owners review the
new reader/mappings and templates, complete the handoffs in the audit, then use
`EVALUATION_TEAMMATE_RUNBOOK.md` on the agreed evaluation host. Do not reseed or
reset the retained prototype namespace merely to repeat this offline audit.

Commit/push only these owned reviewed paths on `jaineel/prototype-demo`. Record
the actual normal-push result, final clean status and local/remote commit equality
after publication in the ignored `git-receipt.json` under this audit's evidence
root. Hosted CI remains separate from local execution.


## 11 November 2026 - delegated M3 payment and seed-audit checkpoint

Scope: the user's supplied Aditya handoff explicitly permits Jaineel to edit
M3 services, migrations and transaction tests for this task. The user delegated
review/design decisions and requested **stay on `jaineel/prototype-demo`, do not
push**. Initial working tree was clean at `3be2916` (PR #19 merge). No branch,
commit or push operation is part of this checkpoint.

Read `docs/OWNERSHIP.md`, personal brief 04, Aditya's progress, the current pending
work audit and relevant canonical specs 01/02/03/06/08/09. Detailed decisions,
contract/audit mapping, deployment instructions and limitations are in
[M3_PAYMENT_HANDOFF_2026_11_11.md](M3_PAYMENT_HANDOFF_2026_11_11.md).

Implemented:

- Paired scenario-ID/seed headers through W-CHECKOUT, W-INTEGRATED, M1's durable
  checkout journal, Orders and the saga to Payments. All ingress controls require
  both benchmark flags and an isolated namespace. The client supplies identity;
  Payments computes outcomes. The existing v2 seeded 95/5 rule is reproduced
  independently, without importing the harness into production services.
- Durable PENDING attempts and a 25-ms completion worker, with a persisted minimum
  100-ms due time and transactional payment guard/ledger/shared outbox. Restart,
  response loss, same-attempt retries, concurrent completion and both completion/
  reversal lock orders retain one effect. DECLINED is stable and never retried;
  only RETRYABLE_PROVIDER_FAILURE may allow attempt two while the hold is valid.
- Original order context persists and is restored for saga/participant events;
  the payment worker likewise restores the accepted attempt's original context.
  Only new `003_*.sql` migrations are added; no applied migration is edited.
- Independent read-only seed snapshots now include Inventory's exact keys,
  unpublished namespace outbox count and one original run ID, and reject conflicts
  with owner callback evidence. Harsh's existing Inventory queries are preserved.

Changed paths:

- `services/conversation/{app,clients,workflow}.py`;
  `services/orders/{app,commands,saga}.py`;
  `services/payments/{app,authorize}.py`.
- `migrations/orders/003_payment_context.sql`,
  `migrations/payments/003_async_completion.sql`,
  `shared/telemetry/benchmark.py`.
- `benchmarks/{drivers,integration_clients,seed_audit}.py`.
- `tests/conversation/test_workflow.py`;
  `tests/transactions/{test_checkout_live,test_payment_logic,test_saga_logic,test_saga_enhancements,test_async_payments,test_payment_handoff}.py`;
  `tests/benchmarks/{test_drivers,test_seed_audit}.py`;
  `tests/telemetry/test_benchmark.py`.
- This progress file and `docs/jaineel/M3_PAYMENT_HANDOFF_2026_11_11.md`.

Environment: Docker Desktop was initially stopped/unavailable; started it hidden.
Created only the disposable `jaineel-m3-20261111` PostgreSQL test container on
loopback port 55432 using the pinned
`pgvector/pgvector:0.8.1-pg18-trixie@sha256:2fd905ba95f99a51be207d0ff0b8d5b8538cbce7e9083b3ccfa65b93bb28b938`.
The actual server is **PostgreSQL 18.2**. Tests create/drop their own uniquely
named schemas (and one isolated SELECT-only role), never reset prototype data.

Commands use `uv run --locked` (Python 3.11, unchanged application lock). For
real database commands set `INVENTORY_TEST_DATABASE_URL` to the disposable
PostgreSQL 18 URL; M1 checks also set `P6_TEST_DATABASE_URL` to that same test URL.
Evidence root is `artifacts/jaineel-m3-20261111/`.

| Exact command/check | Actual outcome | Evidence |
|---|---|---|
| `uv run --locked python -m benchmarks.manual.verify_transaction_boundaries --out artifacts/jaineel-m3-20261111/boundaries-before` | PASS, **8/8**, exit 0; explicit ASGI/SQL doubles | `boundaries-before/boundaries.json` |
| `uv run --locked pytest tests/transactions tests/benchmarks/test_drivers.py tests/benchmarks/test_seed_audit.py -q --tb=short --junitxml=artifacts/jaineel-m3-20261111/initial.xml` | Initial transition check: **24 failed, 142 passed, 36 skipped**, exit 1; old synchronous doubles and missing new fixture inputs exposed | `initial.xml` |
| Same focused suites with real PostgreSQL and `--junitxml=artifacts/jaineel-m3-20261111/checkpoint.xml` | **201 passed, 2 failed**, exit 1; fixed incorrect payload-class import in the new test | `checkpoint.xml` |
| `uv run --locked pytest tests/transactions/test_async_payments.py tests/transactions/test_payment_handoff.py tests/transactions/test_payment_logic.py tests/telemetry/test_benchmark.py tests/conversation/test_workflow.py -q --tb=short --junitxml=artifacts/jaineel-m3-20261111/extended.xml` | **132 passed, 6 fixture errors**, exit 1; lint had removed pytest fixture imports, fixed using explicit re-exports | `extended.{log,xml}` |
| `uv run --locked pytest tests/transactions tests/telemetry/test_benchmark.py tests/benchmarks/test_drivers.py tests/benchmarks/test_seed_audit.py -q --tb=short --junitxml=artifacts/jaineel-m3-20261111/transactions.xml` | **233 passed**, zero skips/failures, exit 0 | `transactions.{log,xml}` |
| `uv run --locked pytest tests/benchmarks/test_seed_audit.py -q --tb=short --junitxml=artifacts/jaineel-m3-20261111/seed-audit.xml` | **26 passed**, zero skips/failures, exit 0; includes real SELECT-only credentials, namespace/published filtering and mixed-run rejection | `seed-audit.xml` |
| `uv run --locked pytest tests/transactions/test_saga_logic.py tests/transactions/test_async_payments.py tests/conversation/test_workflow.py -q --tb=short --junitxml=artifacts/jaineel-m3-20261111/final-focused.xml` | **148 passed**, exit 0; includes new pending/decline/retryable/expiry policy and four concurrent completion workers | `final-focused.{log,xml}` |
| Final lint and format across 42 source/test files | PASS; `ruff check` exit 0 and `ruff format --check` exit 0 | exact scopes below |
| `uv run --locked python -m benchmarks.manual.verify_transaction_boundaries --out artifacts/jaineel-m3-20261111/boundaries-after` | PASS, **8/8**, exit 0; explicit doubles | `boundaries-after/boundaries.json` |
| `uv run --locked pytest tests/transactions tests/conversation tests/integration -q --tb=short -o cache_dir=artifacts/jaineel-m3-20261111/pytest-cache-services --junitxml=artifacts/jaineel-m3-20261111/services.xml` | **699 passed**, zero skips/failures, exit 0 (157.65 s); real M1/M3 databases, explicit provider doubles | `services.{log,xml}` |
| `uv run --locked python benchmarks/manual/verify_p5.py` with `PYTEST_ADDOPTS=-o cache_dir=artifacts/jaineel-m3-20261111/pytest-cache-p5` | First attempt: 10/11 checks passed, exit 1; pytest **916 passed / 1 failed** because the temporary cache override interfered with the nested default-cache isolation assertion. Removed that environment override for the final rerun; verifier and assertions unchanged | `p5.log`; `artifacts/p5/018e148c-71f1-4db5-954c-5192dfc77204/checks.json` |
| `uv run --locked python benchmarks/manual/verify_p5.py` with no PYTEST_ADDOPTS override | **PASS, 11/11 checks**, exit 0; **917 passed**, zero skips/failures (163.15 s). The contracts command's missing-provider/review exit 4 is explicitly expected by this verifier; it is not a real integration pass | `p5-final.log`; `artifacts/p5/3175c0ce-6b2f-4f30-a748-794f8569936b/{checks.json,pytest.xml}` |

The redirected PowerShell logs retain native stderr formatting as well as stdout.
A prior focused run warned about an inaccessible default `.pytest_cache`; the service
run uses an explicit writable artifact cache. P5 already supplies its own cache
isolation hooks, so its final rerun uses no PYTEST_ADDOPTS override. No test/assertion is skipped or
weakened to hide a failure. Updated unit doubles assert PENDING creation and
separate completion effects instead of the superseded synchronous behavior.

The real 100-attempt PostgreSQL cohort produced **95 SUCCESS / 5 FAILED DECLINED**
and 95 debits. Stable scenario agreement is checked against all 6,600 logical
workload records for each of three seeds. HTTP success and decline tests exercise
real Orders, Inventory and Payments with a catalogue HTTP double and offline
registry fixture; the original run/correlation/request identities survive the
workers. Minimum delay, restart, response-loss retries, quiescence/reversal races,
and one debit/event under concurrent workers are checked. These are correctness
results for a simulator, not performance measurements or a real payment gateway.

Remaining handoffs: formal G3/T-07/T-08/T-11/reset bindings, acknowledged controlled
failure hooks (including the separate 35-second expiry-delay scenario), exact
broker receipts and full real analytics reconciliation remain open. Hosted CI,
full B0/matrix measurements and an end-to-end Gold run of this new code are
NOT_RUN. A future owner contract update should document the new optional carrier;
no human approval is fabricated. Historical orders without stored origin context
retain their legacy fallback; historical evidence is not rewritten.

Manual next verification: apply `python -m services.orders.m3_setup` with each
service's owning URL before restarting Orders/Payments, configure both flags on
M1/Orders/Payments for isolated benchmark traffic, then use the real provider
composition after its remaining receipt/hook bindings are supplied. Prototype
data is preserved. This session stops at the delegated handoff checkpoint.


Final lint/format scope (42 files, exit 0 for both commands):

```powershell
$checked = @(
  "services/orders", "services/payments", "shared/telemetry/benchmark.py",
  "services/conversation", "benchmarks/drivers.py", "benchmarks/integration_clients.py",
  "benchmarks/seed_audit.py", "tests/transactions/test_async_payments.py",
  "tests/transactions/test_payment_handoff.py", "tests/transactions/test_payment_logic.py",
  "tests/transactions/test_saga_logic.py", "tests/transactions/test_saga_enhancements.py",
  "tests/conversation/test_workflow.py", "tests/telemetry/test_benchmark.py",
  "tests/benchmarks/test_seed_audit.py", "tests/benchmarks/test_drivers.py"
)
uv run --locked ruff check @checked
uv run --locked ruff format --check @checked
```

Final review: `git diff --check` passes. `git diff --name-only -- docs/specs
contracts shared/contracts uv.lock pyproject.toml infra pipelines shared/outbox
shared/event_transport` is empty. Existing migration files have no diff; only
new migrations are present. `repository-review.json` retains all 26 changed
paths, hashes, HEAD and branch; `working.patch` retains the tracked diff. No
commit or push was made; HEAD remains `3be2916a4896aa1693e46410dcafac2eafc4b34c`.

Cleanup: `docker rm -f -v jaineel-m3-20261111` removed only this session's disposable
test container and anonymous test volume. `docker ps --format '{{.Names}}'` was
empty afterwards. `docker desktop stop` exited 0, restoring the initially stopped
state; retained prototype volumes/data were untouched.

## 11 November 2026 — review, real prototype verification and authorized push

This follow-up explicitly authorizes commit/push on the existing
`jaineel/prototype-demo` branch and delegates Jaineel's review/design decisions.
The earlier checkpoint's no-push instruction above is historical. Initial HEAD
is PR #19 merge `3be2916`; all 26 pre-existing changed/untracked handoff paths
were preserved and reviewed. The fetched remote branch is an ancestor (5 ahead,
0 behind before this commit); no branch change, rebase or force push is needed.

The [current review](PROTOTYPE_REVIEW_2026_11_11.md) records the consumed Harsh/
Vichitr mapping decisions, canonical requirements, presentation sequence and
remaining formal-evaluation scope. The [demo runbook](PROTOTYPE_DEMO.md) now starts
PostgreSQL, imports the retained private bindings and applies repeatable M3 setup
before application startup. This is one prototype/payment-handoff checkpoint;
full B0/matrix measurements, missing formal case compositions and human labels
are not represented as completed by a demo or automated consumer review.

Additional fixes made during this review:

- `services/payments/authorize.py`: reversal now establishes and locks the same
  guard as first authorization, inspects attempts after the lock and timestamps
  reversal with the database clock. The new real concurrency regression first
  reproduced the old missing-attempt/retained-debit bug, then passed with one debit
  and one reversal. Updated explicit unit doubles follow the same SQL contract.
- `services/conversation/provider_contracts.py`: use PyYAML's safe C loader when
  available, retaining the safe fallback, strict validation and source drift
  checks. Repeated safe Python YAML parsing consumed the unchanged turn budget
  during real demo searches; no provider/turn timeout was raised.
- `benchmarks/manual/verify_p5.py` and
  `tests/benchmarks/test_verifier_evidence.py`: retain string/byte/absent timeout
  stdout and stderr without crashing, record the failed check and continue. The
  240-second bound and required assertions are unchanged.
- `projectctl/conversation_contract.py`, `contracts/http/conversation.yaml`:
  document the optional paired benchmark identity headers on M1 checkout.
- `docs/jaineel/{PROTOTYPE_DEMO,PROTOTYPE_REVIEW_2026_11_11,PENDING_WORK_AUDIT_2026_11_10,M3_PAYMENT_HANDOFF_2026_11_11,progress}.md`:
  current consumer decisions, upgrade/demo instructions, evidence and historical
  status links. All other changed paths are the handoff list in the prior section,
  including the extended `tests/transactions/{test_async_payments,test_payment_logic}.py`.
  No teammate implementation, shared DTO, existing migration, spec, lock or infra
  configuration was replaced.

Evidence root: `artifacts/jaineel-m3-review-20261111/`. Commands use
`uv run --locked` with Python 3.11.15/uv 0.10.8. Real test connections use
`INVENTORY_TEST_DATABASE_URL=<disposable PostgreSQL 18.2 URL>` and M1 also uses
`P6_TEST_DATABASE_URL` pointing to that same disposable server. Per-test schemas
are isolated. The retained prototype databases/volumes were never reseeded/reset.

| Exact command/check | Actual outcome | Raw evidence |
|---|---|---|
| `python -m benchmarks.manual.verify_transaction_boundaries --out artifacts/jaineel-m3-review-20261111/boundaries-before` and final `--out .../boundaries-final` | PASS, 8/8 each, exit 0; explicit ASGI/SQL doubles | `boundaries-{before,final}/boundaries.json` |
| `pytest tests/transactions/test_async_payments.py::test_reverse_sees_attempt_created_while_creating_its_guard -q --tb=short --junitxml=artifacts/jaineel-m3-review-20261111/race-before.xml` | Expected reproduction: 1 failed on the old reversal path | `race-before.{log,xml}` |
| `pytest tests/transactions/test_async_payments.py tests/transactions/test_payment_logic.py -q --tb=short -o cache_dir=artifacts/jaineel-m3-review-20261111/pytest-cache --junitxml=artifacts/jaineel-m3-review-20261111/payment-fixes.xml` | 24 passed, 1 fixture error; the new test's connection proxy initially omitted psycopg's `info`, corrected by forwarding attributes | `payment-fixes.{log,xml}` |
| `pytest tests/transactions tests/conversation tests/integration tests/benchmarks/test_drivers.py tests/benchmarks/test_seed_audit.py tests/telemetry/test_benchmark.py -q --tb=short -o cache_dir=artifacts/jaineel-m3-review-20261111/pytest-cache --junitxml=artifacts/jaineel-m3-review-20261111/services.xml` | PASS, 743 passed, zero skips/failures, exit 0; 201.76 s | `services.{log,xml}` |
| `pytest tests/contracts tests/benchmarks/test_verifier_evidence.py -q --tb=short -o cache_dir=artifacts/jaineel-m3-review-20261111/pytest-cache --junitxml=artifacts/jaineel-m3-review-20261111/contracts.xml` | PASS, 140 passed, exit 0, after loader/verifier changes | `contracts.{log,xml}` |
| `PROJECTCTL_ADAPTER_MODULE=infra.postgres python -m projectctl env up --profile postgres-local` | PASS, exit 0; retained PostgreSQL started | `postgres-up.log` |
| `python -m services.orders.m3_setup`, twice with the private prototype service URLs | PASS, both exit 0; first adopts/checks all M3 files and adds upgrades, second applies nothing | `m3-setup{,-repeat}.log` |
| `PROJECTCTL_ADAPTER_MODULE=infra.prototype python -m projectctl env up --profile prototype-local` | PASS, exit 0; all real processes healthy, not a workload assertion | `prototype-up.log`; `artifacts/infra/prototype-local/checks/f32eeb35-8588-4581-9265-5217425fc02e/prototype.json` |
| `PYTHONPATH=<repo> python artifacts/jaineel-m3-review-20261111/live_smoke.py` | Corrected scripted real-provider smoke PASS, exit 0; see facts below. Initial cold-search failures and temporary script route/field mistakes are preserved | `live-smoke*.log`, `live-summary.json`, `transaction-audit.json`, `payment-plan.json`, `checkout-replay.json`, `gold-order-fact.json` |
| `@('1','1','') \| uv run --locked python -m projectctl demo --namespace dev --user-id demo-jaineel-review --query shirt --state artifacts/jaineel-m3-review-20261111/fresh-no-confirm/state.json` | PASS, exit 0; fresh search/quote, no checkout after declined confirmation | `fresh-no-confirm.log`, `fresh-no-confirm/state.json{,.http.jsonl}` |
| `python benchmarks/manual/verify_p5.py`, first attempt while the stack was running | Timed out its nested pytest and exposed text-output decoding crash; not counted as PASS. Fixed verifier, retained evidence; no timeout increase | `p5.log`; `artifacts/p5/e5f178e7-2504-48ce-af71-de2ab86dffbf/checks.json` |
| Final service rerun immediately after restarting disposable PostgreSQL | 571 passed, 129 setup errors because the server was still starting. Confirmed readiness with a real SELECT before rerunning; assertions unchanged | `services-final.{log,xml}`, `test-database-ready.log` |
| `python -m projectctl.conversation_contract --check`; `python -m projectctl.schemas --check` | PASS, exit 0; generated contracts match | CLI outputs, `contracts.xml` |

Focused lint and formatting pass on all 46 changed/relevant Python files:
`ruff check` / `ruff format --check` use the handoff scope above plus
`services/conversation/provider_contracts.py`, `benchmarks/manual/verify_p5.py`,
`tests/benchmarks/test_verifier_evidence.py`, `projectctl/conversation_contract.py`
and `tests/transactions/test_checkout_live.py`. Exact outputs are
`lint-final.log` and `format-final.log`. A broader exploratory lint additionally
reported the existing long docstring in unmodified
`tests/transactions/test_event_payloads.py:144`; it was not edited to broaden
this milestone. `git diff --check` and generated schema checks pass.

Real smoke facts: order `0f2f9566-0001-4f4a-a331-d72634e9d152` reached CONFIRMED,
reservation COMMITTED, with one INR 549.00 debit and the same order on replay.
Payment completion is no earlier than its persisted 100-ms due time and retains
the ingress run identity. Foreign-user status/SSE reads return 404 and tokenless
ledger audit returns 401. Active Gold query generation 221 includes the confirmed
order (row publication generation 213). A separate fresh CLI flow submits no
checkout when confirmation is declined. All fixed-mode search turns record zero
LLM calls. Scripted smoke confirmation is explicitly a regression fixture, not
a claim of human review. Formal G3, complete source/receipt reconciliation,
performance qualification and hosted CI remain unclaimed.

The first standalone timeout-regression run had 3 failures due to its mock matching
the word `contracts` inside the protected git-diff path list; corrected the mock
to identify the actual contracts command. All 140 contract/verifier tests pass.
Diagnostic YAML load/profile logs are local investigations, not controlled B0/O1
or cross-machine benchmark evidence.

Cleanup so far: `PROJECTCTL_ADAPTER_MODULE=infra.prototype python -m projectctl
env down` stopped the app/worker/relay stack and base services. Compose down was
followed by removal of the remaining stopped containers selected by the exact
`com.docker.compose.project=group3-postgres-local` label (profiled services are not
all selected by default Compose down). All named database/Kafka/lakehouse volumes,
private bindings and raw evidence remain. The disposable test container is kept
only until final verification completes, then removed separately.

Final service verification after readiness:
`uv run --locked pytest tests/transactions tests/conversation tests/integration
-q --tb=short -o cache_dir=artifacts/jaineel-m3-review-20261111/pytest-cache-final
--junitxml=artifacts/jaineel-m3-review-20261111/services-ready.xml`
completed with **700 passed, zero skips/failures, exit 0 (143.80 s)**. Raw stdout/
JUnit are `services-ready.{log,xml}`. The warnings are existing FastAPI lifecycle
deprecations and JUnit `record_property` format notices; assertions were not
weakened. Together with the contract/verifier run, this verifies the final source
after the parser and timeout fixes. The earlier 743-test run also exercised the
real restricted seed-audit reader and workload-driver handoff.

Final required P5 verification:
`uv run --locked python benchmarks/manual/verify_p5.py` with the disposable
`INVENTORY_TEST_DATABASE_URL` / `P6_TEST_DATABASE_URL` completed with **11/11
checks matched, exit 0; 920 passed, zero skips/failures (146.58 s)**. Evidence:
`p5-final.log` and `artifacts/p5/90f7aea8-d623-4b75-845c-76aadd1251ca/{checks.json,pytest.xml}`.
The contracts command's exit 4 is explicitly expected: provider compatibility is
not a manufactured formal-owner approval. P5's own real-SUT/performance values
remain NOT_RUN; the separately retained real prototype smoke above is the actual
deployment verification. Every requested pre-push check has now executed.

Publication: stage only the 34 reviewed source/test/migration/contract/doc paths;
use `git commit -m "fix: complete deterministic payment handoff and harden prototype"`
and `git push origin HEAD:refs/heads/jaineel/prototype-demo`. The branch is unchanged
and publication is a normal fast-forward. `repository-review.json` records the
reviewed paths/hashes; the ignored `git-receipt.json` records the actual commit,
remote equality, push outcome and final status after publication. Generated/raw
artifacts, datasets, private bindings and credentials are excluded.

Final cleanup completed: `docker rm -f -v jaineel-m3-review-20261111` removed
only the disposable test container and its anonymous volume. `docker ps -a
--format '{{.ID}} {{.Names}} {{.Status}}'` produced an empty file (zero remaining
containers). `docker desktop stop` exited 0, restoring the initially stopped
Desktop state. `retained-volumes.txt` confirms the named PostgreSQL, Kafka and
lakehouse volumes remain; no volume/image prune or prototype-data reset occurred.
Evidence: `test-container-removed.log`, `docker-containers-after.txt`,
`docker-desktop-stop.log`. Manual presentation restart uses the updated demo
runbook; start Docker Desktop first, then run its prepared-machine commands.

Actual publication: source commit **`5dd1838`**, `fix: complete deterministic
payment handoff and harden prototype`, was created on `jaineel/prototype-demo`.
`git push origin HEAD:refs/heads/jaineel/prototype-demo` exited **0**, advancing
the remote from `33ea39e` to `5dd1838` without rewriting history. `git ls-remote
--heads origin refs/heads/jaineel/prototype-demo` matched local HEAD and the work
tree was clean. This final documentation receipt is published as a separate small
commit on the same branch; `git-receipt.json` retains its final local/remote SHA
and clean status. Hosted CI was not polled and is not claimed green by this run.

## 12 November 2026 — Harsh final handoff and professor presentation

User authorized autonomous integration/review decisions and a working professor
prototype. Started with a clean tree at `136e42d` on `jaineel/prototype-demo`;
Harsh's PR #21 was already merged. Read the ownership/specification inputs,
final deployment/data/import/search deliverables, current implementation and
previous pending reviews. Stayed in Jaineel/coordinated paths. No teammate
implementation, migration, public contract, resource limit or lock was changed.

Implemented `projectctl/presentation.py` and CLI `demo-check`: six preflight
checks through public HTTP (three readiness checks, three actual M1 searches),
plus GET-only saved-order observation and exact terminal-version active-Gold
verification. It checks hard filters, positive stock/historical prices, dataset
revision, zero LLM calls, existing turn budget, immutable order identity/totals
and row publication generation. It retains raw responses, failures and polling;
missing Gold is INCOMPLETE. It never submits checkout, alters the original demo
state or silently replaces a failed provider. New directories cannot overwrite
earlier evidence. Regression cases cover unavailable providers, malformed JSON,
incorrect filters/stock/dataset, missing/duplicate/stale/conflicting Gold,
CONFIRMED/CANCELLED, prior-day cohorts and purchase-state preservation.

Decisions and manuals:
`docs/jaineel/HARSH_ACCEPTANCE_2026_11_12.md` accepts the presentation handoff,
existing dataset and raw-byte/LF hash policy under delegated consumer authority;
it does not invent anyone else's review. `PRESENTATION_READY.md` gives the
prepared Windows startup, preflight, five-minute demonstration, Gold observation
and non-destructive stop. Root/projectctl READMEs and current pointers in
`PROTOTYPE_DEMO.md`, `HARSH_REVIEW_2026_11_09.md` and
`PENDING_WORK_AUDIT_2026_11_10.md` link the new decisions. Tests are in
`tests/projectctl/test_presentation.py`; `projectctl/cli.py` only registers and
dispatches the new command. These files plus this progress entry are the entire
source/documentation change set.

Exact execution and evidence under `artifacts/presentation-20261112/`:

| Command/check | Actual outcome | Retained evidence |
|---|---|---|
| `docker desktop start --timeout 60`; `uv sync --locked --python 3.11` | PASS, exit 0; started initially stopped Desktop, reused application lock | Tool outputs |
| `PROJECTCTL_ADAPTER_MODULE=infra.postgres uv run --locked python -m projectctl env up --profile postgres-local`; `python -m services.orders.m3_setup` using private host bindings | PASS, exit 0; all existing M3 migrations verified, none applied | `artifacts/professor-postgres-up.log`, tool migration output |
| `PROJECTCTL_ADAPTER_MODULE=infra.prototype uv run --locked python -m projectctl env up --profile prototype-local` | PASS, exit 0, retained data | `artifacts/professor-prototype-up.log`; launcher checks `a2488deb-ae76-4892-9887-3ada6168aa9e` |
| `uv run --locked python -m projectctl env verify --profile prototype-local` with prototype adapter | PASS, exit 0; all 12 containers healthy with actual limits | `env-verify.log`; launcher checks `36685df7-9573-49cc-a392-3ac06264b8bd` |
| `uv run --locked python -m projectctl projection wait --namespace dev --sku-manifest artifacts/prototype-setup/prototype-data/sku_manifest.json --timeout-seconds 600` | PASS, exit 0; 19,920/19,920, zero deferred | `projection.log` |
| `uv run --locked python -m projectctl demo-check --out artifacts/presentation-20261112/final-source-preflight` | PASS, 6/6, exit 0, final source | `final-source-preflight.log`, directory with checks/state/raw HTTP |
| `PYTHONPATH=<repo> uv run --locked python -u artifacts/presentation-20261112/rehearse.py` | PASS, real providers; scripted simulated purchase, resume, no-confirmation flow and independent read-only transaction snapshots | `rehearsal-verified.log`, `rehearsal.json`, `purchase/`, `no-confirm/`, `transaction-audit.json` |
| `uv run --locked python -m projectctl demo-check --state artifacts/presentation-20261112/purchase/state.json --out artifacts/presentation-20261112/final-source-order` | PASS, exit 0, final source; exact terminal order in active Gold | `final-source-order.log`, checks/raw HTTP and copied observation state |
| `benchmarks.dataset_checks.inspect_source(Path('data/raw/flipkart_com-ecommerce_sample.csv'))`; `projectctl.input_pins.review_input_pins()` | PASS source assertions/checksum/counts and both published LF identities; review proposals remain labelled | `source-check.json`, `input-pins.json` |
| `uv run --locked pytest tests/transactions/test_payment_handoff.py tests/projectctl tests/contracts tests/integration tests/conversation/test_workflow.py -q --tb=short --junitxml=artifacts/presentation-20261112/verification.xml` with private `INVENTORY_TEST_DATABASE_URL` and `P6_TEST_DATABASE_URL` | **529 passed, zero failures/skips, exit 0, 221.65 s** | `verification.{log,xml}` |
| `uv run --locked pytest tests/projectctl/test_presentation.py tests/projectctl/test_demo.py -q --tb=short --junitxml=artifacts/presentation-20261112/presentation-final.xml` after final strict-type/malformed-response guards | **44 passed, zero failures/skips, exit 0, 12.79 s**; overlaps broader run | `presentation-final.{log,xml}` |
| `uv run --locked ruff check projectctl/presentation.py projectctl/cli.py tests/projectctl/test_presentation.py`; matching `ruff format --check`; `python -m projectctl.conversation_contract --check`; `python -m projectctl.schemas --check`; `git diff --check` | PASS | Final CLI output, `source-validation.log` |
| `uv run --locked python -m projectctl contracts check --all` | **exit 4**, expected missing byte-pinned all-owner review receipts; compatibility checks pass | `contracts-check.log`; `artifacts/projectctl/671d54d1-f93a-45df-b189-4472b3c697f8/` |

Tests use explicit doubles where documented. The transaction handoff tests use
real PostgreSQL/HTTP for M3, with explicit catalogue and schema-registry doubles;
they do not constitute a second real full-stack purchase. The separately
recorded prototype rehearsal used all real running provider services. Its
order `8615ea16-c56f-4268-b2a4-7d6976c2f6bb` is CONFIRMED v6 with a COMMITTED
one-unit reservation, exactly one 116,600-minor INR debit, available stock 9,999
with zero reserved, and the matching order in active Gold generation 237.
Fixed-mode calls were zero. Resume sent no new purchase, and the separate
declined-confirmation state contains no checkout operation.

Retained first attempts: `preflight-first/` correctly refused my initial
incorrect health-mode expectation (`real` is execution mode, `fixed` is assistant
mode); all three searches already passed. Corrected the consumer check, without
changing M1. `targeted.log/xml` has 56 passed / 8 skipped before database URLs
were supplied; the 529-test rerun executes those M3 cases without skips.
The ignored rehearsal driver initially used the wrong local operation/audit
field names (`checkout` instead of its indexed identity; `status`/`entry_type`
instead of `state`/`kind`). Those collection failures are in `rehearsal.log` and
`rehearsal-final.log`; the same confirmed order was resumed, never repurchased.
The final collector and source checks pass. Scripted confirmation is a test
input, not a claim of human review.

Harsh's Linux raw import/rehearsal bundles are absent here. His table's medians
are arithmetically consistent and retained as attributed owner-run results;
six-run digest equality and SSD timings were not independently rerun. Formal
G3/full reconciliation, registered fault campaigns, all-owner receipts, frozen
evaluation resources/clock bindings, controlled B0/matrix/report and genuine
human relevance labels remain outstanding. No performance result or peer review
was fabricated to clear those requirements.

Final runtime: Docker Desktop and the 12 healthy prototype containers are left
running for the user to demonstrate. No import, seed, volume reset/removal,
unrelated container change, commit or push was performed. Test-created schemas
were isolated and cleaned by their fixtures. Raw artifacts, dataset and private
bindings remain ignored. Manual review/restart and the single stack-stop command
are in `PRESENTATION_READY.md`; the demonstration can be launched immediately
with `uv run --locked python -m projectctl demo --namespace dev --user-id
demo-professor --query "men's formal shirt"` from this repository.

## 12 November 2026 — final bug review and same-branch publication

User explicitly requested a thorough review, fixes and push on the existing
`jaineel/prototype-demo` branch. Reviewed the 11 pending presentation paths,
M1 client/state recovery, public-provider checks, current owner runtime exports,
ownership/specification requirements and remaining M0 obligations. Fetched
`origin`'s branch/main and verified the remote feature branch is an ancestor;
publication needs no history rewrite. No other owner's implementation changed.

Concrete fixes, with regression evidence:

- A successful normal search with `intent: null` could pass preflight. Require
  a real INR intent and the expected complete set of hard-filter values,
  including absence of extra constraints on the normal query.
- Gold observation abandoned a temporary transport/HTTP 429/503 outage at the
  first failed read. Retry the same GET identity at most twice consecutively,
  respecting the common retryable flag, `Retry-After` and observation deadline.
  Permanent errors and exhausted attempts remain INCOMPLETE. Streamed error
  responses are retained in a bounded buffered response so policy parsing can
  read their body without `httpx.ResponseNotRead`.
- Malformed saved-state JSON values and invalid identity/origin/operation
  containers could crash resume. Both commands reuse structural validation
  before dispatch or replacing the original state. Valid existing journals
  retain their identities and purchase recovery behaviour.
- Valid service origins ending in `/` produced doubled API path slashes in
  presentation checks. Normalize validated origins consistently with the
  interactive demo. Both preflight and order/Gold observation are covered.

Added the actual existing M3 runtime export to the evaluation teammate runbook,
alongside Harsh's catalogue runtime. A lazy-composition regression proves all
six migration participants register without executing migrations. The provider
already implements these callbacks; no duplicate migration implementation or
automatic owner approval was introduced. `COURSE_COVERAGE.md` maps real DE/DS
code, protocols, present evidence and limits, and the remaining Jaineel M0 work.
Current canonical scope requires a reproducible local profile, not geographic
deployment. Presentation instructions now link this explanation and retry policy.

Additional paths beyond the preceding checkpoint:
`projectctl/demo.py`, `tests/projectctl/test_demo.py`,
`tests/projectctl/test_team_handoff.py`,
`docs/jaineel/EVALUATION_TEAMMATE_RUNBOOK.md`, and
`docs/jaineel/COURSE_COVERAGE.md`. The complete publication contains 16 reviewed
source/test/documentation paths, including the previous presentation work.

Verification (raw evidence: `artifacts/review-push-20261112/`):

| Exact command/check | Actual outcome | Evidence |
|---|---|---|
| New failing regressions selected by `pytest ... -k 'cannot_pass_missing or recovers_from_one or invalid_saved_state'` | 8 failed / 2 passed before fixes; failures reproduce the missing intent, outage handling and invalid-state crashes | `bugs-before.{log,xml}` |
| `pytest tests/projectctl/test_presentation.py -q -k recovers_from_one` with real streaming-response doubles | 2 failed / 1 passed before buffering fix; exposed `ResponseNotRead`, corrected without weakening assertions | `streaming-before.log` |
| `uv run --locked python benchmarks/manual/verify_p5.py` with disposable PostgreSQL 18 test URLs | **11/11 checks matched, exit 0; 958 tests passed, zero failures/errors/skips** | `p5.log`; `artifacts/p5/dca53e23-7bbb-4e4a-a10e-973b834cbdfc/{checks.json,pytest.xml}` |
| `uv run --locked pytest tests/conversation tests/transactions tests/integration -q --tb=short --junitxml=artifacts/review-push-20261112/services.xml` | **702 passed, zero failures/skips, exit 0; 182.94 s** | `services.{log,xml}` |
| `uv run --locked pytest tests/projectctl/test_presentation.py tests/projectctl/test_demo.py tests/projectctl/test_team_handoff.py -q --tb=short --junitxml=artifacts/review-push-20261112/final-focused.xml` | **82 passed, zero failures/skips, exit 0; 27.75 s**, includes final origin normalization and M3 registration; overlaps P5 | `final-focused.{log,xml}` |
| `uv run --locked ruff check projectctl tests/projectctl`; `ruff format --check projectctl tests/projectctl`; generated schema/conversation checks in P5; `git diff --check` | PASS | CLI output, P5 recorder, `diff-check.log` |
| `uv run --locked python -m projectctl demo-check --conversation-url http://127.0.0.1:8001/ --orders-url http://127.0.0.1:8003/ --analytics-url http://127.0.0.1:8006/ --out artifacts/review-push-20261112/live-final-preflight` | PASS 6/6, real providers, exit 0, final source | `live-final-preflight.log`, corresponding state/check/raw HTTP directory |
| `uv run --locked python -m projectctl demo --resume artifacts/presentation-20261112/purchase/state.json` | PASS same CONFIRMED order, no new purchase | `live-resume.log` |
| `uv run --locked python -m projectctl demo-check --state artifacts/presentation-20261112/purchase/state.json --analytics-url http://127.0.0.1:8006/ --out artifacts/review-push-20261112/live-final-order` | PASS exact terminal order in active Gold, exit 0 | `live-final-order.log`, copied observation state/raw HTTP |
| Local Markdown link resolution in root/projectctl/current guide/review/course/evaluation manuals | PASS | Review CLI output |

P5's `contracts check --all` exit 4 is its explicit expected result for absent
formal all-owner review receipts. Its real-SUT/Grafana/performance labels remain
NOT_RUN. Service tests use real isolated PostgreSQL and explicit provider doubles
as documented in those suites; only the separate live smoke above uses every
running prototype provider. Counts from overlapping suites must not be summed.
Existing FastAPI lifecycle/JUnit warnings do not change the assertions.

Testing used only newly created `jaineel-final-review-20261112` on port 55439,
with per-test schemas. It is removed after verification, including its own
anonymous volume; the retained 12-container prototype and all named volumes
stay available. No raw dataset, generated artifact, credential, private binding,
test database or benchmark-result directory is staged.

Publication uses the exact reviewed path list, `git commit -m "feat: add verified
prototype presentation checks"`, then `git push origin
HEAD:refs/heads/jaineel/prototype-demo`. The final source/staged hash review,
actual commit, push output and remote-HEAD equality are retained in
`artifacts/review-push-20261112/git-receipt.json` and its adjacent logs. Manual
run/recovery/stop instructions are in `PRESENTATION_READY.md`. Remaining formal
evaluation prerequisites are listed in `COURSE_COVERAGE.md`; no unfinished
measurement, geographic deployment or human approval is claimed complete.


## 13 November 2026 - Windows desktop conversation and metrics integration

User authorized cross-module prototype integration, preservation of existing
additions, Windows-only delivery and visible professor-demo metrics. Existing
PR #23 was already merged locally; all initial local changes were snapshotted
before edits. No reset, branch switch, import, reseed, volume deletion, commit
or push was performed.

Implemented actual Gemini shopping conversation separately from P11 intent
fallback: private bounded history/preferences, typed catalogue tools, references,
clarification, guarded refinements, durable one-call reservations and clear
provider failures. Preserved explicit purchase confirmation and idempotency.
The browser selects configured AI conversation and separately retains a chosen
deterministic mode. Model settings/key stay in ignored server bindings.

Integrated real session/Gold metrics into the desktop UI. Fixed shirt relevance
with recorded taxonomy, empty-result refresh, overlapping sticky chat bubbles,
Windows projection-manifest startup paths, stale scaffold/CI expectations and
transient Windows evidence-file sharing locks. The strict white-shirt search is
honestly empty: all 896 recorded ordinary shirts lack recorded colour.

Changed paths: services/conversation (app/workflow/shopping, new shopping_llm,
shopping_dialogue, shopping_metrics, generated-contract helper and web assets),
shared/contracts/shopping.py, contracts/http/shopping.yaml,
services/catalog/{products,search,product_types}.py, infra/{prototype,retrieval}.py,
infra/compose.prototype.yaml, root PowerShell scripts, .env.example,
.github/workflows/offline.yml, benchmarks/manual/{verify_p5,verify_prompt6}.py,
relevant conversation/catalogue/benchmark/scaffold tests and current demo docs.
Existing local retrieval/embedding/Gold/recovery additions remain in place.

Actual checks (overlapping suites; do not sum): Windows offline verifier PASS,
1,927 passed / 627 explicitly skipped service checks; isolated PostgreSQL service
suite 766 passed; final dialogue/metrics/guard suite 24 passed; catalogue with
real locked encoder/PostgreSQL under Docker Desktop 73 passed; Node controller
11 passed. Generated shopping/catalogue/original conversation contracts, Ruff,
Node syntax, whitespace and Git-visible secret scan passed.

Real Edge checkout rehearsal PASS: one scripted simulated order
cce5bd87-ccc7-4607-84e6-b72e872d0859, CONFIRMED v6, INR 297, committed reservation,
one successful payment and exactly one 29,700-minor debit. Inventory/projection
versions agree; exact order facts match active Gold. Six corresponding Kafka
receipts are durable and Gold-visible. Unchecked/declined confirmation, response
loss with exact cart retry and refresh/resume did not create another order.

The separate real Gemini browser check PASS: eight turns, eight API attempts,
five searches/embeddings, zero errors and zero checkout requests. Its observed
P50/P95 was 2,251.70/2,684.19 ms and mean model time 1,657.39 ms. These are actual
demo observations, not a controlled performance result. Stop/recreate/start and
post-recreation order audit passed; all twelve containers remain healthy.

Exact commands, outcomes, initial failures, evidence locations and limitations:
[Windows integration record](WINDOWS_DESKTOP_INTEGRATION_2026_11_13.md).
Private raw evidence is artifacts/conversation-integration-20261113/.
The existing contracts all-owner byte-pinned review gate remains NOT_RUN;
GitHub Actions was not rerun without a commit/push. No formal benchmark,
fault-campaign or outside owner-review result is claimed.
Manual steps: open http://127.0.0.1:8001/, follow
[PROFESSOR_DEMO.md](PROFESSOR_DEMO.md), expand Live demo metrics, and stop with
./stop-prototype.ps1 after presenting. Data and volumes remain retained.

Final engine recovery completed: start-engine-recovered.log reports readiness, projection, fixed preflight and hybrid PASS. The latest 24 dialogue/metrics tests and independent purchase audit pass after recovery. final-health.json verifies all 12 containers healthy, AI configured, presentation flags off, key scoped to M1 and persisted session metrics available.

## 14 November — desktop chat layout, automatic hybrid and checkout wording

Completed the user's UI update: independent message scrolling with non-overlapping
controls, automatic hybrid retrieval in chat and top-bar search, facet/budget
extraction before ranked retrieval, friendly order-review wording and removal of
the requested banner. Exact retry identity and explicit confirmation remain in
place. Basic chat remains under Chat settings. Existing source data and local
changes were preserved.

Actual checks: 483 conversation tests passed against isolated PostgreSQL storage
with declared owner/model/event doubles; 11 Node controller tests passed; real
Edge layout/search/cart/quote checks passed at five desktop sizes with settings
open/closed; real Gemini eight-turn browser flow passed. No new purchases were
submitted. Ruff/Node syntax/whitespace checks passed. Evidence, exact commands,
initial failures, changed paths and manual steps are in
[the desktop UI record](DESKTOP_UI_2026_11_14.md).

## 14 November — separate data engineering dashboard

Moved dashboarding off the storefront into `/dashboard`, with a header link.
Added measured event/latency/producer/order/receipt charts, service readiness,
Silver/Gold manifest and offset details, catalogue attribute coverage, scoped
current-order visibility, pause/refresh and JSON export. Missing providers remain
unavailable, and charts document their scopes. The old metrics API remains usable.

Actual checks: 489 conversation tests passed on isolated PostgreSQL storage with
explicit owner/event/model doubles; 11 Node controller tests passed. Real Edge
checks cover the separate page, five desktop sizes, live API projections, store
navigation and export. The browser's partial-provider state uses an explicitly
labelled response projection double. No purchases were submitted for this work.
Ruff, generated contracts, Node syntax and whitespace checks passed. Exact commands,
changed paths, evidence, initial failures, limits and manual steps:
[dashboard delivery record](DASHBOARD_2026_11_14.md).

Final dashboard review found repeated journal observations for the same Kafka
position. Aggregation now counts each namespace/topic/partition/offset once,
rejects conflicting source identities, and reports journal observations separately.
The resume cursor is not treated as proof of more rows. Seven focused dashboard
tests passed after this change. The storefront's five-size layout/search/cart/
review regression also passed after dashboard extraction; no checkout was submitted.

## 14 November — remove similar-product action from details

Removed the Find similar button and its click handler from the product details
window at the user's request. Updated the browser rehearsal to close details
directly and assert that the removed button is absent; updated current demo/spec
instructions. Node syntax/controller and whitespace checks passed. No purchase
or live checkout rehearsal was required for this UI removal.

## 14 November — integrated Failure Demo and measured visual evidence

Implemented all five requested scenarios in the existing `/dashboard`:
analytics-worker pause/catch-up with its read API left available; committed
gateway response loss and exact idempotent checkout retry; deterministic payment
decline/compensation; actual Orders process exit 86 at saga.after_commit and
retained-container recovery; and a persisted 35-second payment plan with expiry,
quiescence and post-due compensation verification. Explicit preparation/consent
gates all scripted checkout; loading/polling/recovery do not purchase or replay.

Added a loopback Windows controller, fixed allowlisted process actions, validated
project/container targets, an exclusive desktop run lease, finite deadlines,
interrupted-state recovery, scoped expiring owner hooks and evidence download.
Independent owner audit APIs verify one purchase/debit, reservation state, stock
conservation and exactly two stock-version changes. Gold checks the exact final
identity/version/status/amount; cancellation matching now follows its canonical
event fields while participant audits remain separate. Normal benchmark/fault
flags stay false. No datasets, models, databases or volumes were reset.

The UI has five-stage controls, scenario concepts/preconditions, manual versus
automated labels, timestamped observations, actual run/request/order IDs, Pending/
Passed/Failed/Unavailable states, a worker/API/order/Gold timeline, stock and ledger
graphs, and a verification journal. Unknown observations stay null. Find similar
remains removed. Existing local changes were preserved; no branch change,
commit or push was performed.

Actual checks: all five real-service CLI cases PASS, followed by a final real
retry check after gateway-error hardening; full isolated PostgreSQL regression
PASS (718 tests in 181.71 s); final focused controller/oracle guards PASS (23,
overlapping the broad suite); storefront Node controller PASS (11). Two real Edge
rehearsals passed all five scenarios plus the normal store-confirmation path,
six viewport widths, measured charts, evidence download and zero refresh/reload
mutations. Screenshots were visually inspected. The 35-second case proves callback
suppression under current saga rules, not a claimed late successful charge/refund.

Start with ./start-prototype.ps1 when needed, then ./start-failure-demo.ps1.
Open /dashboard#failure-demo and Connect. For the primary manual case, add to the
store cart before Prepare, Trigger pause, explicitly confirm in the store, Watch
the new order, Recover and Verify. Other cases use a consent checkbox and an
explicit automated-test action. Stop the helper with ./stop-failure-demo.ps1
before the normal prototype shutdown.

Exact commands, results, changed paths, raw evidence, initial failures and limits:
[Failure Demo delivery and operating guide](FAILURE_DEMOS_2026_11_14.md).
Raw evidence: artifacts/failure-demo-20261114/ and artifacts/failure-demo/.
No scenario remains mock-only or blocked. These local trials do not establish
production HA or broker-head lag. Automatic recovery requires the helper to be
running; after a helper interruption, restart it and use Recover.

## Windows Desktop measurements, resource/clock controls and late payment — 14 November 2026

Added `benchmarks/windows/{evidence,measure,worker}.py`, the Windows-only Desktop
guard, and `run-measurements.ps1`, `verify-desktop-controls.ps1`, and
`run-late-payment.ps1`. Existing uncommitted Desktop work is preserved. The user's
latest instruction is to finish locally without pushing; no Git commit or push
is made for this task. CI/CD checks are deliberately not invoked.

The runner composes the existing owners' real importer, search count/rank SQL,
analytics sink, publisher, compactor and DuckDB query suite. Comparisons retain
three seeded paired repetitions, raw observations, logical-result equality,
negative improvements, build/staging costs and report artifacts. PostgreSQL and
the provider process have separate enforced limits. Windows remains the launcher
and evidence destination. Provider operations use a disposable Docker Desktop
Linux data volume to preserve the storage contract's directory-fsync guarantee.

Resources include actual image identities, host inventory, CPU/RAM/swap/PID
limits, cgroup memory peak/OOM counters, Windows observer CPU/RSS and Docker stats.
UTC probes retain midpoint offset, RTT, error bound and clock-step residual;
before/after checks gate local comparisons. Formal P9 qualification remains
separate and is not asserted by these provider comparisons.

Late-payment verification now also requires a persisted completion deadline
beyond reservation expiry. Its independent ledger check permits no debit or one
debit with exactly one reversal for the same payment, and rejects cross-payment
refunds. The ordinary real-service path safely quiesces the pending callback.

Completed commands and actual results:

- `.venv/Scripts/python.exe -m pytest tests/benchmarks/test_windows_measurements.py tests/benchmarks/test_failure_demo.py -q`: 28 passed; one existing Starlette/httpx deprecation warning.
- Ruff on the Windows harness and changed failure-controller/oracle tests: passed.
- PowerShell AST parsing of all three new launchers: passed.
- `.venv/Scripts/python.exe -m benchmarks.windows.evidence`: passed for all 12
  prototype containers; matching allocations and a largest measured relative
  clock error bound of 98.93 ms (500-ms configured ceiling).
- `./run-late-payment.ps1`: passed all independent expiry/cancellation checks for
  order `8ebddfcd-2315-4703-ac66-2b55d9f1b69a`; one attempt, cancelled order,
  released stock, zero net debit and exact active Gold state. Receipt:
  `artifacts/windows/late-3c3f02516543456b99e67d33a8d92989/`.
  Hook support was disabled and every prototype container removed; all retained
  data/model volumes remain intact.

Initial failed measurement attempts remain under `artifacts/windows/`. Native
Windows FileStore correctly refused directory fsync, prompting the Docker data
volume composition. An initial provider launch lacked the infra/projectctl
mounts; those mounts were added. Both failures removed their disposable
PostgreSQL/provider containers and retained failure evidence. They are not
performance results. See [the operating guide](WINDOWS_MEASUREMENTS.md) for exact
boundaries, reproduction commands, cleanup and limitations.

The first complete provider invocation subsequently exposed an invalid harness
namespace (`windows-measure`); event contracts require the `bench-` prefix.
It was corrected to `bench-windows-measure` throughout. That failed run retained
import timings, query plans and resource receipts, but its partial query journal
was overwritten by the controller's empty list. The controller now preserves
copied partial journals on failure. No performance claim is made from that run.

The subsequent `./run-measurements.ps1 -Smoke` completed all four axes with equal
logical results: 428 raw measurement rows, 108 comparison groups and 438 hashed
evidence files. Before/after clocks passed, provider OOM counters were zero, and
both containers/anonymous volumes were removed. Its receipt is
`artifacts/windows/7571d5432cc1412ea7006b116d85dc6c/` and status is SMOKE_ONLY.
The expanded measurement integrity suite then passed all five tests, including
host clock-step rejection and invalidation of stale successful receipts. These
are focused local checks, not a CI/CD workflow run.

Final measurement outcomes: the full 50-query/30-sample invocation reached its
one-hour provider deadline and remained FAILED, with its partial journal
preserved. The deadline is now configurable (120-minute default). Added explicit
`-Quick` triage mode: three pairs, two timed executions, and two fixed query IDs
per original search stratum. Full mode retains the original fixture and sampling.
Measured imports now each create an absent archive, keeping archive state equal
between variants rather than giving the first run a different write boundary.

`./run-measurements.ps1 -Quick` then completed all provider operations: 276 raw
observations, 24 comparison groups, all three pairs and matching logical results.
However, one Windows Docker stats acquisition timed out. The strict collector
gate correctly rejected the bundle as FAILED rather than qualifying its numbers.
Provider OOM/kill counts were zero; the provider reached its 1-GiB allocation and
recorded memory-pressure events, which remain visible. Before/after clock
qualification for this failed bundle is not established. Receipt:
`artifacts/windows/09aba659a2104d99b5e6c3e8f8ebbd1b/`.

The read-only `benchmarks.windows.report` helper verifies the original journal
hash and rebuilds separate DIAGNOSTIC_ONLY observations without changing the run
or promoting a failed result. Command actually executed:
`.venv/Scripts/python.exe -m benchmarks.windows.report --run artifacts/windows/09aba659a2104d99b5e6c3e8f8ebbd1b`.
Output: `artifacts/windows/reports/09aba659a2104d99b5e6c3e8f8ebbd1b/`.
Docker stats acquisition now permits 30 seconds instead of 10; a timeout still
fails qualification. This environment's interruption is not represented as a pass.

All prototype and disposable PostgreSQL/provider containers have been removed;
`docker ps -a --format '{{.Names}} {{.Status}}'` returned no rows. Existing named
prototype volumes are retained. No commit or push was performed, following the
user's latest instruction. CI/CD remains unexecuted. A formal performance claim
still needs a complete uninterrupted full run plus the canonical P9 gates.

Final focused verification after the diagnostic helper: the same pytest command
for `test_windows_measurements.py` and `test_failure_demo.py` passed 32 tests;
Ruff and changed-path whitespace checks passed. The only pytest warning was the
existing Starlette/httpx deprecation. No CI/CD workflow was run.

## 14 November 2026 — simpler prototype pages and hybrid search repair

Simplified the dashboard and journey page wording, navigation and default layout.
Kept detailed charts, scheduled-workload rates, resource/lag history, raw receipts,
file lineage, stock updates, recordings/playback, and manual/automated failure
controls accessible in expandable sections or through the linked dashboard.
Removed the store chat-mode selector and preference note; UI requests AI
conversation while deterministic mode remains available through the HTTP contract.
Search now uses advertised keyword search when hybrid alone is unavailable.

Prepared embeddings with the existing owner command for the active presentation
namespace: 19,998 vectors, locked model/template, batch size 16, 905.25 encoding
seconds. No catalogue reseed or stock reset. The one-off container removed itself.
An initial cold fixed-mode search exceeded its existing three-second deadline;
the repeated real hybrid check passed with that deadline unchanged. Restarted the
stale local helper after checking no active test/fault, restoring its receipt,
lag and clock observations (1,200 timed events, six lag readings, qualified clock,
zero pending Gold). Core containers remain running because the user asked to use
the local prototype. No commit, push or CI/CD execution.

Changed paths: conversation web dashboard/journey HTML/JS, shared prototype CSS,
store HTML/controller and AI error copy; related browser/controller rehearsals;
presentation guide and this progress record. Exact commands, evidence and limits
are recorded in [SIMPLE_PROTOTYPE_2026_11_14.md](SIMPLE_PROTOTYPE_2026_11_14.md).

Validation: real Edge + Gemini + hybrid search and pipeline metrics, trace, export,
saved playback safety and manual-control availability passed at
`artifacts/simple-prototype-browser/1794664688446`. No purchase/fault submitted.
Hybrid follow-up/filter verification passed at
`artifacts/retrieval/verify-20c8ae91f3614452bfcb799192f222ee`.
Store controller tests: 11 passed; journey model tests: 12 passed; isolated HTTP
browser rendering passed. Python model/dialogue selection: 19 passed, five tests
skipped without their isolated database binding; this is not a live pass for
those skipped tests. Changed Python lint and whitespace checks passed.

## 14 November 2026 — home-page controls and retained session recovery

Reproduced the user's home-page failures against the real running service: a
client record from the old `dev` dataset stopped startup before categories and
retrieval initialized, and changing the category sent no request without Apply.
The earlier fresh-browser check had missed the retained-session case.

Removed More options and its JavaScript references. Category, sort and price now
apply on change. The send button stays disabled until startup finishes; Enter
uses the actual submit button, while Shift+Enter and IME composition stay in the
textarea. Old-dataset sessions (including exact pending checkout identities) are
archived locally rather than replayed into the active dataset. Missing saved
server sessions reconnect only after a definite 404 and with no pending request.
Added a store-script version to ensure the updated controller is fetched.

Changed `services/conversation/web/index.html`, `store.js`, their controller and
layout tests, and added `tests/conversation/storefront.controls.live.cjs`.
`RUN_HOME_CONTROLS_LIVE=1 node tests/conversation/storefront.controls.live.cjs`
passed with real services and AI: retained-session reconnect, automatic category/
sort/price filters with returned data checked, suggestion click, Enter submission,
send-button click, Shift+Enter, chat restoration after reload and zero purchases.
The old client record is an explicitly synthetic browser fixture; backend/AI
responses are real. Evidence: `artifacts/home-controls-browser/1794665812424`.
`node --test tests/conversation/storefront.test.cjs`: 13 passed after extending
the explicit DOM double for the new keyboard check. Syntax and whitespace checks
passed. No commit, push or CI/CD execution; prototype services remain running.

## 14 November 2026 - guided Journey and real edge-case repairs

Replaced the Journey lab's manual Run/Finish/Save/source controls with one
Run test action, a plain expected result and short checks. The browser completes
publication automatically and shows the selected test's result only. Old failures
are retained in explicit history. View test events handles isolated scope without
asking the presenter to pick namespaces. Recording/playback and full reports
remain available in optional sections. Leaving playback or test scope clears the
old trace instead of mixing it with store activity. All seven cases remain.

Real fixture setup exposed an empty metrics vocabulary in the catalogue adapter;
omitting empty vocabularies fixes valid clean imports without changing the shared
Telemetry validator. The race runner now waits for first queryable publication
within its existing deadline; original stock/debit/Gold assertions are unchanged.
Added worker-active state so controls also wait for fixture cleanup to finish.

Changed paths: conversation web journey HTML/controller and prototype CSS;
`benchmarks/journey/lab.py`, `lab_worker.py`, the narrow metrics integration in
`pipelines/catalog/adapter.py`, `tests/benchmarks/test_journey.py`, guided/live/
rendering browser rehearsals and simple-prototype rehearsal compatibility.
The catalogue change is an integration repair in another owner's adapter, with
the exact defect and evidence documented for review; public service contracts
and business rules are unchanged.

All seven fixtures passed both direct real-service checks and the actual guided
Edge page. Browser evidence: `artifacts/journey-guided-browser/1794666758168/`;
direct evidence: `artifacts/journey-fixture-recheck/`. The two-buyer case created
two isolated simulated orders and verified one sale, one cancellation, one
matching debit, no overselling and exact reconciliation in active Gold. Real
recording/save/playback passed with zero playback mutations and zero page errors.
Python Journey/failure tests: 48 passed. Journey model: 12 passed. Final explicit
HTTP-double rendering/playback checks and changed-file syntax/lint/whitespace
checks passed. Commands, limits and manual steps are recorded in
[SIMPLE_PROTOTYPE_2026_11_14.md](SIMPLE_PROTOTYPE_2026_11_14.md).

Manual demo: open `/journey`, choose a case, click Run test (approve two simulated
orders only for the two-buyer case), then read the checks or View test events.
Previous runs and presentation recording remain collapsed until requested.
No old failures deleted and no unmeasured result represented as a pass. No
remaining integration blocker was observed for these seven cases in the running
Windows environment. No CI/CD, commit or push. Disposable fixture containers are
gone; twelve healthy core containers remain for the user to run the prototype.

## 14 November 2026 - remove presentation recording controls

At the user's request, removed the Record or replay a presentation section and
its browser recording/import/playback controller, automatic recordings listing,
and Back to live button. Live tracing, all seven pipeline cases, history and
report downloads remain. Backend saved evidence is retained. Updated the three
affected browser rehearsals for the current UI; explicit HTTP-double rendering
and live-control checks passed. JavaScript syntax and whitespace checks passed.
This supersedes the earlier description of optional recording on the page.
No commit, push or CI/CD execution.

## 14 November 2026 - show technical evidence for pipeline tests

Replaced generic PASS-only result rows with a delivery/input/handling table,
a scenario-specific processing rule and an expected-versus-observed table.
The UI reads actual emissions, payloads, Kafka coordinates, durable receipts,
checkout/order responses and reconciliation checks. Repeated event IDs share
an E1/E2 display alias; changed duration values, stock versions, available units
and event times remain visible. Missing observations stay explicitly unavailable.
Stock tuples are labelled with stock_version/available, and race stock tuples
with on_hand/reserved/available. Full reports and event traces remain accessible.
This is correctness evidence, not an end-to-end latency benchmark.

Changed journey HTML/controller, prototype CSS and the existing opt-in guided
browser rehearsal assertions. JavaScript syntax and explicit HTTP-double desktop
rendering passed: artifacts/journey-browser-double/1794671440618. A further
read-only sweep of retained real runs could not start: Node ran out of memory;
Windows reported only about 240 MiB free virtual commit space. No user processes
or core services were stopped. The new technical-result sweep is NOT_RUN;
earlier real pipeline case passes are retained but are not claimed as a new UI
sweep. No new purchases, CI/CD, commit or push.

## 14 November 2026 - activity selection layout

Made recent activity the primary full-row control, with the existing Find a
specific ID disclosure below it. Expanded ID lookup has aligned Type/ID/Find
fields and stacks on narrow screens. All lookup IDs and handlers are preserved.
Changed journey HTML and prototype CSS; no service, pipeline or purchase changes.
No commit or push.
Validation: node tests/conversation/journey.browser.cjs passed with explicit HTTP doubles at artifacts/journey-browser-double/1794671765077 (desktop/narrow rendering and live lookup). git diff --check passed.

## 14 November 2026 - guided recovery tests and infrastructure empty states

Dashboard failure controls now default to automated testing, connect read-only
when expanded, and guide baseline capture, product review/explicit purchase
consent, then Run test. Only actions relevant to the selected mode and run state
are visible. Automated Run test retains the existing backend workflow for fault,
checkout, recovery and verification; no new automatic mutation was added.
Manual analytics pause/store checkout/watch/recover/verify remains available.
Old results for a different selected scenario/mode are hidden from the current
workspace; previous evidence remains downloadable. Technical verification,
timelines, stock/ledger charts and journal are in an expandable evidence panel.

Infrastructure has a labelled Kafka consumer-lag time graph and per-container
CPU/memory tables. Added current lag summary, zero-axis label, bounded plot size,
initial/unavailable placeholders and missing-field CPU guards. Missing lag samples
are not graphed as zero; cached readings remain labelled stale on connection loss.
Live helper returned six lag rows and twelve resource rows. Later some partition
readings were unavailable; the UI now states that rather than leaving whitespace.

Changed dashboard HTML, failure-demo.js, infrastructure.js, prototype CSS and the
existing opt-in failure rehearsal's entry expectations. node --check for changed
scripts and git diff --check passed. Browser verification passed at
artifacts/recovery-guidance/1794672216584: real infrastructure reads and explicit
HTTP doubles for prepared/running/completed/manual workflow states, zero lag and
endpoint failure. Checked desktop/narrow overflow, no JavaScript errors and no
checkout/fault POSTs (normal dashboard session bootstrap is retained). These are
UI checks, not new live fault-scenario passes. No purchases, CI/CD, commit or push.

## 14 November 2026 - professor justification experiments and delivery

Reviewed existing measurements, owner experiment notes, real journey/failure
artifacts and correctness suites before adding a separate exploratory harness.
Added benchmarks/defense.py (B-tree/hash/BRIN/GIN vs integrity-only, shuffled vs
price-sorted layout, build/index-size/WAL/100-price-update costs, analytical raw
vs summary storage/query costs, lineage-loss and unsafe dedup-retirement probes),
benchmarks/defense_report.py (hash/result/repetition guards and report generator),
and tests/benchmarks/test_defense.py. No production index or retention policy was
changed. New measurements reuse the canonical original catalogue normalization;
unknown categories remain null. The first probe exposed that nullable category
case; its failed evidence is retained rather than overwritten.

The final run has three randomized repetitions, three warmups and ten timed
calls for six query cases, five variants and two layouts: 1,800 timed index calls,
180 EXPLAIN plans, 30 cost probes and 60 summary-query observations. PostgreSQL
was isolated at 1 CPU/512 MiB with 256 MiB tmpfs, removed in finally; DuckDB used
one thread/64 MiB query memory. All prototype containers were stopped first.
This is warm component evidence, not SSD, HTTP/Kafka end-to-end, capacity or P9.
Final evidence: artifacts/defense/20261114-professor-final. Earlier exploratory
runs, including the nullable-category setup failure, are retained separately.

The generated PROFESSOR_QUESTIONS_AND_RESULTS.md covers fourteen likely questions,
actual tables, negative results, provenance, controls and remaining NOT_RUN work.
Revalidated all seven saved real journey runs, including independent saved race
ledger/order identities and stock-version facts. Reused earlier real failure
campaigns and the hash-verified 276-observation Windows journal, preserving its
FAILED/resource-incomplete status. Owner-host COPY/compaction/ANN results remain
explicitly attributed, with no claim that their missing raw bundles were replayed.
The fresh refund rehearsal could not prepare: store product listing returned
HTTP 503 before any checkout. artifacts/defense/refund-20261114/attempt.json records
NOT_RUN; refund unit/oracle tests are not substituted for a real debit/reversal.

Exact new execution: .venv/Scripts/python.exe -m benchmarks.defense --out
artifacts/defense/20261114-professor-final --samples 10. Rebuild command is in the
report. Focused pytest over test_defense, test_journey, test_failure_demo,
test_metrics, test_scheduler, test_comparison, test_windows_measurements,
test_performance_metrics, oracle reconciliation, catalogue normalization and
pipeline replay: 234 passed, zero skips/failures, existing Starlette/httpx warning.
JUnit: artifacts/defense/correctness-20261114.xml. Storefront/Journey Node model
checks: 25 passed. Explicit HTTP-double Edge rendering passed at
artifacts/journey-browser-double/1794673963962. Ruff, syntax and whitespace checks
passed. No CI/CD execution.

C: had only about 200 MiB free. Applied reversible NTFS compression with
compact /C /S:artifacts\windows /I /Q *.csv *.json *.jsonl *.prom *.log to retained
old measurement text files. 1,929 files: 551,799,652 logical bytes stored in
241,923,061 bytes. No data deleted or paths changed; the prior raw journal hash
still matches its original manifest. New timings were taken outside that tree
after compression completed. This filesystem maintenance is not the analytical
summary comparison.

User explicitly superseded the earlier no-push instruction and authorized
commit/push after container cleanup. Ran stop-failure-demo.ps1 (faults recovered,
hook support disabled, helper stopped), then stop-prototype.ps1. Final scratch
PostgreSQL cleanup is verified and docker ps -a returned no containers. Retained
PostgreSQL/Kafka/lakehouse volumes and model files remain. Prepared delivery on
jaineel/prototype-demo. Raw datasets, artifacts and private bindings stay ignored.
