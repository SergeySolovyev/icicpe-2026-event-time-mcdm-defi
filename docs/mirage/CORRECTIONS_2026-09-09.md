# Corrections to the MIRAGE handoff — 9 September 2026

These corrections supersede the monetary and allocator claims in the external
`ETHOnline_2026/HANDOFF_v2.md` and the first hackathon README. The original
research notes are historical input, not submission-ready evidence.

## 1. Shares are not deposited principal

[SharesMathLib.sol](https://github.com/morpho-org/morpho-blue/blob/main/src/libraries/SharesMathLib.sol)
uses 1,000,000 virtual shares and one virtual asset. For a deposit of `a` assets,
shares minted are `floor(a * (S + 1e6) / (A + 1))`, where `S` and `A` are current
totals. Deposits after interest accrual buy a different number of shares.

Example: deposit 100 USDC, accrue 10 USDC interest, then deposit another 100.
Historical deposits total 200 USDC, claims total 210 USDC, and `S / 1e12` is
approximately 190.909090991735, not 200. Withdrawals burn shares, fees mint them,
and realized bad debt changes assets. See
[Morpho.sol](https://github.com/morpho-org/morpho-blue/blob/main/src/Morpho.sol).

Consequently, remove claims of $93,828 PAXG principal, $37.1m reconstructed
principal and $173m behind nonstandard oracles when calculated this way.
No one-snapshot principal reconstruction is implemented.

The retained diagnostic is the normalized exchange rate:
`1e6 * (A + 1) / (S + 1e6)`. It is not a measure of fictitious dollars, nor
proof of recursive borrowing, bad debt, insolvency or recoverable collateral.

## 2. Claims, liquidity and token balance are different quantities

Stored supply assets are accounting claims; stored borrow assets are debt.
Their difference is available market liquidity in loan-token base units.
[IMorpho.sol](https://github.com/morpho-org/morpho-blue/blob/main/src/interfaces/IMorpho.sol)
warns that market totals omit interest not yet accrued after `lastUpdate`.
Accruing interest adds the same amount to supply and borrow, leaving the
liquidity difference unchanged.

Comparing API supply claims with `USDC.balanceOf(singleton)` does not prove
that the API is wrong by 135×. Loans legitimately separate outstanding claims
from cash. Comparing $98.63m market liquidity with $97.01m token balance also
does not establish reconciliation. Both readings must be pinned to the same
block; the singleton can additionally hold USDC collateral or direct donations.

MIRAGE intentionally takes its monetary inputs from direct chain state. This
is a provenance boundary, not proof that every API figure is fictitious.

## 3. Warning labels were conflated

Recalculating the old local 697-market cache gives:

| Historical cache group | Markets | Available liquidity, USDC |
|---|---:|---:|
| Any RED warning | 130 | 9,150.004639 |
| No RED warning | 567 | 98,621,040.562096 |
| No warnings at all | 116 | 97,893,842.469036 |

Of the 567 without RED, **451 have YELLOW warnings**. Thus “unflagged” was
incorrect. These are calculations from an old cache without block provenance,
not live verification. A historical distribution does not establish that
Morpho warnings only arrive after losses or protect no meaningful funds.

## 4. The proposed TVL-to-T1 causal chain does not exist

[T1](../../decision/t1_threshold.py) ranks APR and compares expected extra yield
with gas. T2 and T3 likewise do not read `tvl_usd`. The replay engine transports
TVL in BlockState but never invokes the separate PredictiveMCDMStrategy.
That other strategy uses changes in TVL for stability, not raw TVL magnitude.

The [existing Morpho fetcher](../../data/fetch_morpho_events.py) selects
wstETH/USDC market `0xb323495f7e4148be5643a4ea4a8221eef163e4bccfdedc2a6f4696baacbc86cc`.
It does not rank all permissionless markets. Replacing its identity with PAXG
would make a misleading before/after demo. Use an explicit new market scenario
and show the original proposal beside MIRAGE's entry veto. Historical loss
avoidance needs a separate historically grounded experiment.

## 5. Oracle and bytecode evidence has narrower meaning

- `price() == 0x` is insufficient output. A fallback can return empty bytes;
  absence of code must be checked separately with `eth_getCode`.
- Equal prices at two sampled blocks do not prove constancy between them.
- A constant conversion can be intentional. Independent valuation and market
  semantics are needed before labelling it unsafe.
- Missing standard getters do not make bytecode the only possible source:
  proxies, storage and other ABIs can matter.
- revert.pro's feature extractor discards concrete operands. Enumerating PUSH
  values is new analysis and cannot label their roles without justification.
- Do not claim a vulnerability scanner addresses all bug classes outside its
  own coverage, or that an integration is unique without comparative evidence.

## 6. Fresh evidence retained

At block **25,937,912**, PublicNode and dRPC returned identical params/state:

| Market | Supply raw | Borrow raw | Supply shares raw | Free liquidity USDC |
|---|---:|---:|---:|---:|
| PAXG | 6212914536395500 | 6212914536395500 | 93828252743194492 | 0 |
| deUSD | 348282184849 | 348282174849 | 3176249715872670 | 0.01 |

Stored in [the immutable snapshot](../../mirage/snapshots/mainnet-25937912.json.gz).
SHA256: `cb9622f43a2a346882cfc9ee8bf4976dc224012148a1a032c2651a3696840ccb`.
Block hash: `0x03fd4567f54d76267464bd2219c8ba13a2d00ee94fc2757f45e0ab58646939eb`.
Each response was collected with an individual `eth_call`; all six market
ABI words were validated. Selectors and all 697 cached ID widths checked out.

These observations establish neither current whole-market totals nor a
historical principal. They support a precise accounting observation and an
explicit admission policy at the cited block.
