# Isolated analytical replay (M10)

Owner: Vichitr. See [common §12](../../docs/specs/02_COMMON_SPEC.md) and the
[M10 handoff](../../docs/vichitr/m10_replay_handoff.md).

`AnalyticsPipeline.replay_bronze(request)` reuses validated original Bronze
records in an initially empty, durably claimed analytical namespace. The canonical
HTTP creation/status endpoints use the same job provider. A separate
`python -m pipelines.replay.worker` process resumes durable queued/running jobs.

Publication lineage IDs pin exact Silver/Gold membership and enable semantic
snapshot comparison. Capture IDs also support duplicate/invalid input; without
a pinned published reference their reconciliation is explicitly null. No live
Kafka offsets, operational APIs, source event IDs/content or source pointers are
modified. See the handoff for retries, isolated clocks, source-ID bindings,
repair guards, evidence limitations and the optional Compose worker profile.
