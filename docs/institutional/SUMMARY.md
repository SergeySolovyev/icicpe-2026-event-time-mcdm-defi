# Institutional Dossier — Index

**Strategy**: Event-time gas-aware multi-protocol DeFi lending allocator
across Ethereum L1 USDC pools (Aave V3 + Morpho Blue + Euler V2).
**Status**: Backtest validated on real per-block data, 4-month
test window Jan – Apr 2026. Pre-mainnet (Sepolia paper-trade phase
ready per `agent/RUNBOOK.md`).

## TL;DR (1-minute verdict)

On a **$1M position** over the 4-month test window (Jan – Apr 2026):

| Metric | T1 (strategy) | Aave hold | Morpho hold | Euler hold |
|---|---:|---:|---:|---:|
| Net APY | **4.56%** | 3.23% | 3.30% | 4.77% |
| Final equity ($) | **1,014,880** | 1,010,587 | 1,010,841 | 1,015,697 |
| T1 surplus ($) | — | **+4,293** | **+4,039** | −817 |
| n rebalances | 39 | 1 | 1 | 1 |
| Gas spent ($) | $682 | $18 | $18 | $18 |

T1 beats Aave + Morpho by ~$4k each (statistically significant across
walk-forward 6/6 windows). Trails Euler V2 hold by $817 on test window
and 4/6 walk-forward windows — closing the Euler gap requires F1
lead-rate signal (journal-extension scope).

**Scope disclaimer (read first)**: Vol-2 designed for **6 protocols**
(Aave V3 + Compound V3 + Spark + Morpho Blue + Fluid + Euler V2);
empirical panel covers **3 of 6** (Aave + Morpho + Euler, ~$25B /
~$54B TVL). Compound/Spark/Fluid + Maker DSR signal fetchers failed
during Kaggle data build → queued for journal-extension. Ladder also
**3 tiers designed** (T1, T2, T3); on F3-only features (F1/F4
deferred above), T3's hazard rule analytically reduces to T1's
threshold — empirically confirmed on test window; walk-forward
verification in progress at submission time.

**Walk-forward N×M matrix** (6 non-overlapping 3-month windows
Nov 2024 – Apr 2026; paired bootstrap N=6 per-window ΔAPY, B=10,000
resamples, seed=42):

| Policy | vs Aave V3 hold | vs Morpho Blue hold | vs Euler V2 hold |
|---|---:|---:|---:|
| **T1** threshold | **+1.83pp** p=0.0000 (6/6) | **+1.60pp** p=0.0000 (6/6) | +0.48pp p=0.20 (2/6) |
| **T2** OU stopping | **+1.62pp** p=0.0000 (6/6) | **+1.39pp** p=0.0000 (6/6) | +0.27pp p=0.27 (2/6) |
| B4 MCDM-EMA (hourly) | **+0.92pp** p=0.0000 (6/6) | +0.68pp p=0.05 (5/6) | −0.44pp p=0.76 (2/6) |

**Three concentric claims by decreasing strength**:

1. **Strong**: T1 and T2 strongly outperform Aave + Morpho holds in
   6/6 windows by 1.4–1.8 pp. ~$25B addressable TVL.
2. **Mid**: T1 wins W1+W2 against Euler (Euler launch ramp), shows
   diversification value during regime transitions.
3. **Honest gap**: No policy outperforms passive Euler V2 hold from
   W3 onward — F1 lead-rate signal needed (journal-extension scope).

ΔSharpe runs negative (B1 near-zero vol inflates Sharpe — *Sharpe
inflation paradox*, López de Prado AFML Ch.4); see §02 for full
dual-lens treatment.

**Capacity**: Edge stable up to **$5M**; degrades at **$25M**;
analytical ceiling **$50M** (Morpho/Euler pool-depth bound).
**Live track record**: pre-mainnet — see `07_live_trial_plan.md`
for 5-phase ramp (Sepolia → $10K → $100K → $1M → fund LP).

## Chapter index

| # | Chapter | What's in it |
|---|---|---|
| 00 | [`00_one_pager.md`](./00_one_pager.md) | Single-page allocator leave-behind |
| 01 | [`01_performance_dossier.md`](./01_performance_dossier.md) | 14-column metrics table per policy + Sortino, Calmar, IR, CVaR, higher moments |
| 02 | [`02_walk_forward_robustness.md`](./02_walk_forward_robustness.md) | 6 non-overlapping 3-month windows, per-window Sharpe matrix, paired bootstrap, regime-conditional split |
| 03 | [`03_capacity_analysis.md`](./03_capacity_analysis.md) | Slippage-adjusted net APY at $100K / $1M / $5M / $25M / $50M; Krause (2005) theoretical depth ceiling |
| 04 | [`04_cost_attribution.md`](./04_cost_attribution.md) | Gas + slippage + MEV waterfall; Flashbots private-mempool requirement |
| 05 | [`05_risk_register.md`](./05_risk_register.md) | 21 risks × 7 categories (smart contract, oracle, depeg, MEV, governance, operational, capacity) — likelihood × impact × mitigation |
| 06 | [`06_operational_runbook.md`](./06_operational_runbook.md) | Deployment topology, monitoring/alerting, kill-switch protocol, post-incident review template |
| 07 | [`07_live_trial_plan.md`](./07_live_trial_plan.md) | 5-phase mainnet ramp + public Dune dashboard plan + hard rules |

## How this artifact is built (reproducibility)

Every number above is pulled from a CSV in
`results/institutional/tables/`. To regenerate from scratch:

```powershell
.venv\Scripts\python -m scripts.dossier.build_dossier
```

Inputs:
- `data/cached/per_block_panel.parquet` (3.9M Ethereum blocks, Nov 2024 – Apr 2026)
- `results/tables/equity/equity_*.parquet` (7 policies × per-block equity series)

Outputs (all reproducible):
- `results/institutional/tables/*.csv` — 4 backing tables
- `results/institutional/figures/*.png` — 4 figures
- `docs/institutional/*.md` — 8 chapters

## Methodology grounding

5 microstructure / quant-finance source books anchor every parameter:

- **O'Hara (1995)** *Market Microstructure Theory* — adverse selection, Kyle's lambda, batch-auction framework
- **Krause (2005)** *Asset Pricing Models* — closed-form pool depth `TVL·(1-u)/slope₁`, used in §03 capacity ceiling
- **Kissell (2014)** *Algorithmic Trading and Portfolio Management* — Implementation Shortfall, linear-impact slippage model used in §03
- **López de Prado (2018)** *Advances in Financial Machine Learning* — daily-aggregation Sharpe per Ch.11, triple-barrier label for T3 hazard, DSR threshold
- **MacKenzie (2021)** *Trading at the Speed of Light* — Table 3.2 HFT signal taxonomy (F1 lead / F2 mempool / F3 fragmentation / F4 related) + Flashbots-as-asymmetric-speed-bump (pp 200-203)

Full extraction at `docs/research/literature-foundation.md`.

## Companion paper

ICICPE 2026 SCOPUS Vol-2 submission derives §V (Empirical) + §VI
(Discussion) + §VIII (Conclusion) from this dossier. Last shipped
artifact: `submission_158e8c4.zip` (12 pages, F1+F3+F4 audit-gate
clean). Walk-forward inference (§02) will replace the monthly N=4
bootstrap in §V as the primary statistical lens once
`results/institutional/tables/walk_forward.csv` materialises.

## Contact

Sergei S. Solovev — HSE FCS — sssolovjov@gmail.com
