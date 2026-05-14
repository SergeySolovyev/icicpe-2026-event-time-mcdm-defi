"""Export trained DualBranchKinkSubtractionForecaster -> ONNX for inference.

Why ONNX:
- Decouples PyTorch training from runtime; the strategy loads ONNX via onnxruntime
  inside `PredictiveMCDMStrategy.set_up()`.
- Matches the runtime-constraint pattern from Solovev 2026a (Wunder Fund 1 CPU,
  no GPU, 60-min total inference).
- Allows the Extra+2 PR (`BaseLendingAllocationStrategy`) to declare ONNX as the
  framework-blessed forecaster artifact format.

Outputs:
- forecaster/trained_models/dual_branch_kink.onnx
- forecaster/trained_models/dual_branch_kink_norm_stats.npz  (mean, std per feature)
- forecaster/trained_models/kink_params_snapshot.json        (kink params at training cutoff)
"""
# TODO Week 1 Day 7 (24 May 2026), after training converges
raise NotImplementedError("Implement in Week 1 Day 7")
