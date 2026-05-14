"""Composite loss: alpha*MSE + beta*(1 - WeightedPearson) + gamma*QuantileLoss(q=0.9).

Per PROJECT_2_PLAN.md S2.2 and DEEP_RESEARCH.md S VI.C.

Defaults (alpha, beta, gamma) = (0.4, 0.5, 0.1). Weights tuned via MLflow grid.
WeightedPearson uses w_i = |y_i| + epsilon to emphasize large-rate-move samples
(matches metric in Solovev 2026a section 5.6).

Sanity-check loss: BCE on the binary `r_aave > r_comp at t+12h` label;
forecaster rejected if directional accuracy < 55%.
"""
# TODO Week 1 Day 6 (23 May 2026)
import torch  # noqa: F401 - placeholder

raise NotImplementedError("Implement in Week 1 Day 6")
