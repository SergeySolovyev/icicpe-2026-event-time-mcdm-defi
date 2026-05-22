"""Stitch per-event rate frames from N protocols into a uniform per-block panel.

Each input event frame conforms to `data.event_schema.EVENT_ROW_DTYPES`.
For each protocol, we:

  1. Resolve fetch-time sentinel `block_number == -1` via ts->block lookup.
  2. Re-cumcount `event_idx` within (block_number, protocol) so the
     schema's dedup invariant survives the block resolution.
  3. Take the last-wins value per (block_number, protocol) -- this matches
     Kyle's batch-auction semantics: each Ethereum block is one batch and
     the IRM sets one clearing rate per block.
  4. Forward-fill onto the uniform [block_start, block_end) grid.

Output schema (1 row per block):
    block_number          int64
    block_timestamp       datetime64[ns, UTC]
    <protocol>_lending_apr    float64  (one column per protocol present)
    <protocol>_borrow_apr     float64
    <protocol>_utilization    float64
    <protocol>_tvl_usd        float64

PoS-merge anchor: block 15_537_393 at UTC 2022-09-15 06:42:42 (timestamp
1663224162). Pre-merge timestamps would be inaccurate via the 12s/block
linear model; the panel is only intended for the post-merge window
covered by this study (Nov 2024 onward).
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd

from data.event_schema import EVENT_ROW_DTYPES, validate_event_frame

POS_GENESIS_TS = 1663224162
POS_GENESIS_BLOCK = 15_537_393


def _block_to_ts(block: int) -> pd.Timestamp:
    """Approx block-number -> UTC timestamp (post-PoS, 12s/block)."""
    return pd.Timestamp(
        POS_GENESIS_TS + (block - POS_GENESIS_BLOCK) * 12,
        unit="s",
        tz="UTC",
    )


def _ts_to_block(ts: int) -> int:
    """Approx UTC unix timestamp -> block number (post-PoS, 12s/block)."""
    return POS_GENESIS_BLOCK + (ts - POS_GENESIS_TS) // 12


def _fill_block_numbers(df: pd.DataFrame) -> pd.DataFrame:
    """Replace sentinel `block_number == -1` with the ts->block estimate."""
    if df.empty:
        return df
    needs_fill = df["block_number"] < 0
    if needs_fill.any():
        ts_unix = (
            df.loc[needs_fill, "block_timestamp"].astype("int64") // 10**9
        )
        df.loc[needs_fill, "block_number"] = (
            ts_unix.apply(_ts_to_block).astype("int64")
        )
    return df


def _recumcount_event_idx(df: pd.DataFrame) -> pd.DataFrame:
    """Re-assign event_idx as cumcount within (block_number, protocol).

    Required for the schema dedup invariant to survive block_number
    resolution. If a fetcher had three rows with (block=-1, idx={5,7,11})
    that all map to the same real block, after the cumcount they become
    idx={0,1,2} which preserves uniqueness on (block, idx, protocol).
    """
    if df.empty:
        return df
    df = df.sort_values(
        ["block_number", "block_timestamp", "event_idx"], kind="stable"
    ).reset_index(drop=True)
    df["event_idx"] = (
        df.groupby(["block_number", "protocol"], observed=True)
        .cumcount()
        .astype("int32")
    )
    return df


def build_per_block_panel(
    *,
    event_frames: Iterable[pd.DataFrame],
    block_start: int,
    block_end: int,
) -> pd.DataFrame:
    """Stitch N protocol event frames into a uniform per-block panel.

    Args:
        event_frames: iterable of dataframes, each matching EVENT_ROW_DTYPES.
            All rows in a single frame must share the same `protocol`
            category value.
        block_start: inclusive lower block bound.
        block_end: exclusive upper block bound.

    Returns:
        Dataframe with `block_number`, `block_timestamp`, and four
        ffilled float64 columns per protocol present in `event_frames`.
        Empty frames contribute no columns.
    """
    if block_end <= block_start:
        raise ValueError(
            f"block_end must be > block_start, got [{block_start}, {block_end})"
        )

    grid = pd.DataFrame({"block_number": range(block_start, block_end)})
    grid["block_timestamp"] = grid["block_number"].apply(_block_to_ts)
    grid = grid.set_index("block_number")

    panel = grid.copy()

    for frame in event_frames:
        if frame is None or frame.empty:
            continue

        # Resolve sentinel block_numbers BEFORE validating (validator
        # requires uniqueness on the resolved key, but the fetch-time
        # sentinel state is also legal per the schema -- this is a
        # *transformation* not a contract violation).
        frame = _fill_block_numbers(frame.copy())
        frame = _recumcount_event_idx(frame)

        # Now the frame is in stitcher-time form: real block_numbers,
        # cumulative-within-block event_idx. Validate before reducing.
        validate_event_frame(frame)

        proto = str(frame["protocol"].iloc[0])

        # Per-block last-wins reduction (Kyle batch-auction semantic).
        sub = (
            frame.groupby("block_number", as_index=True)
            .last()[[
                "lending_rate_apr",
                "borrowing_rate_apr",
                "utilization",
                "total_supplied_usd",
            ]]
        )
        sub.columns = [
            f"{proto}_lending_apr",
            f"{proto}_borrow_apr",
            f"{proto}_utilization",
            f"{proto}_tvl_usd",
        ]

        # Align to the master grid and forward-fill into the gaps.
        sub = sub.reindex(panel.index).ffill()
        panel = panel.join(sub, how="left")

    return panel.reset_index()
