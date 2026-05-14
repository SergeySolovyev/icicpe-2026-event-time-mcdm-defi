"""CatBoost on hand-crafted features baseline forecaster.

Mirrors `examples/ml_funding_rate_forecasting/notebooks/baseline_research.ipynb`
in fractal-defi exactly. In-framework house style — making this an
apples-to-apples comparison with fractal-defi's own ML pipeline.

Feature set: same 53 base + 219 extended features as DA-BiGRU-CNN-LOB
adapted to lending rates (rate, utilization, TVL, gas, time-of-day, plus
rolling means/stds at multiple windows, lag/diff features, EWM features).

Per PROJECT_2_PLAN.md S10 ablation #5.
"""
# TODO Week 2 Day 4 (29 May 2026)
raise NotImplementedError("Implement in Week 2 Day 4")
