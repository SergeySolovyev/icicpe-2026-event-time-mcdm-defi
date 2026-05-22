"""F1 lead features: DSR + sDAI / Curve 3pool proxies.

MacKenzie (2021) Table 3.2 "futures lead" class, mapped to DeFi: Maker's
DSR (Dai Savings Rate) empirically leads Aave / Compound USDC supply
rates by ~1-6 hours per Gudgeon et al. (2020), because Maker is the
upstream stablecoin issuer that sets the marginal opportunity cost for
DAI holders. sDAI exchange rate and Curve 3pool swap rate are proxies
for the same lead signal.

Output columns (all float64, prefix `f1_`):
    f1_dsr_apr                  current DSR rate, ffilled onto block grid
    f1_dsr_lag_300              DSR ~1 hour ago  (300 blocks)
    f1_dsr_lag_1800             DSR ~6 hours ago (1800 blocks)
    f1_dsr_delta_300            f1_dsr_apr - f1_dsr_lag_300
    f1_lead_spread_dsr_vs_top   DSR minus max protocol APR at the block
    f1_sdai_proxy_apr           STUB (NaN) — wired in a follow-up
    f1_curve_3pool_apr          STUB (NaN) — wired in a follow-up

The DSR signal is read from `data/cached/events_dsr.parquet` (Plan A
output). If the file is missing, all `f1_dsr_*` columns are NaN-filled
and a warning is emitted so downstream training picks up the gap.
"""
from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from decision.features.base import SignalFeatureBuilder, validate_feature_frame


_DEFAULT_DSR_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "cached"
    / "events_dsr.parquet"
)

# Lag spec (blocks). 12s blocks -> 300 ≈ 1 h, 1800 ≈ 6 h.
_LAG_1H = 300
_LAG_6H = 1800

_FEATURE_COLS = (
    "f1_dsr_apr",
    "f1_dsr_lag_300",
    "f1_dsr_lag_1800",
    "f1_dsr_delta_300",
    "f1_lead_spread_dsr_vs_top",
    "f1_sdai_proxy_apr",
    "f1_curve_3pool_apr",
)


class F1LeadBuilder(SignalFeatureBuilder):
    """Build F1 (lead-rate) features off the per-block panel + DSR events.

    The DSR file is event-sparse (typically <50 rows over 18 months), so
    we merge_asof onto the panel's block_number to forward-fill the rate
    onto the dense grid, then compute lags by integer index shift.
    """

    family = "f1"

    def __init__(self, dsr_events_path: Path | None = None) -> None:
        super().__init__()
        self.dsr_events_path: Path = (
            Path(dsr_events_path) if dsr_events_path is not None
            else _DEFAULT_DSR_PATH
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_dsr(self) -> pd.DataFrame | None:
        """Load DSR rate-change events; return None if file is missing.

        The file is produced by `data/fetch_dsr_events.py` with the
        Plan A event schema: block_number (int64), block_timestamp
        (datetime64[ns, UTC]), lending_rate_apr (float64), ... We only
        need (block_number, lending_rate_apr) for ffill.
        """
        if not self.dsr_events_path.exists():
            warnings.warn(
                f"F1LeadBuilder: DSR events file not found at "
                f"{self.dsr_events_path!s}; all f1_dsr_* columns will "
                f"be NaN. Run data/fetch_dsr_events.py to populate.",
                RuntimeWarning,
                stacklevel=2,
            )
            return None
        df = pd.read_parquet(self.dsr_events_path)
        required = {"block_number", "lending_rate_apr"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(
                f"DSR events file {self.dsr_events_path!s} missing "
                f"required columns {sorted(missing)}; got {df.columns.tolist()}"
            )
        # Keep only what we need, sorted on block_number (required by
        # merge_asof).
        out = df[["block_number", "lending_rate_apr"]].copy()
        out["block_number"] = out["block_number"].astype("int64")
        out["lending_rate_apr"] = out["lending_rate_apr"].astype("float64")
        out = out.sort_values("block_number").reset_index(drop=True)
        return out

    @staticmethod
    def _ffill_dsr_to_panel(
        panel_blocks: pd.Series, dsr: pd.DataFrame
    ) -> np.ndarray:
        """Forward-fill DSR rates onto the panel's block_number grid.

        merge_asof with direction='backward': for each panel block, take
        the most recent DSR event at or before that block. Blocks before
        the first known DSR event get NaN (correctly: we don't know the
        rate yet).
        """
        left = pd.DataFrame({"block_number": panel_blocks.astype("int64").to_numpy()})
        joined = pd.merge_asof(
            left,
            dsr,
            on="block_number",
            direction="backward",
        )
        return joined["lending_rate_apr"].to_numpy(dtype="float64")

    @staticmethod
    def _top_protocol_apr(panel: pd.DataFrame) -> np.ndarray:
        """Max(*_lending_apr) per row, NaN if no protocol has a value."""
        proto_cols = [c for c in panel.columns if c.endswith("_lending_apr")]
        if not proto_cols:
            return np.full(len(panel), np.nan, dtype="float64")
        arr = panel[proto_cols].to_numpy(dtype="float64")
        # All-NaN rows -> NaN; otherwise np.nanmax.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            top = np.nanmax(arr, axis=1)
        all_nan = np.all(np.isnan(arr), axis=1)
        top = np.where(all_nan, np.nan, top)
        return top.astype("float64")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def build(self, panel: pd.DataFrame) -> pd.DataFrame:
        if "block_number" not in panel.columns:
            raise ValueError("panel must have a 'block_number' column")
        if "block_timestamp" not in panel.columns:
            raise ValueError("panel must have a 'block_timestamp' column")

        n = len(panel)
        block_numbers = panel["block_number"].astype("int64")

        # --- DSR ffill onto block grid ---------------------------------
        dsr = self._load_dsr()
        if dsr is None or len(dsr) == 0:
            dsr_apr = np.full(n, np.nan, dtype="float64")
        else:
            dsr_apr = self._ffill_dsr_to_panel(block_numbers, dsr)

        # --- Lag features (positional shift on the dense block grid) ---
        # The panel is one row per block, so a 300-row shift == 300 blocks.
        dsr_series = pd.Series(dsr_apr)
        dsr_lag_300 = dsr_series.shift(_LAG_1H).to_numpy(dtype="float64")
        dsr_lag_1800 = dsr_series.shift(_LAG_6H).to_numpy(dtype="float64")
        dsr_delta_300 = (dsr_apr - dsr_lag_300).astype("float64")

        # --- Lead spread vs best protocol ------------------------------
        top_apr = self._top_protocol_apr(panel)
        lead_spread = (dsr_apr - top_apr).astype("float64")

        # --- Stub columns ---------------------------------------------
        nan_col = np.full(n, np.nan, dtype="float64")

        # NOTE: Pandas .values on a tz-aware datetime Series returns a
        # tz-NAIVE numpy array. Use .array to preserve the tz info
        # through DataFrame construction. The base validator rejects
        # tz-naive timestamps -- this is the documented gotcha.
        out = pd.DataFrame(
            {
                "block_timestamp": panel["block_timestamp"].array,
                "f1_dsr_apr": dsr_apr,
                "f1_dsr_lag_300": dsr_lag_300,
                "f1_dsr_lag_1800": dsr_lag_1800,
                "f1_dsr_delta_300": dsr_delta_300,
                "f1_lead_spread_dsr_vs_top": lead_spread,
                "f1_sdai_proxy_apr": nan_col,
                "f1_curve_3pool_apr": nan_col,
            },
            index=pd.Index(block_numbers.to_numpy(), name="block_number"),
        )

        # Enforce dtypes (defensive: avoid surprises on partial-NaN cols).
        for col in _FEATURE_COLS:
            if out[col].dtype != "float64":
                out[col] = out[col].astype("float64")

        validate_feature_frame(out, expected_family="f1")
        return out
