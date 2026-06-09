# Capacity reconciliation — net-of-cost edge at institutional size

**Date:** 2026-06-09. Closes audit finding #6 (the two capacity CSVs
disagree by sign). Establishes the honest net-of-cost commercial number on
the **real-gas + fToken** panel and identifies the true binding constraint.

## The contradiction the audit found

| model | file | T1 net @ $5M | implied story |
|---|---|---|---|
| per-rebalance round-trip | `capacity_curve.csv` | **−12.2 %** | "edge destroyed at size" |
| continuous yield-impact | `capacity_curve_6way.csv` | **+7.16 %** | "edge survives to $50M" |

Both were also stale (raw APY 4.60 % and 7.43 % — neither the current
real-gas 5.37 % test-window nor the 8.63 % walk-forward), and they disagree
by **10× on rebalance count** (38 vs 383) — they are two different runs on
two different panels.

## Which model is physically correct: the continuous one

Cross-protocol USDC rebalancing is **aToken/cToken mint and burn at par** —
there is **no DEX swap**, so there is **no AMM round-trip "slippage" toll.**
The real cost of moving size into a lending pool is that your own deposit
lowers the marginal supply rate you (and everyone) earn — a **continuous**
rate depression paid every block you hold, not a per-transaction fee.

`scripts/dossier/capacity.py` models the cost as
`slip_bp × 2 × n_rebalances / years` — it multiplies a *rate* (bp of APR)
by a *transaction count*, i.e. it applies an AMM per-swap toll to a mint/burn
that has none. That is a category error, and it is the entire source of the
−12 %. **`capacity_curve.csv` is superseded** (a deprecation note is added to
`scripts/dossier/capacity.py`); the continuous model
(`scripts/capacity_sweep_6way.py`, Krause-2005 yield-impact) is correct for
lending.

## Honest number, recomputed on the real-gas panel

`python scripts/capacity_sweep_6way.py` on the current panel (walk-forward
raw T1 APY 8.63 %, 1{,}735 rebalances over 18 months):

| size | T1 net APY | yield-impact | passive Aave | **net edge** |
|---|---|---|---|---|
| $1M  | 8.57 % |   6 bp | 4.64 % | **+3.93 pp** |
| $5M  | 8.36 % |  27 bp | 4.64 % | **+3.72 pp** |
| $25M | 7.86 % |  77 bp | 4.63 % | +3.23 pp |
| $50M | 7.60 % | 103 bp | 4.62 % | +2.98 pp |

Under the correct model the edge **compresses gracefully but stays strongly
positive** — the −12 % collapse was a modeling artifact.

## The real binding constraint: thin-venue TVL (not slippage)

The smooth linear model still **understates** the ceiling, because the
edge-carrying venues are tiny. Mean panel TVL:

| venue | TVL | ~time-share |
|---|---|---|
| Aave V3 | $3,357M | 5–8 % |
| Compound V3 | $473M | 4–10 % |
| Fluid | $231M | 1–6 % |
| Morpho Blue | $60M | 11–25 % |
| **Spark** | **$29M** | **~29 %** |
| **Euler V2** | **$16M** | **~49 %** |

The strategy earns most of its edge in **Euler ($16M) and Spark ($29M)**,
which together carry ~78 % of held time. A prudent deposit cannot exceed
~10–25 % of a pool's TVL without cratering the rate it is chasing (and a
$25M deposit into a $16M pool is simply infeasible). The linear term
`P/(TVL+P)` saturates and so **hides** this — its smooth "77 bp @ $25M" is
not reachable in Euler.

**Honest capacity ladder:**
- **$1–5M — full edge (+3.7–3.9 pp), all six venues usable.** This is the
  realistic initial institutional ICP.
- **~$5–10M — thin venues (Euler, Spark) begin to saturate;** the effective
  edge starts compressing faster than the smooth curve shows.
- **$25M+ — the thin edge-carrying venues cannot absorb the position;** the
  strategy is effectively deep-venue-only (Aave/Compound/Fluid/Morpho), and
  the realistic edge is smaller than the smooth model's +3 pp (still
  positive, but read the smooth $25–50M points as an upper bound).

## MEV

For pure USDC mint/burn there is **no sandwichable swap**, so MEV is
near-zero under **private-mempool (Flashbots) execution** — the production
design. The project's 5–30 bp MEV band (`scripts/dossier/mev.py`) applies
only to (a) public-mempool execution or (b) any rebalance leg that routes
through a DEX (e.g. an exotic wrapped-token conversion). Disclose that
exception; do not apply the band to the base lending path.

## Commercial bottom line

- The net-of-cost edge is **real at the $1–5M wedge (+3.7–3.9 pp)** — the
  honest number to sell, on the correct cost model.
- The binding constraint is **venue depth, not per-trade slippage**; quote a
  **~$5–10M full-strategy capacity ceiling** openly, with deep-venue-only
  economics above it. This is more credible to a quant DD team than either
  the −12 % artifact or an unqualified +3 pp-to-$50M claim.
- MEV is a managed, near-zero cost under private execution, with the DEX-leg
  exception disclosed.
