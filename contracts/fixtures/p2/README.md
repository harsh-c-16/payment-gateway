# Explicit P2 contract examples

`pairs.json` contains provisional, synthetic request/response examples only.
The catalogue is fictional and the stock is explicitly simulated. These examples
cannot establish the real dataset's counts, attribute coverage, prices or stock.

Schemas, scripted transports and the lost-response key ledger live exclusively in
`tests/contracts/`. Production clients never load this directory. Regenerate the
small examples deliberately with:

```powershell
python -m tests.contracts.provisional
```

See [the handoff/review notes](../../../docs/jaineel/p2_contracts.md) for provisional
headers, page wrappers and provider schema dependencies. Once canonical OpenAPI
files merge, `python -m projectctl contracts check --all` checks these pairs against
them. A consumer test pass currently means **stub verified**, with G0 incomplete.
