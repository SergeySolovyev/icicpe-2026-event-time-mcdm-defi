# Honest Limitations Audit — Event-Time MCDM DeFi Allocator

**Date:** 2026-06-01
**Auditor pass:** empirical re-verification of every claim against the
committed artefacts (`data/cached/per_block_panel.parquet`,
`results/tables/equity/*.parquet`,
`results/institutional/tables/*`, `results/models/t3_*.json`).
**Principle:** no finding is listed unless it was reproduced from the
data/code in this repository. File and line references are given so each
item is independently checkable.

This document is the research-integrity ground truth. The paper prose
must not claim anything this audit contradicts; conversely, the paper's
Limitations section should cover every TIER-1/2/3 item below.

---

## Executive summary

The **binding result is sound and leakage-free**: the T1 gas-aware
threshold rule beats passive single-protocol holds by +1.5–2.8 pp
annualized across the 6-way walk-forward, and T1 (online EWMA) and T2
(rolling-window OU) never see future data. The vulnerabilities are
concentrated in (a) the **T3 ML increment** (+7.03 bp H1c), which is
contaminated by train/test leakage and dominated by a single window, and
(b) the **"gas-aware" framing**, which runs on a constant 25 gwei because
real gas history was never fetched.

| Tier | # | Finding | Severity | Touches headline? | Fixable locally? |
|---|---|---|---|---|---|
| 1 | 1 | T3 walk-forward train/test leakage | HIGH | yes (H1c +7.03 bp) | **yes** |
| 1 | 2 | Gas is a flat 25 gwei constant | HIGH | yes ("gas-aware") | partial (sweep yes; real gas needs key) |
| 2 | 3 | Compound V3 TVL = constant 0 | MED | no (B4/capacity only) | needs RPC |
| 2 | 4 | Fluid utilization = constant 0.85 | MED | no (rate-based policy unaffected) | needs source |
| 2 | 5 | Fluid daily cadence in per-block loop | MED | partially (6% time-share) | inherent |
| 2 | 6 | usdt_peg column all-NaN | LOW | no | needs fetch |
| 2 | 7 | f1_dsr is a 17-level step function | LOW | F1 lift rests on it | inherent |
| 3 | 8 | W6 single-window dominance of +7.03 bp | MED | yes (H1c) | inherent (disclose) |
| 3 | 9 | N=6 walk-forward windows; CI floor +0.48 bp | MED | yes | inherent (disclose) |
| 3 | 10 | No MEV/slippage deducted in backtest | MED | yes (net edge) | needs model/data |
| 4 | 11 | Block timestamps via 12 s/block linear model | LOW | no | inherent |
| 4 | 12 | T2 over-trades (89–201 vs T1's 30–38 reb/window) | LOW | no | tuning |

---

## TIER 1 — Validity-affecting (touch headline claims)

### 1. T3 walk-forward train/test leakage  — HIGH, fixable locally

**Claim affected:** "the F1+F3 sophisticated-retrain T3 closes
pre-registered H1c with ΔAPY = +7.03 bp over T1 on the N=6 walk-forward
paired bootstrap (p=0.015)."

**Evidence:**
- `results/models/t3_sophisticated_training_report.json` → `params`:
  `panel_rows_dense = 3,931,200` (the FULL Nov 2024–Apr 2026 panel),
  `subsample_stride = 12`, `panel_rows_train = 327,600`.
- `scripts/train_t3_sophisticated.py:221-227` (`_final_fit`): the deployed
  model is fit on `train_idx = _subsample(np.arange(len(design)), …)` —
  i.e. a random subsample of the **entire** design matrix, with **no
  chronological cut-off**.
- `scripts/run_6way_walkforward.py:62-64` loads this single
  `results/models/t3_cox.json` and applies it to **all six** windows
  W1…W6 — every one of which lies inside the training span.

**Impact:** the +7.03 bp T3-over-T1 figure is an **in-sample** result
presented as walk-forward out-of-sample. The purged k-fold C-index
(0.563 F3-only / 0.582 F1+F3) is honestly out-of-fold and is *not*
affected; only the walk-forward APY comparison is contaminated.

**Why it is not catastrophic:** Cox PH with L2 penalty on 24 features is
low-variance; and the test-slice already shows T3≡T1 (the model barely
deviates from the threshold). So the leakage advantage is expected to be
small — but it must be measured, not assumed.

**Fix (local, no keys):** expanding-window walk-forward. For each window
W_k, fit T3 on blocks strictly before W_k's start (purged by the 7,200-
block horizon + embargo), then evaluate on W_k. Report the honest OOS
ΔAPY distribution. If it survives, H1c stands on firmer ground; if it
shrinks toward the test-slice null, reframe T3 as a conditional/at-scale
contribution.

### 2. Gas is a flat 25 gwei constant — HIGH, partially fixable

**Claim affected:** the paper's central framing as a "gas-aware
event-time allocator," and every gas-cost-crossover inequality.

**Evidence:**
- `per_block_panel.parquet` → `gas_price_gwei`: `nunique=1`, mean=25.0,
  std=0.0 across all 3.9M blocks.
- `data/cached/f4_gas_gwei_daily.parquet`: `gas_gwei` is also constant
  25.0 (nunique=1) — the "real" daily gas file is itself a placeholder.
- `data/fetch_f4_signals.py:136-141`: the Owlracle gas-history request is
  wrapped in try/except; on failure (no API key) it falls back to
  `rows = [{"timestamp": ts, "gas_gwei": 25.0} …]`. Real gas was never
  obtained.
- ETH/USD *is* real (`eth_usd` nunique=546, $1,470–$4,831), so gas **cost**
  varies via ETH price but the gas **price** (which historically swings
  10–300 gwei) is frozen.

**Impact:** the gas-cost gate is a fixed $17.5/rebalance threshold (at
$3,500/ETH). The allocator never sees congestion spikes that would
suppress profitable switching in reality. "Gas-aware" overstates a
"fixed-gas-cost gate." The effect is symmetric across all policies
(T1/T2/T3 all use the same constant), so cross-policy comparisons are
internally consistent, but the absolute net-APY and rebalance counts are
optimistic for high-gas regimes.

**Fix:**
- *Local now:* gas-sensitivity sweep — re-run T1 (and T2) at
  gas ∈ {10, 25, 50, 100} gwei and report how net APY and rebalance count
  degrade. This bounds the gas-awareness claim honestly.
- *Needs key (next-extension):* fetch real per-block/daily base-fee
  history (Owlracle/Etherscan/Dune) and rebuild the `gas_price_gwei`
  column; re-run the matrix.

---

## TIER 2 — Data-quality gaps (specific protocols / criteria)

### 3. Compound V3 TVL = constant 0 — MED, needs RPC

**Evidence:** `compound_v3_tvl_usd` nunique=1, mean=0. The Comet
view-call fetcher (`data/fetch_compound_events.py:166`) sets
`total_supplied_usd = NaN`; it materialises as 0 in the panel.

**Impact:** only the MCDM-EMA B4 baseline (TVL-weighted criteria; already
**excluded** from the headline benchmark set) and the capacity sweep
consume TVL. The rate-based T1/T2/T3 do **not** use TVL, so the active
allocator and all headline contrasts are unaffected. Capacity numbers
that involve Compound depth are unreliable.

**Fix:** add a `totalSupply×price` RPC call to the Comet fetcher
(needs `ETHEREUM_RPC_URL`). Next-extension scope.

### 4. Fluid utilization = constant 0.85 — MED, needs source

**Evidence:** `fluid_utilization` nunique=1 (=0.85). The Fluid daily
fetcher does not expose utilization; a placeholder was written.

**Impact:** the F3 utilization-spread sub-features and any kink-residual
decomposition involving Fluid are degenerate for 6% of held time. Fluid's
**lending APY** is real-daily (547 unique), so the rate-driven decision is
not fabricated — only the utilization covariate is.

**Fix:** source Fluid utilization from the FluidLiquidityResolver
(needs RPC) or drop Fluid's utilization features explicitly.

### 5. Fluid daily cadence inside a per-block loop — MED, inherent

**Evidence:** `fluid_lending_apr` changes every ~7,200 blocks (≈24 h);
T1 spends 6.0% of test-window time in Fluid.

**Impact:** switch decisions into Fluid act on a rate up to ~1 day stale.
A live agent reading Fluid's resolver faces the same staleness, so it is
realistic, not a backtest artefact — but it is **not** per-block rate
resolution. Already framed in the paper as "per-block decision loop, not
per-block resolution for the three slower venues."

**Fix:** none required (honest disclosure). Optional: restrict the active
set to the three genuine sub-hourly venues as a robustness variant.

### 6. usdt_peg column all-NaN — LOW

**Evidence:** `usdt_peg` nunique=0 (entirely NaN). The F4 signal-class
description mentions USDT peg deviation; it was never fetched. USDC peg
**is** present (`usdc_peg` nunique=397).

**Fix:** drop USDT peg from the F4 description, or fetch it. Cosmetic.

### 7. f1_dsr is a 17-level step function — LOW, inherent

**Evidence:** `f1_dsr_apy_pct` nunique=17 over 18 months (Maker DSR is a
governance-set step rate). The single +1.9 pp non-F3 OOF C-index lift
(the entire empirical case for the F1 lead-rate signal class) rests on
this low-cardinality covariate.

**Impact:** the F1 contribution is real but thin; a reviewer may note the
ML lever is one coarse step series. Disclose explicitly.

---

## TIER 3 — Statistical fragility (partly disclosed already)

### 8. W6 single-window dominance — MED

**Evidence** (`results/institutional/tables/t3_vs_t1_paired_bootstrap.csv`):
per-window ΔAPY = W1 +6.7, W2 +12.8, W3 −2.4, W4 +0.3, W5 +0.5,
**W6 +24.3** bp. Mean = +7.03 bp; **mean without W6 = +3.57 bp**; W6
alone contributes +4.05 bp = **58%** of the mean. 5/6 windows positive.

**Impact:** the H1c effect leans on one volatile window. Must be
disclosed alongside the +7.03 bp headline (currently only the full mean
is foregrounded).

### 9. N=6 walk-forward windows — MED

**Evidence:** `t3_vs_t1_bootstrap_stats.json`: mean +7.03, 95% CI
[+0.48, +14.74], one-sided p=0.0152, wins 5/6. The CI floor is +0.48 bp
— economically negligible and statistically marginal at N=6.

**Fix:** overlapping windows with an overlap-corrected (block) bootstrap
would tighten the CI; or report the result as directional. Inherent to
the 18-month coverage.

### 10. No MEV / slippage in the backtest — MED

**Evidence:** `backtest/replay_per_block.py:128-133` deducts only
`gas_cost_usd` on a switch; the slippage and MEV terms of Eq. (1) are not
applied in replay. The production agent uses the Flashbots private
mempool, but the backtest models neither MEV nor slippage.

**Impact:** public-mempool execution would face ~5–30 bp sandwich tax per
$1 M rebalance, which would erode much of T1's edge if executed
unprotected. Already disclosed in §V.3; keep prominent.

---

## TIER 4 — Minor / methodological

### 11. Block timestamps via 12 s/block linear model — LOW

`data/build_per_block_panel.py:39-50` maps timestamp↔block with a rigid
12 s/block post-merge model. Cross-protocol misalignment is **systematic**
(all protocols share the same map), not differential, so cross-protocol
spreads at a given panel block are consistently time-shifted by the same
small amount (seconds–minutes of slot drift). Negligible for spread
computation; noted for completeness.

### 12. T2 over-trades — LOW

T2 executes 89–201 rebalances/window vs T1's 30–38 (paper §IV.2). The OU
recalibrator over-responds to the richer signal space. Not a validity bug
— a tuning observation; T2 still beats holds but trails T1 net of gas.

---

## What is explicitly NOT broken (verified)

- **No NaN-accrual:** 0 of 863,999 test-window blocks accrue against a
  missing rate, for all of T1/T2/T3
  (`results/tables/equity/equity_*.parquet` joined to the panel).
- **Sign convention:** borrow ≥ lend holds on 100% of dual-non-null
  blocks for all six protocols.
- **T1/T2 leakage-free:** T1 updates its EWMA dwell only on executed
  switches (online); T2 calibrates OU on a `deque(maxlen=window)` of
  **past** spreads only (`decision/t2_optimal_stopping.py:59`). Neither
  sees future data.
- **Protocol existence:** all six have a first real observation at
  ~2024-11-01 (panel start); no mid-panel launch fabricates early-window
  allocation.
- **Stitcher is backward-only:** `build_per_block_panel` reduces with
  `groupby(block).last()` then forward-fills — no look-ahead.

---

## Recommended fix sequence

1. **#1 leakage (do first):** implement expanding-window walk-forward for
   T3; re-estimate the honest OOS ΔAPY vs T1; update
   `t3_vs_t1_paired_bootstrap.csv` + stats. Local, ~6 Cox fits + 6 replays.
2. **#2 gas:** gas-sensitivity sweep for T1/T2 at {10,25,50,100} gwei;
   add a small table. Local.
3. **#8/#9 disclosure:** add the "mean-without-W6 = +3.57 bp" caveat to
   the walk-forward table; keep the N=6 CI-floor caveat.
4. **#3/#4/#6 data gaps:** document as next-extension scope (need RPC);
   ensure the paper does not claim TVL/utilization fidelity it lacks.
5. Only **after** the research numbers are final and honest, propagate to
   the paper prose.
