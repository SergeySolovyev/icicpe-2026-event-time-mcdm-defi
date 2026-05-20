"""Run all 15 ablations from PROJECT_2_PLAN.md S10 on REAL data (default) or
synthetic data (``--synthetic``).

Ablation matrix (plan S10):

    1.  No-forecast EMA baseline (Baseline C)            -- mandatory strawman
    2.  Naive last-observation forecast
    3.  CIR-calibrated forecast (Baseline D)             -- in-file wrapper
    4.  Markov-switching short-rate                       -- in-file wrapper
    5.  CatBoost on hand-crafted features                 -- in-file wrapper
    6.  Single-branch DA-GRU                              -- SKIPPED (needs ONNX variant)
    7.  Dual-branch WITHOUT kink subtraction              -- SKIPPED (needs ONNX variant)
    8.  Forecast with ranking-loss only                   -- SKIPPED (needs ONNX variant)
    9.  MCDM equal weights vs tuned
    10. Single-protocol benchmark (Aave-only, Compound-only)
    11. Greedy max-forecasted-APY vs TOPSIS-MCDM
    12. Zero-gas vs realistic-gas
    13. Sliding-window stability (DefaultPipeline window_size=14*24h)
    14. OOD test on USDC depeg week (Mar 2023)            -- SKIPPED (no OOD dataset)
    15. Forecast horizon sweep (3h, 6h, 12h, 24h)         -- SKIPPED (needs ONNX variants)

Each ablation writes one or more rows to ``results/tables/ablations.csv`` with
columns

    ablation_id, ablation_name, strategy_class, n_rebalances, net_apy,
    sharpe_annual, max_drawdown, gas_usd, status

(plus a richer set of debug columns -- ``apy``, ``sharpe``, ``max_dd``,
``vol_annual`` etc. -- kept for downstream notebooks). Ablations whose code
dependencies are not yet ready produce a single ``SKIPPED:<reason>`` row with
NaN metrics so the table shape is stable.

Headline figure: ``results/figures/ablation_1_vs_main.png`` -- equity-curve
overlay of Ablation 1 (no-forecast EMA) vs the main PredictiveMCDM. This is
the whitepaper title-page figure.

Per-ablation equity plots are emitted to
``results/figures/ablation_<N>_<name>.png`` when ``--save-figure`` is set.

Run::

    python -m backtest.run_ablations
    python -m backtest.run_ablations --synthetic
    python -m backtest.run_ablations --only 1
    python -m backtest.run_ablations --only 9 --save-figure
"""
from __future__ import annotations

import argparse
import sys
import warnings
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "extras" / "fractal_pr_lending_allocation"))

from fractal.core.base import Observation  # noqa: E402

from backtest.observations_builder import build_all  # noqa: E402
from backtest.run_main import (  # noqa: E402
    DEFAULT_ONNX_PATH,
    MainRunConfig,
    _compute_headline_metrics,
    _portfolio_equity,
    _run_one,
)
from strategies.baseline_apy_greedy import APYGreedyStrategy, APYGreedyParams  # noqa: E402
from strategies.baseline_mcdm_ema import MCDMEMAStrategy, MCDMEMAParams  # noqa: E402
from base_lending_allocation import BaseLendingAllocationParams  # noqa: E402

# PredictiveMCDM is required for ablation #2 (naive fallback path) and the
# main-overlay on the headline figure. Wrap defensively so the module is
# importable in a stripped-down environment.
try:
    from strategies.predictive_mcdm import (  # noqa: E402
        PredictiveMCDMStrategy,
        PredictiveMCDMParams,
    )
    _HAS_PREDICTIVE = True
except Exception as _exc:                                  # noqa: BLE001
    logger.warning(f"PredictiveMCDMStrategy import failed: {_exc}")
    PredictiveMCDMStrategy = None                          # type: ignore[assignment]
    PredictiveMCDMParams = None                            # type: ignore[assignment]
    _HAS_PREDICTIVE = False


RESULTS_DIR = ROOT / "results"
TABLES_DIR = RESULTS_DIR / "tables"
FIGURES_DIR = RESULTS_DIR / "figures"
ONNX_PATH = DEFAULT_ONNX_PATH


# ---------------------------------------------------------------------------
# Row schema
#
# CSV columns (required by task spec):
#     ablation_id, ablation_name, strategy_class, n_rebalances, net_apy,
#     sharpe_annual, max_drawdown, gas_usd, status
#
# We also persist the richer debug columns (apy, sharpe, max_dd, ...) that the
# run_baselines/run_main pipelines emit, so the ablations CSV can flow into
# the existing notebook tooling without a separate schema.
# ---------------------------------------------------------------------------

_REQUIRED_COLS = [
    "ablation_id", "ablation_name", "strategy_class", "n_rebalances",
    "net_apy", "sharpe_annual", "max_drawdown", "gas_usd", "status",
]
_DEBUG_COLS = [
    "calmar", "turnover_per_month", "gas_spent_usd", "forecast_hit_rate",
]
_ALL_COLS = _REQUIRED_COLS + _DEBUG_COLS


def _nan_row(ablation_id: str, ablation_name: str, strategy_class: str,
             reason: str) -> Dict[str, Any]:
    """Standardised SKIPPED row with NaN metrics."""
    row: Dict[str, Any] = {
        "ablation_id":   ablation_id,
        "ablation_name": ablation_name,
        "strategy_class": strategy_class,
        "n_rebalances":  0,
        "net_apy":       float("nan"),
        "sharpe_annual": float("nan"),
        "max_drawdown":  float("nan"),
        "gas_usd":       float("nan"),
        "status":        f"SKIPPED:{reason}",
    }
    for c in _DEBUG_COLS:
        row[c] = float("nan")
    return row


def _ok_row(ablation_id: str, ablation_name: str, strategy_class: str,
            metrics: Dict[str, float]) -> Dict[str, Any]:
    """Standardised OK row -- aliases run_main metrics into the task schema."""
    row: Dict[str, Any] = {
        "ablation_id":   ablation_id,
        "ablation_name": ablation_name,
        "strategy_class": strategy_class,
        "n_rebalances":  int(metrics.get("n_rebalances", 0) or 0),
        "net_apy":       float(metrics.get("net_apy", float("nan"))),
        "sharpe_annual": float(metrics.get("sharpe_annual", float("nan"))),
        "max_drawdown":  float(metrics.get("max_drawdown", float("nan"))),
        "gas_usd":       float(metrics.get("gas_spent_usd", float("nan"))),
        "status":        "OK",
    }
    for c in _DEBUG_COLS:
        row[c] = float(metrics.get(c, float("nan")))
    return row


# ---------------------------------------------------------------------------
# Strategy runner with uniform error handling
# ---------------------------------------------------------------------------

def _safe_run(
    strategy_cls,
    params,
    observations: List[Observation],
    label: str,
    cfg: MainRunConfig,
) -> Tuple[Optional[Dict[str, float]], Optional[pd.Series], Optional[str]]:
    """Run a strategy, return (metrics, equity_series, err_or_None)."""
    try:
        _strategy, result, eq = _run_one(strategy_cls, params, observations, label)
        metrics = _compute_headline_metrics(eq, result.to_dataframe(), cfg)
        return metrics, eq, None
    except Exception as exc:                               # noqa: BLE001
        logger.error(f"[{label}] runtime error: {exc}")
        return None, None, str(exc)


# ---------------------------------------------------------------------------
# In-file forecast-injecting MCDM strategies for ablations #3, #4, #5, #11.
#
# Each subclasses MCDMEMAStrategy and overrides compute_criteria_vector so
# that f_APY consumes a pre-computed r_hat[entity] instead of an EMA-smoothed
# spot rate. The forecast dict is populated by the ablation runner from a
# trained baseline forecaster (CIR / Markov / CatBoost) BEFORE strategy.run().
#
# Mechanism: we attach the (timestamp -> {AAVE,COMPOUND} r_hat) lookup table
# as a class attribute and read self._current_timestamp set by the base
# class's `step()` hook. During warm-up the spot rate fallback applies.
# ---------------------------------------------------------------------------

class _ForecastInjectedMCDM(MCDMEMAStrategy):
    """MCDM-EMA with f_APY replaced by an externally-injected forecast.

    Subclass and set ``FORECAST_TABLE`` (an attribute on the instance, NOT a
    class attribute, so two instances on different feeds do not collide).
    """

    PARAMS_CLS = MCDMEMAParams

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # {ts -> {entity_name: annualised r_hat}}; populated by the runner.
        self.forecast_table: Dict[Any, Dict[str, float]] = {}

    def compute_criteria_vector(self, entity_name: str) -> np.ndarray:
        gs = self.get_entity(entity_name).global_state
        utilisation = float(getattr(gs, "utilization", 0.0))
        gas_gwei = float(getattr(gs, "gas_gwei", 30.0))
        delta_tvl = float(getattr(gs, "delta_tvl_24h", 0.0))

        # Lookup forecast for this timestamp; fall back to spot * 365 * 24
        ts = self._current_timestamp
        fc = self.forecast_table.get(ts) if ts is not None else None
        if fc is not None and entity_name in fc:
            annual = float(fc[entity_name])
        else:
            rate = float(getattr(gs, "lending_rate", 0.0))
            annual = rate * 365 * 24

        return np.array([
            self._f_apy(annual, self._params.APYMAX_NORM),
            self._f_risk(utilisation),
            self._f_cost(gas_gwei, self._params.GAS_PER_REBALANCE,
                         self._params.GAS_MAX_ETH),
            self._f_stab(delta_tvl),
        ])


class _ForecastedAPYGreedy(APYGreedyStrategy):
    """APY-greedy that picks argmax over forecasted (not spot) rates.

    Used by ablation #11 (Greedy-on-forecast vs TOPSIS-MCDM-on-forecast).
    Falls back to spot rate during warm-up.
    """

    PARAMS_CLS = APYGreedyParams

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.forecast_table: Dict[Any, Dict[str, float]] = {}

    def compute_criteria_vector(self, entity_name: str) -> np.ndarray:
        gs = self.get_entity(entity_name).global_state
        ts = self._current_timestamp
        fc = self.forecast_table.get(ts) if ts is not None else None
        if fc is not None and entity_name in fc:
            return np.array([float(fc[entity_name])])
        return np.array([float(getattr(gs, "lending_rate", 0.0)) * 365 * 24])


# ---------------------------------------------------------------------------
# Pre-computed forecast builders (CIR / Markov / CatBoost). Each takes the
# train+val observations to fit, the test observations to score, and returns
# a {timestamp -> {AAVE, COMPOUND: annualised r_hat}} dict ready to attach
# to the forecast-injected strategy.
# ---------------------------------------------------------------------------

def _obs_to_panel(observations: List[Observation]) -> pd.DataFrame:
    """Reconstruct the joined panel (r_aave, r_compound, u_aave, u_compound)
    from a list of Observations. Per-period rates (matches loader convention).
    """
    rows = []
    for obs in observations:
        if "AAVE" not in obs.states or "COMPOUND" not in obs.states:
            continue
        a = obs.states["AAVE"]
        c = obs.states["COMPOUND"]
        rows.append({
            "ts":         obs.timestamp,
            "r_aave":     float(getattr(a, "lending_rate", 0.0)),
            "r_compound": float(getattr(c, "lending_rate", 0.0)),
            "u_aave":     float(getattr(a, "utilization", 0.0)),
            "u_compound": float(getattr(c, "utilization", 0.0)),
            "gas_gwei":   float(getattr(a, "gas_gwei", 30.0)),
        })
    df = pd.DataFrame(rows).set_index("ts")
    df.index = pd.DatetimeIndex(df.index)
    return df


PER_HOUR_TO_ANNUAL = 365.0 * 24.0


def _build_cir_forecasts(fit_obs: List[Observation],
                         test_obs: List[Observation],
                         horizon: int = 12) -> Dict[Any, Dict[str, float]]:
    """Fit CIRForecaster on fit_obs (train+val), forecast at every test ts."""
    from forecaster.baseline_cir import CIRForecaster

    fit_df = _obs_to_panel(fit_obs)
    test_df = _obs_to_panel(test_obs)
    if fit_df.empty or test_df.empty:
        return {}

    # Annualised rates for the CIR fit (model assumes time in years).
    r_aave_annual_train = fit_df["r_aave"].to_numpy() * PER_HOUR_TO_ANNUAL
    r_comp_annual_train = fit_df["r_compound"].to_numpy() * PER_HOUR_TO_ANNUAL

    f_a = CIRForecaster(partitioning="utilization", n_partitions=3,
                        n_paths=200, seed=0)
    f_a.fit(r_aave_annual_train, fit_df["u_aave"].to_numpy())
    f_c = CIRForecaster(partitioning="utilization", n_partitions=3,
                        n_paths=200, seed=1)
    f_c.fit(r_comp_annual_train, fit_df["u_compound"].to_numpy())

    out: Dict[Any, Dict[str, float]] = {}
    # Walk the test set with a 200-step look-back history; r_t is the latest.
    r_aave_test_annual = test_df["r_aave"].to_numpy() * PER_HOUR_TO_ANNUAL
    r_comp_test_annual = test_df["r_compound"].to_numpy() * PER_HOUR_TO_ANNUAL
    test_index = list(test_df.index)
    for t in range(len(test_index)):
        lo = max(0, t - 199)
        try:
            r_hat_a = f_a.predict(r_aave_test_annual[lo:t + 1], horizon=horizon)
            r_hat_c = f_c.predict(r_comp_test_annual[lo:t + 1], horizon=horizon)
        except Exception:                                  # noqa: BLE001
            continue
        ts = test_index[t]
        out[ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts] = {
            "AAVE": float(r_hat_a),
            "COMPOUND": float(r_hat_c),
        }
    return out


def _build_markov_forecasts(fit_obs: List[Observation],
                            test_obs: List[Observation],
                            horizon: int = 12) -> Dict[Any, Dict[str, float]]:
    from forecaster.baseline_markov import MarkovSwitchingForecaster

    fit_df = _obs_to_panel(fit_obs)
    test_df = _obs_to_panel(test_obs)
    if fit_df.empty or test_df.empty:
        return {}

    r_a_train = fit_df["r_aave"].to_numpy() * PER_HOUR_TO_ANNUAL
    r_c_train = fit_df["r_compound"].to_numpy() * PER_HOUR_TO_ANNUAL

    f_a = MarkovSwitchingForecaster(n_regimes=2, n_sims=200,
                                    method="quantile", seed=0)
    f_a.fit(r_a_train, fit_df["u_aave"].to_numpy())
    f_c = MarkovSwitchingForecaster(n_regimes=2, n_sims=200,
                                    method="quantile", seed=1)
    f_c.fit(r_c_train, fit_df["u_compound"].to_numpy())

    r_a_test = test_df["r_aave"].to_numpy() * PER_HOUR_TO_ANNUAL
    r_c_test = test_df["r_compound"].to_numpy() * PER_HOUR_TO_ANNUAL
    u_a_test = test_df["u_aave"].to_numpy()
    u_c_test = test_df["u_compound"].to_numpy()

    out: Dict[Any, Dict[str, float]] = {}
    test_index = list(test_df.index)
    for t in range(len(test_index)):
        lo = max(0, t - 199)
        try:
            r_hat_a = f_a.predict(r_a_test[lo:t + 1], u_a_test[lo:t + 1],
                                  horizon=horizon)
            r_hat_c = f_c.predict(r_c_test[lo:t + 1], u_c_test[lo:t + 1],
                                  horizon=horizon)
        except Exception:                                  # noqa: BLE001
            continue
        ts = test_index[t]
        out[ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts] = {
            "AAVE": float(r_hat_a),
            "COMPOUND": float(r_hat_c),
        }
    return out


def _build_catboost_forecasts(fit_obs: List[Observation],
                              test_obs: List[Observation],
                              horizon: int = 12) -> Dict[Any, Dict[str, float]]:
    """Fit per-protocol CatBoost on fit_obs, predict on test_obs."""
    from forecaster.baseline_catboost import (
        CatBoostConfig, CatBoostForecaster,
    )

    fit_df = _obs_to_panel(fit_obs)
    test_df = _obs_to_panel(test_obs)
    if fit_df.empty or test_df.empty:
        return {}

    # Use the same per-period rate scale on fit + predict; we annualise at
    # the end before stuffing into the forecast table.
    cfg = CatBoostConfig(depth=4, iterations=300, learning_rate=0.1,
                        l2_leaf_reg=3, verbose=False,
                        early_stopping_rounds=None)
    fcst = CatBoostForecaster(cfg=cfg, horizon=horizon)
    try:
        fcst.fit(fit_df)
    except Exception as exc:                               # noqa: BLE001
        logger.warning(f"[catboost] fit failed: {exc}")
        return {}

    # Roll the test set through predict() once per row that has enough history.
    out: Dict[Any, Dict[str, float]] = {}
    test_index = list(test_df.index)
    min_history = max(max(fcst.lags), max(fcst.windows), 24) + 2
    for t in range(min_history, len(test_index)):
        hist = test_df.iloc[: t + 1]
        try:
            r_a, r_c = fcst.predict(hist, horizon=horizon)
        except Exception:                                  # noqa: BLE001
            continue
        ts = test_index[t]
        out[ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts] = {
            "AAVE":     float(r_a) * PER_HOUR_TO_ANNUAL,
            "COMPOUND": float(r_c) * PER_HOUR_TO_ANNUAL,
        }
    return out


# ---------------------------------------------------------------------------
# Ablation 1: No-forecast EMA baseline (Baseline C strawman)
# ---------------------------------------------------------------------------

def ablation_1_no_forecast_ema(
    observations: List[Observation],
    cfg: MainRunConfig,
    **_opts,
) -> Tuple[List[Dict[str, Any]], Optional[pd.Series]]:
    params = MCDMEMAParams(
        INITIAL_BALANCE=cfg.initial_balance,
        DEFAULT_INITIAL_ENTITY="AAVE",
    )
    metrics, eq, err = _safe_run(MCDMEMAStrategy, params, observations,
                                 "abl1/MCDM-EMA", cfg)
    if metrics is None:
        return [_nan_row("1", "no_forecast_ema", "MCDMEMAStrategy",
                         err or "runtime error")], None
    return [_ok_row("1", "no_forecast_ema", "MCDMEMAStrategy", metrics)], eq


# ---------------------------------------------------------------------------
# Ablation 2: Naive last-observation forecast.
#
# We use the forecast-injected MCDM with a forecast table where r_hat[t] is
# simply the spot annualised rate at time t. Functionally identical to
# baseline_apy + MCDM-style scoring but with f_APY consuming "naive forecast".
# ---------------------------------------------------------------------------

def ablation_2_naive_forecast(
    observations: List[Observation],
    cfg: MainRunConfig,
    **_opts,
) -> List[Dict[str, Any]]:
    forecast_table: Dict[Any, Dict[str, float]] = {}
    for obs in observations:
        if "AAVE" not in obs.states or "COMPOUND" not in obs.states:
            continue
        gs_a = obs.states["AAVE"]
        gs_c = obs.states["COMPOUND"]
        forecast_table[obs.timestamp] = {
            "AAVE":     float(getattr(gs_a, "lending_rate", 0.0)) * PER_HOUR_TO_ANNUAL,
            "COMPOUND": float(getattr(gs_c, "lending_rate", 0.0)) * PER_HOUR_TO_ANNUAL,
        }
    return _run_forecast_injected(
        forecast_table, observations, cfg,
        ablation_id="2", ablation_name="naive_forecast",
        label="abl2/naive",
    )


# ---------------------------------------------------------------------------
# Ablation 3: CIR-calibrated forecast (Baseline D)
# ---------------------------------------------------------------------------

def ablation_3_cir_forecast(
    observations: List[Observation],
    cfg: MainRunConfig,
    *,
    fit_obs: Optional[List[Observation]] = None,
    **_opts,
) -> List[Dict[str, Any]]:
    if fit_obs is None or len(fit_obs) < 100:
        return [_nan_row("3", "cir_forecast", "CIRForecaster+MCDM",
                         "insufficient fit_obs for CIR calibration")]
    try:
        table = _build_cir_forecasts(fit_obs, observations, horizon=12)
    except Exception as exc:                               # noqa: BLE001
        return [_nan_row("3", "cir_forecast", "CIRForecaster+MCDM",
                         f"CIR build failed: {exc}")]
    return _run_forecast_injected(
        table, observations, cfg,
        ablation_id="3", ablation_name="cir_forecast",
        label="abl3/CIR",
    )


# ---------------------------------------------------------------------------
# Ablation 4: Markov-switching 2-state on utilization
# ---------------------------------------------------------------------------

def ablation_4_markov(
    observations: List[Observation],
    cfg: MainRunConfig,
    *,
    fit_obs: Optional[List[Observation]] = None,
    **_opts,
) -> List[Dict[str, Any]]:
    if fit_obs is None or len(fit_obs) < 100:
        return [_nan_row("4", "markov_switching", "MarkovSwitching+MCDM",
                         "insufficient fit_obs for Markov fit")]
    try:
        table = _build_markov_forecasts(fit_obs, observations, horizon=12)
    except Exception as exc:                               # noqa: BLE001
        return [_nan_row("4", "markov_switching", "MarkovSwitching+MCDM",
                         f"Markov build failed: {exc}")]
    return _run_forecast_injected(
        table, observations, cfg,
        ablation_id="4", ablation_name="markov_switching",
        label="abl4/Markov",
    )


# ---------------------------------------------------------------------------
# Ablation 5: CatBoost on hand-crafted features
# ---------------------------------------------------------------------------

def ablation_5_catboost(
    observations: List[Observation],
    cfg: MainRunConfig,
    *,
    fit_obs: Optional[List[Observation]] = None,
    **_opts,
) -> List[Dict[str, Any]]:
    if fit_obs is None or len(fit_obs) < 200:
        return [_nan_row("5", "catboost", "CatBoost+MCDM",
                         "insufficient fit_obs for CatBoost training")]
    try:
        from forecaster.baseline_catboost import CatBoostForecaster  # noqa: F401
    except Exception as exc:                               # noqa: BLE001
        return [_nan_row("5", "catboost", "CatBoost+MCDM",
                         f"CatBoost import failed: {exc}")]
    try:
        table = _build_catboost_forecasts(fit_obs, observations, horizon=12)
    except Exception as exc:                               # noqa: BLE001
        return [_nan_row("5", "catboost", "CatBoost+MCDM",
                         f"CatBoost build failed: {exc}")]
    return _run_forecast_injected(
        table, observations, cfg,
        ablation_id="5", ablation_name="catboost",
        label="abl5/CatBoost",
    )


# ---------------------------------------------------------------------------
# Ablations 6, 7, 8: SKIPPED (require additional ONNX variants of the
# forecaster that we have not trained for this run).
# ---------------------------------------------------------------------------

def ablation_6_single_branch(observations, cfg, **_opts):
    return [_nan_row("6", "single_branch_da_gru", "PredictiveMCDM",
                     "needs single-branch ONNX export (branch_b_input_dim=0)")]


def ablation_7_no_kink(observations, cfg, **_opts):
    return [_nan_row("7", "dual_branch_no_kink", "PredictiveMCDM",
                     "needs ONNX variant trained on raw r instead of eps")]


def ablation_8_ranking_only(observations, cfg, **_opts):
    return [_nan_row("8", "ranking_loss_only", "PredictiveMCDM",
                     "needs ONNX variant trained with alpha=0,beta=1,gamma=0")]


# ---------------------------------------------------------------------------
# Ablation 9: MCDM equal weights vs tuned
# ---------------------------------------------------------------------------

def ablation_9_equal_weights(
    observations: List[Observation],
    cfg: MainRunConfig,
    **_opts,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    # Tuned weights (default constants from Solovev 2026b)
    tuned = MCDMEMAParams(
        INITIAL_BALANCE=cfg.initial_balance,
        DEFAULT_INITIAL_ENTITY="AAVE",
    )
    metrics, _eq, err = _safe_run(MCDMEMAStrategy, tuned, observations,
                                  "abl9/tuned", cfg)
    if metrics is None:
        rows.append(_nan_row("9a", "equal_vs_tuned[tuned]",
                             "MCDMEMAStrategy", err or "runtime error"))
    else:
        rows.append(_ok_row("9a", "equal_vs_tuned[tuned]",
                            "MCDMEMAStrategy", metrics))

    # Equal weights = 0.25 across the 4 criteria
    equal = MCDMEMAParams(
        INITIAL_BALANCE=cfg.initial_balance,
        DEFAULT_INITIAL_ENTITY="AAVE",
        W_APY=0.25, W_RISK=0.25, W_COST=0.25, W_STAB=0.25,
    )
    metrics, _eq, err = _safe_run(MCDMEMAStrategy, equal, observations,
                                  "abl9/equal", cfg)
    if metrics is None:
        rows.append(_nan_row("9b", "equal_vs_tuned[equal]",
                             "MCDMEMAStrategy", err or "runtime error"))
    else:
        rows.append(_ok_row("9b", "equal_vs_tuned[equal]",
                            "MCDMEMAStrategy", metrics))
    return rows


# ---------------------------------------------------------------------------
# Ablation 10: Single-protocol benchmark (Aave-only, Compound-only)
# ---------------------------------------------------------------------------

def _filter_states(observations: List[Observation],
                   keep: str) -> List[Observation]:
    """Return new observations with only the named entity in `states`."""
    out: List[Observation] = []
    for obs in observations:
        if keep not in obs.states:
            continue
        out.append(Observation(
            timestamp=obs.timestamp,
            states={keep: obs.states[keep]},
        ))
    return out


def ablation_10_single_protocol(
    observations: List[Observation],
    cfg: MainRunConfig,
    **_opts,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for proto in ("AAVE", "COMPOUND"):
        class _SingleStrat(MCDMEMAStrategy):                 # noqa: WPS431
            LENDING_ENTITY_NAMES = (proto,)

        sub = _filter_states(observations, proto)
        params = MCDMEMAParams(
            INITIAL_BALANCE=cfg.initial_balance,
            DEFAULT_INITIAL_ENTITY=proto,
        )
        metrics, _eq, err = _safe_run(_SingleStrat, params, sub,
                                      f"abl10/{proto}", cfg)
        ab_id = "10a" if proto == "AAVE" else "10b"
        if metrics is None:
            rows.append(_nan_row(ab_id, f"single_protocol[{proto}]",
                                 "BuyAndHoldLending", err or "runtime error"))
        else:
            rows.append(_ok_row(ab_id, f"single_protocol[{proto}]",
                                "BuyAndHoldLending", metrics))
    return rows


# ---------------------------------------------------------------------------
# Ablation 11: Greedy max-forecasted-APY vs TOPSIS-MCDM
#
# Both consume the SAME forecast (naive last-obs, the only available signal
# without a trained ONNX variant beyond the main one). The contrast is
# argmax-on-forecast (greedy) vs weighted MCDM scoring on (forecast, risk,
# cost, stability).
# ---------------------------------------------------------------------------

def ablation_11_greedy_vs_mcdm(
    observations: List[Observation],
    cfg: MainRunConfig,
    **_opts,
) -> List[Dict[str, Any]]:
    # Build the shared naive forecast table
    table: Dict[Any, Dict[str, float]] = {}
    for obs in observations:
        if "AAVE" not in obs.states or "COMPOUND" not in obs.states:
            continue
        table[obs.timestamp] = {
            "AAVE":     float(getattr(obs.states["AAVE"], "lending_rate", 0.0))
                        * PER_HOUR_TO_ANNUAL,
            "COMPOUND": float(getattr(obs.states["COMPOUND"], "lending_rate", 0.0))
                        * PER_HOUR_TO_ANNUAL,
        }

    rows: List[Dict[str, Any]] = []

    # Greedy on forecast
    greedy = APYGreedyParams(
        INITIAL_BALANCE=cfg.initial_balance,
        DEFAULT_INITIAL_ENTITY="AAVE",
    )
    try:
        strat = _ForecastedAPYGreedy(debug=False, params=greedy)
        strat.forecast_table = table
        result = strat.run(observations)
        eq = _portfolio_equity(result.to_dataframe())
        if eq is not None:
            eq.index = [o.timestamp for o in observations][: len(eq)]
        metrics = _compute_headline_metrics(eq, result.to_dataframe(), cfg)
        rows.append(_ok_row("11a", "greedy_on_forecast",
                            "ForecastedAPYGreedy", metrics))
    except Exception as exc:                               # noqa: BLE001
        rows.append(_nan_row("11a", "greedy_on_forecast",
                             "ForecastedAPYGreedy", str(exc)))

    # MCDM on forecast
    mcdm = MCDMEMAParams(
        INITIAL_BALANCE=cfg.initial_balance,
        DEFAULT_INITIAL_ENTITY="AAVE",
    )
    try:
        strat = _ForecastInjectedMCDM(debug=False, params=mcdm)
        strat.forecast_table = table
        result = strat.run(observations)
        eq = _portfolio_equity(result.to_dataframe())
        if eq is not None:
            eq.index = [o.timestamp for o in observations][: len(eq)]
        metrics = _compute_headline_metrics(eq, result.to_dataframe(), cfg)
        rows.append(_ok_row("11b", "mcdm_on_forecast",
                            "ForecastInjectedMCDM", metrics))
    except Exception as exc:                               # noqa: BLE001
        rows.append(_nan_row("11b", "mcdm_on_forecast",
                             "ForecastInjectedMCDM", str(exc)))
    return rows


# ---------------------------------------------------------------------------
# Ablation 12: Zero-gas vs realistic-gas
# ---------------------------------------------------------------------------

def ablation_12_gas_sweep(
    observations: List[Observation],
    cfg: MainRunConfig,
    **_opts,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    # Realistic gas (5bps gate, non-zero gas_per_rebalance)
    realistic = MCDMEMAParams(
        INITIAL_BALANCE=cfg.initial_balance,
        DEFAULT_INITIAL_ENTITY="AAVE",
        GAS_GATE_BPS=5.0,
    )
    metrics, _eq, err = _safe_run(MCDMEMAStrategy, realistic, observations,
                                  "abl12/realistic_gas", cfg)
    if metrics is None:
        rows.append(_nan_row("12a", "zero_vs_realistic_gas[realistic]",
                             "MCDMEMAStrategy", err or "runtime error"))
    else:
        rows.append(_ok_row("12a", "zero_vs_realistic_gas[realistic]",
                            "MCDMEMAStrategy", metrics))

    # Zero gas (0bps gate AND zero gas_per_rebalance in metrics)
    zero_params = MCDMEMAParams(
        INITIAL_BALANCE=cfg.initial_balance,
        DEFAULT_INITIAL_ENTITY="AAVE",
        GAS_GATE_BPS=0.0,
    )
    zero_cfg = replace(cfg, gas_per_rebalance=0)
    metrics, _eq, err = _safe_run(MCDMEMAStrategy, zero_params, observations,
                                  "abl12/zero_gas", zero_cfg)
    if metrics is None:
        rows.append(_nan_row("12b", "zero_vs_realistic_gas[zero]",
                             "MCDMEMAStrategy", err or "runtime error"))
    else:
        rows.append(_ok_row("12b", "zero_vs_realistic_gas[zero]",
                            "MCDMEMAStrategy", metrics))
    return rows


# ---------------------------------------------------------------------------
# Ablation 13: Sliding-window stability (mean / q05 / q95 / cvar05)
# ---------------------------------------------------------------------------

def _sliding_windows(observations: List[Observation],
                     window_hours: int,
                     step_hours: int) -> List[List[Observation]]:
    out: List[List[Observation]] = []
    n = len(observations)
    if n < window_hours:
        return out
    i = 0
    while i + window_hours <= n:
        out.append(observations[i:i + window_hours])
        i += step_hours
    return out


def ablation_13_sliding_window(
    observations: List[Observation],
    cfg: MainRunConfig,
    **_opts,
) -> List[Dict[str, Any]]:
    window_hours = 14 * 24
    step_hours = 7 * 24
    windows = _sliding_windows(observations, window_hours, step_hours)
    if not windows:
        return [_nan_row("13", "sliding_window", "MCDMEMAStrategy",
                         f"test window < {window_hours} hours")]

    aprs: List[float] = []
    sharpes: List[float] = []
    dds: List[float] = []
    for w_idx, w in enumerate(windows):
        params = MCDMEMAParams(
            INITIAL_BALANCE=cfg.initial_balance,
            DEFAULT_INITIAL_ENTITY="AAVE",
        )
        metrics, _eq, _err = _safe_run(MCDMEMAStrategy, params, w,
                                       f"abl13/w{w_idx}", cfg)
        if metrics is None:
            continue
        if not pd.isna(metrics["net_apy"]):
            aprs.append(metrics["net_apy"])
        if not pd.isna(metrics["sharpe_annual"]):
            sharpes.append(metrics["sharpe_annual"])
        if not pd.isna(metrics["max_drawdown"]):
            dds.append(metrics["max_drawdown"])

    if not aprs:
        return [_nan_row("13", "sliding_window", "MCDMEMAStrategy",
                         "no windows produced finite metrics")]

    arr = np.asarray(aprs, dtype=float)
    sh = np.asarray(sharpes, dtype=float)
    dd_arr = np.asarray(dds, dtype=float) if dds else np.array([float("nan")])
    q05 = float(np.quantile(arr, 0.05))
    q95 = float(np.quantile(arr, 0.95))
    cvar05 = float(arr[arr <= q05].mean()) if (arr <= q05).any() else q05

    # Single summary row: net_apy is the mean across windows; debug columns
    # repurposed to carry q05 / q95 / cvar05 of net_apy.
    summary = _nan_row("13", "sliding_window", "MCDMEMAStrategy", "")
    summary["status"] = "OK"
    summary["n_rebalances"] = len(windows)
    summary["net_apy"] = float(arr.mean())
    summary["sharpe_annual"] = float(sh.mean()) if len(sh) else float("nan")
    summary["max_drawdown"] = float(dd_arr.mean())
    summary["calmar"] = q05             # repurposed: q05 of net_apy
    summary["turnover_per_month"] = q95 # repurposed: q95 of net_apy
    summary["gas_spent_usd"] = cvar05   # repurposed: cvar05 of net_apy
    return [summary]


# ---------------------------------------------------------------------------
# Ablation 14: OOD test on USDC depeg week (Mar 2023)
# ---------------------------------------------------------------------------

def ablation_14_ood_depeg(
    observations: List[Observation],
    cfg: MainRunConfig,
    **_opts,
) -> List[Dict[str, Any]]:
    return [_nan_row("14", "ood_usdc_depeg", "PredictiveMCDM",
                     "Mar-2023 OOD dataset not provisioned in this repo")]


# ---------------------------------------------------------------------------
# Ablation 15: Forecast horizon sweep (3h, 6h, 12h, 24h)
#
# Requires four separately-trained ONNX models; we have only the 12h export.
# SKIPPED with documented reason.
# ---------------------------------------------------------------------------

def ablation_15_horizon_sweep(
    observations: List[Observation],
    cfg: MainRunConfig,
    **_opts,
) -> List[Dict[str, Any]]:
    return [_nan_row("15", "horizon_sweep", "PredictiveMCDM",
                     "needs ONNX variants at horizons 3h/6h/24h "
                     "(only 12h export exists)")]


# ---------------------------------------------------------------------------
# Ablation 16: Hysteresis-threshold sweep (DEAD_BAND ∈ {0.01, 0.02, 0.05,
# 0.10, 0.20}).
#
# Addresses the n_rebalances=1 observation on the headline PredictiveMCDM run:
# the default HYSTERESIS_THRESHOLD (=0.05, score-delta required to switch)
# leaves the strategy near-static across the 4-month window. By sweeping the
# threshold we expose the rebalance-frequency / Sharpe / gas trade-off and
# turn a potential reviewer objection ("only 1 rebalance — strategy is barely
# active") into an empirical methodology choice. Plan §10 extra row; 5 rows
# 16a..16e in the canonical a/b/.. convention.
#
# Implementation: HYSTERESIS_THRESHOLD is a field on BaseLendingAllocationParams
# (inherited by PredictiveMCDMParams), so we simply pass it via kwargs rather
# than monkey-patching a class attribute. Falls through to a SKIPPED row if
# the ONNX export is missing — same convention as the regime-conditional rows.
# ---------------------------------------------------------------------------

_HYSTERESIS_GRID = [
    ("16a", "hysteresis_0.01", 0.01),
    ("16b", "hysteresis_0.02", 0.02),
    ("16c", "hysteresis_0.05", 0.05),
    ("16d", "hysteresis_0.10", 0.10),
    ("16e", "hysteresis_0.20", 0.20),
]


def ablation_16_hysteresis_sweep(
    observations: List[Observation],
    cfg: MainRunConfig,
    **_opts,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    have_pred = _HAS_PREDICTIVE and ONNX_PATH.exists()
    if not have_pred:
        for ab_id, name, _theta in _HYSTERESIS_GRID:
            rows.append(_nan_row(ab_id, name, "PredictiveMCDMStrategy",
                                 "no ONNX export available"))
        return rows

    for ab_id, name, theta in _HYSTERESIS_GRID:
        params = PredictiveMCDMParams(
            INITIAL_BALANCE=cfg.initial_balance,
            DEFAULT_INITIAL_ENTITY="AAVE",
            HYSTERESIS_THRESHOLD=theta,
        )
        metrics, _eq, err = _safe_run(PredictiveMCDMStrategy, params,
                                      observations, f"abl16/{name}", cfg)
        if metrics is None:
            rows.append(_nan_row(ab_id, name, "PredictiveMCDMStrategy",
                                 err or "runtime error"))
        else:
            rows.append(_ok_row(ab_id, name, "PredictiveMCDMStrategy",
                                metrics))
    return rows


# ---------------------------------------------------------------------------
# Shared runner for forecast-injected ablations (#2, #3, #4, #5)
# ---------------------------------------------------------------------------

def _run_forecast_injected(
    forecast_table: Dict[Any, Dict[str, float]],
    observations: List[Observation],
    cfg: MainRunConfig,
    *,
    ablation_id: str,
    ablation_name: str,
    label: str,
) -> List[Dict[str, Any]]:
    params = MCDMEMAParams(
        INITIAL_BALANCE=cfg.initial_balance,
        DEFAULT_INITIAL_ENTITY="AAVE",
    )
    try:
        strat = _ForecastInjectedMCDM(debug=False, params=params)
        strat.forecast_table = forecast_table
        result = strat.run(observations)
        eq = _portfolio_equity(result.to_dataframe())
        if eq is not None:
            try:
                eq.index = [o.timestamp for o in observations][: len(eq)]
            except Exception:                              # noqa: BLE001
                pass
        metrics = _compute_headline_metrics(eq, result.to_dataframe(), cfg)
        return [_ok_row(ablation_id, ablation_name,
                        "ForecastInjectedMCDM", metrics)]
    except Exception as exc:                               # noqa: BLE001
        logger.error(f"[{label}] runtime error: {exc}")
        return [_nan_row(ablation_id, ablation_name,
                         "ForecastInjectedMCDM", str(exc))]


# ---------------------------------------------------------------------------
# Plan §9.5 regime-conditional + §9.4 forecast-quality rows.
#
# These are NOT numbered ablations; they are extra deliverable rows appended
# to ablations.csv so the whitepaper's regime / forecast-quality macros
# resolve from the same artifact (run_ablations writes ablations.csv last in
# the `make finish` order, so emitting here — not in run_main — survives).
# Regime split = the two quarters of the 2026 test window (Q1 vs Q2), per
# CLAUDE.md "Project regime structure". Forecast quality = OOS R² /
# direction-accuracy / weighted-Pearson / quantile-90 loss of the ONNX
# forecaster vs the realized rate h steps ahead (same r_hat/r_spot log that
# run_main._forecast_hit_rate consumes).
# ---------------------------------------------------------------------------

# 2026 test-window quarter boundaries (UTC). Q1 = Jan–Mar, Q2 = Apr (test
# window ends 2026-04-30 per observations_builder.TEST_END).
_Q1_END = datetime(2026, 3, 31, 23, 59, 59)
_FORECAST_QUALITY_COLS = ["oos_r2", "dir_acc", "w_pearson", "q90_loss"]


def _regime_row(ablation_id: str, metrics: Optional[Dict[str, float]],
                err: Optional[str]) -> Dict[str, Any]:
    """A regime row reuses the OK/NaN row schema (net_apy + sharpe_annual)."""
    if metrics is None:
        return _nan_row(ablation_id, f"regime[{ablation_id}]",
                        "regime_split", err or "no observations in quarter")
    return _ok_row(ablation_id, f"regime[{ablation_id}]",
                   "regime_split", metrics)


def _quarter_obs(observations: List[Observation], q: str) -> List[Observation]:
    out: List[Observation] = []
    for o in observations:
        ts = o.timestamp
        ts = ts.replace(tzinfo=None) if ts.tzinfo is not None else ts
        in_q1 = ts <= _Q1_END
        if (q == "q1" and in_q1) or (q == "q2" and not in_q1):
            out.append(o)
    return out


def _regime_rows(test_obs: List[Observation],
                 cfg: MainRunConfig) -> List[Dict[str, Any]]:
    """Run PredictiveMCDM + MCDM-EMA on each test quarter; emit 4 rows."""
    rows: List[Dict[str, Any]] = []
    have_pred = _HAS_PREDICTIVE and ONNX_PATH.exists()
    for q in ("q1", "q2"):
        sub = _quarter_obs(test_obs, q)
        # EMA leg (always available)
        if len(sub) >= 2:
            ema_params = MCDMEMAParams(
                INITIAL_BALANCE=cfg.initial_balance,
                DEFAULT_INITIAL_ENTITY="AAVE",
            )
            m_ema, _eq, e_ema = _safe_run(MCDMEMAStrategy, ema_params, sub,
                                          f"regime/{q}/ema", cfg)
        else:
            m_ema, e_ema = None, f"only {len(sub)} obs in 2026 {q.upper()}"
        rows.append(_regime_row(f"regime_{q}_ema", m_ema, e_ema))

        # Predictive leg (NaN row if no ONNX — formatter renders n/a)
        if have_pred and len(sub) >= 2:
            p_params = PredictiveMCDMParams(
                INITIAL_BALANCE=cfg.initial_balance,
                DEFAULT_INITIAL_ENTITY="AAVE",
            )
            m_pred, _eq2, e_pred = _safe_run(PredictiveMCDMStrategy, p_params,
                                             sub, f"regime/{q}/pred", cfg)
        else:
            m_pred = None
            e_pred = ("no ONNX" if not have_pred
                      else f"only {len(sub)} obs in 2026 {q.upper()}")
        rows.append(_regime_row(f"regime_{q}_pred", m_pred, e_pred))
    return rows


def _np_weighted_pearson(y_pred: np.ndarray, y_true: np.ndarray,
                         eps: float = 1e-8) -> float:
    """NumPy port of forecaster.losses.weighted_pearson (torch-free here:
    run_ablations uses `from __future__ import annotations` and must not
    import torch — see CLAUDE.md hard constraint 6)."""
    w = np.abs(y_true) + eps
    w = w / w.sum()
    mp = float((w * y_pred).sum())
    mt = float((w * y_true).sum())
    dp = y_pred - mp
    dt = y_true - mt
    cov = float((w * dp * dt).sum())
    vp = max(float((w * dp ** 2).sum()), eps)
    vt = max(float((w * dt ** 2).sum()), eps)
    return cov / (np.sqrt(vp) * np.sqrt(vt))


def _np_quantile_loss(y_pred: np.ndarray, y_true: np.ndarray,
                      q: float = 0.9) -> float:
    """NumPy port of forecaster.losses.quantile_loss (pinball loss)."""
    e = y_true - y_pred
    return float(np.maximum(q * e, (q - 1.0) * e).mean())


def _forecast_quality_row(test_obs: List[Observation],
                          cfg: MainRunConfig) -> Dict[str, Any]:
    """Score the ONNX forecaster vs realized rate h steps ahead (plan §9.4).

    Replays PredictiveMCDM once to harvest its (r_hat, r_spot) history, then
    aligns each forecast to the realized annualised rate `horizon` steps
    later. Metrics pooled across both protocols: OOS R² (vs spot-persistence
    baseline), directional accuracy, weighted Pearson, quantile-90 loss.
    """
    row = _nan_row("forecast_quality", "forecast_quality",
                   "PredictiveMCDM", "no ONNX / insufficient forecasts")
    for c in _FORECAST_QUALITY_COLS:
        row[c] = float("nan")

    if not (_HAS_PREDICTIVE and ONNX_PATH.exists()) or len(test_obs) < 24:
        return row

    horizon = cfg.forecast_horizon_h
    try:
        params = PredictiveMCDMParams(
            INITIAL_BALANCE=cfg.initial_balance,
            DEFAULT_INITIAL_ENTITY="AAVE",
        )
        strat, _res, _eq = _run_one(PredictiveMCDMStrategy, params, test_obs,
                                    "forecast_quality/replay")
    except Exception as exc:                                # noqa: BLE001
        row["status"] = f"SKIPPED:forecast replay failed: {exc}"
        return row

    history = getattr(strat, "_forecast_history", None) or []
    ts_to_idx = {o.timestamp: i for i, o in enumerate(test_obs)}
    y_pred: List[float] = []
    y_true: List[float] = []
    y_spot: List[float] = []
    for entry in history:
        ts = entry.get("timestamp")
        i = ts_to_idx.get(ts)
        if i is None:
            continue
        j = i + horizon
        if j >= len(test_obs):
            continue
        fut = test_obs[j]
        for ent in ("AAVE", "COMPOUND"):
            pair = entry.get(ent)
            if pair is None or ent not in fut.states:
                continue
            r_hat, r_spot = pair
            r_future = float(fut.states[ent].lending_rate) * 365 * 24
            y_pred.append(float(r_hat))
            y_true.append(r_future)
            y_spot.append(float(r_spot))

    if len(y_pred) < 5:
        row["status"] = f"SKIPPED:only {len(y_pred)} aligned forecast points"
        return row

    yp = np.asarray(y_pred, dtype=float)
    yt = np.asarray(y_true, dtype=float)
    ys = np.asarray(y_spot, dtype=float)

    ss_res = float(np.sum((yt - yp) ** 2))
    # Baseline = spot persistence (r_hat == r_spot); honest "skill vs naive".
    ss_base = float(np.sum((yt - ys) ** 2))
    oos_r2 = 1.0 - ss_res / ss_base if ss_base > 0 else float("nan")
    dir_acc = float(np.mean(np.sign(yp - ys) == np.sign(yt - ys)))
    w_pearson = _np_weighted_pearson(yp, yt)
    q90 = _np_quantile_loss(yp, yt, q=0.9)

    row["status"] = "OK"
    row["n_rebalances"] = len(yp)
    row["oos_r2"] = oos_r2
    row["dir_acc"] = dir_acc
    row["w_pearson"] = w_pearson
    row["q90_loss"] = q90
    return row


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------

ABLATIONS: Dict[int, Tuple[str, Callable]] = {
    1:  ("no_forecast_ema",        ablation_1_no_forecast_ema),
    2:  ("naive_forecast",         ablation_2_naive_forecast),
    3:  ("cir_forecast",           ablation_3_cir_forecast),
    4:  ("markov_switching",       ablation_4_markov),
    5:  ("catboost",               ablation_5_catboost),
    6:  ("single_branch_da_gru",   ablation_6_single_branch),
    7:  ("dual_branch_no_kink",    ablation_7_no_kink),
    8:  ("ranking_loss_only",      ablation_8_ranking_only),
    9:  ("equal_vs_tuned",         ablation_9_equal_weights),
    10: ("single_protocol",        ablation_10_single_protocol),
    11: ("greedy_vs_mcdm",         ablation_11_greedy_vs_mcdm),
    12: ("zero_vs_realistic_gas",  ablation_12_gas_sweep),
    13: ("sliding_window",         ablation_13_sliding_window),
    14: ("ood_usdc_depeg",         ablation_14_ood_depeg),
    15: ("horizon_sweep",          ablation_15_horizon_sweep),
    16: ("hysteresis_sweep",       ablation_16_hysteresis_sweep),
}


@dataclass
class _RunContext:
    """Bundle of inputs threaded through every ablation invocation."""
    cfg: MainRunConfig
    test_obs: List[Observation]
    fit_obs: List[Observation]              # train + val for forecaster fits
    save_figure: bool


def run_all(
    cfg: MainRunConfig,
    synthetic: bool = False,
    only: Optional[int] = None,
    save_figure: bool = False,
) -> pd.DataFrame:
    logger.info(f"[load] synthetic={synthetic}")
    _, (train_obs, val_obs, test_obs) = build_all(synthetic=synthetic)
    logger.info(f"[load] train={len(train_obs)}  val={len(val_obs)}  "
                f"test={len(test_obs)}")

    ctx = _RunContext(
        cfg=cfg,
        test_obs=test_obs,
        fit_obs=train_obs + val_obs,
        save_figure=save_figure,
    )

    if only is None:
        targets = sorted(ABLATIONS.keys())
    elif only not in ABLATIONS:
        raise SystemExit(f"--only {only} not in {sorted(ABLATIONS.keys())}")
    else:
        targets = [only]

    rows: List[Dict[str, Any]] = []
    equity_curves: Dict[str, pd.Series] = {}
    abl1_eq: Optional[pd.Series] = None

    for n in targets:
        name, fn = ABLATIONS[n]
        logger.info(f"--- ablation {n}: {name} ---")
        try:
            result = fn(test_obs, cfg, fit_obs=ctx.fit_obs)
        except Exception as exc:                            # noqa: BLE001
            logger.error(f"ablation {n} crashed: {exc}")
            rows.append(_nan_row(str(n), name, "n/a", f"crash:{exc}"))
            continue

        # Ablation 1 may return (rows, equity); all others return rows.
        if n == 1 and isinstance(result, tuple):
            sub_rows, abl1_eq = result
            rows.extend(sub_rows)
        else:
            rows.extend(result)

    # Plan §9.5 regime-conditional + §9.4 forecast-quality deliverable rows.
    # Only on a full run (a single --only N is a numbered-ablation probe).
    if only is None:
        logger.info("--- regime-conditional rows (2026 Q1 / Q2) ---")
        rows.extend(_regime_rows(test_obs, cfg))
        logger.info("--- forecast-quality row (OOS R2 / dir-acc / wP / q90) ---")
        rows.append(_forecast_quality_row(test_obs, cfg))

    df = pd.DataFrame(rows)
    # Force column order: required cols first, debug cols, then the
    # forecast-quality-only columns (NaN for every other row).
    cols = [c for c in _ALL_COLS + _FORECAST_QUALITY_COLS if c in df.columns]
    df = df[cols] if cols else df

    _emit_outputs(df, abl1_eq, test_obs, cfg, save_figure=save_figure)
    return df


def _emit_outputs(df: pd.DataFrame,
                  abl1_eq: Optional[pd.Series],
                  test_obs: List[Observation],
                  cfg: MainRunConfig,
                  *,
                  save_figure: bool) -> None:
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    csv_path = TABLES_DIR / "ablations.csv"
    df.to_csv(csv_path, index=False)
    logger.info(f"[saved] {csv_path}  shape={df.shape}")

    _print_markdown_summary(df)

    # Headline figure: ablation 1 vs main predictive equity overlay.
    if abl1_eq is None:
        return
    try:
        import matplotlib                                  # noqa: WPS433
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt                    # noqa: WPS433

        main_eq: Optional[pd.Series] = None
        if _HAS_PREDICTIVE and ONNX_PATH.exists():
            try:
                p = PredictiveMCDMParams(
                    INITIAL_BALANCE=cfg.initial_balance,
                    DEFAULT_INITIAL_ENTITY="AAVE",
                )
                _strat, _res, main_eq = _run_one(
                    PredictiveMCDMStrategy, p, test_obs,
                    "ablations/main-overlay",
                )
            except Exception as exc:                       # noqa: BLE001
                logger.warning(f"[plot] main overlay disabled: {exc}")
        elif not ONNX_PATH.exists():
            logger.warning(f"[plot] ONNX missing ({ONNX_PATH}); plotting "
                           f"Ablation 1 alone")

        fig, ax = plt.subplots(figsize=(9, 5))
        ax.plot(abl1_eq.index, abl1_eq.values,
                label="Ablation 1 (MCDM-EMA, no forecast)")
        if main_eq is not None:
            ax.plot(main_eq.index, main_eq.values,
                    label="Main (PredictiveMCDM)")
        ax.set_title("Ablation 1 vs Main -- equity curves (test window)")
        ax.set_xlabel("time")
        ax.set_ylabel("portfolio value (USD)")
        ax.legend(loc="best")
        ax.grid(alpha=0.3)
        fig_path = FIGURES_DIR / "ablation_1_vs_main.png"
        fig.savefig(fig_path, dpi=110, bbox_inches="tight")
        plt.close(fig)
        logger.info(f"[saved] {fig_path}")

        # Per-ablation equity figures (Ablation 1 only for now; the
        # _safe_run pathway discards equity for #2..#15 to keep the runner
        # memory-light. To produce a per-ablation figure for any other run,
        # re-execute that ablation with the equity captured.)
        if save_figure:
            fig2, ax2 = plt.subplots(figsize=(9, 5))
            ax2.plot(abl1_eq.index, abl1_eq.values,
                     label="Ablation 1 (MCDM-EMA)")
            ax2.set_title("Ablation 1 -- equity (test window)")
            ax2.legend(loc="best")
            ax2.grid(alpha=0.3)
            f2 = FIGURES_DIR / "ablation_1_no_forecast_ema.png"
            fig2.savefig(f2, dpi=110, bbox_inches="tight")
            plt.close(fig2)
            logger.info(f"[saved] {f2}")
    except Exception as exc:                               # noqa: BLE001
        logger.warning(f"[plot] disabled: {exc}")


def _print_markdown_summary(df: pd.DataFrame) -> None:
    """Print the markdown table with Delta-vs-baseline-1 column."""
    print("\n### Ablations (test window 2026-01-01 .. 2026-04-30)\n")

    baseline_apy: Optional[float] = None
    if not df.empty and "ablation_id" in df.columns:
        mask = (df["ablation_id"] == "1") & (df["status"] == "OK")
        if mask.any():
            v = df.loc[mask, "net_apy"].iloc[0]
            if not pd.isna(v):
                baseline_apy = float(v)

    cols = ["ablation_id", "ablation_name", "status", "net_apy",
            "sharpe_annual", "max_drawdown", "delta_vs_abl1"]
    df_fmt = df.copy()
    df_fmt["delta_vs_abl1"] = df_fmt["net_apy"].apply(
        lambda v: float("nan") if (pd.isna(v) or baseline_apy is None)
        else float(v) - baseline_apy
    )
    for c in ("net_apy", "sharpe_annual", "max_drawdown", "delta_vs_abl1"):
        if c in df_fmt.columns:
            df_fmt[c] = df_fmt[c].apply(
                lambda v: "nan" if pd.isna(v) else f"{float(v):+.4f}"
            )

    print("| " + " | ".join(cols) + " |")
    print("|" + "|".join(["---"] * len(cols)) + "|")
    for _, r in df_fmt[cols].iterrows():
        print("| " + " | ".join(str(r[c]) for c in cols) + " |")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--synthetic", action="store_true",
                    help="run on synthetic joined panel (no API keys required)")
    ap.add_argument("--only", type=int, default=None,
                    help=f"run a single ablation N in {sorted(ABLATIONS.keys())}")
    ap.add_argument("--save-figure", action="store_true",
                    help="emit per-ablation equity-curve figures under results/figures/")
    args = ap.parse_args(argv)

    cfg = MainRunConfig()
    run_all(cfg, synthetic=args.synthetic, only=args.only,
            save_figure=args.save_figure)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
