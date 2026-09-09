# MIRAGE — pre-deposit data-credibility checks for lending markets

**ETHOnline 2026 · Continuity Track** · built on top of this repository's existing
event-time USDC allocator.

Before an allocator moves USDC into a Morpho Blue market, MIRAGE checks three things
that nothing checks automatically today:

1. **Is the oracle price frozen?** An oracle can print a constant compiled into its own bytecode.
2. **Is the reported size a phantom?** Recursive self-borrow loops inflate `supplyAssets` by orders of magnitude.
3. **Can the collateral actually be sold?** Debt against the depth of the pool that has to absorb a liquidation.

**MIRAGE is not a yield optimiser.** It does not look for the highest rate. It *declines*
capital wherever the number the rate rests on does not match reality.

---

## Why this repository needed it

The allocator in this repository ranks venues on APY and TVL. That is exactly the input a
phantom market maximises. Measured on Ethereum mainnet on 2026-09-08, at block ~25 933 700,
by direct `eth_call` — the Morpho public API was used only to enumerate market ids, never for
a number:

| | |
|---|---|
| USDC markets on Morpho mainnet | 697 |
| What they **report** | **$11 743 183 052** |
| What can actually be **withdrawn** today | **$98 630 191** |
| Ratio | **119×** |
| Cross-check: `balanceOf(USDC)` on the singleton | $97 014 123 — agrees |

The worst single case, market `0x8eaf7b29…` (PAXG/USDC): reports **$6.21B**, recovers to
**$93 828** of principal against **$262** of collateral. Inflation **66 216×**, utilisation
exactly 100.000 %.

An allocator trained on APY and TVL drives straight into that. MIRAGE is the gate that stops it.

---

## BEFORE — what existed before the hackathon

Two public MIT repositories, both created well before ETHOnline 2026.

### This repository — event-time MCDM allocator

Created 2026-05-28. Last pre-hackathon commit `520b676`, 2026-09-05, 203 commits.

An event-time allocator for USDC across six Ethereum lending protocols: Aave V3,
Compound V3, Spark, Morpho Blue, Euler V2, Fluid. The central idea is dropping the
calendar grid in favour of **event time: one row equals one Ethereum block**. A panel of
3 931 200 blocks (2024-10-31 → 2026-04-30); `decide()` runs on every block; yield accrues
per block; gas is charged at the real gas price of that day.

A three-rung ladder of decision rules:

| Rung | File | What estimates the dwell |
|---|---|---|
| **T1** | `decision/t1_threshold.py` | EWMA of intervals between leader crossovers |
| **T2** | `decision/t2_optimal_stopping.py` | closed-form Bellman boundary on an Ornstein–Uhlenbeck spread |
| **T3** | `decision/t3_hazard.py` | `1/hazard` from a Cox proportional-hazards model |

All three reduce to one inequality: switch when the expected extra yield over the estimated
dwell exceeds the switching cost. The headline result is that **the simplest rung wins** —
T1, ~50 lines with no trained parameters, beats every passive single-protocol hold by
2.2–4.1 percentage points annualised across six non-overlapping three-month walk-forward
windows, while the ML rung honestly *loses* out of sample by 5.97 bp, 0 of 5 windows.

Reproduction notebook: `notebooks/reproduce_predictive_mcdm_defi.ipynb`, 77 cells, runs
end-to-end from the panel to the final ledger.

### Sibling repository — EVM bytecode feature extraction

[`SergeySolovyev/icicpe-2026-defi-vuln-detection`](https://github.com/SergeySolovyev/icicpe-2026-defi-vuln-detection), MIT.

A pipeline of 70 features computed **directly from EVM runtime bytecode**, no source
required, trained on 117 091 Slither-labelled contracts. It exists because roughly 95 % of
mainnet contracts ship without verified source, so source-required analysers cannot reach
them — but the bytecode is always there.

---

## AFTER — what is being built during ETHOnline 2026

Everything below is new work, committed incrementally from 2026-09-09.

### 1. Market-discovery subgraph — `subgraph/`

A Subgraph Studio subgraph indexing **only** the Morpho Blue `CreateMarket` event.

- `subgraph/subgraph.yaml` — manifest, specVersion 1.0.0, startBlock 18883124
- `subgraph/schema.graphql` — one immutable `Market` entity
- `subgraph/src/morpho-blue.ts` — the single handler, **zero `eth_call`**
- `subgraph/abis/MorphoBlue.json` — the one event, nothing else

1763 events, all ids unique. `CreateMarket` carries `loanToken`, `collateralToken`,
`oracle`, `irm` and `lltv` in the log data itself, so the mapping never touches the chain.

State-changing events (`Supply`, `Withdraw`, `Borrow`, `Repay`, `AccrueInterest`,
`Liquidate`) are **deliberately not indexed** — roughly 17.5M events, the sync would not
finish. Market state is read from the chain through Multicall3 instead.

**Division of labour:** the subgraph answers *which markets exist and with what parameters*;
the chain answers *how much money is actually there*. That boundary is what makes every
dollar figure in this project independent of any API.

### 2. Three detectors — `mirage/detectors/`

| Detector | Method |
|---|---|
| **Frozen price** | `price()` at head and head−1 000 000; for factory oracles also the six immutable getters — all six zero means the price is compiled in |
| **Phantom volume** | principal = `supplyShares / 1e6`; inflation = `supplyAssets / principal`; free liquidity = `supplyAssets − borrowAssets` |
| **Exit depth** | debt priced by the oracle over the dollar depth of the pool that quotes it |

Order matters: **phantom volume runs first**, and its principal feeds the other two. Without
removing phantom inflation, no dollar figure on Morpho means anything.

### 3. Uniswap price reference — `mirage/detectors/reference_price.py`

A Uniswap v3/v4 TWAP as an **independent** reference price against whatever the market's
oracle prints. This is not decoration: it is the only thing that separates *frozen* from
*the collateral genuinely is worth par*. The USDT/USDT pair carries a constant oracle and
that is correct, because it is redeemable at par on demand — MIRAGE reports it as its own
false positive.

The same module supplies pool depth for the exit-depth detector.

### 4. Bytecode path for oracles with no interface

Measured, not asserted:

| Oracles | `BASE_FEED_1()` answers | Silent |
|---|---|---|
| Factory (455) | **455** | 0 |
| **Non-factory (137)** | 9 | **128** |

For the 455 factory oracles MIRAGE reads immutables through public getters — four
`eth_call`s, exact and cheap. For the 128 that answer nothing, the runtime bytecode is the
only remaining instrument, and that is where the sibling repository's machinery is reused:
the same `pyevmasm` dependency, the same input-normalisation pattern, the same
program-counter index. **$173 162 872** of principal on listed markets sits behind those
non-factory oracles.

### 5. Gate into the allocator — `mirage/gate.py`

`MirageGatedPolicy` implements the existing `DecisionPolicy` ABC from
`decision/base.py:87-99`, so it drops into `EventReplayEngine` at
`backtest/replay_per_block.py:126` without a single line changed in the engine.

A before/after backtest runs the same engine over two panels — one where Morpho TVL comes
from the API, one where it comes from on-chain principal — so the damage is *demonstrated*,
not claimed.

---

## Judges: how to verify a number yourself

Every finding in the public feed carries the literal `eth_call` behind it — target, calldata,
block, raw return:

```json
"evidence": [{"to": "0xBBBB…", "data": "0x5c60e39a8eaf7b29…", "block": 25933700, "result": "0x…"}]
```

Paste it into `cast call` and you get the same number. Two examples you can run right now:

```bash
# Phantom volume: market(bytes32) on the Morpho singleton
cast call 0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb \
  "market(bytes32)(uint128,uint128,uint128,uint128,uint128,uint128)" \
  0x8eaf7b29f02ba8d8c1d7aeb587403dcb16e2e943e4e2f5f94b0963c2386406c9

# Frozen price: the same oracle contract that priced USD0++ in January 2025
cast call 0x1325Eb089Ac14B437E78D5D481e32611F6907eF8 "price()(uint256)"
cast call 0x1325Eb089Ac14B437E78D5D481e32611F6907eF8 "BASE_FEED_1()(address)"
```

That oracle prints exactly `1e24` at head and one million blocks back, with all six address
immutables zero. Today it also prices **deUSD/USDC**, whose issuer has publicly stated the
asset no longer has value.

---

## Known limits, stated up front

- **Bytecode analysis covers roughly 20 % of exploitable bug classes** (ICSE 2023, sample of
  516 real bugs). MIRAGE addresses the other 80 % by checking *data credibility* rather than
  code correctness. It does not claim to be a vulnerability scanner.
- **Morpho already publishes `warnings`** and has since May 2024. MIRAGE does not replace
  them. What it adds is measurement: from a `warnings` array you cannot learn that a
  reported $6.21B is really $93 828. Separately, markets Morpho flags RED hold **$9 150** of
  free liquidity between them, while **100 %** of live money sits on unflagged markets.
- **MEV is not modelled** in the backtest, and the reference deployment does not yet route
  through a private mempool.

---

## Repository layout

```
decision/          T1 / T2 / T3 policies + F1/F3/F4 feature builders   [pre-existing]
backtest/          per-block replay engine, bootstrap, ablations       [pre-existing]
data/              panel construction + ~20 protocol fetchers          [pre-existing]
forecaster/        DA-BiGRU-CNN and classical baselines                [pre-existing]
notebooks/         reproduction notebook, 77 cells                     [pre-existing]
papers/            manuscript sources                                  [pre-existing]
subgraph/          Morpho CreateMarket subgraph                        [NEW — hackathon]
mirage/            detectors, chain readers, feed, allocator gate      [NEW — hackathon]
```

---

## Quick start

```bash
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements.txt

# Subgraph (needs a Subgraph Studio deploy key)
cd subgraph && npm install
node .\node_modules\@graphprotocol\graph-cli\bin\run.js codegen
node .\node_modules\@graphprotocol\graph-cli\bin\run.js build
```

---

## License

MIT — see [`LICENSE`](LICENSE).

## Author

Sergei Solovev — [github.com/SergeySolovyev](https://github.com/SergeySolovyev)
