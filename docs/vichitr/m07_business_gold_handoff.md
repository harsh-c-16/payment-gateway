# M07 business Gold provider

Owner: Vichitr. Definitions: [common §11.4](../specs/02_COMMON_SPEC.md).
This checkpoint supplies business reducers and active-file readers. Full G3 and
labelled evaluation import still require the other owners' actual providers.

Stop API/workers/publishers during upgrade; apply analytics migration 004 through
the existing `PROJECTCTL_ADAPTER_MODULE=infra.analytics` and
`python -m projectctl db migrate --namespace bench-<run>`, then restart the new
version. The command's global exit 4 still exposes missing other owners/outbox;
the owned migration evidence must show analytics versions 1–4. Do not run old and
new publishers together. Migrations 001–003 and existing files remain immutable.

Migration 004 locks Silver writes and folds existing business events through a
server cursor, within the migration's transaction. Separate contribution keys
make backfill idempotent without recounting pipeline_minute. Existing Silver
documents, hashes, offsets and published files are retained. Backfilled business
events become export-pending; publish each affected namespace to expose new rows.
An inconsistent legacy reservation reason aborts the upgrade for review rather
than silently modifying accepted history. Large historical backfills have not
been performance tested.

## Output meanings

| Table | Meaning |
|---|---|
| pipeline_minute | Existing unique valid event count, including older/late facts |
| order_fact | Highest aggregate version per order; order_version, full snapshot and source event_id |
| daily_conversion | Current order states by order-created UTC date and currency; checkout conversion is confirmed/created, null for an empty known cohort |
| checkout_funnel | Historical distinct orders reaching each stage, joined to the current order-created cohort/currency |
| payment_failures | Current distinct attempts by attempt-created UTC date/currency; failed rows by terminal failure_code, with successful/reversed/pending/cancelled counts and money separately in the null-code row |
| inventory_failures | One failure per order/reservation_request_id across SKU facts; earliest event UTC date, agreed reason_code |
| search_performance | Latest completion per search_id, grouped by completion UTC date/mode; unique/empty counts and exact duration sum/count/raw references |

All business rows have namespace, UTC-midnight cohort_date, transform_version,
revision and publication_generation. Revisions identify changed table/date
partitions and can advance more than once per publication. A reused immutable
file retains the generation in which it was written; the enclosing manifest and
query result identify the active publication. The manifest's input lineage names
source events, receipts, code commit and schema/lock hashes.

Amounts remain integer minor units. Individual amounts are int64; sums use
PostgreSQL numeric and Parquet decimal128(38,0), so adding two maximum amounts
does not overflow int64. HTTP JSON returns integer sums. Currency dimensions are
kept separate; the current public contract permits INR only. Search durations are
stored as exact decimals of the validated wire number, exposed as decimal strings
in duration_sum_ms and duration_references[{event_id,duration_ms}]. These references
support raw quantiles; the provider never averages p95 values.

Older valid events remain in Silver/pipeline_minute. They cannot replace latest
state, but can establish a historical funnel stage. Payment parent order identity
is stable. Pending payment/inventory joins retain source event and order IDs;
they attach to the order's cohort when any complete order snapshot arrives.
No provisional/fake order date is assigned. Known cohorts include dates/currencies
from all accepted order snapshots, including stale versions, so an empty cohort
does not depend on delivery order. A corrected order creation date
rewrites both old and new cohorts; an emptied known order cohort reports zero
counts and null conversion. Payment/search/inventory partitions with no remaining
facts disappear from the next active file set.

The SQL views project current facts directly, so a correction cannot leave an
old category's count behind. Claim keys, facts, stages, joins, revisions and dirty
keys share the caller transaction with Silver/pipeline/source finalization.
Semantic conflicts roll back those changes before quarantine/outbox append.
Missing Aditya outbox still fails closed; there is no production substitute.

Publication freezes pending IDs, facts and business projections in repeatable
read. It verifies/writes immutable files, then commits the paired pointer CAS.
Dirty keys belong to individual pending event IDs: deleting the frozen IDs cannot
erase a later arrival's dirty membership. Readers pin the active manifest and
never query staging as published Gold. Existing half-open date queries now support
the six business tables; currency filters are rejected for noncurrency tables.

## Outstanding input and bounds

intent_accuracy and retrieval_quality remain explicitly unavailable. Jaineel's
diagnostic synthetic intent evaluator is not a reviewed labelled production
artifact, and there is no canonical labelled-import DTO/handoff yet. Jaineel and
Harsh must provide immutable labelled intent/relevance artifacts, run/version
identity, mode, source/label provenance and independently checked metrics before
that import can be implemented. No F1, recall or NDCG values are invented.

The existing full Silver snapshot limit remains 10,000 facts / 8 MiB document
text. Business Gold additionally enforces 10,000 output rows / 8 MiB projected
JSON before fetching the snapshot. Exceeding a limit leaves pending IDs and the
old active generation intact. These are safety bounds, not measured capacity.
M08 incremental publication is required before full 100,000-record W-QUALITY or
scale/compaction runs. No performance, power-loss resilience, complete real-outbox
integration or end-to-end commerce gate is claimed here.

See [progress](progress.md) for exact test commands and evidence, and
[test skips](test_skips.md) for platform coverage. Next checkpoint: M08 publication
and candidate safety.
