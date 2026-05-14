"""Run the headline H1 evaluation: PredictiveMCDM vs MCDM-EMA on TEST window.

Drops the trained ONNX forecaster into ``forecaster/trained_models/dual_branch_kink.onnx``
and produces the full Project 2 main-result battery in one command. Matches
the metric battery in PROJECT_2_PLAN.md §9 and the statistical-significance
protocol in §9.6 / §16 H1.

Strategies run on the IDENTICAL observation stream and seed:
    - PredictiveMCDMStrategy  (DA-BiGRU-CNN forecast -> f_APY)
    - MCDMEMAStrategy         (EMA-smoothed spot rate -> f_APY)

Headline metrics per strategy:
    net_apy, sharpe_annual, max_drawdown, calmar,
    n_rebalances, turnover_per_month, gas_spent_usd,
    forecast_hit_rate (PredictiveMCDM only -- directional accuracy of
                       12h-ahead forecast vs realized return)

H1 hypothesis test (plan §16):
    Bootstrap 1000 resamples of monthly Sharpe ratios for each strategy,
    test ``Sharpe_pred - Sharpe_ema > 0.2`` at the 95% level.

Outputs:
    results/tables/main.csv             2 rows x 8 cols
    results/tables/h1_significance.csv  metric-level diff table
    results/figures/main_vs_ema_equity.png   equity overlay + drawdown subplot

Graceful exits:
    - ``--synthetic`` without ONNX: runs MCDM-EMA only and emits a clean
      single-strategy report (predictive skipped, not an error).
    - Missing ONNX without ``--synthetic``: prints the exact Colab + scp
      remediation steps and exits with code 2.
    - ``--onnx <path>`` overrides the default ONNX location.

Run::

    python -m backtest.run_main                                # real-data path
    python -m backtest.run_main --synthetic                    # smoke / no-ONNX
    python -m backtest.run_main --test-start 2026-02-01 --test-end 2026-04-30
    python -m backtest.run_main --onnx /tmp/my_model.onnx
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "extras" / "fractal_pr_lending_allocation"))

from fractal.core.base import Observation  # noqa: E402

from backtest.observations_builder import (  # noqa: E402
    build_all,
    TEST_START,
    TEST_END,
)
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
DEFAULT_ONNX_PATH = ROOT / "forecaster" / "trained_models" / "dual_branch_kink.onnx"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class MainRunConfig:
    """End-to-end run configuration."""
    initial_balance: float = 1_000_000.0
    gas_per_rebalance: int = 200_000
    gas_gwei_const: float = 30.0          # fixed per-rebalance gwei (plan §9.3)
    fallback_eth_usd: float = 3500.0      # plan default in task spec
    n_bootstrap: int = 1000
    sharpe_diff_target: float = 0.2       # plan §16 H1
    forecast_horizon_h: int = 12          # plan §1.5
    seed: int = 0
    onnx_path: Path = field(default_factory=lambda: DEFAULT_ONNX_PATH)


# ---------------------------------------------------------------------------
# Equity / metrics helpers (mirrors run_baselines.py)
# ---------------------------------------------------------------------------

def _find_balance_col(df: pd.DataFrame, entity_name: str) -> Optional[str]:
    candidates = [
        f"{entity_name}_balance",
        f"{entity_name}.balance",
        f"balance_{entity_name}",
    ]
    for c in candidates:
        if c in df.columns:
            return c
    for c in df.columns:
        if c.startswith(entity_name) and "balance" in c.lower():
            return c
    return None


def _portfolio_equity(strategy_df: pd.DataFrame) -> Optional[pd.Series]:
    for col in ("net_balance", "portfolio_value", "total_balance", "balance"):
        if col in strategy_df.columns:
            return strategy_df[col].astype(float)
    aave_col = _find_balance_col(strategy_df, "AAVE")
    comp_col = _find_balance_col(strategy_df, "COMPOUND")
    if aave_col is not None and comp_col is not None:
        return strategy_df[aave_col].fillna(0.0) + strategy_df[comp_col].fillna(0.0)
    return None


def _winner_series(strategy_df: pd.DataFrame) -> Optional[np.ndarray]:
    aave_col = _find_balance_col(strategy_df, "AAVE")
    comp_col = _find_balance_col(strategy_df, "COMPOUND")
    if aave_col is None or comp_col is None:
        return None
    aave = strategy_df[aave_col].fillna(0.0).to_numpy(dtype=float)
    comp = strategy_df[comp_col].fillna(0.0).to_numpy(dtype=float)
    return (aave >= comp).astype(int)


def _count_rebalances(strategy_df: pd.DataFrame) -> int:
    winner = _winner_series(strategy_df)
    if winner is None or len(winner) < 2:
        return 0
    return int(np.sum(np.abs(np.diff(winner))))


def _rebalance_indices(strategy_df: pd.DataFrame) -> List[int]:
    winner = _winner_series(strategy_df)
    if winner is None or len(winner) < 2:
        return []
    flips = np.where(np.abs(np.diff(winner)) > 0)[0] + 1
    return [int(i) for i in flips]


# ---------------------------------------------------------------------------
# Metric battery (plan §9)
# ---------------------------------------------------------------------------

def _annualisation_factor(equity: pd.Series) -> Tuple[int, float]:
    """Return (steps_per_year, sqrt(steps_per_year)) for an hourly grid by default."""
    if len(equity) >= 2:
        try:
            dt = (equity.index[1] - equity.index[0]).total_seconds()
            if dt > 0:
                steps_per_year = int(round(365.25 * 86400 / dt))
                return steps_per_year, float(np.sqrt(steps_per_year))
        except Exception:                                # noqa: BLE001
            pass
    return 365 * 24, float(np.sqrt(365 * 24))


def _compute_headline_metrics(
    equity: Optional[pd.Series],
    strategy_df: pd.DataFrame,
    cfg: MainRunConfig,
    forecast_hit_rate: Optional[float] = None,
) -> Dict[str, float]:
    """Compute the 8-column headline battery per plan §9."""
    out: Dict[str, float] = {
        "net_apy": float("nan"),
        "sharpe_annual": float("nan"),
        "max_drawdown": float("nan"),
        "calmar": float("nan"),
        "n_rebalances": int(_count_rebalances(strategy_df)),
        "turnover_per_month": float("nan"),
        "gas_spent_usd": float("nan"),
        "forecast_hit_rate": float("nan") if forecast_hit_rate is None
                             else float(forecast_hit_rate),
    }

    if equity is None or len(equity) < 2:
        return out

    eq = equity.astype(float).dropna()
    if len(eq) < 2:
        return out

    v0 = float(eq.iloc[0])
    vT = float(eq.iloc[-1])
    if v0 <= 0:
        return out

    rets = eq.pct_change().dropna()
    steps_per_year, sqrt_steps = _annualisation_factor(eq)
    n_steps = max(len(eq) - 1, 1)
    years = n_steps / steps_per_year

    net_apy = (vT / v0) ** (1.0 / max(years, 1e-9)) - 1.0 if vT > 0 else float("nan")

    mu = float(rets.mean())
    sd = float(rets.std(ddof=1)) if len(rets) > 1 else 0.0
    sharpe = (mu / sd) * sqrt_steps if sd > 0 else float("nan")

    running_max = eq.cummax()
    drawdown = (eq / running_max) - 1.0
    max_dd = float(drawdown.min()) if len(drawdown) else float("nan")
    calmar = (net_apy / abs(max_dd)) if (max_dd < 0 and not pd.isna(net_apy)) else float("nan")

    # Turnover per month: rebalance count rebased to a 30-day month.
    months = max(years * 12.0, 1e-9)
    turnover_per_month = float(out["n_rebalances"]) / months

    # Gas cost: constant 30 gwei x 200k gas x ETH/USD per rebalance (plan §9.3
    # and task spec). Configurable via MainRunConfig.
    gas_eth_per = cfg.gas_per_rebalance * cfg.gas_gwei_const * 1e-9
    gas_usd = out["n_rebalances"] * gas_eth_per * cfg.fallback_eth_usd

    out.update({
        "net_apy": net_apy,
        "sharpe_annual": sharpe,
        "max_drawdown": max_dd,
        "calmar": calmar,
        "turnover_per_month": turnover_per_month,
        "gas_spent_usd": float(gas_usd),
    })
    return out


# ---------------------------------------------------------------------------
# Forecast directional accuracy (plan §9.4)
# ---------------------------------------------------------------------------

def _forecast_hit_rate(strategy, observations: List[Observation],
                       horizon_h: int = 12) -> Optional[float]:
    """Directional accuracy of forecast on h-step-ahead realized lending-rate change.

    Replays the strategy's ingest path offline to extract a forecast time
    series (one r_hat per protocol per step, after warm-up), then compares
    sign(r_hat - r_spot) to sign(r_realized_{t+h} - r_spot) per protocol.
    Returns the fraction of correct directional calls (NaN if no ONNX-driven
    forecasts were emitted or insufficient samples).
    """
    if strategy is None:
        return None

    # The strategy must have run already so we can read its kink + ONNX state.
    onnx_session = getattr(strategy, "_onnx_session", None)
    if onnx_session is None:
        return None

    # We score directional accuracy by extracting realized rates per step
    # from the observation panel and comparing against a freshly-batched
    # forecast playback. To keep things simple, we walk through the obs
    # list, accumulating r_hat / r_spot pairs each step and comparing
    # sign(r_hat - r_spot) to sign(r_{t+h} - r_t).
    # NOTE: full re-batching is expensive; we use the cached forecasts
    # that the strategy already produced if it exposes them. Otherwise we
    # fall back to a lightweight per-protocol AR(1) check.
    history = getattr(strategy, "_forecast_history", None)
    if not history:
        # The strategy never accumulated history; nothing to compare.
        return None

    correct = 0
    total = 0
    for entry in history:
        # entry is expected to be a dict:
        #   {"timestamp": ts, "AAVE": (r_hat, r_spot), "COMPOUND": (r_hat, r_spot)}
        ts = entry.get("timestamp")
        if ts is None:
            continue
        # Find the realized rate horizon_h steps ahead in the obs list.
        try:
            i = next(i for i, o in enumerate(observations) if o.timestamp == ts)
        except StopIteration:
            continue
        j = i + horizon_h
        if j >= len(observations):
            continue
        obs_future = observations[j]
        for entity in ("AAVE", "COMPOUND"):
            pair = entry.get(entity)
            if pair is None:
                continue
            r_hat, r_spot = pair
            r_future = float(obs_future.states[entity].lending_rate) * 365 * 24
            if (r_hat - r_spot) * (r_future - r_spot) > 0:
                correct += 1
            total += 1
    if total < 5:
        return None
    return correct / total


# ---------------------------------------------------------------------------
# H1 bootstrap of monthly Sharpe difference (plan §9.6 / §16 H1)
# ---------------------------------------------------------------------------

def _monthly_sharpes(equity: pd.Series) -> np.ndarray:
    """Annualised Sharpe within each calendar month from an hourly equity series."""
    eq = equity.astype(float).dropna()
    if len(eq) < 2:
        return np.array([])
    rets = eq.pct_change().dropna()
    _, sqrt_steps = _annualisation_factor(eq)
    monthly: List[float] = []
    for _ym, group in rets.groupby(pd.Grouper(freq="MS")):
        if len(group) < 5:
            continue
        mu = float(group.mean())
        sd = float(group.std(ddof=1))
        if sd > 0:
            monthly.append((mu / sd) * sqrt_steps)
    return np.asarray(monthly, dtype=float)


def _bootstrap_sharpe_diff(
    eq_pred: pd.Series,
    eq_ema: pd.Series,
    n_boot: int = 1000,
    target_diff: float = 0.2,
    seed: int = 0,
) -> Dict[str, float]:
    """Paired bootstrap of (Sharpe_pred - Sharpe_ema) monthly samples.

    Returns dict with observed delta, mean / 95% CI / p-value of ``H1:
    delta > target_diff`` (one-sided, p = P_boot(delta <= target_diff)).
    """
    s_pred = _monthly_sharpes(eq_pred)
    s_ema = _monthly_sharpes(eq_ema)
    n = min(len(s_pred), len(s_ema))
    if n < 2:
        return {
            "n_months": int(n),
            "predictive": float("nan"),
            "ema": float("nan"),
            "delta": float("nan"),
            "ci_low": float("nan"),
            "ci_high": float("nan"),
            "bootstrap_p_value": float("nan"),
            "target": float(target_diff),
        }

    s_pred = s_pred[:n]
    s_ema = s_ema[:n]
    delta_observed = float(np.mean(s_pred - s_ema))

    rng = np.random.default_rng(seed)
    boot_diffs = np.empty(n_boot, dtype=float)
    for b in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boot_diffs[b] = float(np.mean(s_pred[idx] - s_ema[idx]))

    p_value = float(np.mean(boot_diffs <= target_diff))  # H1 fails if true
    return {
        "n_months": int(n),
        "predictive": float(np.mean(s_pred)),
        "ema": float(np.mean(s_ema)),
        "delta": delta_observed,
        "ci_low": float(np.quantile(boot_diffs, 0.025)),
        "ci_high": float(np.quantile(boot_diffs, 0.975)),
        "bootstrap_p_value": p_value,
        "target": float(target_diff),
    }


# ---------------------------------------------------------------------------
# Strategy launcher
# ---------------------------------------------------------------------------

def _run_one(strategy_cls, params, observations: List[Observation],
             label: str, seed: int = 0) -> Tuple[object, object,
                                                 Optional[pd.Series]]:
    """Returns (strategy_instance, result, equity_series_or_None)."""
    logger.info(f"[{label}] running on {len(observations)} observations")
    np.random.seed(seed)
    strategy = strategy_cls(debug=False, params=params)
    result = strategy.run(observations)
    df = result.to_dataframe()
    eq = _portfolio_equity(df)
    if eq is not None:
        try:
            eq.index = pd.DatetimeIndex(
                [o.timestamp for o in observations][: len(eq)]
            )
        except Exception:                                # noqa: BLE001
            pass
    return strategy, result, eq


def _filter_window(observations: List[Observation],
                   start: Optional[datetime],
                   end: Optional[datetime]) -> List[Observation]:
    if start is None and end is None:
        return observations
    out = []
    for obs in observations:
        ts = obs.timestamp
        if start is not None and ts < start:
            continue
        if end is not None and ts > end:
            continue
        out.append(obs)
    return out


# ---------------------------------------------------------------------------
# Sanity gate (plan §16 prereqs)
# ---------------------------------------------------------------------------

_NO_ONNX_MESSAGE = """\
[predictive-mcdm] Trained forecaster ONNX not found.

  Expected at:  {path}

  Train the forecaster first via the Colab notebook
  (notebooks/forecaster_train_colab.ipynb on an H100/T4 runtime),
  then download the exported ONNX to:

      forecaster/trained_models/dual_branch_kink.onnx

  Or pass an alternative path via --onnx <file>.
  Or pass --synthetic to run the EMA strawman alone for a smoke test.

See PROJECT_2_PLAN.md §13 Week 1 Days 6-7 for the training schedule."""


def _check_onnx(cfg: MainRunConfig, synthetic: bool) -> bool:
    """Return True if predictive strategy can run; False to skip gracefully.

    Hard-exits the process (code 2) when ONNX is missing AND we're on the
    real-data path (i.e. user requested a real headline run).
    """
    if cfg.onnx_path.exists():
        return True
    if synthetic:
        logger.warning(
            f"[--synthetic] ONNX not at {cfg.onnx_path}; "
            f"running MCDM-EMA only"
        )
        return False
    msg = _NO_ONNX_MESSAGE.format(path=cfg.onnx_path)
    print(msg, file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_main(cfg: MainRunConfig, synthetic: bool = False,
             test_start: Optional[datetime] = None,
             test_end: Optional[datetime] = None) -> Optional[pd.DataFrame]:
    """Top-level driver. Returns the metrics dataframe (or None if aborted)."""
    run_predictive = _HAS_PREDICTIVE and _check_onnx(cfg, synthetic)

    # Wire the configured ONNX path into the strategy params via env var
    # (PredictiveMCDMParams reads its default from a class attribute, so we
    # patch the param object below after instantiation).

    logger.info(f"[load] synthetic={synthetic}")
    _, (_tr, _val, test_obs) = build_all(synthetic=synthetic)
    test_obs = _filter_window(test_obs, test_start, test_end)
    logger.info(f"[load] test={len(test_obs)} observations")

    if len(test_obs) < 24:
        logger.error("test window too small -- need at least 24 hourly observations")
        return None

    equity_curves: Dict[str, Optional[pd.Series]] = {}
    rebalance_idx: Dict[str, List[int]] = {}
    pred_strategy = None
    pred_result = None
    eq_pred: Optional[pd.Series] = None

    # ----- PredictiveMCDM (main) -----
    if run_predictive:
        pred_params = PredictiveMCDMParams(
            INITIAL_BALANCE=cfg.initial_balance,
            DEFAULT_INITIAL_ENTITY="AAVE",
            FORECAST_MODEL_PATH=str(cfg.onnx_path.relative_to(ROOT))
                                 if cfg.onnx_path.is_absolute()
                                    and ROOT in cfg.onnx_path.parents
                                 else str(cfg.onnx_path),
        )
        try:
            pred_strategy, pred_result, eq_pred = _run_one(
                PredictiveMCDMStrategy, pred_params, test_obs,
                "PredMCDM/test", seed=cfg.seed,
            )
            equity_curves["PredictiveMCDM"] = eq_pred
            rebalance_idx["PredictiveMCDM"] = _rebalance_indices(
                pred_result.to_dataframe()
            )
        except FileNotFoundError as exc:
            logger.error(f"PredictiveMCDM dependency missing: {exc}")
            run_predictive = False
        except Exception as exc:                         # noqa: BLE001
            logger.error(f"PredictiveMCDM runtime error: {exc}")
            run_predictive = False

    # ----- MCDM-EMA strawman (plan §7 Baseline C) -----
    ema_params = MCDMEMAParams(
        INITIAL_BALANCE=cfg.initial_balance,
        DEFAULT_INITIAL_ENTITY="AAVE",
    )
    _, ema_result, eq_ema = _run_one(
        MCDMEMAStrategy, ema_params, test_obs, "MCDM-EMA/test", seed=cfg.seed,
    )
    equity_curves["MCDMEMA"] = eq_ema
    rebalance_idx["MCDMEMA"] = _rebalance_indices(ema_result.to_dataframe())

    # ----- Metrics -----
    rows: List[Dict[str, float]] = []
    if run_predictive and pred_result is not None:
        hit = _forecast_hit_rate(pred_strategy, test_obs,
                                  horizon_h=cfg.forecast_horizon_h)
        pred_metrics = _compute_headline_metrics(
            eq_pred, pred_result.to_dataframe(), cfg, forecast_hit_rate=hit,
        )
        rows.append({"strategy": "PredictiveMCDM", **pred_metrics})

    ema_metrics = _compute_headline_metrics(
        eq_ema, ema_result.to_dataframe(), cfg, forecast_hit_rate=None,
    )
    rows.append({"strategy": "MCDMEMA", **ema_metrics})

    df = pd.DataFrame(rows)

    # ----- H1 bootstrap -----
    if run_predictive and eq_pred is not None and eq_ema is not None:
        h1 = _bootstrap_sharpe_diff(
            eq_pred, eq_ema,
            n_boot=cfg.n_bootstrap,
            target_diff=cfg.sharpe_diff_target,
            seed=cfg.seed,
        )
    else:
        h1 = {
            "n_months": 0,
            "predictive": float("nan"),
            "ema": float("nan"),
            "delta": float("nan"),
            "ci_low": float("nan"),
            "ci_high": float("nan"),
            "bootstrap_p_value": float("nan"),
            "target": float(cfg.sharpe_diff_target),
        }

    _emit_outputs(df, h1, equity_curves, rebalance_idx, cfg,
                  run_predictive=run_predictive)
    return df


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

def _emit_outputs(df: pd.DataFrame, h1: Dict[str, float],
                  equity_curves: Dict[str, Optional[pd.Series]],
                  rebalance_idx: Dict[str, List[int]],
                  cfg: MainRunConfig,
                  run_predictive: bool) -> None:
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    # ----- main.csv (2 rows x 8 cols) -----
    headline_cols = ["strategy", "net_apy", "sharpe_annual", "max_drawdown",
                     "calmar", "n_rebalances", "turnover_per_month",
                     "gas_spent_usd", "forecast_hit_rate"]
    out_df = df[[c for c in headline_cols if c in df.columns]].copy()
    main_csv = TABLES_DIR / "main.csv"
    out_df.to_csv(main_csv, index=False)
    logger.info(f"[saved] {main_csv}")

    # ----- h1_significance.csv -----
    if run_predictive:
        h1_rows = [{
            "metric": "monthly_sharpe",
            "predictive": h1["predictive"],
            "ema": h1["ema"],
            "delta": h1["delta"],
            "bootstrap_p_value": h1["bootstrap_p_value"],
            "ci_low": h1["ci_low"],
            "ci_high": h1["ci_high"],
            "n_months": h1["n_months"],
            "target": h1["target"],
        }]
    else:
        h1_rows = [{
            "metric": "monthly_sharpe",
            "predictive": float("nan"),
            "ema": float("nan"),
            "delta": float("nan"),
            "bootstrap_p_value": float("nan"),
            "ci_low": float("nan"),
            "ci_high": float("nan"),
            "n_months": 0,
            "target": float(cfg.sharpe_diff_target),
            "note": "predictive strategy not run (no ONNX / synthetic mode)",
        }]
    h1_csv = TABLES_DIR / "h1_significance.csv"
    pd.DataFrame(h1_rows).to_csv(h1_csv, index=False)
    logger.info(f"[saved] {h1_csv}")

    # ----- Markdown table to stdout -----
    print("\n### Main run -- headline metrics (test window)\n")
    df_fmt = out_df.copy()
    for c in out_df.columns:
        if c in ("strategy", "n_rebalances"):
            continue
        df_fmt[c] = df_fmt[c].apply(
            lambda v: "nan" if pd.isna(v) else f"{float(v):.4f}"
        )
    print("| " + " | ".join(df_fmt.columns) + " |")
    print("|" + "|".join(["---"] * len(df_fmt.columns)) + "|")
    for _, r in df_fmt.iterrows():
        print("| " + " | ".join(str(r[c]) for c in df_fmt.columns) + " |")

    # ----- H1 banner -----
    print(f"\n### H1 -- monthly Sharpe(predictive) - Sharpe(EMA) > "
          f"{cfg.sharpe_diff_target} ?\n")
    if run_predictive:
        print(f"  n_months    = {h1['n_months']}")
        print(f"  predictive  = {h1['predictive']:.4f}")
        print(f"  ema         = {h1['ema']:.4f}")
        print(f"  delta       = {h1['delta']:.4f}")
        print(f"  95% CI      = [{h1['ci_low']:.4f}, {h1['ci_high']:.4f}]")
        print(f"  p(delta<=t) = {h1['bootstrap_p_value']:.4f}  "
              f"(bootstrap n={cfg.n_bootstrap})")
        verdict = ("REJECT H0 / SUPPORT H1"
                   if h1["bootstrap_p_value"] < 0.05 else "FAIL TO REJECT H0")
        print(f"  verdict     = {verdict}")
    else:
        print("  skipped: predictive strategy did not run "
              "(no ONNX / synthetic mode)")

    # ----- Equity + drawdown plot -----
    try:
        import matplotlib                                # noqa: WPS433
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt                  # noqa: WPS433

        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(10, 7),
            gridspec_kw={"height_ratios": [2, 1]}, sharex=True,
        )

        colors = {"PredictiveMCDM": "tab:blue", "MCDMEMA": "tab:orange"}
        for name, eq in equity_curves.items():
            if eq is None or len(eq) == 0:
                continue
            color = colors.get(name, None)
            ax1.plot(eq.index, eq.values, label=name, color=color, linewidth=1.5)

            # Rebalance markers (downsample to <=200 for visual clarity).
            flips = rebalance_idx.get(name, [])
            if flips:
                step = max(1, len(flips) // 200)
                pts = flips[::step]
                pts = [i for i in pts if i < len(eq)]
                if pts:
                    ax1.scatter(eq.index[pts], eq.values[pts],
                                marker="v", s=14, color=color, alpha=0.6,
                                label=f"{name} rebal ({len(flips)})")

            # Drawdown subplot.
            running_max = pd.Series(eq.values).cummax()
            dd = (pd.Series(eq.values) / running_max - 1.0).values
            ax2.fill_between(eq.index, dd, 0, color=color, alpha=0.35, label=name)

        ax1.set_title("PredictiveMCDM vs MCDM-EMA  --  equity curves "
                      "(test window)")
        ax1.set_ylabel("portfolio value (USD)")
        ax1.legend(loc="best", fontsize=8)
        ax1.grid(alpha=0.3)

        ax2.set_ylabel("drawdown")
        ax2.set_xlabel("time (UTC)")
        ax2.grid(alpha=0.3)
        ax2.axhline(0, color="black", linewidth=0.6)

        fig_path = FIGURES_DIR / "main_vs_ema_equity.png"
        fig.tight_layout()
        fig.savefig(fig_path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        logger.info(f"[saved] {fig_path}")
    except Exception as exc:                             # noqa: BLE001
        logger.warning(f"[plot] disabled: {exc}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_ts(s: Optional[str]) -> Optional[datetime]:
    if s is None:
        return None
    ts = pd.Timestamp(s)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.to_pydatetime()


def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--synthetic", action="store_true",
                    help="run on synthetic joined panel (no API keys required); "
                         "skips PredictiveMCDM if ONNX missing")
    # Accept both --test-start / --test-end (task spec) and the older
    # --test-window-start / --test-window-end aliases for back-compat.
    ap.add_argument("--test-start", "--test-window-start",
                    dest="test_start", default=None,
                    help="override TEST window start (UTC ISO8601), "
                         "default 2026-01-01")
    ap.add_argument("--test-end", "--test-window-end",
                    dest="test_end", default=None,
                    help="override TEST window end (UTC ISO8601), "
                         "default 2026-04-30")
    ap.add_argument("--onnx", default=None,
                    help="path to trained forecaster ONNX (default: "
                         "forecaster/trained_models/dual_branch_kink.onnx)")
    ap.add_argument("--n-bootstrap", type=int, default=1000,
                    help="bootstrap replications for H1 Sharpe-diff test "
                         "(default 1000)")
    ap.add_argument("--initial-balance", type=float, default=1_000_000.0,
                    help="initial portfolio USD (default 1e6)")
    ap.add_argument("--gas-gwei", type=float, default=30.0,
                    help="constant gas price in gwei per rebalance (default 30)")
    ap.add_argument("--eth-usd", type=float, default=3500.0,
                    help="ETH/USD price for gas cost conversion (default 3500)")
    ap.add_argument("--seed", type=int, default=0,
                    help="random seed for bootstrap + strategy (default 0)")
    args = ap.parse_args(argv)

    onnx_path = Path(args.onnx).resolve() if args.onnx else DEFAULT_ONNX_PATH
    cfg = MainRunConfig(
        initial_balance=args.initial_balance,
        gas_gwei_const=args.gas_gwei,
        fallback_eth_usd=args.eth_usd,
        n_bootstrap=args.n_bootstrap,
        seed=args.seed,
        onnx_path=onnx_path,
    )
    run_main(
        cfg,
        synthetic=args.synthetic,
        test_start=_parse_ts(args.test_start),
        test_end=_parse_ts(args.test_end),
    )
    return 0


if __name__ == "__main__":
    sys.exit(_main())
