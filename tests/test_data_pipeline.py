"""Tests for data pipeline: loaders, cleaning, feature engineering.

1. Loader smoke tests: pull 1-day window, check schema + non-empty.
2. Cleaning invariants: NaN count drops; no rates outside [0, 0.50] after.
3. Feature engineering: rate_residual + f_kink(u) reconstructs r to within 1e-6.
4. Cross-protocol alignment: Aave and Compound parquets join on `time` with
   no gaps after forward-fill.
5. RAY / WAD normalization parity: known historical rate matches between
   RAY-sourced (Aave) and WAD-sourced (Compound) for the same day.
"""
# TODO Week 1 Days 1-3 (18-20 May 2026)
import pytest


@pytest.mark.skip(reason="Week 1 Day 3")
def test_aave_loader_smoke() -> None:
    raise NotImplementedError


@pytest.mark.skip(reason="Week 1 Day 3")
def test_compound_loader_smoke() -> None:
    raise NotImplementedError


@pytest.mark.skip(reason="Week 1 Day 4")
def test_kink_subtraction_inverts() -> None:
    """r_residual(t) + f_kink(u(t)) == r(t) for all t in cached data."""
    raise NotImplementedError
