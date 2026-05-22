"""Maximum-likelihood Ornstein-Uhlenbeck process calibration.

OU: dS_t = kappa * (theta - S_t) dt + sigma dW_t
Closed-form MLE per Smith (2010), Iacus (2008). For dt=1 (per-block
sampling on Ethereum) the formulas simplify; the caller is responsible
for converting kappa to per-second / per-year if desired.

Krause prior anchor (literature-foundation.md S2): kappa ~ 2.1e-5
block^-1 (half-life ~33,000 blocks ~ 4.5 days). Realised MLE should
land within ~50% of this on real Aave-Compound spread data.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class OUParams:
    kappa: float
    theta: float
    sigma: float
    # Half-life in the same time unit as kappa (blocks if dt=1).
    @property
    def half_life(self) -> float:
        if self.kappa <= 0:
            return float("inf")
        return math.log(2.0) / self.kappa


class OUCalibrator:
    MIN_WINDOW = 50

    @staticmethod
    def fit(S: np.ndarray, *, dt: float = 1.0) -> OUParams:
        """MLE of (kappa, theta, sigma) from a 1-D series S (length >= 50)."""
        S = np.asarray(S, dtype=float)
        if S.ndim != 1 or len(S) < OUCalibrator.MIN_WINDOW:
            raise ValueError(
                f"need at least {OUCalibrator.MIN_WINDOW} observations, "
                f"got {len(S) if S.ndim == 1 else 'non-1d'}"
            )

        S_lag = S[:-1]
        S_now = S[1:]
        n = len(S_now)

        S_lag_bar = S_lag.mean()
        S_now_bar = S_now.mean()
        S_xx = np.sum((S_lag - S_lag_bar) ** 2)
        S_xy = np.sum((S_lag - S_lag_bar) * (S_now - S_now_bar))

        if S_xx < 1e-12:
            # Constant series -- no slope, theta = mean, kappa = 0.
            return OUParams(kappa=0.0, theta=float(S_lag_bar), sigma=0.0)

        b = S_xy / S_xx
        a = S_now_bar - b * S_lag_bar
        sigma_eps2 = np.mean((S_now - a - b * S_lag) ** 2)

        # Edge case: b >= 1 means the series is non-mean-reverting; pin kappa to 0.
        if b >= 1 - 1e-9:
            return OUParams(
                kappa=0.0,
                theta=float(S_now.mean()),
                sigma=float(np.sqrt(max(sigma_eps2, 0.0))),
            )
        if b <= 0:
            # Anti-correlated -- still mean-reverting but stronger; cap log carefully.
            kappa = -math.log(max(abs(b), 1e-9)) / dt
        else:
            kappa = -math.log(b) / dt

        theta = a / (1 - b)
        denom = 1 - b ** 2
        sigma = (
            math.sqrt(max(sigma_eps2 * 2 * kappa / denom, 0.0))
            if denom > 0
            else 0.0
        )

        return OUParams(kappa=float(kappa), theta=float(theta), sigma=float(sigma))
