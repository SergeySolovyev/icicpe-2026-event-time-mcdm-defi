"""CLI: run all 4 figure builders from existing CSVs.

Idempotent. Walk-forward heatmap emits a placeholder if walk_forward.csv
hasn't materialised yet (the 24-cell replay takes 30-60min wall-clock).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from scripts.dossier.figures import (
    fig_institutional_summary, fig_walk_forward_heatmap,
    fig_capacity_curve, fig_cost_waterfall,
)


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tables-dir", default="results/institutional/tables")
    ap.add_argument("--figures-dir", default="results/institutional/figures")
    ap.add_argument("--equity-dir", default="results/tables/equity")
    args = ap.parse_args(argv)
    td = Path(args.tables_dir)
    fd = Path(args.figures_dir)
    fd.mkdir(parents=True, exist_ok=True)
    metrics = pd.read_csv(td / "institutional_metrics.csv")
    walk = (
        pd.read_csv(td / "walk_forward.csv")
        if (td / "walk_forward.csv").exists() else pd.DataFrame()
    )
    cap = pd.read_csv(td / "capacity_curve.csv")
    cost = pd.read_csv(td / "cost_attribution.csv")
    fig_institutional_summary(metrics, args.equity_dir,
                              fd / "institutional_summary.png")
    fig_walk_forward_heatmap(walk, fd / "walk_forward_heatmap.png")
    fig_capacity_curve(cap, fd / "capacity_curve.png")
    fig_cost_waterfall(cost, "t1_threshold", fd / "cost_waterfall.png")
    # Generate the N×M paired-bootstrap figure if backing CSVs exist
    nxm_path = Path(args.tables_dir) / "walk_forward_NxM_contrasts.csv"
    if nxm_path.exists():
        # Invoke the standalone N×M figure module
        from subprocess import run as _sp_run
        import sys as _sys
        _sp_run([_sys.executable, "-m", "scripts.dossier.figures_walk_forward"],
                check=False)
        print(f"wrote 5 figures to {fd}")
    else:
        print(f"wrote 4 figures to {fd}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
