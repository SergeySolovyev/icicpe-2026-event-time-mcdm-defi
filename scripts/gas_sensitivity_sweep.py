"""Gas-sensitivity sweep (addresses limitations-audit finding #2).

The panel's `gas_price_gwei` column is a flat 25 gwei (real gas history
was never fetched; data/fetch_f4_signals.py falls back to a constant).
The replay engine reads that column, so every headline number assumes
25 gwei. This script bounds the "gas-aware" claim by re-running the
leakage-free policies (T1, T2) on the test window at a range of CONSTANT
gas levels, overwriting the panel's gas column before each replay.

It answers: how do net APY and rebalance count degrade as gas rises from
calm (10 gwei) to congested (100 gwei)? A genuinely gas-aware policy
should rebalance less and retain a positive (if smaller) edge as gas
climbs, rather than collapsing.

Output: results/institutional/tables/gas_sensitivity.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest.replay_per_block import EventReplayEngine
from decision.t1_threshold import T1ThresholdPolicy
from decision.t2_optimal_stopping import T2OptimalStoppingPolicy, OUParams

GAS_LEVELS_GWEI = [10.0, 25.0, 50.0, 100.0, 200.0]
TEST_START = pd.Timestamp("2026-01-01", tz="UTC")
TEST_END = pd.Timestamp("2026-05-01", tz="UTC")


def _net_apy(eq_df: pd.DataFrame) -> float:
    initial = float(eq_df["position_usd"].iloc[0])
    final = float(eq_df["position_usd"].iloc[-1])
    years = max(len(eq_df) / (365 * 24 * 60 * 60 // 12), 1e-9)
    return ((final / initial) ** (1.0 / years) - 1) * 100.0


def _make_t1():
    return T1ThresholdPolicy()


def _make_t2():
    return T2OptimalStoppingPolicy(
        initial_params=OUParams(kappa=1e-5, theta=0.0, sigma=0.001),
        recalibrate_every=5000, window=5000)


def main() -> int:
    panel = pd.read_parquet(ROOT / "data/cached/per_block_panel.parquet")
    panel["block_timestamp"] = pd.to_datetime(panel["block_timestamp"], utc=True)
    mask = (panel.block_timestamp >= TEST_START) & (panel.block_timestamp < TEST_END)
    base = panel.loc[mask].reset_index(drop=True)
    print(f"test window: {len(base):,} blocks", flush=True)

    rows = []
    for gwei in GAS_LEVELS_GWEI:
        slice_df = base.copy()
        slice_df["gas_price_gwei"] = gwei  # overwrite the flat-25 column
        for name, make in (("t1_threshold", _make_t1), ("t2_optimal_stopping", _make_t2)):
            engine = EventReplayEngine(
                initial_capital_usd=1_000_000.0, gas_used_estimate=200_000,
                default_gas_price_gwei=gwei, default_eth_price_usd=3500.0)
            eq, summary = engine.run(panel=slice_df, policy=make())
            rows.append({
                "gas_gwei": gwei,
                "policy": name,
                "net_apy_pct": _net_apy(eq),
                "n_rebalances": summary.n_switches,
                "gas_spent_usd": summary.total_gas_usd,
                "final_equity_usd": summary.final_position_usd,
            })
            print(f"  gas={gwei:>5.0f} gwei  {name:<22} "
                  f"apy={rows[-1]['net_apy_pct']:+.3f}%  "
                  f"reb={summary.n_switches:>4}  gas=${summary.total_gas_usd:>8.0f}",
                  flush=True)

    out = pd.DataFrame(rows)
    out_csv = ROOT / "results/institutional/tables/gas_sensitivity.csv"
    out.to_csv(out_csv, index=False)
    print("\n" + out.to_string(), flush=True)
    print(f"\nwrote {out_csv}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
