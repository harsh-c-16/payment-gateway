# Gold business reducers (M07)

Owner: Vichitr. Authority: [common §11.4](../../docs/specs/02_COMMON_SPEC.md).

aggregate_gold(new_facts, db_transaction) requires an active caller transaction and
returns DirtyPartitionSet. A unique (namespace,event_id) contribution key gates
the exact integer count at UTC minute × event_type × source_service. Repeating a
contribution has no effect. Contribution, aggregate revision and export-pending
identity share a savepoint/caller transaction; the reducer never commits it.

All 24 registered event types contribute to pipeline_minute. Migration 004 adds
latest order/payment/search facts, distinct reached-stage sets, unresolved parent
joins and projections for order_fact, daily_conversion, checkout_funnel,
payment_failures, inventory_failures and search_performance. Older versions remain
valid Silver but do not replace current state. A multi-SKU inventory rejection
counts one (order_id,reservation_request_id); its earliest event defines its UTC
date. Conflicting reasons quarantine atomically, through the real outbox binding.

Amounts sum as exact PostgreSQL numeric / Parquet decimal128 integers, and API
money is an integer. Search duration sums and raw references are decimal strings;
compute quantiles from those observations. Quality scores require labelled input
and remain explicitly unavailable pending the evaluation producer's handoff.
Staging is not visible Gold. Only immutable, hash/schema/count-checked Parquet in an
active manifest defines queryable Gold. See [publication handoff](../../docs/vichitr/m05_vertical_handoff.md).
See the [M07 handoff](../../docs/vichitr/m07_business_gold_handoff.md) for migration,
row meanings, bounds and the outstanding labelled-artifact provider.
