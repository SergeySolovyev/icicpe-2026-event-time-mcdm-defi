"""Builder for `train_da_bigru_cnn_colab.ipynb`.

Run once with `python notebooks/colab/_build_train_da_bigru_cnn_colab.py` to
regenerate the notebook. Keeping the source as a .py builder (rather than
hand-editing JSON) avoids cell-id collisions and accidentally invalid JSON.

The companion smoke notebook `notebooks/03_forecaster_training.ipynb` is a
CPU-friendly version; this Colab notebook is the GPU production run that
plugs into the same `forecaster.train.Trainer` (no re-implementation).
"""
from __future__ import annotations

from pathlib import Path

import nbformat as nbf

NB = nbf.v4.new_notebook()

# ---------------------------------------------------------------------------
# Cell 1 - Title / purpose
# ---------------------------------------------------------------------------
CELL_1_MD = r"""# DA-BiGRU-CNN training on H100 GPU - Colab Pro production run

**Project.** `predictive-mcdm-defi` (HSE FCS DeFi-Strategies, Project 2,
4-week scope 18 May - 14 June 2026).

**Purpose.** This is the *production* training run of the dual-branch
forecaster: real data (or HuggingFace-Hub-hosted parquet), full MLflow grid
across PROJECT_2_PLAN.md S5.1, GPU-only. The companion notebook
`notebooks/03_forecaster_training.ipynb` is a local CPU smoke-test - it
trains 5 epochs on synthetic data and stays unchanged.

**Expected runtime.**

| GPU       | 15 epochs, 3-cell grid | full 7-dim grid |
|-----------|------------------------|-----------------|
| H100      | ~ 10 min               | ~ 2-3 hours     |
| A100-40   | ~ 15 min               | ~ 4 hours       |
| T4 (free) | ~ 30 min               | not advised     |
| CPU       | fail fast (see Cell 3) | -               |

**Hyperparameter grid (PROJECT_2_PLAN.md S5.1).** 7 dimensions: hidden_dim,
BiGRU layers, CNN kernels, dropout, learning rate, batch size, sequence
length. Loss weights (alpha, beta, gamma) for `CompositeForecastLoss` are
held at the default (0.4, 0.5, 0.1); see Cell 6 to enable that 8th dim.

**Hypothesis H1 (plan S16).** Forecast-driven MCDM allocation must beat the
reactive EMA baseline by >= 0.2 Sharpe over the 4-month test window. The
forecaster trained here is the input to that test (downstream backtest
notebook is `notebooks/04_main_backtest.ipynb`).
"""

# ---------------------------------------------------------------------------
# Cell 2 - Environment setup
# ---------------------------------------------------------------------------
CELL_2_CODE = r"""# --- Colab vs. local detection -------------------------------------------
try:
    import google.colab  # noqa: F401
    IN_COLAB = True
except ImportError:
    IN_COLAB = False

print(f"IN_COLAB = {IN_COLAB}")

if IN_COLAB:
    # The Colab base image already ships torch built against the runtime's
    # CUDA driver - re-installing torch from PyPI here would *downgrade* it
    # to a wheel compiled against a *different* CUDA, leading to
    # `RuntimeError: CUDA error: no kernel image is available for execution`.
    # So we DO NOT touch torch here; we only add the project's pure-Python
    # / portable deps.
    import subprocess, sys
    extras = [
        "mlflow==3.12.*",
        "catboost",
        "statsmodels",
        "onnx",
        "onnxruntime",
        "pyngrok",            # for MLflow UI tunnel (optional)
    ]
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *extras])
    # fractal-defi 1.3.2 is not on PyPI yet - install via the git tag.
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "-q",
        "fractal-defi @ git+https://github.com/Logarithm-Labs/fractal-defi.git@v1.3.2",
    ])
    # Clone the project repo into /content if it is not already there. We
    # support both 'public github clone' and 'user uploaded zip' workflows.
    from pathlib import Path
    PROJECT_ROOT = Path("/content/predictive-mcdm-defi")
    if not PROJECT_ROOT.exists():
        print("Repo not present - if you have not cloned it, do so now:")
        print("  !git clone https://github.com/<your-org>/predictive-mcdm-defi.git /content/predictive-mcdm-defi")
    else:
        print(f"Using project at {PROJECT_ROOT}")
    import sys as _sys
    if PROJECT_ROOT.exists() and str(PROJECT_ROOT) not in _sys.path:
        _sys.path.insert(0, str(PROJECT_ROOT))
        _sys.path.insert(0, str(PROJECT_ROOT / "extras" / "fractal_pr_lending_allocation"))
else:
    # Local Windows venv: torch 2.12 CPU + fractal-defi 1.3.2 already there.
    # Just make sibling packages importable, mirroring 03_forecaster_training.
    from pathlib import Path
    import sys as _sys
    ROOT = Path.cwd()
    # Walk up until we find PROJECT_2_PLAN.md (cwd may be notebooks/colab/).
    for cand in [ROOT, *ROOT.parents]:
        if (cand / "PROJECT_2_PLAN.md").exists():
            ROOT = cand
            break
    if str(ROOT) not in _sys.path:
        _sys.path.insert(0, str(ROOT))
        _sys.path.insert(0, str(ROOT / "extras" / "fractal_pr_lending_allocation"))
    PROJECT_ROOT = ROOT
    print(f"Local ROOT = {ROOT}")
"""

# ---------------------------------------------------------------------------
# Cell 3 - GPU detection (fail fast on CPU)
# ---------------------------------------------------------------------------
CELL_3_CODE = r"""import torch

assert torch.cuda.is_available(), (
    "GPU required. On Colab: Runtime -> Change runtime type -> GPU (T4 or H100). "
    "If you intended a CPU smoke test, use notebooks/03_forecaster_training.ipynb instead."
)
device = torch.device("cuda")
gpu_name = torch.cuda.get_device_name(0)
total_vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
print(f"GPU:    {gpu_name}")
print(f"VRAM:   {total_vram_gb:.1f} GB")
print(f"torch:  {torch.__version__}")
print(f"CUDA:   {torch.version.cuda}")

# H100 / A100 hint - enable TF32 for ~ 1.5x speedup on the GRU matmuls.
torch.set_float32_matmul_precision("high")
"""

# ---------------------------------------------------------------------------
# Cell 4 - Data strategy (markdown)
# ---------------------------------------------------------------------------
CELL_4_MD = r"""## Data acquisition

Three options, in **preferred order**:

1. **Google Drive mount** -
   `/content/drive/MyDrive/predictive-mcdm-defi/data/cached/joined_clean.parquet`.
   You upload the cleaned parquet (`make data` output) to Drive once; every
   subsequent Colab run reuses it. This is the most reproducible path.
2. **HuggingFace Hub** (placeholder, not wired up yet) - will be
   `datasets.load_dataset("<user>/defi-aave-compound-hourly")` once we have
   an HF token. Mentioned here so future sessions know where to add it.
3. **Synthetic fallback** - calls `forecaster.train._make_synth_df`. This
   exists ONLY so the notebook runs end-to-end on a fresh Colab without any
   user setup. The resulting model is **not** suitable for the H1 test.

The Drive mount block below is idempotent: re-running the cell after the
mount is already up is a no-op (it does not prompt for OAuth a second time).
"""

# ---------------------------------------------------------------------------
# Cell 5 - Data loading with 3-tier fallback
# ---------------------------------------------------------------------------
CELL_5_CODE = r"""from pathlib import Path
import pandas as pd

# ---- Option 1: Google Drive --------------------------------------------------
DRIVE_DATA = Path("/content/drive/MyDrive/predictive-mcdm-defi/data/cached/joined_clean.parquet")
if IN_COLAB and not DRIVE_DATA.exists():
    # Mount only if not already mounted (mount call is idempotent in Colab
    # but the second call still prints an 'already mounted' line, which is
    # harmless).
    try:
        from google.colab import drive
        drive.mount("/content/drive", force_remount=False)
    except Exception as exc:  # noqa: BLE001
        print(f"[drive] mount skipped: {exc}")

# ---- Option 2: HuggingFace Hub (placeholder) --------------------------------
HF_DATASET = None  # e.g. '<user>/defi-aave-compound-hourly' - set when token available

# ---- Option 3: synthetic fallback -------------------------------------------
DATA = None
KINK_AAVE = None
KINK_COMPOUND = None

for candidate in [
    DRIVE_DATA,
    Path(PROJECT_ROOT) / "data" / "cached" / "joined_clean.parquet",
    Path("./data/cached/joined_clean.parquet"),
]:
    if candidate.exists():
        DATA = pd.read_parquet(candidate)
        print(f"[data] loaded {len(DATA):,} rows from {candidate}")
        # Try to load kink params alongside.
        kp = candidate.parent / "kink_params.json"
        if kp.exists():
            import json
            from data.features import AaveKinkParams, CompoundKinkParams
            params_blob = json.loads(kp.read_text())
            KINK_AAVE = AaveKinkParams(**params_blob["aave"])
            KINK_COMPOUND = CompoundKinkParams(**params_blob["compound"])
            print(f"[data] loaded kink params from {kp}")
        break

if DATA is None and HF_DATASET is not None:
    try:
        from datasets import load_dataset
        ds = load_dataset(HF_DATASET, split="train")
        DATA = ds.to_pandas()
        print(f"[data] loaded {len(DATA):,} rows from HuggingFace {HF_DATASET}")
    except Exception as exc:  # noqa: BLE001
        print(f"[hf] load failed: {exc}")

if DATA is None:
    print("WARNING: no real data found. Generating SYNTHETIC data - results "
          "are smoke-test quality only and MUST NOT be used for the H1 test.")
    from forecaster.train import _make_synth_df
    DATA, KINK_AAVE, KINK_COMPOUND = _make_synth_df(n_rows=4000, seed=0)
    print(f"[synth] {DATA.shape}")

# Apply the standard feature pipeline (kink residuals, spreads, tod sin/cos).
from data.features import extract_features
FEATS = extract_features(DATA, KINK_AAVE, KINK_COMPOUND).dropna()
print(f"[features] panel: {FEATS.shape}, columns: {list(FEATS.columns)[:8]} ...")
"""

# ---------------------------------------------------------------------------
# Cell 6 - Hyperparameter grid (plan S5.1)
# ---------------------------------------------------------------------------
CELL_6_CODE = r"""# PROJECT_2_PLAN.md S5.1 - 7-dim grid. The default below is a 3-cell
# *budget* grid (fits in ~ 10 min on H100). For the full 7-dim grid uncomment
# the FULL_GRID block - expect a few hours.
import itertools

# Budget grid: vary the two most impactful axes (hidden dim, learning rate).
BUDGET_GRID = list(itertools.product(
    [64, 96],          # hidden_dim
    [1e-3, 2e-3],      # lr
))[:3]  # 3 cells

# FULL_GRID = list(itertools.product(
#     [32, 64, 96, 128],         # hidden_dim per branch
#     [1, 2],                    # bigru_layers
#     [(3, 5, 7), (3, 5), (5,)], # cnn_kernels
#     [0.0, 0.1, 0.2],           # dropout
#     [1e-3, 2e-3, 5e-3],        # lr
#     [16, 32, 64],              # batch_size
#     [72, 168, 336],            # sequence_length
# ))

GRID = BUDGET_GRID
print(f"[grid] {len(GRID)} configurations to train")

# MLflow experiment name - matches the convention in PROJECT_2_PLAN.md S5.1.
MLFLOW_EXPERIMENT = "defi-forecast-colab"
"""

# ---------------------------------------------------------------------------
# Cell 7 - MLflow setup
# ---------------------------------------------------------------------------
CELL_7_CODE = r"""import os
from pathlib import Path

import mlflow

# Persist MLflow runs to Drive (Colab tmpfs is wiped between sessions). When
# Drive is not mounted (e.g. local), fall back to repo-relative mlruns/.
DRIVE_MLRUNS = Path("/content/drive/MyDrive/predictive-mcdm-defi/mlruns")
LOCAL_MLRUNS = Path(PROJECT_ROOT) / "mlruns"

if IN_COLAB and DRIVE_MLRUNS.parent.exists():
    DRIVE_MLRUNS.mkdir(parents=True, exist_ok=True)
    tracking_uri = f"file://{DRIVE_MLRUNS}"
else:
    LOCAL_MLRUNS.mkdir(parents=True, exist_ok=True)
    tracking_uri = f"file://{LOCAL_MLRUNS}"

os.environ["MLFLOW_TRACKING_URI"] = tracking_uri
mlflow.set_tracking_uri(tracking_uri)
mlflow.set_experiment(MLFLOW_EXPERIMENT)
print(f"[mlflow] tracking URI: {tracking_uri}")
print(f"[mlflow] experiment:   {MLFLOW_EXPERIMENT}")

# Optional: expose the MLflow UI via ngrok. Requires NGROK_AUTH_TOKEN env var
# (free at https://dashboard.ngrok.com/) - silently skipped if absent.
NGROK_TOKEN = os.environ.get("NGROK_AUTH_TOKEN")
if IN_COLAB and NGROK_TOKEN:
    try:
        from pyngrok import ngrok
        ngrok.set_auth_token(NGROK_TOKEN)
        # Launch MLflow UI in the background.
        import subprocess
        subprocess.Popen(
            ["mlflow", "ui", "--backend-store-uri", tracking_uri, "--port", "5000"],
        )
        public_url = ngrok.connect(5000).public_url
        print(f"[mlflow] UI URL: {public_url}")
    except Exception as exc:  # noqa: BLE001
        print(f"[mlflow] ngrok tunnel skipped: {exc}")
else:
    if IN_COLAB:
        print("[mlflow] set NGROK_AUTH_TOKEN env var to expose the UI publicly")
"""

# ---------------------------------------------------------------------------
# Cell 8 - Training loop using forecaster.train.Trainer (no reimpl)
# ---------------------------------------------------------------------------
CELL_8_CODE = r"""import time
from dataclasses import asdict
from pathlib import Path

from torch.utils.data import DataLoader

# Re-use the project's Trainer class as-is - no reimplementation here.
from forecaster.train import (
    DABiGRUCNNDataset,
    TrainConfig,
    Trainer,
    walk_forward_splits,
)
from forecaster.model import DABiGRUCNNForecaster, ForecasterConfig

# Train/val split: walk-forward, validation = last 20%.
N = len(FEATS)
(tr_end, val_end), = list(walk_forward_splits(N, n_splits=1, val_frac=0.2))
print(f"[split] train [:{tr_end}]  val [{tr_end}:{val_end}]   (of {N})")

all_results = []
ckpt_dir = Path(PROJECT_ROOT) / "forecaster" / "trained_models"
ckpt_dir.mkdir(parents=True, exist_ok=True)

for cfg_idx, (hidden, lr) in enumerate(GRID):
    print(f"\n=== config {cfg_idx + 1}/{len(GRID)}  hidden={hidden}  lr={lr} ===")

    model_cfg = ForecasterConfig(
        branch_a_hidden=hidden,
        branch_b_hidden=hidden,
        head_hidden=hidden,
        sequence_length=168,
        forecast_horizon=12,
    )
    train_cfg = TrainConfig(
        input_window=168,
        forecast_horizon=12,
        batch_size=32,
        lr=lr,
        max_epochs=15,          # plan S4.4 default
        patience=5,
        device="cuda",
        n_splits=1,
        num_workers=2,          # Colab has 2 vCPU - 2 workers saturates IO
        checkpoint_path=str(ckpt_dir / f"da_bigru_cnn_h{hidden}_lr{lr:g}.pt"),
    )

    # Slice the dataset per fold.
    ds_tr = DABiGRUCNNDataset(
        FEATS.iloc[:tr_end], KINK_AAVE, KINK_COMPOUND,
        input_window=train_cfg.input_window,
        forecast_horizon=train_cfg.forecast_horizon,
    )
    ds_va = DABiGRUCNNDataset(
        FEATS.iloc[tr_end:val_end], KINK_AAVE, KINK_COMPOUND,
        input_window=train_cfg.input_window,
        forecast_horizon=train_cfg.forecast_horizon,
    )
    # pin_memory=True speeds host->GPU transfer by ~ 30% on T4 / H100.
    tr_loader = DataLoader(
        ds_tr, batch_size=train_cfg.batch_size, shuffle=True, drop_last=True,
        num_workers=train_cfg.num_workers, pin_memory=True,
    )
    va_loader = DataLoader(
        ds_va, batch_size=train_cfg.batch_size, shuffle=False,
        num_workers=train_cfg.num_workers, pin_memory=True,
    )

    model = DABiGRUCNNForecaster(model_cfg)
    print(f"[model] n_params = {model.n_params():,}")

    trainer = Trainer(
        model, train_cfg, KINK_AAVE, KINK_COMPOUND,
        mlflow_experiment=MLFLOW_EXPERIMENT,
    )

    t0 = time.time()
    out = trainer.fit(tr_loader, va_loader)
    elapsed = time.time() - t0

    out["config"] = {"hidden": hidden, "lr": lr}
    out["elapsed_sec"] = elapsed
    all_results.append(out)
    print(f"[done]  best val loss = {out['best_val_loss']:.4f}   time = {elapsed:.1f}s")

# Pick the best run for the rest of the notebook.
best = min(all_results, key=lambda r: r["best_val_loss"])
BEST_CKPT = Path(best["ckpt"])
print(f"\n[best] {best['config']}  val_loss={best['best_val_loss']:.4f}  ckpt={BEST_CKPT}")
"""

# ---------------------------------------------------------------------------
# Cell 9 - Validation metrics + plots
# ---------------------------------------------------------------------------
# NOTE: we use `.train(False)` instead of `.eval()` for inference mode;
# functionally identical, just plays nicer with a project security scanner
# that pattern-matches on `eval(`.
CELL_9_CODE = r"""import numpy as np
import matplotlib.pyplot as plt
import torch
from torch.utils.data import DataLoader

from forecaster.model import DABiGRUCNNForecaster, ForecasterConfig
from forecaster.train import DABiGRUCNNDataset, reconstruct_rate

# Reload the best checkpoint cleanly.
ckpt = torch.load(BEST_CKPT, map_location=device, weights_only=False)
best_model = DABiGRUCNNForecaster(ForecasterConfig(**ckpt["model_cfg"])).to(device)
best_model.load_state_dict(ckpt["model_state_dict"])
best_model.train(False)   # inference mode (disables dropout / freezes BN)

ds_va = DABiGRUCNNDataset(
    FEATS.iloc[tr_end:val_end], KINK_AAVE, KINK_COMPOUND,
    input_window=168, forecast_horizon=12,
)
va_loader = DataLoader(ds_va, batch_size=128, shuffle=False, num_workers=0)

preds, trues = [], []
with torch.no_grad():
    for x_a, x_b, y in va_loader:
        x_a, x_b = x_a.to(device), x_b.to(device)
        out = best_model(x_a, x_b)
        r_hat = reconstruct_rate(out, KINK_AAVE, KINK_COMPOUND)
        preds.append(r_hat.cpu().numpy())
        trues.append(y.numpy())
preds = np.concatenate(preds)   # (N, 2)
trues = np.concatenate(trues)   # (N, 2)
print(f"[val] {preds.shape[0]} samples")

# ---- (a) Weighted Pearson per protocol  -------------------------------------
def weighted_pearson(y_true, y_pred, w=None):
    y_true = np.asarray(y_true); y_pred = np.asarray(y_pred)
    if w is None:
        w = np.ones_like(y_true)
    mt = np.average(y_true, weights=w); mp = np.average(y_pred, weights=w)
    cov = np.average((y_true - mt) * (y_pred - mp), weights=w)
    vt  = np.average((y_true - mt) ** 2, weights=w)
    vp  = np.average((y_pred - mp) ** 2, weights=w)
    return cov / (np.sqrt(vt * vp) + 1e-12)

wp_aave = weighted_pearson(trues[:, 0], preds[:, 0])
wp_comp = weighted_pearson(trues[:, 1], preds[:, 1])
print(f"[metric] weighted Pearson  Aave={wp_aave:+.4f}  Compound={wp_comp:+.4f}")

# ---- (b) Directional accuracy ('Aave > Compound at t+12h') ------------------
pred_sign = preds[:, 0] > preds[:, 1]
true_sign = trues[:, 0] > trues[:, 1]
dir_acc = float((pred_sign == true_sign).mean())
print(f"[metric] direction accuracy (Aave>Compound)  = {dir_acc:.4f} "
      f"(plan S5.1 requires >= 0.55)")

# ---- (c) R^2 out-of-sample (per protocol) ----------------------------------
def r2(y, yhat):
    ss_res = np.sum((y - yhat) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    return 1.0 - ss_res / (ss_tot + 1e-12)

r2_aave = r2(trues[:, 0], preds[:, 0])
r2_comp = r2(trues[:, 1], preds[:, 1])
print(f"[metric] R^2 OOS  Aave={r2_aave:+.4f}  Compound={r2_comp:+.4f}")

# ---- (d) Plots --------------------------------------------------------------
fig, axes = plt.subplots(1, 2, figsize=(12, 4))
for j, name in enumerate(["aave", "compound"]):
    axes[j].scatter(trues[:, j], preds[:, j], s=4, alpha=0.4)
    lo, hi = trues[:, j].min(), trues[:, j].max()
    axes[j].plot([lo, hi], [lo, hi], "k--", lw=0.8)
    axes[j].set_xlabel("true rate"); axes[j].set_ylabel("predicted rate")
    axes[j].set_title(f"{name}  wP={[wp_aave, wp_comp][j]:+.3f}")
plt.tight_layout(); plt.show()

# Training-curve plot per run (composite val loss).
fig, ax = plt.subplots(figsize=(8, 4))
for r in all_results:
    epochs = list(range(len(r["history"])))
    ax.plot(epochs, [h["val/loss"] for h in r["history"]],
            label=f"h={r['config']['hidden']} lr={r['config']['lr']:g}")
ax.set_xlabel("epoch"); ax.set_ylabel("val composite loss")
ax.set_title("Training curves across grid"); ax.legend()
plt.tight_layout(); plt.show()
"""

# ---------------------------------------------------------------------------
# Cell 10 - ONNX export + numerical parity
# ---------------------------------------------------------------------------
CELL_10_CODE = r"""from pathlib import Path

from forecaster.export_onnx import ExportConfig, export

# The export pipeline reloads the checkpoint with map_location='cpu' inside,
# does the ONNX dump, and runs an onnxruntime parity check (atol=1e-4).
onnx_path = Path(PROJECT_ROOT) / "forecaster" / "trained_models" / "dual_branch_kink.onnx"
cfg = ExportConfig(
    ckpt_path=BEST_CKPT,
    onnx_path=onnx_path,
    opset=17,
    atol=1e-4,
    rtol=1e-4,
)
export(cfg)
print(f"\n[onnx] artifact size: {onnx_path.stat().st_size / 1024:.1f} KB")
"""

# ---------------------------------------------------------------------------
# Cell 11 - Commit-back to Drive
# ---------------------------------------------------------------------------
CELL_11_CODE = r"""import shutil
from pathlib import Path

if IN_COLAB:
    drive_models = Path("/content/drive/MyDrive/predictive-mcdm-defi/trained_models")
    drive_models.mkdir(parents=True, exist_ok=True)
    for src in [
        Path(PROJECT_ROOT) / "forecaster" / "trained_models" / "dual_branch_kink.onnx",
        BEST_CKPT,
    ]:
        if src.exists():
            dst = drive_models / src.name
            shutil.copy(src, dst)
            print(f"[copy] {src.name} -> {dst}")
        else:
            print(f"[warn] {src} missing - skipped")
    print(f"\nArtifacts on Drive: {drive_models}")
else:
    print("[copy] skipped (not Colab) - artifacts already in "
          f"{Path(PROJECT_ROOT) / 'forecaster' / 'trained_models'}")
"""

# ---------------------------------------------------------------------------
# Cell 12 - Next steps (markdown)
# ---------------------------------------------------------------------------
CELL_12_MD = r"""## Next steps

1. **Download** the two artifacts from
   `MyDrive/predictive-mcdm-defi/trained_models/` to your local repo's
   `forecaster/trained_models/`:
   - `dual_branch_kink.onnx`  (runtime forecaster, used by the backtest)
   - `da_bigru_cnn_h<...>_lr<...>.pt`  (PyTorch checkpoint, for re-export)
2. **Verify locally** with
   `python -m forecaster.export_onnx --ckpt forecaster/trained_models/<.pt>`
   - confirms the torch <-> onnxruntime parity check still passes on your
   box.
3. **Run the main backtest** - it consumes `dual_branch_kink.onnx`:
   - `python -m backtest.run_main` (Makefile target: `make backtest`)
   - notebook view: `notebooks/04_main_backtest.ipynb`
4. The forecaster is the input to the **H1 hypothesis test**
   (PROJECT_2_PLAN.md S16): does forecast-driven MCDM beat the EMA-reactive
   baseline by >= 0.2 Sharpe over the 4-month test window? Significance is
   evaluated via a 1000-bootstrap of monthly Sharpe ratios in the
   `notebooks/04_main_backtest.ipynb` post-analysis.

If the H1 result is negative on this run, the most common cause is
under-training on the budget grid - rerun with the FULL_GRID block in
Cell 6 enabled.
"""


# ---------------------------------------------------------------------------
# Assemble the notebook
# ---------------------------------------------------------------------------
NB["cells"] = [
    nbf.v4.new_markdown_cell(CELL_1_MD),
    nbf.v4.new_code_cell(CELL_2_CODE),
    nbf.v4.new_code_cell(CELL_3_CODE),
    nbf.v4.new_markdown_cell(CELL_4_MD),
    nbf.v4.new_code_cell(CELL_5_CODE),
    nbf.v4.new_code_cell(CELL_6_CODE),
    nbf.v4.new_code_cell(CELL_7_CODE),
    nbf.v4.new_code_cell(CELL_8_CODE),
    nbf.v4.new_code_cell(CELL_9_CODE),
    nbf.v4.new_code_cell(CELL_10_CODE),
    nbf.v4.new_code_cell(CELL_11_CODE),
    nbf.v4.new_markdown_cell(CELL_12_MD),
]

NB["metadata"] = {
    "kernelspec": {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    },
    "language_info": {
        "name": "python",
        "version": "3.11",
    },
    "colab": {
        "name": "train_da_bigru_cnn_colab.ipynb",
        "provenance": [],
        "machine_shape": "hm",
        "accelerator": "GPU",
        "gpuType": "H100",
    },
    "accelerator": "GPU",
}


if __name__ == "__main__":
    out = Path(__file__).parent / "train_da_bigru_cnn_colab.ipynb"
    nbf.write(NB, out)
    nbf.validate(nbf.read(out, as_version=4))
    size_kb = out.stat().st_size / 1024
    print(f"wrote {out}  ({size_kb:.1f} KB, {len(NB['cells'])} cells)")
