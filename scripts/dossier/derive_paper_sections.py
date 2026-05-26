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

    sharpe_pivot = walk.pivot_table(
        index="window_id", columns="policy",
        values="sharpe", aggfunc="first",
    )
    apy_pivot = walk.pivot_table(
        index="window_id", columns="policy",
        values="net_apy_pct", aggfunc="first",
    )

    macros_path = ROOT / "papers/icicpe-scopus-vol2/sections/results_macros.tex"
    text = macros_path.read_text(encoding="utf-8")
    # Strip any prior walk-forward macros block to keep this idempotent
    marker = "% --- Walk-forward (Vol-2 primary inference) ---"
    if marker in text:
        text = text.split(marker)[0].rstrip() + "\n"

    lines = ["", marker]
    if ("t1_threshold" in apy_pivot.columns
            and "b1_always_aave" in apy_pivot.columns):
        apy_delta = (apy_pivot["t1_threshold"]
                     - apy_pivot["b1_always_aave"]).dropna()
        n = len(apy_delta)
        n_dir = int((apy_delta > 0).sum())
        mean_apy = float(apy_delta.mean())
        # ΔAPY is the binding fund metric -- the paper's primary inference
        lines.append(rf"\newcommand{{\WFNWindows}}{{{n}}}")
        lines.append(rf"\newcommand{{\WFDirectionalAPY}}{{{n_dir}}}")
        lines.append(rf"\newcommand{{\WFMeanDeltaAPY}}{{{mean_apy:+.2f}}}")
    if ("t1_threshold" in sharpe_pivot.columns
            and "b1_always_aave" in sharpe_pivot.columns):
        sr_delta = (sharpe_pivot["t1_threshold"]
                    - sharpe_pivot["b1_always_aave"]).dropna()
        n_dir_sr = int((sr_delta > 0).sum())
        mean_sr = float(sr_delta.mean())
        # ΔSharpe is the inflation-biased secondary lens (documented in §02)
        lines.append(rf"\newcommand{{\WFDirectionalSharpe}}{{{n_dir_sr}}}")
        lines.append(rf"\newcommand{{\WFMeanDeltaSharpe}}{{{mean_sr:+.2f}}}")
    if "b1_always_aave" in sharpe_pivot.columns:
        b1 = sharpe_pivot["b1_always_aave"].dropna()
        if len(b1) > 0:
            lines.append(rf"\newcommand{{\WFBOneMeanSharpe}}{{{b1.mean():+.2f}}}")
    if "t1_threshold" in sharpe_pivot.columns:
        t1 = sharpe_pivot["t1_threshold"].dropna()
        if len(t1) > 0:
            lines.append(rf"\newcommand{{\WFTOneMeanSharpe}}{{{t1.mean():+.2f}}}")

    # Per-protocol contrast macros (T1 vs each per-protocol buy-and-hold).
    # These are computed in scripts.dossier.* and saved as
    # walk_forward_paired_bootstrap_all.csv -- used by paper §V to disclose
    # honest per-protocol picture (T1 dominates Aave+Morpho, trails Euler).
    pp_path = ROOT / "results/institutional/tables/walk_forward_paired_bootstrap_all.csv"
    if pp_path.exists():
        pp = pd.read_csv(pp_path)
        # Mapping contrast label -> latex command suffix
        suffix_map = {
            "T1 vs Aave hold": "Aave",
            "T1 vs Morpho hold": "Morpho",
            "T1 vs Euler hold": "Euler",
        }
        for _, row in pp.iterrows():
            suf = suffix_map.get(row.contrast)
            if suf is None:
                continue
            lines.append(rf"\newcommand{{\WFMeanDeltaAPY{suf}}}{{{row.mean_pp:+.2f}}}")
            lines.append(rf"\newcommand{{\WFCILow{suf}}}{{{row.ci_low_95:+.2f}}}")
            lines.append(rf"\newcommand{{\WFCIHigh{suf}}}{{{row.ci_high_95:+.2f}}}")
            lines.append(rf"\newcommand{{\WFPValue{suf}}}{{{row.p_one_sided_le0:.4f}}}")
            lines.append(rf"\newcommand{{\WFWins{suf}}}{{{int(row.directional_consistency)}}}")
    text += "\n".join(lines) + "\n"
    macros_path.write_text(text, encoding="utf-8")
    print(f"[derive_paper_sections] wrote {len(lines)-2} walk-forward macros to "
          f"{macros_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
