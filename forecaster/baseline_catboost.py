"""CatBoost on hand-crafted features baseline forecaster.

Mirrors `examples/ml_funding_rate_forecasting/notebooks/baseline_research.ipynb`
in fractal-defi (CatBoostRegressor on lag + rolling features). Per
PROJECT_2_PLAN.md S10 ablation #5.

Hyperparameters per ablation #5 spec:
    depth=6, iterations=2000, learning_rate=0.05, l2_leaf_reg=3,
    loss_function='RMSE', verbose=False.

Two SEPARATE models, one per protocol (Aave, Compound), each predicting the
realised supply rate at t+12h. Cross-protocol spreads ARE included in the
feature matrix.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class CatBoostConfig:
    """Ablation #5 settings."""
    depth: int = 6
    iterations: int = 2000
    learning_rate: float = 0.05
    l2_leaf_reg: float = 3.0
    loss_function: str = "RMSE"
    verbose: bool = False
    random_seed: int = 42
    early_stopping_rounds: int | None = 100


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

# Base columns the feature builder assumes present (joined Aave+Compound panel).
BASE_COLS_RATES = ("r_aave", "r_compound")
BASE_COLS_UTIL  = ("u_aave", "u_compound")


def build_features(
    df: pd.DataFrame,
    lags: Iterable[int] = (1, 3, 6, 12, 24),
    windows: Iterable[int] = (6, 12, 24, 48),
    horizon: int = 12,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build hand-crafted features + aligned (t+horizon) targets.

    Features per protocol:
      * lagged rate at lags
      * rolling mean / std of rate at windows
      * rolling mean of utilization at windows
      * lagged utilization (lag 1, 6, 24)
    Cross-protocol / global features:
      * rate spread r_aave - r_compound (current + 1, 6, 24h lags)
      * utilization spread
      * time-of-day sin/cos
      * gas (current + rolling mean) if present

    Returns:
        X: feature matrix (rows aligned with the LAST observable timestamp t)
        Y: target frame with columns ['r_aave_tplus', 'r_compound_tplus']
           (realised rate at t+horizon).
    """
    lags = tuple(int(x) for x in lags)
    windows = tuple(int(x) for x in windows)
    feats: dict[str, pd.Series] = {}

    for proto in ("aave", "compound"):
        r = df[f"r_{proto}"]
        u = df[f"u_{proto}"]
        for L in lags:
            feats[f"r_{proto}_lag{L}"] = r.shift(L)
            if L in (1, 6, 24):
                feats[f"u_{proto}_lag{L}"] = u.shift(L)
        for W in windows:
            feats[f"r_{proto}_mean{W}"] = r.rolling(W, min_periods=2).mean()
            feats[f"r_{proto}_std{W}"]  = r.rolling(W, min_periods=2).std()
            feats[f"u_{proto}_mean{W}"] = u.rolling(W, min_periods=2).mean()
        # First differences
        feats[f"r_{proto}_diff1"] = r.diff(1)
        feats[f"r_{proto}_diff6"] = r.diff(6)

    # Cross-protocol features
    spread = df["r_aave"] - df["r_compound"]
    feats["spread"] = spread
    for L in (1, 6, 24):
        feats[f"spread_lag{L}"] = spread.shift(L)
    feats["util_spread"] = df["u_aave"] - df["u_compound"]

    # Time-of-day cyclical
    if isinstance(df.index, pd.DatetimeIndex):
        hour = df.index.hour.values
        feats["tod_sin"] = pd.Series(np.sin(2 * np.pi * hour / 24), index=df.index)
        feats["tod_cos"] = pd.Series(np.cos(2 * np.pi * hour / 24), index=df.index)

    # Optional gas
    if "gas_gwei" in df.columns:
        feats["gas_gwei"] = df["gas_gwei"]
        feats["gas_mean24"] = df["gas_gwei"].rolling(24, min_periods=2).mean()

    # Optional dTVL passthroughs (extract_features may have added these)
    for c in ("dTVL_aave_24h", "dTVL_compound_24h"):
        if c in df.columns:
            feats[c] = df[c]

    X = pd.DataFrame(feats, index=df.index)

    # Targets: realised rate at t+horizon
    Y = pd.DataFrame({
        "r_aave_tplus":     df["r_aave"].shift(-horizon),
        "r_compound_tplus": df["r_compound"].shift(-horizon),
    }, index=df.index)

    aligned = pd.concat([X, Y], axis=1).replace([np.inf, -np.inf], np.nan).dropna()
    X_out = aligned[X.columns]
    Y_out = aligned[Y.columns]
    return X_out, Y_out


# ---------------------------------------------------------------------------
# Forecaster
# ---------------------------------------------------------------------------

class CatBoostForecaster:
    """Per-protocol CatBoost regression.

    predict() signature mirrors DABiGRUCNNForecaster's `predict` shape:
        forecaster.predict(history_df, horizon=12) -> (r_aave_hat, r_compound_hat).
    """

    def __init__(
        self,
        cfg: CatBoostConfig | None = None,
        lags: Sequence[int] = (1, 3, 6, 12, 24),
        windows: Sequence[int] = (6, 12, 24, 48),
        horizon: int = 12,
    ):
        self.cfg = cfg or CatBoostConfig()
        self.lags = tuple(lags)
        self.windows = tuple(windows)
        self.horizon = int(horizon)
        self.model_aave: CatBoostRegressor | None = None
        self.model_compound: CatBoostRegressor | None = None
        self.feature_names_: list[str] = []

    def _new_model(self) -> CatBoostRegressor:
        return CatBoostRegressor(
            depth=self.cfg.depth,
            iterations=self.cfg.iterations,
            learning_rate=self.cfg.learning_rate,
            l2_leaf_reg=self.cfg.l2_leaf_reg,
            loss_function=self.cfg.loss_function,
            random_seed=self.cfg.random_seed,
            verbose=self.cfg.verbose,
            allow_writing_files=False,
        )

    def fit(
        self,
        df: pd.DataFrame,
        val_df: pd.DataFrame | None = None,
    ) -> "CatBoostForecaster":
        """Fit two models, one per protocol."""
        X, Y = build_features(df, lags=self.lags, windows=self.windows,
                              horizon=self.horizon)
        self.feature_names_ = list(X.columns)

        eval_a = eval_c = None
        if val_df is not None:
            Xv, Yv = build_features(val_df, lags=self.lags, windows=self.windows,
                                    horizon=self.horizon)
            Xv = Xv[self.feature_names_]
            eval_a = (Xv.to_numpy(), Yv["r_aave_tplus"].to_numpy())
            eval_c = (Xv.to_numpy(), Yv["r_compound_tplus"].to_numpy())

        fit_kw: dict = {}
        if self.cfg.early_stopping_rounds is not None and eval_a is not None:
            fit_kw["early_stopping_rounds"] = self.cfg.early_stopping_rounds

        self.model_aave = self._new_model()
        self.model_aave.fit(X.to_numpy(), Y["r_aave_tplus"].to_numpy(),
                            eval_set=eval_a, **fit_kw)
        self.model_compound = self._new_model()
        self.model_compound.fit(X.to_numpy(), Y["r_compound_tplus"].to_numpy(),
                                eval_set=eval_c, **fit_kw)
        return self

    def _build_predict_row(self, history: pd.DataFrame) -> np.ndarray:
        """Run build_features on `history` then take the last valid row."""
        # Need enough history to fill all lags / windows.
        need = max(max(self.lags), max(self.windows), 24) + 2
        if len(history) < need:
            raise ValueError(
                f"history too short: {len(history)} rows, need >= {need}"
            )
        # Use horizon=1 here just so build_features returns at least one
        # aligned row at the tail; we drop the target columns afterwards.
        X, _ = build_features(history, lags=self.lags, windows=self.windows, horizon=1)
        # Reindex to training feature order (CatBoost requires this).
        X = X[self.feature_names_]
        if len(X) == 0:
            # Re-derive without target alignment.
            X_raw, _ = build_features(history, lags=self.lags, windows=self.windows,
                                      horizon=0)
            X_raw = X_raw[self.feature_names_].dropna()
            if len(X_raw) == 0:
                raise ValueError("Cannot construct prediction features from history.")
            return X_raw.iloc[-1].to_numpy().reshape(1, -1)
        return X.iloc[-1].to_numpy().reshape(1, -1)

    def predict(self, history: pd.DataFrame, horizon: int = 12) -> tuple[float, float]:
        """Predict (r_aave_tplus, r_compound_tplus). `horizon` must equal training horizon."""
        if self.model_aave is None or self.model_compound is None:
            raise RuntimeError("CatBoostForecaster.fit() must be called before predict().")
        if horizon != self.horizon:
            raise ValueError(
                f"horizon mismatch: model trained at {self.horizon}h, asked {horizon}h"
            )
        x = self._build_predict_row(history)
        r_a = float(self.model_aave.predict(x)[0])
        r_c = float(self.model_compound.predict(x)[0])
        return r_a, r_c

    def predict_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        """Predict on every row in df (with enough history). Returns aligned frame."""
        if self.model_aave is None or self.model_compound is None:
            raise RuntimeError("CatBoostForecaster.fit() must be called before predict().")
        X, _ = build_features(df, lags=self.lags, windows=self.windows,
                              horizon=self.horizon)
        X = X[self.feature_names_]
        ra = self.model_aave.predict(X.to_numpy())
        rc = self.model_compound.predict(X.to_numpy())
        return pd.DataFrame({"r_aave_tplus": ra, "r_compound_tplus": rc}, index=X.index)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _make_synth_panel(n: int = 1500, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-02-01", periods=n, freq="h", tz="UTC")
    def util_walk(start):
        u = np.empty(n); u[0] = start
        for i in range(1, n):
            u[i] = np.clip(u[i-1] + rng.normal(0.0, 0.01), 0.05, 0.97)
        return u
    u_a = util_walk(0.55); u_c = util_walk(0.45)
    r_a = 0.05 * u_a + 0.005 + rng.normal(0, 0.001, n)
    r_c = 0.04 * u_c + 0.004 + rng.normal(0, 0.001, n)
    gas = np.clip(20 + 5 * rng.standard_normal(n), 5, 200)
    return pd.DataFrame({
        "r_aave": r_a, "r_compound": r_c,
        "u_aave": u_a, "u_compound": u_c,
        "gas_gwei": gas,
    }, index=idx)


def _selftest() -> None:
    df = _make_synth_panel(n=1500, seed=0)
    cut = int(0.7 * len(df))
    train = df.iloc[:cut]
    val   = df.iloc[cut:]

    # Lightweight ablation #5 config for fast selftest.
    cfg = CatBoostConfig(depth=4, iterations=200, learning_rate=0.1,
                         l2_leaf_reg=3, verbose=False,
                         early_stopping_rounds=None)
    fcst = CatBoostForecaster(cfg=cfg, horizon=12).fit(train, val_df=val)

    # Single-step predict
    r_a, r_c = fcst.predict(df.iloc[:cut + 100], horizon=12)
    assert isinstance(r_a, float) and isinstance(r_c, float), "predict() type"
    assert 0 < r_a < 0.5 and 0 < r_c < 0.5, f"predict() out of range: {r_a}, {r_c}"

    # Batch predict shape
    preds = fcst.predict_batch(val)
    assert preds.shape[1] == 2, f"bad batch shape: {preds.shape}"
    assert len(preds) > 0, "empty batch predict"

    # Compare predictions to realised on validation tail.
    Xv, Yv = build_features(val, horizon=12)
    aligned = Yv.loc[preds.index.intersection(Yv.index)]
    mae_a = float(np.mean(np.abs(preds.loc[aligned.index, "r_aave_tplus"]
                                  - aligned["r_aave_tplus"])))
    mae_c = float(np.mean(np.abs(preds.loc[aligned.index, "r_compound_tplus"]
                                  - aligned["r_compound_tplus"])))
    print(f"CatBoost selftest OK | val MAE aave={mae_a:.5f} compound={mae_c:.5f}, "
          f"n_features={len(fcst.feature_names_)}, n_preds={len(preds)}")


if __name__ == "__main__":
    _selftest()
