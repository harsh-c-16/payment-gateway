# Three demonstration searches

Run on the prototype through the real client (`python -m projectctl demo`, fixed mode, zero LLM
calls) on 12 November 2026, after projection readiness (19,920 of 19,920 SKUs). Results come from
the real catalogue and stock read model; nothing was changed to produce them. Rank order is
deterministic for an unchanged catalogue and stock. If a listed product sells out it drops out
and the next one moves up.

```bash
.venv/bin/python -m projectctl demo --namespace dev --user-id demo-professor --query "<input>"
```

Raw request/response logs: `artifacts/rehearsal-20261112/searches/`.

## 1. Normal query: `men's formal shirt`

**Expected behaviour.** The text is used as a lexical query with no hard filters (the rules find
no category, price or colour in it). Five in-stock formal shirts come back:

| Rank | SKU | Title | Price |
|---:|---|---|---:|
| 1 | FK-SHTEGZB8HYN9BCZK | Hoffmen Men's Self Design Formal Shirt | INR 1,166.00 |
| 2 | FK-SHTEJR4G5K3TAMCM | Raymond Men's Printed Formal Blue Shirt | INR 1,259.00 |
| 3 | FK-SHTEJZKNDAFHN5MZ | KRiSS Men's Solid Formal Linen Blue Shirt | INR 879.00 |
| 4 | FK-SHTE6RHTHFGZE6VV | Kraasa Men's Solid Formal Shirt | INR 449.00 |
| 5 | FK-SHTEC88NBMXYK5ZD | Lamode Men's Checkered Formal Shirt | INR 399.00 |

The turn took 1.5 s, of which search was 1.0 s, inside M1's 3-second budget. This is the query
used for the purchase in the rehearsal: product 2, quantity 2, total INR 2,518.00, `CONFIRMED`.

## 2. Supported filtered query: `watches under 1000 rupees`

**Expected behaviour.** Two hard filters are extracted: `category = watches` and
`max_price_minor = 99999` ("under 1000" means strictly below ₹1,000). Every hit satisfies both.
474 of the 528 active watches qualify; the top five are:

| Rank | SKU | Title | Price |
|---:|---|---|---:|
| 1 | FK-WATDZNSHJHDTS9GN | HMT Sonata Gold Plated Watch For Men Sonata Analog Watch - For Men | INR 899.00 |
| 2 | FK-WATE5ZJZCGQUNQYF | Rana Watches Bw-Prsmd Barbie Analog Watch - For Girls | INR 199.00 |
| 3 | FK-WATEHZN5BG4SUKBY | PIEXIM mxre Moon Design Moving Dimonds Analog Watch - For Women & Girls … | INR 359.00 |
| 4 | FK-WATDDXF3D4SGXCW8 | Fastrack 9912PP15 Tees Analog Watch - For Men, Women | INR 750.00 |
| 5 | FK-WATEJAE8DFSKJDQE | V-Luma W600 Fashion Analog Watch - For Men | INR 699.00 |

The rehearsal used this query for the second session, where pressing Enter at the
`CONFIRM` prompt sent no checkout.

## 3. Unavailable attribute: `black watches under 1000 rupees`

**Expected behaviour.** The rules extract `category = watches`, `colour = black` and
`max_price_minor = 99999`. The answer is **"No products match these constraints. No filters were
relaxed."** No product is offered and no purchase can start.

This is the honest answer for this file. None of the 528 active watches records a colour,
because watch listings record `dial color` (461 of them) and `strap color` (493), and
flipkart-v1 reads colour only from the `color`, `colour` or `primary color` keys. A `null` colour
never satisfies a colour filter, and the assistant does not drop the colour to find something
([data sheet](DATA_SHEET.md#missing-prices-nullable-attributes-and-historical-prices)).

Two other honest outcomes, if asked:

| Input | Behaviour |
|---|---|
| `clothing in size XXL` | "No products match these constraints. No filters were relaxed." Only 4 active listings have an apparel size (3 × L, 1 × ONE_SIZE) |
| `waterproof watch` | "Please clarify: unsupported_attribute." Waterproofing is not a supported filter, so it asks instead of guessing |
