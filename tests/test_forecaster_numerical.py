"""Numerical sanity tests for DualBranchKinkSubtractionForecaster.

1. Output shape: (B, 2) for batch input (B, W=168, F).
2. Output range: predicted rates in [0, 0.50] after clipping.
3. Determinism: same seed + same input -> identical output.
4. ONNX-PyTorch parity: max-abs-diff < 1e-5 between two implementations.
5. Kink reconstruction: r_hat = f_kink(u_hat) + eps_hat numerically consistent.

Per PROJECT_2_PLAN.md S14 risk #14 (Compound WAD vs Aave RAY mis-normalization).
"""
# TODO Week 1 Day 7 (24 May 2026) after first training run
import pytest


@pytest.mark.skip(reason="Week 1 Day 7")
def test_forecaster_output_shape() -> None:
    raise NotImplementedError


@pytest.mark.skip(reason="Week 1 Day 7")
def test_onnx_pytorch_parity() -> None:
    raise NotImplementedError
