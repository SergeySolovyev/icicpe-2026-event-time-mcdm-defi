# Add `BaseLendingAllocationStrategy` for multi-lending-protocol allocators

## Summary

This PR adds a new strategy base class — `BaseLendingAllocationStrategy` —
that handles the bookkeeping common to any allocator that routes capital
between N registered lending entities (Aave, Compound, Morpho, Spark,
SimpleLendingEntity, ...). Subclasses override 4 small hooks; the base
class provides default `predict()` orchestration, cooldown infrastructure
(which the framework lacks), and an opinionated transfer flow.

The first concrete subclass — a 4-factor TOPSIS-style MCDM allocator
with EMA-smoothed rate — is ALSO included as `MCDMEMAStrategy` so the
abstraction is shipped with a real, non-toy user.

## Motivation

Repo state (v1.3.2): `fractal/strategies/` contains
`BasisTradingStrategy`, `HyperliquidBasis`, `TauResetStrategy`. There is
NO multi-lending-protocol allocator, despite the framework shipping four
lending entities and `transfer()` already handling cross-entity cash
movement. Every downstream user writing a lending allocator currently
re-implements the same boilerplate: entity registration, score gathering,
hysteresis, cooldown, gas-gate, two-leg transfer ordering.

Two specific gaps the framework currently leaves to the user:

1. **No cooldown infrastructure.** Existing strategies use boolean
   one-shot guards (`_deposited`, `deposited_initial_funds`) or
   gap-based hysteresis (MIN_LEVERAGE/MAX_LEVERAGE bracket). For a
   time-based "do not rebalance within τ seconds" gate, the user must
   override `step()` to capture `observation.timestamp` themselves.

2. **No "extract scores -> argmax -> transfer" orchestration.** The
   transfer() helper is great, but every subclass repeats the same
   capture-balance-snapshot-then-emit-transfer-with-delegate dance, and
   it's an easy place to get the callable-delegate signature wrong (the
   delegate must take a `_strategy` positional, otherwise the framework's
   `val(self)` resolution overwrites a snapshot default).

Both gaps are filled by this PR, with a single API surface broadly
useful to any lending-allocation use case.

## Design

```python
class BaseLendingAllocationStrategy(BaseStrategy[BaseLendingAllocationParams]):
    STRICT_OBSERVATIONS = True
    LENDING_ENTITY_NAMES: tuple[str, ...] = ("AAVE", "COMPOUND")

    # Subclasses override these 4 hooks (signatures fixed):
    def compute_criteria_vector(self, entity_name: str) -> np.ndarray: ...
    def aggregate_criteria(self, M: np.ndarray) -> np.ndarray: ...
    def select_target(self, scores: np.ndarray) -> str: ...
    def should_rebalance(self, current, target, scores) -> bool: ...

    # Subclasses inherit, rarely override:
    def predict(self) -> List[ActionToTake]: ...
    def step(self, observation: Observation): ...        # timestamp capture
    def set_up(self) -> None: ...                        # SimpleLendingEntity per name
```

Default behaviour:

* `select_target` = argmax over aggregated scores.
* `should_rebalance` = strict hysteresis (`delta > THETA`) + time-based
  cooldown using `observation.timestamp` captured in the overridden
  `step()`.
* `aggregate_criteria` = SAW (Simple Additive Weighting) with
  `self._criterion_weights` (default: equal weights).
* `set_up` = `SimpleLendingEntity` per name in `LENDING_ENTITY_NAMES`.
  Subclasses override to use protocol-specific entities.

## What it enables (the included concrete subclass)

```python
class MCDMEMAStrategy(BaseLendingAllocationStrategy):
    """4-factor (APY, Risk, Cost, Stability) MCDM with EMA-smoothed rate."""
    PARAMS_CLS = MCDMEMAParams                # 4 weights + EMA alpha + APY norm

    def compute_criteria_vector(self, entity_name):
        return np.array([
            f_apy(smoothed_rate(entity_name), apy_max),
            f_risk(gs.utilization),
            f_cost(gs.gas_gwei, gas_per_rebalance, gas_max_eth),
            f_stab(gs.delta_tvl_24h),
        ])
```

The 4 sub-factor functions are pure, side-effect-free; the EMA state lives
in a per-entity dict on the strategy instance; the rest comes from the
base class.

## Loader-contract documentation

The base class's docstring explicitly documents the
`collateral_price = 1.0` requirement for USD-denominated stable lending
(USDC, USDT, DAI). `SimpleLendingGlobalState` defaults
`collateral_price = 0.0`, which silently zeros `entity.balance` and
makes every `transfer()` move zero. A defensive `RuntimeError` fires in
`predict()` at the first rebalance attempt with a clear message —
fail-loud rather than silent-success-with-wrong-numbers.

## Files

```
fractal/
├── strategies/
│   ├── base_lending_allocation.py      ← NEW (240 lines)
│   └── mcdm_ema.py                     ← NEW (120 lines)

tests/
├── strategies/
│   ├── test_base_lending_allocation.py ← NEW: hysteresis, cooldown,
│   │                                       delegate-signature lock-in,
│   │                                       initial-deposit branch, no-op
│   │                                       when target == current
│   └── test_mcdm_ema.py                ← NEW: per-factor unit tests +
│                                            integration on synthetic 30-day
│                                            joined panel
```

## Tests

6 strategy-logic tests in the original project repo, all passing:

```
tests/test_strategy_logic.py::test_initial_predict_emits_deposit_not_transfer PASSED
tests/test_strategy_logic.py::test_hysteresis_blocks_below_threshold PASSED
tests/test_strategy_logic.py::test_hysteresis_allows_above_threshold PASSED
tests/test_strategy_logic.py::test_cooldown_blocks_rapid_rebalance PASSED
tests/test_strategy_logic.py::test_no_rebalance_when_target_equals_current PASSED
tests/test_strategy_logic.py::test_transfer_delegate_returns_snapshot_not_strategy PASSED
```

The `test_transfer_delegate_returns_snapshot_not_strategy` test is the
**lock-in regression test** for a subtle bug I found while reviewing my
own PR: when a delegate is a callable, the framework resolves it as
`val(self)` (BaseStrategy.step line 341) — passing the strategy instance
as positional. A 0-arg lambda whose default captures a snapshot would
have its default overwritten by the strategy instance, silently producing
wrong-type amounts. The test explicitly calls the resolved delegate with
the strategy instance and asserts it returns the snapshot float, not the
strategy. Recommend keeping this test as documentation of the convention.

## Out of scope

- TOPSIS / PROMETHEE / VIKOR aggregators — left to subclasses via the
  `aggregate_criteria` hook.
- Forecast-driven scoring (a `PredictiveMCDMStrategy` subclass) — lives
  downstream because it requires ONNX runtime + a trained model.
- Per-entity weight asymmetry (different sub-factor weights for AAVE vs
  COMPOUND) — current `criterion_weights` is a single vector; extending
  is a non-breaking future change.

## Linked issue / discussion

Full design rationale + 7-issue independent code review (which surfaced
the delegate-signature bug) in
`extras/fractal_pr_lending_allocation/README.md` in the
`SergeySolovyev/predictive-mcdm-defi` repo.

## Checklist

- [ ] Tests pass locally (`pytest tests/strategies/ -v`)
- [ ] CHANGELOG.md entry under [Unreleased]
- [ ] Docstrings on all public functions
- [ ] Loader-contract `collateral_price = 1.0` requirement documented on
      `BaseLendingAllocationStrategy.LENDING_ENTITY_NAMES`
- [ ] Backward compat: existing strategies (BasisTrading, etc.) unchanged
