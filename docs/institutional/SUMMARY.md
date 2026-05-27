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

**Scope** — **two scopes, not one**:
(i) *Active allocation panel* = **3 protocols** (Aave V3 + Morpho
Blue + Euler V2), unified per-block grid; T1/T2/T3 switch among
these three on every block.
(ii) *Hold-benchmark set* = **6 protocols** (the active three plus
Compound V3, Spark, Fluid); each enters the N×M as a passive
buy-and-hold counter-factual. Together the hold-benchmark set
covers ~$36B / ~$54B Ethereum L1 USDC-lending TVL (~67% of
design universe). Each matrix cell asks: "does this 3-protocol
active allocator beat passively parking USDC in protocol $j$?"
Data sources are heterogeneous to avoid single-vendor dependency:
per-block panel (Aave/Morpho/Euler); verified hourly RPC (Compound,
12,904 rows); Sky Messari subgraph (Spark, 6,189 hourly snapshots);
DeFiLlama Yield Pools daily APY (Fluid, 728 snapshots).
Ladder runs at **3 tiers** (T1, T2, T3); on F3-only features (F1/F4
queued for next extension), T3's hazard rule analytically reduces to
T1's threshold — empirically confirmed to ±0.01 pp on every contrast.

The deprecated **B4 hourly MCDM-EMA** (2026c straw-man: 2 rebalances
over 4 months) is intentionally absent from this matrix — the honest
baselines are the six protocol-holds themselves.

**Walk-forward N×M matrix** (3 active policies × 6 protocol-holds =
18 contrasts; 6 non-overlapping 3-month windows Nov 2024 – Apr 2026;
paired bootstrap N=6 per-window ΔAPY, B=10,000 resamples, seed=42):

| Policy | vs Aave | vs Compound | vs Spark | vs Morpho | vs Fluid | vs Euler |
|---|---:|---:|---:|---:|---:|---:|
| **T1** threshold | **+2.81pp**<br>6/6, p<10⁻⁴ | **+2.63pp**<br>6/6, p<10⁻⁴ | **+1.78pp**<br>6/6, p<10⁻⁴ | **+2.58pp**<br>6/6, p<10⁻⁴ | **+2.63pp**<br>6/6, p<10⁻⁴ | **+1.46pp**<br>5/6, p=0.026 |
| **T2** OU stopping | **+2.37pp**<br>6/6, p<10⁻⁴ | **+2.18pp**<br>6/6, p<10⁻⁴ | **+1.34pp**<br>6/6, p<10⁻⁴ | **+2.14pp**<br>6/6, p<10⁻⁴ | **+2.18pp**<br>6/6, p<10⁻⁴ | +1.01pp<br>2/6, p=0.216 |
| **T3** Cox F1+F3+F4 | **+2.88pp**<br>6/6, p<10⁻⁴ | **+2.70pp**<br>6/6, p<10⁻⁴ | **+1.85pp**<br>6/6, p<10⁻⁴ | **+2.65pp**<br>6/6, p<10⁻⁴ | **+2.70pp**<br>6/6, p<10⁻⁴ | **+1.53pp**<br>5/6, p=0.011 |

**Three concentric claims by decreasing strength**:

1. **Strong** (4/6 protocols, all 6 windows, p < 10⁻⁴): T1 and T2
   strongly outperform passive holds of Aave V3, Compound V3, Morpho
   Blue, and Fluid by +1.40 to +1.84 pp. ~$30B addressable TVL.
2. **Mid** (Spark, 5/6 windows, p ≈ 0.03–0.08): event-time edge
   present but smaller — Spark's young Aave-fork rates occasionally
   spike above the active allocator.
3. **Honest gap** (Euler V2, 2/6 windows): from W3 onward Euler is
   the top single-protocol yielder; no F3-only policy preferentially
   routes to it. Closing the gap requires F1 lead-rate signal —
   journal-extension scope.

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
