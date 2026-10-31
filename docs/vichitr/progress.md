# Vichitr progress

Git delivery policy (31 October 2026): the user authorizes committing and pushing
each completed module to `vichitr` after its checks pass. The first delivery covers
the completed M01a/M01b infrastructure and planning notes. Credentials, the raw CSV,
generated data and local evidence stay outside Git. Earlier "not requested/pushed"
notes below describe those checkpoints before this standing authorization.

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
