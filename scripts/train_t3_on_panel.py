"""Train T3 Cox proportional-hazards on the 3-way per-block panel.

F1 (DSR lead) is omitted -- DSR fetcher failed on Kaggle and we don't
have a DSR panel. F3 (fragmentation) and F4 (related) are built from
the existing panel. Cross-protocol lead signals (Euler-lead-Aave etc.)
are not yet a separate builder; the F3 spreads already encode that
information directly as the decision variable.

Splits (consistent with run_test_matrix defaults):
    train      : 2024-11-01 -> 2025-08-31  (~8 months)
    validation : 2025-09-01 -> 2025-12-31  (~4 months, T3 hyperparam tuning)
    test       : 2026-01-01 -> 2026-05-01  (held out for run_test_matrix)

Writes: results/models/t3_cox.json (consumed by T3HazardPolicy.from_json).
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PANEL = ROOT / "data" / "cached" / "per_block_panel.parquet"
OUT = ROOT / "results" / "models" / "t3_cox.json"

TRAIN_START = pd.Timestamp("2024-11-01", tz="UTC")
TRAIN_END = pd.Timestamp("2025-09-01", tz="UTC")
VAL_END = pd.Timestamp("2026-01-01", tz="UTC")

HORIZON_BLOCKS = 7200  # ~24h at 12s/block


def main() -> int:
    if not PANEL.exists():
        print(f"PANEL missing: {PANEL}", file=sys.stderr)
        return 1

    print(f"loading {PANEL}")
    panel = pd.read_parquet(PANEL)
    panel["block_timestamp"] = pd.to_datetime(panel["block_timestamp"], utc=True)
    print(f"  panel shape: {panel.shape}  "
          f"blocks {panel.block_number.min():,} -> {panel.block_number.max():,}")
    print(f"  span: {panel.block_timestamp.min()} -> {panel.block_timestamp.max()}")

    train = panel[
        (panel.block_timestamp >= TRAIN_START)
        & (panel.block_timestamp < TRAIN_END)
    ].reset_index(drop=True)
    val = panel[
        (panel.block_timestamp >= TRAIN_END)
        & (panel.block_timestamp < VAL_END)
    ].reset_index(drop=True)
    print(f"  train slice: {len(train):,} rows  "
          f"{train.block_timestamp.min()} -> {train.block_timestamp.max()}")
    print(f"  val   slice: {len(val):,} rows  "
          f"{val.block_timestamp.min()} -> {val.block_timestamp.max()}")

    # Build F3 + F4 features on the training slice.
    from decision.features.f3_fragmentation import F3FragmentationBuilder
    from decision.features.f4_related import F4RelatedBuilder
    from decision.t3_train import train_t3_cox

    f3_train = F3FragmentationBuilder().build(train)
    print(f"  F3 shape: {f3_train.shape}  cols: {[c for c in f3_train.columns if c != 'block_timestamp']}")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        f4_train = F4RelatedBuilder().build(train)
    print(f"  F4 shape: {f4_train.shape}")

    # Subsample to keep Cox fit tractable: ~50,000 rows is plenty for
    # the coefficients to converge tightly.
    if len(train) > 50_000:
        step = max(1, len(train) // 50_000)
        train_sub = train.iloc[::step].reset_index(drop=True)
        f3_sub = f3_train.iloc[::step].copy()
        f4_sub = f4_train.iloc[::step].copy()
        # Re-align indices with the panel subsample.
        f3_sub.index = train_sub.block_number.to_numpy()
        f4_sub.index = train_sub.block_number.to_numpy()
        f3_sub.index.name = "block_number"
        f4_sub.index.name = "block_number"
        print(f"  subsampling 1/{step} -> {len(train_sub):,} rows")
    else:
        train_sub = train.reset_index(drop=True)
        f3_sub = f3_train.copy()
        f4_sub = f4_train.copy()

    print(f"  fitting Cox MLE (horizon={HORIZON_BLOCKS} blocks ~24h)")
    # F4 columns are all-NaN on this panel (no gas/eth_usd/peg fetcher
    # in scope). Drop F4 from the design; F3 dominance is the expected
    # outcome per the design-spec literature foundation anyway.
    artifact = train_t3_cox(
        feature_frames={"f3": f3_sub},
        panel=train_sub,
        horizon_blocks=HORIZON_BLOCKS,
        penalizer=0.001,
    )

    print(f"  Cox converged.")
    print(f"  C-index             : {artifact.c_index:.4f}")
    print(f"  baseline_mean_hazard: {artifact.baseline_mean_hazard:.6e}")
    print(f"  n_train_rows        : {artifact.n_train_rows:,}")
    print(f"  features            : {len(artifact.feature_names)}")
    for f, b in sorted(artifact.coefficients.items(), key=lambda x: -abs(x[1]))[:10]:
        print(f"    {f:<32s}  beta = {b:+.4f}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    artifact.save_json(OUT)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
