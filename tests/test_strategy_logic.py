"""Unit tests for strategy logic (hysteresis, cooldown, gas-gate, decision rule).

Covers the headline `PredictiveMCDMStrategy` plus all four baselines.
Uses fractal-defi `SimpleLendingEntity` mocks so tests run without network.

Test categories:
1. Hysteresis: rebalance triggers iff |Score_best - Score_current| > theta
2. Cooldown: no rebalance within tau seconds of previous
3. Gas-gate: rebalance only if uplift * dt * notional >= gas_cost
4. Sign convention: actions never produce negative cash / debt
5. Idempotence: predict() with identical state returns identical actions
"""
# TODO Week 2 Day 5-6 (29-30 May 2026)
import pytest


@pytest.mark.skip(reason="Week 2 Day 5-6")
def test_mcdm_hysteresis_blocks_micro_switches() -> None:
    raise NotImplementedError


@pytest.mark.skip(reason="Week 2 Day 5-6")
def test_cooldown_enforced() -> None:
    raise NotImplementedError


@pytest.mark.skip(reason="Week 2 Day 5-6")
def test_gas_gate_blocks_unprofitable_rebalance() -> None:
    raise NotImplementedError
