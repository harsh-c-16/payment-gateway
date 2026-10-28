# Jaineel's Implementation Progress Tracker

**Author:** Jaineel Vora (B24CM1080)
**Role:** M1 (Session, Cart, Assistant, Workflow) & M0 (Measurement Harness, Oracle, Dashboards, Benchmarks)
**Reference Playbook:** [10_JAINEEL_CODEX_PLAYBOOK.md](../specs/10_JAINEEL_CODEX_PLAYBOOK.md)
**Personal Brief:** [04_JAINEEL_VORA.md](../specs/04_JAINEEL_VORA.md)
**Status Date:** 28 October 2026 (Asia/Calcutta)

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
| **P6** | Durable sessions, cart, and idempotency | J04 | state verified with Docker PostgreSQL; shared event gate incomplete | `jaineel/j03-telemetry` | Docker PostgreSQL 18.6; explicit event/outbox/turn doubles |
| **P7** | Zero-call search, quote, and checkout workflow | J04 | stub verified; P7 checkpoint complete; real provider/event gates incomplete | `jaineel/j03-telemetry` | Docker PostgreSQL 18.6; explicit HTTP/event doubles; 717 tests |
| **P8** | Real G1/G3 integration, failures, reconciliation | J06 | stub verified (owner harness); real gates INCOMPLETE | `jaineel/j03-telemetry` | 774 passed; real M1 PostgreSQL, explicit provider/audit/hook doubles |
| **P9** | Correct B0 and controlled performance matrix | J07 | stub verified (owner harness); real measurements NOT_RUN | `jaineel/j03-telemetry` | 823 regression passes; 49 P9 checks; real matrix dependency-blocked |
| **P10** | Reproducible report and clean setup rehearsal | J07 | not started | — | — |
| **P11** | One-call intent fallback (optional last) | J05 | not started | — | — |

Latest cross-milestone review: [P1–P5 audit and fixes](#p1p5-audit-and-fixes--27-october-2026), **511 tests passed**. The counts above describe the original milestone checkpoints; this review does not advance P6.

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
