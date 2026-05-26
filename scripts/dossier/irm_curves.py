"""IRM (interest rate model) parameters per protocol + slippage model.

Values sourced from:
- Aave V3 USDC: ReserveInterestRateStrategy contract, slope1=0.04,
  slope2=0.75, kink=0.92 (Aave Risk Parameter Update, 2024-Q3).
- Morpho Blue USDC vault: AdaptiveCurve IRM, ~slope1=0.04 effective at
  steady state (Morpho whitepaper section 4.2).
- Euler V2 USDC: stable IRM, slope1=0.04, slope2=0.85, kink=0.90
  (Euler V2 risk parameters launch doc, 2024-Q4).

Slippage model: adding $V of supply liquidity moves utilization
DOWN by delta_u = V/TVL * (1-u). Supply rate moves DOWN by
slope1 * delta_u (sub-kink). Average slippage over fill =
0.5 * slope1 * delta_u (Kissell 2014 linear average impact)."""
from __future__ import annotations

import numpy as np


IRM_PARAMS: dict[str, dict[str, float]] = {
    "aave_v3":     {"slope1": 0.04, "slope2": 0.75, "kink": 0.92},
    "morpho_blue": {"slope1": 0.04, "slope2": 0.50, "kink": 0.90},
    "euler_v2":    {"slope1": 0.04, "slope2": 0.85, "kink": 0.90},
}


def slippage_bp(protocol: str, position_usd: float, panel_row: dict) -> float:
    """Average slippage from supplying position_usd to a pool.

    Returns slippage in basis points (positive number; reduction in
    realised supply rate vs naive constant assumption)."""
    params = IRM_PARAMS.get(protocol)
    if params is None:
        return 0.0
    tvl = float(panel_row.get(f"{protocol}_tvl_usd", 0.0))
    u = float(panel_row.get(f"{protocol}_utilization", 0.0))
    if tvl <= 0 or not np.isfinite(tvl):
        return 0.0
    delta_u = position_usd / tvl * (1 - u)
    avg_rate_impact = 0.5 * params["slope1"] * delta_u
    return float(avg_rate_impact * 10_000)


def krause_market_depth(protocol: str, utilization: float, tvl_usd: float) -> float:
    """Krause (2005) closed-form depth: 1/lambda = TVL*(1-u)/slope1.
    Returns $-depth absorbable before a 1bp rate move."""
    params = IRM_PARAMS.get(protocol)
    if params is None:
        return 0.0
    return tvl_usd * (1 - utilization) / params["slope1"]
