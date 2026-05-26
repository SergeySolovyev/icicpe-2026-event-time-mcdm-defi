"""Post-T3-matrix pipeline: bootstrap H1c, regenerate Vol-2 macros,
rebuild the V2 paper, rebuild the F4-gated submission zip.

Pre-conditions:
  - results/tables/test_matrix.csv has a `t3_hazard` row
  - results/tables/equity/equity_t3_hazard.parquet exists
  - All earlier policies' equity parquets are present

Side effects:
  - Updates results/tables/h1_significance.csv with H1c row
  - Re-renders results/figures/equity_curves.png (now 7 policies)
  - Re-runs scripts/fill_vol2_macros.py
  - Re-runs scripts/build_vol2_submission.py
  - Re-runs latexmk
  - Re-runs scripts/build_submission_zip.py --check
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
EQUITY_DIR = ROOT / "results" / "tables" / "equity"
MATRIX = ROOT / "results" / "tables" / "test_matrix.csv"
H1 = ROOT / "results" / "tables" / "h1_significance.csv"


def _verify() -> None:
    if not MATRIX.exists():
        raise FileNotFoundError(f"missing {MATRIX}")
    m = pd.read_csv(MATRIX)
    if "t3_hazard" not in m.policy.values:
        raise RuntimeError(
            "test_matrix.csv has no `t3_hazard` row -- "
            "did the matrix runner finish with --include-t3?"
        )
    if not (EQUITY_DIR / "equity_t3_hazard.parquet").exists():
        raise FileNotFoundError("equity_t3_hazard.parquet missing")


def _run_bootstrap() -> None:
    from backtest.bootstrap_paired_sharpe import (
        monthly_returns_from_equity, paired_monthly_sharpe_bootstrap,
    )

    policies = [
        "b1_always_aave", "b4_mcdm_ema",
        "t1_threshold", "t2_optimal_stopping", "t3_hazard",
    ]
    monthly = {
        p: monthly_returns_from_equity(
            pd.read_parquet(EQUITY_DIR / f"equity_{p}.parquet"), p,
        )
        for p in policies
    }
    # All four hypotheses incl. H1c
    bench = [
        ("H1a", "t1_threshold", "b4_mcdm_ema"),
        ("H1b", "t2_optimal_stopping", "t1_threshold"),
        ("H1c", "t3_hazard", "t2_optimal_stopping"),
        ("H1aux_t1_vs_b1", "t1_threshold", "b1_always_aave"),
        ("H1aux_t3_vs_b1", "t3_hazard", "b1_always_aave"),
    ]
    rows = []
    for name, a, b in bench:
        r = paired_monthly_sharpe_bootstrap(
            monthly[a], monthly[b], name=name, n_resamples=1000, seed=42,
        )
        rows.append({
            "hypothesis": r.name,
            "policy_a": r.policy_a, "policy_b": r.policy_b,
            "delta_sharpe_point": r.delta_sharpe_point,
            "ci_low_95": r.ci_low_95, "ci_high_95": r.ci_high_95,
            "nominal_p": r.nominal_p,
            "n_months": r.n_months, "n_bootstrap": r.n_bootstrap,
        })
        print(
            f"  {name}: delta={r.delta_sharpe_point:+.3f}  "
            f"CI=[{r.ci_low_95:+.3f}, {r.ci_high_95:+.3f}]  "
            f"p={r.nominal_p:.3f}"
        )
    pd.DataFrame(rows).to_csv(H1, index=False)
    print(f"wrote {H1}")


def _run(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr)
        raise SystemExit(r.returncode)
    # tail short output
    tail = "\n".join(r.stdout.splitlines()[-3:])
    if tail.strip():
        print(tail)


def main() -> int:
    _verify()
    print("=== bootstrap H1a-c + auxiliaries ===")
    _run_bootstrap()
    print()
    print("=== regenerate Vol-2 macros ===")
    _run([sys.executable, "-m", "scripts.fill_vol2_macros"])
    print()
    print("=== re-run F2 template conversion ===")
    _run([sys.executable, "-m", "scripts.build_vol2_submission"])
    print()
    print("=== re-render equity_curves figure ===")
    _run([
        sys.executable, "-c",
        "import sys; sys.path.insert(0, 'results/figures');"
        "from results.figures.build_equity_curves import build_equity_curves_figure;"
        "from pathlib import Path;"
        "build_equity_curves_figure("
        "equity_dir=Path('results/tables/equity'),"
        "out_path=Path('results/figures/equity_curves.png'),"
        "protocols=('aave_v3', 'morpho_blue', 'euler_v2'),"
        ")",
    ])
    print()
    print("=== regime breakdown ===")
    _run([sys.executable, "-m", "backtest.run_regime_breakdown"])
    print()
    print("=== latexmk ===")
    submission = ROOT / "papers" / "icicpe-scopus-vol2-submission"
    subprocess.run(["latexmk", "-C"], cwd=submission, capture_output=True)
    r = subprocess.run(
        ["latexmk", "-pdf", "-interaction=nonstopmode", "main.tex"],
        cwd=submission, capture_output=True, text=True,
    )
    pdf = submission / "main.pdf"
    if not pdf.exists():
        print("latexmk failed:")
        print(r.stdout[-2000:])
        print(r.stderr[-2000:])
        raise SystemExit(1)
    print("=== F4 page-budget audit ===")
    _run([
        sys.executable, "-m", "scripts.audit_page_budget", "--pdf", str(pdf),
    ])
    print()
    print("=== LLM transcript refresh ===")
    _run([
        sys.executable, "-m", "scripts.build_llm_transcript",
        "--projects", "C:/Users/1/.claude/projects/D--DeFi",
        "--out", str(submission / "LLM_TRANSCRIPT.md"),
    ])
    print()
    print("=== F6 submission zip with --check ===")
    _run([
        sys.executable, "-m", "scripts.build_submission_zip", "--check",
    ])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
