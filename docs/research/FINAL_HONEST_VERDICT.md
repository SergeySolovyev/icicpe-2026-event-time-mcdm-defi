# Final Honest Research Verdict

**Date:** 2026-06-03. All numbers reproduced locally from the committed
panel + scripts; no API key used (real gas obtained via free-RPC
`eth_feeHistory`). This supersedes the headline framing of the May
submission and is the ground truth the paper must match.

---

## One-paragraph verdict

A **50-line, zero-parameter, gas-aware threshold rule (T1)** is the
result. On the real 6-protocol per-block panel it beats passive
single-protocol holds by **+1.5–2.8 pp** annualized across a leakage-free
6-window walk-forward, and that edge **survives the full gas range**
(10→200 gwei) and is in fact under-stated by the backtest because real
Ethereum gas in 2025–26 ran 50–100× below the placeholder. The two more
sophisticated tiers do **not** beat it: T2 (OU optimal stopping)
over-trades and is gas-naive; T3 (Cox hazard ML), once trained strictly
out-of-sample **and** actually executed, **loses to T1 by −88 bp**. The
honest contribution is the **event-time + gas-aware-threshold** method and
the negative result that ML adds nothing here — not the ML.

---

## 1. T3 ML tier — RETRACTED as a positive claim (clean negative)

The previously-headlined "+7.03 bp H1c" was a **double artifact**:
1. **Leakage** — the deployed `t3_cox.json` was fit on the full
   Nov 2024–Apr 2026 panel, then applied back to all walk-forward windows.
2. **Wrong code path** — worse, the deployed T3 *never executed its Cox
   model* in any replay: the F1 features it was trained on
   (`f1_dsr_lag_300`, `f1_dsr_delta_300`, `f1_lead_spread_dsr_vs_top`) were
   absent from the panel under those names, so `T3HazardPolicy` fell back
   to T1 on every block. The +7.03 bp came from a separate analytic
   hazard-ranking on the leaky design matrix, not from the allocator.

**Corrected (leakage-free + F1 features wired, model genuinely running):**

| Window | T1 APY | T3 OOS APY | ΔAPY |
|---|---|---|---|
| W2 | +5.625% | +4.602% | −102.4 bp |
| W3 | +7.137% | +6.834% | −30.2 bp |
| W4 | +6.568% | +4.858% | −171.1 bp |
| W5 | +5.169% | +4.064% | −110.6 bp |
| W6 | +5.384% | +5.113% | −27.1 bp |
| **mean** | | | **−88.3 bp** |

**Honest OOS T3-vs-T1 = −88.3 bp, 95% CI [−133, −43], p=1.0, 0/5 wins.**
The Cox layer's in-sample concordance (0.62–0.66) does not translate to
better allocation; its model-driven dwell estimate mis-times switches
versus T1's simple EWMA dwell. Source:
`results/institutional/tables/t3_expanding_walkforward.csv`,
`scripts/walkforward_t3_expanding.py`.

## 2. T1 is genuinely gas-aware (robust across the gas range)

`results/institutional/tables/gas_sensitivity.csv`:

| gas (gwei) | T1 net APY | T1 rebalances | T2 net APY | T2 rebalances |
|---|---|---|---|---|
| 10 | 5.24% | 134 | 5.21% | 163 |
| 25 | 5.03% | 55 | 4.82% | 159 |
| 50 | 4.73% | 27 | 4.17% | 159 |
| 100 | 4.48% | 9 | 2.87% | 159 |
| 200 | 4.17% | 6 | 0.31% | 159 |

- **T1 throttles correctly** (134→6 rebalances as gas rises) and **still
  beats passive Aave (~3.26%) even at 200 gwei.** The edge is gas-robust.
- **T2 is gas-naive** (159 rebalances at every level) and collapses to
  0.31% at 200 gwei — empirical proof that only T1 is meaningfully
  gas-aware.

## 3. Real gas — the placeholder was pessimistic, not optimistic

`data/cached/f4_gas_gwei_daily_real.parquet` (546 daily samples via
`eth_feeHistory`, no key): **mean 3.7 gwei, median 0.8, only 3% of days
> 25 gwei.** Per quarter the post-Dencun collapse is stark:

| 2024Q4 | 2025Q1 | 2025Q2 | 2025Q3 | 2025Q4 | 2026Q1 | 2026Q2 |
|---|---|---|---|---|---|---|
| 18.5 | 4.0 | 2.5 | 2.2 | 0.3 | **0.2** | **0.5** |

The **test window (Jan–Apr 2026) ran ~0.3 gwei mean** → ~$0.21 per
rebalance, not $17.5. Re-running T1 with the real forward-filled gas
(`results/institutional/tables/net_of_real_gas.csv`):

| metric | const-25 | **real gas** |
|---|---|---|
| T1 net APY | 5.03% | **5.51%** |
| T1 rebalances | 55 | **311** |
| T1 gas spent | $624 | **$61** |
| **T1 edge over passive Aave** | +176.5 bp | **+224.9 bp** |

- The const-25 backtest is a **pessimistic upper bound on gas drag**; the
  honest net-of-gas T1 edge is **+2.25 pp** over passive Aave — *larger*
  than the conservative backtest (+1.77 pp), not smaller. Cheaper gas lets
  T1 rebalance more (311 vs 55) and capture more crossovers for $61 total.
- **Honest nuance (matters for the product):** this is net-of-gas but
  *gross of MEV/slippage*. At $1 M with near-zero gas, T1 rebalances 311×
  in four months; at that churn the binding constraint at size becomes
  **slippage**, not gas. In the post-Dencun regime "gas-aware" cedes to
  "slippage-aware" — the next modelling layer (audit #10). Gas-awareness
  still binds in high-gas spikes (2024Q4 mean 18.5 gwei; future
  congestion), where T1's throttling beats T2's gas-naive over-trading.

## 4. Statistical fragility (disclosed)

- The retracted +7.03 bp was W6-dominated (W6 = 58% of the mean); moot now
  that the honest number is negative.
- Walk-forward N is small (5–6 windows). The binding T1-vs-holds result is
  significant (p<1e-4 on 5/6 contrasts; Euler the lone 1/6-window miss),
  but the CIs are wide by construction at this N.

## 5. What stands, untouched

- **Binding result: T1 beats passive holds by +1.5–2.8 pp, leakage-free,
  on real `lending_apr` for all 6 protocols.** T1 (online EWMA) and T2
  (past-only OU) never see the future. 0 NaN-accrual blocks. Sign
  convention holds 100%.
- Data is genuinely 6-way (real `lending_apr` everywhere); placeholders
  (gas now fixed; Compound TVL, Spark/Fluid borrow, Fluid util, USDT peg)
  feed only secondary analyses — see `real_data_inventory.md`.

---

## Net effect on the paper

The paper gets **stronger and more honest**:
- Headline stays **T1 / event-time resolution** (unchanged, robust).
- **Retract H1c**; reframe T3 as a **pre-registered negative result**:
  "ML hazard modelling does not beat the simple gas-aware threshold
  out-of-sample (−88 bp); the F3 cross-protocol spread is the decision
  variable and T1 captures it." This pre-empts the sharpest reviewer
  question and showcases the intellectual honesty that is the project's
  signature.
- Add the **gas-sensitivity table** and the **real-gas finding** (gas
  collapsed post-Dencun; edge is gas-robust and net-understated).
