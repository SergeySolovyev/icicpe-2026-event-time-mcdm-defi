"""Kaggle GPU kernel: train DA-BiGRU-CNN forecaster on real Aave/Compound USDC rates.

Adapted from the Colab notebook. Differences:
- No google.colab / Drive — bundle is in /kaggle/input/<dataset-slug>/
- Outputs go to /kaggle/working/ (Kaggle persists this as the kernel's output)
- enable_internet=true → pip install fractal-defi from git tag at runtime

Expected wall-clock: ~30-60 min on T4 GPU (Kaggle free tier).
"""
import os
import sys
import time
import json
import zipfile
import subprocess
from pathlib import Path


# -------------------------------------------------------------------------
# 1. Locate input source (Kaggle auto-extracts ZIP datasets — files live
#    directly under /kaggle/input/<dataset-slug>/ as a project tree)
# -------------------------------------------------------------------------
# Kaggle mount path differs for private vs public datasets:
#  public:  /kaggle/input/<slug>/<files>
#  private: /kaggle/input/datasets/<user>/<slug>/<files>
# Resolve dynamically by globbing for the parquet anchor.
_anchors = list(Path("/kaggle/input").rglob("data/cached/joined_clean.parquet"))
if not _anchors:
    raise RuntimeError(
        "joined_clean.parquet not found under /kaggle/input/. "
        f"Contents: {[p.name for p in Path('/kaggle/input').iterdir()]}"
    )
parquet = _anchors[0]
PROJECT_ROOT = parquet.parent.parent.parent  # .../data/cached/parquet -> project root
print(f"[input] resolved PROJECT_ROOT = {PROJECT_ROOT}")
print(f"[input] {PROJECT_ROOT} ({len(list(PROJECT_ROOT.rglob('*.py')))} .py files; "
      f"parquet {parquet.stat().st_size/1e6:.2f} MB)")

sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)  # CWD is read-only but reads are fine; all writes go to /kaggle/working/


# -------------------------------------------------------------------------
# 3. Install pinned fractal-defi + a few extras
# -------------------------------------------------------------------------
subprocess.check_call([
    sys.executable, "-m", "pip", "install", "-q",
    "fractal-defi @ git+https://github.com/Logarithm-Labs/fractal-defi.git@v1.3.2",
    "mlflow", "catboost", "statsmodels", "onnx", "onnxruntime", "pyarrow",
])
print("[install] dependencies OK")


# -------------------------------------------------------------------------
# 4. GPU detection (fail fast)
# -------------------------------------------------------------------------
import torch  # MUST come before numpy/pandas (CLAUDE.md DLL-order note)

if not torch.cuda.is_available():
    raise RuntimeError(
        "GPU not available. In Kaggle: Settings -> Accelerator -> GPU T4 ×2 (or P100). "
        "Verify kernel-metadata.json has enable_gpu=true."
    )
props = torch.cuda.get_device_properties(0)
print(f"[gpu] {props.name}, {props.total_memory/1e9:.1f} GB VRAM, "
      f"CC {props.major}.{props.minor}; torch {torch.__version__}, CUDA {torch.version.cuda}")
torch.set_float32_matmul_precision("high")
torch.backends.cudnn.benchmark = True


# -------------------------------------------------------------------------
# 5. Load data + stub-fill columns the fetchers never wired (gas_gwei, eth_usd)
# -------------------------------------------------------------------------
import numpy as np
import pandas as pd
from data.features import AaveKinkParams, CompoundKinkParams, extract_features

DATA = pd.read_parquet("data/cached/joined_clean.parquet")
if not isinstance(DATA.index, pd.DatetimeIndex):
    raise RuntimeError(f"joined_clean.parquet must have DatetimeIndex, got {type(DATA.index).__name__}")
if DATA.index.tz is None:
    DATA.index = DATA.index.tz_localize("UTC")
print(f"[data] {len(DATA):,} rows  {DATA.index[0]}  ->  {DATA.index[-1]}")

# Stub-fill (matches the local_smoke_train + Colab notebook contract).
# These are constant inputs to Branch B; BiGRU ignores them, but BRANCH_B_COLS
# still requires the columns to exist.
if "gas_gwei" not in DATA.columns:
    print("[data] gas_gwei missing -> filled with 30.0 (stub, constant)")
    DATA["gas_gwei"] = 30.0
if "eth_usd" not in DATA.columns:
    print("[data] eth_usd missing  -> filled with 3500.0 (stub)")
    DATA["eth_usd"] = 3500.0

kp = json.loads(open("data/cached/kink_params.json").read())
KINK_AAVE = AaveKinkParams(**kp["aave"])
KINK_COMP = CompoundKinkParams(**kp["compound"])
print(f"[kink] aave={KINK_AAVE}")
print(f"[kink] compound={KINK_COMP}")

FEATS = extract_features(DATA, KINK_AAVE, KINK_COMP).dropna()
print(f"[features] panel shape: {FEATS.shape}  (includes r_*_annual cols from R²-fix)")


# -------------------------------------------------------------------------
# 6. Chronological train / val / test split (PROJECT_2_PLAN.md S4.1)
# -------------------------------------------------------------------------
TRAIN_END = pd.Timestamp("2025-09-01", tz="UTC")
VAL_END   = pd.Timestamp("2026-01-01", tz="UTC")
TEST_END  = pd.Timestamp("2026-05-01", tz="UTC")

FT_TR = FEATS.loc[FEATS.index <  TRAIN_END]
FT_VA = FEATS.loc[(FEATS.index >= TRAIN_END) & (FEATS.index < VAL_END)]
FT_TE = FEATS.loc[(FEATS.index >= VAL_END)   & (FEATS.index < TEST_END)]
for name, slc in [("train", FT_TR), ("val", FT_VA), ("test", FT_TE)]:
    print(f"[split] {name:>5}: {len(slc):>5} rows   {slc.index[0]} -> {slc.index[-1]}")

if len(FT_TR) == 0 or len(FT_VA) == 0:
    raise RuntimeError("Train or val split is empty")


# -------------------------------------------------------------------------
# 7. Datasets + DataLoaders (post-R²-fix: ds_tr computes stats, val/test reuse)
# -------------------------------------------------------------------------
from torch.utils.data import DataLoader
from forecaster.train import DABiGRUCNNDataset

SEQ_LEN, HORIZON, BATCH = 168, 12, 64

ds_tr = DABiGRUCNNDataset(FT_TR, KINK_AAVE, KINK_COMP,
                          input_window=SEQ_LEN, forecast_horizon=HORIZON)
ds_va = DABiGRUCNNDataset(FT_VA, KINK_AAVE, KINK_COMP,
                          input_window=SEQ_LEN, forecast_horizon=HORIZON,
                          stats=ds_tr.stats)
ds_te = (DABiGRUCNNDataset(FT_TE, KINK_AAVE, KINK_COMP,
                           input_window=SEQ_LEN, forecast_horizon=HORIZON,
                           stats=ds_tr.stats)
         if len(FT_TE) > SEQ_LEN + HORIZON else None)

train_loader = DataLoader(ds_tr, batch_size=BATCH, shuffle=True,  drop_last=True,
                          num_workers=2, pin_memory=True)
val_loader   = DataLoader(ds_va, batch_size=BATCH, shuffle=False,
                          num_workers=2, pin_memory=True)
test_loader  = (DataLoader(ds_te, batch_size=BATCH, shuffle=False,
                           num_workers=2, pin_memory=True) if ds_te is not None else None)

print(f"[loaders] train batches={len(train_loader)} (n={len(ds_tr)})  "
      f"val batches={len(val_loader)} (n={len(ds_va)})  "
      f"test={'-' if ds_te is None else len(ds_te)}")


# -------------------------------------------------------------------------
# 8. Training (15 epochs, AdamW + cosine, early-stop patience=5, seed=42)
# -------------------------------------------------------------------------
from forecaster.model import DABiGRUCNNForecaster, ForecasterConfig
from forecaster.train import TrainConfig, Trainer

CKPT_DIR = Path("/kaggle/working/trained_models")
CKPT_DIR.mkdir(parents=True, exist_ok=True)

# Persist z-score stats so the strategy can reload at backtest time.
with open(CKPT_DIR / "feature_stats.json", "w") as f:
    stats_serializable = {
        k: {"mean": float(v["mean"]), "std": float(v["std"])}
        for k, v in ds_tr.stats.items()
    }
    json.dump(stats_serializable, f, indent=2)
print(f"[stats] saved feature_stats.json ({len(stats_serializable)} columns)")

model_cfg = ForecasterConfig(
    branch_a_hidden=64, branch_b_hidden=64, head_hidden=64,
    branch_a_layers=2, branch_b_layers=2,
    branch_b_cnn_kernels=(3, 5, 7), dropout=0.1,
    sequence_length=SEQ_LEN, forecast_horizon=HORIZON,
)
train_cfg = TrainConfig(
    input_window=SEQ_LEN, forecast_horizon=HORIZON, batch_size=BATCH,
    lr=2e-3, weight_decay=0.01, grad_clip=1.0,
    max_epochs=15, patience=5, num_workers=2, device="cuda",
    alpha=0.4, beta=0.5, gamma=0.1, quantile_q=0.9,
    n_splits=1, seed=42,
    checkpoint_path=str(CKPT_DIR / "da_bigru_cnn.pt"),
)

model = DABiGRUCNNForecaster(model_cfg)
print(f"[model] n_params = {model.n_params():,}")

trainer = Trainer(model, train_cfg, KINK_AAVE, KINK_COMP, mlflow_experiment=None)

t0 = time.time()
try:
    fit_out = trainer.fit(train_loader, val_loader)
except RuntimeError as exc:
    if "CUDA out of memory" in str(exc):
        raise RuntimeError("OOM — reduce BATCH from 64 to 32 in this script and re-push") from exc
    raise
elapsed = time.time() - t0
print(f"\n[train] done in {elapsed/60:.1f} min   best_val_loss={fit_out['best_val_loss']:.4f}")


# -------------------------------------------------------------------------
# 9. Metrics on val + test
# -------------------------------------------------------------------------
from forecaster.train import reconstruct_rate

trainer.model.train(False)

def _collect(loader):
    preds_, trues_ = [], []
    with torch.no_grad():
        for x_a, x_b, y in loader:
            x_a, x_b = x_a.to("cuda", non_blocking=True), x_b.to("cuda", non_blocking=True)
            out = trainer.model(x_a, x_b)
            r_hat = reconstruct_rate(out, KINK_AAVE, KINK_COMP)
            preds_.append(r_hat.cpu().numpy())
            trues_.append(y.numpy())
    return np.concatenate(preds_), np.concatenate(trues_)


def weighted_pearson(y, yhat):
    w = np.abs(y) + 1e-12
    my, mp = np.average(y, weights=w), np.average(yhat, weights=w)
    cov = np.average((y - my) * (yhat - mp), weights=w)
    vy = np.average((y - my) ** 2, weights=w)
    vp = np.average((yhat - mp) ** 2, weights=w)
    return float(cov / (np.sqrt(vy * vp) + 1e-12))


def r2_score(y, yhat):
    ss_res = float(((y - yhat) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum()) + 1e-12
    return 1.0 - ss_res / ss_tot


val_preds, val_trues = _collect(val_loader)
metrics = {
    "val/wpearson_aave":            weighted_pearson(val_trues[:, 0], val_preds[:, 0]),
    "val/wpearson_compound":        weighted_pearson(val_trues[:, 1], val_preds[:, 1]),
    "val/r2_aave":                  r2_score(val_trues[:, 0], val_preds[:, 0]),
    "val/r2_compound":              r2_score(val_trues[:, 1], val_preds[:, 1]),
    "val/dir_acc_aave_gt_compound": float(((val_preds[:, 0] > val_preds[:, 1]) ==
                                           (val_trues[:, 0] > val_trues[:, 1])).mean()),
    "val/n_samples":                int(val_preds.shape[0]),
    "train/best_val_loss":          float(fit_out["best_val_loss"]),
    "train/elapsed_min":            float(elapsed / 60),
}
if test_loader is not None:
    test_preds, test_trues = _collect(test_loader)
    metrics.update({
        "test/wpearson_aave":            weighted_pearson(test_trues[:, 0], test_preds[:, 0]),
        "test/wpearson_compound":        weighted_pearson(test_trues[:, 1], test_preds[:, 1]),
        "test/r2_aave":                  r2_score(test_trues[:, 0], test_preds[:, 0]),
        "test/r2_compound":              r2_score(test_trues[:, 1], test_preds[:, 1]),
        "test/dir_acc_aave_gt_compound": float(((test_preds[:, 0] > test_preds[:, 1]) ==
                                                (test_trues[:, 0] > test_trues[:, 1])).mean()),
        "test/n_samples":                int(test_preds.shape[0]),
    })

print("\n=== METRICS ===")
for k, v in metrics.items():
    print(f"  {k:38s} = {v}")


# -------------------------------------------------------------------------
# 10. Export to ONNX + parity check
# -------------------------------------------------------------------------
from forecaster.export_onnx import ExportConfig, export

ONNX_PATH = CKPT_DIR / "dual_branch_kink.onnx"
exp_cfg = ExportConfig(
    ckpt_path=CKPT_DIR / "da_bigru_cnn.pt",
    onnx_path=ONNX_PATH,
    opset=17, atol=1e-4, rtol=1e-4,
)
export(exp_cfg)
print(f"[onnx] {ONNX_PATH}  {ONNX_PATH.stat().st_size/1024:.1f} KB")
metrics["onnx_path"] = str(ONNX_PATH)
metrics["onnx_size_kb"] = ONNX_PATH.stat().st_size / 1024


# -------------------------------------------------------------------------
# 11. Persist metrics + bundle outputs for download
# -------------------------------------------------------------------------
(CKPT_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str))

# Bundle into one zip for one-shot retrieval via the Kaggle kernel output page.
TRAINED_ZIP = Path("/kaggle/working/predictive-mcdm-defi-trained.zip")
with zipfile.ZipFile(TRAINED_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
    for p in sorted(CKPT_DIR.iterdir()):
        if p.is_file():
            zf.write(p, arcname=p.name)
print(f"\n[done] {TRAINED_ZIP}  ({TRAINED_ZIP.stat().st_size/1024:.1f} KB)")
print(f"[done] artifacts in {CKPT_DIR}: "
      f"{sorted(p.name for p in CKPT_DIR.iterdir() if p.is_file())}")
print("\nKaggle will save /kaggle/working/* as outputs. Download from the kernel page "
      "(https://www.kaggle.com/code/<user>/predictive-mcdm-defi-train/output) or "
      "via `kaggle kernels output sergeisolovyev/predictive-mcdm-defi-train`.")
