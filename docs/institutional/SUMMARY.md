# Institutional Dossier — Index

**Strategy**: Event-time gas-aware multi-protocol DeFi lending allocator
across Ethereum L1 USDC pools (Aave V3 + Morpho Blue + Euler V2).
**Status**: Backtest validated on real per-block data, 4-month
test window Jan – Apr 2026. Pre-mainnet (Sepolia paper-trade phase
ready per `agent/RUNBOOK.md`).

## TL;DR (1-minute verdict)

On a **$1M position** over the 4-month test window:

| Metric | T1 (this strategy) | B1 (passive Aave hold) | Delta |
|---|---:|---:|---:|
| Net APY | **4.56%** | 3.23% | **+133 bp** |
| Annualized Sharpe | **36.09** | 29.34 | +6.75 |
| Information Ratio | — | (benchmark) | **9.94** |
| Max DD | 0.000% | 0.000% | 0 bp |
| Final equity | $1,014,880 | $1,010,587 | **+$4,293** |

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
