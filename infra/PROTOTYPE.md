# Local prototype deployment (Vichitr)

For the prepared Windows machine, run `./start-prototype.ps1`, then open
http://127.0.0.1:8001/. Use `./stop-prototype.ps1` to remove this project's
containers while retaining volumes and images. The scripts delegate to the
commands below. See the [current browser demonstration](../docs/jaineel/PROFESSOR_DEMO.md).

For the presentation commands, versions, limits and the 12 November rehearsal, see
[DEPLOYMENT_INFO.md](DEPLOYMENT_INFO.md).

This is a development launcher for the existing application. It uses the same
PostgreSQL/Kafka/registry containers and retained volumes as `streaming-local`.
It does not change `configs/evaluation_profiles.json` or certify an evaluation.

The nine application containers contain six APIs (ports 8001–8006), the catalogue
stock consumer, the analytics consumer/publisher, and a development relay process.
That last process hosts five independent instances of Aditya's shared outbox
relay, one per operational database, with separate codecs, connections and Kafka
publishers. Analytics retains its existing worker-zero notification relay.
Use the separate API/worker/relay allocations for official evaluations.

The Windows desktop can enable Gemini conversation by setting
`SHOPPING_LLM_ENABLED=true`, `GEMINI_API_KEY=...` and
`SHOPPING_LLM_MODEL=gemini-3.5-flash-lite` in the ignored
`artifacts/infra/prototype-local/shopping-llm.env`. Only Conversation receives
these settings. Startup and generated bindings never display the key. The
browser selects AI conversation when configured and offers Deterministic chat
separately. Model errors preserve results and show a clear retry/mode choice.
Open http://127.0.0.1:8001/dashboard for the separate dashboard and live graphs.
See [the professor guide](../docs/jaineel/PROFESSOR_DEMO.md) for the presentation flow.

All APIs bind to loopback. Fixed assistant mode makes zero generative calls;
benchmark and fault-injection flags are false. Source/cache mounts are read-only;
the lakehouse remains on the Docker Linux volume. No product image downloads,
model downloads, destructive reset or volume removal are performed.

## Start

Run from the repository root using the locked Python 3.11 environment and Docker
Desktop's Linux engine. On a prepared deployment, start PostgreSQL, load the
retained private bindings and apply the repeatable M3 upgrades before starting
applications:

```powershell
$env:PROJECTCTL_ADAPTER_MODULE = 'infra.postgres'
.venv/Scripts/python.exe -m projectctl env up --profile postgres-local
Get-Content artifacts/infra/prototype-local/.env | ForEach-Object {
    $entry = $_ -split '=', 2
    [Environment]::SetEnvironmentVariable($entry[0], $entry[1], 'Process')
}
.venv/Scripts/python.exe -m services.orders.m3_setup
.venv/Scripts/python.exe -m services.conversation.database
.venv/Scripts/python.exe -m pipelines.catalog.migrate --variant prototype
$env:PROJECTCTL_ADAPTER_MODULE = 'infra.prototype'
.venv/Scripts/python.exe -m projectctl env up --profile prototype-local
.venv/Scripts/python.exe -m projectctl env verify --profile prototype-local
.venv/Scripts/python.exe -m projectctl projection wait --namespace $env:RUN_NAMESPACE --sku-manifest artifacts/prototype-setup/prototype-data/sku_manifest.json --timeout-seconds 600
.venv/Scripts/python.exe -m projectctl demo-check --namespace $env:RUN_NAMESPACE
```

Stop on a nonzero exit code. Retained data needs no import, seed or offset reset.
After startup, open **http://127.0.0.1:8001/** for the shopping website and chat.
The repeatable M1 migration includes the additive saved-conversation context.
See [shopping behaviour](../docs/specs/11_SHOPPING_EXPERIENCE.md), including how
keyword and optional hybrid retrieval differ. No frontend build is required.
The lock requires uv 0.10.8; an older global uv refuses this project. This prepared
Windows checkout has the pinned executable at
`artifacts/tooling/uv-package/bin/uv.exe`. Use its `sync --locked --python 3.11`
command when synchronizing the environment.

The explicit `prototype` catalogue variant adds a partial covering index for
eligibility counts; it changes no product or stock values. It is presentation
tuning, separate from base migrations and O2. Use a fresh evaluation schema for
B0/O2 comparisons, without this optional index. The prototype overlay enables
the existing bounded API connection pools. Its five operational outbox relays
poll every 250 ms; the separate relay default remains 25 ms. These settings do
not establish a measured optimization result.

## Enable the existing semantic retriever

With the retained PostgreSQL container running, private bindings loaded as above,
and the normal application image built, provision the locked model and vectors:

```powershell
.venv/Scripts/python.exe -m infra.retrieval setup
.venv/Scripts/python.exe -m services.conversation.database
$env:PROJECTCTL_ADAPTER_MODULE = 'infra.prototype'
.venv/Scripts/python.exe -m projectctl env up --profile prototype-local
.venv/Scripts/python.exe -m infra.retrieval verify
```

Setup installs the hash-pinned optional runtime in a separate image and fills
missing/changed embeddings in the existing namespace. It does not reimport,
reseed or reset data. It saves `artifacts/infra/prototype-local/retrieval.json`
only after the backfill succeeds. Subsequent normal launches retain the semantic
image, read-only model mount and 768 MiB catalogue allocation. The launcher counts
that larger allocation in its memory check; the core evaluation profiles and
dependency lock are unchanged. An interrupted backfill is resumable by rerunning
setup. It can take several minutes on CPU.

The website selects hybrid for chat when capabilities report complete current
embeddings; an explicit Keyword selection is retained. New shopping API sessions
also select available hybrid when no mode is specified. Follow-ups reuse that
mode and preserve filters/exclusions. Catalogue browsing, sorting and pagination
remain lexical reads. The original fixed-turn endpoint keeps its lexical default.
No generative model or model credential is needed for this local encoder.

`verify` creates one synthetic shopper session and searches through real M1/M2
HTTP APIs. It checks current model inference, strict colour/budget filters, disjoint more
options, similarity, persisted retrieval mode and zero generative calls, retaining
raw responses under `artifacts/retrieval/verify-*`. It sends no cart or purchase
command and makes no performance or relevance-quality claim.

On a first-time deployment without private bindings, run prototype `env up` once
to generate them, then follow the schema and data prerequisites before retrying.

The launcher checks memory/CPUs, stops retained applications that may have
restarted after a host crash, starts/verifies the existing streaming stack,
checks the other owners' database tables read-only, applies only analytics-owned
migrations, provisions the namespace's topics, builds the existing locked image,
then starts domain APIs, client APIs and each background worker in dependency
order. Each stage must become healthy within four minutes before the next starts,
reducing competing cold imports and connection attempts. Actual container health and
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

Harsh's existing importer applies/checks catalogue migrations. The repeatable
`python -m services.orders.m3_setup` command upgrades Orders, Inventory and
Payments using their private database URLs and preserves existing rows. Once those
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

`env up` means the processes and required schemas are available. The connected
client is already implemented; after preflight passes, run:

```powershell
.venv/Scripts/python.exe -m projectctl demo --namespace $env:RUN_NAMESPACE --user-id demo-professor --query "men's formal shirt"
```

Select a product and quantity, review the authoritative total/expiry, then type
exactly `CONFIRM <displayed-quote-id>`. The client prints its state path. Keep it
for safe resume and exact-order Gold verification:

```powershell
.venv/Scripts/python.exe -m projectctl demo --resume <state-path>
.venv/Scripts/python.exe -m projectctl demo-check --state <state-path> --wait-seconds 600
```

In a separate session, leave confirmation empty and verify no purchase is
submitted. Normal simulated payments may decline; `CANCELLED` must agree with
released stock and zero net debit. `MANUAL_REVIEW` and timeouts remain unresolved,
not successful demonstrations. Process health alone proves none of these facts.

The stock worker, analytics worker and operational relay container use
`on-failure:3` in this development overlay. A transient database or broker error
can terminate a worker after its own retries; Docker then restarts it from its
retained state, with at most three retries for consecutive failures. An
intentional Compose stop does not restart it. Inspect a repeatedly failing
worker before retrying; this policy does not establish data readiness or repair
a persistent error.

## Resources, verification and shutdown

For native API debugging against the retained Docker PostgreSQL container, carry
over the same bounded connection-pool configuration used by this overlay:

```powershell
'CATALOG', 'ORDERS', 'INVENTORY', 'PAYMENTS' | ForEach-Object {
    [Environment]::SetEnvironmentVariable("${_}_REUSE_CONNECTIONS", 'true', 'Process')
    [Environment]::SetEnvironmentVariable("${_}_MAX_CONNECTIONS", '4', 'Process')
}
$env:CONVERSATION_MAX_CONNECTIONS = '3'
```

Set these before starting native API processes. Otherwise the background workers
repeatedly open database connections instead of reusing them. Native APIs are
separate processes: Compose `env down` does not stop them. A PostgreSQL-only
shopping preview leaves Kafka, projection and Gold export stopped; it is not the
full-stack presentation or evaluation deployment.

Container RAM ceilings total **3,584 MiB (3.5 GiB)**, plus a required 256 MiB of
Docker VM headroom. CPU ceilings total 8 cores; Conversation and Catalogue get 1 core each, the other
APIs get 0.5 each and the stock worker, analytics worker
and combined relays get 0.75/1/0.5 cores. PostgreSQL/Kafka/registry keep 512/1,024/640 MiB. Operational
APIs, catalogue stock worker and combined relay process each get 128 MiB;
analytics API gets 192 MiB and its worker 320 MiB. These are low-traffic development
limits to verify on the actual host, not throughput or memory feasibility claims
for the official profiles. Stop other experiments before starting this stack.
Docker's memory budget checks its VM, not free Windows RAM. Check host memory
before starting the full stack, especially after a crash. A 4-GB Docker VM does
not mean Windows itself has 4 GB free. The current-machine verification status
and any uncompleted rehearsal are recorded in [progress](../docs/vichitr/progress.md).
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
