# Accounting capture of 697 Graph-discovered USDC markets

All 697 USDC market IDs returned by the MIRAGE subgraph at Ethereum block
**25938815** have stored accounting observations in this artifact. No market was
omitted and no capture failed. **This is an accounting-only dataset:** it does
not establish oracle credibility, an exit quote or permission to allocate.

The four-case workbench demo remains unchanged. A separate full-detector pass is
in progress; its eventual results must state their own completed coverage.

## Evidence and reproduction

- [Raw snapshot](../../mirage/snapshots/mainnet-accounting-25938815.json.gz)
  contains 697 unique market IDs and 1394 individual `eth_call` results:
  `idToMarketParams()` and `market()` for each market.
- Ethereum block hash:
  `0x6151b63f20f0f5fa115ccd736cf42d08759914eb60748c9b102d38a7ad9ffe00`.
- Snapshot SHA-256:
  `88ceb2bc1f7294cc3d5015209c85095baf2e4bbef0561558558abf20b0a4e361`.
- Source: live [MIRAGE Graph deployment](https://api.studio.thegraph.com/query/1759002/mirage-morpho-markets/v0.0.1),
  deployment `QmYkbwLirDouGqfRapedCcQ8YCbM8dzKA13agskDwGzJ6K`, queried at
  the same block and hash. The finalized anchor was rechecked during capture.
- Collection completed on 9 September 2026 at 09:40:07 UTC, in 898.44 seconds.
  All chain reads were individual JSON-RPC requests; no batch-response inference.

After installing `requirements-mirage.txt`, run from the repository root:

```console
python -m mirage demo --offline --snapshot mirage/snapshots/mainnet-accounting-25938815.json.gz
```

This replays and validates the supplied raw observations locally. A second
independent local check parsed the ABI words without importing the product's
decoders: 697 unique IDs matched the discovery manifest, all 1394 call targets,
calldata and block bindings matched, all 4182 stored market words fit `uint128`,
and all loan tokens were USDC. It reproduced the sums below exactly.
This is **not** an independent reread of all markets through a second RPC provider.
Local replay validates internal consistency, not the authenticity of an arbitrary
replacement snapshot.

## Stored balances, in USDC token units

| Stored field | Sum across the 697 markets |
|---|---:|
| Supply assets | 11,750,194,544.266864 USDC |
| Borrow assets | 11,650,901,635.717876 USDC |
| Supply assets minus borrow assets | 99,292,908.548988 USDC |

Supply and borrow are stored accounting asset amounts. They are not recovered
principal, a dollar TVL valuation, avoided losses or immediately withdrawable
cash. Supply minus borrow is the stored free-liquidity balance, not a guaranteed
withdrawal amount. No extra interest accrual was simulated. No market had a
negative stored difference.

## Findings and unfinished checks

| Accounting finding | Markets |
|---|---:|
| Stored accounting observed without this detector's warning | 602 |
| Elevated share exchange rate relative to the initial rate | 59 |
| Zero stored free liquidity, blocked under MIRAGE's entry policy | 36 |

All 697 also receive `remaining_checks_pending`. The combined admission result
is therefore **36 BLOCK and 661 INSUFFICIENT**, with **zero PASS**. A passing
accounting finding alone cannot grant admission. The zero-liquidity block is an
explicit conservative MIRAGE policy, not a claim that Morpho rejects deposits.
An elevated share exchange rate is not, by itself, proof of bad debt or insolvency.
