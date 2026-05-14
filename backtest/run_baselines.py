"""Run all four baselines (A: buy-hold, B: APY-greedy, C: MCDM-EMA, D: MCDM-CIR).

For each baseline:
1. Construct strategy with default params (per PROJECT_2_PLAN.md S5.2 defaults).
2. Build Observations from cached parquets (data/cached/*.parquet).
3. Run via fractal-defi `DefaultPipeline` on validation period (Sep-Dec 2025).
4. Log to MLflow: params, metrics, strategy_backtest_data.csv.
5. Append summary row to results/tables/baseline_summary.csv with columns
   from PROJECT_2_PLAN.md S9: APY, Sharpe, Calmar, MaxDD, turnover, gas_spent.

Run: python -m backtest.run_baselines
"""
# TODO Week 2 Day 6 (30 May 2026)
raise NotImplementedError("Implement in Week 2 Day 6")
