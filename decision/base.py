"""DecisionPolicy ABC + BlockState / Action dataclasses + shared constants.

Both dataclasses are frozen -- pure data, no methods. The policy is
therefore a function in the mathematical sense: decide(state) -> action.
This purity is what lets the replay engine treat policies as
O(1)-state streaming consumers (no policy-side history-keeping that
the engine has to know about).

BLOCKS_PER_YEAR is defined here once (int 2_628_000) because both
T1 (yield math) AND the replay engine (APR accrual) need it; defining
it in each module risks silent int/float drift between subagent
implementations.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd


# 365 days * 24h * 60min * 60s / 12s-per-block = 2_628_000 blocks/year
# post-PoS Ethereum. Exact at integer precision (12 evenly divides 86400).
BLOCKS_PER_YEAR: int = 365 * 24 * 60 * 60 // 12


ActionKind = Literal["hold", "switch"]


@dataclass(frozen=True)
class Action:
    """One block's decision output. Frozen / hashable / equality-comparable."""

    kind: ActionKind
    target_protocol: str | None
    rationale: str = ""

    def __post_init__(self) -> None:
        if self.kind == "switch" and self.target_protocol is None:
            raise ValueError("target_protocol required when kind='switch'")


@dataclass(frozen=True)
class BlockState:
    """One block's input snapshot to the decision policy.

    Pure data: the policy is a pure function decide(state) -> action.
    All per-protocol fields are dict[protocol_name -> value] keyed by
    the names in the `protocols` tuple (validated by __post_init__).

    `aux` is an open-ended dict for additional signal-class features
    (F1 lead-rate, F4 related-instruments). The replay engine populates
    it from panel columns matching `f1_*`, `f4_*`, `usdc_peg_dev_bp`,
    `eth_usd` etc. Policies that don't need extras ignore this field;
    T3HazardPolicy reads it for Cox features outside of the F3
    fragmentation family.
    """

    block_number: int
    block_timestamp: pd.Timestamp
    protocols: tuple[str, ...]
    lending_apr: dict[str, float]
    utilization: dict[str, float]
    tvl_usd: dict[str, float]
    current_protocol: str | None
    position_usd: float
    gas_price_gwei: float
    eth_price_usd: float
    gas_used_estimate: int
    aux: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        proto_set = set(self.protocols)
        for label, d in (
            ("lending_apr", self.lending_apr),
            ("utilization", self.utilization),
            ("tvl_usd", self.tvl_usd),
        ):
            if set(d.keys()) != proto_set:
                raise ValueError(
                    f"protocols={self.protocols} but {label} keys="
                    f"{list(d.keys())}"
                )


class DecisionPolicy(ABC):
    """Abstract interface that every T1/T2/T3 + B1-B4 policy implements.

    Subclasses MUST set the class attribute `name` (used for log lines
    and the results matrix index). They MUST also implement decide();
    everything else is optional helpers.
    """

    name: str = "unnamed"

    @abstractmethod
    def decide(self, state: BlockState) -> Action:
        """Return hold-or-switch decision for the current block."""

    @staticmethod
    def gas_cost_usd(state: BlockState) -> float:
        """Convert (gas_used * gas_price_gwei) to USD using eth_price_usd.

        Static so subclasses can call it without instantiating; identical
        formula across T1/T2/T3 + B3/B4 (since gas is paid the same way
        regardless of which protocol you switch into).
        """
        return (
            state.gas_used_estimate
            * state.gas_price_gwei
            * 1e-9  # gwei -> ETH
            * state.eth_price_usd
        )
