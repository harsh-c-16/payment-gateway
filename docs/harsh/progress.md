# Harsh progress

**Author:** Harsh Chaudhari (B24CM1027)
**Role:** M2: catalogue, retrieval, quotes, stock read model, Parquet compaction and query benchmarks
**Brief:** [05_HARSH_CHAUDHARI.md](../specs/05_HARSH_CHAUDHARI.md)
**Status date:** 8 November 2026
**Branch:** merged to `main` in PRs #3, #4 and #8; later work is on `harsh` until merged

Results: [experiments.md](experiments.md). What teammates need: [handoff.md](handoff.md). How the
relevance labels were made: [relevance_labels.md](relevance_labels.md).

`Real` means checked against real PostgreSQL, the real source file or the real publisher.

## Task status

| Task | Deliverable | Status | Checked by |
|---|---|---|---|
| H01 | Real CSV ingestion, normalization, staging and promotion, hashed manifests | Real; pinned manifests in `data/catalog/flipkart-v1-3a401f32ca99379f8298ce42/` | `test_real_source.py`, `test_import_live.py`, full CLI run below, [handoff evidence](handoff.md#manifests-and-projection-evidence) |
| H02 | Authoritative prices, idempotent quotes, internal lookup, price update | Real PostgreSQL and Aditya's real outbox; the relay to Kafka is not composed yet | `test_quotes_live.py`, `test_price_live.py`, `test_outbox_live.py` |
| H03 | Exact retrieval with hard filters; five search modes; 50 frozen queries | Real PostgreSQL and Aditya's real outbox | `test_search_live.py`, `test_vector_search_live.py`, `test_outbox_live.py`, 0 violations in every experiment |
| H04 | Stock consumer, read model, projection wait, freshness receipts, seed audit for the runner | Real PostgreSQL with records through the real codec. On a real broker, Vichitr ran the normal path; **the edge-case test is NOT_RUN** | `test_projection_live.py`; [Vichitr's run](../vichitr/progress.md) |
| H05 | I0/I1, B0/O2/P1, exact/HNSW | Owner runs done, with import and search repeated on the SSD; **official runner NOT_RUN** | [experiments.md](experiments.md) §§1–6 |
| H06 | Compaction candidates, Q1–Q6 through the real publisher, warm and cold series, compaction fault boundary | Owner run done on a synthetic fixture; **official runner NOT_RUN** | `tests/analytics/`, [experiments.md](experiments.md) §7 |

## Evaluation items I own

| Item | Status | Evidence |
|---|---|---|
| D-01 profile | Real | `catalog profile`: 20,000 rows, full-file accounting |
| D-02 normalization | Real | `catalog verify`: 19 of 19 assertions passed; 19,920 active, 78 inactive, 2 superseded |
| D-03 import twice, interrupt, resume | Real | `test_import_live.py`, including process death at named boundaries |
| D-04 W-IMPORT I0/I1 | Owner run; official NOT_RUN | Identical digests, [experiments.md](experiments.md) §2 |
| T-04 layouts | Owner run on a synthetic fixture | Identical query results across layouts |
| T-06 retrieval | Owner run; official NOT_RUN | Plans, recall by stratum, 0 hard-filter violations |
| T-09 projection | Normal path on a real broker: run by Vichitr on 6 November, 19,920 SKUs projected. **Edge cases on a real broker: NOT_RUN** | [Vichitr's progress](../vichitr/progress.md); the edge-case command is in [handoff.md](handoff.md#vichitr) |

## Full CLI run on the real file

`catalog profile`, `catalog import --load-mode copy` and `catalog verify` all exited 0:

| Fact | Value |
|---|---|
| Source SHA-256 | `56f8f699c9e847356666c2eab3c3ab1244340f6a98ad08e39ea2199ebe993ad1` |
| Dictionary SHA-256 | `a7d381e90986b23f801eca537a689f2d3e056fa0b58040ecb7c182e2be2f9943` |
| Dataset revision | `flipkart-v1-3a401f32ca99379f8298ce42` |
| Canonical digest | `d87f57e638ee1ab75743338516c4cfc1a2acfcc68d8f5493f828e7cfeb9e2bba` |
| Normalized manifest hash | `0d214b4f88f928c9530f7f5838323c08fe2abfa5fc530c07020207c716a9e35b` |

## Tests

Full suite on 8 November, after merging Jaineel's PR #9, with real PostgreSQL for the catalogue and
analytics tests: **1,723 passed, 348 skipped, 2 failed**.

- **The failures** are outside my paths, and both also fail on untouched `main`.
  - `tests/pipelines/test_postgres.py::test_success_evidence_contains_no_credentials` fails only in the
    full run; it passes alone.
  - `tests/pipelines/test_transport.py::test_m1_keyword_builder_and_existing_transaction_binding`
    needs M1's pinned schema cache; Jaineel has asked Vichitr to update it.
- **The skips** include my T-09 real-broker test, which needs a Kafka broker, plus other owners' tests
  that need services unavailable on this machine.
- **The brand-filter xfail is gone.** Jaineel fixed the check, so it is a normal passing test now.

## NOT_RUN, and why

| Item | Why | What it needs |
|---|---|---|
| Official W-IMPORT, W-SEARCH, W-ANALYTICS through the P9 runner, frozen limits | Jaineel's composition exists since 8 November; my hooks for it are in [handoff.md](handoff.md#wiring-the-runner), and the other owners' hooks are still missing | Jaineel's runtime module and the other owners' hooks |
| Catalogue events reaching Kafka | Rows land in `catalog_db`'s outbox, and the shared relay publishes them in a test; no process runs that relay yet | A relay process in the composition |
| T-09 edge cases on a real broker | No broker on this machine | [Command in the handoff](handoff.md#vichitr) |
| `infra/compose.catalog.yaml` running | No Docker on this machine; statically checked only | A machine with Docker |
| Human-judged relevance | The labels are rule-derived, and Jaineel decided on 8 November that their scores are diagnostic only ([relevance_labels.md](relevance_labels.md)) | A hand-reviewed label file |
| HNSW and hybrid search at 10× | The clone fixture has no vectors | Clone vectors too |

## What changed the plan

1. **The statistics bug.** Measurements showed a 60 ms-per-statement penalty for the first minute after
   every load. The cause was a missing `ANALYZE` in the real pipeline as well as the harness. It is
   fixed in `deb084d`, and every catalogue experiment was rerun. See
   [experiments.md](experiments.md) §1.
2. **The embedding dependencies stay out of `uv.lock`.** `configs/evaluation.yaml` pins that lock's
   hash, and core experiments must not carry them, so they sit in a separate hashed requirements file.
3. **A stress ladder was added.** The specification's stress protocol covers W-PIPE only, which left no
   evidence for session reuse under concurrency.
4. **Early runs were on a RAM filesystem.** I repeated import and search on the SSD. Conclusions held,
   except that P1's price-update gain drops from 10× to about 3.4×. See
   [experiments.md](experiments.md) §2a.
5. **The merged service broke Jaineel's workflow.** Reviewing it against the real service showed 33 of
   50 queries rejected over `candidate_count`. CI and my tests had not caught this. It is fixed, and a
   live test now covers it.
