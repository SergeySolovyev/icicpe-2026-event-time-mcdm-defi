"""Run all 15 ablations from PROJECT_2_PLAN.md §10.

Ablation matrix (plan §10):

    1.  No-forecast EMA baseline (Baseline C)            -- mandatory strawman
    2.  Naive last-observation forecast
    3.  CIR-calibrated forecast (Baseline D)
    4.  Markov-switching short-rate (skipped if not impl.)
    5.  CatBoost on hand-crafted features
    6.  Single-branch DA-GRU (skipped: needs separate ONNX export)
    7.  Dual-branch WITHOUT kink subtraction (skipped: needs alt ONNX)
    8.  Forecast with ranking-loss only (skipped: needs alt training run)
    9.  MCDM equal weights vs tuned
    10. Single-protocol benchmark (Aave-only, Compound-only)
    11. Greedy max-forecasted-APY vs TOPSIS-MCDM
    12. Zero-gas vs realistic-gas
    13. Sliding-window stability (DefaultPipeline window_size=14*24h)
    14. OOD test on USDC depeg week (Mar 2023) -- SKIPPED if no OOD data
    15. Forecast horizon sweep (3h, 6h, 12h, 24h)

Each ablation writes one or more rows to ``results/tables/ablations.csv``.
Ablations whose code dependencies are not yet ready produce a single
``[SKIPPED: <reason>]`` row with NaN metrics so the table shape is stable.

Headline figure: ``results/figures/ablation_1_vs_main.png`` (equity overlay
of Ablation 1 EMA-only vs the main predictive run).

Run::

    python -m backtest.run_ablations
    python -m backtest.run_ablations --synthetic
    python -m backtest.run_ablations --only 1
    python -m backtest.run_ablations --only 12
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "extras" / "fractal_pr_lending_allocation"))

from fractal.core.base import Observation  # noqa: E402

from backtest.observations_builder import build_all  # noqa: E402
from backtest.run_main import (  # noqa: E402
    MainRunConfig,
    _compute_metrics,
    _portfolio_equity,
    _run_one,
)
from strategies.baseline_apy_greedy import APYGreedyStrategy, APYGreedyParams  # noqa: E402
from strategies.baseline_mcdm_ema import MCDMEMAStrategy, MCDMEMAParams  # noqa: E402
from base_lending_allocation import BaseLendingAllocationParams  # noqa: E402

try:
    from strategies.predictive_mcdm import (  # noqa: E402
        PredictiveMCDMStrategy,
        PredictiveMCDMParams,
    )
    _HAS_PREDICTIVE = True
except Exception as _exc:                                # noqa: BLE001
    logger.warning(f"PredictiveMCDMStrategy import failed: {_exc}")
    PredictiveMCDMStrategy = None                        # type: ignore[assignment]
    PredictiveMCDMParams = None                          # type: ignore[assignment]
    _HAS_PREDICTIVE = False


RESULTS_DIR = ROOT / "results"
TABLES_DIR = RESULTS_DIR / "tables"
FIGURES_DIR = RESULTS_DIR / "figures"
ONNX_PATH = ROOT / "forecaster" / "trained_models" / "dual_branch_kink.onnx"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _nan_row(ablation: str, variant: str, reason: str) -> Dict[str, float]:
    """Return a NaN-valued metric row tagged as SKIPPED."""
    return {
        "ablation": ablation,
        "variant": variant,
        "status": f"SKIPPED: {reason}",
        "n_rebalances": 0,
        "total_return": float("nan"),
        "apy": float("nan"),
        "sharpe": float("nan"),
        "calmar": float("nan"),
        "max_dd": float("nan"),
        "vol_annual": float("nan"),
        "worst_day_return": float("nan"),
        "turnover": float("nan"),
        "gas_spent_usd": float("nan"),
        "gas_pct_of_pnl": float("nan"),
    }


def _ok_row(ablation: str, variant: str,
            metrics: Dict[str, float]) -> Dict[str, float]:
    return {
        "ablation": ablation,
        "variant": variant,
        "status": "OK",
        **metrics,
    }


def _safe_run(
    strategy_cls,
    params,
    observations: List[Observation],
    label: str,
    cfg: MainRunConfig,
) -> Tuple[Optional[Dict[str, float]], Optional[pd.Series], Optional[str]]:
    """Run a strategy, return (metrics_dict, equity_series, error_or_None)."""
    try:
        result, eq = _run_one(strategy_cls, params, observations, label)
        metrics = _compute_metrics(eq, result.to_dataframe(), cfg, observations)
        return metrics, eq, None
    except Exception as exc:                             # noqa: BLE001
        logger.error(f"[{label}] runtime error: {exc}")
        return None, None, str(exc)


# ---------------------------------------------------------------------------
# Ablation 1: No-forecast EMA baseline (Baseline C strawman)
# ---------------------------------------------------------------------------

def ablation_1_no_forecast_ema(observations: List[Observation],
                               cfg: MainRunConfig) -> Tuple[List[Dict[str, float]],
                                                            Optional[pd.Series]]:
    params = MCDMEMAParams(
        INITIAL_BALANCE=cfg.initial_balance,
        DEFAULT_INITIAL_ENTITY="AAVE",
    )
    metrics, eq, err = _safe_run(MCDMEMAStrategy, params, observations,
                                 "abl1/MCDM-EMA", cfg)
    if metrics is None:
        return [_nan_row("1_no_forecast_ema", "MCDMEMA", err or "runtime error")], None
    return [_ok_row("1_no_forecast_ema", "MCDMEMA", metrics)], eq


# ---------------------------------------------------------------------------
# Ablation 2: Naive last-observation forecast
#
# Use PredictiveMCDMParams but with the cached forecast disabled, which
# degrades to "annual = rate * 365*24" -- the desired "last-obs" behavior
# is identical to the warm-up fallback path inside PredictiveMCDMStrategy.
# We force this by pointing FORECAST_MODEL_PATH at a non-existent file so
# the lazy init silently fails and the cached forecast stays empty.
# ---------------------------------------------------------------------------

def ablation_2_naive_forecast(observations: List[Observation],
                              cfg: MainRunConfig) -> List[Dict[str, float]]:
    if not _HAS_PREDICTIVE:
        return [_nan_row("2_naive_forecast", "PredMCDM-naive", "predictive import failed")]

    params = PredictiveMCDMParams(
        INITIAL_BALANCE=cfg.initial_balance,
        DEFAULT_INITIAL_ENTITY="AAVE",
        FORECAST_MODEL_PATH="forecaster/trained_models/_no_such_file_.onnx",
    )
    metrics, _eq, err = _safe_run(PredictiveMCDMStrategy, params, observations,
                                  "abl2/naive", cfg)
    if metrics is None:
        return [_nan_row("2_naive_forecast", "PredMCDM-naive",
                         err or "runtime error")]
    return [_ok_row("2_naive_forecast", "PredMCDM-naive", metrics)]


# ---------------------------------------------------------------------------
# Ablation 3: CIR-calibrated forecast (Baseline D)
# ---------------------------------------------------------------------------

def ablation_3_cir_forecast(observations: List[Observation],
                            cfg: MainRunConfig) -> List[Dict[str, float]]:
    """Plan §10 #3. baseline_mcdm_cir.py is still a stub, so we mark SKIPPED.

    The CIR forecaster itself (forecaster/baseline_cir.py CIRForecaster)
    works, but the strategy wrapper that injects it into the MCDM pipeline
    is not yet implemented. Once strategies/baseline_mcdm_cir.py lands,
    swap in MCDMCIRStrategy here.
    """
    try:
        from strategies.baseline_mcdm_cir import (  # noqa: F401
            MCDMCIRStrategy, MCDMCIRParams,
        )
    except Exception as exc:                             # noqa: BLE001
        return [_nan_row("3_cir_forecast", "MCDMCIR",
                         f"baseline_mcdm_cir not implemented ({exc})")]
    params = MCDMCIRParams(  # type: ignore[name-defined]
        INITIAL_BALANCE=cfg.initial_balance,
        DEFAULT_INITIAL_ENTITY="AAVE",
    )
    metrics, _eq, err = _safe_run(MCDMCIRStrategy, params, observations,  # type: ignore[name-defined]
                                  "abl3/CIR", cfg)
    if metrics is None:
        return [_nan_row("3_cir_forecast", "MCDMCIR", err or "runtime error")]
    return [_ok_row("3_cir_forecast", "MCDMCIR", metrics)]


# ---------------------------------------------------------------------------
# Ablation 4: Markov-switching
# ---------------------------------------------------------------------------

def ablation_4_markov(observations: List[Observation],
                      cfg: MainRunConfig) -> List[Dict[str, float]]:
    try:
        from forecaster.baseline_markov import MarkovSwitchingForecaster  # noqa: F401
    except Exception as exc:                             # noqa: BLE001
        return [_nan_row("4_markov_switching", "MCDMMarkov",
                         f"baseline_markov not implemented ({exc})")]
    return [_nan_row("4_markov_switching", "MCDMMarkov",
                     "strategy wrapper for MarkovSwitchingForecaster not yet implemented")]


# ---------------------------------------------------------------------------
# Ablation 5: CatBoost
# ---------------------------------------------------------------------------

def ablation_5_catboost(observations: List[Observation],
                        cfg: MainRunConfig) -> List[Dict[str, float]]:
    try:
        from forecaster.baseline_catboost import CatBoostForecaster  # noqa: F401
    except Exception as exc:                             # noqa: BLE001
        return [_nan_row("5_catboost", "MCDMCatBoost",
                         f"CatBoostForecaster import failed ({exc})")]
    # The CatBoost-injecting strategy wrapper is not yet implemented;
    # producing the SKIPPED row keeps the CSV shape stable.
    return [_nan_row("5_catboost", "MCDMCatBoost",
                     "strategy wrapper for CatBoostForecaster not yet implemented")]


# ---------------------------------------------------------------------------
# Ablation 6: Single-branch DA-GRU (no CNN)
# ---------------------------------------------------------------------------

def ablation_6_single_branch(observations: List[Observation],
                             cfg: MainRunConfig) -> List[Dict[str, float]]:
    return [_nan_row("6_single_branch_da_gru", "PredMCDM-singleBranch",
                     "needs separate single-branch ONNX export")]


# ---------------------------------------------------------------------------
# Ablation 7: Dual-branch WITHOUT kink subtraction
# ---------------------------------------------------------------------------

def ablation_7_no_kink(observations: List[Observation],
                       cfg: MainRunConfig) -> List[Dict[str, float]]:
    return [_nan_row("7_dual_branch_no_kink", "PredMCDM-noKink",
                     "needs alternative training run with raw-rate branch A")]


# ---------------------------------------------------------------------------
# Ablation 8: Ranking-loss-only forecast
# ---------------------------------------------------------------------------

def ablation_8_ranking_only(observations: List[Observation],
                            cfg: MainRunConfig) -> List[Dict[str, float]]:
    return [_nan_row("8_ranking_loss_only", "PredMCDM-rankOnly",
                     "needs alternative training run with alpha=0,beta=1,gamma=0")]


# ---------------------------------------------------------------------------
# Ablation 9: MCDM equal weights vs tuned
# ---------------------------------------------------------------------------

def ablation_9_equal_weights(observations: List[Observation],
                             cfg: MainRunConfig) -> List[Dict[str, float]]:
    rows: List[Dict[str, float]] = []

    # Tuned weights (default constants)
    tuned = MCDMEMAParams(
        INITIAL_BALANCE=cfg.initial_balance,
        DEFAULT_INITIAL_ENTITY="AAVE",
    )
    metrics, _eq, err = _safe_run(MCDMEMAStrategy, tuned, observations,
                                  "abl9/tuned", cfg)
    if metrics is None:
        rows.append(_nan_row("9_equal_vs_tuned", "tuned", err or "runtime error"))
    else:
        rows.append(_ok_row("9_equal_vs_tuned", "tuned", metrics))

    # Equal weights = 0.25 across the 4 criteria
    equal = MCDMEMAParams(
        INITIAL_BALANCE=cfg.initial_balance,
        DEFAULT_INITIAL_ENTITY="AAVE",
        W_APY=0.25, W_RISK=0.25, W_COST=0.25, W_STAB=0.25,
    )
    metrics, _eq, err = _safe_run(MCDMEMAStrategy, equal, observations,
                                  "abl9/equal", cfg)
    if metrics is None:
        rows.append(_nan_row("9_equal_vs_tuned", "equal", err or "runtime error"))
    else:
        rows.append(_ok_row("9_equal_vs_tuned", "equal", metrics))
    return rows


# ---------------------------------------------------------------------------
# Ablation 10: Single-protocol benchmark
# ---------------------------------------------------------------------------

def _filter_states(observations: List[Observation],
                   keep: str) -> List[Observation]:
    """Return new observations keeping only the named entity.

    fractal-defi's strict-observations contract requires every registered
    entity to have a state; we pair this with a strategy that registers
    only the kept entity.
    """
    out: List[Observation] = []
    for obs in observations:
        if keep not in obs.states:
            continue
        out.append(Observation(
            timestamp=obs.timestamp,
            states={keep: obs.states[keep]},
        ))
    return out


def ablation_10_single_protocol(observations: List[Observation],
                                cfg: MainRunConfig) -> List[Dict[str, float]]:
    rows: List[Dict[str, float]] = []

    class _SinglePctyParams(MCDMEMAParams):
        pass

    for proto in ("AAVE", "COMPOUND"):
        class _SingleStrat(MCDMEMAStrategy):
            LENDING_ENTITY_NAMES = (proto,)

        sub = _filter_states(observations, proto)
        params = _SinglePctyParams(
            INITIAL_BALANCE=cfg.initial_balance,
            DEFAULT_INITIAL_ENTITY=proto,
        )
        metrics, _eq, err = _safe_run(_SingleStrat, params, sub,
                                      f"abl10/{proto}", cfg)
        if metrics is None:
            rows.append(_nan_row("10_single_protocol", proto,
                                 err or "runtime error"))
        else:
            rows.append(_ok_row("10_single_protocol", proto, metrics))
    return rows


# ---------------------------------------------------------------------------
# Ablation 11: Greedy-on-(spot-)APY vs TOPSIS-MCDM
#
# Plan asks "greedy max-forecasted-APY vs TOPSIS-MCDM". With no forecast
# injection point on APYGreedy, we run greedy-on-spot vs MCDM-EMA -- the
# in-pipeline analogue that compares argmax-on-rate to multi-criterion
# scoring under the same conditions. When a forecast-injected greedy
# exists, swap it in here.
# ---------------------------------------------------------------------------

def ablation_11_greedy_vs_mcdm(observations: List[Observation],
                               cfg: MainRunConfig) -> List[Dict[str, float]]:
    rows: List[Dict[str, float]] = []

    greedy = APYGreedyParams(
        INITIAL_BALANCE=cfg.initial_balance,
        DEFAULT_INITIAL_ENTITY="AAVE",
    )
    metrics, _eq, err = _safe_run(APYGreedyStrategy, greedy, observations,
                                  "abl11/greedy", cfg)
    if metrics is None:
        rows.append(_nan_row("11_greedy_vs_mcdm", "APYGreedy",
                             err or "runtime error"))
    else:
        rows.append(_ok_row("11_greedy_vs_mcdm", "APYGreedy", metrics))

    mcdm = MCDMEMAParams(
        INITIAL_BALANCE=cfg.initial_balance,
        DEFAULT_INITIAL_ENTITY="AAVE",
    )
    metrics, _eq, err = _safe_run(MCDMEMAStrategy, mcdm, observations,
                                  "abl11/mcdm", cfg)
    if metrics is None:
        rows.append(_nan_row("11_greedy_vs_mcdm", "MCDMEMA",
                             err or "runtime error"))
    else:
        rows.append(_ok_row("11_greedy_vs_mcdm", "MCDMEMA", metrics))
    return rows


# ---------------------------------------------------------------------------
# Ablation 12: Zero-gas vs realistic-gas
# ---------------------------------------------------------------------------

def ablation_12_gas_sweep(observations: List[Observation],
                          cfg: MainRunConfig) -> List[Dict[str, float]]:
    rows: List[Dict[str, float]] = []

    # Realistic: default GAS_GATE_BPS == 0 already, but we use a non-zero
    # gas_per_rebalance dollar cost in the metrics roll-up.
    realistic = MCDMEMAParams(
        INITIAL_BALANCE=cfg.initial_balance,
        DEFAULT_INITIAL_ENTITY="AAVE",
        GAS_GATE_BPS=0.0,
    )
    metrics, _eq, err = _safe_run(MCDMEMAStrategy, realistic, observations,
                                  "abl12/realistic_gas", cfg)
    if metrics is None:
        rows.append(_nan_row("12_zero_vs_realistic_gas", "realistic_gas",
                             err or "runtime error"))
    else:
        rows.append(_ok_row("12_zero_vs_realistic_gas", "realistic_gas", metrics))

    # Zero gas: zero out GAS_PER_REBALANCE so gas-cost roll-up is 0.
    zero_cfg = replace(cfg, gas_per_rebalance=0)
    metrics, _eq, err = _safe_run(MCDMEMAStrategy, realistic, observations,
                                  "abl12/zero_gas", zero_cfg)
    if metrics is None:
        rows.append(_nan_row("12_zero_vs_realistic_gas", "zero_gas",
                             err or "runtime error"))
    else:
        rows.append(_ok_row("12_zero_vs_realistic_gas", "zero_gas", metrics))
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


def ablation_13_sliding_window(observations: List[Observation],
                               cfg: MainRunConfig) -> List[Dict[str, float]]:
    window_hours = 14 * 24
    step_hours = 7 * 24
    windows = _sliding_windows(observations, window_hours, step_hours)
    if not windows:
        return [_nan_row("13_sliding_window", "MCDMEMA",
                         f"test window < {window_hours} hours")]
    aprs: List[float] = []
    sharpes: List[float] = []
    for w_idx, w in enumerate(windows):
        params = MCDMEMAParams(
            INITIAL_BALANCE=cfg.initial_balance,
            DEFAULT_INITIAL_ENTITY="AAVE",
        )
        metrics, _eq, err = _safe_run(MCDMEMAStrategy, params, w,
                                      f"abl13/w{w_idx}", cfg)
        if metrics is None:
            continue
        if not pd.isna(metrics["apy"]):
            aprs.append(metrics["apy"])
        if not pd.isna(metrics["sharpe"]):
            sharpes.append(metrics["sharpe"])

    if not aprs:
        return [_nan_row("13_sliding_window", "MCDMEMA",
                         "no windows produced finite metrics")]

    arr = np.asarray(aprs, dtype=float)
    sh = np.asarray(sharpes, dtype=float)
    q05 = float(np.quantile(arr, 0.05))
    q95 = float(np.quantile(arr, 0.95))
    cvar05 = float(arr[arr <= q05].mean()) if (arr <= q05).any() else q05

    summary = _nan_row("13_sliding_window", "MCDMEMA", "OK")
    summary["status"] = "OK"
    summary["apy"] = float(arr.mean())
    summary["sharpe"] = float(sh.mean()) if len(sh) else float("nan")
    summary["max_dd"] = q05
    summary["worst_day_return"] = cvar05
    summary["vol_annual"] = q95
    summary["n_rebalances"] = len(windows)
    return [summary]


# ---------------------------------------------------------------------------
# Ablation 14: OOD test on USDC depeg week (Mar 2023)
# ---------------------------------------------------------------------------

def ablation_14_ood_depeg(observations: List[Observation],
                          cfg: MainRunConfig) -> List[Dict[str, float]]:
    return [_nan_row("14_ood_usdc_depeg", "PredMCDM",
                     "Mar 2023 OOD dataset not provisioned in this repo")]


# ---------------------------------------------------------------------------
# Ablation 15: Forecast horizon sweep
# ---------------------------------------------------------------------------

def ablation_15_horizon_sweep(observations: List[Observation],
                              cfg: MainRunConfig) -> List[Dict[str, float]]:
    if not _HAS_PREDICTIVE:
        return [_nan_row("15_horizon_sweep", "PredMCDM",
                         "predictive import failed")]
    rows: List[Dict[str, float]] = []
    for h in (3, 6, 12, 24):
        params = PredictiveMCDMParams(
            INITIAL_BALANCE=cfg.initial_balance,
            DEFAULT_INITIAL_ENTITY="AAVE",
            FORECAST_HORIZON=h,
        )
        metrics, _eq, err = _safe_run(PredictiveMCDMStrategy, params,
                                      observations, f"abl15/h={h}", cfg)
        if metrics is None:
            rows.append(_nan_row("15_horizon_sweep", f"h={h}",
                                 err or "runtime error"))
        else:
            rows.append(_ok_row("15_horizon_sweep", f"h={h}", metrics))
    return rows


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------

ABLATIONS: Dict[int, Tuple[str, Callable]] = {
    1:  ("1_no_forecast_ema",        ablation_1_no_forecast_ema),
    2:  ("2_naive_forecast",         ablation_2_naive_forecast),
    3:  ("3_cir_forecast",           ablation_3_cir_forecast),
    4:  ("4_markov_switching",       ablation_4_markov),
    5:  ("5_catboost",               ablation_5_catboost),
    6:  ("6_single_branch_da_gru",   ablation_6_single_branch),
    7:  ("7_dual_branch_no_kink",    ablation_7_no_kink),
    8:  ("8_ranking_loss_only",      ablation_8_ranking_only),
    9:  ("9_equal_vs_tuned",         ablation_9_equal_weights),
    10: ("10_single_protocol",       ablation_10_single_protocol),
    11: ("11_greedy_vs_mcdm",        ablation_11_greedy_vs_mcdm),
    12: ("12_zero_vs_realistic_gas", ablation_12_gas_sweep),
    13: ("13_sliding_window",        ablation_13_sliding_window),
    14: ("14_ood_usdc_depeg",        ablation_14_ood_depeg),
    15: ("15_horizon_sweep",         ablation_15_horizon_sweep),
}


def run_all(cfg: MainRunConfig, synthetic: bool = False,
            only: Optional[int] = None) -> pd.DataFrame:
    logger.info(f"[load] synthetic={synthetic}")
    _, (_tr, _val, test_obs) = build_all(synthetic=synthetic)
    logger.info(f"[load] test={len(test_obs)} observations")

    rows: List[Dict[str, float]] = []
    abl1_eq: Optional[pd.Series] = None
    if only is None:
        targets = sorted(ABLATIONS.keys())
    else:
        if only not in ABLATIONS:
            raise SystemExit(f"--only {only} not in {sorted(ABLATIONS.keys())}")
        targets = [only]

    for n in targets:
        name, fn = ABLATIONS[n]
        logger.info(f"--- running ablation {n}: {name} ---")
        try:
            result = fn(test_obs, cfg)
        except Exception as exc:                         # noqa: BLE001
            logger.error(f"ablation {n} crashed: {exc}")
            rows.append(_nan_row(name, "n/a", f"crash: {exc}"))
            continue
        # Ablation 1 returns (rows, equity_series) -- everything else returns rows.
        if n == 1 and isinstance(result, tuple):
            sub_rows, abl1_eq = result
            rows.extend(sub_rows)
        else:
            rows.extend(result)

    df = pd.DataFrame(rows)
    _emit_outputs(df, abl1_eq, test_obs, cfg)
    return df


def _emit_outputs(df: pd.DataFrame,
                  abl1_eq: Optional[pd.Series],
                  test_obs: List[Observation],
                  cfg: MainRunConfig) -> None:
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    csv_path = TABLES_DIR / "ablations.csv"
    df.to_csv(csv_path, index=False)
    logger.info(f"[saved] {csv_path}")

    # Markdown table.
    print("\n### Ablations (test window 2026-01-01 .. 2026-04-30)\n")
    cols = ["ablation", "variant", "status", "n_rebalances",
            "total_return", "apy", "sharpe", "max_dd", "gas_spent_usd"]
    df_fmt = df.copy()
    for c in ("total_return", "apy", "sharpe", "max_dd", "gas_spent_usd"):
        if c in df_fmt.columns:
            df_fmt[c] = df_fmt[c].apply(
                lambda v: "nan" if pd.isna(v) else f"{float(v):.4f}"
            )
    cols = [c for c in cols if c in df_fmt.columns]
    print("| " + " | ".join(cols) + " |")
    print("|" + "|".join(["---"] * len(cols)) + "|")
    for _, r in df_fmt[cols].iterrows():
        print("| " + " | ".join(str(r[c]) for c in cols) + " |")

    # Headline figure: ablation 1 vs main predictive equity.
    if abl1_eq is None:
        return
    try:
        import matplotlib                                # noqa: WPS433
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt                  # noqa: WPS433

        # Try to overlay the main predictive run if available; otherwise
        # we still emit the EMA curve on its own.
        main_eq: Optional[pd.Series] = None
        if _HAS_PREDICTIVE and ONNX_PATH.exists():
            try:
                p = PredictiveMCDMParams(
                    INITIAL_BALANCE=cfg.initial_balance,
                    DEFAULT_INITIAL_ENTITY="AAVE",
                )
                res, eq = _run_one(PredictiveMCDMStrategy, p, test_obs,
                                   "ablations/main-overlay")
                main_eq = eq
            except Exception as exc:                     # noqa: BLE001
                logger.warning(f"[plot] main overlay disabled: {exc}")

        fig, ax = plt.subplots(figsize=(9, 5))
        ax.plot(abl1_eq.index, abl1_eq.values, label="Ablation 1 (MCDM-EMA)")
        if main_eq is not None:
            ax.plot(main_eq.index, main_eq.values, label="Main (PredictiveMCDM)")
        ax.set_title("Ablation 1 vs Main -- equity curves (test window)")
        ax.set_xlabel("time")
        ax.set_ylabel("portfolio value (USD)")
        ax.legend(loc="best")
        ax.grid(alpha=0.3)
        fig_path = FIGURES_DIR / "ablation_1_vs_main.png"
        fig.savefig(fig_path, dpi=110, bbox_inches="tight")
        plt.close(fig)
        logger.info(f"[saved] {fig_path}")
    except Exception as exc:                             # noqa: BLE001
        logger.warning(f"[plot] disabled: {exc}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--synthetic", action="store_true",
                    help="run on synthetic joined panel (no API keys required)")
    ap.add_argument("--only", type=int, default=None,
                    help=f"run a single ablation N in {sorted(ABLATIONS.keys())}")
    args = ap.parse_args(argv)

    cfg = MainRunConfig()
    run_all(cfg, synthetic=args.synthetic, only=args.only)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
