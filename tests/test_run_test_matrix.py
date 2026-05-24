"""Test Plan D Task D1: Full B1-B4 + T1-T3 matrix runner.

Synthetic 2-protocol 1000-block panel with a known crossover at block 500
so each policy can demonstrate switching behaviour. We assert the runner
produces a CSV with the expected row-set and column-set, plus one
equity-curve parquet per policy.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def _synthetic_panel(n_blocks: int = 1000, start: str = "2026-01-01") -> pd.DataFrame:
    """2-protocol synthetic panel with a known crossover at block 500."""
    blocks = np.arange(20_000_000, 20_000_000 + n_blocks, dtype=np.int64)
    ts = pd.date_range(start, periods=n_blocks, freq="12s", tz="UTC")
    aave = np.where(np.arange(n_blocks) < 500, 0.04, 0.06)
    comp = np.where(np.arange(n_blocks) < 500, 0.06, 0.04)
    return pd.DataFrame(
        {
            "block_number": blocks,
            "block_timestamp": ts,
            "aave_v3_lending_apr": aave.astype(np.float64),
            "compound_v3_lending_apr": comp.astype(np.float64),
            "aave_v3_utilization": np.full(n_blocks, 0.8, dtype=np.float64),
            "compound_v3_utilization": np.full(n_blocks, 0.7, dtype=np.float64),
            "aave_v3_tvl_usd": np.full(n_blocks, 1.2e9, dtype=np.float64),
            "compound_v3_tvl_usd": np.full(n_blocks, 6.0e8, dtype=np.float64),
            "gas_price_gwei": np.full(n_blocks, 25.0, dtype=np.float64),
            "eth_price_usd": np.full(n_blocks, 3500.0, dtype=np.float64),
        }
    )


def test_run_test_matrix_writes_csv_and_equity_parquets(tmp_path: Path) -> None:
    from backtest.run_test_matrix import run

    panel_path = tmp_path / "panel.parquet"
    out_csv = tmp_path / "test_matrix.csv"
    equity_dir = tmp_path / "equity"
    _synthetic_panel().to_parquet(panel_path)

    df = run(
        panel_path=panel_path,
        out_path=out_csv,
        equity_dir=equity_dir,
        start=pd.Timestamp("2026-01-01", tz="UTC"),
        end=pd.Timestamp("2026-02-01", tz="UTC"),
        include_t3=False,  # T3 needs a trained artifact; this smoke path skips it.
    )

    assert out_csv.exists()
    assert {
        "policy",
        "n_blocks",
        "n_rebalances",
        "net_apy_pct",
        "max_drawdown_pct",
        "gas_spent_usd",
        "final_equity_usd",
    } <= set(df.columns)

    # Six policies with include_t3=False: B1, B2, B3, B4, T1, T2.
    # The actual `.name` attributes are set by Plan B6's subagent
    # implementation in backtest/run_baselines_event_time.py -- they
    # carry the "b{n}_" prefix to match the matrix-row ordering in the
    # paper. Plan B's t1/t2 don't use a prefix since they're not in the
    # baseline numbering.
    expected = {
        "b1_always_aave",
        "b2_always_compound",
        "b3_greedy_spot",
        "b4_mcdm_ema",
        "t1_threshold",
        "t2_optimal_stopping",
    }
    assert set(df["policy"]) == expected

    # One equity parquet per policy (filename uses the same .name).
    for name in expected:
        assert (equity_dir / f"equity_{name}.parquet").exists(), name


def test_run_test_matrix_rejects_empty_window(tmp_path: Path) -> None:
    from backtest.run_test_matrix import run

    panel_path = tmp_path / "panel.parquet"
    _synthetic_panel().to_parquet(panel_path)

    with pytest.raises(ValueError, match="No blocks"):
        run(
            panel_path=panel_path,
            out_path=tmp_path / "x.csv",
            equity_dir=tmp_path / "eq",
            start=pd.Timestamp("2099-01-01", tz="UTC"),
            end=pd.Timestamp("2099-02-01", tz="UTC"),
            include_t3=False,
        )


def test_run_test_matrix_with_t3_artifact(tmp_path: Path) -> None:
    """When include_t3=True and the JSON artifact path exists, T3 is included.

    Adapts the plan's ONNX-path convention to JSON since our T3HazardPolicy
    consumes the T3TrainingArtifact JSON sidecar produced by `decision.t3_train`.
    """
    from backtest.run_test_matrix import run
    from decision.t3_train import T3TrainingArtifact

    panel_path = tmp_path / "panel.parquet"
    _synthetic_panel().to_parquet(panel_path)

    # Trivial T3 artifact (mimics the gas-aware fallback path; what
    # matters here is that the runner accepts it without crashing).
    art = T3TrainingArtifact(
        feature_names=["f3_spread_max_minus_min"],
        coefficients={"f3_spread_max_minus_min": -50.0},
        baseline_mean_hazard=0.01,
        c_index=0.62,
        n_train_rows=2000,
        horizon_blocks=500,
        penalizer=0.001,
    )
    t3_model = tmp_path / "t3.json"
    art.save_json(t3_model)

    df = run(
        panel_path=panel_path,
        out_path=tmp_path / "test_matrix_t3.csv",
        equity_dir=tmp_path / "equity_t3",
        start=pd.Timestamp("2026-01-01", tz="UTC"),
        end=pd.Timestamp("2026-02-01", tz="UTC"),
        include_t3=True,
        t3_model=t3_model,
    )

    assert "t3_hazard" in set(df["policy"])
    assert len(df) == 7  # 6 baselines + T3
