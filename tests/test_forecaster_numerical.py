"""Numerical sanity tests for the forecaster: gradient flow, shape,
parameter count, determinism, and loss ordering.

Run: pytest tests/test_forecaster_numerical.py -v
"""
from __future__ import annotations

import torch

from forecaster.losses import CompositeForecastLoss, quantile_loss, weighted_pearson
from forecaster.model import DABiGRUCNNForecaster, ForecasterConfig


# --- Model ---

def test_forward_shape():
    cfg = ForecasterConfig()
    model = DABiGRUCNNForecaster(cfg)
    B = 8
    x_a = torch.randn(B, cfg.sequence_length, cfg.branch_a_input_dim)
    x_b = torch.randn(B, cfg.sequence_length, cfg.branch_b_input_dim)
    y = model(x_a, x_b)
    assert y.shape == (B, cfg.n_protocols, cfg.n_targets_per_protocol)


def test_param_count_in_expected_band():
    cfg = ForecasterConfig()
    model = DABiGRUCNNForecaster(cfg)
    n = model.n_params()
    assert 100_000 <= n <= 500_000, f"unexpected param count {n}"


def test_gradient_flows_to_both_branches():
    cfg = ForecasterConfig()
    model = DABiGRUCNNForecaster(cfg)
    x_a = torch.randn(2, cfg.sequence_length, cfg.branch_a_input_dim, requires_grad=True)
    x_b = torch.randn(2, cfg.sequence_length, cfg.branch_b_input_dim, requires_grad=True)
    y = model(x_a, x_b)
    y.sum().backward()
    assert x_a.grad is not None and x_a.grad.abs().sum().item() > 0
    assert x_b.grad is not None and x_b.grad.abs().sum().item() > 0


def test_determinism_eval_mode():
    cfg = ForecasterConfig()
    torch.manual_seed(42)
    model = DABiGRUCNNForecaster(cfg)
    torch.manual_seed(0)
    x_a = torch.randn(2, cfg.sequence_length, cfg.branch_a_input_dim)
    x_b = torch.randn(2, cfg.sequence_length, cfg.branch_b_input_dim)
    model.eval()
    with torch.no_grad():
        y1 = model(x_a, x_b)
        y2 = model(x_a, x_b)
    assert torch.allclose(y1, y2)


# --- Losses ---

def test_weighted_pearson_perfect_corr_is_one():
    y = torch.linspace(-1, 1, 100)
    assert torch.isclose(weighted_pearson(y, y), torch.tensor(1.0), atol=1e-5)


def test_weighted_pearson_perfect_anticorr_is_minus_one():
    y = torch.linspace(-1, 1, 100)
    assert torch.isclose(weighted_pearson(-y, y), torch.tensor(-1.0), atol=1e-5)


def test_quantile_loss_asymmetric_for_q_above_half():
    """q=0.9 penalises under-predictions more than over-predictions."""
    y_true = torch.tensor([1.0, 1.0])
    y_under = torch.tensor([0.0, 0.0])
    y_over = torch.tensor([2.0, 2.0])
    l_under = quantile_loss(y_under, y_true, q=0.9)
    l_over = quantile_loss(y_over, y_true, q=0.9)
    assert l_under > l_over * 5


def test_composite_loss_orders():
    torch.manual_seed(0)
    y_true = torch.randn(256, 2)
    y_pred_good = y_true + 0.01 * torch.randn_like(y_true)
    y_pred_bad = y_true + 1.5 * torch.randn_like(y_true)

    loss_fn = CompositeForecastLoss()
    l_good, _ = loss_fn(y_pred_good, y_true)
    l_bad, _ = loss_fn(y_pred_bad, y_true)
    assert l_good < l_bad
