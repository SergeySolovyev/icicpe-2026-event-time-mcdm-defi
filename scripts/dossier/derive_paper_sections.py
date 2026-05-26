"""Update Vol-2 paper macros from the dossier walk-forward output.

Appends walk-forward-derived macros to
papers/icicpe-scopus-vol2/sections/results_macros.tex. These macros
become the primary inference values in §V (replacing the monthly N=4
bootstrap), and the walk-forward directional-consistency count
becomes a binding fund-relevant statistic."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    walk_path = ROOT / "results/institutional/tables/walk_forward.csv"
    if not walk_path.exists():
        print(f"[derive_paper_sections] walk_forward.csv missing; "
              f"run scripts.dossier.walk_forward_validation first.")
        return 1
    walk = pd.read_csv(walk_path)
    if walk.empty:
        print(f"[derive_paper_sections] walk_forward.csv empty; aborting.")
        return 1

    pivot = walk.pivot_table(
        index="window_id", columns="policy",
        values="sharpe", aggfunc="first",
    )

    macros_path = ROOT / "papers/icicpe-scopus-vol2/sections/results_macros.tex"
    text = macros_path.read_text(encoding="utf-8")

    lines = ["", "% --- Walk-forward (Vol-2 primary inference) ---"]
    if "t1_threshold" in pivot.columns and "b1_always_aave" in pivot.columns:
        delta = (pivot["t1_threshold"] - pivot["b1_always_aave"]).dropna()
        n = len(delta)
        n_dir = int((delta > 0).sum())
        mean_delta = float(delta.mean())
        lines.append(rf"\newcommand{{\WFNWindows}}{{{n}}}")
        lines.append(rf"\newcommand{{\WFDirectional}}{{{n_dir}}}")
        lines.append(rf"\newcommand{{\WFMeanDeltaSharpe}}{{{mean_delta:+.2f}}}")
    if "b1_always_aave" in pivot.columns:
        b1 = pivot["b1_always_aave"].dropna()
        if len(b1) > 0:
            lines.append(rf"\newcommand{{\WFBOneMeanSharpe}}{{{b1.mean():+.2f}}}")
    if "t1_threshold" in pivot.columns:
        t1 = pivot["t1_threshold"].dropna()
        if len(t1) > 0:
            lines.append(rf"\newcommand{{\WFTOneMeanSharpe}}{{{t1.mean():+.2f}}}")
    text += "\n".join(lines) + "\n"
    macros_path.write_text(text, encoding="utf-8")
    print(f"[derive_paper_sections] wrote {len(lines)-2} walk-forward macros to "
          f"{macros_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
