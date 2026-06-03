"""Re-run T1/T2/B1 on the test window with REAL forward-filled gas
(from data/cached/f4_gas_gwei_daily_real.parquet, fetched via
eth_feeHistory) instead of the flat 25 gwei placeholder.

This produces the first honest net-of-real-gas edge — the number the
YC-critic flagged as the load-bearing product figure. Compares directly
to the const-25 headline.

Output: results/institutional/tables/net_of_real_gas.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest.replay_per_block import EventReplayEngine
from decision.base import Action
from decision.t1_threshold import T1ThresholdPolicy
from decision.t2_optimal_stopping import T2OptimalStoppingPolicy, OUParams

TEST_START = pd.Timestamp("2026-01-01", tz="UTC")
TEST_END = pd.Timestamp("2026-05-01", tz="UTC")
REAL_GAS = ROOT / "data/cached/f4_gas_gwei_daily_real.parquet"


class _AlwaysAave:
    name = "b1_always_aave"
    def decide(self, state):
        if state.current_protocol == "aave_v3":
            return Action(kind="hold", target_protocol=None, rationale="passive")
        return Action(kind="switch", target_protocol="aave_v3", rationale="cold")


def _net_apy(eq):
    initial = float(eq["position_usd"].iloc[0]); final = float(eq["position_usd"].iloc[-1])
    years = max(len(eq) / (365 * 24 * 60 * 60 // 12), 1e-9)
    return ((final / initial) ** (1.0 / years) - 1) * 100.0


def main() -> int:
    panel = pd.read_parquet(ROOT / "data/cached/per_block_panel.parquet")
    panel["block_timestamp"] = pd.to_datetime(panel["block_timestamp"], utc=True)

    # Forward-fill real daily gas onto the panel by block_number.
    rg = pd.read_parquet(REAL_GAS).sort_values("block_number")
    merged = pd.merge_asof(
        panel[["block_number"]].sort_values("block_number"),
        rg[["block_number", "gas_gwei"]],
        on="block_number", direction="backward",
    )
    panel = panel.sort_values("block_number").reset_index(drop=True)
    panel["gas_price_gwei_real"] = merged["gas_gwei"].to_numpy()
    # leading blocks before first sample -> first known value
    panel["gas_price_gwei_real"] = panel["gas_price_gwei_real"].bfill()

    mask = (panel.block_timestamp >= TEST_START) & (panel.block_timestamp < TEST_END)
    base = panel.loc[mask].reset_index(drop=True)
    print(f"test window {len(base):,} blocks; real gas mean "
          f"{base['gas_price_gwei_real'].mean():.1f} gwei "
          f"(min {base['gas_price_gwei_real'].min():.1f}, "
          f"max {base['gas_price_gwei_real'].max():.1f})", flush=True)

    def make_policies():
        return [
            ("b1_always_aave", _AlwaysAave()),
            ("t1_threshold", T1ThresholdPolicy()),
            ("t2_optimal_stopping", T2OptimalStoppingPolicy(
                initial_params=OUParams(kappa=1e-5, theta=0.0, sigma=0.001),
                recalibrate_every=5000, window=5000)),
        ]

    rows = []
    for gas_label, gas_col in (("const25", None), ("real", "gas_price_gwei_real")):
        slice_df = base.copy()
        if gas_col is not None:
            slice_df["gas_price_gwei"] = slice_df[gas_col]
        else:
            slice_df["gas_price_gwei"] = 25.0
        for name, pol in make_policies():
            eng = EventReplayEngine(initial_capital_usd=1_000_000.0,
                                    gas_used_estimate=200_000,
                                    default_gas_price_gwei=25.0,
                                    default_eth_price_usd=3500.0)
            eq, summ = eng.run(panel=slice_df, policy=pol)
            rows.append({"gas": gas_label, "policy": name,
                         "net_apy_pct": _net_apy(eq), "n_rebalances": summ.n_switches,
                         "gas_spent_usd": summ.total_gas_usd})
            print(f"  [{gas_label:>7}] {name:<22} apy={rows[-1]['net_apy_pct']:+.3f}%  "
                  f"reb={summ.n_switches:>4}  gas=${summ.total_gas_usd:>8.0f}", flush=True)

    out = pd.DataFrame(rows)
    # T1-vs-Aave edge under each gas regime
    for g in ("const25", "real"):
        sub = out[out.gas == g].set_index("policy")
        edge = sub.loc["t1_threshold", "net_apy_pct"] - sub.loc["b1_always_aave", "net_apy_pct"]
        print(f"\n[{g}] T1 net edge over always-Aave = {edge*100:+.1f} bp", flush=True)
    out.to_csv(ROOT / "results/institutional/tables/net_of_real_gas.csv", index=False)
    print(f"\nwrote results/institutional/tables/net_of_real_gas.csv", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
