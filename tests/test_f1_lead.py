"""Contract & correctness tests for F1LeadBuilder.

Six tests:
    1. family is 'f1'
    2. output passes the shared validator (tiny synthetic panel + DSR)
    3. lag_300 at block N equals the ffilled DSR at block N-300
    4. missing DSR file -> NaN f1_dsr_* cols + RuntimeWarning
    5. lead_spread_dsr_vs_top sign convention: positive when DSR > best pool
    6. block_timestamp output is tz-aware UTC
       (regression for the Pandas `.values` -> tz-naive gotcha,
       documented in tests/test_signal_features_base.py and the F1
       module docstring).
"""
from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from decision.features.base import validate_feature_frame
from decision.features.f1_lead import F1LeadBuilder


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
def _mini_panel(n: int = 2400, start_block: int = 21_000_000) -> pd.DataFrame:
    """A small but realistic per-block panel.

    n=2400 chosen so lag_1800 has some valid (non-NaN) rows for the
    lag-correctness test. Two protocol APR columns so the validator's
    F3-style consumers downstream remain happy and so we can exercise
    the lead-spread max-protocol logic.
    """
    block = np.arange(start_block, start_block + n, dtype="int64")
    ts = pd.date_range("2025-06-01", periods=n, freq="12s", tz="UTC")
    return pd.DataFrame(
        {
            "block_number": block,
            "block_timestamp": ts,
            "morpho_blue_lending_apr": np.full(n, 0.045, dtype="float64"),
            "euler_v2_lending_apr": np.full(n, 0.050, dtype="float64"),
        }
    )


def _synth_dsr(panel: pd.DataFrame, tmp_path: Path,
               rate_before: float = 0.06,
               rate_after: float = 0.08,
               switch_at_offset: int = 100) -> Path:
    """Write a 2-row DSR events parquet at known block numbers.

    The first event is BEFORE the panel start so the entire panel grid
    has a known DSR value; the second event is in-window so we can
    verify ffill semantics across the change.
    """
    panel_start = int(panel["block_number"].iloc[0])
    events = pd.DataFrame(
        {
            "block_number": pd.Series(
                [panel_start - 50, panel_start + switch_at_offset],
                dtype="int64",
            ),
            "block_timestamp": pd.to_datetime(
                [
                    panel["block_timestamp"].iloc[0] - pd.Timedelta("10min"),
                    panel["block_timestamp"].iloc[switch_at_offset],
                ],
                utc=True,
            ),
            "lending_rate_apr": pd.Series(
                [rate_before, rate_after], dtype="float64"
            ),
        }
    )
    path = tmp_path / "events_dsr.parquet"
    events.to_parquet(path, index=False)
    return path


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------
def test_builder_family_is_f1():
    """family classattr is locked to 'f1' so downstream prefix-check works."""
    b = F1LeadBuilder(dsr_events_path=Path("nonexistent.parquet"))
    assert b.family == "f1"


def test_output_passes_validator(tmp_path: Path):
    """Canonical happy path: synthetic panel + synthetic DSR events ->
    output frame passes the shared SignalFeatureBuilder validator."""
    panel = _mini_panel()
    dsr_path = _synth_dsr(panel, tmp_path)
    builder = F1LeadBuilder(dsr_events_path=dsr_path)
    df = builder.build(panel)

    # Validator is the source-of-truth contract for downstream training.
    validate_feature_frame(df, expected_family="f1")

    # Spot-check the expected feature columns are all present.
    expected = {
        "block_timestamp",
        "f1_dsr_apr",
        "f1_dsr_lag_300",
        "f1_dsr_lag_1800",
        "f1_dsr_delta_300",
        "f1_lead_spread_dsr_vs_top",
        "f1_sdai_proxy_apr",
        "f1_curve_3pool_apr",
    }
    assert expected.issubset(set(df.columns)), (
        f"missing columns: {expected - set(df.columns)}"
    )
    assert len(df) == len(panel)
    assert df.index.name == "block_number"


def test_lag_correctness(tmp_path: Path):
    """lag_300 at row N must equal f1_dsr_apr at row N-300.

    Since the panel is one row per block, a 300-block lag IS a 300-row
    positional shift. We pick rows well inside the panel (so both lag
    indices are defined) and assert exact equality, including across the
    DSR rate-change boundary at offset 100.
    """
    panel = _mini_panel(n=2400)
    # Two DSR levels: 6% before block panel_start+100, 8% after.
    dsr_path = _synth_dsr(
        panel, tmp_path,
        rate_before=0.06, rate_after=0.08, switch_at_offset=100,
    )
    df = F1LeadBuilder(dsr_events_path=dsr_path).build(panel)

    apr = df["f1_dsr_apr"].to_numpy()
    lag = df["f1_dsr_lag_300"].to_numpy()

    # First 300 rows have no lag predecessor -> NaN.
    assert np.all(np.isnan(lag[:300]))
    # After that, lag[N] == apr[N-300] exactly.
    for N in (300, 350, 400, 500, 1000, 2399):
        if np.isnan(apr[N - 300]):
            assert np.isnan(lag[N])
        else:
            assert lag[N] == apr[N - 300], (
                f"lag mismatch at row {N}: lag={lag[N]} apr[N-300]={apr[N-300]}"
            )

    # Specifically, row 400 (well past the switch at offset 100):
    # apr[400] == 0.08, lag[400] == apr[100] == 0.08 too (switch happened
    # AT offset 100). Row 399: apr[399]==0.08, lag[399]==apr[99]==0.06.
    assert apr[400] == pytest.approx(0.08)
    assert lag[400] == pytest.approx(0.08)
    assert apr[399] == pytest.approx(0.08)
    assert lag[399] == pytest.approx(0.06)

    # delta_300 = apr - lag, so the same boundary check applies.
    delta = df["f1_dsr_delta_300"].to_numpy()
    assert delta[399] == pytest.approx(0.08 - 0.06)
    assert delta[400] == pytest.approx(0.0)


def test_dsr_missing_file_produces_nan_with_warning(tmp_path: Path):
    """If the events_dsr parquet doesn't exist on disk, the builder
    MUST not raise; it must emit NaN-filled f1_dsr_* columns and warn,
    so downstream T3 training can still proceed (with reduced signal)."""
    panel = _mini_panel(n=600)
    missing = tmp_path / "definitely_not_there.parquet"
    assert not missing.exists()

    builder = F1LeadBuilder(dsr_events_path=missing)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        df = builder.build(panel)
    msgs = [str(x.message) for x in w]
    assert any("not found" in m.lower() or "missing" in m.lower() for m in msgs), (
        f"expected a 'not found' warning, got {msgs}"
    )

    # All DSR-derived columns should be all-NaN.
    for col in (
        "f1_dsr_apr", "f1_dsr_lag_300", "f1_dsr_lag_1800",
        "f1_dsr_delta_300", "f1_lead_spread_dsr_vs_top",
    ):
        assert df[col].isna().all(), f"{col} should be all-NaN, got {df[col].head()}"


def test_lead_spread_sign(tmp_path: Path):
    """f1_lead_spread_dsr_vs_top > 0 iff DSR pays more than the best
    available protocol at that block. Positive spread => pools are
    currently under-priced relative to DSR => expect them to re-price
    upward in the next few hours (the F1 lead hypothesis)."""
    panel = _mini_panel(n=600)
    # Protocols pay 4.5% / 5.0% (max = 5.0%); DSR pays 8.0%.
    # Expected spread = 0.08 - 0.05 = 0.03 (positive, signalling pools
    # should follow DSR up).
    dsr_path = _synth_dsr(
        panel, tmp_path,
        rate_before=0.08, rate_after=0.08, switch_at_offset=10,
    )
    df = F1LeadBuilder(dsr_events_path=dsr_path).build(panel)
    spread = df["f1_lead_spread_dsr_vs_top"].to_numpy()

    # All rows have DSR == 8%, top protocol == 5%, so spread == +3%.
    assert np.all(spread > 0), "spread should be strictly positive when DSR > best pool"
    assert spread[300] == pytest.approx(0.08 - 0.05)

    # Flip the inequality: bump protocols above DSR -> spread negative.
    panel_hot = panel.copy()
    panel_hot["morpho_blue_lending_apr"] = 0.10  # 10% > 8% DSR
    panel_hot["euler_v2_lending_apr"] = 0.09
    df2 = F1LeadBuilder(dsr_events_path=dsr_path).build(panel_hot)
    spread2 = df2["f1_lead_spread_dsr_vs_top"].to_numpy()
    assert np.all(spread2 < 0), "spread should be negative when pools > DSR"
    assert spread2[300] == pytest.approx(0.08 - 0.10)


def test_block_timestamp_tz_aware_utc(tmp_path: Path):
    """Regression for the documented `.values` gotcha: pd.Series.values
    on a tz-aware datetime Series returns tz-NAIVE memory. The base
    validator rejects naive timestamps; the F1 builder MUST emit a
    tz-aware UTC block_timestamp column. This test re-locks that
    invariant at the F1 layer.
    """
    panel = _mini_panel(n=300)
    dsr_path = _synth_dsr(panel, tmp_path)
    df = F1LeadBuilder(dsr_events_path=dsr_path).build(panel)

    ts = df["block_timestamp"]
    assert pd.api.types.is_datetime64_any_dtype(ts), f"got {ts.dtype}"
    tz = getattr(ts.dt, "tz", None)
    assert tz is not None, "block_timestamp lost its tz (the .values gotcha)"
    # Compare via the iana zone string to avoid pytz/zoneinfo identity issues.
    assert str(tz) == "UTC", f"expected UTC, got {tz!s}"

    # Values must match the panel exactly (no off-by-one from shifting).
    assert (df["block_timestamp"].to_numpy() == panel["block_timestamp"].to_numpy()).all()
