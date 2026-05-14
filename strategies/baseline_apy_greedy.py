"""Baseline B — APY-only greedy.

At every hour, allocate 100% to whichever protocol has higher spot APY.
NO hysteresis, NO cooldown — upper bound for reactive switching.

Disables both gates by setting HYSTERESIS_THRESHOLD=0 and COOLDOWN_HOURS=0
in params. The base class respects those defaults and turns into a pure
argmax-on-current-APY allocator.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "extras" / "fractal_pr_lending_allocation"))

from base_lending_allocation import (  # noqa: E402
    BaseLendingAllocationParams,
    BaseLendingAllocationStrategy,
)


@dataclass
class APYGreedyParams(BaseLendingAllocationParams):
    # Override defaults: no hysteresis, no cooldown.
    HYSTERESIS_THRESHOLD: float = 0.0
    COOLDOWN_HOURS: float = 0.0


class APYGreedyStrategy(BaseLendingAllocationStrategy):
    """Pick the entity with highest current lending_rate every step."""

    # The base class concretized the TypeVar at BaseLendingAllocationParams,
    # so subclasses cannot re-parameterize; declare PARAMS_CLS explicitly
    # (explicit override wins per BaseStrategy.__init_subclass__ line 75-76).
    PARAMS_CLS = APYGreedyParams

    def compute_criteria_vector(self, entity_name: str) -> np.ndarray:
        gs = self.get_entity(entity_name).global_state
        # Per-period rate; gateway loader convention. Greedy doesn't care
        # about units as long as both protocols share them.
        return np.array([float(getattr(gs, "lending_rate", 0.0))])

    def aggregate_criteria(self, criteria_matrix: np.ndarray) -> np.ndarray:
        return criteria_matrix[:, 0]


__all__ = ["APYGreedyStrategy", "APYGreedyParams"]
