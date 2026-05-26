# Institutional Dossier — Design Spec

**Date**: 2026-05-26
**Author**: Sergei S. Solovev (HSE FCS) + Claude
**Status**: design approved, implementation pending
**Predecessor brainstorm**: this conversation, sections 1-3

---

## 1. Goal and audience

Build a **single, reproducible, fund-grade analytics artifact** for the
event-time MCDM DeFi lending allocator that serves two audiences:

- **Primary**: institutional allocators (DeFi-native funds, family offices,
  TradFi yield desks) evaluating the strategy for first-allocation tickets
  of $100K–$25M. Audience cares about Sharpe/Sortino/Calmar/IR, MaxDD,
  capacity, risks, live-track-record path.
- **Secondary, derivative**: ICICPE SCOPUS Vol-2 paper which becomes a
  ~20% summary of the dossier. The paper's §V/§VI/§VIII pull numbers
  and framings from the dossier rather than living independently.

The dossier ships as one Markdown document set plus backing CSV/figure
artifacts, all reproducible by a single command from the per-block panel.

---

## 2. Deliverables

```
docs/institutional/
├── 00_one_pager.md                  ← 1-page allocator leave-behind
├── 01_performance_dossier.md        ← full institutional metrics
├── 02_walk_forward_robustness.md    ← 6 non-overlapping windows
├── 03_capacity_analysis.md          ← $100K → $25M + $50M ceiling
├── 04_cost_attribution.md           ← gas + slippage + MEV
├── 05_risk_register.md              ← all risks + mitigations
├── 06_operational_runbook.md        ← deployment + monitoring + kill-switch
└── 07_live_trial_plan.md            ← Sepolia → mainnet ramp

results/institutional/
├── tables/
│   ├── institutional_metrics.csv    ← Sharpe/Sortino/Calmar/IR/CVaR/etc.
│   ├── per_protocol_pnl.csv         ← $ attribution per protocol
│   ├── walk_forward.csv             ← 6 windows × 7 policies × metrics
│   ├── capacity_curve.csv           ← position size × net APY
│   ├── cost_attribution.csv         ← gas/slip/MEV per rebalance
│   └── risk_matrix.csv              ← risk × likelihood × impact × mitigation
└── figures/
    ├── institutional_summary.png    ← 4-panel summary chart
    ├── walk_forward_heatmap.png     ← per-window × per-policy heatmap
    ├── capacity_curve.png           ← APY vs position size
    └── cost_waterfall.png           ← gross → gas → slip → MEV → net

scripts/dossier/
├── compute_institutional_metrics.py
├── walk_forward_validation.py
├── capacity_analysis.py
├── mev_sensitivity.py
├── build_dossier_figures.py
├── render_dossier.py                ← MD chapters with macro substitution
└── derive_paper_sections.py         ← rewrites paper §V/§VI/§VIII from dossier
```

---

## 3. Per-chapter spec

### 3.0 One-pager (`00_one_pager.md`)

**Length**: 1 page (≤350 words).
**Structure**: headline P&L, three-line strategy description, key
metrics table (Net APY, Sharpe, Sortino, Calmar, MaxDD, IR vs Aave),
capacity statement, risk one-liner, contact line.

**Content rules**:
- No jargon. "Net APY 4.60% on $1M, 39 rebalances, max DD 0.005%,
  Sharpe 5.0x Aave hold (p=0.011 paired bootstrap)."
- One chart: cumulative equity vs Aave hold over test window.
- Walk-forward verdict in one sentence: "Strategy outperformed Aave hold
  in N of 6 non-overlapping 3-month windows over Nov2024–Apr2026."

### 3.1 Performance dossier (`01_performance_dossier.md`)

**Length**: 4-6 pages.

**Metrics table** (per policy: B1/B4/T1/T2/T3):
- Net APY (after gas; before MEV deduction — separate ch 04)
- Sharpe ratio (annualized, daily-resolution)
- **Sortino ratio** (downside-only volatility, target = risk-free = 0)
- **Calmar ratio** (APY / Max DD)
- **Information Ratio** vs B1 Aave hold benchmark
- Max DD (%) + Max DD duration (days)
- **Time-to-recovery** from MaxDD (days)
- **CVaR₉₅** (5%-worst daily return tail, $ on $1M position)
- **CVaR₉₉**
- Skewness, Kurtosis of daily returns
- Total rebalances
- Total gas spent ($)
- Final equity ($)

**Per-protocol P&L attribution**:
- Dollars earned from time spent in each protocol
- For policies that switch (T1/T2/T3/B4): % of test window spent in each
  protocol × cumulative return while in that protocol

**Per-quarter breakdown**:
- 2026-Q1, 2026-Q2 (already exists in `regime_breakdown.csv`)
- Add Sortino/Calmar/IR per quarter

**Comparison to benchmarks**:
- T1 vs B1 Aave hold: ΔAPY, ΔSharpe, ΔSortino, ΔCalmar, IR
- T1 vs B4 (published MCDM): same
- T1 vs Buy-Hold Morpho, vs Buy-Hold Euler

### 3.2 Walk-forward robustness (`02_walk_forward_robustness.md`)

**Length**: 3-4 pages.

**Method**:
- Split Nov2024–Apr2026 panel into 6 **non-overlapping** 3-month windows:
  - W1: Nov 2024 – Jan 2025
  - W2: Feb 2025 – Apr 2025
  - W3: May 2025 – Jul 2025
  - W4: Aug 2025 – Oct 2025
  - W5: Nov 2025 – Jan 2026
  - W6: Feb 2026 – Apr 2026
- For each window: run replay engine fresh on each policy (no
  test/train contamination — policy parameters fitted from windows
  prior, or use stateless T1).
- Per window per policy: Sharpe, Sortino, MaxDD, ΔSharpe vs B1.

**Aggregate statistics**:
- Mean per-window ΔSharpe (T1 vs B1) — point estimate
- Paired bootstrap on N=6 window ΔSharpe deltas → 95% CI, p-value
- Directional consistency count: in how many of 6 windows does T1 beat B1?
- Worst-window performance
- Regime classification per window (low-vol vs high-vol spread)

**This is the primary inference for the paper.** N=6 walk-forward
windows gives substantially better statistical power than N=4 monthly
points on a single window, AND demonstrates regime robustness which
allocators care about more than headline p-value.

### 3.3 Capacity analysis (`03_capacity_analysis.md`)

**Length**: 2-3 pages.

**Position sizes**: $100K, $1M, $5M, $25M, $50M (last as analytical ceiling).

**Slippage model**:
For each protocol, the IRM curve gives marginal rate as function of
utilization. Adding/removing $V of liquidity shifts utilization by
`Δu = V / TVL × (1 - u_current)` and rate by `slope₁ × Δu` sub-kink.
For supply (our case): adding liquidity moves utilization DOWN and
supply rate DOWN (against us). Slippage = `0.5 × slope₁ × Δu` (linear
average impact).

**For each (position_size, protocol) cell**:
- Slippage per rebalance (bp)
- Effective rate post-slippage (used by replay engine)
- Re-run T1 + B1 + B4 at this size, compute net APY

**Output table**:
| Position | T1 APY | B1 APY | ΔAPY | T1 Slippage | T1 net APY post-slip |
|---|---|---|---|---|---|
| $100K | 4.60% | 3.23% | +137bp | 0.01bp | 4.60% |
| $1M | 4.60% | 3.23% | +137bp | 0.1bp | 4.60% |
| $5M | ~4.55% | 3.23% | +132bp | 0.5bp | 4.55% |
| $25M | ~4.30% | 3.20% | +110bp | 2.5bp | 4.27% |
| $50M | ~3.80% | 3.10% | +70bp | 5.0bp | 3.75% |

(Numbers illustrative; actual computed from real IRM slopes.)

**Krause (2005) theoretical ceiling**: `TVL × (1-u) / slope₁` per
protocol. Aggregate across in-scope protocols.

**Conclusion**: "Edge stable up to $5M; degrades meaningfully at
$25M; hits theoretical ceiling at $50M against Morpho/Euler pool
depths."

### 3.4 Cost attribution (`04_cost_attribution.md`)

**Length**: 2 pages.

**Three cost components, per rebalance**:
1. **Gas**: already computed by replay engine. Aggregate, distribution,
   per-quarter ETH-price sensitivity.
2. **Slippage**: from capacity-analysis IRM model. Per-rebalance bp.
3. **MEV**: not modeled in backtest. Report **sensitivity analysis**:
   - Public mempool worst case: 5/15/30 bp per rebalance.
   - Flashbots private mempool: 0 bp expected (asymmetric speed bump).
   - For each MEV scenario, show net APY impact at each position size.

**Waterfall chart**: Gross APY → −Gas → −Slip → −MEV(worst) → Net APY.

**Conclusion**: "Under public-mempool submission at $5M, MEV alone
could erase 50-80% of edge. Flashbots dispatch is therefore a
binding requirement, not optional."

### 3.5 Risk register (`05_risk_register.md`)

**Length**: 3-4 pages.

**Risk taxonomy** (each: likelihood / impact / mitigation):

**A. Smart contract risk**
- A1: Aave V3 exploit → mitigation: monitor governance forum + multi-protocol diversification
- A2: Morpho Blue exploit → same
- A3: Euler V2 exploit (note: Euler v1 was exploited 2023; v2 is rewrite) → tighter cap
- A4: USDC stablecoin issuer risk → diversification to USDT/DAI when peg deviates
- A5: ERC-4626 vault wrapper risk (if deploying via vault) → audited contracts only

**B. Oracle risk**
- B1: Chainlink price feed stale or attacked → use multi-oracle median + freshness check
- B2: IRM curve parameters changed by protocol governance → monitor + circuit-breaker

**C. Stablecoin depeg**
- C1: USDC depeg ≥1% → automatic withdraw to ETH or USDT
- C2: USDT depeg → same
- C3: DAI depeg (Maker dependency) → less critical, not direct exposure

**D. MEV exposure**
- D1: Sandwich attack on rebalance → Flashbots private mempool (binding mitigation)
- D2: Front-running on signal → asymmetric speed bump; latency monitoring

**E. Governance**
- E1: Protocol parameter change (kink, slope) → monitor proposals + circuit-breaker
- E2: Aave governance attack via flash loan → low likelihood, no specific mitigation needed
- E3: Morpho Blue isolated market parameters → market-level monitoring

**F. Operational**
- F1: Agent downtime → systemd watchdog + multi-region redundancy
- F2: Private key compromise → multisig for >$1M positions; HSM for keys
- F3: RPC provider outage → multi-provider failover (Alchemy + Infura + own node)
- F4: Gas price spike → built-in price ceiling; pause rebalances above N gwei

**G. Capacity / liquidity**
- G1: Pool TVL collapse (depositor flight) → automatic position size reduction
- G2: Concentration risk in small pools → hard position cap per pool

**Risk matrix**: 3×3 likelihood×impact heatmap with each risk labeled.

### 3.6 Operational runbook (`06_operational_runbook.md`)

**Length**: 3-4 pages.

**Production deployment topology**:
- Off-chain agent: cloud VM (AWS / DigitalOcean / Hetzner — gas-sensitive
  to network latency to RPC; AWS us-east-1 historically best for Ethereum)
- RPC providers: 2x primary (Alchemy + Infura), 1x failover (QuickNode or
  own node)
- Database: Postgres for audit trail + history.parquet snapshots
- Key management: HSM (CloudHSM / YubiHSM) for production keys; **never**
  filesystem keys above $100K
- Multisig for treasury (Safe / Gnosis) above $1M

**Monitoring & alerting**:
- Block-lag alert: agent missed > 100 blocks
- Gas spike alert: gas > 200 gwei sustained > 10 blocks
- Depeg alert: USDC|USDT > 50bp deviation
- Policy stall alert: no rebalance in 24h on a switching policy
- TVL collapse alert: in-position protocol TVL drop > 20% in 1h

**Kill-switch protocol**:
- Manual: operator sends `STOP` signal → agent withdraws all positions
  to USDC custody account
- Auto: triggered on (a) USDC depeg ≥1%, (b) in-position protocol
  exploit detected on Forta, (c) network-level chain reorganization
  detected

**Post-incident review template**: 5-section markdown (what happened,
detection time, response time, root cause, remediation).

### 3.7 Live trial plan (`07_live_trial_plan.md`)

**Length**: 2 pages.

**Five-phase ramp**:

| Phase | Network | Size | Duration | Success criteria | Abort conditions |
|---|---|---|---|---|---|
| **0** Sepolia | testnet | $10K notional | 1 week | ≥10 switches, no agent crashes, Flashbots dry-run path verified end-to-end | any unhandled exception, history.parquet corruption |
| **1** Mainnet shadow | mainnet | $0 (paper trade) | 4 weeks | Allocations match backtest predictions ±5%; gas costs within 2x model | systematic deviation from backtest > 10% |
| **2** Mainnet live | mainnet | $10K | 4 weeks | Net APY > Aave hold by > 20bp annualized; zero kill-switch events | net APY < Aave - 50bp; any safety event |
| **3** Mainnet scale | mainnet | $100K | 8 weeks | Net APY > Aave + 30bp; max DD < 50bp; SLA uptime > 99% | net APY < Aave; DD > 100bp |
| **4** Fund LP allocation | mainnet | $1M+ | ongoing | Track record published on Dune dashboard for transparency | per investor mandate |

**No phase >$25M without 12 months of mainnet track record at lower
sizes — hard rule documented in risk register.**

**Public PnL stream**: Dune Analytics dashboard with on-chain
attestable PnL series; updated daily; comparable to publicly-verifiable
Aave APY benchmark.

---

## 4. Backing-data scripts spec

### 4.1 `scripts/dossier/compute_institutional_metrics.py`

```python
def compute_metrics(
    equity_dir: Path,
    benchmark_policy: str = "b1_always_aave",
    risk_free_apy: float = 0.0,  # USDC is the numeraire
    daily_aggregation: bool = True,
) -> pd.DataFrame:
    """Compute Sharpe, Sortino, Calmar, IR, MaxDD, DD-duration, TTR,
    CVaR_95, CVaR_99, skew, kurt for each policy.

    Returns one row per policy. Aggregates per-block equity to daily
    before computing metrics (Lo 2002 convention).
    """
```

CLI: `--equity-dir results/tables/equity --out results/institutional/tables/institutional_metrics.csv`

### 4.2 `scripts/dossier/walk_forward_validation.py`

```python
def walk_forward(
    panel_path: Path,
    windows: list[tuple[pd.Timestamp, pd.Timestamp]],
    policies: list[str] = ("b1_always_aave", "b4_mcdm_ema",
                           "t1_threshold", "t2_optimal_stopping",
                           "t3_hazard"),
    seed: int = 42,
    n_bootstrap: int = 10_000,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run each policy on each window independently. Compute per-window
    Sharpe and ΔSharpe vs benchmark. Paired bootstrap on per-window
    deltas for aggregate inference.

    Returns: (per_window_metrics, aggregate_inference).
    """
```

Window definition fixed in the script (commit-time constants):
```python
WINDOWS = [
    ("2024-11-01", "2025-02-01"),   # W1
    ("2025-02-01", "2025-05-01"),   # W2
    ("2025-05-01", "2025-08-01"),   # W3
    ("2025-08-01", "2025-11-01"),   # W4
    ("2025-11-01", "2026-02-01"),   # W5
    ("2026-02-01", "2026-05-01"),   # W6
]
```

### 4.3 `scripts/dossier/capacity_analysis.py`

```python
def capacity_sweep(
    panel_path: Path,
    position_sizes_usd: list[float] = (1e5, 1e6, 5e6, 2.5e7, 5e7),
    protocols_to_model: list[str] = ("aave_v3", "morpho_blue", "euler_v2"),
) -> pd.DataFrame:
    """For each position size, run T1/B1/B4 with IRM-curve slippage
    model. Output table: (size, policy, net_apy, slippage_bp,
    rebalances, gas_spent).

    Slippage model: Δu = V/TVL * (1-u); rate impact = 0.5 * slope1 * Δu
    (linear average impact assumption). Sub-kink only; if size pushes
    pool above kink, mark as 'capacity exceeded' and skip.
    """
```

Slippage uses per-protocol slope1 hardcoded from IRM contract calls
(documented in `data/irm_params.json`, separate one-time fetch).

### 4.4 `scripts/dossier/mev_sensitivity.py`

```python
def mev_sensitivity(
    matrix_csv: Path,
    capacity_csv: Path,
    mev_bp_scenarios: list[float] = (0.0, 5.0, 15.0, 30.0),
) -> pd.DataFrame:
    """For each policy × position size × MEV scenario, compute net APY
    after gas + slippage + MEV deduction.

    MEV deducted as: n_rebalances × position_size × mev_bp / 10000.
    The 0bp column represents Flashbots private-mempool outcome.
    """
```

### 4.5 `scripts/dossier/build_dossier_figures.py`

Renders the 4 figures (institutional_summary, walk_forward_heatmap,
capacity_curve, cost_waterfall) from the CSVs above.

### 4.6 `scripts/dossier/render_dossier.py`

Markdown templating system. Each `docs/institutional/*.md` chapter
has a corresponding `templates/*.md.j2` (Jinja2) that pulls numbers
from `results/institutional/tables/*.csv`. The renderer:
1. Loads all CSVs into pandas DataFrames
2. Renders each Jinja2 template with the DataFrame context
3. Writes final `.md` files

This means **all numbers in dossier are reproducible** — change panel,
rerun pipeline, dossier regenerates.

### 4.7 `scripts/dossier/derive_paper_sections.py`

After dossier is built, rewrites paper §V/§VI/§VIII to draw on
dossier CSVs. Re-runs `fill_vol2_macros.py` with the **walk-forward
results** replacing the current monthly bootstrap as the primary
table. Drops the §V "monthly footnote" entirely.

---

## 5. Paper derivation strategy

After dossier is built:

1. **§V Empirical**: H1a/H1b/H1aux/H1c now use **walk-forward
   N=6 windows + paired bootstrap** as primary inference. The
   "monthly N=4 bootstrap" is dropped entirely (was never academic
   best practice for a 4-month series, per Lo 2002). DSR computed
   with N_trials=4 over the walk-forward statistics.
2. **§VI Discussion**: capacity analysis becomes a section.
   "The Krause (2005) theoretical capacity ceiling matches the
   empirical capacity floor from §3.3 of the dossier within an
   order of magnitude — double-confirmation."
3. **§VII Limitations**: structured from the risk register (3.5).
4. **§VIII Conclusion**: live trial plan (3.7) becomes the
   "concrete next steps" paragraph.

Paper stays at 10-12 pages. Numbers in paper are **strict subset**
of numbers in dossier — no claim in paper that isn't backed by a
dossier table.

---

## 6. Execution order

| # | Step | Effort | Why this order |
|---|---|---|---|
| 1 | Implement `compute_institutional_metrics.py` + write ch 01 + ch 00 | 1.5h | First-impression artifact + foundational metrics |
| 2 | Implement `walk_forward_validation.py` + write ch 02 | 3h | Closes the statistical-significance gap; high allocator-value |
| 3 | Fetch IRM params from on-chain, implement `capacity_analysis.py` + write ch 03 | 2h | Determines AUM cap for fund pitches |
| 4 | Implement `mev_sensitivity.py` + write ch 04 | 1.5h | Honest cost accounting |
| 5 | Write ch 05 (risk register) | 1h | Mostly text + risk matrix |
| 6 | Write ch 06 (operational runbook) | 1h | Largely extension of agent/RUNBOOK.md |
| 7 | Write ch 07 (live trial plan) | 0.5h | Structured doc, mostly text |
| 8 | Implement `build_dossier_figures.py` + 4 figures | 1.5h | Visual artifacts for one-pager |
| 9 | Implement `render_dossier.py` + Jinja templates | 1h | Reproducibility infrastructure |
| 10 | Run `derive_paper_sections.py` → rebuild paper + zip | 1h | Paper update from dossier |
| | **Total autonomous** | **~13h** | |

---

## 7. Acceptance criteria

The dossier ships when:

- [ ] `scripts/dossier/build_dossier.sh` (or equivalent makefile target)
  runs the full pipeline end-to-end and produces all 8 chapters + all
  10 CSVs + 4 figures, idempotent.
- [ ] All numbers in dossier chapters are pulled from CSVs (no hardcoded
  values; verified by `grep -n '[0-9]\.[0-9][0-9]' docs/institutional/*.md`
  showing only Jinja-rendered values).
- [ ] One-pager (ch 00) is ≤ 1 printed page when rendered to PDF.
- [ ] Walk-forward chapter (ch 02) reports per-window directional
  consistency: "T1 beat B1 in X of 6 windows" where X is computed,
  not assumed.
- [ ] Capacity analysis (ch 03) does NOT report position sizes above
  $50M (the analytical ceiling for current pool depths).
- [ ] Risk register (ch 05) has ≥20 distinct risks across 7 categories
  with explicit likelihood × impact × mitigation for each.
- [ ] Live trial plan (ch 07) has 5 explicit phases with abort conditions.
- [ ] Paper §V cites walk-forward N=6 as primary inference; monthly
  bootstrap is removed (not "moved to appendix" — removed).
- [ ] All Plan F audits (F1 refs, F3 anonymization, F4 page budget,
  F6 zip --check) still pass after paper derivation.
- [ ] New tests in `tests/test_dossier_*.py` cover the metrics
  computation, walk-forward windowing, slippage model, and MEV
  deduction. Property tests confirm:
  - Sortino ≥ Sharpe (since downside vol ≤ total vol)
  - Walk-forward window count = 6, non-overlapping, covers full panel
  - Capacity slippage monotone-increasing in position size
  - MEV deduction monotone-decreasing in net APY

---

## 8. Open questions deferred to implementation plan

These are not in scope of brainstorming and will be resolved during
implementation:

- Exact IRM slope1 values per protocol (need on-chain fetch; current
  best estimate from `data/fetch_kink_params.py`)
- Walk-forward training data leakage: T2's OU calibrator and T3's Cox
  model use rolling windows that may peek across walk-forward
  boundaries. Either (a) refit per window from scratch, (b) use
  global fit + accept mild leakage as conservative bound. Plan E
  T2/T3 implementations support (a); will use that.
- Jinja2 vs hand-rolled templating: Jinja2 is a 1-dep add; acceptable.
  Alternative: pure-Python format strings — simpler but more fragile.
  Will use Jinja2.

---

*This spec was produced through the `superpowers:brainstorming` skill
in conversation on 2026-05-26. Source design discussion captured in
the session transcript bundled with the next paper submission's
`LLM_TRANSCRIPT.md`. Implementation will be planned via
`superpowers:writing-plans` immediately after this spec is committed.*
