"""T3 Cox-hazard-driven DecisionPolicy.

Consumes a T3TrainingArtifact (JSON sidecar from `decision.t3_train`)
and at each block:
  1. Materialises the model feature vector x_t from the BlockState
     (using a per-block mini-application of the F1/F3/F4 builders).
  2. Computes hazard rate lambda_t = baseline_mean_hazard * exp(beta' x_t).
  3. Estimates expected remaining dwell as E[tau] = 1 / lambda_t
     (Weibull / exponential approximation; full survival integration
     is reserved for Plan D where we have a fitted baseline_hazard_).
  4. Switches iff E[tau] * spread > gas_cost / position_usd, identical
     to T1's cost-aware rule but with model-driven dwell instead of
     EWMA dwell.

If the artifact references features the live BlockState can't produce
(e.g. f1_dsr_apr but no DSR feed at runtime), the policy falls back to
the T1 gas-aware threshold rule. This is a safety property -- a missing
feature must never produce a wrong decision.

ONNX export is deferred to the runtime-agent integration (Plan E Task
E1); for backtest replay we use pure numpy since the Cox forward pass
is one MatMul + Exp + reciprocal.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from decision.base import Action, BlockState, DecisionPolicy
from decision.t1_threshold import T1ThresholdPolicy
from decision.t3_train import T3TrainingArtifact


class T3HazardPolicy(DecisionPolicy):
    """Cox-hazard-driven policy. Plugs into EventReplayEngine."""

    name = "t3_hazard"

    def __init__(
        self,
        *,
        artifact: T3TrainingArtifact,
        fallback_t1: T1ThresholdPolicy | None = None,
    ) -> None:
        self.artifact = artifact
        # Cached numpy vector aligned with feature_names for fast dot product.
        self._beta = np.array(
            [
                artifact.coefficients[name]
                for name in artifact.feature_names
            ],
            dtype=np.float64,
        )
        self._fallback = fallback_t1 or T1ThresholdPolicy()

    @classmethod
    def from_json(cls, path: Path | str) -> "T3HazardPolicy":
        return cls(artifact=T3TrainingArtifact.load_json(path))

    # ------------------------------------------------------------ live features

    def _live_feature_vector(self, state: BlockState) -> np.ndarray | None:
        """Build x_t from a single BlockState.

        Returns None when one of the required features can't be
        produced from the live state -- caller then falls back to T1.

        Currently supports:
            f3_spread_max_minus_min  -- max(apr) - min(apr) across protocols
            f3_spread_top2           -- top APR - runner-up APR
            f3_dispersion_std        -- std(apr) across protocols
            f1_dsr_apr               -- requires DSR feed; falls through
            f4_gas_log10             -- log10(max(gas, 1e-3))

        Unknown features in the artifact trigger fallback. This is
        defensive: a future builder might add new features (e.g.
        f1_sdai_proxy_apr) and we don't want T3HazardPolicy to silently
        zero them and produce a misleading decision.
        """
        # All live APR values for the protocols this state knows about,
        # NaN-stripped for safe reductions.
        aprs = np.array(
            [v for v in state.lending_apr.values() if not math.isnan(v)],
            dtype=np.float64,
        )

        x = np.zeros(len(self.artifact.feature_names), dtype=np.float64)
        for i, name in enumerate(self.artifact.feature_names):
            if name == "f3_spread_max_minus_min":
                if len(aprs) < 2:
                    return None
                x[i] = float(np.max(aprs) - np.min(aprs))
            elif name == "f3_spread_top2":
                if len(aprs) < 2:
                    return None
                sorted_aprs = np.sort(aprs)[::-1]
                x[i] = float(sorted_aprs[0] - sorted_aprs[1])
            elif name == "f3_dispersion_std":
                if len(aprs) < 2:
                    return None
                x[i] = float(np.std(aprs))
            elif name == "f4_gas_log10":
                x[i] = float(np.log10(max(state.gas_price_gwei, 1e-3)))
            elif name.startswith("f3_spread_") and "_vs_" in name:
                # Per-pair spread feature: f3_spread_<i>_vs_<j>.
                try:
                    raw = name.removeprefix("f3_spread_")
                    proto_i, proto_j = raw.split("_vs_", 1)
                    if (
                        proto_i in state.lending_apr
                        and proto_j in state.lending_apr
                        and not math.isnan(state.lending_apr[proto_i])
                        and not math.isnan(state.lending_apr[proto_j])
                    ):
                        x[i] = (
                            state.lending_apr[proto_i]
                            - state.lending_apr[proto_j]
                        )
                    else:
                        return None
                except ValueError:
                    return None
            elif name.startswith(("f1_", "f4_")):
                # F1 lead-rate (Maker DSR), F4 related-instruments (USDC
                # peg, gas quantile) — read from BlockState.aux, which the
                # replay engine populates from the per-block panel columns
                # matching these prefixes. If missing or NaN, abort (T1
                # fallback) — safer than silent zero-imputation.
                v = state.aux.get(name)
                if v is None or math.isnan(v):
                    return None
                x[i] = float(v)
            else:
                # Unknown feature: can't materialise, fall back to T1.
                return None
        return x

    # ------------------------------------------------------------ decision rule

    def decide(self, state: BlockState) -> Action:
        # Cold start: no current allocation -> highest-APR cold-start
        # via T1's rule (no switching cost at allocation time).
        if state.current_protocol is None:
            return self._fallback.decide(state)

        x = self._live_feature_vector(state)
        if x is None:
            # Can't compute model hazard; defer to T1.
            return self._fallback.decide(state)

        # lambda = baseline * exp(beta' x), guarded against overflow
        # by clipping the linear combination.
        linear = float(np.dot(self._beta, x))
        linear_clipped = float(np.clip(linear, -50.0, 50.0))
        hazard = self.artifact.baseline_mean_hazard * math.exp(linear_clipped)
        if hazard <= 1e-12:
            # Effectively zero hazard -> infinite dwell -> always profitable
            # to switch into the best protocol. But guard against
            # pathological extrapolation.
            expected_dwell_blocks = 1e12
        else:
            expected_dwell_blocks = 1.0 / hazard

        # Find target = best APR != current_protocol.
        valid = {
            p: a
            for p, a in state.lending_apr.items()
            if not math.isnan(a)
        }
        if len(valid) < 2:
            return self._fallback.decide(state)
        best_proto = max(valid, key=valid.get)
        if best_proto == state.current_protocol:
            return Action(
                kind="hold",
                target_protocol=None,
                rationale=(
                    f"T3 hold: already at best (hazard={hazard:.2e})"
                ),
            )

        spread = valid[best_proto] - valid[state.current_protocol]

        # Expected yield gain over the predicted dwell window:
        #   yield_gain_usd = position_usd * spread * (dwell_blocks / BLOCKS_PER_YEAR)
        # Switch iff this > gas_cost_usd.
        from decision.base import BLOCKS_PER_YEAR

        yield_gain = (
            state.position_usd
            * spread
            * expected_dwell_blocks
            / BLOCKS_PER_YEAR
        )
        gas_cost = DecisionPolicy.gas_cost_usd(state)

        if yield_gain > gas_cost:
            return Action(
                kind="switch",
                target_protocol=best_proto,
                rationale=(
                    f"T3 switch: gain ${yield_gain:.2f} > gas ${gas_cost:.2f} "
                    f"(hazard={hazard:.2e}, E[dwell]={expected_dwell_blocks:.0f} blocks, "
                    f"spread={spread*1e4:.1f}bp)"
                ),
            )
        return Action(
            kind="hold",
            target_protocol=None,
            rationale=(
                f"T3 hold: gain ${yield_gain:.2f} <= gas ${gas_cost:.2f} "
                f"(hazard={hazard:.2e}, E[dwell]={expected_dwell_blocks:.0f}, "
                f"spread={spread*1e4:.1f}bp)"
            ),
        )
