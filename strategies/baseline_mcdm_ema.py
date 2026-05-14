"""Baseline C — Reactive MCDM-with-EMA (port of AI Yield Vault, Solovev 2026b).

Direct port of the MCDM scoring logic from the author's prior AI-Managed
ERC-4626 Yield Vault (Solovev 2026b §4.4), pinned for like-for-like
comparison on mainnet historicals.

MCDM formula (Solovev 2026b Eq. 15, PROJECT_2_PLAN.md §2.3):

    Score = 0.40*f_APY + 0.25*f_Risk + 0.20*f_Cost + 0.15*f_Stab

Sub-factors:
    f_APY(r)     = clamp(r / APYmax, 0, 1)           APYmax = 0.20
    f_Risk(u)    = 1 - clamp(u, 0, 1)
    f_Cost(g)    = 1 - clamp(g*G / gmax, 0, 1)       G=200_000 gas, gmax=0.01 ETH
    f_Stab(dTVL) = 1 - clamp(|dTVL| / 0.30, 0, 1)

The CRITICAL difference from PredictiveMCDM is that this baseline uses
EMA-smoothed CURRENT rate, NOT a forecast:

    S_t = 0.30 * r_t + 0.70 * S_{t-1}                (EMA smoothing)
    f_APY(S_t) used in the score                     (no look-ahead)

This is the strawman the project's novelty rests on (Plan §16 RQ1, H1):
predictive MCDM should beat reactive MCDM-with-EMA by Sharpe >= 0.2 over
the test window.

EMA state is maintained per-entity in `self._ema_state`. Initialised on
first observation; updated every step before scoring.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "extras" / "fractal_pr_lending_allocation"))

from base_lending_allocation import (  # noqa: E402
    BaseLendingAllocationParams,
    BaseLendingAllocationStrategy,
)


@dataclass
class MCDMEMAParams(BaseLendingAllocationParams):
    """Defaults from Solovev 2026b § 4.4 (AI Yield Vault constants table)."""

    W_APY: float = 0.40
    W_RISK: float = 0.25
    W_COST: float = 0.20
    W_STAB: float = 0.15

    APYMAX_NORM: float = 0.20         # 20% normalisation cap
    GAS_PER_REBALANCE: int = 200_000
    GAS_MAX_ETH: float = 0.01

    EMA_ALPHA: float = 0.30           # Solovev 2026b Eq. 13


class MCDMEMAStrategy(BaseLendingAllocationStrategy):
    """Reactive 4-factor MCDM with EMA-smoothed rate.

    Inherits cooldown + hysteresis from the base abstraction.

    Required per-step inputs (read from entity.global_state):
        lending_rate   — per-period (we annualise client-side)
        utilization    — [0, 1]
        gas_gwei       — current gas price (filled from external feed)
        delta_tvl_24h  — 24h relative TVL change (computed offline)
    """

    PARAMS_CLS = MCDMEMAParams

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Per-entity EMA state for the lending rate (initialised at first obs)
        self._ema_state: dict[str, Optional[float]] = {}

    # ------------------------------------------------------------------
    # MCDM sub-factor functions (Solovev 2026b § 4.4)
    # ------------------------------------------------------------------

    @staticmethod
    def _f_apy(annual_apr: float, apy_max: float) -> float:
        return float(np.clip(annual_apr / apy_max, 0.0, 1.0))

    @staticmethod
    def _f_risk(utilisation: float) -> float:
        return float(1.0 - np.clip(utilisation, 0.0, 1.0))

    @staticmethod
    def _f_cost(gas_gwei: float, gas_per_rebalance: int, gas_max_eth: float) -> float:
        gas_eth = gas_gwei * 1e-9 * gas_per_rebalance
        return float(1.0 - np.clip(gas_eth / gas_max_eth, 0.0, 1.0))

    @staticmethod
    def _f_stab(delta_tvl: float) -> float:
        return float(1.0 - np.clip(abs(delta_tvl) / 0.30, 0.0, 1.0))

    # ------------------------------------------------------------------
    # EMA + per-protocol criteria
    # ------------------------------------------------------------------

    def _update_ema(self, entity_name: str, per_period_rate: float) -> float:
        """Apply S_t = alpha*r_t + (1-alpha)*S_{t-1}; return smoothed rate."""
        alpha = self._params.EMA_ALPHA
        prev = self._ema_state.get(entity_name)
        if prev is None:
            new = per_period_rate
        else:
            new = alpha * per_period_rate + (1 - alpha) * prev
        self._ema_state[entity_name] = new
        return new

    def compute_criteria_vector(self, entity_name: str) -> np.ndarray:
        """Return [f_APY, f_Risk, f_Cost, f_Stab] using EMA-smoothed rate."""
        gs = self.get_entity(entity_name).global_state

        rate = float(getattr(gs, "lending_rate", 0.0))
        utilisation = float(getattr(gs, "utilization", 0.0))
        gas_gwei = float(getattr(gs, "gas_gwei", 30.0))      # default 30 gwei
        delta_tvl = float(getattr(gs, "delta_tvl_24h", 0.0))

        smoothed = self._update_ema(entity_name, rate)
        # Convert per-period rate back to annualised APR (matches APYMAX_NORM scale)
        annual = smoothed * 365 * 24

        return np.array([
            self._f_apy(annual, self._params.APYMAX_NORM),
            self._f_risk(utilisation),
            self._f_cost(gas_gwei, self._params.GAS_PER_REBALANCE, self._params.GAS_MAX_ETH),
            self._f_stab(delta_tvl),
        ])

    def aggregate_criteria(self, criteria_matrix: np.ndarray) -> np.ndarray:
        """Simple Additive Weighting (SAW) — convex combination of criteria.

        NOT TOPSIS (which involves distances from ideal/anti-ideal points).
        SAW is the aggregator used in Solovev 2026b Eq. 15 — kept here for
        like-for-like comparison with the prior paper. Future work
        (whitepaper §10) could swap in TOPSIS / PROMETHEE / VIKOR via the
        same `aggregate_criteria` hook.
        """
        weights = np.array([
            self._params.W_APY,
            self._params.W_RISK,
            self._params.W_COST,
            self._params.W_STAB,
        ])
        return criteria_matrix @ weights


__all__ = ["MCDMEMAStrategy", "MCDMEMAParams"]
