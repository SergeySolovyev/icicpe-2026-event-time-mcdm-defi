"""MEV deduction sensitivity.

Worst-case MEV per rebalance under public mempool ranges 5-30bp
(Flashbots research; mev-explore.com 2024-2025 aggregated stats).
Flashbots private mempool reduces this to ~0 (asymmetric speed bump
preserves intent privacy until inclusion)."""
from __future__ import annotations

import pandas as pd


def deduct_mev(capacity_df: pd.DataFrame, mev_bp: float) -> pd.DataFrame:
    """Deduct mev_bp per rebalance from net_apy_pct.

    MEV cost per rebalance = position_size * mev_bp / 10000.
    Annualize the drag the same way as the rest of the costs."""
    out = capacity_df.copy()
    n_blocks = 7200 * 30 * 4  # 4-month test window approx
    blocks_per_year = 365 * 24 * 60 * 60 // 12
    years = n_blocks / blocks_per_year
    mev_dollar_per_rebalance = out["position_size_usd"] * mev_bp / 10_000
    mev_drag_pct = (
        mev_dollar_per_rebalance * out["n_rebalances"]
        / out["position_size_usd"] / years
    ) * 100
    out["mev_bp"] = mev_bp
    out["mev_drag_pct"] = mev_drag_pct
    out["net_apy_post_mev_pct"] = out["net_apy_pct"] - mev_drag_pct
    return out


def mev_sensitivity_table(
    capacity_df: pd.DataFrame,
    mev_scenarios: list[float] = (0.0, 5.0, 15.0, 30.0),
) -> pd.DataFrame:
    """Cross capacity_df x MEV scenarios."""
    parts = [deduct_mev(capacity_df, mev_bp=bp) for bp in mev_scenarios]
    return pd.concat(parts, ignore_index=True)
