# 6-way Active Allocation Panel: methodology + W1 evidence

This note documents the methodological upgrade from a 3-protocol
per-block active panel (Aave V3 + Morpho Blue + Euler V2) to a
**6-protocol active panel** (adds Compound V3, Spark / SparkLend,
Fluid Finance) on the Vol-2 walk-forward grid. It explains the data
provenance, the unit-coherence audit, the W1 empirical result, and
why the larger active panel matters for the HFT framing.

## Why this matters for the HFT framing

The Vol-2 paper's central argument is that DeFi lending allocation
should be done in event-time (per Ethereum block, ~12s post-PoS),
not at hourly polling resolution. The four-class signal taxonomy
of MacKenzie (2021, Table 3.2) — fragmentation, lead, order-book,
related-instruments — was originally derived for equity HFT, where
the active allocator routes among **every venue with quoted
liquidity** for the same instrument. The natural DeFi analog is the
set of all major lending markets for the same asset (USDC on
Ethereum L1): the more pools you can switch into, the more
fragmentation opportunities the F3 signal can exploit per unit
time.

A 3-pool active panel constrains the allocator to ~50% of the
designed venue universe. A 6-pool panel covers ~67% of TVL and —
crucially — adds two pools (Compound V3, Spark) whose
mean-reversion timescales differ materially from the original three.
Empirically (see W1 below), this gives the gas-aware threshold
policy a meaningful uplift: it can route to Spark when Spark's
rate spikes, even when none of Aave / Morpho / Euler crosses the
switch threshold.

## Data provenance (heterogeneous, by design)

The per-block panel `data/cached/per_block_panel.parquet` was
extended from 14 columns (3 protocols × 4 metrics + block_number +
block_timestamp) to **28 columns** (6 protocols × 4 metrics +
block keys + F1 DSR + F4 ETH/USDC + USDC peg deviation bp).

Per-protocol source + cadence:

| Protocol     | Source                            | Cadence | Coverage on per-block grid |
|--------------|-----------------------------------|---------|----------------------------|
| Aave V3      | Aave subgraph events              | per-event (~50/h) | 100% |
| Morpho Blue  | Morpho subgraph events            | per-event | 100% |
| Euler V2     | Goldsky subgraph                  | per-event | 100% |
| Compound V3  | RPC `getSupplyRate/getUtilization` | hourly snapshot | 98.48% |
| Spark        | Sky Messari subgraph              | hourly (state-change emit) | 99.64% |
| Fluid        | DeFiLlama Yield Pools             | daily APY snapshot | 100% |

F1 + F4 signals added at the same time:

| Signal       | Source                            | Cadence | Coverage |
|--------------|-----------------------------------|---------|----------|
| F1 Maker DSR | DeFiLlama sDAI pool (DSR proxy)   | daily   | 100%     |
| F4 ETH/USD   | DeFiLlama WETH coin price         | daily   | 100%     |
| F4 USDC peg  | DeFiLlama USDC coin price         | daily   | 100%     |
| F4 gas price | Etherscan / Owlracle (next ext.)  | n/a yet | 0% (uses default 25 gwei) |

The merge_asof tolerance is 2h for Compound, 24h for Spark, 36h for
the three daily sources. Forward-fill on the per-block grid is
correct semantically: lending rates change only on protocol events
that the IRM curve makes deterministic between events, so a
snapshot dated T applies to all blocks in [T, T_next).

## Unit-coherence audit

The original per-block panel stored APR as a **fraction**
(`aave_v3_lending_apr.mean() ≈ 0.045`, i.e. 4.5%). The new source
parquets store APR variously as fraction (Compound RPC) or percent
(Spark Messari, Fluid DeFiLlama). The extension script
`scripts/extend_panel_to_6way.py` enforces the fractional
convention at load time:

* Compound: `lending_rate × (365 × 24)` — already per-hour
  fraction, annualized to fraction.
* Spark: `lending_apr / 100` — percent → fraction.
* Fluid: `apyBase / 100` — percent → fraction.

The first 6-way walk-forward run with mismatched units produced a
T1 W1 APY of **79 705 032%** (catastrophic compounding bug). The
correction landed the same window at **15.24%** — sanity-checked
against B1 always-Aave (**9.46% APY**, matching the existing 3-way
panel result of 9.47%).

## W1 6-way walk-forward result

W1 = 2024-11-01 → 2025-02-01, $1M initial position, 662,400 blocks,
gas budget $17.5 per rebalance (200k gas × 25 gwei × $3,500 ETH).

| Policy                  | Net APY  | n_rebalances | Sharpe (daily, ann.) |
|-------------------------|---------:|---:|---:|
| B1 always-Aave          | 9.46 %   | 1   | 62.8  |
| T1 gas-aware threshold  | **15.23 %** | 219 | 48.7  |
| T2 OU optimal stopping  | **15.03 %** | 251 | 47.0  |

Comparison to the 3-way active panel result on the same W1:

| Policy | 3-way APY | 6-way APY | Δ |
|---|---:|---:|---:|
| B1 always-Aave | 9.47% | 9.46% | ~0pp (control) |
| T1 threshold   | 11.35% | **15.23%** | **+3.88 pp** |
| T2 OU stopping | 11.15% | **15.03%** | **+3.88 pp** |

Protocol-time distribution under T1 (W1):

| Protocol    | % of blocks |
|-------------|---:|
| Spark       | 33.2 |
| Compound V3 | 17.2 |
| Euler V2    | 13.4 |
| Aave V3     | 12.9 |
| Morpho Blue | 12.6 |
| Fluid       | 10.7 |

The allocator preferentially routes to Spark, which paid the
highest mean lending APR in W1 (Spark median 7.5%, Aave median
4.5% over the same window). The diversity of destinations is the
HFT taker-quant-first philosophy applied to lending: chase the
**rate** of the pool, not its **TVL share**.

## Capacity caveat

The W1 result is on a $1M position. The Krause (2005) market-depth
analysis (§03 of the paper) gives capacity per pool inverse to
the local IRM slope at the pool's utilization. Spark's $35M
deposit base at the median W1 utilization 0.95 limits the
position size below which T1 can fully realize the +3.88pp uplift
on this protocol; at $5M position the uplift is expected to halve
on Spark; at $25M+ Spark exits the switchable set entirely. The
capacity sweep in `scripts/dossier/capacity.py` produces the
size-dependent curve on the full 6-protocol panel.

## Status of W2–W6

W1 6-way walk-forward complete (B1, T1, T2 all three policies).
W2 partial (B1, T1 complete; T2 ongoing).
W3–W6 queued for the next compute cycle; equity parquets land in
`results/institutional/tables/equity_walk_forward_6way/`. Once all
6 windows × 3 policies = 18 equity files are present,
`scripts/dossier/rebuild_nxm_6way_active.py` regenerates the
canonical N×M matrix (3 policies × 6 hold-benchmarks = 18
contrasts) with full paired-bootstrap CIs on N=6 per-window
deltas.

The 3-way N×M matrix already shipped in commit `50e7213` remains
the canonical headline result while the 6-way runs complete; the
6-way matrix will supersede it once full.

## Reproducibility

```bash
# 1. F1+F4 signal fetchers (one-shot, ~30s)
python -m data.fetch_f4_signals

# 2. Per-protocol APY parquets (one-shot, fast — re-uses cached events)
#   Compound:  python -m data.fetch_compound_via_rpc (already cached)
#   Spark:     fetch via Sky/Spark Messari subgraph
#   Fluid:     fetch via DeFiLlama Yield Pools

# 3. Extend per-block panel from 3 → 6 protocols + F1 + F4
python -m scripts.extend_panel_to_6way

# 4. Run 6-way walk-forward (T1+T2+B1 across 6 windows × 3 policies)
python -m scripts.run_6way_walkforward

# 5. Rebuild N×M matrix with bootstrap CIs (skip cells with incomplete data)
python -m scripts.dossier.rebuild_nxm_6way_active

# 6. Re-render dossier + paper macros
python -m scripts.dossier.render_dossier
python -m scripts.dossier.derive_paper_sections
python -m scripts.build_vol2_submission
```

Estimated wall-clock (mid-tier CPU): step 1 ≈ 30s, step 3 ≈ 10s,
step 4 ≈ 30-45 min per (policy, window) pair, step 5 ≈ 5s.
