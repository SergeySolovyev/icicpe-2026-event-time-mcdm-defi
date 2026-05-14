# Notebooks — Predictive MCDM DeFi

Nine notebooks matching the repo structure in `PROJECT_2_PLAN.md` §12. Each
gracefully falls back to a synthetic-data generator if
`data/cached/joined_clean.parquet` is not yet on disk.

| # | Notebook | Description | Est. runtime |
|---|---|---|---|
| 1 | [`01_data_exploration.ipynb`](01_data_exploration.ipynb) | Rate / TVL / spread / utilization plots for the joined Aave-Compound panel. | < 30 s |
| 2 | [`02_kink_calibration.ipynb`](02_kink_calibration.ipynb) | Fetch on-chain kink params, plot `f_kink(u)` per protocol, verify residuals. | < 1 min |
| 3 | [`03_forecaster_training.ipynb`](03_forecaster_training.ipynb) | 5-epoch CPU smoke train of the DA-BiGRU-CNN forecaster + ONNX parity check. | ~ 2 min |
| 4 | [`04_main_backtest.ipynb`](04_main_backtest.ipynb) | Drive `backtest.run_baselines.run_all`; equity curves, drawdown, turnover. | 1–3 min |
| 5 | [`05_ablations_forecast_value.ipynb`](05_ablations_forecast_value.ipynb) | Ablations 1–5 (EMA, naive, CIR, Markov, CatBoost). | 2–4 min |
| 6 | [`06_ablations_architecture.ipynb`](06_ablations_architecture.ipynb) | Ablations 6–8 (single-branch, no-kink, ranking-loss-only). | ~ 5 min |
| 7 | [`07_ablations_mcdm.ipynb`](07_ablations_mcdm.ipynb) | Ablations 9–11 (equal weights, single-protocol, greedy vs MCDM). | 1–2 min |
| 8 | [`08_regime_analysis.ipynb`](08_regime_analysis.ipynb) | Rolling-vol tertile split, conditional metrics per regime. | < 1 min |
| 9 | [`09_ood_depeg_test.ipynb`](09_ood_depeg_test.ipynb) | Placeholder OOD test on Mar 2023 USDC depeg (Rules-to-Rewards 2025). | N/A until data fetched |

## Running

From the project root (`predictive-mcdm-defi/`) with the venv activated:

```powershell
.venv\Scripts\Activate.ps1
jupyter notebook notebooks/
```

## Regenerating the notebooks from scratch

The notebooks are emitted by a small builder script so they stay in sync with
plan revisions:

```powershell
.venv\Scripts\python.exe notebooks\_build_notebooks.py
```

This re-creates all nine `.ipynb` files and validates them with `nbformat`.
