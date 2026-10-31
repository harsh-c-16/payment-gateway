# Vichitr progress

Git delivery policy (31 October 2026): the user authorizes committing and pushing
each completed module to `vichitr` after its checks pass. The first delivery covers
the completed M01a/M01b infrastructure and planning notes. Credentials, the raw CSV,
generated data and local evidence stay outside Git. Earlier "not requested/pushed"
notes below describe those checkpoints before this standing authorization.

## M04 — Durable FileStore, Bronze and capture ledger, 31 October 2026

Implemented within Vichitr-owned paths. This is capture and receipt **foundation**,
not a completed source disposition/Silver/Gold path. See [M04 handoff](m04_capture_handoff.md).

### Changed paths and behavior

- pipelines/storage/__init__.py and README: three-argument immutable FileStore,
  input/read-back hashes, file/directory fsync, same-directory rename, cooperating
  process lock, traversal/symlink rejection, idempotent retry and read-only orphan
  inventory. Native Windows fails explicitly; real durable execution uses the
  private Linux named volume. No deletion/cleanup implementation was introduced.
- pipelines/ingestion/{__init__,bronze,receipts}.py and README: exact base64 byte
  wrappers, duplicate header order/nulls, source coordinates/times/fingerprint,
  file/row locators, fixed 1-MiB/50-ms capture bounds and bounded input sequences.
  Receipt recovery verifies hashes/membership. Caller-owned SQL persistence keeps
  first source locators, detects changed coordinates/content and rolls back caught
  conflicts with savepoints. Same bytes at a new offset are a distinct source.
- shared/contracts/analytics.py adds internal CapturedSource/RawBatchReceipt DTOs;
  existing public API/receipt fields are unchanged. Capture-only records have no
  final disposition or Silver/Gold times and never authorize worker durability.
- migrations/analytics/001_capture.sql creates captures, source receipts, quarantine
  and processing-run foundations. Migration retry uses an advisory transaction lock
  and normalized-LF checksum; altered applied SQL fails. Aditya still owns outbox DDL.
- infra/analytics.py composes the existing env providers with this owner's migration
  provider. It applies analytics only and explicitly returns dependency exit 4 for
  incomplete global migration dispatch. It never writes another service database.
- infra/{storage.Dockerfile,compose.storage.yaml}: digest-pinned Python 3.11.15,
  existing locked dependencies, opt-in 512-MiB/0.5-CPU Linux verification worker,
  source mounts, one analytics secret and the retained lakehouse volume. Existing
  stack plus worker is 2,688 MiB; Docker RAM was not increased.
- tests/pipelines/{test_storage,test_storage_live,test_analytics_adapter,storage_restart}.py:
  real filesystem/SQL/Kafka checks and explicitly injected syscall/process faults.
  Owned test conftest uses importlib; removing its empty package marker prevents
  test pipelines from shadowing the production namespace. No shared pytest config,
  dependency lock, other owner's code or assertions changed.

### Actual verification and evidence

- Host `.venv/Scripts/python.exe -m pytest tests/pipelines tests/contracts
  tests/integration -q --tb=short --junitxml=artifacts/m04/offline-verified.xml`:
  **286 passed, 31 skipped**, **47.25 seconds**. Windows deliberately skips real
  POSIX fsync tests; explicit opt-in live tests are skipped in this invocation.
  The same new filesystem paths run in the Linux suite below, not as fake passes.
- Linux named-volume `python -m pytest tests/pipelines/test_storage.py
  tests/pipelines/test_storage_live.py -q --tb=short
  --junitxml=artifacts/m04/storage-live-verified.xml`: **26 passed, 1 skipped**,
  **13.77 seconds**. Skip is the Windows-only unsupported-host check. Real broker
  committed offset remained -1001 after capture+SQL; a commit attempt was rejected.
- Real PostgreSQL 18.2 SQL capture rollback, first-locator retry, new-offset source,
  caught corruption rollback and NULL downstream timings passed. Test schemas are
  isolated and dropped afterward; real shared outbox is NOT_RUN, not a test double
  claimed as integration. Evidence: artifacts/m04/{sql-capture,kafka-capture}.json.
- The syscall cases include pre-rename disk/file-fsync failure and directory-fsync
  failure after rename. A child acknowledged M04_AFTER_RENAME_BARRIER_ACK before
  os._exit(73); its orphan was recovered by verified immutable retry. These are
  process/syscall fault checks, not hardware power-loss measurements.
- Existing streaming env up initially returned ConnectionTimeout during cold
  startup (artifacts/projectctl/787f99ad-fdbb-47d0-b4d8-29b5335c5acd). Retained stack
  became healthy; retry exited 0 and verified mappings:
  artifacts/projectctl/85562d40-f84b-4e5c-ae5f-e8273b1ff83b/.
- CLI migration applied analytics but an initial adapter incorrectly pre-created
  the CLI-owned evidence directory; its raw provider result is preserved under
  artifacts/projectctl/57c35968-d9c4-4517-92a2-575c5c6adfea/. Fixed at the adapter's
  evidence path and added a regression test. Verified command with
  PROJECTCTL_ADAPTER_MODULE=infra.analytics, `python -m projectctl db migrate
  --namespace bench-m04`: expected exit **4**, analytics portion applied and global
  dependencies explicit. Evidence: artifacts/projectctl/f4c400ce-7b5f-4ae6-90eb-fea746a1f3f2/
  and artifacts/infra/analytics/checks/f4c400ce-7b5f-4ae6-90eb-fea746a1f3f2/.
- `python -m tests.pipelines.storage_restart` then a verified real PostgreSQL
  container restart and a fresh worker `--resume`: **PASS**; container/image/named
  volume identity retained, database receipt and exact invalid bytes recovered,
  repeat capture remained idempotent and disposition stayed NULL. Evidence:
  artifacts/m04/{restart,restart-container}.json. Public test namespace is
  bench-m04-restart-8d2d7bd3cb264505998693f42249d196; no operational data was reset.
- Initial collection failures, corrected import/source-mount setup and earlier XMLs
  are retained. No failed case/assertion was removed to obtain a pass. Final
  cross-platform migration/checker and delivery evidence follows below.
- Final Linux suite adds the adapter regression and verifies LF/CRLF migration
  retry plus rejection of an idle caller connection: **28 passed, 1 skipped**,
  **6.52 seconds**, artifacts/m04/storage-final.xml. Earlier full run (28/1,
  6.60 seconds) and the missing-source-mount collection failure are retained.
- Owned Ruff lint/format and git diff checks passed after formatting a README code
  block. Existing schemas/API fixtures are unchanged. Real infrastructure/schema
  mappings verified after restart: exit **0**,
  artifacts/projectctl/e05e8f66-05cc-4d68-896b-53596cdc17e9/.
- Environment down exited **0**, volumes retained:
  artifacts/projectctl/6f2e2bdf-0af7-4a4f-bab5-a6737b20847f/. Docker Desktop stopped
  after confirming no other containers were running. Ownership and exact retained
  credential scans passed for all **23** delivery paths; no raw CSV, credentials or
  generated evidence is staged. Audit: artifacts/m04/source-audit.json.
- Full shared Ubuntu/Windows/PostgreSQL workflow verification is performed by the
  branch's GitHub Actions run after delivery; raw status is retained locally in
  artifacts/m04/github-actions.json. Local P5/P6 scripts were not redundantly rerun
  for this module; the focused host and actual Linux capture suites are above.

### Remaining handoffs

M05 must atomically finalize dispositions with Silver/reducers or quarantine and
Aditya's real outbox, then mark durable prefixes. Public receipt/manifest/Gold API,
active publication, replay and performance remain NOT_RUN. Harsh can adopt FileStore
inside the Linux volume; his CSV parsing and source manifests remain his work.

A near-1-MiB raw invalid source can exceed the physical file cap after base64.
CaptureTooLarge backpressures it without committing offsets; fragmentation/locator
contract review is required. Native Windows directory fsync and host power-loss/
volume-loss durability are not claimed. Orphan inventory never deletes data.

## M03 — Shared transport and local diagnostics, 31 October 2026

Implemented on `vichitr` within Vichitr-owned paths. Provider adoption and Aditya's
actual outbox remain external dependencies; full G0/integrated checkout is not
claimed. See [M03 handoff](m03_transport_handoff.md) and the two shared READMEs.

### Implemented paths and behavior

- `shared/event_transport/{__init__,codec,publisher,consumer}.py`: public builder,
  validator, acknowledged publisher, manual consumer/offset functions and pure DLQ
  construction. Existing M1 keyword build/append binding is tested unchanged.
- Producer settings are fixed: idempotence, acks=all, max in-flight=5, Zstandard,
  linger=5 ms, 10,000 records/64 MiB queues, 10-second delivery timeout and 5-second
  request timeout. Queue admission is never returned as success. Ack uncertainty
  preserves event identity/content and remains retryable; no silent drop.
- Consumers preserve exact source bytes/nulls/ordered duplicate headers, namespace,
  coordinates, Kafka/ingress timestamps and a length-delimited raw-byte fingerprint.
  Automatic commit/store is disabled. Explicit durable markers gate contiguous
  delivered prefixes; partial commits release only acknowledged partitions. Revoke
  commits only durable prefixes; lost/old ownership cannot commit new assignments.
- Worker declarations split 2,000 records/16 MiB across one/three workers, including
  remainders. Static indexes, worker-thread ownership, native queue/fetch headroom,
  pause/resume and heartbeat polling are explicit. Oversized sources rewind/fail
  visibly without offsets advancing; no source/Gold success is fabricated.
- `shared/local_diagnostics/{__init__.py,schema.sql}`: caller-owned Connection
  helper/table template. Missing outbox fails before writing; savepoints also roll
  back a caught non-SQL append failure. Same-ID same-content retry is idempotent;
  altered identity conflicts. No service migration or alternate outbox was supplied.
- `shared/contracts/events.py`: typed source/validation/commit results; optional
  envelope/metadata values survive serialization. Diagnostic/DLQ services include
  analytics separately from business producers. All six domain/DLQ schema hashes
  are regenerated and backward-compatible against the actual retained registry.
- `shared/event_transport/schemas.py`, `contracts/events/supported-history.json`:
  verify/cache six current and six released-M02 schema definitions/IDs. Older
  supported records validate offline; unknown/unpublished IDs remain unsupported.
- `tests/pipelines/{transport_doubles,test_transport,test_transport_live}.py` and
  the owned registry live test: explicit doubles, real delivery/offset/rebalance,
  real SQL transaction behavior and actual schema-evolution evidence.

### Actual focused and live verification

Commands use `.venv/Scripts/python.exe` at repository root. Tests run with the
existing workspace-local scratch setup outside Windows sandbox ACL restrictions.

| Command/check | Actual outcome | Evidence |
|---|---|---|
| Initial `-m pytest tests/pipelines -q --tb=short` | **121 passed, 3 skipped**; initial lint formatting issues corrected without changing assertions | `artifacts/m03/offline-first.xml` |
| `-m pytest tests/pipelines tests/contracts -q --tb=short --junitxml=artifacts/m03/offline-verified.xml` | **236 passed, 6 skipped**, 26.93 seconds; opt-in infrastructure/live tests skipped in this offline invocation | `artifacts/m03/offline-verified.xml` |
| Final same focused suites after escaped-invalid-Unicode hashing guard | **237 passed, 6 skipped**, 23.56 seconds; unsupported escaped Unicode returns INVALID_JSON rather than crashing canonical hashing | `artifacts/m03/offline-final-verified.xml` |
| Workflow integration lint/format and `-m pytest tests/integration -q --tb=short --junitxml=artifacts/m03/integration.xml` | **45 passed**, 10.02 seconds | `artifacts/m03/integration.xml` |
| Owned Ruff lint/format and `git diff --check` | Passed | Session |
| `PROJECTCTL_ADAPTER_MODULE=infra.streaming` and `-m projectctl env up --profile streaming-local` | Exit 0. Retained resource profile/volumes; all current and released history schemas read-verified | `artifacts/projectctl/22cf29ed-149a-4268-b60c-00b2548e57d7/` |
| `RUN_TRANSPORT_LIVE_TESTS=1`, `-m pytest tests/pipelines/test_transport_live.py -q` | **3 passed**, 6.82 seconds: real broker/offset/rebalance and SQL savepoints with an explicit outbox double | `artifacts/m03/live-first.xml` |
| Final history-aware live run with `RUN_TRANSPORT_LIVE_TESTS=1`, `RUN_CONTRACTS_LIVE_TESTS=1`; `-m pytest tests/pipelines/test_transport_live.py tests/pipelines/test_event_contracts_live.py -q --tb=short --junitxml=artifacts/m03/live-history-verified.xml` | **4 passed**, 12.76 seconds; known old ID validated, all six subjects accept safe evolution/reject breaking or unsafe typed optional additions | `artifacts/m03/live-history-verified.xml`, `kafka-sdk.json`, `rebalance.json`, `diagnostics-sql.json` |
| `-m projectctl env verify --profile streaming-local` with explicit adapter | Exit 0; real infrastructure and all 12 current/released mappings verified | `artifacts/projectctl/cb6e272c-c322-4fee-a29d-f9bcd30ff77f/` |
| `-m projectctl env down` with explicit adapter | Exit 0, all volumes retained; Docker Desktop stopped after no other containers were running | `artifacts/projectctl/17e388e9-ebed-4576-9b83-690d5a2872d2/` |

Earlier intermediate offline/live XMLs are preserved, including the initial
four-live-test pass in `live-final.xml`. No failed test was removed or weakened.
The final SDK namespace is `bench-m03-3d51729df9914425aa74932f26ac0e07`; rebalance
namespace is `bench-m03-r-fbf8ed33f78b41bdaf99f4e8e77c78cb`. Released conversation
schema ID 9 is verified/cached alongside six latest schemas. Latest local IDs are
17/18/19/20/21/22 for conversation/inventory/order/payment/retrieval/DLQ respectively;
IDs are local evidence, not portable constants.

The SQL test uses a real analytics connection and a randomly named isolated schema
with an explicit transactional outbox double; it does not write operational service
databases. Caller rollback, caught append-failure rollback, one-row retry and
altered-ID rejection all pass. The isolated SQL schema is removed after evidence;
Kafka fixture topics and all project data volumes are retained. Native consumer
durability markers in the transport smoke are fixture assertions, not actual
M04/M05 source-to-Gold processing.

### Remaining adoption and checkpoint

Aditya must provide the real shared outbox. Each service owner applies the diagnostic
template and wires startup/readiness/cache/revision/transaction bindings described
in the handoff. Signature choices for group handles, explicit durable markers and
source_record=null for coordinate-free validation are documented for consumer
review. No business implementation, dependency lock, shared caller, CSV importer,
Bronze/Silver/Gold or performance result was changed/claimed. Next is M04 durable
FileStore/Bronze/actual source receipts. CI-equivalent checks are recorded below.

### CI-script verification

- Source checkpoint: `55b397b`. No application dependency/lock or other owner's
  implementation changed. A local source hash snapshot is retained in
  `artifacts/m03/source-snapshot.json`.
- `.venv/Scripts/python.exe benchmarks/manual/verify_p5.py`: exit **0**, all
  **11/11** expected outcomes matched. Its pytest suite passed **626 tests** in
  **121.58 seconds**; lint, format, generated schema/contract checks, observation
  rebuild and committed-source guards passed. Evidence:
  `artifacts/p5/3899e813-1c35-47d9-a855-dab8a4b5f878/`.
- The contracts inventory retains its expected dependency exit **4**: absent
  Harsh/Aditya providers and full G0 are visible, not replaced by SDK test doubles.
  Observer fixture results are not a real system/performance measurement.
- `.venv/Scripts/python.exe benchmarks/manual/verify_p6.py --out artifacts/m03/p6`:
  exit **0**, all **10/10** inner checks matched; **949 tests passed** in
  **246.50 seconds** with 121 existing JUnit `record_property` warnings. Real
  PostgreSQL 18.6 ran in an isolated 512-MiB Docker container. Restart retained
  container/image/volume identity and the resumed SQL smoke passed. Evidence:
  `artifacts/m03/p6/{docker-summary,docker-checks}.json`,
  `artifacts/m03/p6/checkpoint/{checks.json,pytest.xml,smoke/}`. Its event/outbox
  dependencies remain explicit test doubles, not real shared-outbox integration.
- All local workflow-equivalent checks passed sequentially, including the 45
  integration checks above; no timing assertion, test or expected dependency exit
  was weakened. Raw evidence remains ignored. The isolated P6 container is stopped
  with its volume retained; Docker Desktop is stopped after confirming no other
  running containers.

## M02 correction — Accepted receipt and CI regression, 31 October 2026

The user confirmed Jaineel's agreement with the detailed receipt format and
explicitly authorized updating the shared fixture/tests. This supersedes the
receipt-review blocker in the historical M02 entry below; other producer/G0
reviews remain pending.

- Updated `tests/contracts/provisional.py` and its generated
  `contracts/fixtures/p2/pairs.json` with namespace, source coordinates, raw hash,
  durable-stage timestamps and `timing_validity=missing`. Silver/Gold timing and
  visibility remain null in this synthetic missing-timing fixture.
- Updated `tests/contracts/test_contracts.py` to require analytics presence and
  receipt compatibility, while preserving missing Harsh/Aditya handoffs and
  NOT_RUN metrics. Added actual OpenAPI/DTO coverage that rejects the old shape.
- Recorded the user-reported agreement in the analytics module/OpenAPI generator,
  regenerated OpenAPI, and updated the owned plan/review handoff.
- `python -m pytest tests/contracts tests/pipelines -q --tb=short
  --junitxml=artifacts/m02-ci-fix/focused.xml`: **210 passed, 3 skipped**. All skipped
  tests explicitly require unrelated opt-in live Kafka/PostgreSQL checks.
- `python -m projectctl contracts check --all`: expected dependency exit **4**;
  `receipts-missing-timing` passes and no correctness FAIL remains. Full G0 is
  still incomplete. Evidence: `artifacts/projectctl/3e3991e5-fc28-4c24-8dcb-3e517bf2d99a/`.

### CI-script verification

- Locked dependency sync passed without changing the lock. Shared fixture JSON
  matches its generator; owned/shared lint and format checks passed.
- The remaining workflow steps for integration lint/format and
  `python -m pytest tests/integration -q --tb=short
  --junitxml=artifacts/m02-ci-fix/integration.xml` passed: **45 tests**.
- First `python benchmarks/manual/verify_p5.py` attempt, run concurrently with
  P6: 10/11 checks matched. The pytest step had **625 passed, 1 failed** in
  174.57 seconds. The failure was the existing 61-ms real-process telemetry
  sampler expecting four CPU samples but observing two; the receipt regression
  passed. Raw evidence is preserved at
  `artifacts/p5/8f3459f3-58d9-4eb1-9f9d-a6aa0d50eb6d/`.
- The unchanged telemetry test passed in isolation: **1 passed**, 1.14 seconds,
  `artifacts/m02-ci-fix/telemetry-isolated.xml`. No telemetry code, timing budget,
  expected sample count or assertion was relaxed.
- Serial `python benchmarks/manual/verify_p5.py` rerun passed, exit **0**:
  **11/11 checks matched**, including **626 tests passed** in 118.858 seconds,
  schema regeneration checks, the expected dependency-only contract inventory,
  observer/report reconstruction and clean source guards. Evidence:
  `artifacts/p5/1e27973f-b8f4-434b-8a8b-cf89bcd4ca8e/{checks.json,pytest.xml}`.
- `python benchmarks/manual/verify_p6.py --out artifacts/m02-ci-fix/p6` passed,
  exit **0**, using a real isolated Docker PostgreSQL **18.6** container capped
  at 512 MiB. All 10 inner verification commands matched, including **949 tests
  passed** in 245.855 seconds. The smoke and post-restart resume passed; the
  container ID/data volume were retained and the server start time changed.
  Evidence: `artifacts/m02-ci-fix/p6/{docker-summary.json,docker-checks.json}`
  and `checkpoint/{checks.json,pytest.xml,smoke/}`. Its event/outbox collaborators
  remain explicitly test doubles; no real shared checkout gate is claimed.
- Stopped only the verified isolated P6 test container, retained its volume,
  and stopped Docker Desktop after confirming no other containers were running.

No database format, event schema ID, application lock or deployment was changed.
All workflow-equivalent local checks now pass. The initial failed run is retained
alongside the successful serial run; full shared-service/G0 completion remains
incomplete and was not relabelled as a pass.

## M02 — Contracts implemented; team review pending, 31 October 2026

Branch: `vichitr`. Owned offline and real registry/wire checks pass. This is a
reviewable contract proposal, **not G0 sign-off**. The full shared suite exposes
one historical inventory/receipt-fixture failure requiring Jaineel's review.

### Changes and scope

- `shared/contracts/events.py`: 24 business payload snapshots, envelope/metadata,
  local diagnostic/DLQ shape, reason enum, publish acknowledgement, ownership,
  key/aggregate/version/state/provenance checks and strict known fields.
- `contracts/events/`: six self-contained draft-07 schemas, hash manifest and
  usage guide; `contracts/dictionaries/events/reasons.v1.json`: the 18 reasons.
- `shared/contracts/analytics.py`, `contracts/http/analytics.yaml`: canonical
  manifest/candidate/source range/reconciliation/batch DTOs and proposed receipt,
  quarantine and replay bindings for the six exact analytics endpoints. Internal
  authentication matches the existing `Authorization: Bearer` client proposal.
- `shared/event_transport/schemas.py`: actual registration/read-back, complete
  pinned cache, online policy/mapping checks and pure wire validation. Broker
  wrappers and the service-local transactional helper remain M03.
- `infra/contract_assets.py`: reproducible owned asset generation from models;
  `infra/streaming.py` and `infra/STREAMING.md`: schema-aware existing CLI startup
  and verification, preserving the same low-memory infrastructure profile.
- `tests/pipelines/{event_examples.py,fixtures/events.v1.json,test_event_contracts.py,test_event_contracts_live.py}`:
  synthetic valid/invalid contracts, consumer OpenAPI binding and real wire tests.
- [M02 decision/review handoff](m02_contract_handoff.md): concrete field choices,
  existing receipt mismatch, affected owners, migration/review and verification.

No shared canonical spec, dependency lock, consumer implementation/test, raw CSV,
service migration, business database, operational producer or Gold pipeline was
changed. Optional unknown properties/nulls remain in the immutable parsed wire
document; content hashes cover that document, including event/production times.

### Actual verification

All Python commands below use `.venv/Scripts/python.exe` from the repository root;
pytest runs outside the Windows filesystem sandbox using workspace-local scratch
directories, matching the existing infrastructure test arrangement.

| Command/check | Actual outcome | Evidence |
|---|---|---|
| `-m infra.contract_assets`; owned Ruff check/format | Generated assets reproducible; lint/format passed | Source tests/session |
| Initial contract test collection | Failed relative import; added owned test package initializer | `artifacts/m02/contracts-first.xml` |
| Second focused run | 58 passed; timestamp reason mismatch and two Windows environment-size errors caused by an oversized pytest case ID; fixed classification and bounded IDs | `artifacts/m02/contracts-second.xml` |
| First complete owned run | 99 passed, 2 live tests skipped | `artifacts/m02/offline-first.xml` |
| `-m pytest tests/pipelines -q --tb=short --junitxml=artifacts/m02/offline-final.xml` | **107 passed, 3 skipped**; all three live tests are opt-in | `artifacts/m02/offline-final.xml` |
| `-m pytest tests/pipelines tests/contracts tests/projectctl -q --tb=short --junitxml=artifacts/m02/regression-first.xml` | **336 passed, 3 skipped, 1 failed**; shared historical inventory assertion expects analytics absent/exit 4; new proposal exposes the known receipt conflict/exit 3 | `artifacts/m02/regression-first.xml` |
| Same broad suites, final rerun after the added malformed-input tests | **344 passed, 3 skipped, 1 failed**, 83.62 seconds; same documented shared inventory/receipt failure | `artifacts/m02/regression-final.xml` |
| `PROJECTCTL_ADAPTER_MODULE=infra.streaming` then `-m projectctl env up --profile streaming-local` | Exit 0; registered six actual JSON subjects, verified policy/ID/hash and infrastructure. Repeated after allowing legitimate multiword facets; registration remained backward compatible | `artifacts/projectctl/a12159ec-6e94-4a86-8648-5d0427b1f6a9/`, `artifacts/projectctl/d21a1997-8238-4ead-9140-861a732075cd/` |
| `RUN_CONTRACTS_LIVE_TESTS=1` then `-m pytest tests/pipelines/test_event_contracts_live.py -q --tb=short --junitxml=artifacts/m02/live-first.xml` | **1 passed**, real Kafka and registry, 25 acknowledged/read records | `artifacts/m02/live-first.xml` |
| Same live test, final expanded compatibility checks | **1 passed**, 8.09 seconds; all six subjects accept an unconstrained optional addition and reject both a breaking type and an unsafe typed optional addition to the open model. Old/new example validation and 25 exact-byte wire records pass | `artifacts/m02/live-final.xml`, `artifacts/m02/live-contracts.json` |
| `-m projectctl env verify --profile streaming-local` with explicit adapter | Exit 0; actual final infrastructure/schema mapping checks pass | `artifacts/projectctl/3966f6c7-6e78-4a65-b612-c990f0cfea9f/` |
| Stop live-check infrastructure | Mistakenly supplied startup-only `--profile` to `env down`, which returned 2. Corrected by stopping all three verified project containers directly, then `docker desktop stop`, exit 0. No volumes removed; final Desktop/backend process count 0 | `artifacts/projectctl/a6b8ac64-a5d5-485a-be60-36f32702f2da/`, session |
| Owned lint/format, whitespace and secret/file-scope audit | Passed. Secret audit required the existing elevated file access; no protected password values printed or included in changed files | Session |

The final live namespace is `bench-m02-41c04949c3914f6d943322b431b62dd0`.
The registry returned conversation subject ID 9/version 2, retrieval ID 10/version
2, inventory ID 4/version 1, order ID 5/version 1, payment ID 6/version 1 and DLQ
ID 8/version 1. These IDs are local facts, not portable constants. Complete
ID/hash definitions are retained in the ignored runtime mapping and live evidence.
Early local versions were test proposals; no operational traffic used them.

The broad suite's failure is preserved. `receipts-missing-timing` uses the earlier
provisional `silver_at` item, while the proposed DTO names/contains explicit source
and durable-stage fields. The shared inventory test also asserts the analytics
contract is missing. Jaineel owns those fixtures/tests. No assertion was weakened,
test skipped or consumer field silently rewritten to obtain a green shared gate.
See the handoff for exact old/new shapes and required provider/consumer review.

### Checkpoint and next handoff

M02's implementation and owned/live verification are ready for review. Producer
owners must approve their payloads; Jaineel must review receipt/pagination/source
range bindings and update his historical inventory fixture/test as agreed. G0,
real outbox integration, source-to-Gold correctness and benchmarks remain incomplete.
M03 is next: keyword-compatible builder/validation exports, acknowledged bounded
Kafka transport, offset handling and service-local diagnostics. Aditya's actual
outbox remains a dependency; an explicit test double cannot close real integration.

## M01b — Low-memory infrastructure passed, 31 October 2026

Branch: `vichitr`. PostgreSQL, Kafka **4.1.2** (single KRaft broker/controller) and
Confluent Schema Registry **8.1.0** are running. The `streaming-local` profile
caps PostgreSQL at 512 MiB/0.5 CPU, Kafka at 1,024 MiB/0.75 CPU and registry at
640 MiB/0.5 CPU: **2,176 MiB total**, within the observed Docker memory allowance.
The same PostgreSQL volume/credentials were reused. No Docker VM memory setting
was increased. **M01b passed; canonical domain contracts/full G0 and benchmarks
remain NOT_RUN.**

The supplied `data/raw/flipkart_com-ecommerce_sample.csv` is exactly 38,114,963
bytes and SHA-256 `56f8f699c9e847356666c2eab3c3ab1244340f6a98ad08e39ea2199ebe993ad1`.
It is Git-ignored and unchanged. No CSV normalization/import was implemented;
that remains Harsh's ownership.

### Changes

- `infra/compose.streaming.yaml`, `infra/streaming-profile.json`: low-memory
  overlay, pinned images, bounded JVM heaps, retained Kafka volume, local ports,
  internal DNS, real registry and shared lakehouse volume declaration.
- `infra/streaming.py`: existing CLI's `env up/verify/down` providers, explicit
  dev/bench/replay topic provisioning, partition/retention/ISR verification,
  registry compatibility and image/health/resource/volume checks. Existing topics
  are never repartitioned or silently reconfigured. Worker groups are declared;
  real groups form on consumer join/commit, as demonstrated by the smoke test.
- `infra/postgres.py`: reused credential preparation, explicit verification of
  either profile's PostgreSQL limits and bounded startup timeout support. No SQL
  migrations or credentials changed.
- `tests/pipelines/test_streaming*.py`: offline namespace/resource/idempotency
  checks and explicit real schema/JSON/broker/group/recreation smoke. PostgreSQL
  tests cover credential reuse and the smaller profile without weakening defaults.
- `infra/images.lock.json`: checksum-resolved images, actual version log lines,
  and smoke-tested states/evidence. `infra/STREAMING.md`, README and plan updated.

The canonical event/analytics contracts are still M02. The smoke subject is the
separate `infra-smoke.v1-value`, with registered ID/schema hash mappings in its
evidence. It is not a partially implemented business topic contract or an SDK.
FileStore, Bronze/Silver/Gold and operational business services remain later work.

### Commands and actual outcomes

Python module commands use `.venv/Scripts/python.exe -m`. Docker/live tests require
engine access outside the sandbox. No dependencies or the application lock changed.

| Command / check | Actual result | Evidence |
|---|---|---|
| CSV SHA-256/size and `git check-ignore` | Matches the supplied-file specification; ignored; no import | `artifacts/m01b/source-check.json` |
| Official Docker registry manifest GETs, computed SHA-256 versus response digest | Both match; immutable Kafka 4.1.2 and Registry 8.1.0 references recorded | `artifacts/m01b/kafka-resolution.json`, `schema-registry-resolution.json`, corresponding raw manifests |
| `docker pull --quiet <each pinned reference>` | Both images downloaded successfully | Session transcript; locks and runtime image checks |
| Initial `projectctl env up --profile streaming-local` | Exit 4: cold startup exceeded the original 180-second command budget | `artifacts/projectctl/0cd0b22a-9298-41a3-9d96-eb1d395b3bd4/` |
| Kafka startup diagnosis and configuration fix | Kafka started; extra JVM health probes were costly. Replaced them with a TCP probe; actual Kafka metadata/config checks remain mandatory in the CLI. Streaming `up` now has a bounded 600-second command budget | Source config and session transcript |
| Retried `projectctl env up --profile streaming-local` with `PROJECTCTL_ADAPTER_MODULE=infra.streaming` | Exit 0; three services, six dev topics and shared volume verified | `artifacts/projectctl/11f1f6e9-e5e9-45eb-8953-168ac63e68c8/` and matching infrastructure checks |
| `pytest tests/pipelines -q --junitxml=artifacts/m01b/offline.xml` | 32 passed, 2 explicit live skips | `artifacts/m01b/offline.xml` |
| Expanded final offline suite, same command with `--junitxml=artifacts/m01b/offline-final.xml` | **39 passed, 2 explicit live skips**, exit 0, 3.26 seconds | `artifacts/m01b/offline-final.xml` |
| First explicit live streaming test with `RUN_STREAMING_LIVE_TESTS=1` | Fixture failed because a temporary AdminClient was destroyed before its asynchronous request completed. Retained the client until the request finished; no assertions removed | `artifacts/m01b/live.xml` |
| `pytest tests/pipelines/test_streaming_live.py -q --junitxml=artifacts/m01b/live-verified.xml` | **1 real test passed**, zero skips, 98.48 seconds | `artifacts/m01b/live-verified.xml` |
| Real smoke/recovery evidence | Registered compatible JSON schemas; incompatible candidate check false; broker-acknowledged plain JSON/headers; both independent groups received the record; message/group offset and schema retained after both containers were recreated | `artifacts/infra/streaming-local/checks/03fe5730-05d9-41a1-b0ff-cca4c185ddd7/live-test.json` |
| Actual Kafka/Registry startup version log lines | 4.1.2 / 8.1.0, matching locked images | `artifacts/m01b/version-evidence.json` |
| Final repeated CLI `env up` | Exit 0; existing topics/data/settings reused | `artifacts/projectctl/850c2606-9d57-4595-a928-7ba8332fa681/` |
| Final CLI `env verify` | Exit 0; all declared infrastructure verified | `artifacts/projectctl/d3e048a9-6aad-4099-9b26-607f69d664b4/` and matching infrastructure checks |
| One final `docker stats --no-stream` sample | PostgreSQL 40.57 MiB, Kafka 351.4 MiB, Registry 203 MiB; a single sample, not a peak or performance result | `artifacts/m01b/final-memory-sample.txt` |

Six `dev` topics use one partition, one replica and seven-day retention; the DLQ
notification topic remains separate from the five business topics. Kafka retains
registry metadata in `_schemas`; the named shared lakehouse volume is provisioned
for the later FileStore. No development data, volumes or benchmark evidence were
deleted. Failed smoke namespaces remain for diagnosis/retention.

### Next handoff

- M02: canonical business/DLQ schemas, event dictionaries, event/analytics DTOs,
  analytics OpenAPI and producer/consumer review. G0 is not claimed from the fixture.
- M03: real event transport SDK and local diagnostics, integrating Aditya's outbox
  when supplied. No substitute outbox was added.
- Shared-template conflict to review with Jaineel: `.env.example` specifies
  `RUN_NAMESPACE=local-dev`, while common §7 specifies `dev` or isolated bench/replay
  namespaces. This infrastructure provisions `dev`; the shared file was not changed.
- Jaineel coordinates a smaller, fully declared evaluation profile once application
  services exist and the full stack is measured. This development profile is not a
  replacement evaluation config or a claim that 500 events/s is sustainable.

Setup instructions: `infra/STREAMING.md`. No commit or push was requested/performed.

## M01a — Live verification passed, 31 October 2026

PostgreSQL is running on `127.0.0.1:5432`. The pinned image actually supplies
PostgreSQL **18.2**, with pgvector **0.8.1** installed in `catalog_db`. All six
databases passed service-login, privilege, durability and resource checks.
**M01a passed; full M01/G0 remains incomplete until Kafka/Schema Registry and
the remaining contracts/profile checks are supplied.**

Docker Desktop was installed by the user. Docker's Linux engine is 29.9.2,
Compose is 5.6.1, and WSL2 reports 8 CPUs / 4,040,888,320 bytes of engine memory.
The proposed full 8-GiB SUT budget is not available in this Docker VM yet; the
PostgreSQL-only 0.75-core/2-GiB allocation was verified. No engine settings changed.

### Changes from the initial checkpoint

- Distinguished a Docker command timeout from a missing Docker installation.
  The timeout still fails visibly and instructs checking container state before retry.
- Added nonsecret live-test evidence for all 30 denied cross-database connections,
  different before/after container IDs, the retained volume and persisted marker.
- Updated `infra/images.lock.json` to `SMOKE_TESTED` using actual server facts and
  the live evidence path. The offline lock check now validates both the unresolved
  and smoke-tested lifecycle states, including required evidence/version fields.
- Updated the README and plan. No business migrations, imports, commits or pushes.

### Commands and actual outcomes

Use `.venv/Scripts/python.exe -m` for the Python module commands below.
`PROJECTCTL_ADAPTER_MODULE=infra.postgres` selects the existing CLI's owned adapter.
Docker/live pytest calls required access outside the sandbox for the engine pipe
and pytest's Windows scratch-directory ACLs.

| Command / check | Actual result | Evidence |
|---|---|---|
| `docker version`, `docker info --format ...`, `docker compose version --short` | Engine running on linux/amd64; versions/resource facts recorded | `artifacts/m01a/docker-environment-20261031.json` |
| First `projectctl env up --profile postgres-local` | Exit 4: 180-second Docker command timeout during cold startup; container continued initialization on its retained volume | `artifacts/projectctl/1c7571d3-cff1-41a6-ae87-e3dc54d726f3/` |
| Second `projectctl env up --profile postgres-local` | Exit 4: database check failed; no reset performed. Direct verification subsequently passed all six databases; exact transient DB error was not retained by the safe CLI boundary | `artifacts/projectctl/635e0215-510a-4bac-a85e-143ce89e59ad/` |
| `pytest tests/pipelines -q --junitxml=artifacts/m01a/docker-live-20261031.xml`, with `RUN_POSTGRES_LIVE_TESTS=1` | **19 passed, zero skipped**, exit 0, 36.57 seconds | `artifacts/m01a/docker-live-20261031.xml` |
| Real isolation/recreation proof from that test | All 30 cross-service connections denied; container ID changed; data-volume identity and stored marker preserved; probe removed | `artifacts/infra/postgres-local/checks/7671ad46-0834-4918-ab03-3a1be5ce3888/live-test.json` |
| Final `projectctl env up --profile postgres-local` | Exit 0; existing container/credentials/volume reused | `artifacts/projectctl/663452c9-ea1f-4ead-9a09-1970fa1f4793/` |
| Final `projectctl env verify --profile postgres-local` | Exit 0; running database verified | `artifacts/projectctl/67103724-78e4-4c3c-9e3a-ac36a55e8166/` and matching `artifacts/infra/postgres-local/checks/67103724-78e4-4c3c-9e3a-ac36a55e8166/postgres.json` |
| `pytest tests/pipelines/test_postgres.py -q --junitxml=artifacts/m01a/post-smoke-offline-20261031.xml` | **18 passed**, exit 0, after updating the smoke-tested lock | `artifacts/m01a/post-smoke-offline-20261031.xml` |
| Final Ruff lint and format checks | Passed after formatter wrapped the timeout diagnostic | Session transcript |

The running named volume is `group3-postgres-local_postgres_data`. Local URLs and
passwords remain in the ignored `artifacts/infra/postgres-local/` directory; no
credentials are copied to evidence. Kafka, registry, business tables, source import
and performance results remain NOT_RUN. Next checkpoint: Kafka/Schema Registry in
M01, including a feasible full-stack resource profile and locks.

## M01a — Initial foundation, 31 October 2026

Branch: `vichitr`. Implementation and offline checks are ready. **Real Docker
startup, isolation and persistence remain NOT_RUN**, because Docker is not installed
on this machine. The user will install Docker Desktop. Full M01/G0 is not complete.

### Changes

- `infra/compose.yaml`: pinned PostgreSQL 18 / pgvector 0.8.1 image, persistent
  named volume, loopback-only port, TCP health check, seven file-mounted secrets,
  PostgreSQL-only enforced resource allocation and owner labels.
- `infra/postgres/10-databases.sh` and `infra/.gitattributes`: first-volume
  initialization of six service logins/databases, restricted database privileges,
  catalogue vector extension and LF checkout for the Linux shell script.
- `infra/images.lock.json`: registry-resolved manifest digest, supported Linux
  architectures and explicit unverified smoke status. Actual server patch/evidence
  remains null until Docker runs.
- `infra/postgres.py`: existing `projectctl` providers for PostgreSQL-only
  `env up/verify/down`; private generated credentials; retained-volume shutdown;
  runtime image/resource/role/version/durability checks and safe evidence.
- `tests/pipelines/`: offline dependency/security checks, workspace-local pytest
  configuration using Jaineel's existing convention, and opt-in real Docker test
  for cross-database denial and persisted data after container recreation.
- `infra/README.md`: setup, credentials, boundaries, verification and recovery notes.
  `docs/vichitr/implementation_plan.md` remains the module sequence.

No teammate's service code, migrations, shared tooling, dependencies, lock or
evaluation configuration was changed. No commit or push was performed.

### Commands and actual outcomes

All commands ran from the repository root unless noted. `.venv/Scripts/python.exe`
below is Python 3.11.15 installed from the repository's locked environment.

| Command / check | Actual outcome | Evidence |
|---|---|---|
| `docker version`, `docker compose version` and standard install-path checks | Docker unavailable; user confirmed not installed | Session transcript |
| Initial `python -m pip install --target artifacts/tooling/uv-package uv==0.10.8 --disable-pip-version-check` | Failed to resolve under restricted network | Session transcript |
| `python -m pip --isolated install --index-url https://pypi.org/simple --no-cache-dir --target artifacts/tooling/uv-package uv==0.10.8 --disable-pip-version-check` | Passed with approved network access; workspace-local uv 0.10.8 | `artifacts/tooling/uv-package/` |
| Workspace-local `uv.exe sync --locked --python 3.11`, with workspace `UV_CACHE_DIR` and `UV_PYTHON_INSTALL_DIR` | Passed with approved network access; Python 3.11.15 and 37 packages installed from unchanged lock | `.venv/`, `artifacts/tooling/python/` |
| Official Docker registry token/manifest GET using Python urllib | SHA-256 over manifest bytes matches response digest; Linux amd64/arm64 available | `infra/images.lock.json` and `artifacts/m01a/registry-resolution.json` |
| Initial Ruff lint then format | Five line-length findings; formatter corrected all | Session transcript |
| Initial focused pytest with explicit basetemp/cache and JUnit | 3 passed, 15 errors, 1 skipped; missing temp parent | `artifacts/m01a/pytest.xml` |
| Rerun after workspace scratch configuration | Windows sandbox ACL denial on pytest private temp directory | Session transcript |
| `python -m pytest tests/pipelines -q --junitxml=artifacts/m01a/offline-verified.xml` using `.venv`, outside sandbox | **18 passed, 1 skipped**, exit 0; skipped test requires real Docker | `artifacts/m01a/offline-verified.xml` |
| `python -m pytest tests/pipelines tests/projectctl -q --junitxml=artifacts/m01a/final-checks.xml` using `.venv`, outside sandbox | **154 passed, 1 skipped**, exit 0, 71.03 seconds; includes existing CLI regression tests | `artifacts/m01a/final-checks.xml` |
| `python -m ruff check infra/postgres.py tests/pipelines` using `.venv` | Passed | Session transcript |
| `python -m ruff format --check infra/postgres.py tests/pipelines` using `.venv` | Passed | Session transcript |
| Git Bash `-n infra/postgres/10-databases.sh` | Sandbox signal-pipe failure; approved read-only rerun outside sandbox passed, exit 0 | Session transcript |
| `python -m projectctl env verify --profile postgres-local` with explicit adapter | Expected exit 4, Docker unavailable; real checks NOT_RUN | `artifacts/projectctl/17d0fb15-048d-4ef4-a14a-246da3c17387/` |
| `python -m projectctl env up --profile postgres-local` with explicit adapter | Expected exit 4, Docker unavailable; no database or credentials created | `artifacts/projectctl/c6084735-a918-4fdc-b6b4-082506e1ee0b/` |
| Final Ruff lint/format, `git diff --check`, owned-path/local-link/whitespace/LF checks | Passed; changes confined to owned paths; no runtime credentials created | Session transcript |

`PROJECTCTL_ADAPTER_MODULE=infra.postgres` selects the owned providers; it does not
replace Jaineel's registry or create a competing CLI. Offline test doubles are
explicitly test-only. No synthetic performance values or real integration pass
are claimed. Connection-denial assertions use libpq's failure message because
connection-establishment errors do not expose a PGresult SQLSTATE.

### Next checkpoint and handoffs

1. User installs and starts Docker Desktop with Linux containers/WSL as required
   by Docker's installer. No Windows features or Docker installation were changed.
2. Run the README's `env up`, `env verify` and opt-in live test. Resolve any real
   initialization/permissions/port/resource issues, preserve evidence and then
   update the image smoke status with actual server facts.
3. Give teammates generated URL variable names and reproducible setup instructions,
   never another user's passwords. Each owner applies only their own migrations.
4. Finish M01 with Kafka/Schema Registry, schema-dependent readiness and the full
   enforceable resource profile. Reset/migration dispatch remains a later scoped
   handoff; no destructive reset provider exists at M01a.

Do not mark M01a's real acceptance or M01/G0 complete before the missing checks run.
