"""T2: Optimal stopping with switching cost on an OU spread.

Decision rule: switch iff the live cross-protocol spread S_t is beyond
a closed-form Bellman boundary S* parameterised by the OU (kappa, theta,
sigma) and the switching cost K (gas):

    S* = theta + sigma * sqrt(K_per_dollar / (kappa * dt))

where K_per_dollar = gas_cost_usd / position_usd. This per-dollar
framing keeps S* in the same units as the realised spread (decimal APR).

Closed-form approximation valid for K small relative to position; full
Riccati ODE available but unnecessary in our regime (K_per_dollar
~ 1e-5 typical, kappa ~ 1e-5 ... 1e-3, sigma ~ 1e-3 ... 1e-2).

When OU calibration says no exploitable mean reversion (kappa <= 1e-6)
the policy defers to the T1 gas-aware threshold rule. If there's no
reversion structure, optimal stopping degenerates to "switch when gas
is covered in expected dwell" -- which IS T1. Cold start
(current_protocol=None) also delegates to T1 because the initial
allocation has no "switching cost" to optimise around.

Rolling recalibration via OUCalibrator.fit every `recalibrate_every`
blocks on the last `window` recorded spreads. This tracks regime drift
(e.g. the 2025-Q3->Q4 Aave-Compound inversion documented in CLAUDE.md).
"""
from __future__ import annotations

import collections
import math

import numpy as np

from decision.base import Action, BlockState, DecisionPolicy
from decision.ou_calibrator import OUCalibrator, OUParams
from decision.t1_threshold import T1ThresholdPolicy


class T2OptimalStoppingPolicy(DecisionPolicy):
    """Closed-form Bellman switching boundary on an OU spread."""

    name = "t2_optimal_stopping"

    # Below this kappa, the OU is effectively a random walk; defer to T1.
    KAPPA_FLOOR = 1e-6

    def __init__(
        self,
        *,
        initial_params: OUParams,
        recalibrate_every: int = 5_000,
        window: int = 5_000,
        fallback_t1: T1ThresholdPolicy | None = None,
    ) -> None:
        self.params = initial_params
        self.recalibrate_every = recalibrate_every
        self.window = window
        # Rolling buffer of recent spreads (top vs runner-up APR per block).
        self._buffer: collections.deque[float] = collections.deque(maxlen=window)
        self._blocks_since_refit = 0
        self._fallback_t1 = fallback_t1 or T1ThresholdPolicy()

    def _record(self, state: BlockState) -> None:
        """Append the cross-protocol spread (top - runner-up) to the buffer."""
        valid = {
            p: a for p, a in state.lending_apr.items() if not math.isnan(a)
        }
        if len(valid) < 2:
            return
        sorted_apr = sorted(valid.values(), reverse=True)
        spread = sorted_apr[0] - sorted_apr[1]
        self._buffer.append(spread)
        self._blocks_since_refit += 1

    def _maybe_refit(self) -> None:
        if (
            self._blocks_since_refit >= self.recalibrate_every
            and len(self._buffer) >= OUCalibrator.MIN_WINDOW
        ):
            try:
                self.params = OUCalibrator.fit(np.array(self._buffer))
            except ValueError:
                # Insufficient data or degenerate; keep prior params.
                pass
            self._blocks_since_refit = 0

    def _switching_boundary(self, state: BlockState) -> float:
        """Closed-form S* = theta + sigma * sqrt(K_per_dollar / (kappa * dt))."""
        if self.params.kappa <= self.KAPPA_FLOOR:
            return float("inf")  # signals "use fallback"
        if state.position_usd <= 0:
            return float("inf")
        cost = DecisionPolicy.gas_cost_usd(state)
        K_per_dollar = cost / state.position_usd
        # dt = 1 block; OU calibration done in per-block units (Plan B Task 3).
        return self.params.theta + self.params.sigma * math.sqrt(
            K_per_dollar / (self.params.kappa * 1.0)
        )

    def decide(self, state: BlockState) -> Action:
        self._record(state)
        self._maybe_refit()

        valid = {
            p: a for p, a in state.lending_apr.items() if not math.isnan(a)
        }
        if len(valid) < 2:
            # Insufficient cross-protocol data; let T1 (which only needs
            # to compare best vs current) decide.
            return self._fallback_t1.decide(state)

        # Cold start: no current allocation -> let T1's "cold start picks
        # highest APR" logic run.
        if state.current_protocol is None:
            return self._fallback_t1.decide(state)

        # If OU is degenerate, defer to T1 (gas-aware threshold rule).
        if self.params.kappa <= self.KAPPA_FLOOR:
            return self._fallback_t1.decide(state)

        sorted_apr = sorted(valid.items(), key=lambda kv: kv[1], reverse=True)
        best_proto, best_apr = sorted_apr[0]
        if best_proto == state.current_protocol:
            return Action(
                kind="hold",
                target_protocol=None,
                rationale="T2: already at best",
            )

        current_apr = valid.get(state.current_protocol, float("nan"))
        if math.isnan(current_apr):
            # Current protocol's APR went missing -- switch defensively.
            return Action(
                kind="switch",
                target_protocol=best_proto,
                rationale="T2: current APR is NaN -> defensive switch",
            )

        spread = best_apr - current_apr  # > 0 since best != current
        boundary = self._switching_boundary(state)
        if spread > boundary:
            return Action(
                kind="switch",
                target_protocol=best_proto,
                rationale=(
                    f"T2 switch: spread {spread*1e4:.1f}bp > S* "
                    f"{boundary*1e4:.1f}bp (kappa={self.params.kappa:.2e}, "
                    f"theta={self.params.theta:.4f}, sigma={self.params.sigma:.4f})"
                ),
            )
        return Action(
            kind="hold",
            target_protocol=None,
            rationale=(
                f"T2 hold: spread {spread*1e4:.1f}bp <= S* "
                f"{boundary*1e4:.1f}bp"
            ),
        )
