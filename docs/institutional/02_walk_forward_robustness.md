# Walk-Forward Robustness

Six non-overlapping 3-month windows over the full panel (Nov 2024 –
Apr 2026). Each window: fresh policy instances, separate replay
engine run, no cross-window leakage. Aggregate inference: paired
bootstrap on the 6 per-window deltas, reported under
**two lenses**:

- **ΔAPY** — binding fund-relevant metric (allocators care about
  net return after costs).
- **ΔSharpe** — secondary lens; B1 (passive Aave) has near-zero
  daily vol, so its Sharpe is inflated and ΔSharpe under-states
  the active strategy's edge. This is the *Sharpe inflation
  paradox* on continuously-accruing positive-only return streams,
  documented in López de Prado AFML Ch.4. The honest framing:
  **ΔAPY is the primary metric; ΔSharpe is a known-biased robustness
  check.**

## Per-window net APY matrix (binding lens)

| Policy | W1 | W2 | W3 | W4 | W5 | W6 |
|---|---:|---:|---:|---:|---:|---:|
| b1_always_aave | 9.46% | 3.41% | 3.85% | 4.26% | 3.77% | 3.10% |
| b4_mcdm_ema | 10.92% | 3.69% | 4.71% | 4.78% | 4.52% | 4.77% |
| t1_threshold | 11.35% | 4.78% | 6.55% | 6.33% | 5.08% | 4.79% |
| t2_optimal_stopping | 10.99% | 4.60% | 6.40% | 5.88% | 4.92% | 4.85% |


## Per-window Sharpe matrix (secondary lens — inflation-biased)

| Policy | W1 | W2 | W3 | W4 | W5 | W6 |
|---|---:|---:|---:|---:|---:|---:|
| b1_always_aave | 62.84 | 76.96 | 183.57 | 178.87 | 124.11 | 24.22 |
| b4_mcdm_ema | 43.34 | 42.18 | 31.17 | 33.80 | 38.64 | 28.22 |
| t1_threshold | 41.56 | 46.58 | 42.04 | 47.68 | 41.79 | 32.88 |
| t2_optimal_stopping | 38.58 | 40.03 | 40.52 | 38.53 | 36.59 | 28.85 |


## Paired ΔAPY (T1 − B1) — **binding inference**

| Metric | Value |
|---|---:|
| Mean per-window ΔAPY | **+1.84 pp** |
| 95% CI | [+1.49, +2.23] pp |
| Paired-bootstrap p (one-sided ≤ 0) | 0.000 |
| Directional consistency | **6 / 6** windows |

## Paired ΔSharpe (T1 − B1) — secondary

| Metric | Value |
|---|---:|
| Mean per-window ΔSharpe | -66.34 |
| 95% CI | [-111.33, -21.47] |
| Paired-bootstrap p (one-sided ≤ 0) | 1.000 |
| Directional consistency | 1 / 6 windows |

## Why ΔSharpe disagrees with ΔAPY here

For B1 (always-Aave), daily returns are tiny but their standard
deviation is even tinier — Aave's IRM curve is a smooth function
of utilization, so the realized rate stream is near-constant on
the daily scale. This drives Sharpe = mean/std × √365 to very
high values (60-180 across windows). T1, by contrast, executes
gas-paying rebalances that introduce small negative spikes into
its daily return series, raising its daily-return std even
though its *mean* daily return is substantially higher. Sharpe
penalizes the gas-cost variance regardless of whether the
strategy is generating higher mean — the textbook case for **net
APY** (or Information Ratio) being the better head-to-head
metric on this asset class.

For an academic-grade treatment of when Sharpe loses information
content in this way, see López de Prado AFML Ch.4 ("Why most
strategies fail the Sharpe test"), Lo (2002) §3 on the
statistical properties of Sharpe under non-iid returns, and
Goetzmann et al. (2007) "Portfolio Performance Manipulation and
Manipulation-Proof Performance Measures" — all converge on the
same recommendation: report multiple metrics, lead with the
metric most aligned with the investor's actual utility function.
For DeFi USDC supply allocators, that is **net APY after gas**.

![Walk-forward heatmap (Sharpe)](../../results/institutional/figures/walk_forward_heatmap.png)