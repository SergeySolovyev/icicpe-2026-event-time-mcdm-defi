"""Walk-forward N×M visualization: per-window APY for each policy +
each protocol-hold, side by side. Plus the Sharpe heatmap for the
robustness check.

Output: walk_forward_nxm.png — replaces stale walk_forward_heatmap.png
with a richer fund-relevant visualization.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    pp_apy = pd.read_csv(ROOT / "results/institutional/tables/walk_forward_vs_all_holds.csv")
    nxm = pd.read_csv(ROOT / "results/institutional/tables/walk_forward_NxM_contrasts.csv")

    # 2-panel layout: per-window APY bars (top), N×M bootstrap deltas with CI bars (bottom)
    fig, axes = plt.subplots(2, 1, figsize=(11, 8.5))

    # Top panel: per-window APY (T1 + each protocol-hold side by side)
    ax = axes[0]
    width = 0.18
    x = np.arange(len(pp_apy))
    bars_def = [
        ("T1 threshold", "t1_apy_pct", "#1f77b4", -1.5),
        ("T2 OU stopping", None, "#ff7f0e", -0.5),  # filled from walk_forward.csv
        ("Aave V3 hold", "aave_apy_pct", "#2ca02c", 0.5),
        ("Morpho Blue hold", "morpho_apy_pct", "#d62728", 1.5),
        ("Euler V2 hold", "euler_apy_pct", "#9467bd", 2.5),
    ]
    wf = pd.read_csv(ROOT / "results/institutional/tables/walk_forward.csv")
    t2_apy = wf[wf.policy == "t2_optimal_stopping"].set_index("window_id")["net_apy_pct"].to_dict()
    for label, col, color, off in bars_def:
        if col is None:
            vals = [t2_apy.get(w, 0.0) for w in pp_apy.window_id]
        else:
            vals = pp_apy[col].values
        ax.bar(x + off * width, vals, width, label=label, color=color, alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels(pp_apy.window_id)
    ax.set_ylabel("Net APY (%)")
    ax.set_title("Per-window net APY: T1 + T2 + 3 protocol buy-and-holds")
    ax.grid(axis="y", alpha=0.3)
    ax.legend(fontsize=8, ncol=5, loc="upper left", bbox_to_anchor=(0, 1.15))

    # Bottom panel: N×M bootstrap deltas with 95% CI bars
    ax = axes[1]
    nxm_clean = nxm.copy()
    # Build a label combining policy + protocol
    nxm_clean["label"] = (
        nxm_clean["policy"].map({
            "t1_threshold": "T1",
            "t2_optimal_stopping": "T2",
            "t3_hazard": "T3",
            "b4_mcdm_ema": "B4",
        }) + " vs " + nxm_clean["protocol_hold"].map({
            "aave": "Aave",
            "morpho": "Morpho",
            "euler": "Euler",
        }) + " hold"
    )
    # Sort by policy then by protocol
    policy_order = {"T1": 0, "T2": 1, "T3": 2, "B4": 3}
    proto_order = {"Aave": 0, "Morpho": 1, "Euler": 2}
    nxm_clean["_p"] = nxm_clean["policy"].map({
        "t1_threshold": 0, "t2_optimal_stopping": 1,
        "t3_hazard": 2, "b4_mcdm_ema": 3,
    })
    nxm_clean["_h"] = nxm_clean["protocol_hold"].map({
        "aave": 0, "morpho": 1, "euler": 2,
    })
    nxm_clean = nxm_clean.sort_values(["_p", "_h"]).reset_index(drop=True)
    y = np.arange(len(nxm_clean))
    means = nxm_clean["mean_pp"].values
    lows = nxm_clean["ci_low_95"].values
    highs = nxm_clean["ci_high_95"].values
    err_lo = means - lows
    err_hi = highs - means
    sig = nxm_clean["p_one_sided_le0"].values < 0.05
    colors = ["#2ca02c" if s else "#999999" for s in sig]
    ax.barh(y, means, xerr=[err_lo, err_hi], color=colors, alpha=0.8,
            edgecolor="black", linewidth=0.5, capsize=4)
    ax.axvline(0, color="black", linewidth=1)
    ax.set_yticks(y)
    ax.set_yticklabels(nxm_clean["label"], fontsize=9)
    ax.set_xlabel("ΔAPY mean per-window (pp) with 95% paired-bootstrap CI")
    ax.set_title("N×M paired bootstrap: each policy vs each protocol-hold "
                 "(green = significant at p<0.05, grey = NS)")
    ax.grid(axis="x", alpha=0.3)
    ax.invert_yaxis()

    fig.tight_layout()
    out = ROOT / "results/institutional/figures/walk_forward_nxm.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
