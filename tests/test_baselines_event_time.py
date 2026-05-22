"""Tests for B1-B4 baselines."""
import math

import pandas as pd
import pytest

from backtest.run_baselines_event_time import (
    AlwaysAavePolicy, AlwaysCompoundPolicy, GreedySpotPolicy, MCDMEmaPolicy,
)
from decision.base import BlockState


def _state(*, current=None, aave=0.04, comp=0.05, block=100):
    return BlockState(
        block_number=block,
        block_timestamp=pd.Timestamp("2025-06-01", tz="UTC"),
        protocols=("aave_v3", "compound_v3"),
        lending_apr={"aave_v3": aave, "compound_v3": comp},
        utilization={"aave_v3": 0.8, "compound_v3": 0.7},
        tvl_usd={"aave_v3": 1e9, "compound_v3": 5e8},
        current_protocol=current,
        position_usd=1_000_000.0,
        gas_price_gwei=25.0, eth_price_usd=3500.0, gas_used_estimate=200_000,
    )


def test_b1_always_aave_switches_in_then_holds():
    p = AlwaysAavePolicy()
    a1 = p.decide(_state(current=None))
    assert a1.kind == "switch" and a1.target_protocol == "aave_v3"
    a2 = p.decide(_state(current="aave_v3"))
    assert a2.kind == "hold"
    # Even when Compound is way higher, B1 stays.
    a3 = p.decide(_state(current="aave_v3", aave=0.01, comp=0.10))
    assert a3.kind == "hold"


def test_b2_always_compound_symmetric():
    p = AlwaysCompoundPolicy()
    assert p.decide(_state(current=None)).target_protocol == "compound_v3"
    a = p.decide(_state(current="compound_v3", aave=0.10, comp=0.01))
    assert a.kind == "hold"


def test_b3_greedy_spot_chases_every_change():
    p = GreedySpotPolicy()
    # Aave higher -> switch in.
    assert p.decide(_state(current=None, aave=0.05, comp=0.04)).target_protocol == "aave_v3"
    # Now sit in Aave; Compound rises -> switch out.
    assert p.decide(_state(current="aave_v3", aave=0.04, comp=0.05)).target_protocol == "compound_v3"
    # No tie-break: equal APRs -> hold.
    a = p.decide(_state(current="aave_v3", aave=0.04, comp=0.04))
    assert a.kind == "hold"


def test_b4_mcdm_ema_smooths_and_threshold_gates():
    """MCDM with alpha=0.1 EMA + 0.05 score-delta -> no whipsaw on
    1-block spike; persistent ADEQUATE advantage eventually switches.

    Calibration note (from the Plan B Task 6 retrospective): at the
    realistic Aave-vs-Compound TVL ratio in `_state` (Aave 2x Compound),
    the f_stab factor (15% weight) contributes a +0.075 stability bonus
    to Aave that takes ~3 percentage points of APY-advantage to
    overcome. A 1 percentage point spike (0.04 -> 0.05) is INSIDE the
    threshold and the policy correctly holds. A 4 percentage point
    persistent advantage (0.04 -> 0.08) crosses cleanly.

    This test pin documents an empirical property of the published 2026b
    methodology: the stability factor structurally suppresses moderate
    APY edges. A paper-relevant finding for Plan D Section V.
    """
    p = MCDMEmaPolicy()
    # Warm up at parity for a while so the EMAs converge.
    for blk in range(100, 200):
        p.decide(_state(current="aave_v3", aave=0.04, comp=0.04, block=blk))
    # 1-block spike below the structural threshold -> EMA absorbs, hold.
    a = p.decide(_state(current="aave_v3", aave=0.04, comp=0.05, block=200))
    assert a.kind == "hold"
    # Persistent 4pp advantage for 150 blocks -> eventually crosses the
    # 0.05 score-delta threshold even after stability bonus drag.
    for blk in range(201, 350):
        p.decide(_state(current="aave_v3", aave=0.04, comp=0.08, block=blk))
    a = p.decide(_state(current="aave_v3", aave=0.04, comp=0.08, block=350))
    assert a.kind == "switch"
    assert a.target_protocol == "compound_v3"
