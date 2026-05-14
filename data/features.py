"""Feature engineering: kink subtraction + rate residual + cross-protocol spread.

The kink function `f_kink` reproduces the protocol-known piecewise-linear
supply-rate curve so the forecaster only has to learn the *residual*
`epsilon = r - f_kink(u, kink_params)`, freeing model capacity for genuinely
stochastic variation.

Per PROJECT_2_PLAN.md S2.2 (Branch A target) and DEEP_RESEARCH.md S VI.B.

Reference for the protocol rate formulas:
- Aave V3:        https://docs.aave.com/risk/liquidity-risk/borrow-interest-rate
- Compound V3:    https://docs.compound.finance/interest-rates/
- Both protocols specify the same general kink shape; the parameters differ
  per market and may be governed-updated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Sequence

import numpy as np
import pandas as pd

Protocol = Literal["aave", "compound"]


# ---------------------------------------------------------------------------
# Kink parameter dataclasses (one per protocol; values typically from on-chain config)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AaveKinkParams:
    """Aave V3 interest-rate strategy parameters for a single reserve.

    Borrow rate r_b(u):
        u <= U_opt:   base + slope1 * (u / U_opt)
        u >  U_opt:   base + slope1 + slope2 * (u - U_opt) / (1 - U_opt)

    Supply rate r_s(u) = u * r_b(u) * (1 - reserve_factor)

    All rates are *annualized continuously compounded* (matching the
    project's data-pipeline convention).
    """
    base_variable_borrow_rate: float       # baseVariableBorrowRate
    slope1: float                          # variableRateSlope1
    slope2: float                          # variableRateSlope2
    optimal_usage_ratio: float             # OPTIMAL_USAGE_RATIO in [0, 1]
    reserve_factor: float                  # reserveFactor in [0, 1]


@dataclass(frozen=True)
class CompoundKinkParams:
    """Compound V3 (Comet) supply-side interest-rate parameters for a market.

    Compound V3 specifies supply rate as a *direct* function of utilization
    (NOT derived from borrow rate as in Aave):

        u <= supplyKink:
            r_s = base_s + slopeLow_s * u
        u >  supplyKink:
            r_s = base_s + slopeLow_s * supplyKink + slopeHigh_s * (u - supplyKink)

    All rates annualized continuously compounded.
    """
    supply_kink: float                     # supplyKink in [0, 1]
    supply_per_second_base: float          # supplyPerSecondInterestRateBase (annualized)
    supply_per_second_slope_low: float     # supplyPerSecondInterestRateSlopeLow (annualized)
    supply_per_second_slope_high: float    # supplyPerSecondInterestRateSlopeHigh (annualized)


KinkParams = AaveKinkParams | CompoundKinkParams


# ---------------------------------------------------------------------------
# Kink functions
# ---------------------------------------------------------------------------

def _aave_supply_rate(u: np.ndarray | float, p: AaveKinkParams) -> np.ndarray | float:
    """Aave V3 supply rate from utilization."""
    u_arr = np.asarray(u, dtype=np.float64)

    # Borrow rate at utilization u
    below = p.base_variable_borrow_rate + p.slope1 * (u_arr / p.optimal_usage_ratio)
    above = (
        p.base_variable_borrow_rate
        + p.slope1
        + p.slope2 * (u_arr - p.optimal_usage_ratio) / (1.0 - p.optimal_usage_ratio)
    )
    borrow = np.where(u_arr <= p.optimal_usage_ratio, below, above)

    supply = u_arr * borrow * (1.0 - p.reserve_factor)
    return supply.item() if np.isscalar(u) else supply


def _compound_supply_rate(u: np.ndarray | float, p: CompoundKinkParams) -> np.ndarray | float:
    """Compound V3 supply rate from utilization."""
    u_arr = np.asarray(u, dtype=np.float64)

    below = p.supply_per_second_base + p.supply_per_second_slope_low * u_arr
    above = (
        p.supply_per_second_base
        + p.supply_per_second_slope_low * p.supply_kink
        + p.supply_per_second_slope_high * (u_arr - p.supply_kink)
    )
    supply = np.where(u_arr <= p.supply_kink, below, above)
    return supply.item() if np.isscalar(u) else supply


def f_kink(u: np.ndarray | float, params: KinkParams) -> np.ndarray | float:
    """Deterministic protocol supply-rate curve r_s(u; params).

    Routes to the right protocol-specific formula based on the params type.
    Vectorized: u can be scalar or 1-D / 2-D array.

    Returns the same shape as input.
    """
    if isinstance(params, AaveKinkParams):
        return _aave_supply_rate(u, params)
    if isinstance(params, CompoundKinkParams):
        return _compound_supply_rate(u, params)
    raise TypeError(f"Unknown kink params type: {type(params)}")


# ---------------------------------------------------------------------------
# Residuals and cross-protocol spread
# ---------------------------------------------------------------------------

def rate_residual(
    r: np.ndarray | pd.Series,
    u: np.ndarray | pd.Series,
    params: KinkParams,
) -> np.ndarray:
    """Compute epsilon_t = r_t - f_kink(u_t; params).

    This is the Branch A target for the dual-branch forecaster — the part of
    the rate NOT explained by the deterministic protocol function.
    """
    r_arr = np.asarray(r, dtype=np.float64)
    u_arr = np.asarray(u, dtype=np.float64)
    return r_arr - np.asarray(f_kink(u_arr, params), dtype=np.float64)


def cross_protocol_spread(
    r_a: np.ndarray | pd.Series,
    r_c: np.ndarray | pd.Series,
    u_a: np.ndarray | pd.Series,
    u_c: np.ndarray | pd.Series,
    params_a: AaveKinkParams,
    params_c: CompoundKinkParams,
) -> dict[str, np.ndarray]:
    """Compute the four cross-protocol features the forecaster sees.

    Returns:
        rate_spread       = r_a - r_c
        residual_spread   = epsilon_a - epsilon_c
        kink_spread       = f_kink_a(u_a) - f_kink_c(u_c)
        util_spread       = u_a - u_c
    """
    eps_a = rate_residual(r_a, u_a, params_a)
    eps_c = rate_residual(r_c, u_c, params_c)
    return {
        "rate_spread":     np.asarray(r_a) - np.asarray(r_c),
        "residual_spread": eps_a - eps_c,
        "kink_spread":     np.asarray(f_kink(np.asarray(u_a), params_a))
                           - np.asarray(f_kink(np.asarray(u_c), params_c)),
        "util_spread":     np.asarray(u_a) - np.asarray(u_c),
    }


# ---------------------------------------------------------------------------
# Feature extraction for the strategy buffer
# ---------------------------------------------------------------------------

def extract_features(
    df: pd.DataFrame,
    params_a: AaveKinkParams,
    params_c: CompoundKinkParams,
) -> pd.DataFrame:
    """Build the full feature panel for the forecaster from joined hourly data.

    Input columns (UTC hourly index):
        r_aave, r_compound, u_aave, u_compound,
        tvl_aave, tvl_compound, gas_gwei, eth_usd

    Output columns: above + computed features:
        eps_aave, eps_compound,
        rate_spread, residual_spread, kink_spread, util_spread,
        dTVL_aave_24h, dTVL_compound_24h,
        tod_sin, tod_cos                    (time-of-day cyclical encoding)
    """
    out = df.copy()

    # Per-protocol residuals
    out["eps_aave"] = rate_residual(df["r_aave"], df["u_aave"], params_a)
    out["eps_compound"] = rate_residual(df["r_compound"], df["u_compound"], params_c)

    # Cross-protocol spreads
    spreads = cross_protocol_spread(
        df["r_aave"], df["r_compound"], df["u_aave"], df["u_compound"], params_a, params_c
    )
    for name, arr in spreads.items():
        out[name] = arr

    # TVL momentum (24h relative change)
    out["dTVL_aave_24h"] = df["tvl_aave"].pct_change(24)
    out["dTVL_compound_24h"] = df["tvl_compound"].pct_change(24)

    # Time-of-day cyclical encoding (the funding-rate forecasting baseline does this)
    hour = df.index.hour.values
    out["tod_sin"] = np.sin(2 * np.pi * hour / 24)
    out["tod_cos"] = np.cos(2 * np.pi * hour / 24)

    return out


# ---------------------------------------------------------------------------
# Sanity check (run on import in debug mode)
# ---------------------------------------------------------------------------

def _selftest() -> None:
    """Quick sanity test: known-rate values from Aave V3 USDC docs.

    As of 2024-Q4, Aave V3 USDC mainnet had approximately:
        base = 0, slope1 = 5%, slope2 = 60%, U_opt = 0.92, reserve = 0.10
    At u = 0.50:  r_b = 5% * 0.50/0.92 = 2.72%
                  r_s = 0.50 * 2.72% * 0.90 = 1.22%

    Tolerance 0.01% absolute.
    """
    p = AaveKinkParams(
        base_variable_borrow_rate=0.0,
        slope1=0.05,
        slope2=0.60,
        optimal_usage_ratio=0.92,
        reserve_factor=0.10,
    )
    r_s = f_kink(0.50, p)
    expected = 0.50 * (0.05 * 0.50 / 0.92) * 0.90
    assert abs(r_s - expected) < 1e-6, f"f_kink Aave: {r_s} vs {expected}"

    # Test above kink
    r_s_above = f_kink(0.95, p)
    expected_borrow_above = 0.05 + 0.60 * (0.95 - 0.92) / (1 - 0.92)
    expected_above = 0.95 * expected_borrow_above * 0.90
    assert abs(r_s_above - expected_above) < 1e-6, f"f_kink Aave above kink: {r_s_above}"

    # Test array input
    u_arr = np.array([0.10, 0.50, 0.92, 0.95])
    r_arr = f_kink(u_arr, p)
    assert r_arr.shape == (4,)
    assert np.all(r_arr >= 0)
    assert r_arr[2] < r_arr[3]  # rate jumps after kink


if __name__ == "__main__":
    _selftest()
    print("f_kink self-test passed.")
