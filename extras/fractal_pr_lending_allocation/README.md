# Extra+2 PR: `BaseLendingAllocationStrategy` Abstraction

**Target:** `Logarithm-Labs/fractal-defi`
**PR title:** *"Add `BaseLendingAllocationStrategy` for multi-lending-protocol allocators"*
**Status:** scoped, not yet submitted
**Deadline:** 13 June 2026 (PROJECT_2_PLAN.md timeline Week 4 Day 6)

## Motivation

Repo state (verified 14 May 2026 against v1.3.2 source): `fractal/strategies/`
contains `BasisTradingStrategy`, `HyperliquidBasis`, `TauResetStrategy`, but
**no multi-lending-protocol allocator** despite four lending entities being
available (`AaveEntity`, `MorphoEntity`, `SimpleLendingEntity`, etc.).
This is the gap this PR fills.

**Crucially: no cooldown / hysteresis infrastructure exists in `BaseStrategy`.**
The existing strategies handle "act-when-state-crosses-threshold" via simple
booleans (`_deposited`, `deposited_initial_funds`) and gap-based hysteresis
(`MIN_LEVERAGE` / `MAX_LEVERAGE` bracketing). For a multi-protocol allocator
this is insufficient — we need a proper time-based cooldown AND score-delta
hysteresis. So this PR is genuinely additive abstraction, not duplication.

## Proposed abstraction

`fractal/strategies/lending_allocation.py`:

```python
@dataclass
class BaseLendingAllocationParams(BaseStrategyParams):
    INITIAL_BALANCE          : float
    LENDING_ENTITIES         : tuple[str, ...]
    REBALANCE_COOLDOWN_HOURS : float = 1.0
    HYSTERESIS_THRESHOLD     : float = 0.05

class BaseLendingAllocationStrategy(BaseStrategy[BaseLendingAllocationParams]):
    """Abstract multi-lending-protocol allocator with four overridable hooks.

    Subclasses override:
        compute_criteria_vector(entity_name) -> np.ndarray
            One criterion per dimension (APY, Risk, Cost, Stability, ...).
        aggregate_criteria(criteria_matrix) -> np.ndarray
            One score per protocol (TOPSIS, PROMETHEE, weighted sum, ...).
        select_target(scores) -> str
            Choose entity name (argmax, argmax-with-tiebreak, ...).
        should_rebalance(current, target, scores) -> bool
            Hysteresis + cooldown + gas-gate (default impl provided).

    The framework handles state registration, action emission
    (withdraw-from-current + supply-to-target), and metric logging.
    """

    def set_up(self) -> None:                                                       ...
    def compute_criteria_vector(self, entity_name: str) -> np.ndarray:              ...
    def aggregate_criteria      (self, M: np.ndarray)                  -> np.ndarray: ...
    def select_target           (self, s: np.ndarray)                  -> str:       ...
    def should_rebalance        (self, current: str, target: str, scores: dict)  -> bool: ...
    def predict                 (self)                                 -> List[ActionToTake]: ...
```

## First concrete subclass

This project's `strategies/predictive_mcdm.py` becomes the first concrete
subclass demonstrating the abstraction:

```python
class PredictiveMCDMStrategy(BaseLendingAllocationStrategy):
    """4-factor TOPSIS-MCDM with DL-forecast APY criterion."""

    def compute_criteria_vector(self, entity_name):
        e = self.get_entity(entity_name)
        r_hat = self.forecaster.predict(self._buffer.to_array())[entity_name]
        return np.array([
            clamp(r_hat / self._params.APYMAX_NORM, 0, 1),  # f_APY
            1 - clamp(e.global_state.utilization, 0, 1),    # f_Risk (needs Extra+1)
            1 - clamp(self._gas_cost / self._params.GAS_MAX_ETH, 0, 1),  # f_Cost
            1 - clamp(abs(e.global_state.dTVL_24h) / 0.30, 0, 1),  # f_Stab
        ])

    def aggregate_criteria(self, M):
        return M @ np.array([0.40, 0.25, 0.20, 0.15])

    # select_target, should_rebalance, predict inherited from base
```

## Tests

- `tests/core/test_lending_allocation_base.py` — unit tests with
  `SimpleLendingEntity` mocks for each overridable hook.
- `tests/core/e2e/test_lending_allocation_e2e.py` — full end-to-end run
  with a 2-entity 30-day synthetic scenario.

## Files staged here

```
fractal_pr_lending_allocation/
├── README.md                            (this file)
├── lending_allocation.py                (the abstraction)
├── test_lending_allocation_base.py
└── test_lending_allocation_e2e.py
```
