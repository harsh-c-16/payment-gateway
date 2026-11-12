# Data engineering and distributed systems coverage

The required baseline in [project context](../specs/01_PROJECT_CONTEXT.md) is a
reproducible local deployment. The current specifications do not require servers
in different geographic locations. Separate service processes communicate over
HTTP and Kafka; the professor prototype places them on one Docker host.

## What the project implements

| Course concept | Concrete implementation | Current evidence/limit |
|---|---|---|
| Batch ingestion and data quality | `pipelines/catalog/` parses the original CSV, normalizes conservative facets, preserves provenance and superseded observations, stages/promotes the catalogue | Independent source check: 20,000 observations, 19,998 canonical, 19,920 active; no inferred prices/attributes |
| Stream ingestion and medallion storage | `pipelines/ingestion/`, `curation/`, `gold/`, `storage/`: durable Bronze, unique Silver events, Gold reductions, immutable Parquet and active manifests | The live purchase became queryable in active Gold; complete source/receipt reconciliation is a separate formal gate |
| Reliable event publication | Owner-local transaction plus shared transactional outbox, followed by Kafka relay | Avoids independently committing a business change and its Kafka send; relay may redeliver |
| Duplicate handling and request identity | Event IDs/hashes, durable unique keys, scoped idempotency keys, cart/order/stock versions | Same-key retry preserves the operation; consumer deduplication supplies one logical effect. Do not claim transport-wide exactly-once delivery |
| Distributed transaction workflow | Orders orchestrates Inventory reservation and asynchronous simulated Payments using a durable saga and compensation | Fresh confirmed order, committed reservation and matching single debit verified; complete failure campaigns remain pending |
| Concurrency and consistency | Inventory owns stock mutation; M1 uses cart versions and confirmation against the exact quote; search consumes versioned stock snapshots | Search is eventually consistent and advisory. Checkout revalidates inventory. Full stock-race/fault qualification remains a required evaluation |
| Contracts and schema evolution | OpenAPI/typed DTOs, event JSON Schemas and a real Schema Registry | Consumers validate provider responses. Formal byte-pinned all-owner review receipts remain incomplete |
| Partitioning and consumer scaling | Kafka partition keys, consumer groups and configurable P10/P30/P33 trials | Scaling code/configuration exists; the prototype has one broker and one partition per topic. No measured scaling benefit is claimed |
| Analytical query/storage optimization | DuckDB/Parquet queries, compaction/layout candidates, indexed catalogue search, COPY loading | Harsh's SSD COPY comparison is an attributed owner result. The controlled shared-runner matrix remains pending |
| Measurement and independent verification | `projectctl/`, `benchmarks/`, `shared/telemetry/`, `dashboards/`: open-loop scheduler, raw observations, independent oracle, reconciliation/comparison/report generation | Jaineel owns execution and fair comparisons. A working demo and passing unit tests do not establish benchmark targets |

## Communication and deployment

Public/service commands use HTTP JSON with request/run/correlation identity and
explicit idempotency keys for mutations. API error codes distinguish business
conflicts from unavailable dependencies. Retries preserve the original operation;
a timeout leaves its outcome uncertain until observed.

Events use Kafka's network protocol, namespace-specific topics and partitioned
logs. Ordering is within a partition, not global across topics. Acknowledgements,
durable outboxes, replay and consumer deduplication handle different failure
boundaries. Services own separate databases; cross-service state is obtained
through APIs/events. The current six databases share one PostgreSQL instance.

The prototype is 12 containers on one machine, with one Kafka broker, replication
factor 1 and local persistent database/lakehouse volumes. These are shared host
failure points. It does not demonstrate broker failover, PostgreSQL replication,
multi-host network partitions or geographic disaster recovery. Kafka supplies
its own KRaft machinery; we have not implemented a new consensus algorithm or
demonstrated a replicated controller quorum. HTTP/Kafka connectivity alone does
not prove that moving containers to remote machines preserves the guarantees.

## What remains for Jaineel

The connected fixed-mode M1 prototype is implemented and rehearsed. Remaining
M0 work, in dependency order:

1. Freeze execution-machine dataset/fixture bytes and checkout/integrated request
   templates; collect actual affected-owner review receipts. Keep rule-derived
   relevance scores diagnostic until human judgement is supplied.
2. Configure the existing catalogue and M3 migration modules from
   [the teammate runbook](EVALUATION_TEAMMATE_RUNBOOK.md). Finish reviewed case,
   audit, fault-barrier, resource and shared-clock bindings with their owners.
3. Register and execute the required correctness cases, including source
   dispositions, success/decline, stock races, failures/recovery and replay.
4. Qualify B0, retain bottleneck evidence and execute the prescribed paired
   three-repetition import/batching/index/scaling/layout/integrated trials.
5. Reconcile saved artifacts, build comparisons/report, select a candidate only
   from measurements, and finish stress/recovery and independent reproduction.

These are the release requirements in [evaluation specification](../specs/03_EVALUATION_SPEC.md)
and [runbook](../specs/09_EVALUATION_RUNBOOK.md). A geographic deployment is an
additional scope decision. The present course contribution is evaluated through
correctness, measured optimization and failure behaviour on the declared local
profile. Current acceptance and raw evidence are in [progress](progress.md) and
[the presentation guide](PRESENTATION_READY.md).
