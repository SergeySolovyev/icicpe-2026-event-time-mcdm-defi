"""Contract test for the DecisionPolicy ABC + BlockState/Action dataclasses.

These three types are the shared interface that all of Plan B's policies
(T1 threshold, T2 optimal stopping, T3 hazard from Plan C, B1-B4
baselines) implement, and that the per-block replay engine consumes.
The tests pin invariants so a subagent implementing any policy can
trust the contract without reading every other policy's code.
"""
import pandas as pd
import pytest

from decision.base import (
    Action,
    BlockState,
    BLOCKS_PER_YEAR,
    DecisionPolicy,
)


def _good_state(current=None, position=1_000_000.0):
    return BlockState(
        block_number=19_500_000,
        block_timestamp=pd.Timestamp("2025-06-01", tz="UTC"),
        protocols=("aave_v3", "compound_v3"),
        lending_apr={"aave_v3": 0.04, "compound_v3": 0.05},
        utilization={"aave_v3": 0.78, "compound_v3": 0.72},
        tvl_usd={"aave_v3": 1.2e9, "compound_v3": 0.6e9},
        current_protocol=current,
        position_usd=position,
        gas_price_gwei=25.0,
        eth_price_usd=3500.0,
        gas_used_estimate=200_000,
    )


def test_hold_action_valid():
    a = Action(kind="hold", target_protocol=None, rationale="no edge")
    assert a.kind == "hold"


def test_switch_action_requires_target():
    with pytest.raises(ValueError, match="target_protocol required"):
        Action(kind="switch", target_protocol=None, rationale="x")


def test_blockstate_protocols_must_match_apr_keys():
    with pytest.raises(ValueError, match="protocols.*lending_apr"):
        BlockState(
            block_number=1,
            block_timestamp=pd.Timestamp("2025-01-01", tz="UTC"),
            protocols=("aave_v3",),
            lending_apr={"aave_v3": 0.04, "compound_v3": 0.05},  # extra key
            utilization={"aave_v3": 0.5},
            tvl_usd={"aave_v3": 1e9},
            current_protocol=None,
            position_usd=1.0,
            gas_price_gwei=20.0,
            eth_price_usd=3000.0,
            gas_used_estimate=200_000,
        )


def test_policy_is_abstract():
    """DecisionPolicy must not be instantiable directly -- it's an ABC."""
    with pytest.raises(TypeError):
        DecisionPolicy()  # type: ignore[abstract]


def test_concrete_policy_returns_action():
    """A trivial subclass must return an Action from decide()."""

    class HoldForever(DecisionPolicy):
        name = "hold_forever"

        def decide(self, state):
            return Action(kind="hold", target_protocol=None, rationale="test")

    a = HoldForever().decide(_good_state())
    assert isinstance(a, Action) and a.kind == "hold"


def test_gas_cost_usd_helper():
    """gas_cost_usd(state) = gas_used * gas_price_gwei * 1e-9 * eth_price_usd."""
    state = _good_state()
    cost = DecisionPolicy.gas_cost_usd(state)
    # 200_000 * 25 * 1e-9 * 3500 = 17.5
    assert abs(cost - 17.5) < 0.01


def test_blocks_per_year_is_integer_constant():
    """BLOCKS_PER_YEAR must be an int (not float), since it appears in
    decision math AND in the replay engine. Locked here to prevent
    silent type-drift between modules."""
    assert isinstance(BLOCKS_PER_YEAR, int)
    # 365 * 24 * 60 * 60 // 12 = 2_628_000  (exact on post-PoS 12s/block)
    assert BLOCKS_PER_YEAR == 2_628_000


def test_action_is_frozen():
    """Action is a frozen dataclass -- mutation must raise."""
    a = Action(kind="hold", target_protocol=None, rationale="")
    with pytest.raises(Exception):
        a.kind = "switch"  # type: ignore[misc]


def test_blockstate_is_frozen():
    s = _good_state()
    with pytest.raises(Exception):
        s.position_usd = 0.0  # type: ignore[misc]
