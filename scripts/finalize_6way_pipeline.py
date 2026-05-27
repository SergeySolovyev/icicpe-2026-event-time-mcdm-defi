"""Finalize after the 6-way active walk-forward completes.

Runs the canonical post-walk-forward pipeline:
  1. rebuild_nxm_6way_active   — write 18-row N×M matrix (full coverage)
  2. derive_paper_sections     — refresh paper macros from new matrix
  3. render_dossier            — re-render all 8 dossier chapters
  4. figures_walk_forward      — refresh walk_forward_nxm.png
  5. build_vol2_submission     — propagate to submission tree
  6. latexmk -pdf main.tex     — rebuild paper PDF
  7. build_submission_zip      — final zip

Each step prints status; non-zero exit on any failure halts the chain.
This script is the canonical "press the green button after the
expensive compute lands" entry point.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(label: str, cmd: list[str], *, cwd: Path | None = None) -> None:
    print(f"\n=== {label} ===", flush=True)
    p = subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True, text=True)
    print(p.stdout[-2000:])
    if p.returncode != 0:
        print(p.stderr[-2000:], file=sys.stderr)
        raise SystemExit(f"FAIL: {label} exited {p.returncode}")


def main() -> int:
    py = sys.executable

    _run("[1/7] rebuild N×M matrix from 6-way equity files",
         [py, "-m", "scripts.dossier.rebuild_nxm_6way_active"])

    _run("[2/7] derive paper macros from new matrix",
         [py, "-m", "scripts.dossier.derive_paper_sections"])

    _run("[3/7] re-render 8 dossier chapters",
         [py, "-m", "scripts.dossier.render_dossier"])

    _run("[4/7] regenerate N×M paired-bootstrap figure",
         [py, "-m", "scripts.dossier.figures_walk_forward"])

    _run("[5/7] propagate to submission tree",
         [py, "-m", "scripts.build_vol2_submission"])

    sub_dir = ROOT / "papers" / "icicpe-scopus-vol2-submission"
    for stale in ("main.aux", "main.log", "main.bbl", "main.blg", "main.pdf",
                  "main.fls", "main.fdb_latexmk", "main.toc", "main.out"):
        f = sub_dir / stale
        if f.exists():
            f.unlink()

    _run("[6/7] pdflatex pass 1", ["pdflatex", "-interaction=nonstopmode", "main.tex"], cwd=sub_dir)
    _run("[6/7] bibtex", ["bibtex", "main"], cwd=sub_dir)
    _run("[6/7] pdflatex pass 2", ["pdflatex", "-interaction=nonstopmode", "main.tex"], cwd=sub_dir)
    _run("[6/7] pdflatex pass 3", ["pdflatex", "-interaction=nonstopmode", "main.tex"], cwd=sub_dir)

    _run("[7/7] build submission zip",
         [py, "-m", "scripts.build_submission_zip", "--check"])

    print("\n=== DONE ===")
    print("Next: review papers/icicpe-scopus-vol2-submission/main.pdf and submission_<sha>.zip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
