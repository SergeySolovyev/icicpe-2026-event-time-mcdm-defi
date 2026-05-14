"""Unit tests for the Extra+2 abstraction's decision logic.

Covers the three guards that gate the `transfer()` action in
`BaseLendingAllocationStrategy.should_rebalance`:

* HYSTERESIS_THRESHOLD — blocks micro-switches near the score boundary.
* COOLDOWN_HOURS      — blocks rapid back-to-back rebalances.
* INITIAL deposit     — first call returns deposit, not transfer.

All tests use a tiny `_ScoreInjectorStrategy` mock that overrides
`compute_criteria_vector` to return arbitrary user-controlled scores.
This isolates the guard logic from MCDM / forecast / EMA noise.

Run: pytest tests/test_strategy_logic.py -v
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "extras" / "fractal_pr_lending_allocation"))

from base_lending_allocation import (  # noqa: E402
    BaseLendingAllocationParams,
    BaseLendingAllocationStrategy,
)


# ----------------------------------------------------------------------------
# Test fixtures — score-injecting mock strategy
# ----------------------------------------------------------------------------

class _ScoreInjectorStrategy(BaseLendingAllocationStrategy):
    """Test-only subclass: scores driven by `self._injected_scores` dict.

    Call `s._inject({"AAVE": 0.5, "COMPOUND": 0.7})` between observations
    to control which entity the abstraction prefers.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._injected_scores: dict[str, float] = {"AAVE": 0.5, "COMPOUND": 0.5}

    def _inject(self, scores: dict[str, float]) -> None:
        self._injected_scores = dict(scores)

    def compute_criteria_vector(self, entity_name: str) -> np.ndarray:
        return np.array([self._injected_scores.get(entity_name, 0.0)])

    def aggregate_criteria(self, criteria_matrix: np.ndarray) -> np.ndarray:
        return criteria_matrix[:, 0]


def _ts(year=2026, month=1, day=1, hour=0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _seed_funds_in(strategy, entity_name: str, amount: float = 1_000_000.0) -> None:
    """Simulate post-deposit state: entity has collateral + price = 1.0.

    The default `SimpleLendingGlobalState` initialises `collateral_price` to
    0.0 (which makes balance=0 and triggers our defensive assertion). Real
    runs satisfy the loader contract by setting price=1.0 every observation;
    tests must replicate that.
    """
    e = strategy.get_entity(entity_name)
    e._internal_state.collateral = amount
    e._global_state.collateral_price = 1.0


# ----------------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------------

def test_initial_predict_emits_deposit_not_transfer():
    """First predict() call must initial-deposit, not transfer."""
    s = _ScoreInjectorStrategy()
    s._current_timestamp = _ts()
    actions = s.predict()
    assert len(actions) == 1
    assert actions[0].action.action == "deposit"
    # Second predict() with same scores must NOT rebalance
    s._current_timestamp = _ts(hour=1)
    s._inject({"AAVE": 0.5, "COMPOUND": 0.5})
    actions2 = s.predict()
    assert actions2 == []


def test_hysteresis_blocks_below_threshold():
    """When target's score beats current by less than the threshold, do NOT switch.

    With HYSTERESIS_THRESHOLD=0.05 and delta=0.04 (clearly below),
    should_rebalance must return False. Avoid testing delta == 0.05
    exactly because 0.55 - 0.50 = 0.05000000000000004 in float64 (and
    0.05 + epsilon would be a flaky test across machines).
    """
    s = _ScoreInjectorStrategy(params={
        "INITIAL_BALANCE": 1_000_000.0,
        "HYSTERESIS_THRESHOLD": 0.05,
        "COOLDOWN_HOURS": 0.0,
        "GAS_GATE_BPS": 0.0,
        "DEFAULT_INITIAL_ENTITY": "",
    })
    # Initial deposit
    s._current_timestamp = _ts()
    s.predict()
    assert s._current_entity == "AAVE"
    _seed_funds_in(s, "AAVE")     # loader-contract simulation

    # Clearly below: delta == 0.04 < threshold 0.05 -> no switch
    s._inject({"AAVE": 0.50, "COMPOUND": 0.54})
    s._current_timestamp = _ts(hour=1)
    actions = s.predict()
    assert actions == [], f"Expected no rebalance at delta=0.04; got {len(actions)} actions"


def test_hysteresis_allows_above_threshold():
    """When target's score beats current strictly above the threshold, DO switch."""
    s = _ScoreInjectorStrategy(params={
        "INITIAL_BALANCE": 1_000_000.0,
        "HYSTERESIS_THRESHOLD": 0.05,
        "COOLDOWN_HOURS": 0.0,
        "GAS_GATE_BPS": 0.0,
        "DEFAULT_INITIAL_ENTITY": "",
    })
    # Initial deposit
    s._current_timestamp = _ts()
    s.predict()
    _seed_funds_in(s, "AAVE")

    # Strictly above: delta = 0.06 -> switch
    s._inject({"AAVE": 0.50, "COMPOUND": 0.56})
    s._current_timestamp = _ts(hour=1)
    actions = s.predict()
    # transfer() returns 2 actions (deposit-on-dst, withdraw-from-src)
    assert len(actions) == 2
    entity_names = [a.entity_name for a in actions]
    assert "COMPOUND" in entity_names and "AAVE" in entity_names


def test_cooldown_blocks_rapid_rebalance():
    """A second rebalance attempt within COOLDOWN_HOURS must be blocked."""
    s = _ScoreInjectorStrategy(params={
        "INITIAL_BALANCE": 1_000_000.0,
        "HYSTERESIS_THRESHOLD": 0.05,
        "COOLDOWN_HOURS": 2.0,   # 2-hour cooldown
        "GAS_GATE_BPS": 0.0,
        "DEFAULT_INITIAL_ENTITY": "",
    })
    # t=0: initial deposit into AAVE
    s._current_timestamp = _ts(hour=0)
    s.predict()
    _seed_funds_in(s, "AAVE")

    # t=1 (within cooldown): COMPOUND strongly preferred -> blocked
    s._inject({"AAVE": 0.30, "COMPOUND": 0.70})
    s._current_timestamp = _ts(hour=1)
    actions = s.predict()
    assert actions == [], "Cooldown should block rebalance within COOLDOWN_HOURS"

    # t=3 (past cooldown): same preference -> allowed
    s._current_timestamp = _ts(hour=3)
    actions = s.predict()
    assert len(actions) == 2, "Cooldown should release after COOLDOWN_HOURS"


def test_no_rebalance_when_target_equals_current():
    """If argmax is the current entity, no action emitted."""
    s = _ScoreInjectorStrategy(params={
        "INITIAL_BALANCE": 1_000_000.0,
        "HYSTERESIS_THRESHOLD": 0.0,    # tightest hysteresis still requires switch
        "COOLDOWN_HOURS": 0.0,
        "GAS_GATE_BPS": 0.0,
        "DEFAULT_INITIAL_ENTITY": "",
    })
    s._current_timestamp = _ts(hour=0)
    s.predict()
    # AAVE strictly preferred -> argmax == current -> no switch
    s._inject({"AAVE": 0.99, "COMPOUND": 0.01})
    s._current_timestamp = _ts(hour=1)
    assert s.predict() == []


def test_transfer_delegate_returns_snapshot_not_strategy():
    """Lock-in regression test for the code-review Issue 1 fix.

    The delegate must be a 2-arg function (_strategy, _amt=...) so the
    framework's call `val(self)` doesn't overwrite `_amt` with the
    strategy instance.
    """
    s = _ScoreInjectorStrategy(params={
        "INITIAL_BALANCE": 1_000_000.0,
        "HYSTERESIS_THRESHOLD": 0.0,
        "COOLDOWN_HOURS": 0.0,
        "GAS_GATE_BPS": 0.0,
        "DEFAULT_INITIAL_ENTITY": "",
    })
    s._current_timestamp = _ts()
    s.predict()  # initial deposit

    # Manually set source balance so the rebalance has something to move
    source = s.get_entity("AAVE")
    source._internal_state.collateral = 1_000_000.0
    # Loader-contract: collateral_price must be 1.0 for USD-stable lending
    source._global_state.collateral_price = 1.0

    s._inject({"AAVE": 0.0, "COMPOUND": 1.0})
    s._current_timestamp = _ts(hour=2)
    actions = s.predict()
    assert len(actions) == 2

    # Resolve the delegate — must return a float, not the strategy instance
    for a in actions:
        amt_arg = a.action.args.get("amount_in_notional")
        if callable(amt_arg):
            resolved = amt_arg(s)              # framework calls with strategy
            assert isinstance(resolved, float), (
                f"delegate must return float, got {type(resolved).__name__}"
            )
            assert resolved == pytest.approx(1_000_000.0), (
                f"delegate must return snapshot, got {resolved}"
            )
