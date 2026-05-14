"""Run main ``PredictiveMCDMStrategy`` on the held-out test set (Jan-Apr 2026).

The headline backtest. Loads the trained ONNX forecaster, runs the strategy
on the test parquets, computes the full metrics dict from PROJECT_2_PLAN.md
§9 and the statistical-significance tests from §9.6:

- 1000-bootstrap of monthly Sharpe ratios (H1 test vs Baseline C MCDM-EMA)

Outputs:

    results/tables/main.csv             one row per strategy x metric battery
    results/tables/h1_significance.csv  Sharpe diff bootstrap
    results/figures/main_vs_ema_equity.png

Graceful skip path: if ``forecaster/trained_models/dual_branch_kink.onnx``
is missing, the script prints a clean ``[train forecaster first]`` message
and exits 0 without crashing -- this keeps CI / smoke pipelines green
before the ONNX export step has run.

Run::

    python -m backtest.run_main
    python -m backtest.run_main --synthetic
    python -m backtest.run_main --test-window-start 2026-02-01 --test-window-end 2026-04-30
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
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
ONNX_PATH = ROOT / "forecaster" / "trained_models" / "dual_branch_kink.onnx"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class MainRunConfig:
    """End-to-end run configuration."""
    initial_balance: float = 1_000_000.0
    gas_per_rebalance: int = 200_000
    fallback_eth_usd: float = 3000.0
    n_bootstrap: int = 1000
    sharpe_diff_target: float = 0.2          # plan §16 H1
    seed: int = 0


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


def _count_rebalances(strategy_df: pd.DataFrame) -> int:
    aave_col = _find_balance_col(strategy_df, "AAVE")
    comp_col = _find_balance_col(strategy_df, "COMPOUND")
    if aave_col is None or comp_col is None:
        return 0
    aave = strategy_df[aave_col].fillna(0.0).to_numpy(dtype=float)
    comp = strategy_df[comp_col].fillna(0.0).to_numpy(dtype=float)
    winner = (aave >= comp).astype(int)
    if len(winner) < 2:
        return 0
    return int(np.sum(np.abs(np.diff(winner))))


def _median_gas_gwei(observations: List[Observation]) -> float:
    vals = [obs.states["AAVE"].gas_gwei for obs in observations if "AAVE" in obs.states]
    if not vals:
        return 30.0
    return float(np.median(vals))


# ---------------------------------------------------------------------------
# Metric battery (plan §9.1, §9.2, §9.3, §9.6)
# ---------------------------------------------------------------------------

def _annualisation_factor(equity: pd.Series) -> Tuple[int, float]:
    """Return (steps_per_year, sqrt(steps_per_year)) for a hourly grid by default."""
    if len(equity) >= 2:
        try:
            dt = (equity.index[1] - equity.index[0]).total_seconds()
            if dt > 0:
                steps_per_year = int(round(365.25 * 86400 / dt))
                return steps_per_year, float(np.sqrt(steps_per_year))
        except Exception:                                # noqa: BLE001
            pass
    # Default: hourly
    return 365 * 24, float(np.sqrt(365 * 24))


def _compute_metrics(
    equity: Optional[pd.Series],
    strategy_df: pd.DataFrame,
    cfg: MainRunConfig,
    observations: List[Observation],
) -> Dict[str, float]:
    """Compute metric battery per plan §9 from an equity-curve series."""
    out: Dict[str, float] = {
        "total_return": float("nan"),
        "apy": float("nan"),
        "sharpe": float("nan"),
        "calmar": float("nan"),
        "max_dd": float("nan"),
        "vol_annual": float("nan"),
        "worst_day_return": float("nan"),
        "n_rebalances": int(_count_rebalances(strategy_df)),
        "turnover": float("nan"),
        "gas_spent_usd": float("nan"),
        "gas_pct_of_pnl": float("nan"),
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

    total_return = vT / v0 - 1.0
    apy = (vT / v0) ** (1.0 / max(years, 1e-9)) - 1.0 if vT > 0 else float("nan")

    mu = float(rets.mean())
    sd = float(rets.std(ddof=1)) if len(rets) > 1 else 0.0
    sharpe = (mu / sd) * sqrt_steps if sd > 0 else float("nan")
    vol_annual = sd * sqrt_steps

    running_max = eq.cummax()
    drawdown = (eq / running_max) - 1.0
    max_dd = float(drawdown.min()) if len(drawdown) else float("nan")
    calmar = (apy / abs(max_dd)) if max_dd < 0 else float("nan")

    # Worst daily return (resample to daily mean equity if hourly)
    try:
        daily_eq = eq.resample("1D").last().dropna()
        daily_rets = daily_eq.pct_change().dropna()
        worst_day = float(daily_rets.min()) if len(daily_rets) else float("nan")
    except Exception:                                    # noqa: BLE001
        worst_day = float("nan")

    # Turnover proxy: sum of abs winner-flag changes / 2  ~ rebalances / 2 of NAV
    turnover = float(out["n_rebalances"])

    # Gas dollar cost
    median_gas = _median_gas_gwei(observations)
    gas_eth_per = cfg.gas_per_rebalance * median_gas * 1e-9
    gas_usd = out["n_rebalances"] * gas_eth_per * cfg.fallback_eth_usd
    gross_pnl = vT - v0
    gas_pct = gas_usd / gross_pnl if gross_pnl > 0 else float("nan")

    out.update({
        "total_return": total_return,
        "apy": apy,
        "sharpe": sharpe,
        "calmar": calmar,
        "max_dd": max_dd,
        "vol_annual": vol_annual,
        "worst_day_return": worst_day,
        "turnover": turnover,
        "gas_spent_usd": gas_usd,
        "gas_pct_of_pnl": gas_pct,
    })
    return out


# ---------------------------------------------------------------------------
# H1 bootstrap of monthly Sharpe difference (plan §9.6 / §16 H1)
# ---------------------------------------------------------------------------

def _monthly_sharpes(equity: pd.Series) -> np.ndarray:
    """Annualised Sharpe within each calendar month from an hourly equity series."""
    eq = equity.astype(float).dropna()
    if len(eq) < 2:
        return np.array([])
    rets = eq.pct_change().dropna()
    steps_per_year, sqrt_steps = _annualisation_factor(eq)
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
    """Bootstrap the per-month Sharpe difference (predictive minus ema).

    Returns dict with mean diff, CI bounds, and p_value of
    P(Sharpe(pred) - Sharpe(ema) <= target_diff) under the bootstrap.
    """
    s_pred = _monthly_sharpes(eq_pred)
    s_ema = _monthly_sharpes(eq_ema)
    n = min(len(s_pred), len(s_ema))
    if n < 2:
        return {
            "n_months": int(n),
            "diff_observed": float("nan"),
            "diff_mean": float("nan"),
            "diff_lo95": float("nan"),
            "diff_hi95": float("nan"),
            "p_value_h1": float("nan"),
            "target": float(target_diff),
        }

    s_pred = s_pred[:n]
    s_ema = s_ema[:n]
    diff_observed = float(np.mean(s_pred - s_ema))

    rng = np.random.default_rng(seed)
    boot_diffs = np.empty(n_boot, dtype=float)
    for b in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boot_diffs[b] = float(np.mean(s_pred[idx] - s_ema[idx]))

    p_value = float(np.mean(boot_diffs <= target_diff))   # H1 fails if true
    return {
        "n_months": int(n),
        "diff_observed": diff_observed,
        "diff_mean": float(np.mean(boot_diffs)),
        "diff_lo95": float(np.quantile(boot_diffs, 0.025)),
        "diff_hi95": float(np.quantile(boot_diffs, 0.975)),
        "p_value_h1": p_value,
        "target": float(target_diff),
    }


# ---------------------------------------------------------------------------
# Strategy launcher
# ---------------------------------------------------------------------------

def _run_one(strategy_cls, params, observations: List[Observation],
             label: str) -> Tuple[object, Optional[pd.Series]]:
    logger.info(f"[{label}] running on {len(observations)} observations")
    strategy = strategy_cls(debug=False, params=params)
    result = strategy.run(observations)
    df = result.to_dataframe()
    eq = _portfolio_equity(df)
    if eq is not None:
        try:
            eq.index = [o.timestamp for o in observations][: len(eq)]
        except Exception:                                # noqa: BLE001
            pass
    return result, eq


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
# Orchestration
# ---------------------------------------------------------------------------

def run_main(cfg: MainRunConfig, synthetic: bool = False,
             test_start: Optional[datetime] = None,
             test_end: Optional[datetime] = None) -> Optional[pd.DataFrame]:
    """Top-level driver. Returns the metrics dataframe (or None if skipped)."""
    if not _HAS_PREDICTIVE:
        logger.error("PredictiveMCDMStrategy unavailable -- skipping main run")
        return None

    if not ONNX_PATH.exists():
        msg = (
            f"[train forecaster first] {ONNX_PATH} not found.\n"
            f"  Run: python -m forecaster.train  &&  python -m forecaster.export_onnx"
        )
        print(msg)
        logger.warning(msg)
        return None

    logger.info(f"[load] synthetic={synthetic}")
    _, (_tr, _val, test_obs) = build_all(synthetic=synthetic)
    test_obs = _filter_window(test_obs, test_start, test_end)
    logger.info(f"[load] test={len(test_obs)} observations")

    if len(test_obs) < 24:
        logger.error("test window too small -- need at least 24 hourly observations")
        return None

    # ----- Predictive MCDM (main) -----
    pred_params = PredictiveMCDMParams(
        INITIAL_BALANCE=cfg.initial_balance,
        DEFAULT_INITIAL_ENTITY="AAVE",
    )
    try:
        pred_result, eq_pred = _run_one(
            PredictiveMCDMStrategy, pred_params, test_obs, "PredMCDM/test",
        )
    except Exception as exc:                             # noqa: BLE001
        logger.error(f"PredictiveMCDM runtime error: {exc}")
        return None

    # ----- MCDM-EMA strawman (plan §16 H1) -----
    ema_params = MCDMEMAParams(
        INITIAL_BALANCE=cfg.initial_balance,
        DEFAULT_INITIAL_ENTITY="AAVE",
    )
    ema_result, eq_ema = _run_one(
        MCDMEMAStrategy, ema_params, test_obs, "MCDM-EMA/test",
    )

    # ----- Metrics -----
    pred_metrics = _compute_metrics(eq_pred, pred_result.to_dataframe(), cfg, test_obs)
    ema_metrics = _compute_metrics(eq_ema, ema_result.to_dataframe(), cfg, test_obs)

    rows = [
        {"strategy": "PredictiveMCDM", **pred_metrics},
        {"strategy": "MCDMEMA", **ema_metrics},
    ]
    df = pd.DataFrame(rows)

    # ----- H1 bootstrap -----
    if eq_pred is not None and eq_ema is not None:
        h1 = _bootstrap_sharpe_diff(
            eq_pred, eq_ema,
            n_boot=cfg.n_bootstrap,
            target_diff=cfg.sharpe_diff_target,
            seed=cfg.seed,
        )
    else:
        h1 = {
            "n_months": 0,
            "diff_observed": float("nan"),
            "diff_mean": float("nan"),
            "diff_lo95": float("nan"),
            "diff_hi95": float("nan"),
            "p_value_h1": float("nan"),
            "target": float(cfg.sharpe_diff_target),
        }

    _emit_outputs(df, h1, {"PredictiveMCDM": eq_pred, "MCDMEMA": eq_ema})
    return df


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

def _emit_outputs(df: pd.DataFrame, h1: Dict[str, float],
                  equity_curves: Dict[str, Optional[pd.Series]]) -> None:
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    main_csv = TABLES_DIR / "main.csv"
    df.to_csv(main_csv, index=False)
    logger.info(f"[saved] {main_csv}")

    h1_csv = TABLES_DIR / "h1_significance.csv"
    pd.DataFrame([h1]).to_csv(h1_csv, index=False)
    logger.info(f"[saved] {h1_csv}")

    # Markdown table.
    print("\n### Main run (test window 2026-01-01 .. 2026-04-30)\n")
    cols = ["strategy", "n_rebalances", "total_return", "apy", "sharpe",
            "calmar", "max_dd", "vol_annual", "worst_day_return",
            "gas_spent_usd", "gas_pct_of_pnl"]
    df_fmt = df.copy()
    for c in cols:
        if c == "strategy" or c == "n_rebalances":
            continue
        if c in df_fmt.columns:
            df_fmt[c] = df_fmt[c].apply(
                lambda v: "nan" if pd.isna(v) else f"{float(v):.4f}"
            )
    print("| " + " | ".join(cols) + " |")
    print("|" + "|".join(["---"] * len(cols)) + "|")
    for _, r in df_fmt[cols].iterrows():
        print("| " + " | ".join(str(r[c]) for c in cols) + " |")

    print("\n### H1 — Sharpe(predictive) - Sharpe(EMA) > 0.2 ?\n")
    print(f"  n_months   = {h1['n_months']}")
    print(f"  observed   = {h1['diff_observed']:.4f}" if not pd.isna(h1['diff_observed']) else "  observed   = nan")
    print(f"  boot mean  = {h1['diff_mean']:.4f}" if not pd.isna(h1['diff_mean']) else "  boot mean  = nan")
    print(f"  95% CI     = [{h1['diff_lo95']:.4f}, {h1['diff_hi95']:.4f}]"
          if not pd.isna(h1['diff_lo95']) else "  95% CI     = nan")
    print(f"  p(diff<=0.2)= {h1['p_value_h1']:.4f}"
          if not pd.isna(h1['p_value_h1']) else "  p(diff<=0.2)= nan")

    # Equity overlay.
    try:
        import matplotlib                                # noqa: WPS433
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt                  # noqa: WPS433

        fig, ax = plt.subplots(figsize=(9, 5))
        for name, eq in equity_curves.items():
            if eq is None or len(eq) == 0:
                continue
            ax.plot(eq.index, eq.values, label=name)
        ax.set_title("PredictiveMCDM vs MCDM-EMA -- equity curves (test window)")
        ax.set_xlabel("time")
        ax.set_ylabel("portfolio value (USD)")
        ax.legend(loc="best")
        ax.grid(alpha=0.3)
        fig_path = FIGURES_DIR / "main_vs_ema_equity.png"
        fig.savefig(fig_path, dpi=110, bbox_inches="tight")
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
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--synthetic", action="store_true",
                    help="run on synthetic joined panel (no API keys required)")
    ap.add_argument("--test-window-start", default=None,
                    help="override TEST window start (UTC, ISO8601)")
    ap.add_argument("--test-window-end", default=None,
                    help="override TEST window end (UTC, ISO8601)")
    ap.add_argument("--n-bootstrap", type=int, default=1000,
                    help="bootstrap replications for H1 Sharpe-diff test")
    ap.add_argument("--seed", type=int, default=0,
                    help="random seed for bootstrap")
    args = ap.parse_args(argv)

    cfg = MainRunConfig(n_bootstrap=args.n_bootstrap, seed=args.seed)
    run_main(
        cfg,
        synthetic=args.synthetic,
        test_start=_parse_ts(args.test_window_start),
        test_end=_parse_ts(args.test_window_end),
    )
    return 0


if __name__ == "__main__":
    sys.exit(_main())
