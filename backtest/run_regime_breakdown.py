"""Plan D Task 3 - per-quarter regime-conditional breakdown.

Slice each policy's per-block equity curve (written by D1 to
results/tables/equity/equity_<policy>.parquet) by quarter and compute
(net_apy, sharpe_annual, n_rebalances, final_equity) per cell.

The TEST window covers two of the seven quarters defined in
CLAUDE.md "Project regime structure (CORRECTED)" - 2026-Q1 and
2026-Q2. The Plan D acceptance gate "T3 >= T2 >= T1 >= B4 in >= 3 of 4
quarters" requires running on validation + test combined; we expose
`quarters_with_ordering` for that aggregation.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from decision.base import BLOCKS_PER_YEAR

DEFAULT_GAS_GWEI = 25.0
DEFAULT_ETH_USD = 3500.0
DEFAULT_GAS_USED = 200_000
GAS_USD_PER_SWITCH = (
    DEFAULT_GAS_USED * DEFAULT_GAS_GWEI * 1e-9 * DEFAULT_ETH_USD
)


@dataclass(frozen=True)
class RegimeBreakdownRow:
    """One row in results/tables/regime_breakdown.csv."""
    policy: str
    quarter: str
    n_blocks: int
    net_apy_pct: float
    sharpe_annual: float
    n_rebalances: int
    gas_spent_usd: float
    final_equity_usd: float


@dataclass(frozen=True)
class QuarterSpec:
    label: str
    start: pd.Timestamp
    end: pd.Timestamp  # exclusive


# Locked Plan D regime list - covers TEST window only (D3 default).
TEST_QUARTERS_2026: tuple[QuarterSpec, ...] = (
    QuarterSpec("2026-Q1",
                pd.Timestamp("2026-01-01", tz="UTC"),
                pd.Timestamp("2026-04-01", tz="UTC")),
    QuarterSpec("2026-Q2",
                pd.Timestamp("2026-04-01", tz="UTC"),
                pd.Timestamp("2026-07-01", tz="UTC")),
)

# Full validation + test list per CLAUDE.md "Project regime structure"
# (CORRECTED 2026-05-14). Half-open UTC intervals.
VAL_AND_TEST_QUARTERS_2025_2026: tuple[QuarterSpec, ...] = (
    QuarterSpec("2024-Q4",
                pd.Timestamp("2024-11-01", tz="UTC"),
                pd.Timestamp("2025-01-01", tz="UTC")),
    QuarterSpec("2025-Q1",
                pd.Timestamp("2025-01-01", tz="UTC"),
                pd.Timestamp("2025-04-01", tz="UTC")),
    QuarterSpec("2025-Q2",
                pd.Timestamp("2025-04-01", tz="UTC"),
                pd.Timestamp("2025-07-01", tz="UTC")),
    QuarterSpec("2025-Q3",
                pd.Timestamp("2025-07-01", tz="UTC"),
                pd.Timestamp("2025-10-01", tz="UTC")),
    QuarterSpec("2025-Q4",
                pd.Timestamp("2025-10-01", tz="UTC"),
                pd.Timestamp("2026-01-01", tz="UTC")),
    QuarterSpec("2026-Q1",
                pd.Timestamp("2026-01-01", tz="UTC"),
                pd.Timestamp("2026-04-01", tz="UTC")),
    QuarterSpec("2026-Q2",
                pd.Timestamp("2026-04-01", tz="UTC"),
                pd.Timestamp("2026-07-01", tz="UTC")),
)

# Convenience dict view (half-open UTC intervals).
QUARTER_BOUNDARIES: dict[str, tuple[pd.Timestamp, pd.Timestamp]] = {
    q.label: (q.start, q.end) for q in VAL_AND_TEST_QUARTERS_2025_2026
}


def _net_apy_pct(start_eq: float, end_eq: float, n_blocks: int) -> float:
    if n_blocks <= 0 or start_eq <= 0 or end_eq <= 0:
        return 0.0
    years = n_blocks / BLOCKS_PER_YEAR
    return ((end_eq / start_eq) ** (1 / years) - 1.0) * 100.0


def _sharpe_annual(equity: np.ndarray) -> float:
    if len(equity) < 3:
        return 0.0
    rets = np.diff(equity) / equity[:-1]
    s = float(np.std(rets, ddof=1))
    if s == 0.0:
        return 0.0
    return float(np.mean(rets) / s * np.sqrt(BLOCKS_PER_YEAR))


def _count_switches(current_protocol: pd.Series) -> int:
    """Number of consecutive-row changes in the current_protocol series.
    First row never counts as a switch (it's the initial allocation)."""
    if len(current_protocol) <= 1:
        return 0
    shifted = current_protocol.shift(1)
    return int((current_protocol != shifted).iloc[1:].sum())


def _slice_one(equity: pd.DataFrame, q: QuarterSpec) -> pd.DataFrame:
    ts = pd.DatetimeIndex(equity["block_timestamp"])
    if ts.tz is None:
        equity = equity.copy()
        equity["block_timestamp"] = ts.tz_localize("UTC")
        ts = pd.DatetimeIndex(equity["block_timestamp"])
    mask = (ts >= q.start) & (ts < q.end)
    return equity.loc[mask].reset_index(drop=True)


def slice_quarter(equity_df: pd.DataFrame, quarter_id: str) -> pd.DataFrame:
    """Slice an equity curve by quarter id (e.g. '2026-Q1').

    Looks the quarter up in QUARTER_BOUNDARIES. Returns rows with
    block_timestamp in [start, end), reset_index'd.
    """
    if quarter_id not in QUARTER_BOUNDARIES:
        raise KeyError(
            f"unknown quarter_id={quarter_id!r}; "
            f"known: {sorted(QUARTER_BOUNDARIES)}"
        )
    start, end = QUARTER_BOUNDARIES[quarter_id]
    return _slice_one(equity_df, QuarterSpec(quarter_id, start, end))


def compute_regime_breakdown(
    *, equity_dir: Path,
    quarters: Sequence[QuarterSpec] = TEST_QUARTERS_2026,
) -> pd.DataFrame:
    """Compute one row per (policy, quarter) cell."""
    equity_dir = Path(equity_dir)
    files = sorted(equity_dir.glob("equity_*.parquet"))
    if not files:
        raise FileNotFoundError(f"no equity_*.parquet in {equity_dir}")
    rows = []
    for f in files:
        policy = f.stem[len("equity_"):]
        eq = pd.read_parquet(f)
        for q in quarters:
            sl = _slice_one(eq, q)
            if len(sl) == 0:
                rows.append({
                    "policy": policy, "quarter": q.label,
                    "n_blocks": 0, "net_apy_pct": 0.0,
                    "sharpe_annual": 0.0, "n_rebalances": 0,
                    "gas_spent_usd": 0.0, "final_equity_usd": 0.0,
                })
                continue
            start_eq = float(sl["position_usd"].iloc[0])
            end_eq = float(sl["position_usd"].iloc[-1])
            n_switches = _count_switches(sl["current_protocol"])
            rows.append({
                "policy": policy, "quarter": q.label,
                "n_blocks": int(len(sl)),
                "net_apy_pct": _net_apy_pct(start_eq, end_eq, len(sl)),
                "sharpe_annual": _sharpe_annual(sl["position_usd"].to_numpy()),
                "n_rebalances": n_switches,
                "gas_spent_usd": float(n_switches) * GAS_USD_PER_SWITCH,
                "final_equity_usd": end_eq,
            })
    return pd.DataFrame(rows)


def breakdown_per_policy(
    equity_dir: Path | str,
    quarters: Sequence[QuarterSpec] = TEST_QUARTERS_2026,
    out_path: Path | str = Path("results/tables/regime_breakdown.csv"),
) -> pd.DataFrame:
    """CLI-style helper: compute and persist to `results/tables/regime_breakdown.csv`."""
    df = compute_regime_breakdown(equity_dir=Path(equity_dir), quarters=quarters)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    return df


def quarters_with_ordering(
    breakdown: pd.DataFrame,
    *, ordering: Sequence[str],
    metric: str = "net_apy_pct",
) -> dict[str, int]:
    """Count quarters where policies are ranked by `metric` in `ordering` order.

    Returns {n_quarters_in_order, n_quarters_evaluated, quarters_in_order_labels}.
    """
    n_in_order = 0
    n_eval = 0
    hits = []
    for q, grp in breakdown.groupby("quarter"):
        present = {p: grp.loc[grp["policy"] == p, metric] for p in ordering}
        if any(v.empty for v in present.values()):
            continue
        vals = [float(v.iloc[0]) for v in present.values()]
        n_eval += 1
        if all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1)):
            n_in_order += 1
            hits.append(q)
    return {
        "n_quarters_in_order": n_in_order,
        "n_quarters_evaluated": n_eval,
        "quarters_in_order_labels": hits,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--equity-dir", type=Path,
                        default=Path("results/tables/equity"))
    parser.add_argument("--out", type=Path,
                        default=Path("results/tables/regime_breakdown.csv"))
    parser.add_argument("--full", action="store_true",
                        help="use VAL_AND_TEST_QUARTERS_2025_2026 instead of TEST_QUARTERS_2026")
    args = parser.parse_args()
    qs = VAL_AND_TEST_QUARTERS_2025_2026 if args.full else TEST_QUARTERS_2026
    df = breakdown_per_policy(args.equity_dir, qs, args.out)
    print(df.to_string(index=False))
