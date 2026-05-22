"""T1: Gas-aware threshold decision policy.

Decision rule: switch to the highest-APR protocol iff the expected extra
yield over the EWMA-estimated remaining dwell beats the gas cost.

No ML, no calibration -- 1 hyperparameter (EWMA span, default 1000
blocks ~ 3.3 hours). Reference benchmark for T2/T3 and a sanity check
that the simplest gas-aware logic already beats reactive EMA (Plan B
acceptance gate: T1 net-APY > B4 net-APY by >=10 bp on Sep-Dec 2025).
"""
from __future__ import annotations

import math

from decision.base import BLOCKS_PER_YEAR, Action, BlockState, DecisionPolicy


class T1ThresholdPolicy(DecisionPolicy):
    name = "t1_threshold"

    def __init__(
        self,
        *,
        initial_dwell_blocks: float = 1_000.0,
        ewma_alpha: float = 1.0 / 10.0,  # ~10-observation half-life
    ) -> None:
        self.dwell_blocks: float = float(initial_dwell_blocks)
        self.ewma_alpha = ewma_alpha
        # State for the dwell estimator.
        self._last_winner: str | None = None
        self._last_winner_block: int | None = None

    def _update_dwell(self, state: BlockState) -> None:
        """Pull the dwell EWMA toward the observed inter-crossover block-gap."""
        valid = {p: a for p, a in state.lending_apr.items() if not math.isnan(a)}
        if not valid:
            return
        winner = max(valid, key=valid.get)
        if self._last_winner is None:
            self._last_winner = winner
            self._last_winner_block = state.block_number
            return
        if winner != self._last_winner:
            assert self._last_winner_block is not None
            gap = state.block_number - self._last_winner_block
            self.dwell_blocks = (
                self.ewma_alpha * gap + (1 - self.ewma_alpha) * self.dwell_blocks
            )
            self._last_winner = winner
            self._last_winner_block = state.block_number

    def decide(self, state: BlockState) -> Action:
        self._update_dwell(state)

        valid = {p: a for p, a in state.lending_apr.items() if not math.isnan(a)}
        if not valid:
            return Action(kind="hold", target_protocol=None, rationale="no APR data")

        best_proto = max(valid, key=valid.get)
        best_apr = valid[best_proto]

        # Cold start: no current allocation -> just pick the best.
        if state.current_protocol is None:
            return Action(
                kind="switch",
                target_protocol=best_proto,
                rationale=f"cold start: best APR {best_apr:.4f}",
            )

        if best_proto == state.current_protocol:
            return Action(
                kind="hold",
                target_protocol=None,
                rationale=f"already at best ({best_apr:.4f})",
            )

        current_apr = valid.get(state.current_protocol, float("nan"))
        if math.isnan(current_apr):
            # Current protocol no longer has data -- switch defensively.
            return Action(
                kind="switch",
                target_protocol=best_proto,
                rationale="current_protocol APR is NaN",
            )

        spread = best_apr - current_apr  # > 0 by construction
        expected_extra_yield_usd = (
            state.position_usd
            * spread
            * self.dwell_blocks
            / BLOCKS_PER_YEAR
        )
        cost_usd = DecisionPolicy.gas_cost_usd(state)

        if expected_extra_yield_usd > cost_usd:
            return Action(
                kind="switch",
                target_protocol=best_proto,
                rationale=(
                    f"E[yield]={expected_extra_yield_usd:.2f} > gas={cost_usd:.2f} "
                    f"(spread {spread*1e4:.1f}bp, dwell {self.dwell_blocks:.0f}b)"
                ),
            )
        return Action(
            kind="hold",
            target_protocol=None,
            rationale=(
                f"E[yield]={expected_extra_yield_usd:.2f} < gas={cost_usd:.2f}; "
                f"hold {state.current_protocol}"
            ),
        )
