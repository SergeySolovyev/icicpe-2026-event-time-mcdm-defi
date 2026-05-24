"""Plan D Task 1 — Test-window matrix: B1-B4 + T1 + T2 + T3 (when available)
on the Jan-Apr 2026 held-out TEST window.

Mirrors `backtest/run_validation_matrix.py` (Plan B7) but:
  * Default window is the locked TEST window 2026-01-01 .. 2026-05-01.
  * Includes T3HazardPolicy when --include-t3 is set AND a JSON artifact
    (T3TrainingArtifact sidecar from Plan C Task 5) exists at the
    expected path.
  * Also writes per-policy equity-curve parquets to a separate directory
    so downstream tasks (D2 bootstrap, D3 regime breakdown, D7 figure)
    can re-read them without re-replaying the engine 3x per policy.

API divergence from plan-doc: T3HazardPolicy consumes a JSON sidecar
(produced by `decision.t3_train.T3TrainingArtifact.save_json`), not an
ONNX file. ONNX export is deferred to Plan E Task E1 (live-agent
integration). The CLI flag is still `--t3-model` but the default path
is `.../t3_cox.json` instead of `.onnx`.

CLI:
    python -m backtest.run_test_matrix
        [--start 2026-01-01] [--end 2026-05-01]
        [--panel data/cached/per_block_panel.parquet]
        [--out results/tables/test_matrix.csv]
        [--equity-dir results/tables/equity/]
        [--include-t3]
        [--t3-model results/models/t3_cox.json]
"""
from __future__ import annotations

import argparse
from pathlib import Path

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
DEFAULT_OUT = ROOT / "results" / "tables" / "test_matrix.csv"
DEFAULT_EQUITY_DIR = ROOT / "results" / "tables" / "equity"
DEFAULT_T3_MODEL = ROOT / "results" / "models" / "t3_cox.json"
DEFAULT_START = pd.Timestamp("2026-01-01", tz="UTC")
DEFAULT_END = pd.Timestamp("2026-05-01", tz="UTC")


def _build_policies(
    *, include_t3: bool, t3_model: Path
) -> list[DecisionPolicy]:
    """Return one fresh instance per policy class.

    T2 needs an OU prior; we seed with weak-mean-reversion defaults so
    the first ~5000 blocks defer to T1 while the calibrator collects
    real spread data and refits (identical to Plan B's val matrix).
    T3 is opt-in because it requires a trained artifact from Plan C.
    """
    policies: list[DecisionPolicy] = [
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
    if include_t3:
        from decision.t3_hazard import T3HazardPolicy

        policies.append(T3HazardPolicy.from_json(t3_model))
    return policies


def _slice_panel(
    panel: pd.DataFrame, *, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    if panel["block_timestamp"].dt.tz is None:
        panel = panel.copy()
        panel["block_timestamp"] = panel["block_timestamp"].dt.tz_localize("UTC")
    mask = (panel["block_timestamp"] >= start) & (panel["block_timestamp"] < end)
    return panel.loc[mask].reset_index(drop=True)


def _summarize(summary, n_blocks: int) -> dict[str, float]:
    """Flatten the B5 ReplaySummary into the canonical matrix row.

    B5's field names are: n_switches, total_gas_usd, final_position_usd,
    net_apr_annualized, max_drawdown. We rename to the matrix-CSV
    convention so D2/D3/D5 consume one shape.
    """
    return {
        "n_blocks": n_blocks,
        "n_rebalances": summary.n_switches,
        "net_apy_pct": summary.net_apr_annualized * 100.0,
        "max_drawdown_pct": summary.max_drawdown * 100.0,
        "gas_spent_usd": summary.total_gas_usd,
        "final_equity_usd": summary.final_position_usd,
    }


def run(
    *,
    panel_path: Path,
    out_path: Path,
    equity_dir: Path,
    start: pd.Timestamp = DEFAULT_START,
    end: pd.Timestamp = DEFAULT_END,
    include_t3: bool = True,
    t3_model: Path = DEFAULT_T3_MODEL,
    initial_position_usd: float = 1_000_000.0,
    constant_gas_gwei: float = 25.0,
    constant_eth_price_usd: float = 3500.0,
    constant_gas_used: int = 200_000,
) -> pd.DataFrame:
    """Execute the test-window matrix; write CSV + per-policy equity parquets."""
    if not panel_path.exists():
        raise FileNotFoundError(f"panel not found at {panel_path}")
    panel = pd.read_parquet(panel_path)
    slice_df = _slice_panel(panel, start=start, end=end)
    if len(slice_df) == 0:
        raise ValueError(
            f"No blocks in [{start}, {end}) — panel spans "
            f"[{panel['block_timestamp'].min()}, "
            f"{panel['block_timestamp'].max()}]"
        )

    proto_cols = [c for c in slice_df.columns if c.endswith("_lending_apr")]
    protocols = tuple(sorted(c[: -len("_lending_apr")] for c in proto_cols))
    print(
        f"[D1 matrix] slice {len(slice_df):,} blocks  protocols={protocols}  "
        f"window=[{slice_df['block_timestamp'].min()}, "
        f"{slice_df['block_timestamp'].max()}]"
    )

    equity_dir.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for policy in _build_policies(include_t3=include_t3, t3_model=t3_model):
        engine = EventReplayEngine(
            initial_capital_usd=initial_position_usd,
            gas_used_estimate=constant_gas_used,
            default_gas_price_gwei=constant_gas_gwei,
            default_eth_price_usd=constant_eth_price_usd,
        )
        equity_df, summary = engine.run(panel=slice_df, policy=policy)
        # Attach block_timestamp so D2/D3 can resample without
        # re-joining the panel.
        equity_df = equity_df.merge(
            slice_df[["block_number", "block_timestamp"]],
            on="block_number",
            how="left",
        )
        equity_path = equity_dir / f"equity_{policy.name}.parquet"
        equity_df.to_parquet(equity_path)

        row = {"policy": policy.name, **_summarize(summary, len(slice_df))}
        rows.append(row)
        print(
            f"  [{policy.name:<24s}] apy={row['net_apy_pct']:+6.2f}%  "
            f"max_dd={row['max_drawdown_pct']:+6.2f}%  "
            f"n_rebal={row['n_rebalances']:>4d}  "
            f"gas=${row['gas_spent_usd']:>7.2f}  "
            f"final=${row['final_equity_usd']:>11,.0f}"
        )

    out_df = pd.DataFrame(rows)
    out_df.to_csv(out_path, index=False)
    print(f"[D1 matrix] wrote {out_path} ({len(out_df)} policies)")
    return out_df


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default=str(DEFAULT_START.date()))
    ap.add_argument("--end", default=str(DEFAULT_END.date()))
    ap.add_argument("--panel", default=str(DEFAULT_PANEL))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--equity-dir", default=str(DEFAULT_EQUITY_DIR))
    ap.add_argument("--include-t3", action="store_true")
    ap.add_argument("--t3-model", default=str(DEFAULT_T3_MODEL))
    args = ap.parse_args(argv)

    run(
        panel_path=Path(args.panel),
        out_path=Path(args.out),
        equity_dir=Path(args.equity_dir),
        start=pd.Timestamp(args.start, tz="UTC"),
        end=pd.Timestamp(args.end, tz="UTC"),
        include_t3=args.include_t3,
        t3_model=Path(args.t3_model),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
