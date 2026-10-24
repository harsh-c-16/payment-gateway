# Jaineel's Implementation Progress Tracker

**Author:** Jaineel Vora (B24CM1080)
**Role:** M1 (Session, Cart, Assistant, Workflow) & M0 (Measurement Harness, Oracle, Dashboards, Benchmarks)
**Reference Playbook:** [10_JAINEEL_CODEX_PLAYBOOK.md](../specs/10_JAINEEL_CODEX_PLAYBOOK.md)
**Personal Brief:** [04_JAINEEL_VORA.md](../specs/04_JAINEEL_VORA.md)
**Status Date:** 25 October 2026 (Asia/Calcutta)

> [!NOTE]
> This local progress document tracks technical milestone execution in Codex. It is separate from the academic Excel tracker. Status labels used: `not started`, `in progress`, `stub verified`, `real verified`, `blocked`.

---

## Milestone Summary

| Milestone | Deliverable | Associated Brief Task | Status | Branch | Test Mode |
|---|---|---|---|---|---|
| **P0** | Team repository scaffold and governance | Setup / Prompt 0 | real verified (local scaffold) | `jaineel/j01-foundation` | local files/Git |
| **P1** | Python tooling, CLI/config/artifact foundation | J01 | stub verified (offline checkpoint complete) | `jaineel/j01-foundation` | Python 3.11; explicit adapter doubles |
| **P2** | Conversation contract, clients, explicit stubs | J01 | stub verified (offline checkpoint complete) | `jaineel/j01-contracts` | 89 contract tests + 110 P1 regressions; explicit HTTP/SSE doubles |
| **P3** | Independent fixtures, oracle, and metric math | J01 + early J06 | not started | — | — |
| **P4** | Open-loop workload generation & experiment lifecycle | J02 | not started | — | — |
| **P5** | Telemetry, raw collectors, dashboard | J03 | not started | — | — |
| **P6** | Durable sessions, cart, and idempotency | J04 | not started | — | — |
| **P7** | Zero-call search, quote, and checkout workflow | J04 | not started | — | — |
| **P8** | Real G1/G3 integration, failures, reconciliation | J06 | not started | — | — |
| **P9** | Correct B0 and controlled performance matrix | J07 | not started | — | — |
| **P10** | Reproducible report and clean setup rehearsal | J07 | not started | — | — |
| **P11** | One-call intent fallback (optional last) | J05 | not started | — | — |

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
- **State:** not started
- **Branch:** —
- **Base Commit:** —
- **Brief Task:** J01 + early J06
- **Commands:** —
- **Evidence Paths:** —
- **Test Mode:** —
- **Pending Owner Handoffs:** None (uses independent fixtures and raw CSV).
- **Next Action:** Build reconciliation math, quantiles, and offline oracle validation.

---

### Milestone P4: Open-Loop Workload Generator & Lifecycle
- **State:** not started
- **Branch:** —
- **Base Commit:** —
- **Brief Task:** J02
- **Commands:** —
- **Evidence Paths:** —
- **Test Mode:** —
- **Pending Owner Handoffs:** Awaiting provider integration adapters as merged.
- **Next Action:** Implement open-loop generator and stage-managed runner.

---

### Milestone P5: Telemetry, Raw Collectors, and Dashboard
- **State:** not started
- **Branch:** —
- **Base Commit:** —
- **Brief Task:** J03
- **Commands:** —
- **Evidence Paths:** —
- **Test Mode:** —
- **Pending Owner Handoffs:** Prometheus metrics definitions alignment across services.
- **Next Action:** Implement shared/telemetry and dashboards.

---

### Milestone P6: Durable Sessions, Cart, and Idempotency
- **State:** not started
- **Branch:** —
- **Base Commit:** —
- **Brief Task:** J04
- **Commands:** —
- **Evidence Paths:** —
- **Test Mode:** —
- **Pending Owner Handoffs:** Aditya (A02 shared outbox library) and PostgreSQL container.
- **Next Action:** Implement services/conversation persistence and idempotency.

---

### Milestone P7: Zero-Call Search, Quote, and Checkout Workflow
- **State:** not started
- **Branch:** —
- **Base Commit:** —
- **Brief Task:** J04
- **Commands:** —
- **Evidence Paths:** —
- **Test Mode:** —
- **Pending Owner Handoffs:** Harsh (M2 search/quote HTTP API), Aditya (M3 order creation API).
- **Next Action:** Integrate conversation workflow with catalogue and transaction APIs.

---

### Milestone P8: Real G1/G3 Integration, Failures, and Reconciliation
- **State:** not started
- **Branch:** —
- **Base Commit:** —
- **Brief Task:** J06
- **Commands:** —
- **Evidence Paths:** —
- **Test Mode:** —
- **Pending Owner Handoffs:** Vichitr (V02 event transport, V03 ingestion) and Aditya (A03 saga).
- **Next Action:** Execute end-to-end integration tests and reconciliation oracle against real services.

---

### Milestone P9: Correct B0 Baseline & Controlled Performance Matrix
- **State:** not started
- **Branch:** —
- **Base Commit:** —
- **Brief Task:** J07
- **Commands:** —
- **Evidence Paths:** —
- **Test Mode:** —
- **Pending Owner Handoffs:** All team members' baseline services running and locked.
- **Next Action:** Execute evaluation matrix runs and collect primary benchmark data.

---

### Milestone P10: Reproducible Report and Clean Setup Rehearsal
- **State:** not started
- **Branch:** —
- **Base Commit:** —
- **Brief Task:** J07
- **Commands:** —
- **Evidence Paths:** —
- **Test Mode:** —
- **Pending Owner Handoffs:** Team review of benchmark results.
- **Next Action:** Generate final consolidated report and test clean environment reproduction.

---

### Milestone P11: Optional One-Call Intent Fallback
- **State:** not started
- **Branch:** —
- **Base Commit:** —
- **Brief Task:** J05 (Optional last)
- **Commands:** —
- **Evidence Paths:** —
- **Test Mode:** —
- **Pending Owner Handoffs:** Optional external LLM API availability.
- **Next Action:** Implement structured intent fallback adapter respecting single-call constraint.
