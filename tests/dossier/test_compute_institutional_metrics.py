"""Test the CLI driver end-to-end: seeded equity parquets -> CSV with
all required columns and per-policy rows."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def _seed_equity(equity_dir: Path, policy: str, start_eq: float, daily_drift: float):
    n_blocks = 7200 * 30 * 4  # 4 months of blocks
    ts = pd.date_range("2026-01-01", periods=n_blocks, freq="12s", tz="UTC")
    drift = (1 + daily_drift / 7200) ** np.arange(n_blocks)
    df = pd.DataFrame({
        "block_number": np.arange(21_000_000, 21_000_000 + n_blocks),
        "position_usd": start_eq * drift,
        "current_protocol": "aave_v3",
        "block_timestamp": ts,
    })
    equity_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(equity_dir / f"equity_{policy}.parquet")


def test_compute_metrics_writes_csv_with_all_columns(tmp_path):
    from scripts.dossier.compute_institutional_metrics import compute

    equity_dir = tmp_path / "equity"
    out_csv = tmp_path / "institutional_metrics.csv"

    _seed_equity(equity_dir, "b1_always_aave", 1e6, 0.00002)
    _seed_equity(equity_dir, "t1_threshold", 1e6, 0.00003)

    compute(equity_dir=equity_dir, out_csv=out_csv,
            benchmark_policy="b1_always_aave")

    assert out_csv.exists()
    df = pd.read_csv(out_csv)
    expected_cols = {
        "policy", "net_apy_pct", "sharpe", "sortino", "calmar",
        "information_ratio_vs_benchmark", "max_drawdown_pct",
        "max_drawdown_duration_days", "time_to_recovery_days",
        "cvar_95_pct", "cvar_99_pct", "skew", "kurtosis_excess",
        "final_equity_usd",
    }
    assert expected_cols.issubset(set(df.columns))
    assert set(df["policy"]) == {"b1_always_aave", "t1_threshold"}
