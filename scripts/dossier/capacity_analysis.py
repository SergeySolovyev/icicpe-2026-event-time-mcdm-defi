"""CLI driver: per-block panel -> capacity_curve.csv."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from scripts.dossier.capacity import capacity_sweep


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", default="data/cached/per_block_panel.parquet")
    ap.add_argument("--out",
                    default="results/institutional/tables/capacity_curve.csv")
    ap.add_argument("--equity-dir", default="results/tables/equity")
    args = ap.parse_args(argv)
    panel = pd.read_parquet(args.panel)
    panel["block_timestamp"] = pd.to_datetime(panel["block_timestamp"], utc=True)
    df = capacity_sweep(panel=panel, equity_dir=Path(args.equity_dir))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(df.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
