"""Composite loss: alpha*MSE + beta*(1 - WeightedPearson) + gamma*QuantileLoss(q=0.9).

Per PROJECT_2_PLAN.md §2.2 and DEEP_RESEARCH.md §VI.C.

Rationale (from DEEP_RESEARCH.md):
* Weighted Pearson loss directly optimises the metric used to evaluate
  the strategy at the rebalance decision boundary — accurate level
  matters less than getting the RELATIVE ranking Aave vs Compound right.
* The MSE term anchors absolute magnitudes (without it the model can
  drift in mean while preserving correlation).
* Quantile-90 loss penalises high-magnitude UNDER-predictions on the
  CHOSEN protocol asymmetrically — under-predicting yield on the picked
  protocol is worse than over-predicting on the rejected one.

The DA-BiGRU-CNN-LOB paper (Solovev 2026a) §5.6 ablation:
    MSE-only:               -19.5%   vs weighted Pearson loss
    MAE-only:               -14.2%
    Unweighted Pearson:      -6.1%
    Weighted Pearson:    baseline

So weighted-Pearson dominance is empirically established for the LOB
case. We carry the architecture but composite the loss to also penalise
absolute drift (relevant for DeFi-rate-magnitude-sensitive gas-gate).
"""
from __future__ import annotations

import torch
import torch.nn.functional as F


# ---------------------------------------------------------------------------
# Weighted Pearson correlation
# ---------------------------------------------------------------------------

def weighted_pearson(
    y_pred: torch.Tensor,
    y_true: torch.Tensor,
    weights: torch.Tensor | None = None,
    eps: float = 1e-8,
) -> torch.Tensor:
    """Weighted Pearson correlation in [-1, 1].

    weights default to |y_true| + eps — emphasises large-magnitude points
    (which dominate the MCDM allocator's downstream decision sensitivity).

    All inputs are 1-D after the caller flattens. Returns a scalar tensor.
    """
    if weights is None:
        weights = y_true.abs() + eps
    w = weights / weights.sum()

    mean_pred = (w * y_pred).sum()
    mean_true = (w * y_true).sum()
    dp = y_pred - mean_pred
    dt = y_true - mean_true

    cov = (w * dp * dt).sum()
    var_pred = (w * dp.pow(2)).sum().clamp_min(eps)
    var_true = (w * dt.pow(2)).sum().clamp_min(eps)
    return cov / (var_pred.sqrt() * var_true.sqrt())


# ---------------------------------------------------------------------------
# Pinball / quantile loss
# ---------------------------------------------------------------------------

def quantile_loss(
    y_pred: torch.Tensor,
    y_true: torch.Tensor,
    q: float = 0.9,
) -> torch.Tensor:
    """Pinball loss at quantile q.

    For q > 0.5 it asymmetrically penalises UNDER-predictions
    (residual > 0 ⇒ y_pred < y_true ⇒ penalty * q).
    """
    e = y_true - y_pred
    return torch.maximum(q * e, (q - 1.0) * e).mean()


# ---------------------------------------------------------------------------
# Composite loss (callable module)
# ---------------------------------------------------------------------------

class CompositeForecastLoss(torch.nn.Module):
    """L = alpha*MSE + beta*(1 - WeightedPearson) + gamma*QuantileLoss(q).

    Defaults: alpha=0.4, beta=0.5, gamma=0.1 (PROJECT_2_PLAN.md §2.2).
    Computes per-protocol separately, then averages — both protocols get
    equal weight in the gradient (one cannot dominate via larger rates).
    """

    def __init__(
        self,
        alpha: float = 0.4,
        beta: float = 0.5,
        gamma: float = 0.1,
        quantile_q: float = 0.9,
    ):
        super().__init__()
        self.alpha = float(alpha)
        self.beta = float(beta)
        self.gamma = float(gamma)
        self.quantile_q = float(quantile_q)

    def forward(
        self,
        r_pred: torch.Tensor,    # (B, n_protocols)
        r_true: torch.Tensor,    # (B, n_protocols)
    ) -> tuple[torch.Tensor, dict[str, float]]:
        # Reduce each component to a scalar per-protocol, then mean across protocols.
        mse_per = F.mse_loss(r_pred, r_true, reduction="none").mean(dim=0)
        wpe_per = torch.stack([
            weighted_pearson(r_pred[:, k], r_true[:, k])
            for k in range(r_pred.shape[1])
        ])
        qnt_per = torch.stack([
            quantile_loss(r_pred[:, k], r_true[:, k], q=self.quantile_q)
            for k in range(r_pred.shape[1])
        ])

        mse_term = mse_per.mean()
        wpearson_term = 1.0 - wpe_per.mean()
        quantile_term = qnt_per.mean()

        total = (
            self.alpha * mse_term
            + self.beta * wpearson_term
            + self.gamma * quantile_term
        )

        # Detached scalars for MLflow logging
        components = {
            "loss/total":         total.item(),
            "loss/mse":           mse_term.item(),
            "loss/wpearson":      wpe_per.mean().item(),
            "loss/wpearson_term": wpearson_term.item(),
            "loss/quantile":      quantile_term.item(),
        }
        return total, components


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _selftest() -> None:
    torch.manual_seed(0)

    # Synthetic: y_true is sin wave per protocol; y_pred is shifted version
    B = 256
    t = torch.linspace(0, 4 * 3.14159, B)
    y_true = torch.stack([torch.sin(t), torch.cos(t)], dim=1)        # (B, 2)
    y_pred_good = y_true + 0.01 * torch.randn_like(y_true)           # near-perfect
    y_pred_bad = y_true + 1.5 * torch.randn_like(y_true)             # noisy

    loss_fn = CompositeForecastLoss()

    loss_good, comp_good = loss_fn(y_pred_good, y_true)
    loss_bad, comp_bad = loss_fn(y_pred_bad, y_true)

    assert loss_good < loss_bad, f"loss did not order: good={loss_good} vs bad={loss_bad}"
    assert comp_good["loss/wpearson"] > comp_bad["loss/wpearson"], (
        f"weighted Pearson did not order: good={comp_good['loss/wpearson']} "
        f"vs bad={comp_bad['loss/wpearson']}"
    )
    print(f"CompositeForecastLoss OK:")
    print(f"  good: total={comp_good['loss/total']:.4f}, "
          f"wpearson={comp_good['loss/wpearson']:.4f}, "
          f"mse={comp_good['loss/mse']:.4f}")
    print(f"  bad : total={comp_bad['loss/total']:.4f}, "
          f"wpearson={comp_bad['loss/wpearson']:.4f}, "
          f"mse={comp_bad['loss/mse']:.4f}")


if __name__ == "__main__":
    _selftest()
