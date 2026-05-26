"""Capacity sweep: for each position size, apply closed-form slippage
deduction to existing equity parquets and compute net APY.

Approximation: rather than re-running the full per-block replay engine
inside the slippage loop (expensive), apply slippage to each policy's
existing equity_*.parquet: net_apy_adjusted = net_apy - mean_slippage_bp
* 2 * n_rebalances / 10000 (factor 2 because each rebalance involves
a withdraw and a deposit, each with slippage)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from scripts.dossier.irm_curves import slippage_bp, IRM_PARAMS


def capacity_sweep(
    panel: pd.DataFrame,
    *,
    position_sizes_usd: list[float] = (1e5, 1e6, 5e6, 2.5e7, 5e7),
    policies: tuple[str, ...] = (
        "b1_always_aave", "b4_mcdm_ema", "t1_threshold", "t2_optimal_stopping",
    ),
    equity_dir: Path = Path("results/tables/equity"),
) -> pd.DataFrame:
    """For each (position_size, policy), compute slippage-adjusted net APY."""
    rows = []
    protocols = list(IRM_PARAMS.keys())
    panel_mean: dict[str, dict[str, float]] = {}
    for p in protocols:
        if f"{p}_utilization" in panel.columns and f"{p}_tvl_usd" in panel.columns:
            panel_mean[p] = {
                f"{p}_utilization": float(panel[f"{p}_utilization"].mean()),
                f"{p}_tvl_usd": float(panel[f"{p}_tvl_usd"].mean()),
            }
    for size in position_sizes_usd:
        for policy in policies:
            eq_path = Path(equity_dir) / f"equity_{policy}.parquet"
            if not eq_path.exists():
                continue
            eq_df = pd.read_parquet(eq_path)
            initial = float(eq_df["position_usd"].iloc[0])
            final = float(eq_df["position_usd"].iloc[-1])
            if "current_protocol" in eq_df.columns:
                n_rebalances = int(
                    eq_df["current_protocol"].ne(
                        eq_df["current_protocol"].shift()
                    ).sum() - 1
                )
                proto_counts = eq_df["current_protocol"].value_counts().to_dict()
            else:
                n_rebalances = 0
                proto_counts = {}
            slip_total_bp = 0.0
            for proto, count in proto_counts.items():
                if proto not in panel_mean:
                    continue
                slip_total_bp += (
                    slippage_bp(proto, size, panel_mean[proto])
                    * count / len(eq_df)
                )
            n_blocks = len(eq_df)
            blocks_per_year = 365 * 24 * 60 * 60 // 12
            years = max(n_blocks / blocks_per_year, 1e-9)
            raw_apy = (final / initial) ** (1.0 / years) - 1.0
            slippage_apy_drag = (slip_total_bp * 2 * n_rebalances / 1e4) / years
            net_apy = raw_apy - slippage_apy_drag
            rows.append({
                "position_size_usd": size,
                "policy": policy,
                "raw_apy_pct": raw_apy * 100,
                "slippage_bp_avg": slip_total_bp,
                "slippage_drag_pct": slippage_apy_drag * 100,
                "net_apy_pct": net_apy * 100,
                "n_rebalances": n_rebalances,
            })
    return pd.DataFrame(rows)
