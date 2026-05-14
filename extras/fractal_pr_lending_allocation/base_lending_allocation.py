"""BaseLendingAllocationStrategy — Extra+2 contribution to fractal-defi.

Multi-lending-protocol allocator base class. Provides four extension
points the framework lacks, lifting the bookkeeping of rebalance triggers
and the dispatch of move-cash-between-two-lending-entities into a single
inheritable shape.

The four hooks subclasses override:

  1. compute_criteria_vector(entity_name) -> np.ndarray
       Per-protocol vector of criteria (APY, risk, cost, stability, ...).
       Returned in a fixed order; the order is the subclass's convention.

  2. aggregate_criteria(criteria_matrix) -> np.ndarray
       Reduce (n_protocols, n_criteria) -> (n_protocols,) score vector.
       Default: convex combination by self._criterion_weights.
       Subclasses can override for TOPSIS, PROMETHEE, etc.

  3. select_target(scores) -> str
       Pick the winning entity name. Default: argmax.

  4. should_rebalance(current, target, scores) -> bool
       Final go/no-go. Default: hysteresis + cooldown + gas-gate.

The default `predict()` orchestrates: gather criteria -> aggregate ->
select -> check -> if yes, emit a transfer() of the full balance from
current to target.

Cooldown infrastructure (the framework lacks it): we override `step` to
capture observation.timestamp into `self._current_timestamp`, then
should_rebalance() reads self._last_rebalance_ts to enforce the cooldown.

This file is staged here pending project-level validation before PR
submission. The production location after merge is
`fractal/strategies/base_lending_allocation.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, List, Optional, Sequence

import numpy as np

from fractal.core.base import (
    Action,
    ActionToTake,
    BaseStrategy,
    BaseStrategyParams,
    NamedEntity,
    Observation,
)
from fractal.core.entities import SimpleLendingEntity


# ---------------------------------------------------------------------------
# Params
# ---------------------------------------------------------------------------

@dataclass
class BaseLendingAllocationParams(BaseStrategyParams):
    """Hyper-parameters shared across all lending-allocation subclasses.

    Subclasses may extend with their own fields (e.g. MCDM weights,
    forecast model path); the framework auto-coerces dict-shaped grid
    cells into the most-derived params class via `PARAMS_CLS`.
    """

    INITIAL_BALANCE: float = 1_000_000.0

    # Rebalance discipline (Plan §1.5)
    HYSTERESIS_THRESHOLD: float = 0.05       # score-delta required to switch
    COOLDOWN_HOURS: float = 1.0              # min hours between rebalances
    GAS_GATE_BPS: float = 0.0                # 0 disables; subclass can wire in

    # Initial deposit goes here at t=0 if no entity has a balance yet
    DEFAULT_INITIAL_ENTITY: str = ""


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

class BaseLendingAllocationStrategy(BaseStrategy[BaseLendingAllocationParams]):
    """Allocator across N registered lending entities.

    Entity registration is delegated to the subclass's `set_up`. Each
    registered entity name appears as a column / row label everywhere
    downstream — keep them stable across observations.

    Subclasses MUST override:
        compute_criteria_vector(entity_name) -> np.ndarray
    Subclasses MAY override:
        aggregate_criteria(matrix) -> np.ndarray
        select_target(scores) -> str
        should_rebalance(current, target, scores) -> bool

    The default `predict()` is fully wired and rarely needs override.

    Default `set_up()` registers a `SimpleLendingEntity` for each name
    in `LENDING_ENTITY_NAMES`. Subclasses can override `set_up` to use
    protocol-specific entity types (e.g. `AaveEntity`,
    `CompoundV3Entity` once available) without changing the rest of the
    abstraction.
    """

    # default is True; subclass can flip when feeds are misaligned.
    # WARNING: with STRICT_OBSERVATIONS=True any observation missing a state
    # for any registered entity raises ValueError before predict() runs.
    # Compound V3 / Aave subgraphs are known to have hourly gaps during
    # network congestion. The companion `data/clean.py` reindexes the
    # joined dataset to a uniform hourly UTC grid and forward-fills gaps
    # up to 6 hours; subclasses that bypass `data/clean.py` should consider
    # setting `STRICT_OBSERVATIONS = False` and reading per-step validity
    # masks instead.
    STRICT_OBSERVATIONS = True

    #: Entity names this allocator manages. Subclasses override to add
    #: more protocols. The default `set_up` registers a `SimpleLendingEntity`
    #: per name. Override `set_up` to use protocol-specific entity classes.
    #:
    #: REQUIRED loader contract: when populating the per-step GlobalState
    #: for each lending entity, the loader MUST set
    #: `collateral_price = 1.0` for USD-denominated stable-asset lending
    #: (USDC, USDT, DAI). The default `SimpleLendingGlobalState` initialises
    #: collateral_price to 0.0, which makes `entity.balance == 0` and
    #: silently zeros every transfer's amount. The fractal-defi loader
    #: contract should fill this when the data is built; subclasses can
    #: also assert it in set_up().
    LENDING_ENTITY_NAMES: tuple[str, ...] = ("AAVE", "COMPOUND")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._current_entity: Optional[str] = None   # set on first allocation
        self._last_rebalance_ts: Optional[datetime] = None
        self._current_timestamp: Optional[datetime] = None
        # Stable order: locked at first predict() so criteria_matrix rows align
        self._entity_order: List[str] = []

    # ------------------------------------------------------------------
    # Lifecycle: capture timestamp before predict()
    # ------------------------------------------------------------------

    def set_up(self) -> None:
        """Default: register one SimpleLendingEntity per LENDING_ENTITY_NAMES.

        Subclasses override to use protocol-specific entity classes (e.g.
        replace `SimpleLendingEntity()` with `AaveEntity()`).
        """
        for name in self.LENDING_ENTITY_NAMES:
            self.register_entity(NamedEntity(
                entity_name=name,
                entity=SimpleLendingEntity(),
            ))

    def step(self, observation: Observation):
        """Snapshot the observation timestamp for cooldown checks, then
        delegate to the framework's step()."""
        self._current_timestamp = observation.timestamp
        return super().step(observation)

    # ------------------------------------------------------------------
    # Hooks — subclasses override
    # ------------------------------------------------------------------

    def compute_criteria_vector(self, entity_name: str) -> np.ndarray:  # pragma: no cover
        """Return per-criterion vector for `entity_name`.

        Length, semantics, and order are subclass-defined and must be
        consistent across all entities.
        """
        raise NotImplementedError("subclass must implement compute_criteria_vector")

    def aggregate_criteria(self, criteria_matrix: np.ndarray) -> np.ndarray:
        """Default: convex combination via self._criterion_weights.

        Subclass can override (e.g. TOPSIS distance, PROMETHEE flow).
        """
        weights = getattr(self, "_criterion_weights", None)
        if weights is None:
            # Default: equal weighting
            n_criteria = criteria_matrix.shape[1]
            weights = np.full(n_criteria, 1.0 / n_criteria)
        return criteria_matrix @ np.asarray(weights, dtype=float)

    def select_target(self, scores: np.ndarray) -> str:
        return self._entity_order[int(np.argmax(scores))]

    def should_rebalance(
        self,
        current: Optional[str],
        target: str,
        scores: np.ndarray,
    ) -> bool:
        """Hysteresis + cooldown + (subclass-injectable) gas-gate."""
        # First allocation always proceeds
        if current is None:
            return True

        if current == target:
            return False

        # Cooldown
        if self._last_rebalance_ts is not None and self._current_timestamp is not None:
            elapsed = self._current_timestamp - self._last_rebalance_ts
            if elapsed < timedelta(hours=self._params.COOLDOWN_HOURS):
                return False

        # Hysteresis: target must beat current by STRICTLY MORE than THETA.
        # Using `<=` rather than `<` keeps equal-to-threshold cases as
        # "no switch", which prevents oscillation when the score delta
        # lands exactly on the dead-band edge across consecutive cooldown
        # boundaries (relevant when HYSTERESIS_THRESHOLD is swept in grid
        # search).
        cur_idx = self._entity_order.index(current)
        tgt_idx = self._entity_order.index(target)
        delta = float(scores[tgt_idx] - scores[cur_idx])
        if delta <= self._params.HYSTERESIS_THRESHOLD:
            return False

        return True

    # ------------------------------------------------------------------
    # Default predict() orchestration
    # ------------------------------------------------------------------

    def predict(self) -> List[ActionToTake]:
        # Lock entity order on first call so criteria matrix rows are stable
        if not self._entity_order:
            self._entity_order = list(self._entities.keys())

        # Initial deposit
        if self._current_entity is None:
            init_to = (
                self._params.DEFAULT_INITIAL_ENTITY
                or self._entity_order[0]
            )
            if init_to not in self._entity_order:
                raise ValueError(
                    f"DEFAULT_INITIAL_ENTITY {init_to!r} not in registered "
                    f"entities {self._entity_order}"
                )
            self._current_entity = init_to
            self._last_rebalance_ts = self._current_timestamp
            return [
                ActionToTake(
                    entity_name=init_to,
                    action=Action("deposit", {
                        "amount_in_notional": self._params.INITIAL_BALANCE,
                    }),
                ),
            ]

        # Gather criteria
        criteria = np.stack([
            self.compute_criteria_vector(name)
            for name in self._entity_order
        ], axis=0)   # (n_entities, n_criteria)
        scores = self.aggregate_criteria(criteria)
        target = self.select_target(scores)

        if not self.should_rebalance(self._current_entity, target, scores):
            return []

        # Capture total balance now (before any actions mutate it).
        # CRITICAL: the framework resolves callable delegates as `val(self)`
        # (BaseStrategy.step line 341), passing the strategy instance as a
        # positional arg. A 0-arg lambda whose default captures the snapshot
        # would have its `_amt` default overwritten by the strategy instance,
        # silently producing wrong-type amounts. Use a 2-arg form that
        # accepts and ignores the strategy positional.
        source = self._current_entity
        source_entity = self.get_entity(source)
        amount_to_move = source_entity.balance

        # Defensive: if balance is 0 but we expect funds (have rebalanced
        # previously OR have made initial deposit), the loader almost
        # certainly forgot to set collateral_price (default = 0.0 on
        # SimpleLendingGlobalState). See class docstring on the loader
        # contract; fail loud rather than silently transferring 0.
        if amount_to_move <= 0.0 and self._params.INITIAL_BALANCE > 0:
            raise RuntimeError(
                f"Source entity {source!r} has zero balance at rebalance "
                f"time. Likely cause: collateral_price defaulted to 0.0 in "
                f"the loader output, making balance = collateral * 0 = 0. "
                f"For USD-denominated stable lending the loader must set "
                f"collateral_price = 1.0 on every GlobalState. See class "
                f"docstring for the loader contract."
            )

        def _amount_delegate(_strategy, _amt: float = amount_to_move) -> float:
            return _amt

        actions = self.transfer(
            from_entity=source,
            to_entity=target,
            amount_in_notional=_amount_delegate,
        )

        # Update internal state
        self._current_entity = target
        self._last_rebalance_ts = self._current_timestamp
        return actions
