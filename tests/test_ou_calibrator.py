"""Tests for OUCalibrator: MLE of an Ornstein-Uhlenbeck process on a
rolling spread window."""
import numpy as np
import pytest

from decision.ou_calibrator import OUCalibrator, OUParams


def _simulate_ou(*, kappa, theta, sigma, S0, n, seed):
    """Forward-simulate an OU path with dt=1 for synthetic tests."""
    rng = np.random.default_rng(seed)
    S = np.empty(n)
    S[0] = S0
    eps = rng.standard_normal(n - 1)
    for i in range(1, n):
        S[i] = S[i-1] + kappa * (theta - S[i-1]) + sigma * eps[i-1]
    return S


def test_ou_mle_recovers_synthetic_params_within_50pct():
    """Forward-simulate a known OU, then MLE and check param recovery."""
    true_kappa, true_theta, true_sigma = 0.01, 0.005, 0.002
    S = _simulate_ou(
        kappa=true_kappa, theta=true_theta, sigma=true_sigma,
        S0=0.0, n=10_000, seed=42,
    )
    params = OUCalibrator.fit(S)
    assert abs(params.kappa - true_kappa) / true_kappa < 0.5
    assert abs(params.theta - true_theta) < 0.01
    assert abs(params.sigma - true_sigma) / true_sigma < 0.5


def test_rolling_window_yields_changing_params():
    """Two windows from a regime-changing series should give different params."""
    a = _simulate_ou(kappa=0.01, theta=0.005, sigma=0.001, S0=0, n=2000, seed=1)
    b = _simulate_ou(kappa=0.05, theta=-0.002, sigma=0.003, S0=0, n=2000, seed=2)
    pa = OUCalibrator.fit(a)
    pb = OUCalibrator.fit(b)
    assert pa.kappa != pytest.approx(pb.kappa, rel=0.1)
    assert pa.theta != pytest.approx(pb.theta, abs=1e-3)


def test_fit_requires_minimum_window():
    with pytest.raises(ValueError, match="need at least"):
        OUCalibrator.fit(np.array([1.0, 2.0]))  # too short


def test_degenerate_constant_series_returns_zero_kappa():
    """A constant spread has no mean reversion; kappa is 0 (or near-0)."""
    S = np.ones(1000) * 0.005
    params = OUCalibrator.fit(S)
    assert abs(params.kappa) < 1e-6
    assert abs(params.theta - 0.005) < 1e-6
    assert params.sigma < 1e-6
