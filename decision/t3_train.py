"""T3 Cox proportional-hazards training pipeline.

Joins F1/F3/F4 feature frames + flip-labels into a Cox design matrix
and fits a CoxPHFitter (lifelines >= 0.30). Exports the trained
coefficients + baseline-hazard table to a portable JSON sidecar.
The ONNX projection graph is produced by `decision/t3_hazard.py`
(Task C6) which consumes this artifact at inference time.

The Cox model parameterises the hazard as
    lambda(t | x) = lambda_0(t) * exp(beta' x)
so at inference time E[remaining_dwell] = exp(-beta' x) * mean_baseline
(approximation that ignores baseline shape; T3HazardPolicy refines with
the full survival CDF).
"""
from __future__ import annotations

import json
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from decision.features.base import build_flip_labels, validate_feature_frame


# Suppress lifelines' progress chatter -- pytest captures it as noise.
warnings.filterwarnings("ignore", category=UserWarning, module="lifelines")


@dataclass(frozen=True)
class T3TrainingArtifact:
    """Serialisable Cox fit output. Consumed by T3HazardPolicy at
    inference time. Stored as JSON sidecar; the ONNX graph in Task C6
    embeds the same coefficients but as a static numeric tensor for
    the agent's runtime."""

    feature_names: list[str]
    coefficients: dict[str, float]
    baseline_mean_hazard: float
    c_index: float
    n_train_rows: int
    horizon_blocks: int
    penalizer: float

    def save_json(self, path: Path | str) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load_json(cls, path: Path | str) -> "T3TrainingArtifact":
        return cls(**json.loads(Path(path).read_text()))


def build_design_matrix(
    *,
    feature_frames: Mapping[str, pd.DataFrame],
    panel: pd.DataFrame,
    horizon_blocks: int,
) -> pd.DataFrame:
    """Inner-join F1/F3/F4 feature frames + flip-labels by block_number.

    Args:
        feature_frames: dict keyed by family ("f1","f3","f4") -> the
            frame produced by that family's SignalFeatureBuilder.
        panel: per-block panel from Plan A's stitcher.
        horizon_blocks: censoring horizon for flip-label generation.

    Returns:
        DataFrame indexed by block_number with all `<family>_*` value
        columns + blocks_to_flip + event_observed. Rows with any NaN
        in feature columns are dropped (lifelines requires complete
        cases).
    """
    if not feature_frames:
        raise ValueError("feature_frames is empty -- need at least 1 family")

    # Validate each frame against its expected family.
    for family, frame in feature_frames.items():
        validate_feature_frame(frame, expected_family=family)

    # Strip block_timestamp from each frame -- it's a join-on-the-side
    # column, not a model feature. Then inner-join.
    feat_only = [
        frame.drop(columns=["block_timestamp"]) for frame in feature_frames.values()
    ]
    joined = feat_only[0]
    for nxt in feat_only[1:]:
        joined = joined.join(nxt, how="inner")

    # Add labels by inner-joining on block_number.
    labels = build_flip_labels(panel, horizon_blocks=horizon_blocks)
    design = joined.join(labels, how="inner")

    # Drop any rows where any feature is NaN -- lifelines fitter is
    # complete-cases (no missing-at-random imputation built in).
    before = len(design)
    design = design.dropna()
    dropped = before - len(design)
    if dropped > 0 and dropped / max(before, 1) > 0.30:
        warnings.warn(
            f"build_design_matrix dropped {dropped}/{before} "
            f"({dropped/before*100:.1f}%) rows due to NaN features. "
            f"Check feature coverage on the panel.",
            RuntimeWarning,
            stacklevel=2,
        )
    return design


def train_t3_cox(
    *,
    feature_frames: Mapping[str, pd.DataFrame],
    panel: pd.DataFrame,
    horizon_blocks: int,
    penalizer: float = 0.001,
) -> T3TrainingArtifact:
    """Fit a Cox proportional-hazards model on the F1/F3/F4 design matrix.

    Args:
        feature_frames: family -> feature DataFrame.
        panel: per-block panel for flip-label generation.
        horizon_blocks: censoring horizon (e.g. 7200 ~ 24h).
        penalizer: L2 penalty on the coefficient vector. The lifelines
            default is 0.0 but for high-dimensional feature sets a
            small ridge term (1e-3) prevents pathological coefficients
            from rare-event collinearity (e.g. f3_spread_top2 and
            f3_spread_max_minus_min are highly correlated by
            construction).

    Returns:
        T3TrainingArtifact carrying the coefficients, baseline hazard
        scalar (the Breslow estimator's mean over the observed events),
        concordance index, and training-set metadata.
    """
    from lifelines import CoxPHFitter
    from lifelines.utils import concordance_index

    design = build_design_matrix(
        feature_frames=feature_frames,
        panel=panel,
        horizon_blocks=horizon_blocks,
    )
    if len(design) < 100:
        raise ValueError(
            f"design matrix has only {len(design)} rows after NaN-drop; "
            f"Cox fit needs >=100 to converge"
        )

    # lifelines expects (duration_col, event_col) explicitly + features
    # as the remaining columns. We feed everything except the labels.
    fitter = CoxPHFitter(penalizer=penalizer)
    fitter.fit(
        design,
        duration_col="blocks_to_flip",
        event_col="event_observed",
        show_progress=False,
    )

    coef_series: pd.Series = fitter.params_
    feature_names = list(coef_series.index)
    coefficients = {name: float(coef_series[name]) for name in feature_names}

    # Baseline hazard scalar: average of the baseline cumulative hazard
    # increments. Used in T3HazardPolicy as
    #     E[remaining_dwell] ~ 1 / (baseline_mean_hazard * exp(beta'x))
    bh = fitter.baseline_hazard_
    baseline_mean_hazard = float(bh.iloc[:, 0].mean()) if len(bh) else 0.0

    # Concordance index on the training set (in-sample; Plan D D2
    # bootstrap CI computes out-of-sample CI on test fold).
    predicted_partial_hazards = fitter.predict_partial_hazard(design)
    c_index = float(
        concordance_index(
            design["blocks_to_flip"],
            -predicted_partial_hazards,
            design["event_observed"],
        )
    )

    return T3TrainingArtifact(
        feature_names=feature_names,
        coefficients=coefficients,
        baseline_mean_hazard=baseline_mean_hazard,
        c_index=c_index,
        n_train_rows=len(design),
        horizon_blocks=horizon_blocks,
        penalizer=penalizer,
    )
