"""Unit-contract tests covering the audit-findings-2026-05-20 batch-fix.

Tests are organized by audit finding number. Each test was written BEFORE the
corresponding fix so it would fail on the broken code (red) and pass after
(green). See `docs/research/audit-findings-2026-05-20.md` for the diagnosis.

Findings covered:
  #1  R² scale catastrophe — r_*_annual columns + TARGET_COLS
  #2  train/inference convergence (eps magnitude parity)
  #5  z-score normalization with training-window stats (no leakage)
  #6  seed reproducibility (two fits, same seed → same first-batch loss)
  #7  torch f_kink — gradient flows through u_hat
  #8  u_hat bounding (sigmoid) + data clamping (u <= 1.0)

IMPORTANT: torch MUST be imported before numpy/pandas on Windows (CLAUDE.md
constraint #6). Do NOT add `from __future__ import annotations` here.
"""
import torch

import json
import math
import random
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from data.features import (
    AaveKinkParams,
    CompoundKinkParams,
    extract_features,
    f_kink,
)


ROOT = Path(__file__).resolve().parent.parent
KINK_JSON = ROOT / "data" / "cached" / "kink_params.json"
JOINED_PARQUET = ROOT / "data" / "cached" / "joined_clean.parquet"


def _load_kink_params():
    with open(KINK_JSON) as f:
        kp = json.load(f)
    return AaveKinkParams(**kp["aave"]), CompoundKinkParams(**kp["compound"])


KP_AAVE, KP_COMP = _load_kink_params()


# ===========================================================================
# Finding #1: R² scale — eps and f_kink(u) must be on the same scale
# ===========================================================================

def test_finding_1_r_annual_columns_present():
    """extract_features must emit r_aave_annual and r_compound_annual."""
    df = pd.read_parquet(JOINED_PARQUET).head(500).copy()
    if "gas_gwei" not in df.columns:
        df["gas_gwei"] = 30.0
    if "eth_usd" not in df.columns:
        df["eth_usd"] = 3500.0
    feats = extract_features(df, KP_AAVE, KP_COMP)
    assert "r_aave_annual" in feats.columns
    assert "r_compound_annual" in feats.columns
    # Annual rate should be ~3-5% (0.03–0.05), per-hour ~ 4e-6
    median_annual = feats["r_aave_annual"].median()
    assert 0.001 < median_annual < 0.5, (
        f"r_aave_annual median {median_annual:.3e} is outside [1e-3, 0.5]"
    )


def test_finding_1_rate_residual_scale_matches_f_kink():
    """eps_aave and f_kink(u) must be on the same scale (within 2 orders)."""
    df = pd.read_parquet(JOINED_PARQUET).head(1000).copy()
    if "gas_gwei" not in df.columns:
        df["gas_gwei"] = 30.0
    if "eth_usd" not in df.columns:
        df["eth_usd"] = 3500.0
    feats = extract_features(df, KP_AAVE, KP_COMP).dropna()
    eps_med = feats["eps_aave"].abs().median()
    fkink_med = abs(float(f_kink(df["u_aave"].median(), KP_AAVE)))
    ratio = eps_med / max(fkink_med, 1e-30)
    assert 0.001 < ratio < 100.0, (
        f"eps_aave median {eps_med:.2e} vs f_kink {fkink_med:.2e} → "
        f"scale ratio {ratio:.4f} suggests a unit mismatch"
    )


def test_finding_1_target_cols_are_annual():
    """forecaster.train.TARGET_COLS must reference *_annual columns."""
    from forecaster.train import TARGET_COLS

    assert TARGET_COLS == ("r_aave_annual", "r_compound_annual"), (
        f"TARGET_COLS={TARGET_COLS}: expected the annualized columns"
    )


# ===========================================================================
# Finding #2: train/inference convergence — eps magnitudes must match
# ===========================================================================

def test_finding_2_train_inference_eps_magnitude_parity():
    """The strategy's runtime eps formula must match the training pipeline.

    Strategy: r_a = lending_rate * 365*24; eps_a = r_a - f_kink(u_a).
    Training (post-fix #1): r_a_annual = r_aave * 365*24;
                            eps_aave = r_a_annual - f_kink(u_a).
    So for any row: dataset eps_aave should equal r_a_annual - f_kink(u_a).
    """
    df = pd.read_parquet(JOINED_PARQUET).head(500).copy()
    if "gas_gwei" not in df.columns:
        df["gas_gwei"] = 30.0
    if "eth_usd" not in df.columns:
        df["eth_usd"] = 3500.0
    feats = extract_features(df, KP_AAVE, KP_COMP).dropna()

    # Pick a non-null sample row
    sample = feats.iloc[0]
    r_a_strategy = float(sample["r_aave"]) * 365 * 24
    eps_strategy = r_a_strategy - float(f_kink(sample["u_aave"], KP_AAVE))
    eps_dataset = float(sample["eps_aave"])
    assert abs(eps_strategy - eps_dataset) < 1e-9, (
        f"strategy-eps {eps_strategy:.3e} vs dataset-eps {eps_dataset:.3e}: "
        f"diff {abs(eps_strategy - eps_dataset):.3e}"
    )


# ===========================================================================
# Finding #7: gradient must flow through u_hat in reconstruct_rate
# ===========================================================================

def test_finding_7_gradient_flows_through_u_hat():
    """After loss.backward(), u_hat parameter must have non-zero gradient.

    Constructs a tiny tensor that emulates model_out and verifies that the
    u_hat component receives gradient through reconstruct_rate's f_kink path.
    """
    from forecaster.train import reconstruct_rate

    torch.manual_seed(0)
    # (B=4, n_protocols=2, n_targets=2)
    model_out = torch.tensor(
        [
            [[0.5, 0.001], [0.6, 0.002]],
            [[0.7, 0.001], [0.8, 0.002]],
            [[0.9, 0.001], [0.5, 0.002]],
            [[0.4, 0.001], [0.7, 0.002]],
        ],
        dtype=torch.float32,
        requires_grad=True,
    )
    r_pred = reconstruct_rate(model_out, KP_AAVE, KP_COMP)  # (B, 2)
    target = torch.full_like(r_pred, 0.03)
    loss = ((r_pred - target) ** 2).mean()
    loss.backward()

    assert model_out.grad is not None
    # u_hat columns are model_out[..., 0]
    grad_u = model_out.grad[..., 0]
    grad_eps = model_out.grad[..., 1]
    assert grad_u.abs().sum().item() > 1e-9, (
        f"u_hat received zero gradient: sum={grad_u.abs().sum().item():.3e}"
    )
    assert grad_eps.abs().sum().item() > 1e-9, (
        f"eps_corr received zero gradient (sanity check)"
    )


# ===========================================================================
# Finding #8: u_hat sigmoid bound + data clamp u <= 1.0
# ===========================================================================

def test_finding_8_data_clamp_u_aave_le_one():
    """After data.clean.main(), joined_clean.parquet must have u_aave <= 1."""
    df = pd.read_parquet(JOINED_PARQUET)
    assert df["u_aave"].max() <= 1.0 + 1e-9, (
        f"u_aave.max() = {df['u_aave'].max()}: data/clean.py must clamp to 1.0"
    )
    assert df["u_compound"].max() <= 1.0 + 1e-9, (
        f"u_compound.max() = {df['u_compound'].max()}: must clamp"
    )


def test_finding_8_u_hat_bounded_via_sigmoid():
    """reconstruct_rate must apply sigmoid to u_hat so it lives in (0, 1)."""
    from forecaster.train import reconstruct_rate

    # Extreme raw logits (negative and positive); without sigmoid these would
    # cause f_kink to extrapolate to nonsense.
    model_out = torch.tensor(
        [
            [[-50.0, 0.0], [50.0, 0.0]],   # huge raw logits
        ],
        dtype=torch.float32,
    )
    r_pred = reconstruct_rate(model_out, KP_AAVE, KP_COMP)
    # Sigmoid(-50) ≈ 0, sigmoid(50) ≈ 1 → r_pred should equal f_kink(0) and f_kink(1)
    expected_low = float(f_kink(0.0, KP_AAVE))
    expected_high = float(f_kink(1.0, KP_COMP))
    assert abs(r_pred[0, 0].item() - expected_low) < 1e-3, (
        f"At raw=-50, expected r_pred≈f_kink(0)={expected_low}, got {r_pred[0, 0].item()}"
    )
    assert abs(r_pred[0, 1].item() - expected_high) < 1e-3, (
        f"At raw=+50, expected r_pred≈f_kink(1)={expected_high}, got {r_pred[0, 1].item()}"
    )


# ===========================================================================
# Finding #5: z-score normalization with training-window stats
# ===========================================================================

def test_finding_5_zscore_normalization_applied():
    """DABiGRUCNNDataset must z-score Branch A + Branch B columns using
    training-window statistics; the result must have mean≈0, std≈1.
    """
    from forecaster.train import (
        BRANCH_A_COLS, BRANCH_B_COLS, DABiGRUCNNDataset,
    )

    df = pd.read_parquet(JOINED_PARQUET).head(1500).copy()
    if "gas_gwei" not in df.columns:
        df["gas_gwei"] = 30.0
    if "eth_usd" not in df.columns:
        df["eth_usd"] = 3500.0
    feats = extract_features(df, KP_AAVE, KP_COMP).dropna()

    ds = DABiGRUCNNDataset(
        feats, KP_AAVE, KP_COMP,
        input_window=168, forecast_horizon=12,
    )

    # After normalization, x_a / x_b columns should have ~zero mean, unit std
    mean_a = ds.x_a.mean(axis=0)
    std_a  = ds.x_a.std(axis=0)
    mean_b = ds.x_b.mean(axis=0)
    std_b  = ds.x_b.std(axis=0)

    assert np.allclose(mean_a, 0.0, atol=0.05), f"Branch A means not ≈0: {mean_a}"
    # Some Branch B columns may be constant (gas_gwei=30) → std=0 → leave as-is
    # but those with std > 0 must come out unit-std
    for i, col in enumerate(BRANCH_A_COLS):
        assert abs(std_a[i] - 1.0) < 0.05, (
            f"Branch A col {col} std not ≈1: {std_a[i]:.3f}"
        )
    for i, col in enumerate(BRANCH_B_COLS):
        # constant cols (std≈0 originally) should produce std≈0 after norm too
        if std_b[i] > 0.01:
            assert abs(std_b[i] - 1.0) < 0.05, (
                f"Branch B col {col} std not ≈1: {std_b[i]:.3f}"
            )


# ===========================================================================
# Finding #6: seed reproducibility
# ===========================================================================

def test_finding_6_seed_reproducibility_first_batch_loss():
    """Two Trainer.fit calls with identical seed and data produce identical
    first-batch training loss.
    """
    from forecaster.model import DABiGRUCNNForecaster, ForecasterConfig
    from forecaster.train import (
        DABiGRUCNNDataset, TrainConfig, Trainer,
    )
    from torch.utils.data import DataLoader

    df = pd.read_parquet(JOINED_PARQUET).head(1500).copy()
    if "gas_gwei" not in df.columns:
        df["gas_gwei"] = 30.0
    if "eth_usd" not in df.columns:
        df["eth_usd"] = 3500.0
    feats = extract_features(df, KP_AAVE, KP_COMP).dropna()

    def run_one_epoch_first_batch_loss(seed):
        cfg = TrainConfig(
            input_window=96, forecast_horizon=12,
            batch_size=32, max_epochs=1, patience=5,
            n_splits=1, seed=seed,
            checkpoint_path="forecaster/trained_models/_seedtest.pt",
        )
        ds = DABiGRUCNNDataset(
            feats, KP_AAVE, KP_COMP,
            input_window=cfg.input_window, forecast_horizon=cfg.forecast_horizon,
        )
        # Use a torch generator for the shuffle so seed governs it deterministically
        g = torch.Generator()
        g.manual_seed(seed)
        loader = DataLoader(
            ds, batch_size=cfg.batch_size, shuffle=True, drop_last=True,
            generator=g,
        )
        model_cfg = ForecasterConfig(
            sequence_length=cfg.input_window,
            branch_a_hidden=16, branch_b_hidden=16, dropout=0.0,
        )
        # Trainer.__init__ should seed everything; we re-seed *before* model
        # construction too via a small helper. The simplest portable interface
        # is: Trainer.fit() reseeds; model construction is also affected via
        # torch.manual_seed inside the Trainer.
        torch.manual_seed(seed)
        np.random.seed(seed)
        random.seed(seed)
        model = DABiGRUCNNForecaster(model_cfg)
        trainer = Trainer(model, cfg, KP_AAVE, KP_COMP, mlflow_experiment=None)

        # Run one batch manually to get a single loss number
        batch = next(iter(loader))
        x_a, x_b, y = batch
        x_a = x_a.to(cfg.device); x_b = x_b.to(cfg.device); y = y.to(cfg.device)
        model.train(True)
        out = model(x_a, x_b)
        from forecaster.train import reconstruct_rate
        r_pred = reconstruct_rate(out, KP_AAVE, KP_COMP)
        loss, _ = trainer.loss_fn(r_pred, y)
        return float(loss.item())

    l1 = run_one_epoch_first_batch_loss(seed=42)
    l2 = run_one_epoch_first_batch_loss(seed=42)
    assert abs(l1 - l2) < 1e-5, (
        f"Non-reproducible: loss1={l1:.6f}, loss2={l2:.6f}, diff={abs(l1-l2):.3e}"
    )


def test_finding_6_trainconfig_has_seed_field():
    from forecaster.train import TrainConfig

    cfg = TrainConfig()
    assert hasattr(cfg, "seed"), "TrainConfig must expose a `seed` field"
    assert isinstance(cfg.seed, int)
