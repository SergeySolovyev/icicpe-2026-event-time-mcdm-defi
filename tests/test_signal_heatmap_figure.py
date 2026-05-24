"""Test D8: signal-heatmap figure smoke."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def _synth_coefs(path: Path):
    rows = []
    families = [("f1", ["f1_dsr_apr", "f1_dsr_lag_3600", "f1_curve_3pool_apr"]),
                ("f3", ["f3_spread_aave_vs_compound",
                        "f3_spread_max_minus_min", "f3_dispersion_std"]),
                ("f4", ["f4_gas_log10", "f4_eth_usd",
                        "f4_usdc_peg_dev_bps"])]
    for fam, feats in families:
        for f in feats:
            rows.append({
                "feature": f,
                "family": fam,
                "beta": np.random.normal(),
                "se": 0.1,
            })
    df = pd.DataFrame(rows)
    df["z"] = df["beta"] / df["se"]
    df.to_csv(path, index=False)


def test_signal_heatmap_builds(tmp_path):
    from results.figures.build_signal_heatmap import build_signal_heatmap_figure

    coefs_path = tmp_path / "t3_hazard_coefs.csv"
    _synth_coefs(coefs_path)
    out_png = tmp_path / "signal_heatmap.png"
    fig = build_signal_heatmap_figure(coefs_path=coefs_path, out_path=out_png)
    assert out_png.exists()
    assert out_png.stat().st_size > 1000
    # The figure has at least one axes (the heatmap).
    assert len(fig.axes) >= 1


def test_signal_heatmap_synthetic_fallback(tmp_path):
    from results.figures.build_signal_heatmap import build_signal_heatmap_figure
    out_png = tmp_path / "signal_heatmap.png"
    # Missing coefs file -> synthetic fallback (for CI before Plan C lands).
    fig = build_signal_heatmap_figure(
        coefs_path=tmp_path / "ghost.csv",
        out_path=out_png,
        allow_synthetic=True,
    )
    assert out_png.exists()


def test_signal_heatmap_missing_coefs_raises_when_not_synth(tmp_path):
    from results.figures.build_signal_heatmap import build_signal_heatmap_figure
    with pytest.raises(FileNotFoundError):
        build_signal_heatmap_figure(
            coefs_path=tmp_path / "ghost.csv",
            out_path=tmp_path / "x.png",
            allow_synthetic=False,
        )
