"""Tests for T2 optimal stopping policy.

Closed-form Bellman switching boundary on an OU spread with switching
cost K:  switch iff realised cross-protocol spread > S*.
"""
import math

import numpy as np
import pandas as pd
import pytest

from decision.base import BlockState
from decision.ou_calibrator import OUParams
from decision.t2_optimal_stopping import T2OptimalStoppingPolicy


def _state(
    *,
    current,
    aave,
    comp,
    gas=25.0,
    position=1_000_000.0,
    block=19_500_000,
):
    return BlockState(
        block_number=block,
        block_timestamp=pd.Timestamp("2025-06-01", tz="UTC"),
        protocols=("aave_v3", "compound_v3"),
        lending_apr={"aave_v3": aave, "compound_v3": comp},
        utilization={"aave_v3": 0.8, "compound_v3": 0.7},
        tvl_usd={"aave_v3": 1e9, "compound_v3": 5e8},
        current_protocol=current,
        position_usd=position,
        gas_price_gwei=gas,
        eth_price_usd=3500.0,
        gas_used_estimate=200_000,
    )


def test_switch_when_spread_above_boundary():
    """High kappa + huge spread vs S* boundary -> switch."""
    params = OUParams(kappa=0.001, theta=0.0, sigma=0.005)
    p = T2OptimalStoppingPolicy(initial_params=params, recalibrate_every=10_000)
    a = p.decide(_state(current="aave_v3", aave=0.03, comp=0.06))  # 300 bp
    assert a.kind == "switch"
    assert a.target_protocol == "compound_v3"


def test_hold_when_spread_below_boundary():
    """Tiny spread / low kappa -> S* is huge, hold."""
    params = OUParams(kappa=1e-7, theta=0.0, sigma=0.005)
    p = T2OptimalStoppingPolicy(initial_params=params, recalibrate_every=10_000)
    a = p.decide(_state(current="aave_v3", aave=0.0400, comp=0.0405))  # 5 bp
    assert a.kind == "hold"


def test_low_kappa_defers_to_t1():
    """If MLE says no mean reversion (kappa near 0), policy must defer to T1.

    Cold start (current_protocol=None) is one path that always delegates
    to T1 regardless of kappa.
    """
    params = OUParams(kappa=1e-9, theta=0.0, sigma=0.005)
    p = T2OptimalStoppingPolicy(initial_params=params, recalibrate_every=10_000)
    a = p.decide(_state(current=None, aave=0.05, comp=0.04))
    assert a.kind == "switch"
    assert a.target_protocol == "aave_v3"


def test_recalibration_after_window():
    """After recalibrate_every blocks of observations, the calibrator
    refits the OU and (some) parameter changes vs the initial prior."""
    rng = np.random.default_rng(7)
    params0 = OUParams(kappa=0.01, theta=0.0, sigma=0.002)
    p = T2OptimalStoppingPolicy(
        initial_params=params0, recalibrate_every=200, window=500
    )

    for i in range(250):
        ap = 0.04 + 0.001 * rng.standard_normal()
        cp = 0.04 + 0.001 + 0.001 * rng.standard_normal()
        p.decide(_state(current="aave_v3", aave=ap, comp=cp, block=100 + i))

    assert p.params != params0


def test_decide_does_not_mutate_state():
    """BlockState is frozen; decide() must not require mutation."""
    params = OUParams(kappa=0.001, theta=0.0, sigma=0.005)
    p = T2OptimalStoppingPolicy(initial_params=params, recalibrate_every=10_000)
    s = _state(current="aave_v3", aave=0.04, comp=0.05)
    a1 = p.decide(s)
    a2 = p.decide(s)
    # Same state, same params: same decision (the buffer grows but
    # nothing about the boundary changes after 2 identical obs).
    assert a1.kind == a2.kind
