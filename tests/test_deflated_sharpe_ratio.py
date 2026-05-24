"""Test D4: Deflated Sharpe Ratio per Lopez de Prado AFML Ch 14.7.3."""
import math

import numpy as np
import pytest


def test_sr_zero_for_n_trials():
    """SR_0 = sqrt(2 * log(N)). For N=3 -> ~1.482."""
    from backtest.deflated_sharpe_ratio import sr_zero_from_n_trials
    assert math.isclose(sr_zero_from_n_trials(1), 0.0, abs_tol=1e-12)
    assert math.isclose(sr_zero_from_n_trials(3), math.sqrt(2 * math.log(3)),
                        rel_tol=1e-12)
    assert sr_zero_from_n_trials(54) > sr_zero_from_n_trials(3)


def test_dsr_perfect_strategy_high_dsr():
    """A 'too good to be true' SR with low N and many obs -> DSR ~ 1."""
    from backtest.deflated_sharpe_ratio import compute_dsr
    rng = np.random.default_rng(0)
    # Construct: monthly returns with high mean / low std -> high SR.
    rets = rng.normal(loc=0.05, scale=0.005, size=120)
    res = compute_dsr(rets, n_trials=3)
    assert res.n_trials == 3
    assert res.t == 120
    assert res.dsr > 0.95
    assert res.passes is True


def test_dsr_marginal_strategy_low_dsr():
    """A small-edge strategy on few obs (T=4) -> DSR << 0.95."""
    from backtest.deflated_sharpe_ratio import compute_dsr
    # Tiny mean, large std - Sharpe well under sqrt(2*log(3)) = 1.482.
    rets = np.array([0.002, -0.001, 0.003, 0.000])
    res = compute_dsr(rets, n_trials=3)
    assert res.t == 4
    assert res.dsr < 0.95
    assert res.passes is False


def test_dsr_zero_variance_returns_safe_value():
    """Degenerate input (zero std) must not crash."""
    from backtest.deflated_sharpe_ratio import compute_dsr
    rets = np.array([0.01, 0.01, 0.01, 0.01])
    res = compute_dsr(rets, n_trials=3)
    assert math.isfinite(res.dsr)
    assert res.passes is False


def test_compose_h1_significance_csv_shape(tmp_path):
    """The composer joins bootstrap CI (D2) and DSR (D4) into one CSV."""
    from backtest.deflated_sharpe_ratio import compose_h1_significance
    import pandas as pd

    bootstrap_df = pd.DataFrame([
        {"name": "H1a", "policy_a": "t1_threshold", "policy_b": "mcdm_ema",
         "delta_sharpe_point": 2.5, "ci_low_95": 0.4, "ci_high_95": 4.9,
         "nominal_p": 0.02, "n_bootstrap": 1000, "n_months": 4, "note": ""},
        {"name": "H1b", "policy_a": "t2_optimal_stopping", "policy_b": "t1_threshold",
         "delta_sharpe_point": 0.6, "ci_low_95": -0.3, "ci_high_95": 1.4,
         "nominal_p": 0.18, "n_bootstrap": 1000, "n_months": 4, "note": ""},
        {"name": "H1c", "policy_a": "t3_hazard", "policy_b": "t2_optimal_stopping",
         "delta_sharpe_point": float("nan"), "ci_low_95": float("nan"),
         "ci_high_95": float("nan"), "nominal_p": float("nan"),
         "n_bootstrap": 1000, "n_months": 0, "note": "missing policy column"},
    ])

    monthly_returns = pd.DataFrame({
        "t1_threshold": [0.005, 0.006, 0.004, 0.007],
        "mcdm_ema":     [0.003, 0.004, 0.003, 0.005],
        "t2_optimal_stopping": [0.006, 0.007, 0.006, 0.008],
        "t3_hazard":    [float("nan")] * 4,
    })

    out = compose_h1_significance(bootstrap_df, monthly_returns, n_trials=3)
    assert {"name", "delta_sharpe_point", "ci_low_95", "ci_high_95",
            "nominal_p", "dsr", "sr_zero", "passes_dsr"} <= set(out.columns)
    assert len(out) == 3
    # H1c row should have NaN DSR (no T3 data) but not crash.
    h1c = out[out["name"] == "H1c"].iloc[0]
    assert pd.isna(h1c["dsr"])
