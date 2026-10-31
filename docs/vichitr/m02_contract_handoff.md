# ADR-M02 proposal: executable contracts and review handoff

Date: 31 October 2026. Status: Jaineel accepted the receipt format, as reported
by the user in this session. The shared fixture/generator and inventory assertion
are updated within that explicit authorization. Other producer/G0 reviews remain
pending; no canonical specification or service implementation was changed.

## Provided interfaces

- `shared/contracts/events.py`: the immutable envelope shape, 24 typed payload
  snapshots, metadata, `DlqNotice`, local diagnostic shape, validation failure,
  publish acknowledgement and topic/key selection.
- `contracts/events/*.schema.json`, `manifest.json` and
  `contracts/dictionaries/events/reasons.v1.json`: five business domains and
  separate DLQ, draft-07, pinned hashes and the 18 common §12 reasons.
- `shared/event_transport/schemas.py`: real registration/read-back, complete
  verified offline cache, online mapping/policy verification and pure validation.
  This does not yet expose M03's `build_event`/`validate_event`/broker wrappers.
- `shared/contracts/analytics.py`, `contracts/http/analytics.yaml`: manifest,
  source range, candidate, reconciliation, batch outcome, six HTTP contracts and
  health/readiness/metrics declarations. No running analytics API is claimed.
- `infra/streaming.py`: existing `env up` now registers schemas, while `env verify`
  requires a verified subject/version/ID/hash mapping. No competing CLI.
- `tests/pipelines/fixtures/events.v1.json`: deterministic synthetic owner-review
  examples, not historical data, benchmark measurements or live customer activity.

## Choices needing producer/consumer sign-off

| Reviewers | Concrete proposed binding | Required decision |
|---|---|---|
| Jaineel / conversation | `INTENT_REJECTED.restricted_content_reference`; `TOOL_CALLED.tool_call_id` is UUID; current turn outcomes/extractor sources match his DTO | Confirm producers emit these shapes without retaining raw free-form text in events |
| Harsh / retrieval | Session-keyed search facts; `PRICE_UPDATED` is SKU-keyed; `PRODUCT_COMPARED` uses aggregate_type `search` and aggregate_id `comparison_id` | Confirm optional compare identity, modes, embedded intent and real dictionary bindings; no compare event is fabricated |
| Aditya / inventory | `INVENTORY_REJECTED.reservation_request_id` is a UUID, required alongside a non-null order ID and reason | Common §11.4 requires a stable reserve-operation identifier but does not name it. Agree on this field before emitting per-SKU rejection facts |
| Aditya / order and payment | Required immutable snapshots, positive versions, matching event/state, stock-version equality; dataset and simulation provenance | Review all transaction examples; migrations/outboxes remain Aditya's responsibility |
| Jaineel / analytics readers | `{receipts:[...],next_cursor}`, `{records:[...],next_cursor}`; uppercase replay states; proposed `receipt_membership_ref` source-range field | Receipt item shape accepted by Jaineel via user confirmation; other pagination/range bindings still need review |
| All HTTP consumers | Internal `Authorization: Bearer <INTERNAL_API_TOKEN>` | Matches the existing client proposal; no alternative token header introduced |

Common §7 permits nullable envelope session/user identities outside session
facts. Payload order snapshots still carry their required user/session identity.
All catalogue-linked facts require `metadata.dataset_revision`; simulated
transaction facts require `synthetic=true` and `scenario_source=simulation` or
`benchmark`. Benchmark sources are restricted to `bench-` namespaces. Event time
is never copied from the historical CSV crawl time. Optional future values/nulls
remain in the original wire document for deduplication/provenance.

## Receipt agreement and former mismatch

Before this correction, `contracts/fixtures/p2/pairs.json`, example
`receipts-missing-timing`, contained this provisional test-only receipt:

```json
{"event_id":"00000000-0000-0000-0000-000000000008","disposition":"new_valid","silver_at":null,"visibility_generation":null}
```

The proposed `SourceReceipt` includes `namespace`, `source` with topic/partition/
offset/raw locator, `raw_sha256`, `event_id`, `disposition`, `reason_code`,
`ingested_at`, `bronze_durable_at`, `silver_committed_observed_at`,
`gold_visible_at`, `visibility_generation` and `timing_validity`. Missing Silver
or visibility observations are explicitly null; `timing_validity` is `missing`
or `recovery_upper_bound` when appropriate. Stage times are not fabricated.

The user confirmed that Jaineel agreed to this detailed receipt shape on
31 October 2026 and authorized updating the shared files. The fixture generator
and committed JSON now supply the required source/hash/stage fields, keep missing
Silver/Gold observations null and set `timing_validity=missing`. The old `silver_at`
field is removed. Regression coverage validates the accepted fixture against both
the actual OpenAPI and `ReceiptPage`, and proves the old shape is rejected.

`tests/contracts/test_contracts.py::test_contracts_check_all_preserves_missing_handoffs_in_evidence`
now expects analytics to be present and its receipt example to pass. It still
requires the checker to report genuinely missing catalogue/transaction contracts,
return dependency exit 4 and retain unmeasured metrics as NOT_RUN. It also asserts
there are no contract correctness failures. The P5/P6 expected exit remains 4;
no failing exit code is accepted merely to make CI green.

This is a fixture/contract migration before a running analytics API exists, so no
live reader or persisted database migration is needed. Other owner contracts,
SDK/outbox implementation and full G0 review remain incomplete.

## Verification and operational bounds

Run the offline owned tests:

```powershell
.venv/Scripts/python.exe -m pytest tests/pipelines -q
```

Start Docker Desktop, then run the existing low-memory profile and the real wire
test. It retains isolated fixture topics and does not advance business offsets:

```powershell
$env:PROJECTCTL_ADAPTER_MODULE='infra.streaming'
.venv/Scripts/python.exe -m projectctl env up --profile streaming-local
$env:RUN_CONTRACTS_LIVE_TESTS='1'
.venv/Scripts/python.exe -m pytest tests/pipelines/test_event_contracts_live.py -q
Remove-Item Env:RUN_CONTRACTS_LIVE_TESTS
```

Real evidence is in `artifacts/m02/`; runtime mappings are in
`artifacts/infra/streaming-local/registry-manifest.json`. These ignored runtime
files stay local. Generated schemas are environment independent. Cache loading
does not call the registry per event; a fresh process without a complete verified
mapping is unready. A cache authorizes only this build's pinned schemas, so a new
registry ID requires an explicit supported-schema/cache update. Check actual
compatibility across all retained versions before deploying changes.

M03 adds the agreed keyword-call builder and broker/offset SDK, then the
caller-owned transactional diagnostic helper. Real integration still requires
Aditya's shared outbox and owner-specific migrations. M04/M05 add actual durable
source receipts and active Gold. No CSV import, database business schema,
analytics HTTP runtime, Gold result or performance result is claimed here.
