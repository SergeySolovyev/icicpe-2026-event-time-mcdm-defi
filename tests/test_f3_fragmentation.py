"""Tests for F3 fragmentation builder (Plan C Task 3)."""
from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd
import pytest

from decision.features.base import validate_feature_frame
from decision.features.f3_fragmentation import F3FragmentationBuilder


def _panel(protos, n=50, seed=0):
    """Build a synthetic per-block panel with the given protocols."""
    rng = np.random.default_rng(seed)
    block = np.arange(1_000_000, 1_000_000 + n, dtype="int64")
    ts = pd.date_range("2025-01-01", periods=n, freq="12s", tz="UTC")
    data = {"block_number": block, "block_timestamp": ts}
    for p in protos:
        data[f"{p}_lending_apr"] = rng.uniform(0.03, 0.08, size=n).astype(
            "float64"
        )
    return pd.DataFrame(data)


def test_builder_family_is_f3():
    b = F3FragmentationBuilder()
    assert b.family == "f3"


def test_dynamic_protocol_discovery():
    """2-protocol partial panel -> exactly 1 pair column."""
    panel = _panel(["morpho_blue", "euler_v2"], n=20)
    df = F3FragmentationBuilder().build(panel)

    pair_cols = [c for c in df.columns if c.startswith("f3_spread_")
                 and c not in ("f3_spread_max_minus_min", "f3_spread_top2")]
    assert len(pair_cols) == 1
    assert pair_cols[0] == "f3_spread_euler_v2_vs_morpho_blue"
    validate_feature_frame(df, expected_family="f3")


def test_dynamic_protocol_discovery_6_proto():
    """6-protocol full panel -> C(6,2) = 15 pair columns."""
    protos = [
        "aave_v3", "compound_v3", "morpho_blue",
        "euler_v2", "spark", "fluid",
    ]
    panel = _panel(protos, n=10)
    df = F3FragmentationBuilder().build(panel)

    pair_cols = [c for c in df.columns if c.startswith("f3_spread_")
                 and c not in ("f3_spread_max_minus_min", "f3_spread_top2")]
    assert len(pair_cols) == 15
    # All unordered pairs in sorted-name order are present.
    sorted_protos = sorted(protos)
    expected = {
        f"f3_spread_{sorted_protos[i]}_vs_{sorted_protos[j]}"
        for i, j in combinations(range(6), 2)
    }
    assert set(pair_cols) == expected
    validate_feature_frame(df, expected_family="f3")


def test_spread_sign_convention():
    """Spread = panel[i] - panel[j] given canonical sort i<j."""
    panel = _panel(["aave_v3", "compound_v3"], n=30, seed=42)
    df = F3FragmentationBuilder().build(panel)

    # Sorted-name order: aave_v3 < compound_v3.
    expected = (
        panel["aave_v3_lending_apr"].to_numpy()
        - panel["compound_v3_lending_apr"].to_numpy()
    )
    actual = df["f3_spread_aave_v3_vs_compound_v3"].to_numpy()
    np.testing.assert_allclose(actual, expected, rtol=1e-12)


def test_top2_equals_max_minus_runner_up():
    """f3_spread_top2 == max - runner_up (immediate switching signal)."""
    protos = ["aave_v3", "compound_v3", "morpho_blue", "euler_v2"]
    panel = _panel(protos, n=40, seed=7)
    df = F3FragmentationBuilder().build(panel)

    apr_cols = [f"{p}_lending_apr" for p in protos]
    apr = panel[apr_cols].to_numpy(dtype="float64")
    sorted_asc = np.sort(apr, axis=1)
    expected_top2 = sorted_asc[:, -1] - sorted_asc[:, -2]
    np.testing.assert_allclose(
        df["f3_spread_top2"].to_numpy(), expected_top2, rtol=1e-12
    )

    expected_mmm = np.nanmax(apr, axis=1) - np.nanmin(apr, axis=1)
    np.testing.assert_allclose(
        df["f3_spread_max_minus_min"].to_numpy(), expected_mmm, rtol=1e-12
    )


def test_dispersion_std_zero_when_1_protocol_raises():
    """Single-protocol panel -> ValueError (no spread to compute)."""
    panel = _panel(["aave_v3"], n=10)
    with pytest.raises(ValueError, match="at least 2"):
        F3FragmentationBuilder().build(panel)


def test_block_timestamp_tz_aware_utc():
    """Regression for the Pandas .values tz-naive gotcha (commit 911a7d7).

    `Series[datetime64[ns, UTC]].values` strips tz; the builder must use
    `.array` (or reassign tz) so validate_feature_frame doesn't reject
    the output as tz-naive.
    """
    panel = _panel(["aave_v3", "compound_v3"], n=15)
    df = F3FragmentationBuilder().build(panel)

    ts = df["block_timestamp"]
    assert pd.api.types.is_datetime64_any_dtype(ts)
    assert ts.dt.tz is not None
    assert str(ts.dt.tz) == "UTC"
    # And the contract validator must accept it.
    validate_feature_frame(df, expected_family="f3")
