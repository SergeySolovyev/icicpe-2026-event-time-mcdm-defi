"""Plot capacity curve from capacity_curve_6way.csv.

Renders results/institutional/figures/capacity_curve_6way.png with:
- log x-axis: position size from $1M to $50M
- y-axis: net APY (%)
- one line per policy (B1, T1, T2, T3)
- dashed reference line at B1 baseline APY

This is the canonical fund-LP-facing capacity chart.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "results/institutional/tables/capacity_curve_6way.csv"
OUT_PNG = ROOT / "results/institutional/figures/capacity_curve_6way.png"


def main() -> int:
    df = pd.read_csv(CSV)
    fig, ax = plt.subplots(figsize=(8, 5))
    colors = {"b1_always_aave": "#888888", "t1_threshold": "#1f77b4",
              "t2_optimal_stopping": "#ff7f0e", "t3_hazard": "#2ca02c"}
    labels = {"b1_always_aave": "B1 Always-Aave (passive)",
              "t1_threshold": "T1 gas-aware threshold",
              "t2_optimal_stopping": "T2 OU optimal stopping",
              "t3_hazard": "T3 Cox F1+F3+F4 (canonical)"}
    for policy, grp in df.groupby("policy"):
        grp = grp.sort_values("position_size_usd")
        ax.plot(grp["position_size_usd"] / 1e6, grp["net_apy_pct"],
                marker="o", linewidth=2.0, color=colors.get(policy, "#000"),
                label=labels.get(policy, policy))
    ax.set_xscale("log")
    ax.set_xlabel("Position size (USD millions)")
    ax.set_ylabel("Net APY (%)")
    ax.set_title("Capacity curve: net APY vs position size (6-way active panel)\n"
                 "Krause-2005 yield-impact, Nov 2024–Apr 2026 walk-forward")
    ax.grid(alpha=0.3, which="both")
    ax.legend(loc="lower left", fontsize=9, frameon=False)
    ax.set_xticks([1, 5, 25, 50])
    ax.set_xticklabels(["$1M", "$5M", "$25M", "$50M"])
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
    print(f"wrote {OUT_PNG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
