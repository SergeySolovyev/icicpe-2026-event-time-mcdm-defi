"""Tests for T3HazardPolicy -- the Cox-hazard-driven DecisionPolicy.

T3 consumes a T3TrainingArtifact (JSON sidecar from Task C5) and at
each block:
  1. Materialises x_t = the feature vector for the current state
     (using F1/F3/F4 builders applied to a 1-row mini-panel).
  2. Computes hazard lambda_t = baseline_mean_hazard * exp(beta' x_t).
  3. Estimates E[remaining_dwell] = 1 / lambda_t (Weibull approximation).
  4. Switches iff E[dwell] * spread > gas_cost / position.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from decision.base import Action, BlockState, DecisionPolicy
from decision.t3_hazard import T3HazardPolicy
from decision.t3_train import T3TrainingArtifact


def _trivial_artifact() -> T3TrainingArtifact:
    """Coefficients tuned so a positive `f3_spread_max_minus_min`
    yields LOW hazard (long dwell) -- the model says 'spread is wide
    and will persist'. Negative coefficient on f3 ⇒ exp(beta * spread)
    < 1 ⇒ hazard down ⇒ dwell up ⇒ profitable switching window."""
    return T3TrainingArtifact(
        feature_names=["f3_spread_max_minus_min"],
        coefficients={"f3_spread_max_minus_min": -50.0},
        baseline_mean_hazard=0.01,  # per-block flip probability baseline
        c_index=0.62,
        n_train_rows=2000,
        horizon_blocks=500,
        penalizer=0.001,
    )


def _state(*, current=None, aave=0.04, comp=0.05, position=1_000_000.0):
    return BlockState(
        block_number=19_500_000,
        block_timestamp=pd.Timestamp("2025-06-01", tz="UTC"),
        protocols=("aave_v3", "compound_v3"),
        lending_apr={"aave_v3": aave, "compound_v3": comp},
        utilization={"aave_v3": 0.8, "compound_v3": 0.7},
        tvl_usd={"aave_v3": 1e9, "compound_v3": 5e8},
        current_protocol=current,
        position_usd=position,
        gas_price_gwei=25.0,
        eth_price_usd=3500.0,
        gas_used_estimate=200_000,
    )


def test_t3_is_decision_policy_subclass():
    """ABC compliance: T3 plugs into the replay engine like any policy."""
    p = T3HazardPolicy(artifact=_trivial_artifact())
    assert isinstance(p, DecisionPolicy)


def test_t3_has_canonical_name():
    p = T3HazardPolicy(artifact=_trivial_artifact())
    assert p.name == "t3_hazard"


def test_t3_decide_returns_action():
    p = T3HazardPolicy(artifact=_trivial_artifact())
    a = p.decide(_state(current="aave_v3"))
    assert isinstance(a, Action)


def test_t3_cold_start_picks_highest_apr():
    """No current allocation -> immediately go to the best APR (T1 fallback)."""
    p = T3HazardPolicy(artifact=_trivial_artifact())
    a = p.decide(_state(current=None, aave=0.04, comp=0.07))
    assert a.kind == "switch"
    assert a.target_protocol == "compound_v3"


def test_t3_switch_when_dwell_pays_for_gas():
    """With a large spread (5 pp) and persistent-spread coefficient,
    the predicted dwell ~ 1220 blocks ⇒ $23 yield gain > $17.5 gas
    on a $1M position. (At 300 bp the math correctly forces hold --
    that case is exercised by test_t3_hold_when_dwell_too_short_for_gas
    below; the gap surfaces a paper-relevant economic regime.)"""
    artifact = _trivial_artifact()
    p = T3HazardPolicy(artifact=artifact)
    # 5 pp spread (rare crossover event); compound is the better protocol.
    a = p.decide(_state(current="aave_v3", aave=0.04, comp=0.09))
    assert a.kind == "switch"
    assert a.target_protocol == "compound_v3"


def test_t3_hold_when_dwell_too_short_for_gas():
    """With a tiny spread (1 bp), even a long predicted dwell can't
    recover gas cost; the policy must hold."""
    p = T3HazardPolicy(artifact=_trivial_artifact())
    a = p.decide(_state(current="aave_v3", aave=0.04, comp=0.0401))  # 1 bp
    assert a.kind == "hold"


def test_t3_load_from_json_path(tmp_path: Path):
    """Constructor can take a path to a JSON artifact file."""
    artifact = _trivial_artifact()
    sidecar = tmp_path / "t3.json"
    artifact.save_json(sidecar)
    p = T3HazardPolicy.from_json(sidecar)
    # 5 pp spread to clear the gas-cost gate (see _trivial_artifact docstring).
    a = p.decide(_state(current="aave_v3", aave=0.04, comp=0.09))
    assert a.kind == "switch"


def test_t3_decide_is_deterministic():
    """Two consecutive decisions on the same state must return the
    same action -- no internal RNG, no hidden state mutation."""
    p = T3HazardPolicy(artifact=_trivial_artifact())
    s = _state(current="aave_v3", aave=0.04, comp=0.05)
    a1 = p.decide(s)
    a2 = p.decide(s)
    assert a1.kind == a2.kind
    assert a1.target_protocol == a2.target_protocol


def test_t3_handles_missing_features_gracefully():
    """If the artifact references a feature the live BlockState can't
    produce (e.g. f1_dsr_apr but no DSR fetcher hooked up), the policy
    should fall back to T1-style gas-aware threshold."""
    art = T3TrainingArtifact(
        feature_names=["f1_dsr_apr", "f3_spread_max_minus_min"],
        coefficients={"f1_dsr_apr": -5.0, "f3_spread_max_minus_min": -50.0},
        baseline_mean_hazard=0.01,
        c_index=0.62,
        n_train_rows=2000,
        horizon_blocks=500,
        penalizer=0.001,
    )
    p = T3HazardPolicy(artifact=art)
    a = p.decide(_state(current="aave_v3", aave=0.04, comp=0.07))
    # Should not raise; either switch or hold is valid.
    assert isinstance(a, Action)
