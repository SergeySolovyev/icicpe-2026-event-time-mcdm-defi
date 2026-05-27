"""Streaming per-block replay engine for event-time backtesting.

Given a per-block panel (from data.build_per_block_panel) and a
DecisionPolicy, replay the policy block-by-block and accrue position
USD at the current protocol's APR per block. Gas is deducted per switch.

The engine is O(1) state -- it does NOT keep a history-per-block in
memory. Equity curve is materialised at the end (one float per row).
This is what makes a 3.9 M-block replay practical.

Kyle batch-auction semantic (lit-foundation S1 O'Hara): one block =
one batch; the APR observed AT a block is the rate paid during that
block. (Pre-merge Ethereum violated this slightly; post-merge 12 s/block
is rigid enough that block-as-batch holds.)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from decision.base import Action, BlockState, DecisionPolicy, BLOCKS_PER_YEAR

DEFAULT_GAS_USED = 200_000
DEFAULT_GAS_PRICE_GWEI = 25.0
DEFAULT_ETH_PRICE_USD = 3500.0


@dataclass(frozen=True)
class ReplaySummary:
    n_blocks: int
    n_switches: int
    total_gas_usd: float
    final_position_usd: float
    net_apr_annualized: float
    max_drawdown: float


class EventReplayEngine:
    def __init__(
        self,
        *,
        initial_capital_usd: float = 1_000_000.0,
        gas_used_estimate: int = DEFAULT_GAS_USED,
        default_gas_price_gwei: float = DEFAULT_GAS_PRICE_GWEI,
        default_eth_price_usd: float = DEFAULT_ETH_PRICE_USD,
    ) -> None:
        self.initial_capital_usd = initial_capital_usd
        self.gas_used_estimate = gas_used_estimate
        self.default_gas_price_gwei = default_gas_price_gwei
        self.default_eth_price_usd = default_eth_price_usd

    def _row_to_state(self, row, position_usd, current_protocol) -> BlockState:
        """Build a BlockState from one panel row + engine accruals."""
        # Identify protocols dynamically from column suffixes.
        protos = tuple(sorted({
            c.removesuffix("_lending_apr")
            for c in row.index
            if c.endswith("_lending_apr")
        }))

        def _get(col, default=float("nan")):
            return float(row[col]) if col in row.index else default

        lending = {p: _get(f"{p}_lending_apr") for p in protos}
        util = {p: _get(f"{p}_utilization") for p in protos}
        tvl = {p: _get(f"{p}_tvl_usd") for p in protos}

        gas_gwei = _get("gas_price_gwei", self.default_gas_price_gwei)
        eth_usd = _get("eth_price_usd", _get("eth_usd", self.default_eth_price_usd))

        # Populate aux dict with F1/F4 + signal-class columns. T3HazardPolicy
        # reads from this when its trained artifact references features
        # outside the F3 fragmentation family (computed from lending_apr).
        aux: dict[str, float] = {}
        for c in row.index:
            if c.startswith(("f1_", "f4_")) or c in (
                "eth_usd", "usdc_peg_dev_bp", "usdc_peg", "usdt_peg",
            ):
                v = row[c]
                if isinstance(v, (int, float)) or (
                    hasattr(v, "dtype") and "float" in str(v.dtype)
                ):
                    try:
                        aux[c] = float(v)
                    except (TypeError, ValueError):
                        pass

        return BlockState(
            block_number=int(row["block_number"]),
            block_timestamp=pd.Timestamp(row["block_timestamp"]),
            protocols=protos,
            lending_apr=lending,
            utilization=util,
            tvl_usd=tvl,
            current_protocol=current_protocol,
            position_usd=position_usd,
            gas_price_gwei=gas_gwei,
            eth_price_usd=eth_usd,
            gas_used_estimate=self.gas_used_estimate,
            aux=aux,
        )

    def run(self, *, panel: pd.DataFrame, policy: DecisionPolicy):
        position_usd = self.initial_capital_usd
        current_protocol: str | None = None
        cumulative_gas = 0.0
        n_switches = 0

        eq_block: list[int] = []
        eq_position: list[float] = []
        eq_current: list[str | None] = []

        for _, row in panel.iterrows():
            # Accrue at the CURRENT protocol's APR before letting the
            # policy decide on this block (the decision sees the new
            # state, but the accrual is for the period that just ended).
            if current_protocol is not None:
                apr = float(row.get(f"{current_protocol}_lending_apr", float("nan")))
                if not math.isnan(apr):
                    position_usd *= (1 + apr / BLOCKS_PER_YEAR)

            state = self._row_to_state(row, position_usd, current_protocol)
            action = policy.decide(state)

            if action.kind == "switch":
                cost = DecisionPolicy.gas_cost_usd(state)
                position_usd -= cost
                cumulative_gas += cost
                n_switches += 1
                current_protocol = action.target_protocol

            eq_block.append(state.block_number)
            eq_position.append(position_usd)
            eq_current.append(current_protocol)

        eq = pd.DataFrame({
            "block_number": eq_block,
            "position_usd": eq_position,
            "current_protocol": eq_current,
        })

        if len(eq) == 0:
            summary = ReplaySummary(0, 0, 0.0, self.initial_capital_usd, 0.0, 0.0)
            return eq, summary

        final = eq_position[-1]
        n_blocks = len(eq)
        years_elapsed = n_blocks / BLOCKS_PER_YEAR
        # Annualized return (geometric).
        if years_elapsed > 0 and final > 0:
            net_apr_annualized = (final / self.initial_capital_usd) ** (1 / years_elapsed) - 1
        else:
            net_apr_annualized = 0.0
        running_max = np.maximum.accumulate(eq_position)
        drawdowns = (np.array(eq_position) - running_max) / running_max
        max_drawdown = float(drawdowns.min()) if len(drawdowns) > 0 else 0.0

        summary = ReplaySummary(
            n_blocks=n_blocks,
            n_switches=n_switches,
            total_gas_usd=cumulative_gas,
            final_position_usd=final,
            net_apr_annualized=net_apr_annualized,
            max_drawdown=max_drawdown,
        )
        return eq, summary
