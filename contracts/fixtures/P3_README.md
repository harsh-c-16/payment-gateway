# P3 authored expectations

- [Dirty catalogue fixtures](catalog/dirty_catalogue.json) contain synthetic raw
  records and literal partial normalized-field/disposition expectations. They
  cover the 13 dirty-fixture families in runbook §3. Provider comparison is `NOT_RUN`.
- [Assistant scenarios](assistant/scenarios.json) contain 60 draft scenarios.
  Human review is pending, labels are unfrozen and relevance ground truth is null.
- [Adversarial identity cases](quality/adversarial.json) are separate from the
  primary W-QUALITY 98,500/1,000/500 arithmetic.

The larger W-QUALITY expectation JSONL is generated into ignored run artifacts by
`python -m projectctl fixtures build --config configs/evaluation.yaml --seed 42`.
It is a logical template, not a canonical event DTO or real traffic result.

Expected fields are authored in `tests/oracles/draft_fixtures.py`, independently
of provider modules. Deliberate fixture maintenance can regenerate the small files
with `python -m tests.oracles.draft_fixtures`; review the full diff afterward.
Do not treat regeneration or a double-backed check as human/provider approval.

See [P3 bindings, limitations and manual checks](../../docs/jaineel/p3_oracles.md).
