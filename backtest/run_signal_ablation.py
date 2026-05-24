"""Leave-One-Out (LOO) ablation over the F1/F3/F4 signal families.

Re-fits the T3 Cox hazard model 7 times -- once with all 3 families,
once with each one dropped, once with each one alone -- and emits a
tidy CSV with the C-index per variant. Plan D's D2 task takes this
CSV as input for the paper-grade out-of-sample comparison + bootstrap
CI on net APY.

Pre-registered hypothesis (design spec §III.D, MacKenzie Table 3.2
F3 mapping): F3 (cross-protocol spread) is the dominant predictor of
flip timing. We expect T3_no_F3 to be the worst drop-variant.

CLI:
    python -m backtest.run_signal_ablation
        [--panel data/cached/per_block_panel.parquet]
        [--horizon-blocks 7200]
        [--out results/tables/signal_ablation.csv]
"""
from __future__ import annotations

import argparse
import warnings
from pathlib import Path
from typing import Mapping

import pandas as pd

from decision.t3_train import train_t3_cox


# Seven variants per the plan: full, 3 drops, 3 only-singletons.
ABLATION_VARIANTS: tuple[str, ...] = (
    "T3_full",
    "T3_no_F1",
    "T3_no_F3",
    "T3_no_F4",
    "T3_F1_only",
    "T3_F3_only",
    "T3_F4_only",
)


def _select_families(
    feature_frames: Mapping[str, pd.DataFrame], variant: str
) -> dict[str, pd.DataFrame]:
    """Map a variant name to the subset of feature_frames to fit on."""
    if variant == "T3_full":
        return {f: feature_frames[f] for f in ("f1", "f3", "f4") if f in feature_frames}
    if variant == "T3_no_F1":
        return {f: feature_frames[f] for f in ("f3", "f4") if f in feature_frames}
    if variant == "T3_no_F3":
        return {f: feature_frames[f] for f in ("f1", "f4") if f in feature_frames}
    if variant == "T3_no_F4":
        return {f: feature_frames[f] for f in ("f1", "f3") if f in feature_frames}
    if variant == "T3_F1_only":
        return {"f1": feature_frames["f1"]} if "f1" in feature_frames else {}
    if variant == "T3_F3_only":
        return {"f3": feature_frames["f3"]} if "f3" in feature_frames else {}
    if variant == "T3_F4_only":
        return {"f4": feature_frames["f4"]} if "f4" in feature_frames else {}
    raise ValueError(f"unknown variant {variant!r}")


def run_signal_ablation(
    *,
    feature_frames: Mapping[str, pd.DataFrame],
    panel: pd.DataFrame,
    horizon_blocks: int,
    out_path: Path | None = None,
    penalizer: float = 0.001,
) -> pd.DataFrame:
    """Run the 7-variant LOO ablation and return the result DataFrame.

    Each row:
        variant        str       canonical name from ABLATION_VARIANTS
        c_index        float64   in-sample concordance index (NaN on fit failure)
        n_train_rows   Int64     dropped-NaN row count fed into the Cox fit
        n_features     int       number of features in this variant's X matrix
        fit_status     str       "OK" or short failure reason
    """
    rows = []
    for variant in ABLATION_VARIANTS:
        subset = _select_families(feature_frames, variant)
        if not subset:
            rows.append(
                {
                    "variant": variant,
                    "c_index": float("nan"),
                    "n_train_rows": pd.NA,
                    "n_features": 0,
                    "fit_status": "no_features",
                }
            )
            continue

        try:
            with warnings.catch_warnings():
                # ConvergenceWarning is benign on small synthetic panels
                # (Plan D will use the real 3.9M-block panel).
                warnings.simplefilter("ignore")
                artifact = train_t3_cox(
                    feature_frames=subset,
                    panel=panel,
                    horizon_blocks=horizon_blocks,
                    penalizer=penalizer,
                )
            rows.append(
                {
                    "variant": variant,
                    "c_index": artifact.c_index,
                    "n_train_rows": artifact.n_train_rows,
                    "n_features": len(artifact.feature_names),
                    "fit_status": "OK",
                }
            )
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {
                    "variant": variant,
                    "c_index": float("nan"),
                    "n_train_rows": pd.NA,
                    "n_features": sum(
                        len(
                            [c for c in subset[fam].columns if c != "block_timestamp"]
                        )
                        for fam in subset
                    ),
                    "fit_status": f"fit_error: {type(exc).__name__}: {str(exc)[:80]}",
                }
            )

    df = pd.DataFrame(rows)
    if out_path is not None:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_path, index=False)
    return df


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--panel",
        default="data/cached/per_block_panel.parquet",
        help="Path to per-block panel parquet (Plan A output).",
    )
    ap.add_argument("--horizon-blocks", type=int, default=7200,
                    help="Censoring horizon in blocks (default 7200 ~ 24h).")
    ap.add_argument(
        "--out",
        default="results/tables/signal_ablation.csv",
        help="Output CSV path.",
    )
    args = ap.parse_args(argv)

    panel = pd.read_parquet(args.panel)

    # Build the 3 feature frames inline (saves a second pass over the panel).
    from decision.features.f1_lead import F1LeadBuilder
    from decision.features.f3_fragmentation import F3FragmentationBuilder
    from decision.features.f4_related import F4RelatedBuilder

    feats = {
        "f1": F1LeadBuilder().build(panel),
        "f3": F3FragmentationBuilder().build(panel),
        "f4": F4RelatedBuilder().build(panel),
    }

    df = run_signal_ablation(
        feature_frames=feats,
        panel=panel,
        horizon_blocks=args.horizon_blocks,
        out_path=Path(args.out),
    )

    # Pretty-print to stdout.
    print(df.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
