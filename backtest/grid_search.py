"""MLflow grid search over MCDM hyperparameters (PROJECT_2_PLAN.md S5.2).

Grid:
- MCDM weights (w1..w4)  -- Dirichlet 20 samples + AI Yield Vault default (0.40, 0.25, 0.20, 0.15)
- Hysteresis theta       -- {0.02, 0.05, 0.08, 0.10}
- Cooldown tau           -- {0.5h, 1h, 2h, 6h}
- Forecast horizon Delta -- {6h, 12h, 24h}
- APYmax normalization   -- {0.10, 0.15, 0.20, 0.25}

Selection criterion: Sharpe on validation, turnover < 2x best baseline turnover.

Uses fractal-defi `DefaultPipeline` with `window_size=14` for sliding-window
stability metrics (mean / q05 / q95 / cvar05) per ablation #13.

Run: python -m backtest.grid_search
"""
# TODO Week 3 Day 1 (1 June 2026)
raise NotImplementedError("Implement in Week 3 Day 1")
