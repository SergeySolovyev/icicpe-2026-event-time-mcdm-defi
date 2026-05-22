"""Plan B Task 7 — Validation matrix: B1-B4 baselines + T1 + T2 on the
same per-block panel slice.

Reads `data/cached/per_block_panel.parquet`, slices to the
Sept-Dec 2025 validation window, runs every policy through the
event-time replay engine, and emits `results/tables/plan_b_validation_matrix.csv`
with one row per policy (sharpe_annual, net_apy, max_drawdown,
n_rebalances, gas_spent_usd, final_equity_usd).

Designed to run even on a PARTIAL panel (e.g. when only Morpho + Euler
columns are present because Kaggle secrets are not yet bound for the
other 5 protocols). The replay engine extracts available protocols
dynamically from `<proto>_lending_apr` columns, so the matrix runs
with whatever data is present and produces a comparable cross-policy
ranking.

CLI:
    python -m backtest.run_validation_matrix
        [--start 2025-09-01] [--end 2026-01-01]
        [--panel data/cached/per_block_panel.parquet]
        [--out results/tables/plan_b_validation_matrix.csv]
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

from backtest.replay_per_block import EventReplayEngine
from backtest.run_baselines_event_time import (
    AlwaysAavePolicy,
    AlwaysCompoundPolicy,
    GreedySpotPolicy,
    MCDMEmaPolicy,
)
from decision.base import DecisionPolicy
from decision.ou_calibrator import OUParams
from decision.t1_threshold import T1ThresholdPolicy
from decision.t2_optimal_stopping import T2OptimalStoppingPolicy


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PANEL = ROOT / "data" / "cached" / "per_block_panel.parquet"
DEFAULT_OUT = ROOT / "results" / "tables" / "plan_b_validation_matrix.csv"


def _build_policies() -> list[DecisionPolicy]:
    """Return one fresh instance per policy class.

    T2 needs an OU prior; we seed with weak-mean-reversion defaults so
    the first ~5000 blocks defer to T1 while the calibrator collects
    real spread data and refits.
    """
    return [
        AlwaysAavePolicy(),
        AlwaysCompoundPolicy(),
        GreedySpotPolicy(),
        MCDMEmaPolicy(),
        T1ThresholdPolicy(),
        T2OptimalStoppingPolicy(
            initial_params=OUParams(kappa=1e-5, theta=0.0, sigma=0.001),
            recalibrate_every=5000,
            window=5000,
        ),
    ]


def _slice_panel(
    panel: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """Slice panel by block_timestamp [start, end). Validates input."""
    if panel["block_timestamp"].dt.tz is None:
        panel = panel.copy()
        panel["block_timestamp"] = panel["block_timestamp"].dt.tz_localize("UTC")
    mask = (panel["block_timestamp"] >= start) & (panel["block_timestamp"] < end)
    out = panel.loc[mask].reset_index(drop=True)
    return out


def _summarize(summary, n_blocks: int) -> dict[str, float]:
    """Convert ReplaySummary (B5 subagent's actual field names) to a flat
    dict suitable for CSV row.

    Field-name alignment note: the B5 subagent named fields
    n_switches / final_position_usd / net_apr_annualized / max_drawdown
    (no Sharpe field in this version). We compute Sharpe externally if
    needed; for the validation matrix CSV we expose the raw fields the
    engine returned so downstream consumers (paper figures, plan D) can
    read directly.
    """
    return {
        "n_blocks": n_blocks,
        "n_rebalances": summary.n_switches,
        "net_apy_pct": summary.net_apr_annualized * 100.0,
        "max_drawdown_pct": summary.max_drawdown * 100.0,
        "gas_spent_usd": summary.total_gas_usd,
        "final_equity_usd": summary.final_position_usd,
    }


def run(*, panel_path: Path, out_path: Path,
        start: pd.Timestamp, end: pd.Timestamp,
        initial_position_usd: float = 1_000_000.0,
        constant_gas_gwei: float = 25.0,
        constant_eth_price_usd: float = 3500.0,
        constant_gas_used: int = 200_000) -> pd.DataFrame:
    """Run all policies and write the matrix CSV."""
    if not panel_path.exists():
        raise FileNotFoundError(
            f"panel not found at {panel_path}. Run Kaggle build kernel or "
            f"the local stitcher first."
        )
    panel = pd.read_parquet(panel_path)
    slice_df = _slice_panel(panel, start=start, end=end)
    if len(slice_df) == 0:
        raise ValueError(
            f"No blocks in [{start}, {end}) -- panel spans "
            f"[{panel['block_timestamp'].min()}, "
            f"{panel['block_timestamp'].max()}]"
        )

    proto_cols = [c for c in slice_df.columns if c.endswith("_lending_apr")]
    protocols = tuple(sorted(c[: -len("_lending_apr")] for c in proto_cols))
    print(f"[matrix] panel slice: {len(slice_df):,} blocks  "
          f"protocols={protocols}  "
          f"window=[{slice_df['block_timestamp'].min()}, "
          f"{slice_df['block_timestamp'].max()}]")

    rows = []
    for policy in _build_policies():
        engine = EventReplayEngine(
            initial_capital_usd=initial_position_usd,
            gas_used_estimate=constant_gas_used,
            default_gas_price_gwei=constant_gas_gwei,
            default_eth_price_usd=constant_eth_price_usd,
        )
        equity_df, summary = engine.run(panel=slice_df, policy=policy)
        row = {"policy": policy.name, **_summarize(summary, len(slice_df))}
        rows.append(row)
        print(
            f"  [{policy.name:<24s}] "
            f"apy={row['net_apy_pct']:+6.2f}%  "
            f"max_dd={row['max_drawdown_pct']:+6.2f}%  "
            f"n_rebal={row['n_rebalances']:>4d}  "
            f"gas=${row['gas_spent_usd']:>7.2f}  "
            f"final=${row['final_equity_usd']:>11,.0f}"
        )

    out_df = pd.DataFrame(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_path, index=False)
    print(f"[matrix] wrote {out_path} ({len(out_df)} policies, "
          f"{len(out_df.columns)} cols)")
    return out_df


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2025-09-01",
                    help="ISO date, validation slice start (default 2025-09-01)")
    ap.add_argument("--end", default="2026-01-01",
                    help="ISO date, validation slice end exclusive (default 2026-01-01)")
    ap.add_argument("--panel", default=str(DEFAULT_PANEL),
                    help="Path to per_block_panel.parquet")
    ap.add_argument("--out", default=str(DEFAULT_OUT),
                    help="Output CSV path")
    args = ap.parse_args(argv)

    run(
        panel_path=Path(args.panel),
        out_path=Path(args.out),
        start=pd.Timestamp(args.start, tz="UTC"),
        end=pd.Timestamp(args.end, tz="UTC"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
