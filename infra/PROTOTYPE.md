# Local prototype deployment (Vichitr)

This is a development launcher for the existing application. It uses the same
PostgreSQL/Kafka/registry containers and retained volumes as `streaming-local`.
It does not change `configs/evaluation_profiles.json` or certify an evaluation.

The nine application containers contain six APIs (ports 8001–8006), the catalogue
stock consumer, the analytics consumer/publisher, and a development relay process.
That last process hosts five independent instances of Aditya's shared outbox
relay, one per operational database, with separate codecs, connections and Kafka
publishers. Analytics retains its existing worker-zero notification relay.
Use the separate API/worker/relay allocations for official evaluations.

All APIs bind to loopback. Fixed assistant mode makes zero generative calls;
benchmark and fault-injection flags are false. Source/cache mounts are read-only;
the lakehouse remains on the Docker Linux volume. No product image downloads,
model downloads, destructive reset or volume removal are performed.

## Start

Run from the repository root using the locked Python 3.11 environment and Docker
Desktop's Linux engine:

```powershell
$env:PROJECTCTL_ADAPTER_MODULE = 'infra.prototype'
.venv/Scripts/python.exe -m projectctl env up --profile prototype-local
```

The launcher checks memory/CPUs, starts/verifies the existing streaming stack,
checks the other owners' database tables read-only, applies only analytics-owned
migrations, provisions the namespace's topics, builds the existing locked image,
then starts and verifies every application container. Actual container health and
individual CPU/RAM limits are recorded without credentials. No workflow or
acceptance result is inferred from process health.

The prototype defaults to `dev`. On the first launch, an explicit `RUN_NAMESPACE`
can instead select a `bench-` namespace. The original namespace/run identity is
retained in `artifacts/infra/prototype-local/context.json`; the launcher refuses a
namespace change. `CODE_COMMIT` is the actual checkout HEAD. Development mounts
may include uncommitted edits; this is not a clean-source evaluation proof.

Local bindings are generated privately in `artifacts/infra/prototype-local/.env`.
Passwords are reused from the existing PostgreSQL secret files; the internal
token is generated once and retained. A missing retained token fails rather than
silently rotating it. Do not commit or share these files. Import the host-side
bindings for the existing owner commands without printing them:

```powershell
Get-Content artifacts/infra/prototype-local/.env | ForEach-Object {
    $name, $value = $_ -split '=', 2
    [Environment]::SetEnvironmentVariable($name, $value, 'Process')
}
```

The launcher uses its generated database credentials/token consistently across
containers; it does not adopt placeholder URLs/tokens from `.env.example`.

## Owner prerequisites and data

The first startup may stop at `schema-prerequisites`. The message names the
database and missing tables. Conversation, Catalogue and M3 migrations remain
their owners' responsibility. The launcher does not execute another owner's SQL
files or mark partial global migrations successful. M1 has an existing command:

```powershell
.venv/Scripts/python.exe -m services.conversation.database
```

Harsh's existing importer applies/checks catalogue migrations. Aditya must supply
the operational migration setup for Orders, Inventory and Payments. Once those
schemas are ready, run the existing owner commands in the Linux setup container.
Native Windows cannot provide the directory fsync required by catalogue artifacts.
The 768-MiB setup helper must run while the application containers are stopped:

```powershell
$compose = @('compose', '--project-name', 'group3-postgres-local', '--env-file', 'artifacts/infra/prototype-local/.container.env')
@('compose.yaml', 'compose.streaming.yaml', 'compose.catalog.yaml', 'compose.analytics.yaml', 'compose.prototype.yaml') | ForEach-Object {
    $compose += @('--file', "infra/$_")
}
docker @compose stop --timeout 40 conversation catalog catalog-worker orders inventory payments analytics analytics-worker prototype-relays
docker @compose run --rm --no-deps prototype-setup python -m projectctl catalog import --source data/raw/flipkart_com-ecommerce_sample.csv --rules flipkart-v1 --load-mode copy --namespace $env:RUN_NAMESPACE --out prototype-volume/prototype-data
docker @compose run --rm --no-deps prototype-setup python -m projectctl catalog verify --namespace $env:RUN_NAMESPACE --manifest prototype-volume/prototype-data/normalized_manifest.json
docker @compose run --rm --no-deps prototype-setup python -m projectctl inventory seed --namespace $env:RUN_NAMESPACE --sku-manifest prototype-volume/prototype-data/sku_manifest.json --profile performance --seed 42
docker @compose run --rm --no-deps prototype-setup python -c "from pathlib import Path; from shutil import copyfile; p=Path('/app/artifacts/prototype-data'); p.mkdir(parents=True,exist_ok=True); copyfile('/app/prototype-volume/prototype-data/sku_manifest.json',p/'sku_manifest.json')"
.venv/Scripts/python.exe -m projectctl env up --profile prototype-local
.venv/Scripts/python.exe -m projectctl projection wait --namespace $env:RUN_NAMESPACE --sku-manifest artifacts/prototype-setup/prototype-data/sku_manifest.json --timeout-seconds 600
```

The normalized files and authoritative manifests remain in
`lakehouse_data/prototype-data`, mounted at `/app/prototype-volume/prototype-data`
inside the helper. The host SKU manifest is a copy for the existing read-only
projection-readiness command. The source CSV is mounted read-only inside `/app`
so the existing CLI's repository-path checks are preserved. Setup CLI evidence
is retained under `artifacts/prototype-setup/projectctl` on the host.

Use an appropriate fresh namespace for the initial seed. The seed command owns
its existing idempotency checks and refuses incompatible prior data. Existing
namespaces and unrelated QA schemas are never cleared by this launcher.
The `performance` seed option selects the existing 10,000-unit stock recipe; it
does not start a performance run. For a tight-memory machine, import before
starting all application containers. Stock events remain in the real Inventory
outbox until the relays start; projection must catch up before the demo.

`env up` means the processes and required schemas are available. A complete demo
still needs Jaineel's client/workflow to perform explicit confirmation and the
existing transaction services to complete the saga. Payment success/decline,
stock release, retry idempotency and resulting queryable Gold must be observed
separately. Known transaction behavior fixes remain with Aditya.

The stock worker, analytics worker and operational relay container use
`on-failure:3` in this development overlay. A transient database or broker error
can terminate a worker after its own retries; Docker then restarts it from its
retained state, with at most three retries for consecutive failures. An
intentional Compose stop does not restart it. Inspect a repeatedly failing
worker before retrying; this policy does not establish data readiness or repair
a persistent error.

## Resources, verification and shutdown

Container RAM ceilings total **3,584 MiB (3.5 GiB)**, plus a required 256 MiB of
Docker VM headroom. CPU ceilings total 8 cores; Conversation and Catalogue get 1 core each, the other
APIs get 0.5 each and the stock worker, analytics worker
and combined relays get 0.75/1/0.5 cores. PostgreSQL/Kafka/registry keep 512/1,024/640 MiB. Operational
APIs, catalogue stock worker and combined relay process each get 128 MiB;
analytics API gets 192 MiB and its worker 320 MiB. These are low-traffic development
limits to verify on the actual host, not throughput or memory feasibility claims
for the official profiles. Stop other experiments before starting this stack.
The analytics API/worker use the existing O1 batching (100 rows, 50-ms bound),
with the same durable capture and 250-ms publication behavior. This is a prototype
configuration, not a B0/O1 comparison.

```powershell
.venv/Scripts/python.exe -m projectctl env verify --profile prototype-local
```

Read the currently published pipeline totals while the stack is running. The
date range is half-open; the end date must follow the start date:

```powershell
$from = (Get-Date).ToUniversalTime().Date
$url = 'http://127.0.0.1:8006/v1/analytics/gold/pipeline_minute?namespace=' + $env:RUN_NAMESPACE + '&date_from=' + $from.ToString('yyyy-MM-dd') + '&date_to=' + $from.AddDays(1).ToString('yyyy-MM-dd')
Invoke-RestMethod $url
```

Stop the stack when finished:

```powershell
.venv/Scripts/python.exe -m projectctl env down
```

Keep `PROJECTCTL_ADAPTER_MODULE=infra.prototype` for shutdown. It stops the nine
application containers first, then the three infrastructure containers. All
database files, lakehouse files, topics, offsets and secret files remain intact.
It does not quit Docker Desktop or stop unrelated containers. On startup failure,
inspect `artifacts/infra/prototype-local/checks/<run-id>/startup.jsonl` and the
reported streaming check directory; retained state is never deleted to retry.

To release Docker Desktop's VM memory after the stack has stopped:

```powershell
docker desktop stop --timeout 60
```

Focused offline checks:

```powershell
.venv/Scripts/python.exe -m pytest tests/pipelines/test_prototype.py tests/pipelines/test_catalog_relay.py -q
```
