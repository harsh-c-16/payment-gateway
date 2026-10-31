# M04 capture handoff

Owner: Vichitr. Implements common §11.1 and the capture/receipt foundations of §11.2.
This checkpoint does not claim the M05 Silver/Gold vertical slice or full G0/G1.

## Consumers and contracts

- Harsh: import FileStore from pipelines.storage. Run on the Linux named-volume
  mount, preserve original CSV bytes and supply your independently known row/schema
  metadata in your SourceManifest. No CSV parser/normalizer was added here.
- Vichitr M05: consume RawBatchReceipt/CapturedSource, read_bronze and persist_capture
  from the owned packages. Keep the source coordinate/raw hash separate from event
  identity. Existing captured rows are not yet final dispositions. Final source
  processing must remain one analytical transaction with Silver/Gold or quarantine
  and the real shared outbox, before worker durability markers/offsets.
- Jaineel: the SDK and receipt DTOs retain the accepted public schema. New capture
  DTOs are internal; do not return NULL-disposition rows through the receipts API.
  Wire the existing provider composition seam; no competing CLI was introduced.
- Aditya: actual outbox DDL/library is still absent. Quarantine's analytics table
  foundation exists, but notification/outbox and valid/invalid sink processing are
  not implemented by this module. There is no fake production outbox.

## Migration and runtime

Set PROJECTCTL_ADAPTER_MODULE=infra.analytics to compose existing streaming env
providers with this owner's db migrate provider. Run the existing command:

```powershell
$env:PROJECTCTL_ADAPTER_MODULE='infra.analytics'
python -m projectctl db migrate --namespace bench-smoke
```

It uses ANALYTICS_DATABASE_URL if explicitly supplied, otherwise the retained local
analytics credential. It applies only analytics/001_capture.sql. Global db migrate
returns dependency exit 4 until the other service/outbox owners compose their
providers; its reason/evidence explicitly confirms the analytics portion applied.
No namespace data reset or cross-service migration occurs. The callable
migrate_analytics(tx) requires an active owner transaction and never commits it.
Migration identity normalizes CRLF/LF and rejects changed applied SQL.

The Linux checker image uses the pinned Python 3.11.15 base in
infra/storage.Dockerfile and existing uv.lock. Build from a minimal scratch context
containing only that Dockerfile, pyproject.toml and uv.lock; never send .env, raw CSV
or artifact/secret directories as the build context. Example at repository root:

```powershell
New-Item -ItemType Directory -Force artifacts/m04/build-context | Out-Null
Copy-Item pyproject.toml,uv.lock artifacts/m04/build-context
Copy-Item infra/storage.Dockerfile artifacts/m04/build-context/Dockerfile
docker build -t group3-m04-storage:local artifacts/m04/build-context
$env:POSTGRES_SECRETS_DIR=(Resolve-Path artifacts/infra/postgres-local/secrets).Path
docker compose -p group3-postgres-local -f infra/compose.yaml -f infra/compose.streaming.yaml -f infra/compose.storage.yaml --profile storage-check run --rm --no-deps --env RUN_STORAGE_LIVE_TESTS=1 storage-check python -m pytest tests/pipelines/test_storage.py tests/pipelines/test_storage_live.py -q --tb=short --junitxml=artifacts/m04/storage-live.xml
```

Start/verify streaming-local first. The opt-in checker adds 512 MiB/0.5 CPU to the
existing 2,176-MiB stack, uses the existing retained lakehouse volume, mounts source
read-only, mounts only the analytics secret and writes ignored M04 evidence. It is
a verification worker, not a deployed ingestion service. No Docker RAM increase is
needed. Native Windows fails directory-fsync readiness; run durable writes inside
the Linux volume. The checker does not copy source/data/secrets into its image.

## Boundaries and remaining review

The fixed physical cap is 1 MiB of encoded wrapper bytes. Base64 makes a nearly
1-MiB raw invalid source exceed that cap, although the transport permits that raw
size. Such sources backpressure/fail with offsets untouched; a fragmentation/locator
extension needs owner review. Normal events (maximum 64 KiB) and tested malformed
fixtures fit. No schema/size change was silently made.

Fsync and rename evidence covers successful local Linux syscalls, injected failures,
an acknowledged process crash and retained-volume restart. It does not prove host
power-loss durability or volume redundancy. All writers must use FileStore on the
private tree. Orphan inventory never deletes; supply all retained/pinned references.
No active manifest, replay, performance or Gold visibility claim is made.

The owned pipeline tests now use importlib collection and remove the empty package
marker that shadowed the production pipelines namespace. Existing pipeline,
contract and integration tests are verified together; no shared pytest config or
another owner's test was edited. Exact evidence is in [progress](progress.md).
