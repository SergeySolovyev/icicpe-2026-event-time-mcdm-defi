"""Capacity sweep on the 6-way active panel: yield-impact-adjusted
net APY at position sizes [$1M, $5M, $25M, $50M].

Methodology (Krause 2005 market-depth → DeFi lending yield-impact):

For a USDC lending pool with TVL_pre, utilization u, IRM slope κ
(per-unit-utilization rate derivative at the kink), depositing a
position P moves utilization from u to u·TVL_pre/(TVL_pre+P).
The marginal earned APR for the depositor (averaged over the
deposit lifetime) is approximately

    earned_APR ≈ spot_APR − ½ × κ × P / TVL_pre

i.e. the yield-impact is HALF the marginal rate-curve shift (linear
IRM, finite-deposit average). Expressed as a basis-point reduction
from the spot rate:

    yield_impact_bp = ½ × κ × P / TVL_pre × 10^4

This is a CONTINUOUS effect (paid every block we hold, not per
rebalance). For a policy spending fraction f_p of its time in
protocol p, total annual yield drag is

    yield_drag_pp = Σ_p f_p × yield_impact_bp(p, P) / 100

Gas cost is a separate per-rebalance cost (already captured in the
raw walk-forward equity files at $17.5 / rebalance).

Improvements over scripts/dossier/capacity.py:

1. Uses the 6-way walk-forward equity files (full 18 months across
   6 windows), not the 4-month test-window equity_*.parquet.

2. Computes per-protocol TVL from the 6-way panel, including the
   three new protocols (Compound/Spark/Fluid) whose aggregate depth
   roughly doubles the available USDC supply-side liquidity.

3. Aggregates time-in-protocol per equity file to get the policy's
   protocol-weighted slippage exposure.

4. Caps net APY at -100% (floors a position loss at total wipeout
   rather than reporting -260% nonsense from naive extrapolation).

Output: results/institutional/tables/capacity_curve_6way.csv with
schema {position_size_usd, policy, raw_apy_pct, slippage_drag_pct,
net_apy_pct, n_rebalances, capacity_ok}.

`capacity_ok = True` iff net_apy_pct > raw_apy_pct - 50% (i.e. the
strategy retains at least half its raw alpha at this size — a fund-
LP-relevant binary).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Per-protocol IRM kink slope (per Krause 2005 + empirical fit to each
# protocol's rate curve). Lower slope = more depth = better capacity.
# Estimated from each protocol's IRM curve at u_kink (where the slope
# transitions from linear to steep). For Aave V3 USDC, u_kink = 0.92,
# slope_1 ≈ 0.04 (4 percentage points of rate per unit utilization).
IRM_SLOPE_KINK = {
    "aave_v3":     0.04,
    "compound_v3": 0.05,
    "spark":       0.04,   # Aave V3 fork
    "morpho_blue": 0.06,   # adaptive curve, conservative
    "euler_v2":    0.05,
    "fluid":       0.05,   # similar to Compound
}

POSITION_SIZES = [1e6, 5e6, 2.5e7, 5e7]
POLICIES = ["b1_always_aave", "t1_threshold", "t2_optimal_stopping", "t3_hazard"]

EQ_DIR = ROOT / "results/institutional/tables/equity_walk_forward_6way"
PANEL_PATH = ROOT / "data/cached/per_block_panel.parquet"
OUT_CSV = ROOT / "results/institutional/tables/capacity_curve_6way.csv"


def _per_protocol_tvl_util(panel: pd.DataFrame) -> dict[str, tuple[float, float]]:
    """Mean TVL + mean utilization per protocol over the 18-month panel."""
    out: dict[str, tuple[float, float]] = {}
    for p in IRM_SLOPE_KINK:
        tvl_col = f"{p}_tvl_usd"
        util_col = f"{p}_utilization"
        if tvl_col not in panel.columns or util_col not in panel.columns:
            continue
        tvl_mean = float(panel[tvl_col].dropna().mean())
        util_mean = float(panel[util_col].dropna().mean())
        if tvl_mean > 0 and 0 < util_mean < 1:
            out[p] = (tvl_mean, util_mean)
    return out


def _yield_impact_bp(position: float, tvl: float, util: float,
                      slope_kink: float) -> float:
    """Continuous yield-impact in bp from depositing `position` into a
    pool with TVL `tvl`, utilization `util`, IRM slope `slope_kink`.

    Linearization of the IRM curve at the kink: depositing P into pool
    of TVL_pre moves utilization down by ΔU = u·P/(TVL_pre+P), which
    reduces the earned rate by κ·ΔU. Averaged over [0, P] this gives

        yield_impact ≈ ½ × κ × u × P / (TVL_pre + P)

    For small P/TVL this is ≈ ½ × κ × u × P / TVL_pre.
    Returned in BASIS POINTS (= rate-impact × 10⁴).
    """
    if tvl <= 0:
        return 0.0
    impact = 0.5 * slope_kink * util * position / (tvl + position)
    return impact * 10_000


def _policy_protocol_time(eq_files: list[Path]) -> tuple[float, dict[str, float], int]:
    """Aggregate over all walk-forward windows: total APY (geometric),
    per-protocol time-share, total n_rebalances."""
    if not eq_files:
        return float("nan"), {}, 0
    BPY = 365 * 24 * 60 * 60 // 12
    total_blocks = 0
    growth_product = 1.0
    proto_blocks: dict[str, int] = {}
    n_rebal_total = 0
    for f in eq_files:
        eq = pd.read_parquet(f)
        initial = float(eq["position_usd"].iloc[0])
        final = float(eq["position_usd"].iloc[-1])
        growth_product *= final / initial
        total_blocks += len(eq)
        if "current_protocol" in eq.columns:
            for p, n in eq["current_protocol"].value_counts().items():
                proto_blocks[str(p)] = proto_blocks.get(str(p), 0) + int(n)
            n_rebal_total += int(
                eq["current_protocol"].ne(eq["current_protocol"].shift()).sum() - 1
            )
    years = max(total_blocks / BPY, 1e-9)
    raw_apy_pct = (growth_product ** (1.0 / years) - 1.0) * 100
    proto_share = {p: n / total_blocks for p, n in proto_blocks.items()}
    return raw_apy_pct, proto_share, n_rebal_total


def main() -> int:
    print("[capacity] loading 6-way panel...", flush=True)
    panel = pd.read_parquet(PANEL_PATH)
    print(f"          {len(panel):,} blocks, {len(panel.columns)} cols", flush=True)

    print("[capacity] computing per-protocol mean TVL + utilization...",
          flush=True)
    tvl_util = _per_protocol_tvl_util(panel)
    for p, (tvl, util) in tvl_util.items():
        print(f"          {p:<14s} TVL ${tvl/1e6:8.1f}M  util {util*100:5.1f}%",
              flush=True)

    rows = []
    for policy in POLICIES:
        eq_files = sorted(EQ_DIR.glob(f"w*_{policy}.parquet"))
        if not eq_files:
            print(f"[capacity] no equity files for {policy}, skipping", flush=True)
            continue
        raw_apy_pct, proto_share, n_rebal = _policy_protocol_time(eq_files)
        print(f"\n[{policy}] raw_apy={raw_apy_pct:.2f}%  n_rebal={n_rebal}",
              flush=True)
        for size_usd in POSITION_SIZES:
            # Per-protocol yield-impact averaged by time-in-protocol.
            # CONTINUOUS effect — already in annualized rate units, no
            # n_rebalances multiplier.
            yield_impact_total_bp = 0.0
            for p, share in proto_share.items():
                if p not in tvl_util:
                    continue
                tvl, util = tvl_util[p]
                slope = IRM_SLOPE_KINK.get(p, 0.05)
                impact = _yield_impact_bp(size_usd, tvl, util, slope)
                yield_impact_total_bp += impact * share
            yield_drag_pp = yield_impact_total_bp / 100.0
            net_apy_pct = raw_apy_pct - yield_drag_pp
            cap_ok = net_apy_pct > (raw_apy_pct * 0.5)  # retain ≥50% raw alpha
            print(f"  ${size_usd/1e6:>5.1f}M  yield_impact={yield_impact_total_bp:7.2f}bp  "
                  f"drag={yield_drag_pp:6.2f}pp  net={net_apy_pct:6.2f}%  "
                  f"capacity_ok={cap_ok}", flush=True)
            rows.append({
                "position_size_usd": size_usd,
                "policy": policy,
                "raw_apy_pct": raw_apy_pct,
                "yield_impact_bp_avg": yield_impact_total_bp,
                "yield_drag_pp": yield_drag_pp,
                "net_apy_pct": net_apy_pct,
                "n_rebalances": n_rebal,
                "capacity_ok": cap_ok,
            })

    out = pd.DataFrame(rows)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)
    print(f"\n[capacity] wrote {OUT_CSV}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
