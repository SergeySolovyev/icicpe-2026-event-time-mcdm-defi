"""CLI driver: equity parquets -> institutional_metrics.csv.

Reads per-policy equity parquets, aggregates each to daily, computes
all institutional metrics from scripts.dossier.metrics, writes one CSV
row per policy. Information Ratio is computed against the configured
benchmark policy (default: b1_always_aave).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.dossier.metrics import (
    sharpe, sortino, calmar, information_ratio,
    max_drawdown, max_drawdown_duration, time_to_recovery,
    cvar, skew_kurt, daily_from_block_equity,
)


def _load_daily_equity(parquet_path: Path) -> pd.Series:
    df = pd.read_parquet(parquet_path)
    if "block_timestamp" not in df.columns or "position_usd" not in df.columns:
        raise ValueError(f"{parquet_path} missing required columns")
    eq = df.set_index(pd.DatetimeIndex(df["block_timestamp"]))["position_usd"]
    return daily_from_block_equity(eq)


def compute(*, equity_dir: Path, out_csv: Path,
            benchmark_policy: str = "b1_always_aave") -> pd.DataFrame:
    equity_dir = Path(equity_dir)
    files = sorted(equity_dir.glob("equity_*.parquet"))
    if not files:
        raise FileNotFoundError(f"no equity_*.parquet in {equity_dir}")
    daily = {}
    for f in files:
        policy = f.stem[len("equity_"):]
        daily[policy] = _load_daily_equity(f)
    if benchmark_policy not in daily:
        raise KeyError(f"benchmark {benchmark_policy!r} not in {list(daily)}")

    bench_returns = daily[benchmark_policy].pct_change().dropna()

    rows = []
    for policy, eq in daily.items():
        ret = eq.pct_change().dropna()
        n_days = len(eq)
        if n_days < 2:
            continue
        initial = float(eq.iloc[0])
        final = float(eq.iloc[-1])
        years = n_days / 365.0
        apy = (final / initial) ** (1.0 / max(years, 1e-9)) - 1.0
        mdd = max_drawdown(eq)
        sk, kt = skew_kurt(ret)
        rows.append({
            "policy": policy,
            "net_apy_pct": apy * 100,
            "sharpe": sharpe(ret, periods_per_year=365),
            "sortino": sortino(ret, periods_per_year=365),
            "calmar": calmar(apy, mdd),
            "information_ratio_vs_benchmark":
                information_ratio(ret, bench_returns.reindex(ret.index).fillna(0),
                                  periods_per_year=365)
                if policy != benchmark_policy else 0.0,
            "max_drawdown_pct": mdd * 100,
            "max_drawdown_duration_days": max_drawdown_duration(eq),
            "time_to_recovery_days": time_to_recovery(eq),
            "cvar_95_pct": cvar(ret, 0.05) * 100,
            "cvar_99_pct": cvar(ret, 0.01) * 100,
            "skew": sk,
            "kurtosis_excess": kt,
            "final_equity_usd": final,
        })
    df = pd.DataFrame(rows)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)
    return df


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--equity-dir", default="results/tables/equity")
    ap.add_argument("--out", default="results/institutional/tables/institutional_metrics.csv")
    ap.add_argument("--benchmark", default="b1_always_aave")
    args = ap.parse_args(argv)
    df = compute(equity_dir=Path(args.equity_dir), out_csv=Path(args.out),
                 benchmark_policy=args.benchmark)
    print(df.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
