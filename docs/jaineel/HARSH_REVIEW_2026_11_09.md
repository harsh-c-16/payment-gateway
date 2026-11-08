# Harsh: frozen-input and report handoff

9 November 2026. These are the implementation choices Jaineel has prepared.
Harsh's approval is pending; no review receipt or performance result is invented.

## Input decision

Use the unchanged CSV, `flipkart-v1` rules, existing dataset revision
`flipkart-v1-3a401f32ca99379f8298ce42`, 19,920 active SKUs and canonical business
digest `d87f57e638ee1ab75743338516c4cfc1a2acfcc68d8f5493f828e7cfeb9e2bba`.
The packet generator validates the source checksum and the manifest/SKU
provenance, and refuses a dictionary whose LF identity differs from the manifest.

Two hashes have different purposes. Evaluation input pins use exact bytes,
as [runbook §1](../specs/09_EVALUATION_RUNBOOK.md#1-one-cli-and-reproducible-configuration)
requires. Your dictionary identity uses UTF-8 text with universal newlines and
continues to determine the existing dataset revision. We retain that identity;
we do not replace it with a Windows raw-byte hash or regenerate all SKUs.

Actual hashes observed on this Windows checkout:

| File / identity | SHA-256 |
|---|---|
| Source CSV, exact bytes | `56f8f699c9e847356666c2eab3c3ab1244340f6a98ad08e39ea2199ebe993ad1` |
| Dictionary, exact CRLF bytes | `7de194b5f49538e84a43ce91e734acae2182a0c96e3b743d668695ad6c6c2a02` |
| Dictionary, existing LF identity | `a7d381e90986b23f801eca537a689f2d3e056fa0b58040ecb7c182e2be2f9943` |
| Search queries, exact CRLF bytes | `14733547c0ce5690a79e3ea633d2b5ecdb0b5a133fd30e3fffcc175cf0ffcd63` |
| Search queries, published LF identity | `89d89ac030f10d23e85d6e5084caa125017b5f927a1ed94854aadc3be4762410` |
| Normalized manifest, exact bytes | `8fed5a445051b577cfcdc6e5eedcd2de8d302875c2a92f7495904df0d64a8b0e` |
| Normalized manifest, embedded canonical content hash | `0d214b4f88f928c9530f7f5838323c08fe2abfa5fc530c07020207c716a9e35b` |
| SKU manifest, exact bytes | `51632d83217a64946eda40f2ccdf1b2f90c62a9240c0798ac2dbed31a861fa75` |

Linux checkout bytes may differ. Generate the final packet once on the actual
execution machine, review it there, and retain those bytes for every comparator.
The verifier fails on even an LF/CRLF change. If a real input or rule changes,
make a new packet and rerun affected pairs; do not edit an old input lock.

## What to inspect or change

1. Confirm the revision, normalized/SKU manifests and dictionary identities above.
   Check the source mapping against [file 08](../specs/08_DATASET_PROFILE_AND_RULES.md),
   and the packet's `input_lock.json` and `input_hash_policy.json`.
2. Inspect generated W-IMPORT, W-PIPE, W-QUALITY, W-SEARCH and W-ANALYTICS recipes
   in `recipes.json`. Checkout/integrated request templates remain unavailable;
   their hashes remain null until frozen templates actually exist. Relevance
   scores derived by rules remain diagnostic; `retrieval.label_sha256` stays null
   pending human judgements. No ANN/model installation is needed for the core.
3. Review your two entries in `provider_review.proposed.json`, together with the
   validators in `projectctl/provider_validation.py`. After actual review, copy
   to a new `provider_review.json`, mark only reviewed entries `APPROVED` and list
   their actual owner and consumer reviewers. Unreviewed entries remain pending.
   A reviewed entry now becomes PASS through `contracts check`; stale bytes or
   a failing validator still fail. The receipt documents a review, not a live test.
4. Review the analytics audit mapping with Jaineel/Aditya/Vichitr. The proposed
   mapping pins raw exports, resource collectors, runtime, oracle and saved
   recheck code. In particular review null payload fields, paired publication
   generations, source IDs, quality reasons and read-only role/schema selection.
5. Supply the existing catalogue/query/layout callbacks using the team runtime
   extension described in the teammate runbook. Freeze each analytical layout's
   manifest generation and query day before execution. Complete operational
   migrations/seed/projection with Aditya before claiming fresh business setup.

Suggestions or corrections should identify the exact field, contract and affected
consumer. Do not change shared DTOs, price/stock semantics or the canonical spec
to fit a local test. Public changes need affected-owner review.

## Final report responsibilities

Jaineel runs saved reconciliation, paired comparison and `report build` using
actual artifacts. Harsh supplies the import/search/query bottleneck explanation,
query plans/index cost, every repetition and any null/unavailable I/O counters.
Vichitr supplies stream/scaling/freshness and publication/replay evidence;
Aditya supplies stock/ledger/saga/recovery evidence.

Keep all three repetitions, failures, resource costs and unresolved sample counts.
Owner experiments already documented in `docs/harsh/experiments.md` retain their
own machine/profile provenance; they are not automatically official runner pairs.
Do not combine them with a different resource profile or copy illustrative lab
numbers into final tables. C-BEST remains a measured selection, and final report
metrics stay null/NOT_RUN until the required real runs and independent gates exist.
