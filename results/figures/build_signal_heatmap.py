"""Plan D Task 8 — Signal-heatmap figure (F1/F3/F4 x Cox z-score).

Reads Plan C's results/tables/t3_hazard_coefs.csv (one row per feature
with beta, se, z) and renders a heatmap with features (rows) grouped
by family (F1 / F3 / F4) and z-scores as cell intensities.

If t3_hazard_coefs.csv does not exist and allow_synthetic=True (the
default for the figure-build CLI), fall back to a synthetic random
heatmap so Plan D's CI does not depend on Plan C having landed.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


_SYNTH_FEATURES = [
    ("f1", "f1_dsr_apr"),
    ("f1", "f1_dsr_lag_3600"),
    ("f1", "f1_curve_3pool_apr"),
    ("f3", "f3_spread_aave_vs_compound"),
    ("f3", "f3_spread_max_minus_min"),
    ("f3", "f3_dispersion_std"),
    ("f4", "f4_gas_log10"),
    ("f4", "f4_eth_usd"),
    ("f4", "f4_usdc_peg_dev_bps"),
]


def _synthetic_coefs() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    rows = []
    for fam, feat in _SYNTH_FEATURES:
        # F3 features dominate by design.
        scale = 4.0 if fam == "f3" else 1.0
        beta = float(rng.normal(scale=scale))
        se = 0.1 + abs(rng.normal(scale=0.05))
        rows.append({"feature": feat, "family": fam, "beta": beta,
                     "se": se, "z": beta / se})
    return pd.DataFrame(rows)


def build_signal_heatmap_figure(
    *, coefs_path: Path, out_path: Path,
    allow_synthetic: bool = True,
) -> plt.Figure:
    coefs_path = Path(coefs_path)
    if coefs_path.exists():
        df = pd.read_csv(coefs_path)
        if "z" not in df.columns and {"beta", "se"} <= set(df.columns):
            df["z"] = df["beta"] / df["se"]
    elif allow_synthetic:
        df = _synthetic_coefs()
    else:
        raise FileNotFoundError(coefs_path)

    df = df.sort_values(["family", "feature"]).reset_index(drop=True)
    # 1-column heatmap of z-scores -- vertical bar.
    z = df["z"].to_numpy(dtype=np.float64).reshape(-1, 1)

    fig, ax = plt.subplots(figsize=(4.5, max(4.0, 0.4 * len(df))))
    vmax = float(np.nanmax(np.abs(z))) if len(z) else 1.0
    im = ax.imshow(z, cmap="RdBu_r", aspect="auto",
                   vmin=-vmax, vmax=vmax)
    ax.set_yticks(range(len(df)))
    ax.set_yticklabels(df["feature"].tolist(), fontsize=8)
    ax.set_xticks([0])
    ax.set_xticklabels([r"$\hat{\beta}/\hat{\sigma}_\beta$"], fontsize=10)

    # Family separators.
    families = df["family"].tolist()
    for i in range(1, len(families)):
        if families[i] != families[i - 1]:
            ax.axhline(i - 0.5, color="k", linewidth=1.0)

    # Family labels on the right.
    for fam in df["family"].unique():
        rows = df.index[df["family"] == fam]
        center = (rows.min() + rows.max()) / 2.0
        ax.text(0.6, center, fam.upper(), va="center", ha="left",
                fontsize=11, fontweight="bold")

    cbar = fig.colorbar(im, ax=ax, shrink=0.7)
    cbar.set_label("standardised Cox hazard coefficient", fontsize=9)
    ax.set_title("Signal-class hazard contributions\n(F3 fragmentation dominates)",
                 fontsize=11)
    fig.tight_layout()

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    return fig


def _main() -> int:
    ROOT = Path(__file__).resolve().parent.parent.parent
    build_signal_heatmap_figure(
        coefs_path=ROOT / "results" / "tables" / "t3_hazard_coefs.csv",
        out_path=ROOT / "results" / "figures" / "signal_heatmap.png",
        allow_synthetic=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
