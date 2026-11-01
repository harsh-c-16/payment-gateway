# Gold pipeline_minute reducer (M06)

Owner: Vichitr. Authority: [common §11.4](../../docs/specs/02_COMMON_SPEC.md).

aggregate_gold(new_facts, db_transaction) requires an active caller transaction and
returns DirtyPartitionSet. A unique (namespace,event_id) contribution key gates
the exact integer count at UTC minute × event_type × source_service. Repeating a
contribution has no effect. Contribution, aggregate revision and export-pending
identity share a savepoint/caller transaction; the reducer never commits it.

All 24 registered event types contribute to pipeline_minute. Latest-state order/payment reducers, currency
reconciliation, funnel sets, joins and quality results are M07; they are not stubbed.
Staging is not visible Gold. Only immutable, hash/schema/count-checked Parquet in an
active manifest defines queryable Gold. See [publication handoff](../../docs/vichitr/m05_vertical_handoff.md).
