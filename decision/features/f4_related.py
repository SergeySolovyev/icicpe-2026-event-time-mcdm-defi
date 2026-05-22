"""F4 (related) signal features: gas regime + stablecoin peg deviations.

MacKenzie (2021) Table 3.2 class F4 = "correlated instruments". For the
DeFi-lending switching problem the most directly correlated instruments
are:

    * gas price (ETH-denominated cost of executing the switch itself)
    * ETH/USD (drives the USD value of the gas burn)
    * stablecoin peg deviations (USDC, USDT) -- a depeg is a stress
      regime where APRs spike and switching dynamics change.

Feature columns produced (all float64, prefix ``f4_``):

    f4_gas_gwei          current gas price (NaN if missing from panel)
    f4_gas_log10         log10(max(gas_gwei, 1e-3)) -- right-skew tame
    f4_gas_quantile_30d  rank vs trailing 30 days of blocks in [0,1]
    f4_eth_usd           ETH/USD price (NaN if missing)
    f4_usdc_peg_dev_bps  (usdc_peg - 1.0) * 10_000 (NaN if missing)
    f4_usdt_peg_dev_bps  same for USDT

DEFERRED (per Plan C Task 4 scope):
    Top-LP wallet activity (per-pool subgraph queries that risk cost
    overruns). Documented in the design spec as F4-extension work to be
    picked up after the paper draft locks.

Protocol-tolerant pattern (same as F1 + F3 builders): if the per-block
panel is missing any of the input columns
(``gas_price_gwei``, ``eth_usd``, ``usdc_peg``, ``usdt_peg``), the
corresponding feature columns are emitted as NaN-filled float64 with a
``UserWarning``, rather than raising. This keeps the builder runnable
against partial historical panels.

Pandas timezone gotcha (Plan C Task 1 documented):
    ``pd.Series[datetime64[ns, UTC]].values`` returns a **tz-naive**
    numpy ndarray (it strips the tz). The validator rejects tz-naive
    timestamps. Use ``.array`` (or the Series itself) to preserve tz.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from decision.features.base import SignalFeatureBuilder


# ~30 days at 12-second blocks = 30 * 24 * 3600 / 12 = 216_000 blocks.
_BLOCKS_30D = 30 * 24 * 3600 // 12


class F4RelatedBuilder(SignalFeatureBuilder):
    """Build F4 (related-instrument) features from the per-block panel.

    Inputs (all optional; NaN-emitting if absent):
        gas_price_gwei, eth_usd, usdc_peg, usdt_peg

    Output: DataFrame indexed by ``block_number`` (int64, monotonic),
    with ``block_timestamp`` (tz-aware UTC) + 6 float64 ``f4_*`` columns.
    """

    family = "f4"

    def build(self, panel: pd.DataFrame) -> pd.DataFrame:
        if "block_number" not in panel.columns:
            raise ValueError("panel must have a 'block_number' column")
        if "block_timestamp" not in panel.columns:
            raise ValueError("panel must have a 'block_timestamp' column")

        n = len(panel)
        block_index = pd.Index(
            panel["block_number"].to_numpy(dtype="int64"),
            name="block_number",
        )

        # Preserve tz-aware timestamps. Note: .values strips the tz on
        # datetime64[ns, UTC] columns -- use .array instead (documented
        # in the module docstring).
        ts = panel["block_timestamp"]
        if not pd.api.types.is_datetime64_any_dtype(ts):
            raise ValueError(
                f"panel.block_timestamp must be datetime, got {ts.dtype}"
            )
        if getattr(ts.dt, "tz", None) is None:
            raise ValueError(
                "panel.block_timestamp must be tz-aware UTC"
            )

        out = pd.DataFrame(index=block_index)
        out["block_timestamp"] = ts.array

        # --- Gas features --------------------------------------------------
        if "gas_price_gwei" in panel.columns:
            gas = panel["gas_price_gwei"].to_numpy(dtype="float64")
        else:
            warnings.warn(
                "panel missing 'gas_price_gwei'; emitting NaN-filled "
                "f4_gas_gwei / f4_gas_log10 / f4_gas_quantile_30d",
                UserWarning,
                stacklevel=2,
            )
            gas = np.full(n, np.nan, dtype="float64")

        out["f4_gas_gwei"] = gas
        # log10 with a floor so low/zero gas doesn't blow up to -inf.
        floored = np.where(np.isnan(gas), np.nan, np.maximum(gas, 1e-3))
        out["f4_gas_log10"] = np.log10(floored).astype("float64")

        # Trailing 30-day quantile rank (pct) over ~216k blocks.
        gas_series = pd.Series(gas, index=block_index, dtype="float64")
        # min_periods=window forces NaN until the window is fully populated
        # (regression for "rank of current gas vs trailing 30 days"; an
        # incomplete window is not a valid quantile reference).
        out["f4_gas_quantile_30d"] = (
            gas_series.rolling(_BLOCKS_30D, min_periods=_BLOCKS_30D)
            .rank(pct=True)
            .astype("float64")
            .to_numpy()
        )

        # --- ETH/USD -------------------------------------------------------
        if "eth_usd" in panel.columns:
            out["f4_eth_usd"] = panel["eth_usd"].to_numpy(dtype="float64")
        else:
            warnings.warn(
                "panel missing 'eth_usd'; emitting NaN-filled f4_eth_usd",
                UserWarning,
                stacklevel=2,
            )
            out["f4_eth_usd"] = np.full(n, np.nan, dtype="float64")

        # --- Stablecoin peg deviations (bps) -------------------------------
        for stable in ("usdc", "usdt"):
            src_col = f"{stable}_peg"
            dst_col = f"f4_{stable}_peg_dev_bps"
            if src_col in panel.columns:
                peg = panel[src_col].to_numpy(dtype="float64")
                out[dst_col] = ((peg - 1.0) * 10_000.0).astype("float64")
            else:
                warnings.warn(
                    f"panel missing {src_col!r}; emitting NaN-filled "
                    f"{dst_col}",
                    UserWarning,
                    stacklevel=2,
                )
                out[dst_col] = np.full(n, np.nan, dtype="float64")

        return out
