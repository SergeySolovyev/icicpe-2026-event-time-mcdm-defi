"""Run T1 + B1 + T2 walk-forward across all 6 windows on the 6-protocol panel.

Bypasses scripts.dossier.walk_forward_validation.run()'s file-naming bug
(it always writes w1_*.parquet for single-window inputs by indexing the
windows list from 0). Instead we call the EventReplayEngine directly
and write to canonical wN_<policy>.parquet names per window.

Reads `data/cached/per_block_panel.parquet` (extended to 6 protocols by
scripts.extend_panel_to_6way). Writes:

* `results/institutional/tables/equity_walk_forward_6way/wN_<policy>.parquet`
* `results/institutional/tables/walk_forward_6way.csv`

Resumable: skips any (window, policy) pair whose equity parquet already
exists. Delete the parquet to force a re-run.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest.replay_per_block import EventReplayEngine
from decision.t1_threshold import T1ThresholdPolicy
from decision.t2_optimal_stopping import T2OptimalStoppingPolicy, OUParams
from scripts.dossier.metrics import sharpe, sortino, max_drawdown, daily_from_block_equity


class _AlwaysAave:
    name = "b1_always_aave"
    def decide(self, state):
        from decision.base import Action
        if state.current_protocol == "aave_v3":
            return Action(kind="hold", target_protocol=None, rationale="passive")
        return Action(kind="switch", target_protocol="aave_v3", rationale="cold start / drift")


WINDOWS = [
    ("W1", pd.Timestamp("2024-11-01", tz="UTC"), pd.Timestamp("2025-02-01", tz="UTC")),
    ("W2", pd.Timestamp("2025-02-01", tz="UTC"), pd.Timestamp("2025-05-01", tz="UTC")),
    ("W3", pd.Timestamp("2025-05-01", tz="UTC"), pd.Timestamp("2025-08-01", tz="UTC")),
    ("W4", pd.Timestamp("2025-08-01", tz="UTC"), pd.Timestamp("2025-11-01", tz="UTC")),
    ("W5", pd.Timestamp("2025-11-01", tz="UTC"), pd.Timestamp("2026-02-01", tz="UTC")),
    ("W6", pd.Timestamp("2026-02-01", tz="UTC"), pd.Timestamp("2026-04-30 23:59:59", tz="UTC")),
]


def _build_policy(name: str):
    if name == "t1_threshold":
        return T1ThresholdPolicy()
    if name == "t2_optimal_stopping":
        return T2OptimalStoppingPolicy(
            initial_params=OUParams(kappa=1e-5, theta=0.0, sigma=0.001),
            recalibrate_every=5000, window=5000,
        )
    if name == "b1_always_aave":
        return _AlwaysAave()
    raise ValueError(name)


def main(policies: tuple[str, ...] = ("b1_always_aave", "t1_threshold", "t2_optimal_stopping")) -> int:
    panel_path = ROOT / "data/cached/per_block_panel.parquet"
    eq_dir = ROOT / "results/institutional/tables/equity_walk_forward_6way"
    eq_dir.mkdir(parents=True, exist_ok=True)
    out_csv = ROOT / "results/institutional/tables/walk_forward_6way.csv"

    print(f"loading {panel_path}", flush=True)
    panel = pd.read_parquet(panel_path)
    panel["block_timestamp"] = pd.to_datetime(panel["block_timestamp"], utc=True)
    panel = panel.sort_values("block_timestamp").reset_index(drop=True)
    print(f"panel rows: {len(panel):,}", flush=True)

    rows = []
    for wid, s, e in WINDOWS:
        slice_df = panel[(panel.block_timestamp >= s) & (panel.block_timestamp < e)].reset_index(drop=True)
        if len(slice_df) < 100:
            print(f"[{wid}] <100 blocks, skipping", flush=True)
            continue
        print(f"[{wid}] {len(slice_df):,} blocks {s.date()}..{e.date()}", flush=True)
        for pol_name in policies:
            out_pq = eq_dir / f"w{int(wid[1:])}_{pol_name}.parquet"
            if out_pq.exists():
                print(f"  [{pol_name}] skip — {out_pq.name} exists", flush=True)
                # Still need to load summary for the CSV row
                eq_df = pd.read_parquet(out_pq)
            else:
                t0 = time.time()
                policy = _build_policy(pol_name)
                engine = EventReplayEngine(initial_capital_usd=1_000_000.0,
                                           gas_used_estimate=200_000,
                                           default_gas_price_gwei=25.0,
                                           default_eth_price_usd=3500.0)
                eq_df, summary = engine.run(panel=slice_df, policy=policy)
                eq_df = eq_df.merge(slice_df[["block_number", "block_timestamp"]],
                                    on="block_number", how="left")
                eq_df.to_parquet(out_pq)
                print(f"  [{pol_name}] done in {time.time()-t0:.0f}s, "
                      f"n_switches={summary.n_switches}, "
                      f"final={eq_df.position_usd.iloc[-1]:.2f}", flush=True)
            # Compute per-window stats from equity
            initial = float(eq_df.position_usd.iloc[0])
            final = float(eq_df.position_usd.iloc[-1])
            n_blocks = len(eq_df)
            years = max(n_blocks / (365 * 24 * 60 * 60 // 12), 1e-9)
            apy = (final / initial) ** (1.0 / years) - 1
            eq_df["block_timestamp"] = pd.to_datetime(eq_df["block_timestamp"], utc=True)
            eq = eq_df.set_index(pd.DatetimeIndex(eq_df["block_timestamp"]))["position_usd"]
            eq_daily = daily_from_block_equity(eq)
            ret = eq_daily.pct_change().dropna()
            n_rebal = 0
            if "current_protocol" in eq_df.columns:
                n_rebal = int(eq_df["current_protocol"].ne(eq_df["current_protocol"].shift()).sum() - 1)
            rows.append({
                "window_id": wid,
                "window_start": s.date().isoformat(),
                "window_end": e.date().isoformat(),
                "policy": pol_name,
                "n_blocks": n_blocks,
                "net_apy_pct": apy * 100,
                "sharpe": sharpe(ret, periods_per_year=365),
                "sortino": sortino(ret, periods_per_year=365),
                "max_drawdown_pct": max_drawdown(eq_daily) * 100,
                "n_rebalances": n_rebal,
            })

    out = pd.DataFrame(rows)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_csv, index=False)
    print(out.to_string(), flush=True)
    print(f"\nwrote {out_csv}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
