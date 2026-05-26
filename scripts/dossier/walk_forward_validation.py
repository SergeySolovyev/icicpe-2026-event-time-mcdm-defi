"""Run the per-block replay engine on each (window, policy) cell.
Output: walk_forward.csv with one row per (window, policy) of
metrics + delta-Sharpe vs benchmark.

For each window: re-instantiate policies fresh (T1 stateless;
T2 OU calibrator refits on the window's first 50k blocks). T3 omitted
from default walk-forward set since on F3-only features it collapses
to T1's decisions (verified empirically - T1 == T3 in test_matrix.csv).

Equity time series for each (window, policy) saved to
results/institutional/equity_walk_forward/ for downstream paired-
delta computation."""
from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import pandas as pd

from backtest.replay_per_block import EventReplayEngine
from decision.t1_threshold import T1ThresholdPolicy
from decision.t2_optimal_stopping import T2OptimalStoppingPolicy, OUParams
from backtest.run_baselines_event_time import AlwaysAavePolicy, MCDMEmaPolicy
from scripts.dossier.walk_forward import WINDOWS
from scripts.dossier.metrics import (
    sharpe, sortino, max_drawdown, daily_from_block_equity,
)


_POLICY_BUILDERS = {
    "b1_always_aave": lambda: AlwaysAavePolicy(),
    "b4_mcdm_ema": lambda: MCDMEmaPolicy(),
    "t1_threshold": lambda: T1ThresholdPolicy(),
    "t2_optimal_stopping": lambda: T2OptimalStoppingPolicy(
        initial_params=OUParams(kappa=1e-5, theta=0.0, sigma=0.001),
        recalibrate_every=5000, window=5000,
    ),
}


def _t3_builder():
    """Lazy T3 builder — loads trained Cox model from disk only when needed.
    Returns None if model artifact missing (e.g. T3 untrained on extension panel)."""
    from pathlib import Path as _P
    from decision.t3_hazard import T3HazardPolicy
    artifact = _P(__file__).resolve().parents[2] / "results/models/t3_cox.json"
    if not artifact.exists():
        return None
    return T3HazardPolicy.from_json(artifact)


_POLICY_BUILDERS["t3_hazard"] = _t3_builder


def _slice_panel(panel: pd.DataFrame, start: pd.Timestamp,
                 end: pd.Timestamp) -> pd.DataFrame:
    mask = (panel["block_timestamp"] >= start) & (panel["block_timestamp"] < end)
    return panel.loc[mask].reset_index(drop=True)


def run(*, panel_path: Path, out_path: Path,
        windows: list[tuple[pd.Timestamp, pd.Timestamp]] = None,
        policies: tuple[str, ...] = (
            "b1_always_aave", "b4_mcdm_ema", "t1_threshold", "t2_optimal_stopping",
        ),
        initial_capital_usd: float = 1_000_000.0,
        equity_out_dir: Path = None,
        ) -> pd.DataFrame:
    if windows is None:
        windows = WINDOWS
    panel = pd.read_parquet(panel_path)
    panel["block_timestamp"] = pd.to_datetime(panel["block_timestamp"], utc=True)

    rows = []
    equity_out_dir = Path(equity_out_dir or out_path.parent / "equity_walk_forward")
    equity_out_dir.mkdir(parents=True, exist_ok=True)

    for w_idx, (start, end) in enumerate(windows):
        slice_df = _slice_panel(panel, start, end)
        if len(slice_df) < 100:
            warnings.warn(f"window {w_idx} ({start}..{end}) has <100 blocks, skipping")
            continue
        for policy_name in policies:
            builder = _POLICY_BUILDERS.get(policy_name)
            if builder is None:
                warnings.warn(f"unknown policy {policy_name!r}, skipping")
                continue
            try:
                policy = builder()
                engine = EventReplayEngine(initial_capital_usd=initial_capital_usd,
                                           gas_used_estimate=200_000,
                                           default_gas_price_gwei=25.0,
                                           default_eth_price_usd=3500.0)
                equity_df, summary = engine.run(panel=slice_df, policy=policy)
                equity_df = equity_df.merge(
                    slice_df[["block_number", "block_timestamp"]],
                    on="block_number", how="left",
                )
                equity_df.to_parquet(
                    equity_out_dir / f"w{w_idx+1}_{policy_name}.parquet"
                )
                eq = equity_df.set_index(pd.DatetimeIndex(equity_df["block_timestamp"]))["position_usd"]
                eq_daily = daily_from_block_equity(eq)
                ret = eq_daily.pct_change().dropna()
                rows.append({
                    "window_id": f"W{w_idx+1}",
                    "window_start": start.date().isoformat(),
                    "window_end": end.date().isoformat(),
                    "policy": policy_name,
                    "n_blocks": len(slice_df),
                    "net_apy_pct": summary.net_apr_annualized * 100.0,
                    "sharpe": sharpe(ret, periods_per_year=365),
                    "sortino": sortino(ret, periods_per_year=365),
                    "max_drawdown_pct": max_drawdown(eq_daily) * 100,
                    "n_rebalances": int(summary.n_switches),
                })
            except Exception as e:
                warnings.warn(f"window {w_idx} policy {policy_name!r}: {type(e).__name__}: {e}")
                continue

    out = pd.DataFrame(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)
    return out


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", default="data/cached/per_block_panel.parquet")
    ap.add_argument("--out", default="results/institutional/tables/walk_forward.csv")
    args = ap.parse_args(argv)
    df = run(panel_path=Path(args.panel), out_path=Path(args.out))
    print(df.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
