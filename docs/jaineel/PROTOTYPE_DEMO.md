# Fixed-mode prototype demo

The runnable client is `python -m projectctl demo`. It connects the existing M1
session, turn, cart, quote and checkout APIs, then polls Orders for its current
status. It uses historical catalogue prices and simulated stock/payments. No
model provider, embedding download or new frontend service is needed.

## Start on the prototype machine

Use Python 3.11 and the existing application lock:

```powershell
uv sync --locked --python 3.11
$env:PROJECTCTL_ADAPTER_MODULE = 'infra.prototype'
.venv/Scripts/python.exe -m projectctl env up --profile prototype-local
.venv/Scripts/python.exe -m projectctl env verify --profile prototype-local
```

Follow [Vichitr's setup instructions](../../infra/PROTOTYPE.md) for owner migrations,
catalogue import, inventory seed and projection catch-up. Do not repeat import or
seeding on an already prepared deployment. Process readiness does not establish
successful search or terminal checkout.

Use the namespace retained in `artifacts/infra/prototype-local/context.json`.
The normal prototype namespace is `dev`; pass its actual value explicitly if
different. The default public origins are M1 at `http://127.0.0.1:8001` and Orders
at `http://127.0.0.1:8003`. Remote deployments can supply `--conversation-url` and
`--orders-url`. Origins cannot contain credentials, paths, queries or fragments.
The client needs no internal service token or database URL.

```powershell
.venv/Scripts/python.exe -m projectctl demo --namespace dev --user-id demo-jaineel --query "shirt"
```

The client prints its state path immediately. Select a numbered product, enter a
quantity, and review the quoted lines, unit prices, total, cart version and UTC
expiry. Enter exactly `CONFIRM <displayed-quote-id>` at the confirmation prompt
to submit checkout. Entering anything else leaves checkout unsubmitted. Free-text
purchase instructions cannot initiate checkout. There is deliberately no
`--yes`/automatic-confirmation switch.

The last display reports the backend's status and version. Both `CONFIRMED` and
`CANCELLED` are completed demonstrations; cancellation is not a successful payment.
`MANUAL_REVIEW`, a polling timeout or a provider failure returns exit 4 with the
order unresolved. A failed purchase invariant or business conflict returns exit 3.
The polling interval is 500 ms and its default window is 60 seconds; use
`--wait-seconds 120` for a longer observation window. This is a smoke/demo, not a
throughput measurement, independent transaction reconciliation or Gold proof.

## Resume and inspect

Use the printed state file after Ctrl+C, a transport failure or unresolved status:

```powershell
.venv/Scripts/python.exe -m projectctl demo --resume artifacts/demo/<printed-id>/state.json
```

The file retains user, namespace, run/correlation/session identity, cart version,
selected SKU/quantity, exact quote, human confirmation and every mutation's body,
request ID and idempotency key. Writes are atomic and flushed before dispatch.
There are at most two automatic retries per HTTP operation, always with the same
identity and input. A pending checkout resumes the previously confirmed operation,
including after the quote expires; an accepted order resumes observation only.
No new purchase key is generated to resolve uncertainty.

A **completed** search turn with a dependency-error outcome is a durable result.
Resume prompts for another search with a new turn identity, so it does not replay
the old failed turn forever. Clarification/no results asks for another query
without removing constraints. An expired, unconfirmed quote needs `REQUOTE`, price
review and a fresh confirmation. A changed cart fails closed; start a new demo
state after inspecting the conflict. Do not hand-edit a pending purchase's state.
If checkout definitively rejects a quote with `409 QUOTE_EXPIRED` while the user
was confirming, the client also requires `REQUOTE` and a fresh confirmation.
Only that definitive rejection permits a new checkout identity; transport
uncertainty keeps the original one.

`state.json.http.jsonl` beside the state file retains request identities, raw
response bytes (base64), HTTP status and monotonic elapsed timings. These files
are local ignored evidence; do not commit them. The client never logs an internal
token or follows a provider-supplied status URL to another origin. Order reads
verify user/session/order/quote binding and immutable quote lines/totals.

Each state file has an exclusive `.lock` while running. Normal exit/Ctrl+C removes
it. After a forced process kill, first verify its recorded PID is no longer
running, then remove only that stale lock before resuming. Keep the state itself.

## Basic prototype acceptance and owner handoffs

This CLI supplies the missing connected demonstration. A web UI, live LLM, real
payment gateway and performance matrix are not needed for this milestone.
Before presenting the **real** demo, verify these on the prepared deployment:

1. Search returns actual eligible catalogue hits within its unchanged 2-second
   provider timeout; M1's whole search-turn budget remains 3 seconds. Harsh owns
   the reported eligible-count/HTTP execution failure. Do not relax either limit
   or substitute a known SKU to hide a failing search.
2. Run the CLI through confirmation and observe a terminal order. Aditya owns
   M3 migration/setup, quote-expiry acceptance, order/SSE ownership, internal-token
   enforcement and participant/saga recovery. Preserve the original checkout
   identity while diagnosing uncertain outcomes.
3. Resume the same completed state and verify it reports the same order. Review
   the raw request log to check that retries preserved keys and inputs.
4. In a separate new session, decline confirmation and verify there is no
   checkout request. Review the quote and historical/simulated-data labels.
5. For the broader G3 project gate, independently reconcile Inventory and Payments
   and observe the resulting events in active Gold using the existing harness.
   A CLI terminal snapshot alone cannot establish that gate.

Backend ownership and contracts stay canonical in
[the common spec](../specs/02_COMMON_SPEC.md),
[the dataset rules](../specs/08_DATASET_PROFILE_AND_RULES.md) and
[the ownership record](../OWNERSHIP.md). Local verification and outstanding live
checks are recorded in [Jaineel's progress](progress.md).
