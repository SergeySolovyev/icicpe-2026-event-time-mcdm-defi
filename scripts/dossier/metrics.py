"""Pure metric functions for the Institutional Dossier.

All functions accept pd.Series of returns (or equity) and return
scalar floats. No I/O, no logging, no side effects."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def daily_from_block_equity(eq_block: pd.Series) -> pd.Series:
    """Resample a per-block equity series (tz-aware DatetimeIndex) to
    daily last-of-day equity. Convention: Lo (2002) recommends daily
    aggregation for Sharpe inference on series shorter than ~3 years."""
    if not isinstance(eq_block.index, pd.DatetimeIndex):
        raise ValueError("eq_block must have a DatetimeIndex")
    return eq_block.resample("D").last().dropna()


def _daily_returns(eq_daily: pd.Series) -> pd.Series:
    """Daily arithmetic returns. First day = eq[1]/eq[0]-1."""
    return eq_daily.pct_change().dropna()


def sharpe(returns: pd.Series, periods_per_year: int = 365) -> float:
    """Annualized Sharpe = mean(r)/std(r) * sqrt(periods_per_year).
    Uses sample std with ddof=1 per Lo (2002) convention."""
    if len(returns) < 2:
        return 0.0
    sd = returns.std(ddof=1)
    if sd == 0:
        return 0.0
    return float(returns.mean() / sd * np.sqrt(periods_per_year))


def sortino(returns: pd.Series, periods_per_year: int = 365,
            target: float = 0.0) -> float:
    """Sortino = mean(r-target) / downside_std * sqrt(periods_per_year).
    Downside std considers only periods where r < target."""
    if len(returns) < 2:
        return 0.0
    downside = returns[returns < target] - target
    if len(downside) == 0:
        return float("inf")
    dsd = np.sqrt((downside ** 2).mean())  # MSE-style downside dev
    if dsd == 0:
        return 0.0
    return float((returns.mean() - target) / dsd * np.sqrt(periods_per_year))


def max_drawdown(equity: pd.Series) -> float:
    """Max drawdown as negative fraction (e.g. -0.20 for 20% drawdown).
    Defined as min over time of (equity[t] - running_max[t]) / running_max[t]."""
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    return float(drawdown.min())


def _delta_to_periods(delta) -> int:
    """Convert an index-delta to integer periods. Handles Timedelta
    (DatetimeIndex) and plain int (RangeIndex)."""
    if hasattr(delta, "days"):
        return int(delta.days)
    return int(delta)


def max_drawdown_duration(equity: pd.Series) -> int:
    """Periods between the peak before the max drawdown and the recovery
    point (or end of series if no recovery). Returns days for a
    DatetimeIndex, integer steps for a RangeIndex."""
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    trough_idx = drawdown.idxmin()
    peak_value = running_max.loc[trough_idx]
    pre_trough = equity.loc[:trough_idx]
    peak_idx = pre_trough[pre_trough >= peak_value].index[0]
    post_trough = equity.loc[trough_idx:]
    rec = post_trough[post_trough >= peak_value]
    if len(rec) == 0:
        return _delta_to_periods(equity.index[-1] - peak_idx)
    return _delta_to_periods(rec.index[0] - peak_idx)


def time_to_recovery(equity: pd.Series) -> float:
    """Periods from MaxDD trough to recovery; inf if no recovery."""
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    trough_idx = drawdown.idxmin()
    peak_value = running_max.loc[trough_idx]
    post_trough = equity.loc[trough_idx:]
    rec = post_trough[post_trough >= peak_value]
    if len(rec) == 0:
        return float("inf")
    return float(_delta_to_periods(rec.index[0] - trough_idx))


def calmar(apy: float, max_dd: float) -> float:
    """Calmar = APY / |MaxDD|. Both inputs as decimal fractions.
    Returns inf if max_dd == 0."""
    if max_dd == 0:
        return float("inf")
    return apy / abs(max_dd)


def information_ratio(strat: pd.Series, bench: pd.Series,
                      periods_per_year: int = 365) -> float:
    """IR = mean(r_strat - r_bench) / std(r_strat - r_bench) * sqrt(ppy).
    Inputs are per-period returns of equal length, aligned by index."""
    d = strat - bench
    if len(d) < 2:
        return 0.0
    sd = d.std(ddof=1)
    if sd == 0:
        return 0.0
    return float(d.mean() / sd * np.sqrt(periods_per_year))


def cvar(returns: pd.Series, alpha: float = 0.05) -> float:
    """Conditional Value-at-Risk at alpha-tail. Returns the mean of
    the alpha-fraction worst returns. For alpha=0.05 this is CVaR_95."""
    var = np.quantile(returns, alpha)
    tail = returns[returns <= var]
    if len(tail) == 0:
        return float(var)
    return float(tail.mean())


def skew_kurt(returns: pd.Series) -> tuple[float, float]:
    """Sample skewness + excess kurtosis (Fisher convention, kurt=0 for normal)."""
    return float(stats.skew(returns)), float(stats.kurtosis(returns))
