# Infrastructure (Vichitr / M4)

Authority: [personal brief](../docs/specs/07_VICHITR_ARORA.md),
[runtime contracts](../docs/specs/02_COMMON_SPEC.md), and
[module plan](../docs/vichitr/implementation_plan.md).

M01a provides the **PostgreSQL-only** `postgres-local` profile described below.
For Kafka, registry and the smaller PostgreSQL allocation, use
the [M01b streaming-local instructions](STREAMING.md). Application services,
domain schema freeze, FileStore and benchmark readiness remain later checkpoints.

## Start and verify

Install/start [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/)
using its Linux-container backend. Then run from the repository root with the
[locked Python 3.11 environment](../projectctl/README.md):

```powershell
uv sync --locked --python 3.11
$env:PROJECTCTL_ADAPTER_MODULE = 'infra.postgres'
.venv/Scripts/python.exe -m projectctl env up --profile postgres-local
.venv/Scripts/python.exe -m projectctl env verify --profile postgres-local
```

The available system uv may be older than the repository's required 0.10.8.
In the current workspace, that version is installed locally; use this instead:

```powershell
$env:UV_CACHE_DIR = "$PWD/.uv-cache"
$env:UV_PYTHON_INSTALL_DIR = "$PWD/artifacts/tooling/python"
& ./artifacts/tooling/uv-package/bin/uv.exe sync --locked --python 3.11
```

`env up` checks Docker before creating local credentials. It starts only this
project's PostgreSQL container and then runs the database checks. A missing engine,
incomplete credentials, failed initialization or failed verification returns exit 4
through the existing CLI with evidence. An unsupported profile returns exit 2.

The Compose image is the maintainer's
[PostgreSQL 18 / pgvector 0.8.1 image](https://hub.docker.com/r/pgvector/pgvector),
pinned by registry manifest digest in [images.lock.json](images.lock.json).
The real Docker smoke check passed on Windows/WSL2 with PostgreSQL 18.2 and pgvector
0.8.1; the lock records its evidence reference. Other machines still run their own
verification. No floating image tag determines the runtime.

The first image download/initialization can exceed the command timeout. A timeout
does not mean the container failed: inspect its state, wait for health, then rerun
the same `env up` command. It reuses the existing credentials and data volume.

## Databases and credentials

The first initialization creates six empty service databases and restricted login
roles. `catalog_db` also receives the vector extension at version 0.8.1. Service
table migrations remain their owners' responsibility; this module runs none.

| Database | Login | Owner of tables/migrations |
|---|---|---|
| conversation_db | conversation_user | Jaineel |
| catalog_db | catalog_user | Harsh |
| orders_db | orders_user | Aditya |
| inventory_db | inventory_user | Aditya |
| payments_db | payments_user | Aditya |
| analytics_db | analytics_user | Vichitr |

On successful first startup, local connection strings are written to
`artifacts/infra/postgres-local/.env`. Load only the relevant service's URL into its
process environment; services use their own `DATABASE_URL` binding. This is a private
local file, not a file to paste into chat, commit or share with teammates.

Passwords are randomly generated into `artifacts/infra/postgres-local/secrets/`
and mounted as Compose secrets. The administrative login is not an application
credential. Service logins have no superuser, database/role creation, replication
or row-security-bypass privilege. Each can connect only to its own database.
PostgreSQL's [database privileges](https://www.postgresql.org/docs/18/sql-grant.html)
are checked after startup, including exclusion of the maintenance databases.

Host applications connect to `127.0.0.1:5432`; future Compose applications connect
to `postgres:5432` on the Compose network. The generated URLs are for host processes.
Port 5432 must be free; no existing PostgreSQL service is stopped automatically.
The root `.env.example` contains placeholders, not the generated passwords.

Keep the credential files with the retained volume. Existing passwords are never
automatically rotated, and incomplete secret sets fail visibly. POSIX permissions
are restricted; on Windows keep the workspace in your private user storage and
use your normal Windows access controls.

## Durability and resources

PostgreSQL 18 persists its data under the named `postgres_data` volume mounted at
`/var/lib/postgresql`, following the
[official image's PostgreSQL 18 layout](https://hub.docker.com/_/postgres).
Health checks use TCP so the temporary initialization server is not mistaken for
the final ready server. Verification checks the image reference, volume, loopback
port, PostgreSQL major, pgvector version, durability flags and role isolation.

This profile enforces the draft evaluation config's PostgreSQL allocation only:
0.75 CPU cores and 2,048 MiB RAM, plus 128 MiB shared memory. It does not certify
the whole proposed 4-core/8-GiB SUT or the host's capacity. Service role connection
limits are 10; analytics allows 14 for the specified 12 sink plus 2 publisher
connections. Application pool configuration must still respect those budgets.

Stop this project's container without removing its data:

```powershell
.venv/Scripts/python.exe -m projectctl env down
```

This command retains both the named volume and credentials. No reset, volume deletion,
automatic orphan cleanup, service migrations or catalogue import is implemented here.
Initialization scripts run only for an empty volume; editing one does not migrate an
existing database. If initialization fails partway, preserve the volume and diagnose
it before any explicit recovery. Never delete data to bypass a failed check.

## Checks and evidence

```powershell
.venv/Scripts/python.exe -m pytest tests/pipelines -q
.venv/Scripts/python.exe -m ruff check infra/postgres.py tests/pipelines
.venv/Scripts/python.exe -m ruff format --check infra/postgres.py tests/pipelines
```

Offline tests explicitly use doubles for dependency/security rejection paths.
They do not prove real PostgreSQL behavior. After Docker is installed and running:

```powershell
$env:RUN_POSTGRES_LIVE_TESTS = '1'
.venv/Scripts/python.exe -m pytest tests/pipelines/test_postgres_live.py -q
Remove-Item Env:RUN_POSTGRES_LIVE_TESTS
```

The live test uses this PostgreSQL-only project. It verifies all 30 cross-service
connection denials, writes one uniquely named analytical probe table, recreates the
container without deleting its volume, reads the original marker and drops only
its own probe table. It interrupts this project's database connections: run before
starting application work. A failed trial may retain its probe for diagnosis.

CLI summaries live under `artifacts/projectctl/<run_id>/`. Successful database facts
live under `artifacts/infra/postgres-local/checks/<run_id>/postgres.json`; they contain
no passwords or connection URLs. See [progress](../docs/vichitr/progress.md) for the
exact commands actually run and remaining checks.
