"""Test D3: regime-conditional breakdown on synthetic equity curves."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def _equity_with_switches(tmp_path: Path, name: str, monthly_apr: float,
                          switch_block_offsets: list[int]) -> Path:
    """Synthetic equity: cumulative compounding with explicit
    current_protocol changes at given block offsets so n_rebalances
    is exercise-counted by the aggregator."""
    n = 4000
    blocks = np.arange(20_000_000, 20_000_000 + n, dtype=np.int64)
    ts = pd.date_range("2026-01-01", periods=n, freq="30min", tz="UTC")
    per_period = (1 + monthly_apr / 12.0) ** (1 / (n / 4))
    equity = 1_000_000.0 * np.cumprod(np.full(n, per_period, dtype=np.float64))

    protocols = ["aave_v3"] * n
    flip = "aave_v3"
    for off in switch_block_offsets:
        flip = "compound_v3" if flip == "aave_v3" else "aave_v3"
        for i in range(off, n):
            protocols[i] = flip

    df = pd.DataFrame({
        "block_number": blocks,
        "block_timestamp": ts,
        "position_usd": equity,
        "current_protocol": protocols,
    })
    p = tmp_path / f"equity_{name}.parquet"
    df.to_parquet(p)
    return p


def test_regime_breakdown_basic_shape(tmp_path):
    from backtest.run_regime_breakdown import (
        compute_regime_breakdown, TEST_QUARTERS_2026,
    )

    _equity_with_switches(tmp_path, "policy_x", 0.06, [1000, 2500])
    _equity_with_switches(tmp_path, "policy_y", 0.04, [])

    df = compute_regime_breakdown(
        equity_dir=tmp_path, quarters=TEST_QUARTERS_2026,
    )

    expected_cols = {
        "policy", "quarter", "n_blocks", "net_apy_pct",
        "sharpe_annual", "n_rebalances",
        "gas_spent_usd", "final_equity_usd",
    }
    assert expected_cols <= set(df.columns)
    # 2 policies x 2 quarters in TEST_QUARTERS_2026.
    assert len(df) == 4
    assert set(df["policy"]) == {"policy_x", "policy_y"}
    assert set(df["quarter"]) == {"2026-Q1", "2026-Q2"}


def test_regime_breakdown_counts_switches(tmp_path):
    from backtest.run_regime_breakdown import (
        compute_regime_breakdown, TEST_QUARTERS_2026,
    )
    _equity_with_switches(tmp_path, "policy_x", 0.06, [1000, 2500])

    df = compute_regime_breakdown(
        equity_dir=tmp_path, quarters=TEST_QUARTERS_2026,
    )
    # Both switches occur in the test window. They should be split
    # across the two quarter slices; total across both quarters = 2.
    total_switches = df[df["policy"] == "policy_x"]["n_rebalances"].sum()
    assert int(total_switches) == 2


def test_quarters_with_ordering(tmp_path):
    from backtest.run_regime_breakdown import (
        compute_regime_breakdown, quarters_with_ordering, TEST_QUARTERS_2026,
    )
    _equity_with_switches(tmp_path, "a", 0.10, [])
    _equity_with_switches(tmp_path, "b", 0.05, [])
    _equity_with_switches(tmp_path, "c", 0.02, [])
    df = compute_regime_breakdown(equity_dir=tmp_path, quarters=TEST_QUARTERS_2026)
    # a > b > c in every quarter.
    result = quarters_with_ordering(df, ordering=["a", "b", "c"])
    assert result["n_quarters_in_order"] == 2
    assert result["n_quarters_evaluated"] == 2
