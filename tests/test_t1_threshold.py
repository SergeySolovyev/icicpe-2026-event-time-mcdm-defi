"""Tests for T1 gas-aware threshold policy."""
import math

import pandas as pd
import pytest

from decision.base import Action, BlockState
from decision.t1_threshold import T1ThresholdPolicy


def _state(*, current, aave_apr, comp_apr, gas_gwei=25.0,
           position_usd=1_000_000.0, block_number=19_500_000):
    return BlockState(
        block_number=block_number,
        block_timestamp=pd.Timestamp("2025-06-01", tz="UTC"),
        protocols=("aave_v3", "compound_v3"),
        lending_apr={"aave_v3": aave_apr, "compound_v3": comp_apr},
        utilization={"aave_v3": 0.8, "compound_v3": 0.7},
        tvl_usd={"aave_v3": 1e9, "compound_v3": 5e8},
        current_protocol=current,
        position_usd=position_usd,
        gas_price_gwei=gas_gwei,
        eth_price_usd=3500.0,
        gas_used_estimate=200_000,
    )


def test_hold_when_already_at_best():
    """At Aave with 4%, Compound 3%: T1 should hold."""
    p = T1ThresholdPolicy(initial_dwell_blocks=10_000)
    a = p.decide(_state(current="aave_v3", aave_apr=0.04, comp_apr=0.03))
    assert a.kind == "hold"


def test_switch_when_spread_easily_clears_gas():
    """200 bp spread, 100 000 blocks dwell, $1 M position: huge edge."""
    p = T1ThresholdPolicy(initial_dwell_blocks=100_000)
    a = p.decide(_state(current="aave_v3", aave_apr=0.02, comp_apr=0.04))
    assert a.kind == "switch"
    assert a.target_protocol == "compound_v3"


def test_hold_when_spread_too_thin_for_gas():
    """1 bp spread, 1 000 blocks dwell: nowhere near worth $17.5 gas."""
    p = T1ThresholdPolicy(initial_dwell_blocks=1_000)
    a = p.decide(_state(current="aave_v3", aave_apr=0.0400, comp_apr=0.0401))
    assert a.kind == "hold"


def test_initial_allocation_picks_highest_apr_when_no_current():
    """current_protocol=None: pick the highest-APR protocol regardless of gas."""
    p = T1ThresholdPolicy(initial_dwell_blocks=10_000)
    a = p.decide(_state(current=None, aave_apr=0.05, comp_apr=0.04))
    assert a.kind == "switch"
    assert a.target_protocol == "aave_v3"


def test_dwell_updates_on_observed_crossover():
    """When the winner changes between two decide() calls, the EWMA dwell
    estimator must take note. After one observed crossover, expected_dwell
    drops toward the realised gap."""
    p = T1ThresholdPolicy(initial_dwell_blocks=10_000)
    # Block 100: Aave is winner.
    p.decide(_state(current="aave_v3", aave_apr=0.05, comp_apr=0.04,
                    block_number=100))
    # Block 5_100: Compound is winner -- 5_000 blocks dwell observed.
    p.decide(_state(current="aave_v3", aave_apr=0.04, comp_apr=0.05,
                    block_number=5_100))
    # After one observation, EWMA should have pulled toward 5_000.
    assert p.dwell_blocks < 10_000
    assert p.dwell_blocks > 5_000


def test_decide_is_deterministic_given_same_state_and_dwell():
    """Pure function semantics."""
    p1 = T1ThresholdPolicy(initial_dwell_blocks=5_000)
    p2 = T1ThresholdPolicy(initial_dwell_blocks=5_000)
    s = _state(current="aave_v3", aave_apr=0.04, comp_apr=0.05)
    assert p1.decide(s) == p2.decide(s)


def test_nan_apr_in_unselectable_protocols_is_safe():
    """If Compound has NaN APR (no data yet), T1 ignores it."""
    p = T1ThresholdPolicy(initial_dwell_blocks=10_000)
    a = p.decide(_state(current="aave_v3", aave_apr=0.04, comp_apr=float("nan")))
    assert a.kind == "hold"
