"""Four figure builders for the Institutional Dossier."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def fig_institutional_summary(metrics_df: pd.DataFrame, equity_dir,
                              out_path) -> None:
    """4-panel: equity curves, Sharpe vs Sortino, APY bars, MaxDD bars."""
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    # Panel A: equity curves
    ax = axes[0, 0]
    for policy in metrics_df["policy"]:
        p = Path(equity_dir) / f"equity_{policy}.parquet"
        if not p.exists():
            continue
        eq = pd.read_parquet(p)
        eq["block_timestamp"] = pd.to_datetime(eq["block_timestamp"], utc=True)
        ax.plot(eq["block_timestamp"],
                eq["position_usd"] / eq["position_usd"].iloc[0],
                label=policy, linewidth=1)
    ax.set_title("Cumulative equity (normalized)")
    ax.legend(fontsize=7, loc="best")
    ax.grid(alpha=0.3)
    # Panel B: Sharpe vs Sortino
    ax = axes[0, 1]
    x = range(len(metrics_df))
    finite_sortino = metrics_df["sortino"].replace([float("inf"), float("-inf")], 0)
    ax.bar([i - 0.2 for i in x], metrics_df["sharpe"], width=0.4, label="Sharpe")
    ax.bar([i + 0.2 for i in x], finite_sortino, width=0.4, label="Sortino")
    ax.set_xticks(list(x))
    ax.set_xticklabels(metrics_df["policy"], rotation=45, ha="right", fontsize=7)
    ax.set_title("Sharpe vs Sortino")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    # Panel C: APY
    ax = axes[1, 0]
    ax.bar(x, metrics_df["net_apy_pct"], color="steelblue")
    ax.set_xticks(list(x))
    ax.set_xticklabels(metrics_df["policy"], rotation=45, ha="right", fontsize=7)
    ax.set_title("Net APY (%)")
    ax.grid(alpha=0.3)
    # Panel D: MaxDD
    ax = axes[1, 1]
    ax.bar(x, metrics_df["max_drawdown_pct"], color="firebrick")
    ax.set_xticks(list(x))
    ax.set_xticklabels(metrics_df["policy"], rotation=45, ha="right", fontsize=7)
    ax.set_title("Max Drawdown (%)")
    ax.grid(alpha=0.3)
    fig.suptitle("Institutional summary: 4-month test window", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_walk_forward_heatmap(walk_df: pd.DataFrame, out_path) -> None:
    """Per-policy x per-window Sharpe heatmap."""
    if walk_df.empty:
        # No data yet -- emit placeholder
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "Walk-forward results pending\n(see results/institutional/tables/walk_forward.csv)",
                ha="center", va="center")
        ax.set_axis_off()
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return
    pivot = walk_df.pivot_table(index="policy", columns="window_id",
                                values="sharpe", aggfunc="first")
    fig, ax = plt.subplots(figsize=(8, 4))
    im = ax.imshow(pivot.values, cmap="RdYlGn", aspect="auto")
    ax.set_xticks(range(pivot.shape[1]))
    ax.set_xticklabels(pivot.columns)
    ax.set_yticks(range(pivot.shape[0]))
    ax.set_yticklabels(pivot.index)
    ax.set_title("Walk-forward Sharpe: 6 non-overlapping 3-month windows")
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            v = pivot.iloc[i, j]
            ax.text(j, i, f"{v:.1f}" if pd.notna(v) else "—",
                    ha="center", va="center", fontsize=7)
    fig.colorbar(im, ax=ax, shrink=0.6)
    fig.tight_layout()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_capacity_curve(cap_df: pd.DataFrame, out_path) -> None:
    """APY vs position size, one curve per policy."""
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for policy in cap_df["policy"].unique():
        sub = cap_df[cap_df["policy"] == policy].sort_values("position_size_usd")
        ax.plot(sub["position_size_usd"], sub["net_apy_pct"],
                marker="o", label=policy)
    ax.set_xscale("log")
    ax.set_xlabel("Position size (USD, log scale)")
    ax.set_ylabel("Net APY (%) after slippage")
    ax.set_title("Capacity analysis: $100K → $50M")
    ax.grid(alpha=0.3, which="both")
    ax.legend(fontsize=8)
    fig.tight_layout()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_cost_waterfall(cost_df: pd.DataFrame, policy: str, out_path) -> None:
    """Gross APY -> slippage -> MEV(worst) -> net APY waterfall, 1 policy."""
    sub = cost_df[cost_df["policy"] == policy].copy()
    if sub.empty:
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.text(0.5, 0.5, f"No cost data for policy {policy}",
                ha="center", va="center")
        ax.set_axis_off()
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return
    # Take $1M position row + worst MEV scenario
    sub_1m = sub[sub["position_size_usd"] == 1e6]
    if sub_1m.empty:
        sub_1m = sub
    row = sub_1m.sort_values("mev_bp", ascending=False).iloc[0]
    gross = row.get("raw_apy_pct", row["net_apy_pct"])
    after_slip = row["net_apy_pct"]
    after_mev = row["net_apy_post_mev_pct"]
    fig, ax = plt.subplots(figsize=(7, 4))
    labels = ["Gross", "-Slippage", "-MEV (worst)", "Net"]
    vals = [gross, after_slip, after_mev, after_mev]
    colors = ["steelblue", "orange", "firebrick", "green"]
    ax.bar(labels, vals, color=colors)
    ax.set_ylabel("APY (%)")
    ax.set_title(f"Cost waterfall ({policy}, $1M, worst-case MEV)")
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
