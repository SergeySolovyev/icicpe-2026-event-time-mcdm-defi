"""Tests for data.fetch_fluid_events (Task A8).

Fluid has no subgraph -- the live smoke is RPC against FluidLendingResolver.
Live test marked @pytest.mark.network; CI runs `pytest -m 'not network'`.
"""
import os
import re

import pandas as pd
import pytest

from data.event_schema import validate_event_frame
from data.fetch_fluid_events import (
    SEL_GET_OVERALL,
    fetch_fluid_events,
    fetch_fluid_events_cached,
)


def test_imports_resolve():
    """Module + public surface load (offline)."""
    assert callable(fetch_fluid_events)
    assert callable(fetch_fluid_events_cached)


def test_selector_hex_format():
    """getOverallTokenData(address) selector is 4-byte 0x-prefixed hex."""
    # 0x + 8 hex chars = 10 chars total.
    assert re.fullmatch(r"0x[0-9a-f]{8}", SEL_GET_OVERALL), SEL_GET_OVERALL
    # Sanity: matches the documented selector (eth_utils keccak of the
    # canonical signature). If this ever changes, eth_utils is broken.
    assert SEL_GET_OVERALL == "0x29e04fbf", SEL_GET_OVERALL


def test_naive_timestamp_raises():
    """tz-naive start/end is a programmer error -- fail fast, no RPC call."""
    with pytest.raises(ValueError, match="tz-aware"):
        fetch_fluid_events(
            start=pd.Timestamp("2026-04-01"),
            end=pd.Timestamp("2026-04-02"),
        )


@pytest.mark.network
def test_fetch_fluid_events_one_day_smoke():
    """Pull 24h of Fluid USDC rate samples via RPC."""
    if not os.environ.get("ETHEREUM_RPC_URL"):
        pytest.skip("ETHEREUM_RPC_URL not set")
    start = pd.Timestamp("2026-04-01", tz="UTC")
    end = pd.Timestamp("2026-04-02", tz="UTC")
    df = fetch_fluid_events(start=start, end=end, sample_every_n_blocks=600)
    # 24h ~ 7200 blocks; sample_every_n_blocks=600 -> ~12 rows.
    assert 5 <= len(df) <= 50, f"expected 5-50 sampled rows, got {len(df)}"
    assert (df["protocol"] == "fluid").all()
    assert (df["source"] == "rpc").all()
    validate_event_frame(df)
    assert df["lending_rate_apr"].between(0.001, 0.30).all(), (
        f"supply APR outside plausible range: "
        f"min={df['lending_rate_apr'].min()} max={df['lending_rate_apr'].max()}"
    )
