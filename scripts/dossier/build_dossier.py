"""Single-command rebuild of the entire Institutional Dossier from
the per-block panel + equity parquets. Idempotent.

Skips walk-forward replay if walk_forward.csv already exists (the
24-cell replay is long-running; rerun manually if you want fresh
walk-forward output)."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _run(args: list[str]) -> None:
    print(f"$ {' '.join(args)}")
    r = subprocess.run(args, cwd=ROOT)
    if r.returncode != 0:
        raise SystemExit(r.returncode)


def main(skip_walk_forward: bool = False) -> int:
    py = sys.executable
    _run([py, "-m", "scripts.dossier.compute_institutional_metrics"])
    if not skip_walk_forward:
        wf_csv = ROOT / "results/institutional/tables/walk_forward.csv"
        if not wf_csv.exists():
            print(f"[build_dossier] walk_forward.csv missing; running replay "
                  f"(30-60 min wall-clock). Pass --skip-walk-forward to skip.")
            _run([py, "-m", "scripts.dossier.walk_forward_validation"])
        else:
            print(f"[build_dossier] walk_forward.csv exists; skipping replay")
    _run([py, "-m", "scripts.dossier.capacity_analysis"])
    _run([py, "-m", "scripts.dossier.mev_sensitivity"])
    _run([py, "-m", "scripts.dossier.build_dossier_figures"])
    _run([py, "-m", "scripts.dossier.render_dossier"])
    print()
    print("=== Institutional Dossier built ===")
    print(f"  docs:    {ROOT}/docs/institutional/")
    print(f"  tables:  {ROOT}/results/institutional/tables/")
    print(f"  figures: {ROOT}/results/institutional/figures/")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-walk-forward", action="store_true",
                    help="skip the 30-60min walk-forward replay")
    args = ap.parse_args()
    raise SystemExit(main(skip_walk_forward=args.skip_walk_forward))
