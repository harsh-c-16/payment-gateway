# Relevance labels: how they were made and what they limit

**These labels are rule-derived, not manual.** The specification asks for manual 0–3 labels and allows
no unreviewed LLM labels (evaluation §3, runbook §6). The team chose not to label 903 rows by hand, so
this is a deliberate deviation. Any report using these scores must say so, and Jaineel should confirm
that it is acceptable before recording the hash in `configs/evaluation.yaml`.

| Item | Value |
|---|---|
| Rules | `rule_label` in `pipelines/catalog/relevance.py` |
| Per-query key | `contracts/fixtures/catalog/relevance_key.json` (`rules-v2`) |
| Labels | `contracts/fixtures/catalog/relevance_labels.csv` |
| `label_sha256` | `acb1a6e490cb309b298e8768a5f77fe0aff5f457a7cc6f0703922572694be928` |
| Pool | 903 rows across 45 queries; the top 10 of each of `filter_only`, `lexical` and `hybrid_exact`, in a hash order that hides the mode |
| Pool SHA-256 | `33a81b4829da600773ed9464eb9bda7a883eba17b3471545fa4ce834eb48f7e5`, reproduced byte for byte after the `deb084d` fix |

## How they were made

An LLM assistant drafted the rules and the key, and they are deterministic: nothing calls a model per
row, and the same pool and key always give the same labels.

1. The key for held-out queries was first written from the query text alone.
2. The rules were tuned on development rows only, frozen as `rules-v1`, then applied to held-out rows.
3. Reading the result showed errors, such as a teddy pencil box scored as a soft toy. Correcting those
   gave `rules-v2`, which changed 48 labels. **So the held-out labels are not blind to the rule
   author.** No NDCG had been computed at that point, the pool hides which mode returned each row, and
   no search code changed because of them.
4. Harsh approved `rules-v2` on 2 November 2026 with no corrections. The 60-row review sample was not
   returned, so **no row-level agreement figure exists**.

## The rules

Product type comes from the title alone, which is what a shopper sees. A brand name never counts as an
attribute. The first matching rule decides:

| Rule | Label |
|---|---|
| The query has no text (B18, S07, S16, S17), so nothing separates eligible products | Blank, unjudged |
| Title has an excluded word (a bra for a shirt search, a pencil box for a soft toy) | 0 |
| Wanted product not in the title, but the description names it (only `pendant`) | 2 |
| Wanted product not in the title, related product is | 1 |
| Wanted product not in the title, nor a related one | 0 |
| Product in title, an attribute missing from the title, and the title conflicts (silver plated for gold plated) | 1 |
| Product in title, an attribute missing from title and description | 2 |
| Product in title, all attributes in title or description | 3 |
| A label of 3 where the title shows a close match only (top sheet, sneaker, cream sold with a face wash) | Lowered to 2 |

Result: 319 labelled 0, 126 labelled 1, 39 labelled 2, 345 labelled 3, and 74 blank.

Hard constraints such as price, colour and size need no rule, because every pooled row already came
through the hard filters, and the experiments measured 0 violations.

## What this limits

- **Literal matching.** The rules reward exact title wording, as lexical search does. The key lists
  synonyms, but this still favours `lexical` over `hybrid_*`, so comparing them is indicative only.
- **The NDCG@5 ≥ 0.70 target cannot be claimed as human-validated.**
- **Five queries have no relevant product in their pool** (S01, S09, S12, S15, S19). They are reported
  separately and not scored as zero.
- **Five queries have one label throughout** (S13, U02, U03, U04, U05) and score 1.0 under any ranking.
  Reports show the mean with and without them.
- **Only the first 300 characters of a description are available** to the rules, so an attribute named
  later counts as missing.
- **`hybrid_ann` was not in the pool.** Its 7 unjudged results out of 192 count as 0.

## Regenerating

```bash
python -m pipelines.catalog.relevance pool --namespace NS --out pool.csv
python -m pipelines.catalog.relevance label --pool pool.csv --out labels.csv
python -m pipelines.catalog.relevance score --namespace NS --labels labels.csv --out ndcg.json \
    --modes filter_only,lexical,hybrid_exact,hybrid_ann
```

`NS` must be imported and stock-seeded, with embeddings loaded for the vector modes and the `r-ann`
index applied for `hybrid_ann`. Each report repeats `label_sources`, so a score cannot lose its
provenance. To replace these with human labels, fill the pool's `label` column by hand and pass that
file to `score`; nothing else changes.
