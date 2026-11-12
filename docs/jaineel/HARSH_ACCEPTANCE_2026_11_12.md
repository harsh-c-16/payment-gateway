# Harsh handoff: Jaineel consumer acceptance

Reviewed on 12 November 2026 at repository HEAD `136e42d` (PR #21), with
Jaineel's delegated authority to make integration and presentation decisions.
This accepts the presentation handoff for M1/M0 consumption; it does not assert
that Harsh, Aditya or Vichitr signed a new formal review receipt.

## Accepted decisions

- Keep the unchanged CSV, `flipkart-v1`, dataset revision
  `flipkart-v1-3a401f32ca99379f8298ce42` and the existing SKU/dictionary semantics.
  Independent source checks here confirm the source SHA-256, all 20,000 rows,
  19,998 canonical listings, 19,920 active, 78 missing prices and 2 superseded
  observations. There is no reason to rebuild catalogue or seed the deployment.
- Retain the dictionary's LF text identity for the dataset revision. Evaluation
  pins still identify exact runtime bytes. Both published dictionary/query LF
  hashes match this checkout. Freeze execution-machine bytes when building the
  final evaluation packet; do not substitute CRLF hashes into dataset identity.
- Use Harsh's three demonstrated searches as the presentation cases, without
  hard-coding a purchasable SKU or dropping missing attributes. Real M1 requests
  on this Windows deployment reproduce all three expected behaviours.
- Accept `COPY` for prototype loading. Keep explicit I0=row and I1=copy for
  controlled experiments. No extra import is necessary on the retained stack.
- Present the I0/I1 table as **Harsh's owner-run SSD result**, with all three
  repetitions, equal-digest claim and host limitations. The medians in the
  supplied table support 3.31× faster staging and 21.6% lower total duration.
  His raw `artifacts/import-comparison-20261112/` and Linux rehearsal bundle are
  not present on this checkout. Their raw timings and six-run digest equality
  were not independently remeasured here. They are not shared-runner P9 results.
- Consume the updated transaction contract through the existing strict OpenAPI
  validator. Real M1 checkout, Orders observation and active Gold pass against
  it; no provider DTO, purchase policy or service implementation was replaced.

## Implementation and local acceptance

`python -m projectctl demo-check` supplies the missing repeatable presentation
preflight. `--state PATH` verifies the exact accepted order through the public
Orders and Gold APIs, preserving the original purchase state and request keys.
It never submits a purchase. Wrong filters, dataset identity, model use, duplicate
Gold facts and immutable order mismatches fail, with retained evidence.

The [Windows presentation guide](PRESENTATION_READY.md) gives start, verification,
demo, Gold observation and stop commands. The fresh rehearsal used real services
and retained data. It passed purchase/resume, no checkout without confirmation,
zero fixed-mode model calls, active Gold and read-only transaction snapshots.
The reservation was COMMITTED and one debit matched the quoted INR 1,166.00.

Evidence is local and ignored under `artifacts/presentation-20261112/`:
`source-check.json`, `input-pins.json`, `preflight-final/`, `purchase/`,
`no-confirm/`, `order-gold-final/`, `transaction-audit.json`, `rehearsal.json`,
`env-verify.log`, `projection.log`, test stdout/JUnit and the scripted driver.
The progress file records exact commands and outcomes, including failed first
attempts. No generated evidence, raw CSV or private binding belongs in Git.

## Work that remains outside presentation acceptance

The prototype is ready for the professor demonstration. Full M0 qualification
still requires all-owner byte-pinned receipts, complete reviewed evaluation
hooks/resources/clock mappings, registered correctness/fault campaigns, B0,
controlled paired repetitions and a report rebuilt from those artifacts.
`contracts check --all` still returns exit 4 for the missing formal receipts;
offline compatibility passes. Automated checks and this delegated consumer
decision do not fabricate the other owners' reviews or human relevance labels.
Live LLM/ANN evaluation remains optional. These requirements do not block the
working fixed-mode prototype.
