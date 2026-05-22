"""B1-B4 baseline policies for the event-time matrix.

B1 AlwaysAavePolicy        -- cold-start switch into aave_v3, then hold forever
B2 AlwaysCompoundPolicy    -- symmetric
B3 GreedySpotPolicy        -- switch every block to highest spot APR (no gas gate)
B4 MCDMEmaPolicy           -- Solovev 2026b 4-factor MCDM with alpha=0.1 EMA
                              + 0.05 score-delta threshold
"""
from __future__ import annotations

import math

from decision.base import Action, BlockState, DecisionPolicy


class _FixedTargetPolicy(DecisionPolicy):
    """Helper: always sit in a fixed protocol."""
    def __init__(self, target: str) -> None:
        self.target = target

    def decide(self, state: BlockState) -> Action:
        if state.current_protocol == self.target:
            return Action(kind="hold", target_protocol=None, rationale="")
        if self.target not in state.protocols:
            return Action(kind="hold", target_protocol=None, rationale="target unavailable")
        return Action(kind="switch", target_protocol=self.target, rationale="fixed")


class AlwaysAavePolicy(_FixedTargetPolicy):
    name = "b1_always_aave"
    def __init__(self) -> None: super().__init__("aave_v3")


class AlwaysCompoundPolicy(_FixedTargetPolicy):
    name = "b2_always_compound"
    def __init__(self) -> None: super().__init__("compound_v3")


class GreedySpotPolicy(DecisionPolicy):
    """Switch every block to highest spot APR, ignore gas (catastrophic churn)."""
    name = "b3_greedy_spot"

    def decide(self, state: BlockState) -> Action:
        valid = {p: a for p, a in state.lending_apr.items() if not math.isnan(a)}
        if not valid:
            return Action(kind="hold", target_protocol=None, rationale="no data")
        best = max(valid, key=valid.get)
        if best == state.current_protocol:
            return Action(kind="hold", target_protocol=None, rationale="")
        # Tie-break: if best's APR equals current's APR exactly, hold.
        if state.current_protocol in valid and valid[best] == valid[state.current_protocol]:
            return Action(kind="hold", target_protocol=None, rationale="tied")
        return Action(kind="switch", target_protocol=best, rationale="greedy")


class MCDMEmaPolicy(DecisionPolicy):
    """Solovev 2026b: 4-factor MCDM (APY 40 / Risk 25 / Cost 20 / Stability 15)
    on alpha=0.1 EMA-smoothed spot APRs + 0.05 score-delta threshold gate."""
    name = "b4_mcdm_ema"

    def __init__(self, *, alpha: float = 0.1, score_threshold: float = 0.05) -> None:
        self.alpha = alpha
        self.score_threshold = score_threshold
        self._ema_apr: dict[str, float] = {}
        self._ema_util: dict[str, float] = {}
        self._ema_tvl: dict[str, float] = {}

    def _update_ema(self, key, current, store):
        if math.isnan(current):
            return store.get(key, float("nan"))
        if key not in store:
            store[key] = current
        else:
            store[key] = self.alpha * current + (1 - self.alpha) * store[key]
        return store[key]

    def decide(self, state: BlockState) -> Action:
        valid = []
        for p in state.protocols:
            apr_ema = self._update_ema(p, state.lending_apr[p], self._ema_apr)
            util_ema = self._update_ema(p, state.utilization[p], self._ema_util)
            tvl_ema = self._update_ema(p, state.tvl_usd[p], self._ema_tvl)
            if not math.isnan(apr_ema):
                valid.append((p, apr_ema, util_ema, tvl_ema))

        if not valid:
            return Action(kind="hold", target_protocol=None, rationale="no data")

        # Normalise per factor over the live set.
        max_apr = max(v[1] for v in valid)
        max_util = max(v[2] for v in valid) or 1.0
        max_tvl = max(v[3] for v in valid) or 1.0
        # Cost factor: gas is the same across protocols (same Ethereum L1),
        # so it's a constant -- contributes nothing to ranking. We keep
        # the weight anyway to mirror Solovev 2026b structure.
        scores = {}
        for p, apr, util, tvl in valid:
            f_apy = apr / max_apr
            f_risk = 1 - util / max_util  # lower util = lower risk
            f_cost = 1.0  # uniform across protocols
            f_stab = tvl / max_tvl
            scores[p] = 0.40 * f_apy + 0.25 * f_risk + 0.20 * f_cost + 0.15 * f_stab

        best = max(scores, key=scores.get)
        if best == state.current_protocol:
            return Action(kind="hold", target_protocol=None, rationale="")
        if state.current_protocol is None:
            return Action(kind="switch", target_protocol=best, rationale="cold start MCDM")
        delta = scores[best] - scores[state.current_protocol]
        if delta > self.score_threshold:
            return Action(
                kind="switch", target_protocol=best,
                rationale=f"MCDM delta {delta:.4f} > {self.score_threshold}",
            )
        return Action(
            kind="hold", target_protocol=None,
            rationale=f"MCDM delta {delta:.4f} <= threshold",
        )
