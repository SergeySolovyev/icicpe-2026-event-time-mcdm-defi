"""Plan D Task 4 - Deflated Sharpe Ratio per Lopez de Prado AFML Ch 14.7.3.

Implements eq. 14.5:

    DSR(SR_hat) = Phi( (SR_hat - SR0) * sqrt(T - 1)
                       / sqrt(1 - gamma * SR_hat + (kappa - 1)/4 * SR_hat^2) )

where:
  * Phi is the standard-normal CDF.
  * SR_hat is the non-annualized observed Sharpe of the
    strategy-minus-baseline differential returns.
  * SR0 = sqrt(2 * log(N)) for N independent trials (eq 14.4, simplified).
    For our N=3 H1 trials this is ~1.482.
  * T is the number of return observations (4 monthly returns for the
    Jan-Apr 2026 test window).
  * gamma is sample skewness (3rd standardized central moment).
  * kappa is NON-excess sample kurtosis (4th standardized central
    moment; 3 for normal). Most libraries return EXCESS kurtosis;
    we compute the raw value here.

Reference: Lopez de Prado, "Advances in Financial Machine Learning"
(2018), Ch 14.7.3, Snippet 14.5 (p. 205), eq. 14.5.

Gate per literature-foundation.md section 4.3 (Marcos' Third Law,
AFML Snippet 14.5, p 205): passes iff DSR > 0.95 -- NOT nominal p<0.05.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DSRResult:
    sr_hat: float              # observed (non-annualized) Sharpe of treatment-minus-baseline
    sr_zero: float             # SR threshold = sqrt(2 * log(N)) for N trials
    n_trials: int              # 3 (H1a, H1b, H1c)
    t: int                     # number of monthly observations
    gamma_3: float             # estimated skewness of returns difference
    gamma_4: float             # estimated kurtosis of returns difference (NOT excess)
    dsr: float                 # P_hat_SR[SR0] -- AFML eq 14.5 output, in [0,1]
    passes: bool               # dsr > 0.95


def sr_zero_from_n_trials(n_trials: int) -> float:
    """SR_0 threshold for N independent trials (AFML eq 14.4 simplified).

    The strict eq 14.4 includes Euler-Mascheroni correction terms; the
    AFML book itself uses sqrt(2 * log(N)) as the leading-order
    high-confidence approximation, which is sufficient at the precision
    of our T=4 monthly Sharpe estimate.
    """
    if n_trials <= 1:
        return 0.0
    return math.sqrt(2.0 * math.log(n_trials))


def _norm_cdf(x: float) -> float:
    """Standard-normal CDF via erf, no scipy."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _sample_moments(rets: np.ndarray) -> tuple[float, float, float, float]:
    """Return (mean, std_ddof1, skew, raw_kurtosis_NOT_excess)."""
    n = len(rets)
    mu = float(np.mean(rets))
    sd = float(np.std(rets, ddof=1)) if n >= 2 else 0.0
    if sd == 0.0 or n < 3:
        return mu, sd, 0.0, 3.0  # normal-like defaults
    centered = rets - mu
    m2 = float(np.mean(centered ** 2))
    m3 = float(np.mean(centered ** 3))
    m4 = float(np.mean(centered ** 4))
    skew = m3 / (m2 ** 1.5) if m2 > 0 else 0.0
    kurt_raw = m4 / (m2 ** 2) if m2 > 0 else 3.0  # 3 for normal
    return mu, sd, skew, kurt_raw


def compute_dsr(
    differential_returns: np.ndarray | list[float] | pd.Series,
    *,
    n_trials: int,
    dsr_gate: float = 0.95,
) -> DSRResult:
    """Compute the Deflated Sharpe Ratio for a series of paired
    differential returns (strategy minus baseline)."""
    arr = np.asarray(differential_returns, dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    t = int(len(arr))
    sr0 = sr_zero_from_n_trials(n_trials)

    if t < 2:
        return DSRResult(
            sr_hat=0.0, sr_zero=sr0, n_trials=n_trials, t=t,
            gamma_3=0.0, gamma_4=3.0, dsr=0.0, passes=False,
        )

    mu, sd, gamma_3, gamma_4 = _sample_moments(arr)
    if sd == 0.0:
        sr_hat = 0.0
    else:
        sr_hat = mu / sd  # non-annualized

    denom_sq = 1.0 - gamma_3 * sr_hat + (gamma_4 - 1.0) / 4.0 * sr_hat ** 2
    if denom_sq <= 0.0:
        # Pathological higher-moment estimate (small sample). Cap to 0.
        return DSRResult(
            sr_hat=sr_hat, sr_zero=sr0, n_trials=n_trials, t=t,
            gamma_3=gamma_3, gamma_4=gamma_4, dsr=0.0, passes=False,
        )
    numer = (sr_hat - sr0) * math.sqrt(t - 1)
    dsr = _norm_cdf(numer / math.sqrt(denom_sq))
    return DSRResult(
        sr_hat=sr_hat, sr_zero=sr0, n_trials=n_trials, t=t,
        gamma_3=gamma_3, gamma_4=gamma_4,
        dsr=float(dsr), passes=bool(dsr > dsr_gate),
    )


def compose_h1_significance(
    bootstrap_df: pd.DataFrame,
    monthly_returns: pd.DataFrame,
    *,
    n_trials: int = 3,
    dsr_gate: float = 0.95,
) -> pd.DataFrame:
    """Join bootstrap CI (D2 output) with DSR (D4 output) into one
    DataFrame ready for results/tables/h1_significance.csv."""
    rows = []
    for _, br in bootstrap_df.iterrows():
        a, b = br["policy_a"], br["policy_b"]
        if a in monthly_returns.columns and b in monthly_returns.columns:
            d = (monthly_returns[a] - monthly_returns[b]).to_numpy(dtype=np.float64)
            d = d[np.isfinite(d)]
            if len(d) >= 2:
                dsr_res = compute_dsr(d, n_trials=n_trials, dsr_gate=dsr_gate)
                dsr_val = dsr_res.dsr
                sr_zero_val = dsr_res.sr_zero
                passes = dsr_res.passes
            else:
                dsr_val = float("nan")
                sr_zero_val = sr_zero_from_n_trials(n_trials)
                passes = False
        else:
            dsr_val = float("nan")
            sr_zero_val = sr_zero_from_n_trials(n_trials)
            passes = False
        rows.append({
            "name": br["name"],
            "policy_a": a, "policy_b": b,
            "delta_sharpe_point": br["delta_sharpe_point"],
            "ci_low_95": br["ci_low_95"],
            "ci_high_95": br["ci_high_95"],
            "nominal_p": br["nominal_p"],
            "dsr": dsr_val,
            "sr_zero": sr_zero_val,
            "passes_dsr": passes,
            "n_bootstrap": br.get("n_bootstrap", 0),
            "n_months": br.get("n_months", 0),
            "note": br.get("note", ""),
        })
    return pd.DataFrame(rows)
