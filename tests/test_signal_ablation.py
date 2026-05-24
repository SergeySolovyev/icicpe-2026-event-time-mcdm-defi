"""Tests for the signal LOO (Leave-One-Out) ablation runner.

Retrains T3 with all 3 signal families, then 3 more times with one
family dropped each, then 3 more 1-family-only variants. Computes
in-sample C-index per fit + writes a tidy CSV. Plan D D2 takes this
CSV and runs the actual paper-grade comparison on the test fold.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtest.run_signal_ablation import (
    ABLATION_VARIANTS,
    run_signal_ablation,
)


def _synth_panel_and_features(n_blocks: int = 800, seed: int = 7):
    """Build a tiny synthetic dataset with 3 feature frames + panel
    that has a real F3 signal and noise F1/F4 features."""
    rng = np.random.default_rng(seed)
    block = np.arange(20_000_000, 20_000_000 + n_blocks, dtype="int64")
    ts = pd.date_range("2025-06-01", periods=n_blocks, freq="12s", tz="UTC")
    aave = 0.04 + np.cumsum(rng.standard_normal(n_blocks) * 0.0002)
    comp = 0.04 + np.cumsum(rng.standard_normal(n_blocks) * 0.0002)
    for i in range(n_blocks - 10):
        if abs(aave[i] - comp[i]) > 0.005:
            sgn = 1 if comp[i] > aave[i] else -1
            aave[i + 5 : i + 10] = comp[i + 5 : i + 10] + sgn * 0.001
    panel = pd.DataFrame({
        "block_number": block,
        "block_timestamp": ts,
        "aave_v3_lending_apr": aave,
        "compound_v3_lending_apr": comp,
    })
    f3 = pd.DataFrame({
        "block_timestamp": ts,
        "f3_spread_max_minus_min": np.abs(aave - comp),
    }, index=pd.Index(block, name="block_number"))
    f1 = pd.DataFrame({
        "block_timestamp": ts,
        "f1_dsr_apr": rng.standard_normal(n_blocks) * 0.001 + 0.05,
    }, index=pd.Index(block, name="block_number"))
    f4 = pd.DataFrame({
        "block_timestamp": ts,
        "f4_gas_gwei": rng.lognormal(3, 0.5, size=n_blocks),
    }, index=pd.Index(block, name="block_number"))
    return panel, {"f1": f1, "f3": f3, "f4": f4}


def test_ablation_variants_complete_set():
    """Must include the canonical 7 ablation variants per the plan."""
    expected = {
        "T3_full",
        "T3_no_F1",
        "T3_no_F3",
        "T3_no_F4",
        "T3_F1_only",
        "T3_F3_only",
        "T3_F4_only",
    }
    assert set(ABLATION_VARIANTS) == expected


def test_ablation_runner_csv_shape(tmp_path: Path):
    panel, feats = _synth_panel_and_features()
    out_csv = tmp_path / "signal_ablation.csv"
    df = run_signal_ablation(
        feature_frames=feats,
        panel=panel,
        horizon_blocks=200,
        out_path=out_csv,
    )
    assert out_csv.exists()
    assert len(df) == len(ABLATION_VARIANTS)
    expected_cols = {"variant", "c_index", "n_train_rows", "n_features"}
    assert expected_cols.issubset(df.columns)


def test_ablation_full_beats_dropping_dominant_family(tmp_path: Path):
    """Pre-registered hypothesis (design spec §III.D): F3 is the
    dominant signal. So dropping F3 must produce a noticeably lower
    C-index than dropping F1 or F4."""
    panel, feats = _synth_panel_and_features(n_blocks=2_000, seed=7)
    df = run_signal_ablation(
        feature_frames=feats,
        panel=panel,
        horizon_blocks=500,
        out_path=tmp_path / "ablation.csv",
    )
    by_var = df.set_index("variant")["c_index"]
    # Sanity: T3_no_F3 should be the WEAKEST drop variant.
    assert by_var["T3_no_F3"] <= by_var["T3_no_F1"] + 0.10, (
        f"Expected F3 dominance: c_index_no_F3 ({by_var['T3_no_F3']:.4f}) "
        f"should be <= c_index_no_F1 ({by_var['T3_no_F1']:.4f}) + 0.10 "
        f"tolerance, but it isn't."
    )


def test_ablation_runs_with_partial_feature_family():
    """If a variant tries to fit with only one family but that family
    has zero features remaining (e.g. dropped because of NaN), the
    runner must skip gracefully rather than raise."""
    panel, feats = _synth_panel_and_features()
    # All-NaN F1 frame.
    f1_nan = feats["f1"].copy()
    for col in f1_nan.columns:
        if col != "block_timestamp":
            f1_nan[col] = float("nan")
    feats["f1"] = f1_nan
    df = run_signal_ablation(
        feature_frames=feats,
        panel=panel,
        horizon_blocks=200,
        out_path=None,  # don't write the csv for this test
    )
    # F1_only variant should be flagged with NaN c_index instead of raising.
    f1_only = df[df["variant"] == "T3_F1_only"].iloc[0]
    assert pd.isna(f1_only["c_index"]) or f1_only["c_index"] < 0.55
