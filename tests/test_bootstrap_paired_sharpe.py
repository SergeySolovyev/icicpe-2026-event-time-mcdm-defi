"""Tests for Plan D Task 2 -- paired-monthly Sharpe bootstrap.

Spec source:
  docs/superpowers/plans/2026-05-24-empirical-study-paper-draft.md, Task D2.

Per the task constraint the bootstrap is pure-numpy (no scipy.stats);
seeded via np.random.default_rng so all reproducibility tests use a
fixed seed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _equity_curve(monthly_apr: float, n: int = 8000) -> pd.DataFrame:
    """Build a synthetic 4-month constant-APR equity curve.

    The curve is geometric so that end-of-month equity equals
    start * (1 + monthly_apr/12) per month; the bootstrap math is the
    same as for a real curve but the test is sub-second.
    """
    # Span Jan-Apr 2026 (~120 days). 120*24*60 / n minutes per step gives
    # us 4 calendar months of synthetic blocks.
    blocks = np.arange(20_000_000, 20_000_000 + n, dtype=np.int64)
    minutes_total = 120 * 24 * 60  # ~4 months
    freq_min = max(1, minutes_total // n)
    ts = pd.date_range("2026-01-01", periods=n, freq=f"{freq_min}min", tz="UTC")
    per_period = (1.0 + monthly_apr / 12.0) ** (1.0 / (n / 4.0))
    equity = 1_000_000.0 * np.cumprod(np.full(n, per_period, dtype=np.float64))
    return pd.DataFrame({
        "block_number": blocks,
        "block_timestamp": ts,
        "position_usd": equity,
        "current_protocol": ["aave_v3"] * n,
    })


def test_monthly_returns_table_shape():
    from backtest.bootstrap_paired_sharpe import monthly_returns_from_equity

    eq_x = _equity_curve(monthly_apr=0.06)
    eq_y = _equity_curve(monthly_apr=0.04)
    rx = monthly_returns_from_equity(eq_x, "policy_x")
    ry = monthly_returns_from_equity(eq_y, "policy_y")

    assert rx.name == "policy_x"
    assert ry.name == "policy_y"
    assert isinstance(rx.index, pd.PeriodIndex)
    assert len(rx) == 4  # Jan-Apr
    assert len(ry) == 4
    # Higher-APR series must have a higher mean monthly return.
    assert rx.mean() > ry.mean()


def test_bootstrap_paired_sharpe_pointwise():
    """When policy_a strictly dominates policy_b, point delta-Sharpe > 0
    and the 95% CI contains the point estimate."""
    from backtest.bootstrap_paired_sharpe import (
        monthly_returns_from_equity,
        paired_monthly_sharpe_bootstrap,
    )

    ra = monthly_returns_from_equity(_equity_curve(monthly_apr=0.08), "policy_a")
    rb = monthly_returns_from_equity(_equity_curve(monthly_apr=0.04), "policy_b")
    res = paired_monthly_sharpe_bootstrap(
        ra, rb, n_resamples=1000, seed=42, name="H_dummy",
    )

    assert res.name == "H_dummy"
    assert res.policy_a == "policy_a"
    assert res.policy_b == "policy_b"
    assert res.delta_sharpe_point > 0.0
    assert res.n_bootstrap == 1000
    assert res.n_months == 4
    assert res.ci_low_95 <= res.delta_sharpe_point <= res.ci_high_95


def test_bootstrap_reproducible_with_seed():
    """Same seed -> identical CI bounds (np.random.default_rng contract)."""
    from backtest.bootstrap_paired_sharpe import (
        monthly_returns_from_equity,
        paired_monthly_sharpe_bootstrap,
    )

    ra = monthly_returns_from_equity(_equity_curve(monthly_apr=0.05), "a")
    rb = monthly_returns_from_equity(_equity_curve(monthly_apr=0.045), "b")
    r1 = paired_monthly_sharpe_bootstrap(ra, rb, n_resamples=500, seed=7, name="H")
    r2 = paired_monthly_sharpe_bootstrap(ra, rb, n_resamples=500, seed=7, name="H")
    assert r1.ci_low_95 == r2.ci_low_95
    assert r1.ci_high_95 == r2.ci_high_95
    assert r1.nominal_p == r2.nominal_p


def test_bootstrap_rejects_unnamed_series():
    """A series without .name set is a programming error (we can't
    label the result), and must raise KeyError before any sampling."""
    from backtest.bootstrap_paired_sharpe import (
        monthly_returns_from_equity,
        paired_monthly_sharpe_bootstrap,
    )

    ra = monthly_returns_from_equity(_equity_curve(monthly_apr=0.05), "a")
    rb_unnamed = monthly_returns_from_equity(_equity_curve(monthly_apr=0.045), "b")
    rb_unnamed.name = None
    with pytest.raises(KeyError, match="returns_b"):
        paired_monthly_sharpe_bootstrap(
            ra, rb_unnamed, n_resamples=10, seed=0, name="H",
        )
