# Professor demonstration: prepared Windows machine

For the current storefront, chat, checkout and in-browser Gold observation,
use [the browser demonstration guide](PROFESSOR_DEMO.md). It provides one-command
startup and container cleanup. The 12 November CLI rehearsal below remains
historical evidence and an alternative demonstration.

The connected prototype was rehearsed on this Windows machine on 12 November
2026 against real PostgreSQL, Kafka and all six APIs. Search, cart, quote,
simulated purchase, safe resume, declined confirmation and active Gold passed.
Use this guide from the repository root (`payment-gateway`).

Harsh's [deployment record](../../infra/DEPLOYMENT_INFO.md) describes his Linux
rehearsal and infrastructure pins. His [data sheet](../harsh/DATA_SHEET.md),
[three searches](../harsh/DEMO_SEARCHES.md) and
[import comparison](../harsh/IMPORT_COMPARISON.md) are the supporting material.
The [consumer review](HARSH_ACCEPTANCE_2026_11_12.md) records the decisions and
what was independently checked here.

## Start and check before class

The existing data, credentials and Docker volumes are already prepared. Start
Docker Desktop with its Linux engine, then run:

```powershell
uv sync --locked --python 3.11
$env:PROJECTCTL_ADAPTER_MODULE = 'infra.postgres'
uv run --locked python -m projectctl env up --profile postgres-local
Get-Content artifacts/infra/prototype-local/.env | ForEach-Object {
    $entry = $_ -split '=', 2
    [Environment]::SetEnvironmentVariable($entry[0], $entry[1], 'Process')
}
uv run --locked python -m services.orders.m3_setup
$env:PROJECTCTL_ADAPTER_MODULE = 'infra.prototype'
uv run --locked python -m projectctl env up --profile prototype-local
uv run --locked python -m projectctl env verify --profile prototype-local
uv run --locked python -m projectctl projection wait --namespace dev --sku-manifest artifacts/prototype-setup/prototype-data/sku_manifest.json --timeout-seconds 600
uv run --locked python -m projectctl demo-check --namespace dev
```

Check each command's exit code before continuing. `env verify` and projection
must return `exit_code: 0`; projection must cover 19,920 SKUs with zero deferred.
`demo-check` must print six PASS lines and `Presentation checks: PASS (exit 0)`.
It checks the three public service readiness responses used by the client and
all three real M1 searches. It creates only sessions/search turns; it sends no
cart update, quote or checkout. Every search must use rules and zero model calls,
fit the existing 3-second turn budget and preserve its hard filters. Returned
products must have the expected dataset revision, historical INR prices and
positive displayed stock. It does not replace the container/projection checks.

A new computer needs the initial setup in
[infra/PROTOTYPE.md](../../infra/PROTOTYPE.md) before this prepared-machine
sequence. Keep this machine's retained namespace `dev`. No import, inventory
seed or reset is needed when restarting it.

## Five-minute presentation

1. Explain the source: 20,000 historical Flipkart observations, 19,998 canonical
   listings, 19,920 active, 78 missing prices and 2 superseded observations.
   Prices are historical INR values; inventory and payments are simulated.
2. Run the connected client:

   ```powershell
   uv run --locked python -m projectctl demo --namespace dev --user-id demo-professor --query "men's formal shirt"
   ```

   Select a product and quantity. Explain that search stock is advisory, the
   quote supplies authoritative prices, and checkout rechecks stock. Review the
   total and expiry, then type exactly `CONFIRM <displayed-quote-id>`. Show the
   terminal order status. Normal payments have a 5% simulated decline, so
   `CANCELLED` is a valid business outcome; explain it accurately.
3. Follow the printed state path to show the same order after resume:

   ```powershell
   uv run --locked python -m projectctl demo --resume artifacts/demo/<printed-id>/state.json
   uv run --locked python -m projectctl demo-check --state artifacts/demo/<printed-id>/state.json
   ```

   The second command reads Orders and waits for that exact terminal order
   version in active Gold. It checks user/session/quote identity, status,
   amount/currency, reservation/payment IDs and publication generation. It uses
   the order's UTC creation day, so yesterday's saved demonstration still works.
   It sends GET requests only and never modifies the original purchase state.
   The default observation window is 120 seconds per stage; an initial backlog
   can need `--wait-seconds 600`. Missing Gold remains INCOMPLETE with exit 4.
   Temporary transport failures and retryable HTTP 429/503 allow at most two
   consecutive retries of the same read, honoring `Retry-After` and the overall
   observation deadline. Permanent errors remain failures.
4. Explain filters with `watches under 1000 rupees`: category watches, price
   strictly below INR 1,000. Then show `black watches under 1000 rupees`: no
   matches because this dataset does not record the watch colour in a supported
   colour field. Constraints stay intact. The preflight evidence contains both
   responses; alternatively start another `demo` with either query. At a
   successful quote, pressing Enter declines confirmation and sends no checkout.
   At the search prompt after no results, type `q` to leave.
5. Explain the data path: local transactional outbox → Kafka → durable Bronze →
   deduplicated Silver → published Gold. For optimization, show Harsh's I0/I1
   table: median staging 3.735 → 1.129 s and total 11.815 → 9.264 s, three paired
   owner runs on his SSD. Attribute these measurements to his machine.

Fixed mode calls no LLM. A terminal snapshot plus matching Gold is a prototype
acceptance result; full source/receipt, inventory and signed-ledger
reconciliation belongs to the formal G3/evaluation suite.

## Evidence and recovery

Each `demo-check` prints a new directory under `artifacts/presentation/`.
`checks.json` records each actual result; adjacent HTTP journals retain raw
responses and timings. `--out` accepts a new directory and refuses to overwrite
old evidence. Search state files and order observation copies are retained there.
Use the original `projectctl demo` state for purchase recovery.

The fresh local rehearsal is in `artifacts/presentation-20261112/`. Its order
`8615ea16-c56f-4268-b2a4-7d6976c2f6bb` reached `CONFIRMED` version 6, with a
COMMITTED reservation and one INR 1,166.00 debit. Active Gold generation 237
returned the matching terminal order. Confirmation was a scripted regression
input, not a human review. No benchmark or fault campaign is claimed.

If a provider is unavailable, retain the evidence, restore the stack and rerun
preflight in a new directory. Resume uncertain purchases with their original
state/key. An expired unconfirmed quote requires `REQUOTE` and fresh review.

## Stop after presenting

```powershell
$env:PROJECTCTL_ADAPTER_MODULE = 'infra.prototype'
uv run --locked python -m projectctl env down
```

This retains database/Kafka/lakehouse volumes, credentials and demo evidence.

For course concepts, communication protocols, current limitations and the exact
remaining M0 work, see [course coverage](COURSE_COVERAGE.md).
