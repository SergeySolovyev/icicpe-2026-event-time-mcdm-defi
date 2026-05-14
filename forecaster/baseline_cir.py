"""CIR (Cox-Ingersoll-Ross) baseline with data-driven partitioning.

Implements Orlando-Mininni-Bufalo (2020) "Forecasting interest rates through
Vasicek and CIR models: a partitioning approach" (J. Forecasting 39(4))
adapted for DeFi supply rates (DEEP_RESEARCH.md S II.B, S VI.A).

Methodology:
  1. Partition historical rate series into sub-groups either by variance-
     change detection (Orlando 2020 default) or by utilization quintile
     (DeFi-native variant per PROJECT_2_PLAN.md S7 Baseline D).
  2. Calibrate CIR parameters (a, b, sigma) per partition via MLE on the
     Euler-Maruyama discretisation of dr = a*(b - r) dt + sigma*sqrt(r) dW.
  3. Forecast: identify current partition, simulate CIR trajectory `horizon`
     hours forward, take Monte-Carlo MEAN as point forecast.

This is baseline D in PROJECT_2_PLAN.md S7. Tests whether deep learning
adds value over a regime-aware classical model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal, Sequence

import numpy as np
import pandas as pd
from scipy import optimize, stats

PartitioningKind = Literal["data-driven", "utilization", "none"]
DT_HOURLY = 1.0 / (365.0 * 24.0)            # one hour as fraction of year


# ---------------------------------------------------------------------------
# Per-partition CIR parameter container
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CIRParams:
    a: float          # mean-reversion speed
    b: float          # long-run mean
    sigma: float      # volatility (must satisfy 2ab > sigma^2 for Feller)
    n_obs: int = 0    # observations the partition was fit on

    def feller_ok(self) -> bool:
        return 2.0 * self.a * self.b > self.sigma ** 2


# ---------------------------------------------------------------------------
# CIR MLE on Euler-discretised increments
# ---------------------------------------------------------------------------

def _cir_neg_log_likelihood(
    params: np.ndarray,
    r: np.ndarray,
    dt: float,
) -> float:
    """Negative log-likelihood under Euler-Maruyama approximation.

    dr_t = a (b - r_t) dt + sigma sqrt(r_t) dW_t
       =>  r_{t+1} | r_t  ~  N( r_t + a(b - r_t)dt,  sigma^2 r_t dt )

    Used because the exact non-central chi-square density is heavy to
    optimise and the Euler approximation is standard in Orlando (2020).
    """
    a, b, sigma = params
    if a <= 0 or b <= 0 or sigma <= 0:
        return 1e10
    r_prev = r[:-1]
    r_next = r[1:]
    r_prev_safe = np.clip(r_prev, 1e-9, None)
    mean = r_prev + a * (b - r_prev) * dt
    var = (sigma ** 2) * r_prev_safe * dt
    var = np.clip(var, 1e-12, None)
    nll = 0.5 * np.sum(np.log(2 * np.pi * var) + (r_next - mean) ** 2 / var)
    if not np.isfinite(nll):
        return 1e10
    return float(nll)


def _fit_cir_single(r: np.ndarray, dt: float = DT_HOURLY) -> CIRParams:
    """Fit a single CIR on a clipped non-negative series."""
    r = np.asarray(r, dtype=np.float64)
    r = r[np.isfinite(r)]
    r = np.clip(r, 1e-9, None)
    if len(r) < 30:
        # Degenerate partition: collapse to a near-deterministic CIR around the mean.
        mean = float(np.maximum(r.mean() if len(r) else 1e-4, 1e-6))
        return CIRParams(a=1.0, b=mean, sigma=1e-4, n_obs=len(r))

    # Initial guess: method of moments.
    mean = float(r.mean())
    var = float(r.var() + 1e-12)
    a0 = 1.0
    b0 = max(mean, 1e-6)
    sigma0 = max(np.sqrt(2.0 * a0 * var / mean), 1e-4)

    res = optimize.minimize(
        _cir_neg_log_likelihood,
        x0=np.array([a0, b0, sigma0]),
        args=(r, dt),
        method="L-BFGS-B",
        bounds=[(1e-4, 50.0), (1e-6, 1.0), (1e-6, 5.0)],
    )
    a, b, sigma = res.x
    return CIRParams(a=float(a), b=float(b), sigma=float(sigma), n_obs=len(r))


# ---------------------------------------------------------------------------
# Partitioning
# ---------------------------------------------------------------------------

def _variance_change_partition(r: np.ndarray, n_partitions: int) -> np.ndarray:
    """Partition by rolling-variance quantile bins (Orlando-style proxy).

    Computes a 24-h rolling variance, then bins the series by quantile
    of that variance. Returns an int array of partition labels of len(r).
    """
    s = pd.Series(np.asarray(r, dtype=np.float64))
    rv = s.rolling(24, min_periods=4).var().bfill().fillna(s.var())
    # qcut may fail on degenerate input -> fall back to single partition.
    try:
        labels = pd.qcut(rv, q=n_partitions, labels=False, duplicates="drop")
    except ValueError:
        return np.zeros(len(r), dtype=np.int64)
    return labels.fillna(0).astype(np.int64).to_numpy()


def _utilization_partition(u: np.ndarray, n_partitions: int) -> np.ndarray:
    """Partition by utilization quintile (PROJECT_2_PLAN.md S7 Baseline D)."""
    try:
        labels = pd.qcut(pd.Series(u), q=n_partitions, labels=False, duplicates="drop")
    except ValueError:
        return np.zeros(len(u), dtype=np.int64)
    return labels.fillna(0).astype(np.int64).to_numpy()


# ---------------------------------------------------------------------------
# Top-level fit function
# ---------------------------------------------------------------------------

@dataclass
class CIRFitResult:
    """Per-partition params plus the partition assignment function + a
    `predict(r_t, horizon)` callable."""
    params_per_partition: dict[int, CIRParams]
    partitioning: PartitioningKind
    n_partitions: int
    dt: float
    # The bin edges of the partitioning variable, used to classify a NEW
    # observation at predict() time. None if partitioning='none'.
    bin_edges: np.ndarray | None = None
    # Saved series for proximity-based classification fallback.
    _ref_partition_means: dict[int, float] = field(default_factory=dict)

    def assign_partition(self, value: float) -> int:
        if self.partitioning == "none" or self.bin_edges is None:
            return 0
        idx = int(np.digitize(value, self.bin_edges[1:-1]))
        return max(0, min(idx, self.n_partitions - 1))

    def predict(
        self,
        r_t: float,
        horizon: int = 12,
        partition_key: float | None = None,
        n_paths: int = 500,
        seed: int = 0,
    ) -> float:
        """Monte-Carlo mean of CIR after `horizon` Euler steps."""
        rng = np.random.default_rng(seed)
        if partition_key is None:
            partition_key = float(r_t)
        k = self.assign_partition(partition_key)
        p = self.params_per_partition.get(k, next(iter(self.params_per_partition.values())))
        r = np.full(n_paths, max(float(r_t), 1e-9))
        for _ in range(horizon):
            drift = p.a * (p.b - r) * self.dt
            noise = p.sigma * np.sqrt(np.clip(r, 0, None) * self.dt) * rng.standard_normal(n_paths)
            r = np.clip(r + drift + noise, 1e-9, None)
        return float(r.mean())


def fit_cir(
    r_series: pd.Series | np.ndarray | Sequence[float],
    partitioning: PartitioningKind = "data-driven",
    n_partitions: int = 3,
    utilization_series: pd.Series | np.ndarray | None = None,
    dt: float = DT_HOURLY,
) -> CIRFitResult:
    """Partition the rate series and fit one CIR per partition.

    Args:
        r_series: hourly rate series (annualised, non-negative).
        partitioning: "data-driven" (variance-change), "utilization"
            (requires utilization_series), or "none" (single CIR).
        n_partitions: number of partitions.
        utilization_series: required if partitioning='utilization'.
        dt: time step (default hourly, in years).

    Returns:
        CIRFitResult with `.predict(r_t, horizon)` callable.
    """
    r = np.asarray(r_series, dtype=np.float64)
    r = np.clip(r, 1e-9, None)

    if partitioning == "none" or n_partitions == 1:
        params = {0: _fit_cir_single(r, dt)}
        return CIRFitResult(
            params_per_partition=params,
            partitioning="none",
            n_partitions=1,
            dt=dt,
            bin_edges=None,
        )

    if partitioning == "utilization":
        if utilization_series is None:
            raise ValueError("utilization_series required for partitioning='utilization'")
        partition_var = np.asarray(utilization_series, dtype=np.float64)
        labels = _utilization_partition(partition_var, n_partitions)
    else:
        labels = _variance_change_partition(r, n_partitions)
        # for "data-driven" we partition on the rate's own rolling variance,
        # so at predict() time we will route by r_t value as a coarse proxy.
        partition_var = r

    params_per_partition: dict[int, CIRParams] = {}
    for k in np.unique(labels):
        mask = labels == k
        if mask.sum() < 5:
            continue
        params_per_partition[int(k)] = _fit_cir_single(r[mask], dt)

    if not params_per_partition:                  # safety: empty -> single
        params_per_partition = {0: _fit_cir_single(r, dt)}

    edges = np.quantile(partition_var, np.linspace(0.0, 1.0, n_partitions + 1))

    return CIRFitResult(
        params_per_partition=params_per_partition,
        partitioning=partitioning,
        n_partitions=len(params_per_partition),
        dt=dt,
        bin_edges=edges,
    )


# ---------------------------------------------------------------------------
# Forecaster wrapper (predict-API parity with DABiGRUCNNForecaster)
# ---------------------------------------------------------------------------

class CIRForecaster:
    """SCALAR per-protocol CIR forecaster.

    Same I/O contract as DABiGRUCNNForecaster but for scalar input:
        forecaster = CIRForecaster()
        forecaster.fit(rate_series, utilization_series=...)
        r_hat = forecaster.predict(history, horizon=12)
    """

    def __init__(
        self,
        partitioning: PartitioningKind = "data-driven",
        n_partitions: int = 3,
        n_paths: int = 500,
        seed: int = 0,
    ):
        self.partitioning = partitioning
        self.n_partitions = n_partitions
        self.n_paths = n_paths
        self.seed = seed
        self.fit_result: CIRFitResult | None = None

    def fit(
        self,
        rate_series: pd.Series | np.ndarray,
        utilization_series: pd.Series | np.ndarray | None = None,
    ) -> "CIRForecaster":
        self.fit_result = fit_cir(
            rate_series,
            partitioning=self.partitioning,
            n_partitions=self.n_partitions,
            utilization_series=utilization_series,
        )
        return self

    def predict(self, history: pd.Series | np.ndarray, horizon: int = 12) -> float:
        if self.fit_result is None:
            raise RuntimeError("CIRForecaster.fit() must be called before predict().")
        history = np.asarray(history, dtype=np.float64)
        if history.size == 0:
            raise ValueError("history is empty")
        r_t = float(history[-1])
        return self.fit_result.predict(r_t, horizon=horizon,
                                       partition_key=r_t,
                                       n_paths=self.n_paths,
                                       seed=self.seed)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _simulate_cir_path(a: float, b: float, sigma: float, r0: float,
                      n_steps: int, dt: float, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    r = np.empty(n_steps)
    r[0] = r0
    for t in range(1, n_steps):
        drift = a * (b - r[t-1]) * dt
        noise = sigma * np.sqrt(max(r[t-1], 0) * dt) * rng.standard_normal()
        r[t] = max(r[t-1] + drift + noise, 1e-9)
    return r


def _selftest() -> None:
    # Simulate a known CIR path (annual params, hourly dt).
    n = 4000
    true_a, true_b, true_sigma = 3.0, 0.04, 0.10
    r0 = 0.05
    series = _simulate_cir_path(true_a, true_b, true_sigma, r0,
                                n, DT_HOURLY, seed=42)

    half = n // 2
    fcst = CIRForecaster(partitioning="none", n_partitions=1, n_paths=300).fit(series[:half])

    # Predict 12h-ahead at each midpoint anchor on the second half.
    horizon = 12
    preds = []
    truth = []
    for t in range(half, n - horizon, 24):
        preds.append(fcst.predict(series[max(0, t-200):t+1], horizon=horizon))
        truth.append(series[t + horizon])
    preds = np.array(preds); truth = np.array(truth)
    mae = float(np.mean(np.abs(preds - truth)))
    # CIR around b=4% with sigma=10%: realistic horizon-12h MAE well under 1%.
    assert mae < 0.02, f"CIR forecaster MAE too high: {mae:.4f}"

    # Naive last-value baseline
    naive = np.array([series[t] for t in range(half, n - horizon, 24)])
    naive_mae = float(np.mean(np.abs(naive - truth)))
    fitted = fcst.fit_result.params_per_partition[0]
    print(
        f"CIR baseline selftest OK | true (a={true_a}, b={true_b:.3f}, "
        f"sigma={true_sigma:.3f}) -> fitted (a={fitted.a:.2f}, "
        f"b={fitted.b:.3f}, sigma={fitted.sigma:.3f})"
    )
    print(f"  12h-ahead MAE: CIR {mae:.4f}  vs  naive last-value {naive_mae:.4f}")


if __name__ == "__main__":
    _selftest()
