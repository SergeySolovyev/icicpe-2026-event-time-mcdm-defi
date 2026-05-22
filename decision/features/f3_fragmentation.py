"""F3 fragmentation features: cross-protocol APR spreads.

F3 in MacKenzie (2021) Table 3.2 = "same instrument across multiple
venues". In DeFi-lending, this maps directly to USDC supply APR across
Aave/Compound/Morpho/Euler/Spark/Fluid. Per the design spec, F3 IS our
decision variable: cross-protocol spread, dispersion, and immediate-
switching signals dominate F1 (rate-lead) and F4 (related instruments)
in the LOO ablation.

The builder reads the per-block panel and produces:

    one column per UNORDERED pair (i < j alphabetical):
        f3_spread_<i>_vs_<j> = panel[i_lending_apr] - panel[j_lending_apr]

    universe-level summaries:
        f3_spread_max_minus_min   max(all_aprs) - min(all_aprs) per block
        f3_spread_top2            max - runner_up (immediate switching)
        f3_dispersion_std         std of all available protocol APRs
        f3_top_protocol_id        float64 of the argmax index in the
                                  sorted-name list (deterministic)

Protocols are discovered dynamically from `<proto>_lending_apr` column
suffixes -- same pattern as `backtest/replay_per_block.py`. For a
partial panel (Morpho + Euler only) you get exactly 1 pair column;
for the full 6-protocol panel you get 15 pair columns (C(6,2)).
"""
from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd

from decision.features.base import SignalFeatureBuilder


class F3FragmentationBuilder(SignalFeatureBuilder):
    """Cross-protocol APR spread + dispersion features.

    Raises ValueError if the panel has fewer than 2 protocol APR
    columns -- with only 1 protocol there is no spread to compute.
    """

    family = "f3"

    def build(self, panel: pd.DataFrame) -> pd.DataFrame:
        protos = sorted(
            c.removesuffix("_lending_apr")
            for c in panel.columns
            if c.endswith("_lending_apr")
        )
        if len(protos) < 2:
            raise ValueError(
                f"F3FragmentationBuilder requires at least 2 "
                f"*_lending_apr columns, got {len(protos)} ({protos})"
            )

        # Index: block_number (int64). Preserve tz-aware block_timestamp
        # via .array (NOT .values -- per the Pandas tz-naive gotcha
        # documented in commit 911a7d7).
        index = pd.Index(
            panel["block_number"].to_numpy(dtype="int64"),
            name="block_number",
        )
        out: dict[str, np.ndarray | pd.array] = {}
        out["block_timestamp"] = panel["block_timestamp"].array

        # APR matrix in canonical (sorted) protocol order.
        apr_cols = [f"{p}_lending_apr" for p in protos]
        apr = panel[apr_cols].to_numpy(dtype="float64")  # (n, k)

        # One column per UNORDERED pair (i<j alphabetical).
        for i, j in combinations(range(len(protos)), 2):
            col = f"f3_spread_{protos[i]}_vs_{protos[j]}"
            out[col] = (apr[:, i] - apr[:, j]).astype("float64")

        # Universe-level summaries. nan-aware reductions: if a row has
        # all-NaN it stays NaN (consistent with NaN allowance in the
        # validator).
        with np.errstate(all="ignore"):
            row_max = np.nanmax(apr, axis=1)
            row_min = np.nanmin(apr, axis=1)
            row_std = np.nanstd(apr, axis=1, ddof=0)

            # Top-2 (max minus runner-up). For rows with all-NaN, the
            # sort yields NaN runner-up so the result is NaN. For rows
            # with exactly one non-NaN APR (would only happen with NaN
            # gaps in a multi-proto panel), top2 falls back to NaN as
            # there is no meaningful runner-up.
            # np.sort pushes NaNs to the end, so the largest finite
            # value is at index -1 and runner-up at -2.
            sorted_asc = np.sort(apr, axis=1)
            runner_up = sorted_asc[:, -2]
            top1 = sorted_asc[:, -1]
            top2 = top1 - runner_up

            # Deterministic top-protocol id: argmax in sorted-name order,
            # NaN treated as -inf so it loses.
            apr_safe = np.where(np.isnan(apr), -np.inf, apr)
            top_idx = np.argmax(apr_safe, axis=1).astype("float64")
            # If a row is all-NaN, argmax returns 0 spuriously; mark NaN.
            all_nan = np.isnan(apr).all(axis=1)
            top_idx[all_nan] = np.nan

        out["f3_spread_max_minus_min"] = (row_max - row_min).astype("float64")
        out["f3_spread_top2"] = top2.astype("float64")
        out["f3_dispersion_std"] = row_std.astype("float64")
        out["f3_top_protocol_id"] = top_idx

        return pd.DataFrame(out, index=index)
