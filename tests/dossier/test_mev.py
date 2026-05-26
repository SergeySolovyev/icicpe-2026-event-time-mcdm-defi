"""MEV deduction property tests."""
from __future__ import annotations

import pandas as pd


def test_mev_deduction_monotone_decreasing():
    from scripts.dossier.mev import deduct_mev
    base = pd.DataFrame({
        "policy": ["t1_threshold", "t1_threshold", "t1_threshold"],
        "position_size_usd": [1e6, 1e6, 1e6],
        "net_apy_pct": [4.60, 4.60, 4.60],
        "n_rebalances": [39, 39, 39],
    })
    df0 = deduct_mev(base, mev_bp=0.0)
    df5 = deduct_mev(base, mev_bp=5.0)
    df30 = deduct_mev(base, mev_bp=30.0)
    assert df30["net_apy_post_mev_pct"].iloc[0] < df5["net_apy_post_mev_pct"].iloc[0]
    assert df5["net_apy_post_mev_pct"].iloc[0] < df0["net_apy_post_mev_pct"].iloc[0]
    assert df0["net_apy_post_mev_pct"].iloc[0] == 4.60


def test_mev_sensitivity_table_has_all_scenarios():
    from scripts.dossier.mev import mev_sensitivity_table
    base = pd.DataFrame({
        "policy": ["t1_threshold"],
        "position_size_usd": [1e6],
        "net_apy_pct": [4.60],
        "n_rebalances": [39],
    })
    df = mev_sensitivity_table(base, mev_scenarios=[0.0, 5.0, 15.0, 30.0])
    assert len(df) == 4  # 1 row x 4 scenarios
    assert {"mev_bp", "net_apy_post_mev_pct"}.issubset(df.columns)


def test_mev_zero_rebalances_means_zero_drag():
    from scripts.dossier.mev import deduct_mev
    base = pd.DataFrame({
        "policy": ["b1_always_aave"],
        "position_size_usd": [1e6],
        "net_apy_pct": [3.23],
        "n_rebalances": [0],
    })
    df = deduct_mev(base, mev_bp=30.0)
    assert df["mev_drag_pct"].iloc[0] == 0.0
    assert df["net_apy_post_mev_pct"].iloc[0] == 3.23
