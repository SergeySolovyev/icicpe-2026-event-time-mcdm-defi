"""MAIN STRATEGY — PredictiveMCDMStrategy (DL-forecast-driven MCDM allocator).

Headline contribution. The 4-factor MCDM scoring is identical to
baseline_mcdm_ema.py; the difference is that f_APY consumes the
12-hour-ahead DA-BiGRU-CNN forecast `r_hat(t+12h)` instead of the
EMA-smoothed current rate.

Forecaster I/O contract:
    Inputs:
        x_branch_a: (1, 168, 3) tensor of [eps_aave, eps_compound, eps_spread]
                    over a 7-day rolling window (168 hourly obs).
        x_branch_b: (1, 168, 7) tensor of [u_a, u_c, dTVL_a, dTVL_c, gas, sin, cos]
                    over the same window.
    Output:
        (1, 2, 2) tensor: [protocol][u_hat | eps_corr]

Reconstruction (closed-form, no params):
    r_hat_i = f_kink_i(u_hat_i, kink_params_i) + eps_corr_i

The forecaster is loaded from ONNX (CPU runtime) to avoid pulling torch
into the strategy path. The ONNX file is trained + exported by
forecaster/train.py + forecaster/export_onnx.py respectively.

During the 168-hour warm-up before the buffer is full, the strategy
falls back to spot rate (degrades gracefully to the same logic as
baseline_apy_greedy + MCDM cost/risk/stab factors).
"""
from __future__ import annotations

import json
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "extras" / "fractal_pr_lending_allocation"))
sys.path.insert(0, str(ROOT))

from base_lending_allocation import BaseLendingAllocationParams, BaseLendingAllocationStrategy  # noqa: E402
from data.features import AaveKinkParams, CompoundKinkParams, f_kink  # noqa: E402


@dataclass
class PredictiveMCDMParams(BaseLendingAllocationParams):
    """MCDM weights + forecast configuration."""

    # MCDM weights (Solovev 2026b § 4.4)
    W_APY: float = 0.40
    W_RISK: float = 0.25
    W_COST: float = 0.20
    W_STAB: float = 0.15

    APYMAX_NORM: float = 0.20
    GAS_PER_REBALANCE: int = 200_000
    GAS_MAX_ETH: float = 0.01

    # Forecaster
    FORECAST_MODEL_PATH: str = "forecaster/trained_models/dual_branch_kink.onnx"
    KINK_PARAMS_PATH: str = "data/cached/kink_params.json"
    SEQUENCE_LENGTH: int = 168                    # 7-day buffer
    FORECAST_HORIZON: int = 12                    # plan §1.5
    FORECAST_REFRESH_HOURS: int = 1               # how often to call ONNX


class PredictiveMCDMStrategy(BaseLendingAllocationStrategy):
    """Predictive MCDM with DA-BiGRU-CNN forecast feeding f_APY."""

    PARAMS_CLS = PredictiveMCDMParams

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Rolling buffers for the two forecaster branches. Each row is a
        # feature vector at one hourly observation.
        self._buf_a: deque = deque(maxlen=self._params.SEQUENCE_LENGTH)
        self._buf_b: deque = deque(maxlen=self._params.SEQUENCE_LENGTH)

        # Cached forecast outputs — refreshed every FORECAST_REFRESH_HOURS
        self._cached_r_hat: dict[str, float] = {}
        self._steps_since_refresh: int = 0

        # Per-refresh forecast log: list of
        #   {"timestamp": ts, "AAVE": (r_hat, r_spot), "COMPOUND": (r_hat, r_spot)}
        # Consumed by backtest.run_main._forecast_hit_rate (directional
        # accuracy, plan §9.3) and the forecast-quality battery (plan §9.4).
        self._forecast_history: list = []

        # Lazy-loaded ONNX session + kink params (initialised on first use)
        self._onnx_session = None
        self._kink_aave: Optional[AaveKinkParams] = None
        self._kink_compound: Optional[CompoundKinkParams] = None

    # ------------------------------------------------------------------
    # Lazy initialisation (defers heavy imports to runtime)
    # ------------------------------------------------------------------

    def _lazy_init_forecaster(self) -> None:
        import onnxruntime as ort

        sess_opts = ort.SessionOptions()
        sess_opts.intra_op_num_threads = 1
        sess_opts.inter_op_num_threads = 1
        sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        model_path = ROOT / self._params.FORECAST_MODEL_PATH
        if not model_path.exists():
            raise FileNotFoundError(
                f"Forecast ONNX not found at {model_path}. "
                f"Train via `python -m forecaster.train` and export via "
                f"`python -m forecaster.export_onnx` first."
            )
        self._onnx_session = ort.InferenceSession(
            str(model_path), sess_opts, providers=["CPUExecutionProvider"]
        )

        kink_path = ROOT / self._params.KINK_PARAMS_PATH
        if not kink_path.exists():
            raise FileNotFoundError(
                f"Kink params not found at {kink_path}. "
                f"Run `python -m data.fetch_kink_params` first."
            )
        kp = json.loads(kink_path.read_text())
        self._kink_aave = AaveKinkParams(**kp["aave"])
        self._kink_compound = CompoundKinkParams(**kp["compound"])

    def _kink_for(self, entity_name: str):
        if entity_name == "AAVE":
            return self._kink_aave
        if entity_name == "COMPOUND":
            return self._kink_compound
        raise KeyError(f"No kink params for entity {entity_name}")

    # ------------------------------------------------------------------
    # Per-step buffer update (called inside compute_criteria_vector via
    # a small trick: we only update once per timestep, on the first
    # entity_name accessed)
    # ------------------------------------------------------------------

    def _ingest_observation(self) -> None:
        """Build per-step feature vectors and push into both branch buffers."""
        if self._kink_aave is None or self._kink_compound is None:
            return  # cannot compute residuals yet

        gs_a = self.get_entity("AAVE").global_state
        gs_c = self.get_entity("COMPOUND").global_state

        r_a = float(getattr(gs_a, "lending_rate", 0.0)) * 365 * 24    # to annual APR
        r_c = float(getattr(gs_c, "lending_rate", 0.0)) * 365 * 24
        u_a = float(getattr(gs_a, "utilization", 0.0))
        u_c = float(getattr(gs_c, "utilization", 0.0))

        eps_a = r_a - float(f_kink(u_a, self._kink_aave))
        eps_c = r_c - float(f_kink(u_c, self._kink_compound))

        # Branch A: (eps_aave, eps_compound, eps_spread)
        self._buf_a.append([eps_a, eps_c, eps_a - eps_c])

        # Branch B context features (defaults if missing on the GlobalState)
        dTVL_a = float(getattr(gs_a, "delta_tvl_24h", 0.0))
        dTVL_c = float(getattr(gs_c, "delta_tvl_24h", 0.0))
        gas = float(getattr(gs_a, "gas_gwei", 30.0))                  # shared between protocols
        ts = self._current_timestamp
        hour = ts.hour if ts is not None else 12
        tod_sin = float(np.sin(2 * np.pi * hour / 24))
        tod_cos = float(np.cos(2 * np.pi * hour / 24))

        self._buf_b.append([u_a, u_c, dTVL_a, dTVL_c, gas, tod_sin, tod_cos])

    def _run_forecaster(self) -> Optional[dict[str, float]]:
        """Returns {entity_name: annualised r_hat(t+12h)} or None during warm-up."""
        if len(self._buf_a) < self._params.SEQUENCE_LENGTH:
            return None
        if self._onnx_session is None:
            self._lazy_init_forecaster()

        x_a = np.array(self._buf_a, dtype=np.float32)[None, :, :]    # (1, T, 3)
        x_b = np.array(self._buf_b, dtype=np.float32)[None, :, :]    # (1, T, 7)

        inputs = {"x_branch_a": x_a, "x_branch_b": x_b}
        # ONNX session output ordering must be (1, n_protocols, 2)
        out = self._onnx_session.run(None, inputs)[0]                # (1, 2, 2)
        u_hat = out[0, :, 0]            # (2,)  forecast utilizations
        eps_corr = out[0, :, 1]         # (2,)  residual correction

        r_hat_aave = float(f_kink(u_hat[0], self._kink_aave)) + float(eps_corr[0])
        r_hat_compound = float(f_kink(u_hat[1], self._kink_compound)) + float(eps_corr[1])
        return {"AAVE": r_hat_aave, "COMPOUND": r_hat_compound}

    # ------------------------------------------------------------------
    # MCDM sub-factors (identical to baseline_mcdm_ema except the APY input)
    # ------------------------------------------------------------------

    @staticmethod
    def _f_apy(annual_apr: float, apy_max: float) -> float:
        return float(np.clip(annual_apr / apy_max, 0.0, 1.0))

    @staticmethod
    def _f_risk(u: float) -> float:
        return float(1.0 - np.clip(u, 0.0, 1.0))

    @staticmethod
    def _f_cost(gas_gwei: float, gas_per_rebalance: int, gas_max_eth: float) -> float:
        gas_eth = gas_gwei * 1e-9 * gas_per_rebalance
        return float(1.0 - np.clip(gas_eth / gas_max_eth, 0.0, 1.0))

    @staticmethod
    def _f_stab(delta_tvl: float) -> float:
        return float(1.0 - np.clip(abs(delta_tvl) / 0.30, 0.0, 1.0))

    # ------------------------------------------------------------------
    # Hook implementations
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Orchestration: ingest + refresh BEFORE the base class iterates
    # entities. Keeps compute_criteria_vector pure (no side effects),
    # so subclass-overrides for ablations don't have to replicate the
    # ingest-on-first-entity trick.
    # ------------------------------------------------------------------

    def predict(self) -> "list[ActionToTake]":   # noqa: F821 — forward ref
        # Lazy init on first call. Tolerate missing ONNX during scaffolding
        # / warm-up so the strategy degrades to spot-rate without crashing.
        if self._onnx_session is None:
            try:
                self._lazy_init_forecaster()
            except FileNotFoundError:
                pass

        # Per-step buffer update + optional forecast refresh
        self._ingest_observation()
        if (
            len(self._buf_a) >= self._params.SEQUENCE_LENGTH
            and self._onnx_session is not None
            and self._steps_since_refresh % self._params.FORECAST_REFRESH_HOURS == 0
        ):
            forecast = self._run_forecaster()
            if forecast is not None:
                self._cached_r_hat = forecast
                # Log (r_hat, r_spot) per protocol so the offline forecast
                # battery can score it against the realized rate h steps ahead.
                entry = {"timestamp": self._current_timestamp}
                for _ent in ("AAVE", "COMPOUND"):
                    if _ent not in forecast:
                        continue
                    _gs = self.get_entity(_ent).global_state
                    _r_spot = float(getattr(_gs, "lending_rate", 0.0)) * 365 * 24
                    entry[_ent] = (float(forecast[_ent]), _r_spot)
                self._forecast_history.append(entry)
        self._steps_since_refresh += 1

        # Delegate to base class for the rest of the cycle. compute_criteria_vector
        # is now a pure reader of self._cached_r_hat + entity.global_state.
        return super().predict()

    def compute_criteria_vector(self, entity_name: str) -> np.ndarray:
        """Pure: read cached forecast (if any) + spot state; return MCDM vector."""
        gs = self.get_entity(entity_name).global_state
        u = float(getattr(gs, "utilization", 0.0))
        gas = float(getattr(gs, "gas_gwei", 30.0))
        delta_tvl = float(getattr(gs, "delta_tvl_24h", 0.0))

        # Forecast > spot fallback during warm-up
        if entity_name in self._cached_r_hat:
            annual = self._cached_r_hat[entity_name]
        else:
            rate = float(getattr(gs, "lending_rate", 0.0))
            annual = rate * 365 * 24

        return np.array([
            self._f_apy(annual, self._params.APYMAX_NORM),
            self._f_risk(u),
            self._f_cost(gas, self._params.GAS_PER_REBALANCE, self._params.GAS_MAX_ETH),
            self._f_stab(delta_tvl),
        ])

    def aggregate_criteria(self, criteria_matrix: np.ndarray) -> np.ndarray:
        """SAW (Simple Additive Weighting), per Solovev 2026b Eq. 15."""
        weights = np.array([
            self._params.W_APY,
            self._params.W_RISK,
            self._params.W_COST,
            self._params.W_STAB,
        ])
        return criteria_matrix @ weights


__all__ = ["PredictiveMCDMStrategy", "PredictiveMCDMParams"]
