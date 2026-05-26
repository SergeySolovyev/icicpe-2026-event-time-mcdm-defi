"""CLI: capacity_curve.csv -> cost_attribution.csv."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from scripts.dossier.mev import mev_sensitivity_table


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--capacity",
                    default="results/institutional/tables/capacity_curve.csv")
    ap.add_argument("--out",
                    default="results/institutional/tables/cost_attribution.csv")
    args = ap.parse_args(argv)
    cap = pd.read_csv(args.capacity)
    df = mev_sensitivity_table(cap)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(df.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
