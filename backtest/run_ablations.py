"""Run all 15 ablations from PROJECT_2_PLAN.md S10.

Ablation matrix:
     1. No-forecast EMA baseline (Baseline C)         -- mandatory strawman
     2. Naive last-observation forecast
     3. CIR-calibrated forecast (Baseline D)
     4. Markov-switching 2-state on utilization
     5. CatBoost forecast (mirrors examples/ml_funding_rate_forecasting)
     6. Single-branch DA-GRU (no CNN, no decomposition)
     7. Dual-branch WITHOUT kink subtraction
     8. Forecast with ranking-loss only
     9. MCDM equal weights vs tuned
    10. Single-protocol benchmark (Aave-only, Compound-only)
    11. Greedy max-forecasted-APY vs TOPSIS-MCDM
    12. Zero-gas vs realistic-gas
    13. Sliding-window stability (window_size=14)
    14. OOD test on USDC depeg week Mar 2023 ("Rules to Rewards" dataset)
    15. Forecast horizon sweep (3h, 6h, 12h, 24h)

Each ablation logs to MLflow + a row in results/tables/ablations.csv.

The headline figure for the whitepaper title page comes from #1 vs main strategy.

Run: python -m backtest.run_ablations [--only <n>]
"""
# TODO Week 3 Days 2-6 (2-6 June 2026)
raise NotImplementedError("Implement in Week 3 Days 2-6")
