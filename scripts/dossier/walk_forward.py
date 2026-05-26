"""Walk-forward validation primitives: window definitions, paired
bootstrap on per-window deltaSharpe deltas, single-window replay helper.

The 6-window split is non-overlapping and pre-registered. Inference
is paired bootstrap over the N=6 per-window deltaSharpe deltas, with
directional consistency reported alongside CI."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


WINDOWS: list[tuple[pd.Timestamp, pd.Timestamp]] = [
    (pd.Timestamp("2024-11-01", tz="UTC"), pd.Timestamp("2025-02-01", tz="UTC")),
    (pd.Timestamp("2025-02-01", tz="UTC"), pd.Timestamp("2025-05-01", tz="UTC")),
    (pd.Timestamp("2025-05-01", tz="UTC"), pd.Timestamp("2025-08-01", tz="UTC")),
    (pd.Timestamp("2025-08-01", tz="UTC"), pd.Timestamp("2025-11-01", tz="UTC")),
    (pd.Timestamp("2025-11-01", tz="UTC"), pd.Timestamp("2026-02-01", tz="UTC")),
    (pd.Timestamp("2026-02-01", tz="UTC"), pd.Timestamp("2026-05-01", tz="UTC")),
]


@dataclass(frozen=True)
class WalkForwardResult:
    name: str
    delta_mean: float
    ci_low_95: float
    ci_high_95: float
    nominal_p: float
    directional_consistency: int  # # of windows with positive delta (out of N)
    n_windows: int
    n_bootstrap: int


def paired_bootstrap_per_window_deltas(
    deltas: pd.Series,
    *,
    name: str,
    n_resamples: int = 10_000,
    seed: int = 42,
) -> WalkForwardResult:
    """Paired bootstrap on per-window deltaSharpe deltas."""
    d = deltas.to_numpy(dtype=float)
    n = len(d)
    rng = np.random.default_rng(seed)
    boots = np.empty(n_resamples, dtype=float)
    for i in range(n_resamples):
        idx = rng.integers(0, n, size=n)
        boots[i] = d[idx].mean()
    return WalkForwardResult(
        name=name,
        delta_mean=float(d.mean()),
        ci_low_95=float(np.percentile(boots, 2.5)),
        ci_high_95=float(np.percentile(boots, 97.5)),
        nominal_p=float(np.mean(boots <= 0)),
        directional_consistency=int((d > 0).sum()),
        n_windows=n,
        n_bootstrap=n_resamples,
    )
