"""Walk-forward validation property tests."""
from __future__ import annotations

import pandas as pd
import pytest


def test_six_windows_non_overlapping():
    from scripts.dossier.walk_forward import WINDOWS
    assert len(WINDOWS) == 6
    prev_end = None
    for start, end in WINDOWS:
        assert isinstance(start, pd.Timestamp) and start.tz is not None
        assert isinstance(end, pd.Timestamp) and end.tz is not None
        assert start < end
        if prev_end is not None:
            assert start >= prev_end
        prev_end = end


def test_windows_cover_full_panel():
    from scripts.dossier.walk_forward import WINDOWS
    first_start = WINDOWS[0][0]
    last_end = WINDOWS[-1][1]
    assert first_start <= pd.Timestamp("2024-11-01", tz="UTC")
    assert last_end >= pd.Timestamp("2026-05-01", tz="UTC")


def test_paired_bootstrap_returns_named_tuple():
    from scripts.dossier.walk_forward import paired_bootstrap_per_window_deltas
    deltas = pd.Series([0.5, 0.3, -0.1, 0.4, 0.2, 0.6])
    result = paired_bootstrap_per_window_deltas(
        deltas, name="H1aux", n_resamples=200, seed=42,
    )
    assert hasattr(result, "delta_mean")
    assert hasattr(result, "ci_low_95")
    assert hasattr(result, "ci_high_95")
    assert hasattr(result, "nominal_p")
    assert hasattr(result, "directional_consistency")
    assert result.directional_consistency == 5  # 5 of 6 deltas positive


def test_paired_bootstrap_ci_brackets_mean():
    from scripts.dossier.walk_forward import paired_bootstrap_per_window_deltas
    deltas = pd.Series([0.5, 0.3, 0.6, 0.4, 0.2, 0.7])  # all positive
    result = paired_bootstrap_per_window_deltas(
        deltas, name="t", n_resamples=2000, seed=42,
    )
    assert result.ci_low_95 < result.delta_mean < result.ci_high_95
    assert result.ci_low_95 > 0  # all positive -> CI > 0
    assert result.nominal_p < 0.05
