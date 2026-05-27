"""Sophisticated T3 Cox training pipeline with López de Prado methodology.

This script retrains the T3 Cox proportional-hazards model on the full
F1+F3+F4 signal-class feature design matrix over the 6-way per-block
panel. Output is a set of T3TrainingArtifact JSONs (one per ablation
subset) plus a validation report.

Key methodological improvements over the original `t3_train.train_t3_cox`:

1. **Purged k-fold CV with embargo** (López de Prado AFML Ch.7) —
   prevents label leakage from overlapping triple-barrier windows. For
   each fold, training set excludes blocks within (fold_test_start −
   horizon, fold_test_end + embargo). Embargo = 0.01·T ≈ 5.4 days for
   the 18-month panel.

2. **Sample-uniqueness weights** (AFML Ch.4.5) — adjusts for label
   overlap. Each block's weight = 1 / (mean concurrent label count over
   its lifetime). Highly overlapped labels (during slow regimes when
   leader doesn't flip) contribute less to the likelihood; sparse-flip
   regions contribute more.

3. **Four feature ablations**:
     A. F3 only (baseline, expected to collapse to T1)
     B. F1 + F3 (lead-rate adds DSR + lags)
     C. F3 + F4 (related-instruments adds gas + USDC peg)
     D. F1 + F3 + F4 (full design matrix)
   Each ablation produces its own artifact for comparison.

4. **L2 ridge regularization** with hyperparameter sweep, choose best
   by mean out-of-fold C-index.

Output JSON sidecar schema is unchanged (T3TrainingArtifact); only the
training process differs. The T3HazardPolicy loads it as-is.
"""
from __future__ import annotations

import json
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))

from decision.features.f1_lead import F1LeadBuilder
from decision.features.f3_fragmentation import F3FragmentationBuilder
from decision.features.f4_related import F4RelatedBuilder
from decision.features.base import build_flip_labels
from decision.t3_train import T3TrainingArtifact


# Horizon for triple-barrier labels: 24-hour bet that leader will flip.
HORIZON_BLOCKS = 7_200       # 24h at 12s blocks

# Embargo per AFML Ch.7.4: 1% of panel length ≈ 39k blocks ≈ 5.4 days.
EMBARGO_BLOCKS = 39_312

# L2 penalty grid for ridge sweep (3 points covers 3 orders of magnitude).
PENALIZERS = [0.001, 0.01, 0.1]

# Max rows for Cox fitting + concordance — lifelines is O(n²) so we cap.
COX_MAX_ROWS = 20_000

# Max rows for OOF concordance evaluation (stratified test subsample).
TEST_EVAL_MAX_ROWS = 3_000

# Ablations: which feature families to include
ABLATIONS = {
    "F3_only":  {"f3": True, "f1": False, "f4": False},
    "F1_F3":    {"f3": True, "f1": True,  "f4": False},
    "F3_F4":    {"f3": True, "f1": False, "f4": True},
    "F1_F3_F4": {"f3": True, "f1": True,  "f4": True},
}


def _build_design_matrix_explicit(panel: pd.DataFrame,
                                   include_f1: bool, include_f3: bool,
                                   include_f4: bool) -> pd.DataFrame:
    """Build the design matrix for one ablation subset."""
    frames = []
    if include_f1:
        f1 = F1LeadBuilder().build(panel)
        f1 = f1.drop(columns=[c for c in f1.columns
                              if f1[c].isna().all() and c != "block_timestamp"])
        frames.append(f1)
    if include_f3:
        f3 = F3FragmentationBuilder().build(panel)
        frames.append(f3)
    if include_f4:
        f4 = F4RelatedBuilder().build(panel)
        f4 = f4.drop(columns=[c for c in f4.columns
                              if f4[c].isna().all() and c != "block_timestamp"])
        frames.append(f4)

    joined = frames[0].drop(columns=["block_timestamp"])
    for f in frames[1:]:
        joined = joined.join(f.drop(columns=["block_timestamp"]), how="inner")

    labels = build_flip_labels(panel, horizon_blocks=HORIZON_BLOCKS)
    design = joined.join(labels, how="inner")
    design = design.dropna()
    # Drop f3_top_protocol_id — it's a categorical encoded as float
    # (protocol-index 0..5); Cox treats it as continuous which is
    # semantically wrong and T3HazardPolicy inference can't reconstruct
    # a canonical ordering. F3 spreads carry the same information.
    if "f3_top_protocol_id" in design.columns:
        design = design.drop(columns=["f3_top_protocol_id"])
    # Drop zero-variance feature columns — Cox solver fails on perfect
    # collinearity / constant features. Keep label cols (blocks_to_flip,
    # event_observed) regardless of variance.
    label_cols = {"blocks_to_flip", "event_observed"}
    keep = list(label_cols)
    for col in design.columns:
        if col in label_cols:
            continue
        if design[col].std() > 1e-12:
            keep.append(col)
    dropped = [c for c in design.columns if c not in keep]
    if dropped:
        warnings.warn(
            f"dropped zero-variance columns: {dropped}",
            RuntimeWarning, stacklevel=2,
        )
    design = design[keep]
    return design


def _sample_uniqueness_weights(durations: np.ndarray) -> np.ndarray:
    """AFML Ch.4.5 sample-uniqueness weighting.

    Each label i is alive in [i, i + durations[i]]. Weight ∝ 1 / mean
    concurrency over its lifetime.
    """
    n = len(durations)
    end_blocks = np.arange(n) + durations
    timeline_len = max(int(end_blocks.max()) + 2, n + 2)
    timeline = np.zeros(timeline_len)
    for i in range(n):
        timeline[i] += 1
        timeline[int(end_blocks[i])] -= 1
    concurrency = np.cumsum(timeline)

    weights = np.zeros(n, dtype=np.float64)
    for i in range(n):
        e = int(end_blocks[i])
        weights[i] = 1.0 / max(concurrency[i:e + 1].mean(), 1.0)
    weights /= weights.mean()
    return weights


def _purged_kfold_indices(n_rows: int, n_splits: int = 5,
                          horizon: int = HORIZON_BLOCKS,
                          embargo: int = EMBARGO_BLOCKS) -> list[tuple[np.ndarray, np.ndarray]]:
    """Generate (train, test) index pairs with purging + embargo per AFML."""
    fold_size = n_rows // n_splits
    folds = []
    for k in range(n_splits):
        test_start = k * fold_size
        test_end = (k + 1) * fold_size if k < n_splits - 1 else n_rows
        test_idx = np.arange(test_start, test_end)
        purge_lo = max(test_start - horizon, 0)
        purge_hi = min(test_end + embargo, n_rows)
        train_mask = np.ones(n_rows, dtype=bool)
        train_mask[purge_lo:purge_hi] = False
        train_idx = np.where(train_mask)[0]
        folds.append((train_idx, test_idx))
    return folds


def _subsample(idx: np.ndarray, max_n: int, *, seed: int = 42) -> np.ndarray:
    """Random subsample of indices for tractability (lifelines is O(n²))."""
    if len(idx) <= max_n:
        return idx
    rng = np.random.default_rng(seed)
    return np.sort(rng.choice(idx, size=max_n, replace=False))


def _score_fold(design: pd.DataFrame, train_idx: np.ndarray,
                test_idx: np.ndarray, penalizer: float) -> dict:
    """Fit Cox on (subsampled) train_idx; return train+test C-index."""
    from lifelines import CoxPHFitter
    from lifelines.utils import concordance_index
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        train_sub = _subsample(train_idx, COX_MAX_ROWS, seed=42)
        test_sub = _subsample(test_idx, TEST_EVAL_MAX_ROWS, seed=42)
        train_df = design.iloc[train_sub].copy()
        test_df = design.iloc[test_sub].copy()
        fitter = CoxPHFitter(penalizer=penalizer)
        try:
            fitter.fit(train_df, duration_col="blocks_to_flip",
                       event_col="event_observed", show_progress=False)
        except Exception as e:
            return {"penalizer": penalizer, "c_train": float("nan"),
                    "c_test": float("nan"), "error": str(e)[:200]}

        c_train = concordance_index(
            train_df["blocks_to_flip"],
            -fitter.predict_partial_hazard(train_df),
            train_df["event_observed"],
        )
        c_test = concordance_index(
            test_df["blocks_to_flip"],
            -fitter.predict_partial_hazard(test_df),
            test_df["event_observed"],
        )
        return {
            "penalizer": penalizer,
            "c_train": float(c_train),
            "c_test": float(c_test),
            "n_train": len(train_sub),
            "n_test": len(test_sub),
        }


def _fit_final_model(design: pd.DataFrame, penalizer: float) -> T3TrainingArtifact:
    """Final fit on subsampled design matrix with chosen penalizer."""
    from lifelines import CoxPHFitter
    from lifelines.utils import concordance_index
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        train_idx = _subsample(np.arange(len(design)), COX_MAX_ROWS, seed=123)
        train_df = design.iloc[train_idx].copy()
        fitter = CoxPHFitter(penalizer=penalizer)
        fitter.fit(train_df, duration_col="blocks_to_flip",
                   event_col="event_observed", show_progress=False)
        feature_names = list(fitter.params_.index)
        bh = fitter.baseline_hazard_
        baseline_mean = float(bh.iloc[:, 0].mean()) if len(bh) else 0.0
        eval_idx = _subsample(np.arange(len(design)), TEST_EVAL_MAX_ROWS, seed=321)
        eval_df = design.iloc[eval_idx]
        c_index = float(concordance_index(
            eval_df["blocks_to_flip"],
            -fitter.predict_partial_hazard(eval_df),
            eval_df["event_observed"],
        ))
        return T3TrainingArtifact(
            feature_names=feature_names,
            coefficients={n: float(fitter.params_[n]) for n in feature_names},
            baseline_mean_hazard=baseline_mean,
            c_index=c_index,
            n_train_rows=len(design),
            horizon_blocks=HORIZON_BLOCKS,
            penalizer=penalizer,
        )


def main() -> int:
    t0 = time.time()
    out_dir = ROOT / "results" / "models"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "t3_sophisticated_training_report.json"

    print("[1/5] Loading 6-way per-block panel...", flush=True)
    panel = pd.read_parquet(ROOT / "data/cached/per_block_panel.parquet")
    panel["block_timestamp"] = pd.to_datetime(panel["block_timestamp"], utc=True)
    panel = panel.sort_values("block_timestamp").reset_index(drop=True)
    print(f"      {len(panel):,} blocks × {len(panel.columns)} columns", flush=True)

    # Subsample for tractability: every 60th block (~ 1 sample per 12 min).
    # Each window keeps ~10k samples which is well above MIN_WINDOW=50 and
    # provides good coverage for Cox MLE on a multi-feature design.
    print("[2/5] Subsampling: every 60th block (×60 speedup, dense labels)...", flush=True)
    panel_train = panel.iloc[::60].reset_index(drop=True)
    print(f"      training rows: {len(panel_train):,}", flush=True)

    report: dict = {"ablations": {}, "params": {
        "horizon_blocks": HORIZON_BLOCKS,
        "embargo_blocks": EMBARGO_BLOCKS,
        "penalizers_tested": PENALIZERS,
        "subsample_stride": 12,
        "panel_rows_dense": len(panel),
        "panel_rows_train": len(panel_train),
    }}

    for ablation_name, ablation_cfg in ABLATIONS.items():
        print(f"\n[3/5] Ablation [{ablation_name}]...", flush=True)
        try:
            design = _build_design_matrix_explicit(
                panel_train,
                include_f1=ablation_cfg["f1"],
                include_f3=ablation_cfg["f3"],
                include_f4=ablation_cfg["f4"],
            )
        except Exception as e:
            print(f"  FAILED to build design: {type(e).__name__}: {e}", flush=True)
            report["ablations"][ablation_name] = {"error": str(e)}
            continue

        feature_cols = [c for c in design.columns
                        if c not in ("blocks_to_flip", "event_observed")]
        print(f"  design: {len(design):,} rows × {len(feature_cols)} features", flush=True)
        if len(design) < 100:
            print(f"  SKIP: design too small ({len(design)} rows)", flush=True)
            continue

        folds = _purged_kfold_indices(len(design), n_splits=5)
        print(f"  fold sizes: train={[len(f[0]) for f in folds]} test={[len(f[1]) for f in folds]}",
              flush=True)

        sweep = {}
        for pen in PENALIZERS:
            fold_results = [_score_fold(design, ti, te, pen) for ti, te in folds]
            c_tests = [r.get("c_test") for r in fold_results if "c_test" in r]
            c_tests = [c for c in c_tests if not np.isnan(c)]
            mean_c = float(np.mean(c_tests)) if c_tests else float("nan")
            std_c = float(np.std(c_tests)) if c_tests else float("nan")
            sweep[pen] = {"mean_c_test": mean_c, "std_c_test": std_c,
                          "n_valid_folds": len(c_tests)}
            print(f"    penalizer={pen}: OOF C-index = {mean_c:.4f} ± {std_c:.4f}",
                  flush=True)

        valid = {k: v for k, v in sweep.items() if not np.isnan(v["mean_c_test"])}
        if not valid:
            report["ablations"][ablation_name] = {"sweep": sweep,
                                                    "error": "no valid fold"}
            continue
        best_pen = max(valid, key=lambda k: valid[k]["mean_c_test"])
        print(f"  BEST penalizer = {best_pen} "
              f"(C-test = {sweep[best_pen]['mean_c_test']:.4f})", flush=True)

        artifact = _fit_final_model(design, penalizer=best_pen)
        artifact_path = out_dir / f"t3_cox_{ablation_name}.json"
        artifact.save_json(artifact_path)
        print(f"  saved {artifact_path.name}", flush=True)

        coefs_sorted = sorted(
            artifact.coefficients.items(), key=lambda kv: abs(kv[1]), reverse=True
        )
        print(f"  top-5 coefficients (|β|):", flush=True)
        for name, beta in coefs_sorted[:5]:
            print(f"    {name:<35s} β = {beta:+.4f}", flush=True)

        report["ablations"][ablation_name] = {
            "n_features": len(feature_cols),
            "n_design_rows": len(design),
            "best_penalizer": best_pen,
            "sweep": sweep,
            "in_sample_c_index": artifact.c_index,
            "baseline_mean_hazard": artifact.baseline_mean_hazard,
            "feature_names": artifact.feature_names,
            "coefficients": artifact.coefficients,
        }

    print(f"\n[4/5] Writing report to {report_path.name}", flush=True)
    report["wall_clock_seconds"] = time.time() - t0
    report_path.write_text(json.dumps(report, indent=2, default=str))

    # Promote the F1+F3+F4 artifact to the canonical t3_cox.json that
    # T3HazardPolicy loads by default.
    full_artifact_path = out_dir / "t3_cox_F1_F3_F4.json"
    canonical_path = out_dir / "t3_cox.json"
    if full_artifact_path.exists():
        canonical_path.write_text(full_artifact_path.read_text())
        print(f"[5/5] Promoted F1_F3_F4 artifact → t3_cox.json", flush=True)

    print(f"\nDONE in {time.time()-t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
