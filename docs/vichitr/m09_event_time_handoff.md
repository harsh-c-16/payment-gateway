# M09 event time and DLQ recovery

The owned event-time provider is implemented. Actual notification storage/relay
integration still requires Aditya's `shared.outbox`; the production path continues
to fail closed when it is absent. This is not a completed integrated T-03/T-12 or
a freshness/performance result. See [progress](progress.md) for executed evidence.

## Processing and publication

Migration 006 adds partition maxima/activity, a monotonic namespace watermark and
one processing annotation per newly accepted Silver event. They commit with the
Silver fact, reducer, source disposition and export marker. Duplicates refresh
partition activity without adding another contribution or annotation. Rejected
future/invalid/conflicting events do not move the watermark.

- Windows are UTC minutes. The candidate watermark is the minimum maximum valid
  event time among active partitions minus 120 seconds. Activity uses analytics
  processing wall time, not producer event time or historical CSV crawl time.
- At exactly 10 seconds without an accepted valid record, a partition is idle.
  Unseen partitions do not hold progress. A watermark never regresses when an idle
  partition resumes; with all partitions idle it retains its last value.
- An event strictly before the prior watermark is late. An older event from a
  resumed idle partition also takes reconciliation. Out-of-order events within
  the allowance are flagged without being discarded. An event exactly at the
  watermark is within the allowance.
- Timestamp flags are `WITHIN_POLICY`, `OUT_OF_ORDER`,
  `RESUMED_IDLE_PARTITION`, `LATE_RECONCILIATION` and
  `FUTURE_WITHIN_TOLERANCE`. The existing validator rejects more than five seconds
  ahead of original ingress; the quarantine reason is `FUTURE_TIMESTAMP`.
- Valid late facts remain immutable Silver facts and revise Gold. The annotation
  retains the resulting minute revision, prior watermark and
  `reason=LATE_RECONCILIATION`. Normal annotations use `INGESTION`.
- The worker schedules provisional publication every 250 ms without waiting for
  the watermark. Slow synchronous work can miss ticks; missed ticks are skipped,
  not added as drift after each publication. This is a schedule, not a measured
  promise of 250-ms end-to-end latency.

Publication roots contain the policy and a snapshot of watermark/activity state;
bounded membership shards carry event-specific flags/reason/revision. Existing
typed Parquet schemas, public DTOs and source envelopes are unchanged. Old
unannotated facts have null processing annotations, not invented timestamps.
Migration 006 seeds partition maxima from accepted historical Silver/source rows;
it does not invent old watermark decisions or rewrite old manifests.

## Read-only handoff to Jaineel

These SQL views are analytics-owner inspection surfaces, not permission to read
operational databases. Always filter by the intended namespace.

```sql
SELECT * FROM event_time_windows WHERE namespace = :namespace;
SELECT * FROM event_time_visibility WHERE namespace = :namespace;
```

`event_time_windows` reports `provisionally_complete` when the minute end is at
or before the stored watermark. Publication reevaluates idle partitions even
without pending facts. An unchanged generation retains its original lineage
watermark; the SQL status can advance independently. No state is permanently
sealed and no historical generation is edited.

`event_time_visibility` separates `initial_visibility` and `late_correction` and
provides ingress-to-visibility and processing-to-visibility seconds, generation,
observed timestamp and existing timing-validity status. These are wall-clock
post-COMMIT upper-bound observations. Missing observations remain null; recovery
is explicitly `recovery_upper_bound`, not an exact latency sample. The independent
harness must preserve those cohorts and validity markers. Existing receipts still
provide the original producer/sink/publication evidence. No new Prometheus names
or independent harness arithmetic are introduced here.

## DLQ boundary and fault test

Existing quarantine inspection is authenticated and exposes restricted raw
references/hash/reasons, not the malformed bytes. The original Bronze file remains
recoverable. `route_dlq` calls `append_outbox(tx, notice)` in the same transaction
as quarantine/disposition. Infrastructure failures abort processing instead of
becoming dirty-data reasons. Business workers subscribe only to the five domain
topics. A registered DLQ notice is not a business fact or another invalid ingress.

The broker fault test uses real Kafka, PostgreSQL and Bronze, with an explicitly
labelled SQL storage/relay double in `tests/pipelines`. The host controller pauses
the actual Kafka container only after the test writes `artifacts/m09/dlq-ready.json`,
acknowledges `<namespace>-paused`, waits for `<namespace>-resume-request`, unpauses
Kafka and acknowledges `<namespace>-resumed`. The double keeps the notification
pending during the unconfirmed send, reloads it after recovery, and marks it sent
only after a real broker acknowledgement. Lost acknowledgements may yield duplicate
notices with the same diagnostic ID. This does not prove Aditya's absent relay.

Opt in with `RUN_VERTICAL_LIVE_TESTS=1 M09_BROKER_OUTAGE=1`; use the existing
storage-check container and a controller for the two marker acknowledgements.
The marker wait is bounded at 90 seconds; always unpause Kafka in controller
cleanup. It is deliberately excluded from unattended normal CI.

Next checkpoint: M10 isolated analytical replay. Actual outbox adoption, full
W-QUALITY, integrated gates and sustained performance remain pending.
