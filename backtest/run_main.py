"""Run main `PredictiveMCDMStrategy` on held-out test set (Jan-Apr 2026).

The headline backtest. Loads the trained ONNX forecaster, runs the strategy
on the test parquets, computes the full metrics dict from PROJECT_2_PLAN.md
S9 and the statistical-significance tests from S9.6:
- 1000-bootstrap of monthly Sharpe ratios (H1 test vs Baseline C)
- McNemar's test on directional accuracy (H2 test)

Run: python -m backtest.run_main
"""
# TODO Week 3 (1-7 June 2026)
raise NotImplementedError("Implement in Week 3")
