# Windows Desktop measurements and expiry rehearsal

Use Windows PowerShell in the Desktop checkout. These commands use the existing
`.venv/Scripts/python.exe`, Docker Desktop Linux engine, pinned PostgreSQL 18 image,
and original checksum-verified CSV under `data/raw`. They do not invoke CI/CD.

```powershell
.\start-prototype.ps1
.\verify-desktop-controls.ps1
.\run-late-payment.ps1
# The late-payment command removes project containers after the rehearsal.
.\run-measurements.ps1 -Quick
# Full 50-query / 30-measurement series (can be lengthy on the fixed 1-CPU budget):
# .\run-measurements.ps1 -TimeoutMinutes 120
```

`verify-desktop-controls.ps1` checks every prototype container against the actual
declared CPU/RAM allocations using the existing infrastructure verifier. It saves
host CPU, cores, RAM, storage, OS, image identities, limits, revision, application
lock and source-tree hashes. No container environment or credentials are exported.
The Windows Time service status is diagnostic; unavailable external NTP is visible
and never represented as synchronized.

Each running project container gets five UTC probes. A probe brackets the remote
clock with local UTC and `perf_counter`, retaining round-trip time, signed midpoint
offset, conservative absolute offset bound and host clock-step residual. The
tightest round trip must bound the offset within 500 ms; any observed host clock
step over 10 ms fails verification. Override the allowable error with
`-MaxClockErrorMs` when a stricter latency comparison requires it. This check is
relative to the Windows host; it does not prove UTC accuracy against an external
time authority. Cross-service differences smaller than the combined clock error
are not established. Duration measurements use one local monotonic clock.

`run-late-payment.ps1` authorizes one scripted simulated purchase, arms a scoped
payment plan for exactly 35,000 ms, and observes reservation expiry before the
completion deadline. Independent API audits require cancellation, one attempt,
stock and reservation conservation, zero signed net debit, and exact active Gold
identity/version/status/amount. A debit is allowed only with exactly one reversal
for the same payment. The ordinary observed path quiesces the pending attempt
before it debits. Verification waits beyond the persisted deadline; it does not
sleep 35 seconds and assume success. Evidence is retained under
`artifacts/windows/late-<id>`. Hook support is disabled in `finally`, and all of
this project's containers are removed through `stop-prototype.ps1`. Existing
database/Kafka/lakehouse/model volumes are retained.

The measurement command refuses to run while any Docker container is running.
It creates a uniquely named/labelled PostgreSQL container on a random loopback
port, with enforced CPU, RAM, swap and PID limits. Default database allocation is
1 CPU and 2 GiB RAM; choose another fixed feasible budget with `-Cpus` and
`-MemoryMiB`. A separate provider container uses the prepared
`group3-m04-storage:local` image resolved to its immutable image ID, with 1 CPU and
1 GiB RAM. Code is mounted from this Windows Desktop checkout read-only. The
provider's anonymous Docker data volume supplies directory fsync, which the
storage contract requires and a native Windows path cannot supply. The launcher
and observer run in Windows; no WSL checkout is created.

The same limits, images, source, query fixture, seed and cache policy apply to
every comparator. Evidence is copied back to the Desktop before both disposable
containers and their anonymous volumes are removed in `finally`, including failed
runs. Temporary database schemas are isolated per trial. The prototype's retained
database volume is never mounted or reset. Evidence remains available.

Four axes use existing production provider implementations:

| Axis | Baseline / candidate | Timed boundary and checks |
|---|---|---|
| Bulk import | I0 INSERT / I1 COPY | Raw CSV open to manifest readiness; same 1,000-row staging chunks; verify 20,000 raw, 19,998 canonical, 19,920 active and equal logical business digests; retain stages and WAL bytes |
| Index | B0 / O2 category-price B-tree | Original 50 query fixtures, filter-only and lexical kept separate; actual count/ranking SQL; plans with ANALYZE/BUFFERS; equal result identities, prices, scores and eligible counts |
| Sink batching | B0 size 1 / O1 size 100 | Same immutable captured synthetic events, same physical capture size; time real Silver/Gold staging transactions; reconcile source dispositions and Q1-Q6 results after publication |
| Compaction | Small files / F-COMPACT | Frozen labelled synthetic snapshot through real publisher/compactor, same partitions and zstd codec; Q1-Q6, file count/selected bytes and identical logical query results |

Each axis runs three paired repetitions in a seeded variant order. Query series
use three warmups and 30 measurements per query per repetition. The summary saves
individual repetition medians, median/min/max, nearest-rank p95, and improvement
percent with the correct lower-is-better direction. Negative improvements stay
negative; zero baselines yield null percentages. Every measured result is checked
for equality. Raw JSONL, import artifacts, query plans, file manifests and resource
samples are retained under `artifacts/windows/<id>`, with file hashes in the final
manifest. `report.md` and `comparison.json` contain actual numbers only. Failed
runs keep partial evidence with FAILED status and never generate a winner.

`-Quick` retains three paired repetitions but uses two timed samples per query
and the first two query IDs in each of the four original search strata (eight
queries; the selected fixture is saved). Analytical Q1-Q6 remain present with
two timed samples each. Status is MEASURED_LOCAL_QUICK: this is descriptive local
triage, not the full evaluation matrix. The default command retains all 50 search
queries and 30 measured executions. `-TimeoutMinutes` sets the provider deadline
(default 120); a timeout retains partial evidence and marks the run FAILED.
Every measured import starts with a fresh absent source archive, so both I0/I1
pay the durable archive creation cost under the same state policy.

The Windows observer records actual CPU/RSS/peak RSS through Win32 and samples
Docker stats with actual timestamps; its interval is one second plus acquisition
time. Cgroup CPU/memory limits, memory peak and OOM counters are saved separately.
Clock checks run before and after measurements. An observer failure, clock check
failure, OOM, missing pair or unequal result rejects the run.

These are local provider comparisons, not formal P9/G4/G5 qualification. Search
excludes HTTP/outbox and uses closed-loop reads. Batching excludes Kafka transport,
consumer scaling, the 50-ms accumulation wait and Gold visibility latency.
Compaction uses a small synthetic fixture and warm cache; selected bytes are not
actual storage bytes read. Provider Python/Arrow/DuckDB run outside PostgreSQL's
allocation but inside the provider's separate fixed allocation (query DuckDB uses
one thread and a 512-MB engine limit). Background
desktop processes can still interfere. Formal claims still require the canonical
P9 resource/review receipts, complete collectors and integrated correctness gates.

`run-measurements.ps1 -Smoke` runs one repetition with fewer samples/events to
check setup; its output is explicitly SMOKE_ONLY and cannot establish improvement.
Generated data, secrets and raw benchmark results remain ignored by Git.

If a provider completes but a collector fails, the run remains FAILED. To inspect
the completed raw observations without promoting them, run:

```powershell
.venv/Scripts/python.exe -m benchmarks.windows.report --run artifacts/windows/RUN_ID
```

This checks the original journal hash, requires all four axes and matching paired
results, and writes a separate diagnostic report under `artifacts/windows/reports`.
It never changes the original bundle or its qualification. Diagnostic numbers
cannot establish an optimization or a formal performance claim. Import RSS fields
are process-lifetime peaks in the shared provider; per-trial peak RSS is not
established. The Windows observer allows 30 seconds per Docker stats acquisition;
an exceeded deadline still leaves resource evidence incomplete and rejects the run.
