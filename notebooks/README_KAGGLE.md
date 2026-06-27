# Reproducible companion notebook — Predictive MCDM USDC allocator

`reproduce_predictive_mcdm_defi.ipynb` recomputes **every empirical number in the paper**
(ICICPE Scopus Vol-2) from a single cached input, with **no API keys** and **no `fractal-defi`**.
Academic layout: each section is *markdown (theory) → code → markdown (interpretation)*, top to bottom.

## What it reproduces (all from `per_block_panel.parquet`)
| Section | Result |
|---|---|
| §4 Main matrix | B1–B4 + T1 + T2 to the dollar (T1 5.37% / $1,017,341 / 322 reb) |
| §5 Regime | Q1 calm 4.39% vs Q2 volatile 8.37% |
| §6 Walk-forward | T1 beats best in-hindsight venue **6/6** windows |
| §7 Significance | per-window paired bootstrap + **Holm 6/6**; monthly H1 |
| §8 Negative control | **T3 OOS −5.97 bp, 0/5** (in-sample +7.0 bp is leakage) |
| §9 Robustness | random-null **9σ**, **PBO=0**, flat plateau, gas sweep, block-bootstrap |
| §10 Capacity | yield-impact curve 8.5% → 7.6% ($1M→$50M) |
| §11 L2/Base | live DeFiLlama dispersion (optional, needs internet) |
| §12 Ledger | every paper number beside its reproduced value |

## Run on Kaggle
1. **Create a dataset** containing both files (from `data/cached/`):
   - `per_block_panel.parquet` (~72 MB, the raw input)
   - `events_dsr.parquet` (~30 KB, DSR lead-rate side file for T3 F1 features)
2. **New Notebook → Add Data →** your dataset. The notebook auto-locates the files under `/kaggle/input/`.
3. (Optional) turn **Internet ON** only for §11 (the live Base measurement); everything else is offline.
4. **Run All.** Runtime ≈ 8–12 min (the T3 Cox fits in §8 are the slow part).

`lifelines` is the only non-default dependency; the notebook installs it automatically if missing.

## Run locally
```bash
# from the repo root (so the panel resolves at data/cached/)
.venv/Scripts/python -m nbconvert --to notebook --execute --inplace \
    notebooks/reproduce_predictive_mcdm_defi.ipynb --ExecutePreprocessor.timeout=1800
```

## Provenance / honesty notes
- The engine is validated to reproduce the production `EventReplayEngine` **to the dollar**.
- §7 H1 (N=4 monthly) is reproduced **self-consistently on the 6-way curves**; the paper's printed H1 table predates
  the 6-way regeneration (3-protocol basis per `results_macros.tex`) — the robust inference is the per-window bootstrap.
- §8 T3 OOS reproduces to ≤0.02 bp per window (lifelines 0.30.x); sign, mean, CI, p and 0/5 wins are exact.
- §10 capacity reproduces the continuous-model curve to within ~0.03 pp.

Rebuild the notebook from source: `python notebooks/build_reproduction_notebook.py`
(assembles it from `scripts/robustness/notebook_{core,robust,t3}.py`).
