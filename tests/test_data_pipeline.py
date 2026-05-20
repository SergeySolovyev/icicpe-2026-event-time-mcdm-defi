"""Tests for the data pipeline: kink math, feature extraction, cleaning.

These tests do NOT hit the network. They use synthetic data to verify
internal invariants of the pipeline.

Run: pytest tests/test_data_pipeline.py -v
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from data.features import (
    AaveKinkParams,
    CompoundKinkParams,
    cross_protocol_spread,
    extract_features,
    f_kink,
    rate_residual,
)


# Realistic-ish Aave V3 USDC params (matches docs.aave.com as of 2024-Q4)
AAVE_USDC = AaveKinkParams(
    base_variable_borrow_rate=0.0,
    slope1=0.05,
    slope2=0.60,
    optimal_usage_ratio=0.92,
    reserve_factor=0.10,
)

# Compound V3 cUSDCv3 params (illustrative)
COMP_USDC = CompoundKinkParams(
    supply_kink=0.85,
    supply_per_second_base=0.0,
    supply_per_second_slope_low=0.05,
    supply_per_second_slope_high=0.60,
)


# ----------------------------------------------------------------------------
# Kink math invariants
# ----------------------------------------------------------------------------

def test_aave_supply_rate_zero_at_zero_utilization():
    assert f_kink(0.0, AAVE_USDC) == pytest.approx(0.0, abs=1e-10)


def test_aave_supply_rate_monotonic_increasing():
    u = np.linspace(0.0, 0.99, 100)
    r = f_kink(u, AAVE_USDC)
    diffs = np.diff(r)
    assert (diffs >= -1e-12).all(), "supply rate must be non-decreasing in u"


def test_aave_supply_rate_jumps_at_kink():
    """Above the kink, slope2 dominates -> rate accelerates sharply."""
    pre_kink_slope = f_kink(0.91, AAVE_USDC) - f_kink(0.90, AAVE_USDC)
    post_kink_slope = f_kink(0.94, AAVE_USDC) - f_kink(0.93, AAVE_USDC)
    assert post_kink_slope > 5 * pre_kink_slope, (
        f"slope2 not dominant post-kink: pre={pre_kink_slope:.4f} post={post_kink_slope:.4f}"
    )


def test_compound_supply_rate_continuous_at_kink():
    """Both formulas must agree at u == supply_kink."""
    eps = 1e-6
    just_below = float(f_kink(COMP_USDC.supply_kink - eps, COMP_USDC))
    just_above = float(f_kink(COMP_USDC.supply_kink + eps, COMP_USDC))
    assert abs(just_below - just_above) < 1e-6


def test_compound_supply_rate_monotonic_increasing():
    u = np.linspace(0.0, 0.99, 100)
    r = f_kink(u, COMP_USDC)
    assert (np.diff(r) >= -1e-12).all()


# ----------------------------------------------------------------------------
# Residual reconstruction invariant
# ----------------------------------------------------------------------------

def test_residual_zero_for_on_curve_data():
    """If r = f_kink(u; params) exactly, the residual should be zero."""
    u = np.linspace(0.1, 0.95, 50)
    r = np.asarray(f_kink(u, AAVE_USDC))
    eps = rate_residual(r, u, AAVE_USDC)
    assert np.allclose(eps, 0.0, atol=1e-10)


def test_residual_plus_kink_reconstructs_rate():
    """Round-trip: r ≈ f_kink(u) + (r - f_kink(u))."""
    rng = np.random.default_rng(42)
    u = rng.uniform(0.1, 0.95, size=50)
    r = np.asarray(f_kink(u, AAVE_USDC)) + 0.005 * rng.standard_normal(50)
    eps = rate_residual(r, u, AAVE_USDC)
    reconstructed = np.asarray(f_kink(u, AAVE_USDC)) + eps
    assert np.allclose(reconstructed, r, atol=1e-12)


# ----------------------------------------------------------------------------
# Cross-protocol spread
# ----------------------------------------------------------------------------

def test_cross_protocol_spread_keys_and_shapes():
    u_a = np.linspace(0.1, 0.9, 24)
    u_c = np.linspace(0.1, 0.9, 24)
    r_a = np.asarray(f_kink(u_a, AAVE_USDC))
    r_c = np.asarray(f_kink(u_c, COMP_USDC))

    out = cross_protocol_spread(r_a, r_c, u_a, u_c, AAVE_USDC, COMP_USDC)
    assert set(out.keys()) == {"rate_spread", "residual_spread", "kink_spread", "util_spread"}
    for v in out.values():
        assert v.shape == (24,)


def test_cross_protocol_spread_zero_when_protocols_identical():
    """Identical inputs + identical kink params -> all spreads zero.

    We don't have identical kink params between AAVE and COMP types, but the
    *util_spread* must be zero when u_a == u_c.
    """
    u = np.linspace(0.1, 0.9, 10)
    r_a = np.asarray(f_kink(u, AAVE_USDC))
    r_c = np.asarray(f_kink(u, COMP_USDC))
    out = cross_protocol_spread(r_a, r_c, u, u, AAVE_USDC, COMP_USDC)
    assert np.allclose(out["util_spread"], 0.0)


# ----------------------------------------------------------------------------
# extract_features integration
# ----------------------------------------------------------------------------

def _synthetic_joined_df(n_hours: int = 48) -> pd.DataFrame:
    """Build a tiny synthetic dataframe matching the joined-clean schema.

    Per the joined_clean.parquet convention (verified by the audit on
    2026-05-20), r_aave / r_compound are PER-HOUR rates. f_kink returns
    annualized rates, so we divide by HOURS_PER_YEAR here so the synthetic
    data lies on the kink curve in the same scale as production data.
    extract_features will multiply back by 8760 internally to produce
    r_*_annual columns.
    """
    HOURS_PER_YEAR = 365 * 24
    rng = np.random.default_rng(0)
    idx = pd.date_range("2026-01-01", periods=n_hours, freq="1h", tz="UTC")
    u_a = np.clip(0.5 + 0.1 * rng.standard_normal(n_hours), 0.0, 0.99)
    u_c = np.clip(0.4 + 0.1 * rng.standard_normal(n_hours), 0.0, 0.99)
    r_a = np.asarray(f_kink(u_a, AAVE_USDC)) / HOURS_PER_YEAR
    r_c = np.asarray(f_kink(u_c, COMP_USDC)) / HOURS_PER_YEAR
    return pd.DataFrame({
        "r_aave": r_a, "r_compound": r_c,
        "u_aave": u_a, "u_compound": u_c,
        "tvl_aave": rng.uniform(1e8, 2e8, n_hours),
        "tvl_compound": rng.uniform(1e8, 2e8, n_hours),
        "gas_gwei": rng.uniform(20, 50, n_hours),
        "eth_usd": rng.uniform(3000, 4000, n_hours),
    }, index=idx)


def test_extract_features_adds_expected_columns():
    df = _synthetic_joined_df(48)
    out = extract_features(df, AAVE_USDC, COMP_USDC)
    expected = {"eps_aave", "eps_compound", "rate_spread", "residual_spread",
                "kink_spread", "util_spread", "dTVL_aave_24h",
                "dTVL_compound_24h", "tod_sin", "tod_cos"}
    assert expected.issubset(set(out.columns))


def test_extract_features_eps_close_to_zero_for_on_curve_synth():
    """Our synthetic data was generated ON the kink curve, so eps must be ~0."""
    df = _synthetic_joined_df(48)
    out = extract_features(df, AAVE_USDC, COMP_USDC)
    assert np.allclose(out["eps_aave"].values, 0.0, atol=1e-10)
    assert np.allclose(out["eps_compound"].values, 0.0, atol=1e-10)


def test_extract_features_tod_cyclical_encoding():
    """tod_sin^2 + tod_cos^2 == 1 for every row."""
    df = _synthetic_joined_df(48)
    out = extract_features(df, AAVE_USDC, COMP_USDC)
    norm = out["tod_sin"] ** 2 + out["tod_cos"] ** 2
    assert np.allclose(norm.values, 1.0)


# ----------------------------------------------------------------------------
# Markov-switching baseline (forecaster/baseline_markov.py, ablation #4)
# ----------------------------------------------------------------------------

def test_markov_forecaster_transition_matrix_rows_sum_to_one():
    """Sanity: any valid Markov transition matrix has rows summing to 1."""
    from forecaster.baseline_markov import MarkovSwitchingForecaster

    rng = np.random.default_rng(0)
    n = 200
    u = np.clip(rng.beta(5, 2, n), 0.05, 0.99)
    # Synthetic: rate proportional to u, with regime-dependent noise.
    r = 0.02 + 0.05 * u + 0.005 * rng.standard_normal(n)

    rate = pd.Series(r, index=pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC"))
    util = pd.Series(u, index=rate.index)

    # Pin the quantile path so the test is deterministic and fast.
    fc = MarkovSwitchingForecaster(n_regimes=2, method="quantile").fit(rate, util)
    P = fc.fit_result.transition_matrix
    assert P.shape == (2, 2), f"transition matrix shape {P.shape}, expected (2, 2)"
    row_sums = P.sum(axis=1)
    assert np.allclose(row_sums, 1.0, atol=1e-9), (
        f"rows do not sum to 1: {row_sums}"
    )
    assert (P >= 0).all() and (P <= 1).all(), "entries must lie in [0, 1]"


def test_markov_forecaster_predict_returns_scalar():
    """The predict() method must return a single float, not an array."""
    from forecaster.baseline_markov import MarkovSwitchingForecaster

    rng = np.random.default_rng(1)
    n = 200
    u = np.clip(rng.beta(5, 2, n), 0.05, 0.99)
    r = 0.02 + 0.05 * u + 0.005 * rng.standard_normal(n)
    rate = pd.Series(r, index=pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC"))
    util = pd.Series(u, index=rate.index)

    fc = MarkovSwitchingForecaster(n_regimes=2, method="quantile",
                                   n_sims=100).fit(rate, util)
    out = fc.predict(rate.tail(168), util.tail(168), horizon=12)
    assert isinstance(out, float), f"expected float, got {type(out).__name__}: {out!r}"
    assert np.isfinite(out), f"forecast must be finite, got {out}"
