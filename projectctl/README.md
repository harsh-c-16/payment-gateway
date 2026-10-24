# Unified CLI foundation

Owner: Jaineel. Contracts: [runbook §1](../docs/specs/09_EVALUATION_RUNBOOK.md),
[brief J01](../docs/specs/04_JAINEEL_VORA.md), [P1](../docs/specs/10_JAINEEL_CODEX_PLAYBOOK.md).

Run commands from the repository root. Use Python 3.11 and uv 0.10.8.
`uv.lock` is the single generated application lock, including development tools.
This is an application workspace (`tool.uv.package=false`); run modules from the
checkout. No model, embedding or vector stack is installed.

```powershell
uv python install 3.11
uv sync --locked
.\.venv\Scripts\Activate.ps1
python --version
python -m projectctl --help
python -m projectctl eval run --help
python -m projectctl benchmark run --help
python -m pytest tests/projectctl -q
python -m ruff check projectctl tests/projectctl
python -m ruff format --check projectctl tests/projectctl
python -m projectctl.schemas --check
```

On Linux/macOS, activate with `source .venv/bin/activate`. Activation is optional:
use `uv run --locked python ...` or the environment's Python directly. If a corporate
policy prevents writing uv's default cache, configure an approved writable cache
with `UV_CACHE_DIR`; never disable TLS or remove package hashes.

P1 pytest runs use a unique `artifacts/pytest/<uuid>/` directory for temporary files
and pytest's cache. This avoids Windows permission errors when an earlier run used
a different account to create `%TEMP%/pytest-of-<user>` or `.pytest_cache`.
Normal `python -m pytest tests/projectctl -q` works without deleting those directories,
changing ACLs or running as administrator. Explicit `--basetemp` and `-o cache_dir=...`
overrides remain supported. New sessions leave earlier run directories intact.

The reproducible install follows [uv's project workflow](https://docs.astral.sh/uv/guides/projects/).
Update dependencies deliberately with `uv lock`, review its diff, then repeat the
offline checks. Routine installs use `uv sync --locked`, which refuses a stale lock.
Infrastructure/image locks belong to Vichitr; Aditya verifies DB compatibility.

All runbook actions and flags are parsed strictly; abbreviated/unknown flags fail.
No production adapters exist at P1. `ProviderRegistry.register(action, adapter)` is
the explicit seam for reviewed owner adapters; `Invocation` carries the complete
arguments, resolved config, UUID run identity and namespace. Test doubles live only
in `tests/projectctl/` and always declare `test_mode=stub`. There is no automatic
mock fallback, startup implementation, domain contract implementation or benchmark
execution hidden behind the CLI.

```powershell
# Expected exit 4: Vichitr's adapter is missing; JSON links failure evidence.
python -m projectctl env verify --profile local4c8g
# Expected exit 2: unknown flags cannot be silently ignored.
python -m projectctl env verify --profile local4c8g --unknown
# Expected exit 4: draft controls/hashes/providers block all six requested runs.
python -m projectctl benchmark run --workload W-PIPE --variants B0,O1 --repetitions 3 --config configs/evaluation.yaml
```

Each invocation saves `manifest.json` and `summary.json`; configuration-bearing
commands also save `resolved_config.json`. Benchmark requests prepare a unique
`benchmarks/results/<run_id>/` for each requested variant/repetition. Preparation
does not start measurement. Commands without evaluation config save under
`artifacts/projectctl/<run_id>/`. Paths in stdout are repository-relative. P1 metrics
are null with `NOT_RUN`, and missing collectors are listed without creating fake
empty Parquet/CSV files. These ignored directories preserve failure evidence locally.

Exit codes: **0** completed/pass; **2** invalid input; **3** correctness failure;
**4** missing dependency/incomplete evidence; **5** completed measurement missing a
declared target. Metric statuses are `MEASURED`, `INCOMPLETE`, `NOT_RUN` independently
of exit codes. A passing adapter double is not a real integration or measurement.

The evaluation YAML is explicitly `draft`: source SHA is the published expectation
from file 08, while unknown provider paths/hashes are null. `local4c8g` allocations
are proposed, not verified hardware. Full frozen controls are recorded with each
request. Only registered variant differences are allowed. Finite jobs retain null
measurement-window seconds; query jobs retain 3 warmups/30 executions per Q1-Q6.
The matrix records measured-best selection requests without inventing C-BEST.
The `locks` section records the actual generated application-lock SHA; infrastructure
and event-schema lock paths/hashes remain null until their owners supply them.
Unknown actual host memory/storage/physical-core information remains null.

Schemas in `contracts/evaluation/` are generated from strict Pydantic models:

```powershell
python -m projectctl.schemas
python -m projectctl.schemas --check
```

Schema checks validate shape; `load_config` additionally validates variant semantics,
resource totals and path confinement. JSON canonicalization sorts keys, preserves
arrays, encodes UTF-8 and rejects nonfinite numbers. Manifest content hashes exclude
their own `content_sha256`; raw file/lock hashes cover exact bytes.

P2 implements conversation/provider contracts. P3 supplies fixtures/oracles. P4
supplies scheduling, matrix expansion/resume and random paired execution.
No real environment, exact-file data, live-model or performance gate has run at P1.

Reproduce this checkpoint and retain command/stdout/stderr/exit evidence with:

```powershell
python benchmarks/manual/verify_p1.py
```

It writes a new directory under `artifacts/p1/` and expects missing provider actions
to exit 4. Its own exit 0 means these expected checkpoint outcomes matched.
