"""Training pipeline for DA-BiGRU-CNN forecaster.

Implements PROJECT_2_PLAN.md S5 calibration and S4.4 optimiser configuration:

  * AdamW(lr=2e-3, weight_decay=0.01) per plan S4.4
  * gradient clipping max_norm=1.0
  * cosine annealing LR schedule
  * early stopping with patience=5
  * MLflow logging: per-epoch losses + components, grad-norm,
    val direction accuracy, training-curves PNG, best-checkpoint artifact
  * walk-forward CV (`n_splits` argument) — minimal correct implementation

The model produces (u_hat, eps_corr) per protocol; the realised rate is
reconstructed (CPU-side) via r_hat = f_kink(u_hat, kink_params) + eps_corr
so kink parameters can be swapped without retraining (model.py docstring).

Self-test (`python -m forecaster.train`):
generates 2000 hourly synthetic rows mimicking the joined Aave/Compound
schema, runs 2 training epochs, asserts val loss decreased.
"""
from __future__ import annotations

# NOTE: torch MUST be imported before numpy/pandas on Windows — otherwise
# pandas pulls in an MKL build that conflicts with torch's bundled DLLs
# (OSError WinError 1114 on c10.dll). Confirmed on this env (torch 2.12 CPU).
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

import json
import math
import random
import tempfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


def _seed_all(seed: int) -> None:
    """Seed torch + numpy + python `random` + CUDA for reproducibility.

    Audit finding #6 (2026-05-20). Called inside `Trainer.__init__` and
    `Trainer.fit` so a fresh Trainer with the same `cfg.seed` deterministically
    reproduces model init, optimizer state, and DataLoader shuffle order.
    """
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

import numpy as np
import pandas as pd

from data.features import (
    AaveKinkParams,
    CompoundKinkParams,
    extract_features,
    f_kink,
)
from forecaster.losses import CompositeForecastLoss
from forecaster.model import DABiGRUCNNForecaster, ForecasterConfig

# Lazy MLflow / matplotlib imports inside Trainer (selftest must run without).


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class TrainConfig:
    input_window: int = 168
    forecast_horizon: int = 12
    batch_size: int = 32
    lr: float = 2e-3
    weight_decay: float = 0.01
    grad_clip: float = 1.0
    max_epochs: int = 50
    patience: int = 5
    num_workers: int = 0
    device: str = "cpu"
    # composite loss
    alpha: float = 0.4
    beta: float = 0.5
    gamma: float = 0.1
    quantile_q: float = 0.9
    # CV
    n_splits: int = 1
    # reproducibility (audit finding #6, 2026-05-20)
    seed: int = 42
    # output
    checkpoint_path: str = "forecaster/trained_models/da_bigru_cnn.pt"


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

BRANCH_A_COLS = ("eps_aave", "eps_compound", "residual_spread")
BRANCH_B_COLS = (
    "u_aave", "u_compound",
    "dTVL_aave_24h", "dTVL_compound_24h",
    "gas_gwei", "tod_sin", "tod_cos",
)
TARGET_COLS = ("r_aave_annual", "r_compound_annual")


FEATURE_STATS_PATH = Path("data/cached/feature_stats.json")


class DABiGRUCNNDataset(Dataset):
    """Slices a long feature DataFrame into (x_a, x_b, y_target) windows.

    The dataframe must already have the columns produced by
    `data.features.extract_features` (plus gas_gwei).
    y_target is the realised future ANNUALISED rate at t+horizon for both
    protocols (shape: (n_protocols,)).

    Audit finding #5 (2026-05-20): Branch A and Branch B columns are
    z-scored in-place using either (a) stats computed from THIS dataset's
    rows (when `stats=None`, used on the training fold) or (b) the
    `stats` dict passed in (used on val/test folds so the normalization
    is identical to training — no data leakage). After computing stats
    on the training fold the caller should write them via
    `dataset.save_stats(path)` and pass `stats=...` to subsequent folds.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        params_a: AaveKinkParams,
        params_c: CompoundKinkParams,
        input_window: int = 168,
        forecast_horizon: int = 12,
        stats: dict | None = None,
    ):
        super().__init__()
        # Defensive copy + na-drop on the columns we need.
        cols = list(BRANCH_A_COLS) + list(BRANCH_B_COLS) + list(TARGET_COLS)
        df_clean = df[cols].replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)

        self.x_a = df_clean[list(BRANCH_A_COLS)].to_numpy(dtype=np.float32)
        self.x_b = df_clean[list(BRANCH_B_COLS)].to_numpy(dtype=np.float32)
        self.y   = df_clean[list(TARGET_COLS)].to_numpy(dtype=np.float32)

        # --- Audit Finding #5 fix: z-score normalization ----------------
        # Compute or reuse training-window stats. Std is floored at 1e-8 to
        # leave constant columns (e.g. gas_gwei stub at 30, dTVL_compound
        # all-zero) at their original near-zero scale instead of blowing up
        # by 1/0.
        if stats is None:
            x_a_mean = self.x_a.mean(axis=0)
            x_a_std  = self.x_a.std(axis=0)
            x_b_mean = self.x_b.mean(axis=0)
            x_b_std  = self.x_b.std(axis=0)
        else:
            x_a_mean = np.asarray(stats["x_a_mean"], dtype=np.float32)
            x_a_std  = np.asarray(stats["x_a_std"],  dtype=np.float32)
            x_b_mean = np.asarray(stats["x_b_mean"], dtype=np.float32)
            x_b_std  = np.asarray(stats["x_b_std"],  dtype=np.float32)

        # For columns with std≈0 (constant features), set std=1 so the
        # zero-centered column remains zero after normalization rather than
        # exploding (any std<1e-6 is treated as constant).
        x_a_std_safe = np.where(x_a_std > 1e-6, x_a_std, 1.0).astype(np.float32)
        x_b_std_safe = np.where(x_b_std > 1e-6, x_b_std, 1.0).astype(np.float32)

        self.x_a = ((self.x_a - x_a_mean) / x_a_std_safe).astype(np.float32)
        self.x_b = ((self.x_b - x_b_mean) / x_b_std_safe).astype(np.float32)

        # Persist stats so val/test datasets can be constructed with the same
        # normalization (call `dataset.save_stats(path)` on the training one).
        self.stats = {
            "x_a_mean": x_a_mean.tolist(),
            "x_a_std":  x_a_std.tolist(),
            "x_b_mean": x_b_mean.tolist(),
            "x_b_std":  x_b_std.tolist(),
            "branch_a_cols": list(BRANCH_A_COLS),
            "branch_b_cols": list(BRANCH_B_COLS),
        }

        self.input_window = int(input_window)
        self.horizon = int(forecast_horizon)
        self.n_samples = len(df_clean) - self.input_window - self.horizon + 1
        if self.n_samples <= 0:
            raise ValueError(
                f"Need at least {self.input_window + self.horizon} rows, "
                f"got {len(df_clean)}"
            )

        self.params_a = params_a
        self.params_c = params_c

    def save_stats(self, path: str | Path) -> None:
        """Persist normalization stats to JSON (for ONNX-side reuse)."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as f:
            json.dump(self.stats, f, indent=2)

    def __len__(self) -> int:
        return self.n_samples

    def __getitem__(self, idx: int):
        s = idx
        e = idx + self.input_window
        t = e + self.horizon - 1                     # target index
        x_a = torch.from_numpy(self.x_a[s:e])        # (T, 3)
        x_b = torch.from_numpy(self.x_b[s:e])        # (T, 7)
        y   = torch.from_numpy(self.y[t])            # (2,)
        return x_a, x_b, y


# ---------------------------------------------------------------------------
# Reconstruction helper: (u_hat, eps_corr) per protocol -> r_hat
# ---------------------------------------------------------------------------

def f_kink_torch_aave(u: torch.Tensor, p: AaveKinkParams) -> torch.Tensor:
    """Pure-torch port of `data.features._aave_supply_rate`, differentiable in u.

    Mirrors the numpy version exactly, using `torch.where` for the kink
    piecewise selector so gradient flows through `u` end-to-end.
    """
    u_opt = float(p.optimal_usage_ratio)
    below = p.base_variable_borrow_rate + p.slope1 * (u / u_opt)
    above = (
        p.base_variable_borrow_rate
        + p.slope1
        + p.slope2 * (u - u_opt) / (1.0 - u_opt)
    )
    borrow = torch.where(u <= u_opt, below, above)
    return u * borrow * (1.0 - p.reserve_factor)


def f_kink_torch_compound(u: torch.Tensor, p: CompoundKinkParams) -> torch.Tensor:
    """Pure-torch port of `data.features._compound_supply_rate`."""
    kink = float(p.supply_kink)
    below = p.supply_per_second_base + p.supply_per_second_slope_low * u
    above = (
        p.supply_per_second_base
        + p.supply_per_second_slope_low * kink
        + p.supply_per_second_slope_high * (u - kink)
    )
    return torch.where(u <= kink, below, above)


def reconstruct_rate(
    model_out: torch.Tensor,                          # (B, 2, 2)
    params_a: AaveKinkParams,
    params_c: CompoundKinkParams,
) -> torch.Tensor:
    """Closed-form r_hat = f_kink(u_hat, params) + eps_corr — fully differentiable.

    Audit Finding #7 + #8 fix (2026-05-20):
      * The kink is re-implemented in pure torch (`f_kink_torch_aave/compound`)
        so gradient flows through `u_hat` AS WELL AS `eps_corr`. The previous
        version did `.detach().cpu().numpy()` on u_hat, which silently killed
        2 of the 4 model output heads (`u_hat_aave`, `u_hat_compound`).
      * `u_hat` is squashed via `torch.sigmoid` so f_kink only sees values
        in (0, 1) — the physical domain of utilization. Without this, raw
        MLP logits could push f_kink into linear extrapolation territory
        and produce nonsense rates.
    """
    u_hat_raw = model_out[..., 0]                     # (B, 2)
    eps_corr = model_out[..., 1]                      # (B, 2)

    # Finding #8: constrain u_hat to (0, 1) before passing through f_kink.
    u_hat = torch.sigmoid(u_hat_raw)

    # Finding #7: pure-torch kink keeps the computation graph intact.
    kink_a = f_kink_torch_aave(u_hat[:, 0], params_a)
    kink_c = f_kink_torch_compound(u_hat[:, 1], params_c)
    kink_t = torch.stack([kink_a, kink_c], dim=1)
    return kink_t + eps_corr


# ---------------------------------------------------------------------------
# Trainer
# ---------------------------------------------------------------------------

@dataclass
class _EpochMetrics:
    loss: float
    mse: float
    wpearson: float
    quantile: float
    grad_norm: float = 0.0
    dir_acc: float = 0.0


class Trainer:
    """Train/val orchestrator with MLflow logging.

    Args:
        model: DABiGRUCNNForecaster instance
        cfg: TrainConfig
        params_a, params_c: kink params (used for reconstruction)
        mlflow_experiment: experiment name (None disables MLflow)
    """

    def __init__(
        self,
        model: DABiGRUCNNForecaster,
        cfg: TrainConfig,
        params_a: AaveKinkParams,
        params_c: CompoundKinkParams,
        mlflow_experiment: str | None = "defi-forecast-train",
    ):
        # Audit finding #6 (2026-05-20): seed all PRNGs BEFORE constructing
        # the optimizer / scheduler so AdamW's internal state is also
        # deterministic across runs with the same `cfg.seed`.
        _seed_all(cfg.seed)

        self.model = model.to(cfg.device)
        self.cfg = cfg
        self.params_a = params_a
        self.params_c = params_c
        self.loss_fn = CompositeForecastLoss(
            alpha=cfg.alpha, beta=cfg.beta, gamma=cfg.gamma, quantile_q=cfg.quantile_q,
        )
        self.optim = torch.optim.AdamW(
            self.model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay,
        )
        self.sched = torch.optim.lr_scheduler.CosineAnnealingLR(
            self.optim, T_max=cfg.max_epochs,
        )
        self.mlflow_experiment = mlflow_experiment
        self._mlflow = None  # lazy

    # ---- MLflow ----------------------------------------------------------
    def _ensure_mlflow(self):
        if self._mlflow is not None or self.mlflow_experiment is None:
            return
        try:
            import mlflow                            # noqa: WPS433
            mlflow.set_experiment(self.mlflow_experiment)
            self._mlflow = mlflow
        except Exception as exc:                     # noqa: BLE001
            print(f"[Trainer] MLflow disabled: {exc}")
            self.mlflow_experiment = None

    def _mlflow_log_metrics(self, metrics: dict[str, float], step: int):
        if self._mlflow is None:
            return
        try:
            self._mlflow.log_metrics(metrics, step=step)
        except Exception:                            # noqa: BLE001
            pass

    # ---- Loops -----------------------------------------------------------
    def _run_epoch(self, loader: DataLoader, train: bool) -> _EpochMetrics:
        self.model.train(train)
        total_loss = 0.0
        total_mse = 0.0
        total_wp = 0.0
        total_qt = 0.0
        total_grad = 0.0
        total_correct = 0
        total_seen = 0
        n_batches = 0

        for x_a, x_b, y in loader:
            x_a = x_a.to(self.cfg.device)
            x_b = x_b.to(self.cfg.device)
            y   = y.to(self.cfg.device)

            with torch.set_grad_enabled(train):
                out = self.model(x_a, x_b)             # (B, 2, 2)
                r_pred = reconstruct_rate(out, self.params_a, self.params_c)
                loss, comp = self.loss_fn(r_pred, y)

                if train:
                    self.optim.zero_grad(set_to_none=True)
                    loss.backward()
                    grad = torch.nn.utils.clip_grad_norm_(
                        self.model.parameters(), max_norm=self.cfg.grad_clip,
                    )
                    total_grad += float(grad)
                    self.optim.step()

            total_loss += comp["loss/total"]
            total_mse  += comp["loss/mse"]
            total_wp   += comp["loss/wpearson"]
            total_qt   += comp["loss/quantile"]
            n_batches  += 1

            # Direction accuracy: sign(r_aave - r_compound)
            with torch.no_grad():
                pred_sign = (r_pred[:, 0] > r_pred[:, 1])
                true_sign = (y[:, 0] > y[:, 1])
                total_correct += int((pred_sign == true_sign).sum().item())
                total_seen += y.shape[0]

        n = max(n_batches, 1)
        return _EpochMetrics(
            loss=total_loss / n,
            mse=total_mse / n,
            wpearson=total_wp / n,
            quantile=total_qt / n,
            grad_norm=total_grad / n if train else 0.0,
            dir_acc=total_correct / max(total_seen, 1),
        )

    def fit(self, train_loader: DataLoader, val_loader: DataLoader) -> dict[str, Any]:
        # Audit finding #6 (2026-05-20): re-seed at the start of fit so that
        # callers who construct a Trainer once and call fit() multiple times
        # still get reproducible results, AND so the cuDNN / DataLoader RNGs
        # are deterministic for this run.
        _seed_all(self.cfg.seed)
        self._ensure_mlflow()
        best_val = math.inf
        best_state = None
        patience_left = self.cfg.patience
        history: list[dict[str, float]] = []

        run_ctx = self._mlflow.start_run() if self._mlflow is not None else None
        try:
            if self._mlflow is not None:
                try:
                    self._mlflow.log_params(asdict(self.cfg))
                except Exception:                        # noqa: BLE001
                    pass

            for epoch in range(self.cfg.max_epochs):
                tr = self._run_epoch(train_loader, train=True)
                va = self._run_epoch(val_loader,   train=False)
                self.sched.step()

                metrics = {
                    "train/loss":     tr.loss,
                    "train/mse":      tr.mse,
                    "train/wpearson": tr.wpearson,
                    "train/quantile": tr.quantile,
                    "train/grad":     tr.grad_norm,
                    "train/dir_acc":  tr.dir_acc,
                    "val/loss":       va.loss,
                    "val/mse":        va.mse,
                    "val/wpearson":   va.wpearson,
                    "val/quantile":   va.quantile,
                    "val/dir_acc":    va.dir_acc,
                    "lr":             self.optim.param_groups[0]["lr"],
                }
                self._mlflow_log_metrics(metrics, step=epoch)
                history.append(metrics)
                print(
                    f"epoch {epoch:02d} | train {tr.loss:.4f} (wP {tr.wpearson:+.3f}) "
                    f"| val {va.loss:.4f} (wP {va.wpearson:+.3f}, dir {va.dir_acc:.2f})"
                )

                if va.loss < best_val - 1e-6:
                    best_val = va.loss
                    best_state = {k: v.detach().cpu().clone() for k, v in self.model.state_dict().items()}
                    patience_left = self.cfg.patience
                else:
                    patience_left -= 1
                    if patience_left <= 0:
                        print(f"early stopping at epoch {epoch}")
                        break

            if best_state is not None:
                self.model.load_state_dict(best_state)

            ckpt_path = Path(self.cfg.checkpoint_path)
            ckpt_path.parent.mkdir(parents=True, exist_ok=True)
            torch.save({
                "model_state_dict": self.model.state_dict(),
                "cfg":              asdict(self.cfg),
                "model_cfg":        asdict(self.model.cfg),
                "best_val_loss":    best_val,
            }, ckpt_path)

            if self._mlflow is not None:
                try:
                    self._mlflow.log_artifact(str(ckpt_path))
                    self._log_curve(history)
                except Exception:                        # noqa: BLE001
                    pass

            return {"best_val_loss": best_val, "history": history, "ckpt": str(ckpt_path)}
        finally:
            if run_ctx is not None:
                try:
                    self._mlflow.end_run()
                except Exception:                        # noqa: BLE001
                    pass

    def _log_curve(self, history: list[dict[str, float]]):
        try:
            import matplotlib                        # noqa: WPS433
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt          # noqa: WPS433
        except Exception:                            # noqa: BLE001
            return
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.plot([h["train/loss"] for h in history], label="train")
        ax.plot([h["val/loss"]   for h in history], label="val")
        ax.set_xlabel("epoch"); ax.set_ylabel("composite loss"); ax.legend()
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "training_curves.png"
            fig.savefig(p, dpi=100, bbox_inches="tight")
            plt.close(fig)
            try:
                self._mlflow.log_artifact(str(p))
            except Exception:                        # noqa: BLE001
                pass


# ---------------------------------------------------------------------------
# Walk-forward CV
# ---------------------------------------------------------------------------

def walk_forward_splits(n_rows: int, n_splits: int, val_frac: float = 0.2):
    """Yields (train_idx_end, val_idx_end) bounds for sequential splits.

    Split k uses rows [0, train_k_end) for training, [train_k_end, val_k_end)
    for validation. Splits grow forward in time (no shuffling).
    """
    if n_splits < 1:
        raise ValueError("n_splits must be >= 1")
    if n_splits == 1:
        cut = int(n_rows * (1.0 - val_frac))
        yield (cut, n_rows)
        return
    fold = n_rows // (n_splits + 1)
    for k in range(1, n_splits + 1):
        train_end = fold * k
        val_end   = min(train_end + fold, n_rows)
        yield (train_end, val_end)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(
    data_path: str,
    kink_params_path: str,
    mlflow_experiment: str = "defi-forecast-train",
    **hp,
) -> dict[str, Any]:
    """Load data + kink params, build dataset, run training.

    `data_path`: parquet produced by `data.clean` with `extract_features` applied.
    `kink_params_path`: JSON {"aave": {...AaveKinkParams...}, "compound": {...CompoundKinkParams...}}.
    `**hp`: TrainConfig overrides.
    """
    df = pd.read_parquet(data_path)
    with open(kink_params_path) as f:
        kp = json.load(f)
    params_a = AaveKinkParams(**kp["aave"])
    params_c = CompoundKinkParams(**kp["compound"])

    cfg = TrainConfig(**hp)

    # Walk-forward CV: report best val loss across folds; final model trained
    # on the last fold's data (most recent regime).
    results = []
    for fold_idx, (tr_end, val_end) in enumerate(
        walk_forward_splits(len(df), cfg.n_splits)
    ):
        print(f"\n=== fold {fold_idx + 1}/{cfg.n_splits}  "
              f"train[:{tr_end}]  val[{tr_end}:{val_end}] ===")
        ds_tr = DABiGRUCNNDataset(df.iloc[:tr_end], params_a, params_c,
                                  cfg.input_window, cfg.forecast_horizon)
        # Finding #5: val/test consume the TRAINING-fold's normalization stats
        # (no leakage). Persist them to disk so ONNX-side / strategy-side
        # inference can reuse the exact same scaling.
        ds_tr.save_stats(FEATURE_STATS_PATH)
        ds_va = DABiGRUCNNDataset(df.iloc[tr_end:val_end], params_a, params_c,
                                  cfg.input_window, cfg.forecast_horizon,
                                  stats=ds_tr.stats)
        tr_loader = DataLoader(ds_tr, batch_size=cfg.batch_size, shuffle=True,
                               num_workers=cfg.num_workers, drop_last=True)
        va_loader = DataLoader(ds_va, batch_size=cfg.batch_size, shuffle=False,
                               num_workers=cfg.num_workers)

        model = DABiGRUCNNForecaster(ForecasterConfig(sequence_length=cfg.input_window,
                                                      forecast_horizon=cfg.forecast_horizon))
        trainer = Trainer(model, cfg, params_a, params_c,
                          mlflow_experiment=mlflow_experiment)
        out = trainer.fit(tr_loader, va_loader)
        results.append(out)

    return {"folds": results, "best_val_loss": min(r["best_val_loss"] for r in results)}


# ---------------------------------------------------------------------------
# Synthetic-data self-test
# ---------------------------------------------------------------------------

def _make_synth_df(n_rows: int = 2000, seed: int = 0) -> pd.DataFrame:
    """Synthesise a 2000-hour joined Aave/Compound schema.

    Columns: r_aave, r_compound, u_aave, u_compound, tvl_aave, tvl_compound,
             gas_gwei, eth_usd
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n_rows, freq="h", tz="UTC")

    # Utilization random walks confined to [0.05, 0.97].
    def util_walk(start: float) -> np.ndarray:
        u = np.empty(n_rows)
        u[0] = start
        for i in range(1, n_rows):
            u[i] = np.clip(u[i - 1] + rng.normal(0.0, 0.01), 0.05, 0.97)
        return u

    u_a = util_walk(0.55)
    u_c = util_walk(0.45)

    # Build "true" kink params (defaults).
    pa = AaveKinkParams(
        base_variable_borrow_rate=0.0, slope1=0.05, slope2=0.60,
        optimal_usage_ratio=0.92, reserve_factor=0.10,
    )
    pc = CompoundKinkParams(
        supply_kink=0.85,
        supply_per_second_base=0.0,
        supply_per_second_slope_low=0.04,
        supply_per_second_slope_high=0.50,
    )
    r_a = np.asarray(f_kink(u_a, pa)) + rng.normal(0, 0.002, n_rows)
    r_c = np.asarray(f_kink(u_c, pc)) + rng.normal(0, 0.002, n_rows)

    tvl_a = 1e8 + np.cumsum(rng.normal(0, 1e5, n_rows))
    tvl_c = 5e7 + np.cumsum(rng.normal(0, 5e4, n_rows))
    gas = np.clip(20 + 5 * rng.standard_normal(n_rows) + 10 * np.sin(np.arange(n_rows) / 24), 5, 200)
    eth = 3000 + np.cumsum(rng.normal(0, 5, n_rows))

    df = pd.DataFrame({
        "r_aave": r_a, "r_compound": r_c,
        "u_aave": u_a, "u_compound": u_c,
        "tvl_aave": tvl_a, "tvl_compound": tvl_c,
        "gas_gwei": gas, "eth_usd": eth,
    }, index=idx)
    return df, pa, pc


def _selftest() -> None:
    torch.manual_seed(0)
    np.random.seed(0)

    df_raw, pa, pc = _make_synth_df(n_rows=2000)
    df_feat = extract_features(df_raw, pa, pc).dropna()

    cfg = TrainConfig(
        input_window=64, forecast_horizon=12,
        batch_size=32, max_epochs=2, patience=10,
        checkpoint_path=str(Path(__file__).parent / "trained_models" / "da_bigru_cnn_selftest.pt"),
    )

    n = len(df_feat)
    cut = int(0.7 * n)
    ds_tr = DABiGRUCNNDataset(df_feat.iloc[:cut], pa, pc,
                              cfg.input_window, cfg.forecast_horizon)
    ds_va = DABiGRUCNNDataset(df_feat.iloc[cut:], pa, pc,
                              cfg.input_window, cfg.forecast_horizon)
    tr_loader = DataLoader(ds_tr, batch_size=cfg.batch_size, shuffle=True, drop_last=True)
    va_loader = DataLoader(ds_va, batch_size=cfg.batch_size, shuffle=False)

    model = DABiGRUCNNForecaster(ForecasterConfig(
        sequence_length=cfg.input_window, forecast_horizon=cfg.forecast_horizon,
    ))
    trainer = Trainer(model, cfg, pa, pc, mlflow_experiment=None)

    # Capture epoch-1 val loss BEFORE the cfg.max_epochs=2 run so we have
    # two distinct points to compare.
    pre = trainer._run_epoch(va_loader, train=False).loss
    out = trainer.fit(tr_loader, va_loader)
    post = out["best_val_loss"]

    assert post <= pre + 1e-3, (
        f"Val loss did not improve: pre={pre:.4f} post={post:.4f}"
    )
    print(f"\nTrainer selftest OK: pre-val {pre:.4f} -> post-val {post:.4f}")


if __name__ == "__main__":
    _selftest()
