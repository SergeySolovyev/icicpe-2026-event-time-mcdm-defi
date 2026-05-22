"""Tests for the per-block panel stitcher.

The stitcher takes N event-frames (one per protocol) and emits a uniform
per-block dataframe. It must:
  1. Forward-fill each protocol's columns onto every block.
  2. Resolve fetch-time sentinel block_number=-1 via ts->block lookup.
  3. Re-cumcount event_idx within (block_number, protocol) to preserve
     the schema's uniqueness invariant after block resolution.
"""
import pandas as pd
import pytest

from data.event_schema import EVENT_ROW_DTYPES, empty_event_frame
from data.build_per_block_panel import build_per_block_panel


def _mini_event(block, ts, protocol, lending, borrowing, util, event_idx=0):
    """Build a single-row EventRow frame for the test fixtures."""
    return pd.DataFrame([{
        "block_number": block,
        "block_timestamp": pd.Timestamp(ts, tz="UTC"),
        "event_idx": event_idx,
        "protocol": protocol,
        "event_type": "rate_update",
        "lending_rate_apr": lending,
        "borrowing_rate_apr": borrowing,
        "utilization": util,
        "total_supplied_usd": 1e9,
        "total_borrowed_usd": util * 1e9,
        "tx_hash": "",
        "source": "subgraph",
    }]).astype(EVENT_ROW_DTYPES)


def test_stitch_two_protocols_forward_fill():
    """Aave event at block 100; Compound event at block 102; check ffill."""
    aave = _mini_event(100, "2025-01-01 00:00:00", "aave_v3", 0.04, 0.05, 0.80)
    comp = _mini_event(102, "2025-01-01 00:00:24", "compound_v3", 0.05, 0.06, 0.70)
    panel = build_per_block_panel(
        event_frames=[aave, comp],
        block_start=100,
        block_end=105,
    )
    assert len(panel) == 5  # blocks 100..104

    # Aave value present from block 100 onward.
    assert panel.loc[panel["block_number"] == 100, "aave_v3_lending_apr"].iloc[0] == 0.04
    assert panel.loc[panel["block_number"] == 104, "aave_v3_lending_apr"].iloc[0] == 0.04

    # Compound value: NaN before its event, present after.
    assert pd.isna(panel.loc[panel["block_number"] == 101, "compound_v3_lending_apr"].iloc[0])
    assert panel.loc[panel["block_number"] == 103, "compound_v3_lending_apr"].iloc[0] == 0.05


def test_stitch_empty_inputs_returns_grid_only():
    """Empty frames should yield a grid with no protocol columns."""
    panel = build_per_block_panel(
        event_frames=[empty_event_frame(), empty_event_frame()],
        block_start=0, block_end=10,
    )
    assert len(panel) == 10
    # No protocol columns added since both frames were empty.
    proto_cols = [c for c in panel.columns if "_lending_apr" in c]
    assert proto_cols == []


def test_stitch_resolves_sentinel_block_numbers():
    """Fetch-time sentinel -1 must be resolved to a real block via ts->block."""
    # Use a timestamp well after the PoS genesis (2022-09-15).
    ts = pd.Timestamp("2025-01-01 00:00:00", tz="UTC")
    frame = pd.DataFrame([{
        "block_number": -1,  # sentinel from fetcher
        "block_timestamp": ts,
        "event_idx": 0,
        "protocol": "aave_v3",
        "event_type": "rate_update",
        "lending_rate_apr": 0.04,
        "borrowing_rate_apr": 0.05,
        "utilization": 0.5,
        "total_supplied_usd": 1e9,
        "total_borrowed_usd": 5e8,
        "tx_hash": "",
        "source": "subgraph",
    }]).astype(EVENT_ROW_DTYPES)

    # Approximate block: (2025-01-01 - 2022-09-15) seconds / 12 + 15_537_393
    expected_block = 15_537_393 + (int(ts.timestamp()) - 1663224162) // 12

    panel = build_per_block_panel(
        event_frames=[frame],
        block_start=expected_block,
        block_end=expected_block + 3,
    )
    # The resolved block should appear in the panel with the lending rate set.
    val_at_block = panel.loc[
        panel["block_number"] == expected_block, "aave_v3_lending_apr"
    ].iloc[0]
    assert val_at_block == 0.04


def test_stitch_recumcounts_event_idx_after_block_resolution():
    """Regression test for the Task A2 schema-bug fix.

    Several fetcher rows share (block_number=-1, protocol="aave_v3") with
    unique within-frame event_idx (5, 7, 11). After ts->block resolution,
    they may all collapse to the same real block number. The stitcher
    must re-cumcount event_idx within (block_number, protocol) so the
    dedup invariant survives.
    """
    # Three Aave rows in the SAME 12-second block (one Ethereum block).
    ts_base = pd.Timestamp("2025-01-01 00:00:00", tz="UTC")
    rows = []
    for i, evt_idx in enumerate([5, 7, 11]):  # non-contiguous fetch-time idx
        rows.append({
            "block_number": -1,
            "block_timestamp": ts_base + pd.Timedelta(seconds=i * 2),
            "event_idx": evt_idx,
            "protocol": "aave_v3",
            "event_type": "rate_update",
            "lending_rate_apr": 0.04 + 0.001 * i,
            "borrowing_rate_apr": 0.05 + 0.001 * i,
            "utilization": 0.5,
            "total_supplied_usd": 1e9,
            "total_borrowed_usd": 5e8,
            "tx_hash": "",
            "source": "subgraph",
        })
    frame = pd.DataFrame(rows).astype(EVENT_ROW_DTYPES)

    expected_block = 15_537_393 + (int(ts_base.timestamp()) - 1663224162) // 12

    # Stitcher should not raise -- after re-cumcount, three rows in the
    # same block get event_idx = 0, 1, 2 within (block_number, protocol).
    panel = build_per_block_panel(
        event_frames=[frame],
        block_start=expected_block,
        block_end=expected_block + 2,
    )
    # The panel keeps last-wins semantics -- the LAST of the three (i=2)
    # is what appears at the resolved block.
    val = panel.loc[
        panel["block_number"] == expected_block, "aave_v3_lending_apr"
    ].iloc[0]
    assert abs(val - 0.042) < 1e-9, f"expected last-wins 0.042, got {val}"


def test_stitch_rejects_inverted_window():
    """block_end must be > block_start."""
    with pytest.raises(ValueError, match="block_end must be"):
        build_per_block_panel(
            event_frames=[empty_event_frame()],
            block_start=100,
            block_end=50,
        )
