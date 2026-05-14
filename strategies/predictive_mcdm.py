"""MAIN STRATEGY: PredictiveMCDMStrategy — DL-forecast-driven MCDM allocator.

Headline contribution. Combines:
- DA-BiGRU-CNN dual-branch-with-kink-subtraction forecaster from `forecaster/`
  (ONNX-loaded for inference), and
- TOPSIS-style 4-factor MCDM aggregator inherited from AI Yield Vault (Solovev 2026b).

Architecture summary (see PROJECT_2_PLAN.md S3 for full pseudocode):

    1. Observe (r_a, u_a, TVL_a, dTVL_a), (r_c, u_c, TVL_c, dTVL_c), gas
    2. Append to 168-hour rolling buffer
    3. Forecast (r_hat_a, r_hat_c) at t+12h via ONNX
    4. Score Score_i = 0.40*f_APY(r_hat_i) + 0.25*f_Risk(u_i) + 0.20*f_Cost(g) + 0.15*f_Stab(dTVL_i)
    5. If (Score_best - Score_current > 0.05) AND cooldown OK AND gas-gate OK:
           withdraw all from current, supply all to best

Inherits from project-defined `BaseLendingAllocationStrategy` (the Extra+2
abstraction in `extras/fractal_pr_lending_allocation/`).

KEY DIFFERENCE vs baseline_mcdm_ema.py: line 4 uses `r_hat_i(t+12h)` from the
DL forecaster instead of `EMA(r_i(t))`.
"""
# TODO Week 2 Day 5 (29 May 2026)
raise NotImplementedError("Implement in Week 2 Day 5")
