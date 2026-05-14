"""Baseline A — buy-and-hold Aave V3.

Deposit INITIAL_USDC at t=0 into the AAVE entity, never rebalance.
The naive yield benchmark per PROJECT_2_PLAN.md §7 (Baseline A).

We subclass BaseLendingAllocationStrategy with a trivial scoring rule that
always pins the score on AAVE so the abstraction handles deposit + no-op
mechanics, demonstrating the abstraction is honest-to-goodness reusable.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "extras" / "fractal_pr_lending_allocation"))

from base_lending_allocation import (  # noqa: E402
    BaseLendingAllocationParams,
    BaseLendingAllocationStrategy,
)


class BuyAndHoldAaveStrategy(BaseLendingAllocationStrategy):
    """Always pick AAVE; never switch."""

    def compute_criteria_vector(self, entity_name: str) -> np.ndarray:
        # Single criterion: 1.0 for AAVE, 0.0 for everyone else
        return np.array([1.0 if entity_name == "AAVE" else 0.0])

    def aggregate_criteria(self, criteria_matrix: np.ndarray) -> np.ndarray:
        return criteria_matrix[:, 0]  # the single column == the score


__all__ = ["BuyAndHoldAaveStrategy", "BaseLendingAllocationParams"]
