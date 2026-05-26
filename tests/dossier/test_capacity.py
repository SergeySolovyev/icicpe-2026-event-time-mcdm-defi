"""Capacity sweep + IRM slippage tests."""
from __future__ import annotations

import pandas as pd


def test_irm_params_present_for_all_panel_protocols():
    from scripts.dossier.irm_curves import IRM_PARAMS
    for p in ("aave_v3", "morpho_blue", "euler_v2"):
        assert p in IRM_PARAMS
        assert "slope1" in IRM_PARAMS[p]
        assert "kink" in IRM_PARAMS[p]


def test_slippage_monotone_in_position_size():
    from scripts.dossier.irm_curves import slippage_bp
    panel_row = {"aave_v3_utilization": 0.8, "aave_v3_tvl_usd": 1e10}
    s_small = slippage_bp("aave_v3", position_usd=1e5, panel_row=panel_row)
    s_large = slippage_bp("aave_v3", position_usd=1e7, panel_row=panel_row)
    assert s_large > s_small
    assert s_small > 0


def test_slippage_zero_when_unknown_protocol():
    from scripts.dossier.irm_curves import slippage_bp
    assert slippage_bp("nonexistent_proto", 1e6, {}) == 0.0


def test_capacity_sweep_returns_one_row_per_size_per_policy(tmp_path):
    from scripts.dossier.capacity import capacity_sweep
    import numpy as np
    # Build a tiny synthetic panel + matching equity parquet
    n = 1000
    ts = pd.date_range("2026-01-01", periods=n, freq="12s", tz="UTC")
    panel = pd.DataFrame({
        "block_number": range(1000),
        "block_timestamp": ts,
        "aave_v3_lending_apr": [0.04] * n,
        "aave_v3_utilization": [0.8] * n,
        "aave_v3_tvl_usd": [1e10] * n,
        "morpho_blue_lending_apr": [0.05] * n,
        "morpho_blue_utilization": [0.7] * n,
        "morpho_blue_tvl_usd": [5e9] * n,
        "euler_v2_lending_apr": [0.06] * n,
        "euler_v2_utilization": [0.6] * n,
        "euler_v2_tvl_usd": [1e9] * n,
    })
    # Seed a matching equity parquet for one policy
    eq_dir = tmp_path / "equity"
    eq_dir.mkdir()
    eq = pd.DataFrame({
        "block_number": range(1000),
        "block_timestamp": ts,
        "position_usd": np.linspace(1_000_000, 1_010_000, n),
        "current_protocol": ["aave_v3"] * n,
    })
    eq.to_parquet(eq_dir / "equity_b1_always_aave.parquet")
    df = capacity_sweep(
        panel=panel,
        position_sizes_usd=[1e5, 1e6, 1e7],
        policies=("b1_always_aave",),
        equity_dir=eq_dir,
    )
    assert len(df) == 3  # 3 sizes x 1 policy
    assert {"position_size_usd", "policy", "net_apy_pct",
            "slippage_bp_avg"}.issubset(df.columns)


def test_krause_ceiling_decreases_at_high_utilization():
    """Higher u -> lower depth (Krause 2005)."""
    from scripts.dossier.irm_curves import krause_market_depth
    d_low_u = krause_market_depth(protocol="aave_v3", utilization=0.5, tvl_usd=1e10)
    d_high_u = krause_market_depth(protocol="aave_v3", utilization=0.85, tvl_usd=1e10)
    assert d_low_u > d_high_u
