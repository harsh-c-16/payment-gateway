# Presentation comparison: choices, numbers and reasons

Prepared 15 November 2026. Measurements were taken on 14 November 2026.
Full evidence and the fourteen-question discussion: [Professor questions and results](PROFESSOR_QUESTIONS_AND_RESULTS.md).

## Slide 1 - Which approach fits which workload?

These are measured component comparisons and conditional recommendations. They do not indicate that a new production index was deployed.

| Workload / decision | Preferred approach | Alternative and measured numbers | Why this choice? | Status |
|---|---|---|---|---|
| Category + price range/order | Composite B-tree | B-tree **1.295 ms**; hash **2.610 ms**; no optional index **4.160 ms** | B-tree query latency was **50.36% lower than hash**, and **68.86% lower than baseline**. It fits the equality-plus-range predicate. | Measured local candidate; no production index changed |
| Keyword search: `shirt` | GIN is a candidate for a separate text-search optimization | GIN **3.303 ms**; no optional index **4.756 ms** | **30.55% lower query latency** for this positive-hit text case. It addresses text membership rather than numeric ordering. | Experimental; GIN was not deployed by this work |
| Price range on shuffled data | Prefer B-tree over BRIN for this case | B-tree **1.426 ms**; BRIN **2.472 ms** | B-tree query latency was **42.30% lower**. Unordered values reduce BRIN's usefulness. | Measured local comparison |
| Price range on price-sorted data | BRIN becomes a candidate | BRIN **0.748 ms**; B-tree **1.387 ms** | BRIN query latency was **46.09% lower** on the sorted layout. Physical layout changes the answer. | Conditional; sorting cost excluded and live data not reordered |
| Historical analytics | Keep audit/replay data and materialize summaries | **20,000 events / 93,828 bytes** vs **1,336 summary rows / 3,009 bytes** | The summary representation is **96.79% smaller** and preserves tested counts/sums, but loses exact event history. Retain the source data for audit and replay. | Analytical policy probe; no production purge introduced |

**Say this aloud:** "We chose methods based on the query and correctness requirement. B-tree helped category/price queries, GIN helped the tested keyword query, and BRIN depended on physical ordering. These results do not support a universal winner."

### Essential footnotes for this slide

- Timing unit: milliseconds per query, lower is better. Each cell is the median of three repetition medians, with ten timed calls per repetition and three warmups. These are point estimates, not a significance claim.
- Original source: 20,000 observations, 19,998 canonical listings, 19,920 active. The index probe uses a title/category/price projection; it excludes production stock joins, HTTP, Kafka, hybrid ranking and embedding inference.
- PostgreSQL: 1 CPU, 512 MiB RAM limit, 256 MiB RAM-backed data directory; warm cache, primary-key integrity retained, no other Docker containers. This is not SSD, cold-cache, application throughput or formal P9 evidence.
- Index size/build cost: B-tree **424 KiB / 25.502 ms**, hash **840 KiB / 20.599 ms**, BRIN **24 KiB / 5.917 ms**, GIN **1,184 KiB / 45.609 ms**. These build medians are from the shuffled-layout trials. GIN's text-update cost was not measured by the price-only update probe.
- The summary space comparison is **representation versus representation**. Keeping both files uses **96,837 bytes**, before other metadata. We did not delete the raw file or save 96.79% of the entire platform's storage.
- The aggregate query was **2.585 ms on raw data** and **2.805 ms on summaries**: summaries were **8.51% slower** here. Claim the measured space trade-off, not a query-speed improvement.

## Slide 2 - Why these correctness mechanisms?

These numbers validate invariants. They are not latency comparisons with alternative distributed-system implementations.

| Mechanism / choice | Numerical evidence | What it establishes |
|---|---|---|
| Retain deduplication identities across supported replay | Retained-ID policy: **1 logical effect**; intentionally unsafe ID-retirement policy: **2 effects** for the same event sent twice | Summaries alone do not prevent double-counting after replay. This was an isolated local policy probe, not a production deletion test. |
| Deduplicate identical deliveries | Real pipeline: **3 deliveries -> 2 logical valid events; 1 duplicate suppressed** | At-least-once delivery can still produce one logical effect per event ID. |
| Version-check stock updates | Real pipeline: **v2 = 4 units**, then **v1 = 9 units**; final result **v2 = 4 units**, **1 stale update ignored** | Arrival order must not overwrite newer stock state. Both valid events remain in analytical history. |
| Reconcile late events by event time | Real pipeline: earlier window count **1 -> 2**, published in a newer Gold generation | A late event updates its original window instead of being silently dropped. |
| Let Inventory serialize the last-unit race | Real services: **2 checkouts, 1 unit, 1 confirmed order, 1 cancellation, 1 matching debit, 0 overselling** | The successful sale, stock effect, payment and final Gold facts reconcile. |
| Preserve malformed-event isolation | Real pipeline: **1 malformed record quarantined; 2 neighboring valid events processed** | One bad message does not stop valid messages from reaching analytics. |

**Say this aloud:** "We tested both successful processing and failure boundaries. We check the exact business effects, not just HTTP success or Kafka lag."

The real pipeline figures above reuse retained runs from 14 November; their checks were revalidated from saved evidence. They were not all rerun as fresh transactions for this handout. The local retention probes and index measurements are separate experiments.

## Claims to leave out of the headline slide

| Topic | Current evidence status | Safe presentation wording |
|---|---|---|
| COPY, sink batching and compaction | Existing local journal has 276 observations, but its collector-qualified run FAILED | "The experiments exist; the current local diagnostic numbers are not a qualified performance win." Owner-host figures may be shown separately with attribution and their limits. |
| Real debit then reversal | Fresh rehearsal NOT_RUN: catalogue HTTP 503 during preparation, before checkout | "The ordinary 35-second expiry test is cancellation before debit; it does not prove a paid amount was refunded." |
| Full end-to-end throughput, scaling and stress | Not newly qualified in this report | "These SQL/storage component timings do not establish application capacity or Kafka scaling." |
| HNSW versus exact retrieval | Existing owner-host note reports recall 0.906; raw bundle absent locally | Attribute it as the owner's result; do not label it a fresh local measurement. |
| B-tree versus every possible data structure | Four local index types measured; no universal sweep | Do not claim that untested structures or database engines were benchmarked. |

## Files to give another LLM

1. **This file:** slide-ready conclusions, exact numbers, status labels and cautions.
2. **[Full report](PROFESSOR_QUESTIONS_AND_RESULTS.md):** methodology, fourteen questions, cost tables and source evidence.
3. **[CSV comparison](PRESENTATION_COMPARISON.csv):** numeric comparison rows for charts or tables.
4. Optional local raw evidence: `artifacts/defense/20261114-professor-final/defense-report.json`, `index-costs.json`, `query-fixture.json` and `query-reference-results.json`. These stay local and are not committed.

### Copy this prompt

```text
Create two clear presentation tables for a data engineering/distributed systems project using the attached PRESENTATION_COMPARISON.md and CSV. Use PROFESSOR_QUESTIONS_AND_RESULTS.md as the detailed source if attached.

Table 1: workload, approach, alternative, measured values with units, reason for the choice, trade-off, and evidence/deployment status.
Table 2: edge case, mechanism, observed numerical outcome, and invariant verified.
Then write a short speaker explanation answering why we used this approach rather than its alternative.

Rules:
- Use only the supplied measurements; do not invent values, confidence intervals or throughput.
- Label timings as warm local component experiments, not end-to-end application benchmarks.
- Distinguish a deployed mechanism from a measured candidate. GIN/BRIN were not deployed by these tests.
- Preserve negative results: summaries reduced representation size but the measured aggregate query was slower.
- Keep raw-plus-summary total storage separate from the summary-only representation reduction.
- Mark the fresh refund test NOT_RUN and existing failed collector results unqualified.
- Treat the seven saved real pipeline runs as reused evidence, not freshly executed comparisons.
- Do not claim a universal winner or a statistically proven production speedup.
Keep the main tables short enough for two slides; move detailed controls and caveats into speaker notes.
```
