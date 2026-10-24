# Repository working rules

This is Group 3's data-engineering project. Prioritize a correct measurable
baseline, pipeline optimization, reproducibility and independent reconciliation.

## Context and authority
- Read docs/OWNERSHIP.md, the current owner's brief and the relevant sections
  of docs/specs/01_PROJECT_CONTEXT.md, 02_COMMON_SPEC.md,
  03_EVALUATION_SPEC.md, 08_DATASET_PROFILE_AND_RULES.md and
  09_EVALUATION_RUNBOOK.md.
- The common spec defines interfaces; file 08 defines source mapping;
  files 03/09 define evaluation. Personal briefs assign implementation.
- Do not silently resolve a contract conflict by changing public behavior.
  Record exact conflicting requirements and the required owner/consumer review.
- Never treat old lab sample numbers as measured results.

## Scope
- Read across the repo as needed; edit only the active task owner's paths.
- Creating the initial scaffold is a one-time exception for directories,
  placeholders and ownership documentation, not business implementations.
- Do not replace another owner's implementation or canonical DTO.
- Keep shared specifications canonical in docs/specs; use links elsewhere.

## Implementation
- Use the frozen technology families and one reproducible application lock.
- Services communicate through documented APIs/events, not cross-service
  database writes or imports of service internals.
- Reuse the shared outbox, event transport and canonical DTOs.
- Fixed assistant mode makes zero generative calls. Optional assist follows
  the documented single-call policy. Purchase actions require explicit controls.
- Use integer minor units, UTC wire timestamps and monotonic elapsed timings.
- Preserve request identity, idempotency, cart versions and provenance.

## Evidence
- Implement one requested milestone, run appropriate checks and stop at its
  checkpoint. Fix failures within the milestone before reporting completion.
- Test doubles must be explicit. A stub pass is not a real integration pass.
- Missing providers, missing data and unexecuted checks must remain visible.
- Preserve raw evidence. Unmeasured results are null/NOT_RUN, not fabricated.
- Do not weaken assertions or skip required tests merely to obtain a green run.
- Record changed paths, exact commands, actual outcomes, evidence locations,
  remaining handoffs and manual verification steps in the owner's progress file.

## Git
- Preserve existing work. Inspect branch/status/diff before editing or committing.
- Never force-push, rewrite shared history or reset/delete unrelated work.
- Do not commit credentials, .env, raw datasets, generated data or benchmark
  result directories. Small deterministic test fixtures belong in Git.
- Commit and push only when the current task explicitly requests it.
- Use small feature branches and PRs after the initial shared scaffold.
