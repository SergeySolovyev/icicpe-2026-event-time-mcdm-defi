"""Run all four strategies on the joined-clean panel and report metrics.

Strategies:
    A. BuyAndHoldAaveStrategy
    B. APYGreedyStrategy
    C. MCDMEMAStrategy
    D. PredictiveMCDMStrategy (skipped if ONNX missing)

For each, we report on the TEST window (Jan-Apr 2026) plus a val-APY
reference number. Output:

    results/tables/baselines.csv
    results/figures/baselines_equity.png
    + markdown table printed to stdout.

Gas-spent estimate: ``200_000 gas * historical median gas_gwei * 1e-9 ETH * ETH/USD``
per rebalance, summed across the run. Without an ETH/USD feed on the
joined panel we fall back to a static $3000.

Run::

    python -m backtest.run_baselines
    python -m backtest.run_baselines --synthetic
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "extras" / "fractal_pr_lending_allocation"))

from fractal.core.base import Observation  # noqa: E402

from backtest.observations_builder import (  # noqa: E402
    LendingGlobalStateExt,
    build_all,
)
from strategies.baseline_buyhold import BuyAndHoldAaveStrategy  # noqa: E402
from strategies.baseline_apy_greedy import APYGreedyStrategy, APYGreedyParams  # noqa: E402
from strategies.baseline_mcdm_ema import MCDMEMAStrategy, MCDMEMAParams  # noqa: E402
from base_lending_allocation import BaseLendingAllocationParams  # noqa: E402

# Predictive strategy may fail to import-time without its data dependencies;
# wrap defensively.
try:
    from strategies.predictive_mcdm import PredictiveMCDMStrategy, PredictiveMCDMParams  # noqa: E402
    _HAS_PREDICTIVE = True
except Exception as _exc:                                # noqa: BLE001
    print(f"[run_baselines] PredictiveMCDMStrategy import failed: {_exc}")
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
class BaselineRunConfig:
    """End-to-end run configuration."""
    initial_balance: float = 1_000_000.0
    gas_per_rebalance: int = 200_000
    fallback_eth_usd: float = 3000.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _median_gas_gwei(observations: List[Observation]) -> float:
    vals = [obs.states["AAVE"].gas_gwei for obs in observations if "AAVE" in obs.states]
    if not vals:
        return 30.0
    return float(np.median(vals))


def _count_rebalances(strategy_df: pd.DataFrame) -> int:
    """Count switches of the active entity from the per-step balance dataframe.

    A rebalance is a step where the entity holding the bulk of balance
    changes from the previous step. We use AAVE balance fraction as a
    proxy: switches happen when the AAVE-vs-COMPOUND winner flips.
    """
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


def _find_balance_col(df: pd.DataFrame, entity_name: str) -> Optional[str]:
    """Locate the balance column for an entity in the per-step dataframe."""
    candidates = [
        f"{entity_name}_balance",
        f"{entity_name}.balance",
        f"balance_{entity_name}",
    ]
    for c in candidates:
        if c in df.columns:
            return c
    # Best-effort fallback: any column starting with entity_name + balance-ish suffix
    for c in df.columns:
        if c.startswith(entity_name) and "balance" in c.lower():
            return c
    return None


def _portfolio_equity(strategy_df: pd.DataFrame) -> Optional[pd.Series]:
    """Best-effort: locate (or derive) a per-step total portfolio value series.

    fractal-defi typically exposes ``net_balance`` or similar; we probe a
    few likely names, then fall back to summing AAVE + COMPOUND balance.
    """
    for col in ("net_balance", "portfolio_value", "total_balance", "balance"):
        if col in strategy_df.columns:
            return strategy_df[col].astype(float)
    aave_col = _find_balance_col(strategy_df, "AAVE")
    comp_col = _find_balance_col(strategy_df, "COMPOUND")
    if aave_col is not None and comp_col is not None:
        return strategy_df[aave_col].fillna(0.0) + strategy_df[comp_col].fillna(0.0)
    return None


def _summarise(
    strategy_name: str,
    result,
    observations: List[Observation],
    cfg: BaselineRunConfig,
    val_apy: Optional[float] = None,
) -> Dict[str, float]:
    """Roll up metrics into the row schema for the baselines.csv."""
    metrics = result.get_default_metrics() or {}
    df = result.to_dataframe()

    n_rebalances = _count_rebalances(df)
    median_gas = _median_gas_gwei(observations)
    gas_eth = cfg.gas_per_rebalance * median_gas * 1e-9
    gas_usd = n_rebalances * gas_eth * cfg.fallback_eth_usd

    def _get(*keys, default=float("nan")):
        for k in keys:
            # StrategyMetrics is a dataclass; mappings also work via .get
            val = None
            if hasattr(metrics, k):
                val = getattr(metrics, k)
            elif isinstance(metrics, dict) and k in metrics:
                val = metrics[k]
            if val is None:
                continue
            try:
                return float(val)
            except Exception:                           # noqa: BLE001
                continue
        return default

    return {
        "strategy": strategy_name,
        "n_rebalances": int(n_rebalances),
        "total_return": _get("accumulated_return", "total_return"),
        "apy": _get("apy"),
        "sharpe": _get("sharpe"),
        "max_dd": _get("max_drawdown", "max_dd"),
        "gas_spent_usd": float(gas_usd),
        "val_apy": float(val_apy) if val_apy is not None else float("nan"),
    }


def _apy_only(result) -> float:
    metrics = result.get_default_metrics()
    if metrics is None:
        return float("nan")
    try:
        if hasattr(metrics, "apy"):
            return float(metrics.apy)
        if isinstance(metrics, dict):
            return float(metrics.get("apy", float("nan")))
    except Exception:                                   # noqa: BLE001
        pass
    return float("nan")


# ---------------------------------------------------------------------------
# Strategy launcher
# ---------------------------------------------------------------------------

def _run_one(strategy_cls, params, observations: List[Observation],
             label: str) -> Tuple[object, Optional[pd.Series]]:
    """Instantiate, run, return (StrategyResult, equity_series_or_None)."""
    print(f"  [{label}] running on {len(observations)} observations...")
    strategy = strategy_cls(debug=False, params=params)
    result = strategy.run(observations)
    df = result.to_dataframe()
    eq = _portfolio_equity(df)
    if eq is not None:
        # Align index to observation timestamps where possible.
        try:
            eq.index = [o.timestamp for o in observations][: len(eq)]
        except Exception:                               # noqa: BLE001
            pass
    return result, eq


def run_all(cfg: BaselineRunConfig, synthetic: bool = False) -> pd.DataFrame:
    print(f"[load] synthetic={synthetic}")
    _, (_tr, val_obs, test_obs) = build_all(synthetic=synthetic)
    print(f"[load] val={len(val_obs)}  test={len(test_obs)}")

    rows: List[Dict[str, float]] = []
    equity_curves: Dict[str, pd.Series] = {}

    # ----- A: Buy and Hold (AAVE) -----
    bh_params_val = BaseLendingAllocationParams(
        INITIAL_BALANCE=cfg.initial_balance, DEFAULT_INITIAL_ENTITY="AAVE",
    )
    bh_params_test = BaseLendingAllocationParams(
        INITIAL_BALANCE=cfg.initial_balance, DEFAULT_INITIAL_ENTITY="AAVE",
    )
    val_r, _ = _run_one(BuyAndHoldAaveStrategy, bh_params_val, val_obs, "BuyHold/val")
    test_r, eq = _run_one(BuyAndHoldAaveStrategy, bh_params_test, test_obs, "BuyHold/test")
    rows.append(_summarise("BuyAndHold", test_r, test_obs, cfg, val_apy=_apy_only(val_r)))
    if eq is not None:
        equity_curves["BuyAndHold"] = eq

    # ----- B: APY-only greedy -----
    apy_params_val = APYGreedyParams(
        INITIAL_BALANCE=cfg.initial_balance, DEFAULT_INITIAL_ENTITY="AAVE",
    )
    apy_params_test = APYGreedyParams(
        INITIAL_BALANCE=cfg.initial_balance, DEFAULT_INITIAL_ENTITY="AAVE",
    )
    val_r, _ = _run_one(APYGreedyStrategy, apy_params_val, val_obs, "APYGreedy/val")
    test_r, eq = _run_one(APYGreedyStrategy, apy_params_test, test_obs, "APYGreedy/test")
    rows.append(_summarise("APYGreedy", test_r, test_obs, cfg, val_apy=_apy_only(val_r)))
    if eq is not None:
        equity_curves["APYGreedy"] = eq

    # ----- C: MCDM-EMA -----
    ema_params_val = MCDMEMAParams(
        INITIAL_BALANCE=cfg.initial_balance, DEFAULT_INITIAL_ENTITY="AAVE",
    )
    ema_params_test = MCDMEMAParams(
        INITIAL_BALANCE=cfg.initial_balance, DEFAULT_INITIAL_ENTITY="AAVE",
    )
    val_r, _ = _run_one(MCDMEMAStrategy, ema_params_val, val_obs, "MCDM-EMA/val")
    test_r, eq = _run_one(MCDMEMAStrategy, ema_params_test, test_obs, "MCDM-EMA/test")
    rows.append(_summarise("MCDMEMA", test_r, test_obs, cfg, val_apy=_apy_only(val_r)))
    if eq is not None:
        equity_curves["MCDMEMA"] = eq

    # ----- D: Predictive MCDM (main) -- skip if ONNX missing -----
    if _HAS_PREDICTIVE and ONNX_PATH.exists():
        try:
            pred_params_val = PredictiveMCDMParams(
                INITIAL_BALANCE=cfg.initial_balance, DEFAULT_INITIAL_ENTITY="AAVE",
            )
            pred_params_test = PredictiveMCDMParams(
                INITIAL_BALANCE=cfg.initial_balance, DEFAULT_INITIAL_ENTITY="AAVE",
            )
            val_r, _ = _run_one(PredictiveMCDMStrategy, pred_params_val, val_obs, "PredMCDM/val")
            test_r, eq = _run_one(PredictiveMCDMStrategy, pred_params_test, test_obs, "PredMCDM/test")
            rows.append(_summarise("PredictiveMCDM", test_r, test_obs, cfg, val_apy=_apy_only(val_r)))
            if eq is not None:
                equity_curves["PredictiveMCDM"] = eq
        except Exception as exc:                        # noqa: BLE001
            print(f"[PredictiveMCDM] runtime error -> skipped: {exc}")
    else:
        print(f"[PredictiveMCDM] trained model not yet exported "
              f"({ONNX_PATH}); skipping main strategy")

    df = pd.DataFrame(rows)
    _emit_outputs(df, equity_curves)
    return df


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

def _emit_outputs(df: pd.DataFrame, equity_curves: Dict[str, pd.Series]) -> None:
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    csv_path = TABLES_DIR / "baselines.csv"
    df.to_csv(csv_path, index=False)
    print(f"[saved] {csv_path}")

    # Markdown table to stdout.
    print("\n### Baselines (test window 2026-01-01 .. 2026-04-30)\n")
    cols = ["strategy", "n_rebalances", "total_return", "apy", "sharpe",
            "max_dd", "gas_spent_usd", "val_apy"]
    df_fmt = df.copy()
    for c in ("total_return", "apy", "sharpe", "max_dd", "gas_spent_usd", "val_apy"):
        if c in df_fmt.columns:
            df_fmt[c] = df_fmt[c].apply(
                lambda v: "nan" if pd.isna(v) else f"{float(v):.4f}"
            )
    # Manual markdown print (avoids tabulate dependency).
    print("| " + " | ".join(cols) + " |")
    print("|" + "|".join(["---"] * len(cols)) + "|")
    for _, r in df_fmt[cols].iterrows():
        print("| " + " | ".join(str(r[c]) for c in cols) + " |")

    # Equity-curve overlay.
    if equity_curves:
        try:
            import matplotlib                            # noqa: WPS433
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt              # noqa: WPS433

            fig, ax = plt.subplots(figsize=(9, 5))
            for name, eq in equity_curves.items():
                if eq is None or len(eq) == 0:
                    continue
                ax.plot(eq.index, eq.values, label=name)
            ax.set_title("Baselines equity curves (test window)")
            ax.set_xlabel("time")
            ax.set_ylabel("portfolio value (USD)")
            ax.legend(loc="best")
            ax.grid(alpha=0.3)
            fig_path = FIGURES_DIR / "baselines_equity.png"
            fig.savefig(fig_path, dpi=110, bbox_inches="tight")
            plt.close(fig)
            print(f"[saved] {fig_path}")
        except Exception as exc:                        # noqa: BLE001
            print(f"[plot] disabled: {exc}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--synthetic", action="store_true",
                    help="run on synthetic joined panel (no API keys required)")
    args = ap.parse_args(argv)

    cfg = BaselineRunConfig()
    run_all(cfg, synthetic=args.synthetic)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
