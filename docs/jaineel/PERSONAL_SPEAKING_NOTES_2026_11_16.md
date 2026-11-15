# Jaineel: short speaking notes for 16 November

Use this for rehearsal; the [full viva guide](PERSONAL_VIVA_GUIDE_2026_11_16.md) contains schema details, alternatives, evidence and follow-up answers.

## Slide 1 — My contribution

> “I own M1, the session/cart/assistant workflow, and M0, the evaluation system. M1 preserves state and request identity, enforces quote/cart confirmation, and integrates the other services. M0 generates reproducible traffic, checks correctness independently, and reports measurements with their evidence.”

Harsh owns catalogue/search, Aditya owns transactions/outbox, Vichitr owns streaming/Gold. Your contribution to those paths is integration, orchestration and verification.

## Slide 2 — Architecture and schema

Draw: **Browser → M1 → Catalogue / Orders**; below M1: **PostgreSQL state + command journal + shared outbox → Kafka → Gold**. Draw your **generator/oracle/dashboard** observing the APIs and active analytical results.

> “A command journal saves the downstream request before calling another service. An outbox saves events with the local state change. The first handles an uncertain remote operation; the second handles reliable publication.”

**Star-schema question:** “My operational schema is relational tables plus JSONB snapshots, not a star. Sessions, carts, cart lines, turns and operation keys have different grains. Star/snowflake are analytical design alternatives; I did not benchmark them against my cart schema.”

Example: one cart, three line rows. Primary keys prevent duplicate lines; cart versions prevent stale confirmation. JSONB stores flexible context/responses; quantities, versions and identities remain typed and constrained.

## Slide 3 — Alternatives and results

> “I distinguish alternatives we considered from alternatives we actually measured.”

| Measured comparison | Numbers | What to say |
|---|---|---|
| Category + price: no optional index / B-tree / hash | **4.160 / 1.295 / 2.610 ms** | B-tree suited this equality-plus-range query |
| Keyword `shirt`: no optional index / GIN | **4.756 / 3.303 ms** | A text index serves a different predicate |
| Price-sorted range: B-tree / BRIN | **1.387 / 0.748 ms** | Physical layout matters; sorting cost was excluded |
| Raw / summary representation | **93,828 / 3,009 bytes** | Summary representation was 96.79% smaller |
| Raw / summary query | **2.585 / 2.805 ms** | Summary was 8.51% slower here; no latency win |

Always attach this sentence: **“These are warm local component experiments, three repetitions, not end-to-end platform capacity. The index probe used a catalogue projection and did not change production indexes.”**

Other architecture options—monolith, Redis, document-only state, full event sourcing—were design alternatives, not measured competing implementations.

## Slide 4 — Retention and edge cases

**Keep summaries?** “Yes, alongside the detail needed for audit/replay. Counts and sums cannot reconstruct individual events. Keeping both files costs 96,837 bytes, so the 96.79% is not a whole-platform saving.”

**Delete dedup IDs?** “Only after the supported redelivery/replay horizon and retention requirements are satisfied. Our policy probe produced one effect with the ID retained and two after unsafe deletion.”

Three personal edge cases to explain confidently:

1. **Repeated click/lost response:** same durable operation identity → same effect/order; changed body with same key → conflict.
2. **Stale cart/quote:** cart edit increments version and invalidates confirmation; first checkout after expiry needs a fresh quote. Recovery of an already accepted request keeps the original identity.
3. **Uncertain provider/model output:** pending remains pending; unavailable is visible; models cannot choose purchases or override authoritative amounts/explicit filters.

Three team cases you independently verified from retained real runs:

- Duplicate delivery: **3 deliveries → 2 logical events**.
- Last unit: **2 checkouts → 1 confirmed, 1 cancelled, 1 matching debit**.
- Late event: old window **1 → 2** in a newer active Gold generation.

## Slide 5 — Why this is data engineering

> “I track provenance and identity across requests, event deliveries, unique facts and published datasets. I validate counts and business effects independently, preserve raw measurements, and reject unfair comparisons.”

- Open-loop scheduling exposes missed arrivals and backlog instead of reducing demand when the service slows.
- Track **offered, admitted and completed** work separately.
- Track **outbox, Kafka lag and pending Gold** separately. Lag zero is not analytical completion.
- Report raw-duration quantiles with sample counts and unresolved work. Do not average p95s.
- Freeze source/config/resources and compare paired repetitions; do not select the fastest run.

Original dataset: **20,000 observations, 19,998 canonical listings, 19,920 active**. Historical catalogue; transactions/stock are simulated. A later source-colour edit changed the checksum: old measurements still belong to the original source revision.

## Slide 6 — Honest limits and lessons

> “Not every experiment produced a usable win. Summaries were smaller but slightly slower. BRIN depended on layout. A broader optimization run retained 276 observations but failed resource collection, so it remains unqualified. The full throughput/scaling matrix is not established by these component timings.”

Fresh focused checks: **649 passed, 0 failed, 0 errors, 0 skipped**. Tests used real PostgreSQL in isolated schemas and explicit external-provider doubles; saved live runs were checked separately. An initial connection-limit failure was resolved by using the deployed three-connection test budget, without changing application code or assertions. Details are in [the progress checkpoint](progress.md) and `artifacts/presentation/20261115-jaineel/evidence-verification.json`.

Keep these distinctions ready:

- Fixed benchmark assistant: **zero** generative calls. Current Gemini storefront: separate bounded conversational path; explicit purchases still use controls.
- At-least-once delivery plus deduplication: **one logical effect**, not universally exactly-once transport.
- 35-second cancellation before debit: **not a demonstrated refund**.
- Two-buyer race: **not a 100-buyer stress test**.
- Separate containers on one host: **not replicated multi-host availability**.
- Passed tests with explicit doubles: **not live model quality or a new full-service benchmark**.

If asked what comes next: “Freeze the current source revision and reviewed bindings, qualify B0, then complete the controlled batching/index/scaling/layout/integrated matrix with full resource and clock evidence.”
