"""Baseline D: CIR-calibrated forecast feeding the same MCDM allocator.

Intermediate strategy between "no forecast" (Baseline C) and "DL forecast"
(main predictive_mcdm.py). Uses `forecaster.baseline_cir.CIRForecaster` for
r_i(t+12h) and feeds into the same MCDM scoring as Baseline C.

Tests whether DL adds value over a classical regime-aware model.

Per PROJECT_2_PLAN.md S7 Baseline D.
"""
# TODO Week 2 Day 4 (28 May 2026)
raise NotImplementedError("Implement in Week 2 Day 4")
