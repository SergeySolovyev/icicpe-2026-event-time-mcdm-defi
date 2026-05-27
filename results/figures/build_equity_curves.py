"""Plan D Task 7 - Per-protocol equity-curves figure.

Reads the per-policy equity parquets written by D1
(results/tables/equity/equity_<policy>.parquet) and produces a 4x2
grid (6 protocol panels + 1 portfolio summary + 1 legend) saved to
results/figures/equity_curves.png at 300 dpi.

Each panel plots one line per policy; B1-B4 are dashed, T1-T3 are
solid; T3 is bolded if present. Per-protocol panels filter equity
samples by the policy's current_protocol at each block, so a panel
shows only blocks during which the relevant policy was holding the
panel's protocol.
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

import matplotlib
matplotlib.use("Agg")  # headless for CI
import matplotlib.pyplot as plt
import pandas as pd

BASELINE_NAMES = {"always_aave", "always_compound", "greedy_spot", "mcdm_ema"}
TREATMENT_NAMES = {"t1_threshold", "t2_optimal_stopping", "t3_hazard"}


def _style_for(policy_name: str) -> dict:
    if policy_name in BASELINE_NAMES:
        return {"linestyle": "--", "linewidth": 1.0, "alpha": 0.8}
    if policy_name == "t3_hazard":
        return {"linestyle": "-", "linewidth": 2.0}
    return {"linestyle": "-", "linewidth": 1.5}


def build_equity_curves_figure(
    *, equity_dir: Path, out_path: Path,
    protocols: Sequence[str],
    initial_position_usd: float = 1_000_000.0,
) -> plt.Figure:
    equity_dir = Path(equity_dir)
    if not equity_dir.exists():
        raise FileNotFoundError(equity_dir)
    files = sorted(equity_dir.glob("equity_*.parquet"))
    if not files:
        raise FileNotFoundError(f"no equity_*.parquet in {equity_dir}")

    # Pre-scan: which protocols actually have data on this equity set?
    # Drops empty panels (e.g. Compound/Spark/Fluid panels are empty when
    # the equity files come from a 3-protocol active panel run).
    protocols_with_data = []
    for proto in protocols[:6]:
        has_data = False
        for f in files:
            try:
                eq = pd.read_parquet(f, columns=["current_protocol"])
                if (eq["current_protocol"] == proto).any():
                    has_data = True
                    break
            except Exception:
                continue
        if has_data:
            protocols_with_data.append(proto)
    n_proto = len(protocols_with_data)

    # Grid: per-protocol panels + 1 portfolio summary + 1 legend.
    # Layout adapts: e.g. 3 protocols + summary + legend = 5 panels → 3×2,
    # 6 protocols + summary + legend = 8 panels → 4×2.
    n_panels = n_proto + 2  # +summary +legend
    n_cols = 2
    n_rows = (n_panels + n_cols - 1) // n_cols
    fig, axes = plt.subplots(n_rows, n_cols,
                             figsize=(12, max(4, 3 * n_rows)),
                             sharex=True)
    axes_flat = axes.flatten()
    protocol_axes = dict(zip(protocols_with_data, axes_flat[:n_proto]))
    summary_ax = axes_flat[n_proto]
    legend_ax = axes_flat[n_proto + 1]
    legend_ax.axis("off")
    # Hide any spare axes at the end (when n_panels is odd).
    for ax in axes_flat[n_proto + 2:]:
        ax.axis("off")

    line_handles, line_labels = [], []
    for f in files:
        policy = f.stem[len("equity_"):]
        eq = pd.read_parquet(f)
        if "block_timestamp" not in eq.columns:
            continue
        eq = eq.copy()
        eq["block_timestamp"] = pd.to_datetime(eq["block_timestamp"], utc=True)
        eq["norm_equity"] = eq["position_usd"] / initial_position_usd
        style = _style_for(policy)

        # Portfolio summary.
        line, = summary_ax.plot(
            eq["block_timestamp"], eq["norm_equity"], label=policy, **style,
        )
        line_handles.append(line)
        line_labels.append(policy)

        # Per-protocol panels: subset where current_protocol == panel.
        for proto, ax in protocol_axes.items():
            mask = eq["current_protocol"] == proto
            if mask.any():
                ax.plot(
                    eq.loc[mask, "block_timestamp"],
                    eq.loc[mask, "norm_equity"],
                    **style,
                )

    for proto, ax in protocol_axes.items():
        ax.set_title(proto)
        ax.grid(alpha=0.3)
        ax.set_ylabel("equity / initial")
    summary_ax.set_title("portfolio summary (all blocks)")
    summary_ax.grid(alpha=0.3)
    summary_ax.set_ylabel("equity / initial")

    legend_ax.legend(line_handles, line_labels, loc="center", fontsize=9,
                     frameon=False, title="policy")

    fig.suptitle("Per-protocol equity curves, Jan--Apr 2026 test window",
                 fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.97))

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    return fig


def _main() -> int:
    ROOT = Path(__file__).resolve().parent.parent.parent
    build_equity_curves_figure(
        equity_dir=ROOT / "results" / "tables" / "equity",
        out_path=ROOT / "results" / "figures" / "equity_curves.png",
        protocols=("aave_v3", "spark", "compound_v3",
                   "morpho_blue", "fluid", "euler_v2"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
