"""Decisive experiment (audit completeness-critic, highest leverage):
does the gas-aware T1 threshold actually beat NAIVE greedy APR-chasing,
and WHERE does the gas-awareness earn its keep?

On the real-gas test window (~0.3 gwei) T1 beats b3_greedy_spot by only
+1.5 bp net APY (5.368 vs 5.353) -- gas is nearly free, so throttling
barely matters. The paper's gas-sensitivity sweep includes only T1/T2,
never greedy, so the comparison that JUSTIFIES the gas-aware threshold
(greedy collapses as gas rises because it switches ~424x ignoring cost;
T1 throttles) was never run. This script runs it: greedy vs T1 across
10/25/50/100/200 gwei on the test window, and reports T1 - greedy at
each level.

Hypothesis: T1 ~= greedy at ~0 gwei but greedy goes NEGATIVE at high gas
while T1 stays positive -> the gas-aware threshold's contribution is a
high-gas-regime property, honestly disclosed.

Output: results/institutional/tables/greedy_vs_t1_gas_sensitivity.csv
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest.replay_per_block import EventReplayEngine
from decision.base import Action, BlockState, DecisionPolicy
from decision.t1_threshold import T1ThresholdPolicy

GAS_LEVELS_GWEI = [10.0, 25.0, 50.0, 100.0, 200.0]
TEST_START = pd.Timestamp("2026-01-01", tz="UTC")
TEST_END = pd.Timestamp("2026-05-01", tz="UTC")


class GreedySpotPolicy(DecisionPolicy):
    """b3: switch to the highest-spot-APR protocol every block, NO gas gate.

    This is the naive baseline the gas-aware T1 must beat to justify its
    existence. It ignores gas entirely, so its rebalance count is ~constant
    across gas regimes while its net APY is eaten alive as gas rises.
    """
    name = "b3_greedy_spot"

    def decide(self, state: BlockState) -> Action:
        valid = {p: a for p, a in state.lending_apr.items() if not math.isnan(a)}
        if not valid:
            return Action(kind="hold", target_protocol=None, rationale="no APR data")
        best = max(valid, key=valid.get)
        if state.current_protocol is None or best != state.current_protocol:
            return Action(kind="switch", target_protocol=best,
                          rationale=f"greedy argmax {valid[best]:.4f}")
        return Action(kind="hold", target_protocol=None, rationale="already best")


def _slim(panel: pd.DataFrame) -> pd.DataFrame:
    keep = [c for c in panel.columns
            if c.endswith(("_lending_apr", "_utilization", "_tvl_usd"))
            or c in ("block_number", "block_timestamp", "gas_price_gwei",
                     "eth_price_usd", "eth_usd")]
    return panel[keep]


def main() -> int:
    panel = pd.read_parquet(ROOT / "data/cached/per_block_panel.parquet")
    panel["block_timestamp"] = pd.to_datetime(panel["block_timestamp"], utc=True)
    mask = (panel.block_timestamp >= TEST_START) & (panel.block_timestamp < TEST_END)
    base = _slim(panel.loc[mask].reset_index(drop=True))
    print(f"test window: {len(base):,} blocks", flush=True)

    rows = []
    for gwei in GAS_LEVELS_GWEI:
        slice_df = base.copy()
        slice_df["gas_price_gwei"] = gwei  # overwrite -> constant-gas regime
        for name, make in (("b3_greedy_spot", GreedySpotPolicy),
                           ("t1_threshold", T1ThresholdPolicy)):
            engine = EventReplayEngine(
                initial_capital_usd=1_000_000.0, gas_used_estimate=200_000,
                default_gas_price_gwei=gwei, default_eth_price_usd=3500.0)
            _, summ = engine.run(panel=slice_df, policy=make())
            rows.append({
                "gas_gwei": gwei, "policy": name,
                "net_apy_pct": round(summ.net_apr_annualized * 100, 4),
                "n_rebalances": summ.n_switches,
                "gas_spent_usd": round(summ.total_gas_usd, 2),
            })
            print(f"  {gwei:6.0f} gwei  {name:16s}  "
                  f"net {summ.net_apr_annualized*100:7.3f}%  "
                  f"{summ.n_switches:4d} reb  ${summ.total_gas_usd:,.0f} gas", flush=True)

    df = pd.DataFrame(rows)
    out = ROOT / "results/institutional/tables/greedy_vs_t1_gas_sensitivity.csv"
    df.to_csv(out, index=False)

    # pivot: T1 - greedy at each gas level
    piv = df.pivot(index="gas_gwei", columns="policy", values="net_apy_pct")
    piv["t1_minus_greedy_bp"] = (piv["t1_threshold"] - piv["b3_greedy_spot"]) * 100
    print("\n=== net APY (%) by gas level ===", flush=True)
    print(piv.to_string(), flush=True)
    print(f"\n[ok] wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
