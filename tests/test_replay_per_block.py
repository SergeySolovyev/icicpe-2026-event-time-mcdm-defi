"""Tests for the per-block replay engine."""
import math

import numpy as np
import pandas as pd
import pytest

from backtest.replay_per_block import EventReplayEngine, ReplaySummary
from decision.base import Action, BlockState, DecisionPolicy, BLOCKS_PER_YEAR


class AlwaysHoldPolicy(DecisionPolicy):
    name = "always_hold"
    def decide(self, state):
        return Action(kind="hold", target_protocol=None, rationale="")


class AlwaysSwitchPolicy(DecisionPolicy):
    name = "always_switch"
    def decide(self, state):
        # Always sit in the highest-APR protocol.
        valid = {p: a for p, a in state.lending_apr.items() if not math.isnan(a)}
        best = max(valid, key=valid.get) if valid else None
        if best is None or best == state.current_protocol:
            return Action(kind="hold", target_protocol=None, rationale="")
        return Action(kind="switch", target_protocol=best, rationale="")


def _mini_panel():
    """2 blocks, Aave at 5% APR consistently, Compound at 3%."""
    return pd.DataFrame({
        "block_number": [100, 101],
        "block_timestamp": pd.to_datetime([1735689600, 1735689612], unit="s", utc=True),
        "aave_v3_lending_apr": [0.05, 0.05],
        "compound_v3_lending_apr": [0.03, 0.03],
        "aave_v3_utilization": [0.8, 0.8],
        "compound_v3_utilization": [0.7, 0.7],
        "aave_v3_tvl_usd": [1e9, 1e9],
        "compound_v3_tvl_usd": [5e8, 5e8],
    })


def test_replay_zero_blocks_returns_empty():
    panel = _mini_panel().iloc[:0]
    engine = EventReplayEngine(initial_capital_usd=1_000_000.0)
    eq, summary = engine.run(panel=panel, policy=AlwaysHoldPolicy())
    assert len(eq) == 0
    assert summary.n_switches == 0


def test_replay_hold_accrues_no_position_change_until_allocated():
    """AlwaysHold + no current_protocol: position never enters a pool, no growth."""
    panel = _mini_panel()
    engine = EventReplayEngine(initial_capital_usd=1_000_000.0)
    eq, summary = engine.run(panel=panel, policy=AlwaysHoldPolicy())
    assert eq["position_usd"].iloc[-1] == 1_000_000.0


def test_replay_always_switch_picks_aave_first_block():
    """AlwaysSwitch + Aave 5% > Compound 3%: first block switches into Aave."""
    panel = _mini_panel()
    engine = EventReplayEngine(initial_capital_usd=1_000_000.0)
    eq, summary = engine.run(panel=panel, policy=AlwaysSwitchPolicy())
    assert summary.n_switches == 1
    assert eq["current_protocol"].iloc[-1] == "aave_v3"
    # 2 blocks at 5% APR (annualised) ~ tiny; check position > initial - gas
    assert eq["position_usd"].iloc[-1] > 1_000_000.0 - 100.0  # gas <= $100


def test_gas_cost_is_deducted_on_switch():
    """One switch must cost gas_used * gas_price * eth_price USD."""
    panel = _mini_panel().copy()
    panel["gas_price_gwei"] = 50.0
    panel["eth_price_usd"] = 4000.0
    engine = EventReplayEngine(initial_capital_usd=1_000_000.0,
                               gas_used_estimate=200_000)
    eq, summary = engine.run(panel=panel, policy=AlwaysSwitchPolicy())
    # 200_000 * 50 * 1e-9 * 4000 = $40 gas
    assert abs(summary.total_gas_usd - 40.0) < 0.5
    assert summary.n_switches == 1


def test_apr_accrues_at_blocks_per_year_rate():
    """Hold in Aave for 1 year of blocks at 5% APR -> position * 1.05 +/- compounding fuzz."""
    rows = []
    for i in range(BLOCKS_PER_YEAR):
        rows.append({
            "block_number": 100 + i,
            "block_timestamp": pd.Timestamp(1735689600 + i*12, unit="s", tz="UTC"),
            "aave_v3_lending_apr": 0.05,
            "compound_v3_lending_apr": 0.03,
            "aave_v3_utilization": 0.8,
            "compound_v3_utilization": 0.7,
            "aave_v3_tvl_usd": 1e9,
            "compound_v3_tvl_usd": 5e8,
        })
    panel = pd.DataFrame(rows)
    engine = EventReplayEngine(initial_capital_usd=1_000_000.0)
    eq, summary = engine.run(panel=panel, policy=AlwaysSwitchPolicy())
    final = eq["position_usd"].iloc[-1]
    # Compounded 1 year at 5% APR: ~ exp(0.05) ~ 1.05127
    # Initial gas deduction ~ $17.5 (default gas/eth)
    assert 1_050_000.0 < final < 1_055_000.0
