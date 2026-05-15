"""Local CPU smoke-train: produce a DUMMY trained ONNX in ~3 minutes so the
full backtest + whitepaper pipeline can be validated end-to-end BEFORE the
real Colab GPU run.

The dummy model's numerical metrics are near-noise (only 1-2 epochs on a
smaller-than-production architecture); the purpose is to validate the PATH
through:

    real joined panel -> extract_features -> Dataset -> Trainer.fit
    -> .pt checkpoint -> forecaster.export_onnx -> ONNX parity check

If anything is broken, we discover it locally in 3-5 min instead of after
a 45-minute Colab run.

CLI::

    python -m scripts.local_smoke_train                     # 2 epochs (default)
    python -m scripts.local_smoke_train --epochs 1          # fastest path
    python -m scripts.local_smoke_train --seq-len 96 --force
    python -m scripts.local_smoke_train --no-onnx           # debug: skip export

Exit codes:
    0  full success
    1  ONNX numerical parity check failed
    2  no real data found at data/cached/joined_clean.parquet
    3  Dataset has 0 windows (data too short or filtered out)
"""
# === DEFENSIVE IMPORT ORDER (CLAUDE.md hard-constraint #6) ===
# torch MUST be imported before numpy / pandas / anything that may pull in
# MKL on Windows -- otherwise c10.dll load order is poisoned (OSError 1114).
import torch
torch.set_num_threads(4)
import torch.nn as nn
from torch.utils.data import DataLoader

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

# Project imports (after torch)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.features import (  # noqa: E402
    AaveKinkParams,
    CompoundKinkParams,
    extract_features,
)
from forecaster.model import DABiGRUCNNForecaster, ForecasterConfig  # noqa: E402
from forecaster.train import (  # noqa: E402
    DABiGRUCNNDataset,
    TrainConfig,
    Trainer,
    reconstruct_rate,
)
from forecaster.losses import weighted_pearson  # noqa: E402


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

JOINED_PARQUET = ROOT / "data" / "cached" / "joined_clean.parquet"
KINK_JSON      = ROOT / "data" / "cached" / "kink_params.json"
CKPT_PATH      = ROOT / "forecaster" / "trained_models" / "da_bigru_cnn.pt"
ONNX_PATH      = ROOT / "forecaster" / "trained_models" / "dual_branch_kink.onnx"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _banner(msg: str) -> None:
    bar = "=" * max(len(msg) + 4, 60)
    print(bar)
    print(f"  {msg}")
    print(bar)


def _load_real_panel() -> pd.DataFrame:
    """Load joined panel, filter to rows valid in both protocols, ensure
    auxiliary columns gas_gwei / eth_usd exist (synthetic constants if not).
    """
    if not JOINED_PARQUET.exists():
        print(f"[FATAL] no real data at {JOINED_PARQUET}")
        print("        Run `make data` (or fetch_aave + fetch_compound + clean) first.")
        sys.exit(2)

    df = pd.read_parquet(JOINED_PARQUET)

    # DEFENSIVE CHECK #1 -- both protocols must have valid rows.
    if "valid_aave" in df.columns and "valid_compound" in df.columns:
        mask = df["valid_aave"] & df["valid_compound"]
        print(f"[data] {mask.sum()}/{len(df)} rows valid in both protocols")
        df = df[mask].copy()
    else:
        print("[data] no validity columns found -- using all rows")

    # Stub auxiliary columns the feature pipeline needs but isn't always in cache.
    if "gas_gwei" not in df.columns:
        df["gas_gwei"] = 30.0
        print("[data] gas_gwei missing -> filled with 30.0 (stub)")
    if "eth_usd" not in df.columns:
        df["eth_usd"] = 3500.0
        print("[data] eth_usd missing -> filled with 3500.0 (stub)")

    return df


def _load_kink_params() -> tuple[AaveKinkParams, CompoundKinkParams]:
    if not KINK_JSON.exists():
        print(f"[FATAL] no kink params at {KINK_JSON}")
        sys.exit(2)
    with open(KINK_JSON) as f:
        kp = json.load(f)
    pa = AaveKinkParams(**kp["aave"])
    pc = CompoundKinkParams(**kp["compound"])
    print(f"[data] kink params: aave={pa}, compound={pc}")
    return pa, pc


def _validation_metrics(
    model: DABiGRUCNNForecaster,
    ds_val,
    params_a: AaveKinkParams,
    params_c: CompoundKinkParams,
) -> dict:
    """Compute weighted_pearson per protocol + direction accuracy on val set."""
    model.train(False)
    preds = []
    trues = []
    loader = DataLoader(ds_val, batch_size=64, shuffle=False, drop_last=False)
    with torch.no_grad():
        for x_a, x_b, y in loader:
            out = model(x_a, x_b)
            r_pred = reconstruct_rate(out, params_a, params_c)
            preds.append(r_pred.cpu())
            trues.append(y.cpu())
    p = torch.cat(preds, dim=0)
    t = torch.cat(trues, dim=0)

    wp_aave  = float(weighted_pearson(p[:, 0], t[:, 0]).item())
    wp_comp  = float(weighted_pearson(p[:, 1], t[:, 1]).item())

    pred_sign = (p[:, 0] > p[:, 1])
    true_sign = (t[:, 0] > t[:, 1])
    dir_acc = float((pred_sign == true_sign).float().mean().item())

    return {
        "n_val_windows": int(t.shape[0]),
        "wp_aave":  wp_aave,
        "wp_compound": wp_comp,
        "direction_accuracy_aave_gt_comp_at_t12h": dir_acc,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--seq-len", type=int, default=168,
                    help="sequence length; defaults to the production 168 so the "
                         "dummy ONNX matches the strategy/export_onnx contract "
                         "(use a smaller value only for a non-representative fast run)")
    ap.add_argument("--max-rows", type=int, default=1500,
                    help="truncate the panel to the first N rows before the "
                         "train/val split. The smoke produces a throwaway-weight "
                         "model whose ONLY job is to validate the pipeline + ONNX "
                         "contract (seq_len comes from the model config, not the "
                         "row count), so a small slice keeps CPU wall-time low "
                         "while still exercising the production seq_len=168. "
                         "Set 0 to use the full panel.")
    ap.add_argument("--force", action="store_true",
                    help="overwrite existing checkpoint/onnx without asking")
    ap.add_argument("--no-onnx", action="store_true",
                    help="skip ONNX export (debug)")
    args = ap.parse_args()

    t0 = time.time()

    _banner("LOCAL CPU SMOKE TRAIN -- DUMMY MODEL FOR PIPELINE VALIDATION")
    print(
        "DUMMY MODEL: numerical metrics will be near-random; "
        "this validates the PATH only.\n"
    )
    print(f"torch {torch.__version__} | threads {torch.get_num_threads()} | "
          f"epochs {args.epochs} | seq_len {args.seq_len}")

    # --- Existing-artifact guard (DEFENSIVE CHECK #2) -------------------
    if CKPT_PATH.exists() and not args.force:
        print(f"\n[warn] checkpoint exists at {CKPT_PATH}")
        print("       use --force to overwrite, OR delete it first.")
        print("       proceeding anyway (smoke-test mode).\n")

    # --- 1. Load data ----------------------------------------------------
    _banner("1. Load real joined panel")
    df_raw = _load_real_panel()
    params_a, params_c = _load_kink_params()

    # --- 2. Feature extraction ------------------------------------------
    _banner("2. extract_features")
    df_feat = extract_features(df_raw, params_a, params_c)
    print(f"[feat] shape {df_feat.shape}")

    if args.max_rows and len(df_feat) > args.max_rows:
        # 80/20 split -> the 20% val side is the binding constraint and needs
        # >= seq_len + horizon(12) + 1 rows, so total >= 5 * (seq_len + 13).
        min_needed = 5 * (args.seq_len + 12 + 1)  # 12 = forecast_horizon below
        if args.max_rows < min_needed:
            print(f"[FATAL] --max-rows {args.max_rows} too small for "
                  f"seq_len {args.seq_len}: need >= {min_needed} so the 20% "
                  f"val slice still yields >= {args.seq_len + 13} rows.")
            return 3
        df_feat = df_feat.iloc[: args.max_rows]
        print(f"[feat] truncated to first {args.max_rows} rows for smoke speed "
              f"(seq_len {args.seq_len} contract preserved): {df_feat.shape}")

    # --- 3. Build Dataset / chronological 80-20 split -------------------
    _banner("3. Build Dataset (80/20 chronological split)")
    n = len(df_feat)
    cut = int(0.8 * n)
    horizon = 12

    try:
        ds_tr = DABiGRUCNNDataset(
            df_feat.iloc[:cut], params_a, params_c,
            input_window=args.seq_len, forecast_horizon=horizon,
        )
        ds_va = DABiGRUCNNDataset(
            df_feat.iloc[cut:], params_a, params_c,
            input_window=args.seq_len, forecast_horizon=horizon,
        )
    except ValueError as exc:
        print(f"[FATAL] Dataset construction failed: {exc}")
        return 3

    if len(ds_tr) == 0 or len(ds_va) == 0:
        print(f"[FATAL] empty dataset -- tr={len(ds_tr)}, va={len(ds_va)}")
        return 3

    print(f"[ds] train windows: {len(ds_tr)}  val windows: {len(ds_va)}")

    # --- 4. Smaller model config (~50k params target) -------------------
    _banner("4. Build small model")
    model_cfg = ForecasterConfig(
        sequence_length=args.seq_len,
        branch_a_hidden=32,
        branch_b_hidden=32,
        forecast_horizon=horizon,
        dropout=0.1,
    )
    model = DABiGRUCNNForecaster(model_cfg)
    n_params = model.n_params()
    print(f"[model] {n_params:,} params (production ~320k, this ~50k)")
    # DEFENSIVE CHECK #3 -- guard against accidental full-size config slipping in.
    if n_params > 120_000:
        print(f"[warn] param count {n_params:,} is bigger than the ~50k target; "
              f"CPU training may take >5 min.")

    # --- 5. Train -------------------------------------------------------
    _banner(f"5. Train {args.epochs} epoch(s) (batch=64, lr=2e-3)")
    train_cfg = TrainConfig(
        input_window=args.seq_len,
        forecast_horizon=horizon,
        batch_size=64,
        lr=2e-3,
        max_epochs=args.epochs,
        patience=max(args.epochs, 1),  # don't early-stop a 1-epoch run
        n_splits=1,
        checkpoint_path=str(CKPT_PATH),
    )
    tr_loader = DataLoader(
        ds_tr, batch_size=train_cfg.batch_size, shuffle=True, drop_last=True,
    )
    va_loader = DataLoader(
        ds_va, batch_size=train_cfg.batch_size, shuffle=False,
    )

    trainer = Trainer(model, train_cfg, params_a, params_c,
                      mlflow_experiment=None)  # MLflow off for smoke-test
    fit_out = trainer.fit(tr_loader, va_loader)
    print(f"[train] best val loss: {fit_out['best_val_loss']:.4f}")
    print(f"[train] checkpoint saved -> {CKPT_PATH}")

    # --- 6. Validation metrics ------------------------------------------
    _banner("6. Validation metrics (dummy-model, near-random expected)")
    metrics = _validation_metrics(model, ds_va, params_a, params_c)
    print(json.dumps(metrics, indent=2))

    # --- 7. Export ONNX --------------------------------------------------
    onnx_max_diff = None
    if args.no_onnx:
        _banner("7. ONNX export SKIPPED (--no-onnx)")
    else:
        _banner("7. Export to ONNX + numerical parity check")
        from forecaster.export_onnx import ExportConfig, export
        try:
            cfg = ExportConfig(
                ckpt_path=CKPT_PATH,
                onnx_path=ONNX_PATH,
                opset=17,
                atol=1e-4,
                rtol=1e-4,
            )
            export(cfg)
            # Independent-seed parity check so we have an explicit max-abs-diff
            # number for the report.
            import onnxruntime as ort
            seq = model_cfg.sequence_length
            rng = np.random.default_rng(7)
            x_a = rng.standard_normal((1, seq, model_cfg.branch_a_input_dim)).astype(np.float32)
            x_b = rng.standard_normal((1, seq, model_cfg.branch_b_input_dim)).astype(np.float32)
            model.train(False)
            with torch.no_grad():
                y_t = model(torch.from_numpy(x_a), torch.from_numpy(x_b)).cpu().numpy()
            sess = ort.InferenceSession(str(ONNX_PATH), providers=["CPUExecutionProvider"])
            y_o = sess.run(None, {"x_branch_a": x_a, "x_branch_b": x_b})[0]
            onnx_max_diff = float(np.max(np.abs(y_t - y_o)))
            print(f"[onnx] max|torch-onnx| (independent seed) = {onnx_max_diff:.3e}")
        except AssertionError as exc:
            print(f"[FATAL] ONNX parity check failed: {exc}")
            return 1
        except Exception as exc:                          # noqa: BLE001
            print(f"[FATAL] ONNX export failed: {exc}")
            import traceback; traceback.print_exc()
            return 1

    # --- 8. Report -------------------------------------------------------
    dt = time.time() - t0
    _banner("DONE")
    print(f"Wall-clock: {dt:.1f} s")
    print(f"Param count: {n_params:,}")
    print(f"Val weighted-Pearson  aave    : {metrics['wp_aave']:+.4f}")
    print(f"Val weighted-Pearson  compound: {metrics['wp_compound']:+.4f}")
    print(f"Val direction acc (aave>comp @ t+12h): "
          f"{metrics['direction_accuracy_aave_gt_comp_at_t12h']:.3f}")
    if onnx_max_diff is not None:
        print(f"ONNX parity max|diff|: {onnx_max_diff:.3e}")

    print()
    print(f"Dummy ONNX written to forecaster/trained_models/dual_branch_kink.onnx")
    print(f"Run: python -m backtest.run_main          # now uses this ONNX")
    print(f"Run: python -m backtest.run_ablations     # 15 ablations")
    print(f"Then: python -m scripts.fill_whitepaper_results")
    print(f"Then: cd whitepaper && pdflatex main && biber main && "
          f"pdflatex main && pdflatex main")
    return 0


if __name__ == "__main__":
    sys.exit(main())
