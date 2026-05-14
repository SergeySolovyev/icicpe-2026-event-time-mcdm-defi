"""DA-BiGRU-CNN forecaster, DeFi-lending adaptation.

Domain-Aware Dual-Branch Bidirectional GRU + multi-scale Conv1d, derived
from Solovev 2026a (DA-BiGRU-CNN-LOB) §4.3.3 with the branching scheme
re-instantiated for lending-rate dynamics per PROJECT_2_PLAN.md §2.2.

Branching scheme (DEFI-SPECIFIC):

    Branch A — Rate residual
        Input  : 7-day rolling window of (eps_aave, eps_compound, eps_spread)
                 where eps_i(t) = r_i(t) - f_kink_i(u_i(t)).
        Why    : the deterministic kink function f_kink is known, so we
                 force the forecaster to model only the unexplained part.
        Arch   : BiGRU(hidden=64, layers=2), LayerNorm output.

    Branch B — Utilization + context
        Input  : 7-day rolling window of
                    (u_aave, u_compound,
                     dTVL_aave_24h, dTVL_compound_24h,
                     gas_gwei, tod_sin, tod_cos)
        Arch   : BiGRU(hidden=64, layers=2) -> Conv1d stack k=[3,5,7],
                 progressive channel reduction 2d -> 2d -> d -> d/2.

    Late fusion: concat(h_A, h_B_cnn) -> MLP head producing
                 (u_hat_aave, u_hat_compound, eps_corr_aave, eps_corr_compound).

    Reconstruction (closed-form, no params):
        r_hat_i(t+H) = f_kink_i(u_hat_i, kink_params_i) + eps_corr_i

Hyperparameter defaults match the LOB-paper baseline that achieved
weighted-Pearson 0.266 on test (paper §5.3, Table 4):
    hidden=64, layers=2, dropout=0.15.

The forecast horizon H defaults to 12 hours (PROJECT_2_PLAN.md §1.5).

Loss is defined in `forecaster/losses.py`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class ForecasterConfig:
    """All architecture hyperparameters in one place (MLflow-loggable)."""
    branch_a_input_dim: int = 3              # eps_aave, eps_compound, eps_spread
    branch_a_hidden: int = 64
    branch_a_layers: int = 2

    branch_b_input_dim: int = 7              # u_a, u_c, dTVL_a, dTVL_c, gas, sin, cos
    branch_b_hidden: int = 64
    branch_b_layers: int = 2
    branch_b_cnn_kernels: tuple[int, ...] = (3, 5, 7)

    head_hidden: int = 64
    n_targets_per_protocol: int = 2          # (u_hat, eps_corr)
    n_protocols: int = 2                     # aave, compound

    dropout: float = 0.15
    sequence_length: int = 168               # 7 days * 24h
    forecast_horizon: int = 12               # hours


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

class RateResidualBranch(nn.Module):
    """Branch A — BiGRU over the 3-D residual time-series.

    Output: (B, 2*hidden) — last-step bidirectional hidden state, LayerNorm'd.
    """

    def __init__(self, cfg: ForecasterConfig):
        super().__init__()
        self.gru = nn.GRU(
            input_size=cfg.branch_a_input_dim,
            hidden_size=cfg.branch_a_hidden,
            num_layers=cfg.branch_a_layers,
            batch_first=True,
            bidirectional=True,
            dropout=cfg.dropout if cfg.branch_a_layers > 1 else 0.0,
        )
        self.norm = nn.LayerNorm(2 * cfg.branch_a_hidden)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _h = self.gru(x)                  # (B, T, 2*hidden)
        return self.norm(out[:, -1, :])        # (B, 2*hidden)


class UtilizationBranch(nn.Module):
    """Branch B — BiGRU + multi-scale Conv1d on context features.

    Progressive channel reduction: 2d -> 2d (k=3) -> d (k=5) -> d/2 (k=7).
    Output: (B, d//2) — global-avg-pooled multi-scale conv features.
    """

    def __init__(self, cfg: ForecasterConfig):
        super().__init__()
        h = cfg.branch_b_hidden
        self.gru = nn.GRU(
            input_size=cfg.branch_b_input_dim,
            hidden_size=h,
            num_layers=cfg.branch_b_layers,
            batch_first=True,
            bidirectional=True,
            dropout=cfg.dropout if cfg.branch_b_layers > 1 else 0.0,
        )

        k = cfg.branch_b_cnn_kernels
        self.conv1 = nn.Conv1d(2 * h, 2 * h, kernel_size=k[0], padding=k[0] // 2)
        self.conv2 = nn.Conv1d(2 * h, h,     kernel_size=k[1], padding=k[1] // 2)
        self.conv3 = nn.Conv1d(h,    h // 2, kernel_size=k[2], padding=k[2] // 2)

        self.out_dim = h // 2
        self.dropout = nn.Dropout(cfg.dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        gru_out, _h = self.gru(x)              # (B, T, 2h)
        c = gru_out.transpose(1, 2)            # (B, 2h, T)
        c = F.gelu(self.conv1(c))
        c = F.gelu(self.conv2(c))
        c = F.gelu(self.conv3(c))              # (B, h//2, T)
        c = self.dropout(c)
        return c.mean(dim=2)                   # (B, h//2)


class FusionHead(nn.Module):
    """Late fusion + MLP head producing per-protocol (u_hat, eps_corr) pairs."""

    def __init__(self, cfg: ForecasterConfig, branch_a_dim: int, branch_b_dim: int):
        super().__init__()
        in_dim = branch_a_dim + branch_b_dim
        out_dim = cfg.n_protocols * cfg.n_targets_per_protocol   # 4 = 2 protocols * 2 outputs
        self.mlp = nn.Sequential(
            nn.Linear(in_dim, cfg.head_hidden),
            nn.GELU(),
            nn.Dropout(cfg.dropout),
            nn.Linear(cfg.head_hidden, out_dim),
        )
        self.n_protocols = cfg.n_protocols

    def forward(self, h_a: torch.Tensor, h_b: torch.Tensor) -> torch.Tensor:
        z = torch.cat([h_a, h_b], dim=-1)
        raw = self.mlp(z)                                  # (B, 2*n_protocols)
        return raw.view(raw.shape[0], self.n_protocols, 2) # (B, n_protocols, 2)


# ---------------------------------------------------------------------------
# Full model
# ---------------------------------------------------------------------------

class DABiGRUCNNForecaster(nn.Module):
    """DA-BiGRU-CNN for DeFi lending rates — dual-branch + kink reconstruction.

    Output: (B, n_protocols, 2) where [..., 0] = u_hat, [..., 1] = eps_corr.
    Reconstruction r_hat = f_kink(u_hat, kink_params) + eps_corr is done
    OUTSIDE the model (CPU-side, see forecaster/train.py) so kink params
    can be swapped without retraining.
    """

    def __init__(self, cfg: Optional[ForecasterConfig] = None):
        super().__init__()
        self.cfg = cfg or ForecasterConfig()

        self.branch_a = RateResidualBranch(self.cfg)
        self.branch_b = UtilizationBranch(self.cfg)
        self.head = FusionHead(
            self.cfg,
            branch_a_dim=2 * self.cfg.branch_a_hidden,
            branch_b_dim=self.branch_b.out_dim,
        )

    def forward(
        self,
        x_branch_a: torch.Tensor,             # (B, T, 3)
        x_branch_b: torch.Tensor,             # (B, T, 7)
    ) -> torch.Tensor:                        # (B, 2, 2) — [protocol][u_hat | eps_corr]
        h_a = self.branch_a(x_branch_a)
        h_b = self.branch_b(x_branch_b)
        return self.head(h_a, h_b)

    def n_params(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


def _selftest() -> None:
    cfg = ForecasterConfig()
    model = DABiGRUCNNForecaster(cfg)

    B = 4
    x_a = torch.randn(B, cfg.sequence_length, cfg.branch_a_input_dim)
    x_b = torch.randn(B, cfg.sequence_length, cfg.branch_b_input_dim)

    y = model(x_a, x_b)
    assert y.shape == (B, cfg.n_protocols, cfg.n_targets_per_protocol), (
        f"unexpected output shape: {y.shape}"
    )
    n = model.n_params()
    assert 30_000 < n < 500_000, f"unexpected param count {n}"
    print(f"DABiGRUCNN smoke test OK: output {y.shape}, params {n:,}")


if __name__ == "__main__":
    _selftest()
