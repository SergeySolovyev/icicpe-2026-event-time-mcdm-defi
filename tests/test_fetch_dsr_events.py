"""Tests for data/fetch_dsr_events.py (Task A9, Signal F1)."""
from __future__ import annotations

import os

import pandas as pd
import pytest

from data.event_schema import validate_event_frame
from data.fetch_dsr_events import fetch_dsr_events


@pytest.mark.network
def test_fetch_dsr_events_window_smoke():
    """Pull DSR changes in a 6-month window -- expect >=1 event."""
    if not os.environ.get("ETHEREUM_RPC_URL"):
        pytest.skip("ETHEREUM_RPC_URL not set")
    start = pd.Timestamp("2024-11-01", tz="UTC")
    end = pd.Timestamp("2025-05-01", tz="UTC")
    df = fetch_dsr_events(start=start, end=end)
    assert len(df) >= 1, f"expected >=1 DSR change in 6 months, got {len(df)}"
    assert (df["protocol"] == "dsr").all()
    assert (df["event_type"] == "dsr_update").all()
    assert (df["source"] == "rpc").all()
    validate_event_frame(df)
    assert df["lending_rate_apr"].between(0.0, 0.30).all()
    # DSR rows have real block_numbers (not sentinel -1)
    assert (df["block_number"] > 0).all()
    # event_idx must be globally unique within the frame (RangeIndex)
    assert df["event_idx"].is_unique
    # borrow == lend for DSR
    assert (df["borrowing_rate_apr"] == df["lending_rate_apr"]).all()


def test_fetch_dsr_events_naive_timestamp_raises():
    """Offline guard: tz-naive start/end must be rejected before any RPC call."""
    naive_start = pd.Timestamp("2024-11-01")
    naive_end = pd.Timestamp("2025-05-01")
    with pytest.raises(ValueError, match="tz-aware"):
        fetch_dsr_events(start=naive_start, end=naive_end)

    # Mixed: aware start, naive end -> still rejected.
    aware_start = pd.Timestamp("2024-11-01", tz="UTC")
    with pytest.raises(ValueError, match="tz-aware"):
        fetch_dsr_events(start=aware_start, end=naive_end)
