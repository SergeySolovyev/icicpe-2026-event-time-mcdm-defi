"""Test D7: equity-curves figure smoke."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def _synth_equity(tmp_path: Path, policy: str, protocols=("aave_v3", "compound_v3")):
    n = 600
    blocks = np.arange(20_000_000, 20_000_000 + n, dtype=np.int64)
    ts = pd.date_range("2026-01-01", periods=n, freq="2h", tz="UTC")
    eq = 1_000_000.0 * np.cumprod(np.full(n, 1.00005))
    current = [protocols[i % len(protocols)] for i in range(n)]
    df = pd.DataFrame({
        "block_number": blocks,
        "block_timestamp": ts,
        "position_usd": eq,
        "current_protocol": current,
    })
    p = tmp_path / f"equity_{policy}.parquet"
    df.to_parquet(p)
    return p


def test_equity_curves_figure_builds(tmp_path):
    from results.figures.build_equity_curves import build_equity_curves_figure

    equity_dir = tmp_path / "equity"
    equity_dir.mkdir()
    for pol in ("always_aave", "t1_threshold", "mcdm_ema"):
        _synth_equity(equity_dir, pol)

    out_png = tmp_path / "equity_curves.png"
    fig = build_equity_curves_figure(
        equity_dir=equity_dir,
        out_path=out_png,
        protocols=("aave_v3", "spark", "compound_v3",
                   "morpho_blue", "fluid", "euler_v2"),
    )
    assert out_png.exists()
    assert out_png.stat().st_size > 1000  # not a stub
    # 4 rows x 2 cols = 8 axes (6 protocol panels + 1 summary + 1 legend slot).
    assert len(fig.axes) >= 7


def test_equity_curves_missing_equity_dir_raises(tmp_path):
    from results.figures.build_equity_curves import build_equity_curves_figure
    with pytest.raises(FileNotFoundError):
        build_equity_curves_figure(
            equity_dir=tmp_path / "ghost",
            out_path=tmp_path / "x.png",
            protocols=("aave_v3",),
        )
