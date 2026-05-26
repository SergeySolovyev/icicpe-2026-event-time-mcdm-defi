"""Trigger script: run after walk_forward.csv materialises.

Re-runs the downstream pipeline (figures, render, paper-deriv) to
replace the pending-state placeholder in §02 with real walk-forward
numbers, inject walk-forward macros into the Vol-2 paper, and prep
a single commit covering all derived artifacts.

This is decoupled from build_dossier.py so the long-running
walk-forward replay can run once and the post-processing can be
re-triggered without waiting for replay again."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _run(args: list[str]) -> None:
    print(f"$ {' '.join(args)}")
    r = subprocess.run(args, cwd=ROOT)
    if r.returncode != 0:
        raise SystemExit(r.returncode)


def main() -> int:
    py = sys.executable
    wf_csv = ROOT / "results/institutional/tables/walk_forward.csv"
    if not wf_csv.exists():
        print(f"[finalize] walk_forward.csv missing at {wf_csv}")
        print(f"[finalize] aborting -- run scripts.dossier.walk_forward_validation first")
        return 1
    # 1. Rebuild figures (now with real walk_forward_heatmap)
    _run([py, "-m", "scripts.dossier.build_dossier_figures"])
    # 2. Re-render all 8 chapters (now with §02 populated)
    _run([py, "-m", "scripts.dossier.render_dossier"])
    # 3. Inject walk-forward macros into Vol-2 paper
    _run([py, "-m", "scripts.dossier.derive_paper_sections"])
    print()
    print("=== Finalize complete ===")
    print(f"  walk-forward data:  {wf_csv}")
    print(f"  dossier chapters:   {ROOT}/docs/institutional/")
    print(f"  paper macros:       {ROOT}/papers/icicpe-scopus-vol2/sections/results_macros.tex")
    print()
    print("Next steps:")
    print("  - Rebuild paper PDF: scripts.build_vol2_submission + latexmk")
    print("  - Re-run audit gates: scripts.audit_page_budget on the new PDF")
    print("  - Build submission zip: scripts.build_submission_zip --check")
    print("  - Commit all derived artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
