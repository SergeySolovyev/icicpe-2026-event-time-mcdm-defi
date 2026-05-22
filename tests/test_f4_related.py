"""Tests for the F4 (gas + stablecoin peg) feature builder.

Covers:
    * builder.family == 'f4'
    * output passes the canonical validator
    * gas_log10 algebra (gas=10 -> log10=1.0)
    * trailing 30d quantile rank uses last row vs known window
    * peg-deviation algebra (1.0 -> 0 bps, 1.01 -> +100 bps, 0.99 -> -100 bps)
    * missing input columns produce NaN + UserWarning
    * block_timestamp stays tz-aware (Pandas .values gotcha regression)
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

from decision.features.base import validate_feature_frame
from decision.features.f4_related import F4RelatedBuilder, _BLOCKS_30D


def _panel(n: int = 400, *, include: tuple[str, ...] = (
    "gas_price_gwei", "eth_usd", "usdc_peg", "usdt_peg",
)) -> pd.DataFrame:
    """Minimal per-block panel for F4 tests."""
    block = np.arange(1_000_000, 1_000_000 + n, dtype="int64")
    ts = pd.date_range("2025-01-01", periods=n, freq="12s", tz="UTC")
    base = {"block_number": block, "block_timestamp": ts}
    if "gas_price_gwei" in include:
        base["gas_price_gwei"] = np.linspace(5.0, 50.0, n)
    if "eth_usd" in include:
        base["eth_usd"] = np.linspace(2000.0, 3000.0, n)
    if "usdc_peg" in include:
        base["usdc_peg"] = np.full(n, 1.0)
    if "usdt_peg" in include:
        base["usdt_peg"] = np.full(n, 1.0)
    return pd.DataFrame(base)


def test_builder_family_is_f4():
    assert F4RelatedBuilder().family == "f4"


def test_output_passes_validator():
    df = F4RelatedBuilder().build(_panel())
    validate_feature_frame(df, expected_family="f4")
    # All six declared feature columns present.
    for col in (
        "f4_gas_gwei", "f4_gas_log10", "f4_gas_quantile_30d",
        "f4_eth_usd", "f4_usdc_peg_dev_bps", "f4_usdt_peg_dev_bps",
    ):
        assert col in df.columns, f"missing {col}"


def test_gas_log10_transform():
    """gas=10 gwei -> log10(10) = 1.0; gas=100 -> 2.0; gas=1 -> 0.0."""
    panel = _panel(n=5)
    panel["gas_price_gwei"] = np.array([1.0, 10.0, 100.0, 0.0, 50.0])
    df = F4RelatedBuilder().build(panel)
    log10 = df["f4_gas_log10"].to_numpy()
    assert log10[0] == pytest.approx(0.0)
    assert log10[1] == pytest.approx(1.0)
    assert log10[2] == pytest.approx(2.0)
    # gas=0 is floored to 1e-3 -> log10 = -3.0 (no -inf).
    assert log10[3] == pytest.approx(-3.0)
    assert np.isfinite(log10).all()


def test_30d_quantile_uses_trailing_window():
    """With a strictly increasing gas series, the last row's
    trailing-30d rank must be 1.0 (current is the highest in the window)
    and rows before the window completes must be NaN.
    """
    n = _BLOCKS_30D + 50
    panel = _panel(n=n)
    panel["gas_price_gwei"] = np.arange(1, n + 1, dtype="float64")
    df = F4RelatedBuilder().build(panel)
    q = df["f4_gas_quantile_30d"].to_numpy()

    # Window incomplete for the first (_BLOCKS_30D - 1) rows -> NaN.
    assert np.isnan(q[: _BLOCKS_30D - 1]).all()
    # Once the window fills, monotonically increasing input -> rank = 1.0.
    assert q[_BLOCKS_30D - 1] == pytest.approx(1.0)
    assert q[-1] == pytest.approx(1.0)


def test_peg_deviation_zero_when_peg_is_1():
    """peg=1.0 -> 0 bps; peg=1.01 -> +100 bps; peg=0.99 -> -100 bps."""
    panel = _panel(n=3)
    panel["usdc_peg"] = np.array([1.0, 1.01, 0.99])
    panel["usdt_peg"] = np.array([1.0, 0.99, 1.01])
    df = F4RelatedBuilder().build(panel)

    usdc = df["f4_usdc_peg_dev_bps"].to_numpy()
    usdt = df["f4_usdt_peg_dev_bps"].to_numpy()

    assert usdc[0] == pytest.approx(0.0)
    assert usdc[1] == pytest.approx(100.0)
    assert usdc[2] == pytest.approx(-100.0)
    assert usdt[0] == pytest.approx(0.0)
    assert usdt[1] == pytest.approx(-100.0)
    assert usdt[2] == pytest.approx(100.0)


def test_missing_columns_emit_nan_with_warning():
    """Every absent input column triggers a UserWarning and the
    corresponding feature column(s) are NaN-filled float64."""
    panel = _panel(n=10, include=())  # only block_number + block_timestamp
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        df = F4RelatedBuilder().build(panel)

    # At least one warning per missing input family
    # (gas, eth, usdc_peg, usdt_peg -> 4 warnings).
    messages = [str(item.message) for item in w]
    assert any("gas_price_gwei" in m for m in messages)
    assert any("eth_usd" in m for m in messages)
    assert any("usdc_peg" in m for m in messages)
    assert any("usdt_peg" in m for m in messages)

    # All numeric feature columns are NaN, but still float64 so the
    # validator passes.
    for col in (
        "f4_gas_gwei", "f4_gas_log10", "f4_gas_quantile_30d",
        "f4_eth_usd", "f4_usdc_peg_dev_bps", "f4_usdt_peg_dev_bps",
    ):
        assert df[col].dtype == "float64"
        assert df[col].isna().all(), f"{col} not all NaN"

    # Builder output STILL satisfies the canonical contract.
    validate_feature_frame(df, expected_family="f4")


def test_block_timestamp_tz_aware_utc():
    """Regression for the Pandas .values gotcha: the output's
    block_timestamp column must remain tz-aware UTC."""
    df = F4RelatedBuilder().build(_panel(n=20))
    ts = df["block_timestamp"]
    assert pd.api.types.is_datetime64_any_dtype(ts)
    assert ts.dt.tz is not None
    assert str(ts.dt.tz) == "UTC"
