"""Plan D Task 2 - paired-monthly Sharpe bootstrap with 95% CI.

Methodology (AFML S11.4 out-of-sample variance estimation; design-spec
H1 pre-registration):

  1. From each policy's per-block equity curve, resample to month-end
     and take arithmetic monthly returns:
        r_i = equity_end_of_month_i / equity_end_of_month_{i-1} - 1
     (the first month uses starting equity instead of a prior month-end).
  2. For a hypothesis pair (policy_a, policy_b) form the paired monthly
     difference series d_i = r_{a,i} - r_{b,i}.
  3. Bootstrap n_resamples times: draw len(d) PAIRED row-indices with
     replacement (so the (a, b) pairing is preserved -- H1 is a paired
     test, month-i T1 minus month-i B4 controls for any common macro
     shock that hits both policies). For each draw compute the
     annualized Sharpe of the resampled d:
        Sharpe(d) = mean(d) / std(d, ddof=1) * sqrt(12)
  4. CI = percentile [alpha/2, 1-alpha/2] over the bootstrap distribution.
     Nominal one-sided p = fraction of bootstrap draws with Sharpe(d) <= 0.

Pure numpy -- no scipy.stats. Seeded via np.random.default_rng for
reproducibility. The dataclass field names match the spec on lines
89-108 of docs/superpowers/plans/2026-05-24-empirical-study-paper-draft.md
so that Plan D4 (Deflated Sharpe Ratio) can consume them downstream
without a type-drift adapter.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MonthlyReturnsTable:
    """Per-policy monthly arithmetic returns over the test window.

    `table` columns are policy names; the index is a `pd.PeriodIndex`
    of monthly periods (e.g. 2026-01 .. 2026-04 for the Jan-Apr test
    window). Each cell is `equity_end / equity_start - 1` for that
    policy in that month.
    """

    table: pd.DataFrame


@dataclass(frozen=True)
class BootstrapResult:
    name: str                  # hypothesis label, e.g. "H1a"
    policy_a: str              # treatment, e.g. "t1_threshold"
    policy_b: str              # baseline, e.g. "b4_mcdm_ema"
    delta_sharpe_point: float  # paired-monthly Sharpe of (a-b) on full sample
    ci_low_95: float           # alpha/2 percentile of bootstrap distribution
    ci_high_95: float          # 1-alpha/2 percentile
    nominal_p: float           # one-sided p-value: fraction of draws with delta <= 0
    n_bootstrap: int           # number of resamples (default 1000)
    n_months: int              # length of paired series


# ---------- equity-curve -> monthly returns -----------------------------------

def monthly_returns_from_equity(
    equity_df: pd.DataFrame,
    policy_name: str,
) -> pd.Series:
    """Resample a per-block equity curve to month-end arithmetic returns.

    Parameters
    ----------
    equity_df : pd.DataFrame
        Per-block equity curve. Must have a `block_timestamp` column
        (tz-aware DatetimeIndex-compatible) and a `position_usd` column.
    policy_name : str
        Name to set as the resulting Series' `.name` attribute -- used
        as the column label when these series are concat'd into a
        MonthlyReturnsTable across multiple policies.

    Returns
    -------
    pd.Series
        Monthly arithmetic returns, indexed by `pd.PeriodIndex` (freq='M').
        The first month is computed as `month_end / starting_equity - 1`
        so the test window's 4 months yield 4 returns (not 3).

    Raises
    ------
    ValueError
        If required columns are missing or the curve is empty.
    """
    if "block_timestamp" not in equity_df.columns:
        raise ValueError(
            f"monthly_returns_from_equity({policy_name!r}): "
            f"equity_df missing 'block_timestamp' column "
            f"(have: {list(equity_df.columns)})"
        )
    if "position_usd" not in equity_df.columns:
        raise ValueError(
            f"monthly_returns_from_equity({policy_name!r}): "
            f"equity_df missing 'position_usd' column "
            f"(have: {list(equity_df.columns)})"
        )
    if len(equity_df) == 0:
        raise ValueError(
            f"monthly_returns_from_equity({policy_name!r}): empty equity_df"
        )

    eq = equity_df.copy()
    eq = eq.set_index(pd.DatetimeIndex(eq["block_timestamp"]))
    # Month-end resample, take last equity of each month. 'ME' is the
    # post-pandas-2.2 spelling of 'M' (which is now deprecated).
    monthly_eq = eq["position_usd"].resample("ME").last().dropna()
    if len(monthly_eq) == 0:
        raise ValueError(
            f"monthly_returns_from_equity({policy_name!r}): "
            f"resample to month-end produced no rows"
        )

    monthly_ret = monthly_eq.pct_change().dropna()
    # Prepend the first-month return computed against starting equity --
    # so a 4-month window (Jan-Apr) gives 4 returns, not 3.
    first_start = float(eq["position_usd"].iloc[0])
    first_end = float(monthly_eq.iloc[0])
    first_ret = first_end / first_start - 1.0
    monthly_ret = pd.concat([
        pd.Series([first_ret], index=[monthly_eq.index[0]]),
        monthly_ret,
    ]).sort_index()
    monthly_ret.index = monthly_ret.index.to_period("M")
    monthly_ret.name = policy_name
    return monthly_ret


# ---------- pure-numpy bootstrap ----------------------------------------------

def _annualized_sharpe(d: np.ndarray) -> float:
    """Annualized monthly Sharpe. Returns 0.0 on degenerate input."""
    if len(d) < 2:
        return 0.0
    s = float(np.std(d, ddof=1))
    if s == 0.0:
        return 0.0
    return float(np.mean(d) / s * np.sqrt(12.0))


def paired_monthly_sharpe_bootstrap(
    returns_a: pd.Series,
    returns_b: pd.Series,
    *,
    n_resamples: int = 1000,
    seed: int = 0,
    alpha: float = 0.05,
    name: str = "",
) -> BootstrapResult:
    """Paired-monthly Sharpe bootstrap of (returns_a - returns_b).

    Parameters
    ----------
    returns_a, returns_b : pd.Series
        Monthly returns for the treatment (a) and baseline (b) policies.
        `.name` is read as the policy label for the result; raises
        KeyError if either is missing/empty so the caller learns about
        misuse instead of getting a silently mislabeled result.
    n_resamples : int, default 1000
        Number of bootstrap resamples (the "1000-bootstrap" in the task name).
    seed : int, default 0
        Passed to `np.random.default_rng` for reproducibility.
    alpha : float, default 0.05
        CI level: returns the [alpha/2, 1-alpha/2] percentiles of the
        bootstrap distribution (so 95% CI at alpha=0.05).
    name : str, default ""
        Hypothesis label, e.g. "H1a" -- echoed back in BootstrapResult.name.

    Returns
    -------
    BootstrapResult
        Frozen dataclass with point delta, CI bounds, one-sided nominal
        p (P(bootstrap Sharpe <= 0)), and audit fields.

    Raises
    ------
    KeyError
        If either series has no `.name` set (so the caller passed a
        policy that doesn't exist in the table they built it from).
    ValueError
        If the two series have different lengths.
    """
    policy_a = returns_a.name
    policy_b = returns_b.name
    if policy_a is None or policy_a == "":
        raise KeyError(
            "paired_monthly_sharpe_bootstrap: returns_a has no .name; "
            "set Series.name to the policy label (e.g. 't1_threshold')"
        )
    if policy_b is None or policy_b == "":
        raise KeyError(
            "paired_monthly_sharpe_bootstrap: returns_b has no .name; "
            "set Series.name to the policy label (e.g. 'b4_mcdm_ema')"
        )
    if len(returns_a) != len(returns_b):
        raise ValueError(
            f"paired_monthly_sharpe_bootstrap: returns_a and returns_b "
            f"have different lengths ({len(returns_a)} vs {len(returns_b)}) "
            f"-- pairing is undefined"
        )

    a = returns_a.to_numpy(dtype=np.float64)
    b = returns_b.to_numpy(dtype=np.float64)
    d = a - b
    n = len(d)
    rng = np.random.default_rng(seed)

    boot_sharpes = np.empty(n_resamples, dtype=np.float64)
    for i in range(n_resamples):
        # Pure-numpy paired resample: sample row indices with
        # replacement. Pairing is preserved because we draw from `d`
        # (= a - b) directly rather than resampling a and b separately.
        idx = rng.integers(0, n, size=n)
        boot_sharpes[i] = _annualized_sharpe(d[idx])

    low_q = 100.0 * (alpha / 2.0)
    high_q = 100.0 * (1.0 - alpha / 2.0)
    ci_low = float(np.percentile(boot_sharpes, low_q))
    ci_high = float(np.percentile(boot_sharpes, high_q))
    nominal_p = float(np.mean(boot_sharpes <= 0.0))
    point = _annualized_sharpe(d)

    return BootstrapResult(
        name=name,
        policy_a=str(policy_a),
        policy_b=str(policy_b),
        delta_sharpe_point=point,
        ci_low_95=ci_low,
        ci_high_95=ci_high,
        nominal_p=nominal_p,
        n_bootstrap=n_resamples,
        n_months=n,
    )
