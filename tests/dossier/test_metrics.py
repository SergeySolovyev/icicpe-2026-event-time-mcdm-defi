"""Unit + property tests for institutional metrics.

Reference values cross-checked against:
- Sharpe: Lo (2002) "The Statistics of Sharpe Ratios" eq (4)
- Sortino: Sortino & Price (1994) "Performance Measurement in a Downside
  Risk Framework" Journal of Investing 3(3):59-64.
- Calmar: Young (1991) "Calmar Ratio: A Smoother Tool"
- Information Ratio: Grinold & Kahn (1999) "Active Portfolio Management" Ch 4
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.dossier.metrics import (
    sharpe,
    sortino,
    calmar,
    information_ratio,
    max_drawdown,
    max_drawdown_duration,
    time_to_recovery,
    cvar,
    skew_kurt,
    daily_from_block_equity,
)


@pytest.fixture
def simple_daily_returns():
    """Simple synthetic series: mean +0.001/day, std 0.005, 252 days."""
    rng = np.random.default_rng(42)
    return pd.Series(0.001 + 0.005 * rng.standard_normal(252))


def test_sharpe_basic(simple_daily_returns):
    """Sharpe = mean/std * sqrt(periods_per_year). Annualized at 365 (crypto)."""
    s = sharpe(simple_daily_returns, periods_per_year=365)
    # mean 0.001, std ~0.005 -> daily SR ~0.2, ann ~0.2*sqrt(365)~3.82
    assert 2.5 < s < 5.0


def test_sortino_at_least_sharpe(simple_daily_returns):
    """Sortino uses downside-only std, which is <= total std,
    so Sortino >= Sharpe for any series with non-zero downside."""
    s = sharpe(simple_daily_returns, periods_per_year=365)
    so = sortino(simple_daily_returns, periods_per_year=365, target=0.0)
    assert so >= s


def test_calmar_apy_div_maxdd():
    """Calmar = APY / |MaxDD|, both positive scalars."""
    eq = pd.Series([1.0, 1.05, 1.10, 1.05, 1.045, 1.10])
    apy = eq.iloc[-1] / eq.iloc[0] - 1.0
    mdd = max_drawdown(eq)
    cal = calmar(apy=apy, max_dd=mdd)
    assert cal == pytest.approx(apy / abs(mdd))


def test_information_ratio_basic():
    """IR = mean(r_a - r_b) / std(r_a - r_b) * sqrt(periods_per_year).
    A series that consistently beats benchmark by +0.001/day with low
    tracking-error has IR ~ sqrt(252) for daily, sqrt(365) for crypto."""
    rng = np.random.default_rng(0)
    bench = pd.Series(0.0 + 0.001 * rng.standard_normal(365))
    strat = bench + 0.001  # +10bp/day constant alpha
    ir = information_ratio(strat, bench, periods_per_year=365)
    assert ir > 10  # huge IR because constant alpha


def test_max_drawdown_known():
    """Equity 1.0 -> 1.5 -> 1.2 -> 1.8 has MaxDD = (1.5 - 1.2)/1.5 = 0.20."""
    eq = pd.Series([1.0, 1.5, 1.2, 1.8])
    mdd = max_drawdown(eq)
    assert mdd == pytest.approx(-0.20)


def test_max_drawdown_duration_known():
    """Index implied as integers (days). 1.0@0 -> 1.5@1 (peak) -> 1.2@2
    (trough) -> 1.4@3 -> 1.6@4 (recovery). Peak at index 1, recovery at
    index 4 -> duration 3."""
    eq = pd.Series([1.0, 1.5, 1.2, 1.4, 1.6])
    dur = max_drawdown_duration(eq)
    assert dur == 3


def test_time_to_recovery_no_recovery():
    """If equity never recovers to peak, TTR = inf (or NaN)."""
    eq = pd.Series([1.0, 1.5, 1.2, 1.3, 1.4])  # never reaches 1.5
    ttr = time_to_recovery(eq)
    assert np.isinf(ttr) or pd.isna(ttr)


def test_cvar_95():
    """CVaR_95 of N(0,1) sampled densely ~ -2.06 (theoretical -2.063)."""
    rng = np.random.default_rng(0)
    returns = pd.Series(rng.standard_normal(100_000))
    c = cvar(returns, alpha=0.05)
    assert -2.2 < c < -1.9


def test_cvar_99_below_cvar_95():
    """CVaR_99 should be more extreme (more negative) than CVaR_95."""
    rng = np.random.default_rng(0)
    returns = pd.Series(rng.standard_normal(10_000))
    c95 = cvar(returns, alpha=0.05)
    c99 = cvar(returns, alpha=0.01)
    assert c99 < c95  # more negative


def test_skew_kurt_normal_close_to_zero_three():
    """N(0,1) has skew=0, excess kurtosis=0 (raw kurtosis=3)."""
    rng = np.random.default_rng(0)
    returns = pd.Series(rng.standard_normal(50_000))
    sk, kt = skew_kurt(returns)
    assert abs(sk) < 0.05
    assert abs(kt) < 0.1


def test_daily_from_block_equity_aggregation():
    """Per-block equity series -> daily last-of-day equity series."""
    n = 24 * 60 * 60 // 12 * 3  # 3 days worth of 12s blocks
    timestamps = pd.date_range("2026-01-01", periods=n, freq="12s", tz="UTC")
    eq_block = pd.Series(np.linspace(1_000_000, 1_001_500, n), index=timestamps)
    eq_daily = daily_from_block_equity(eq_block)
    assert len(eq_daily) == 3  # three days
    assert eq_daily.index.tz is not None  # tz preserved
