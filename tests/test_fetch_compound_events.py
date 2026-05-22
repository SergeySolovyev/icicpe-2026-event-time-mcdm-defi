"""Tests for data.fetch_compound_events (Task A5).

Live RPC test marked @pytest.mark.network -- CI runs `pytest -m 'not network'`.
"""
import os

import pandas as pd
import pytest

from data.event_schema import validate_event_frame
from data.fetch_compound_events import (
    fetch_compound_events,
    fetch_compound_events_cached,
)


def test_imports_resolve():
    """Module + public surface load (offline)."""
    assert callable(fetch_compound_events)
    assert callable(fetch_compound_events_cached)


def test_naive_timestamp_raises():
    """tz-naive start/end is a programmer error -- fail fast, no RPC call."""
    with pytest.raises(ValueError, match="tz-aware"):
        fetch_compound_events(
            start=pd.Timestamp("2026-04-01"),
            end=pd.Timestamp("2026-04-02"),
        )


@pytest.mark.network
def test_fetch_compound_events_one_day_smoke():
    """Pull 24h of Compound V3 USDC rate samples (1 per N blocks via RPC)."""
    if not os.environ.get("ETHEREUM_RPC_URL"):
        pytest.skip("ETHEREUM_RPC_URL not set")
    start = pd.Timestamp("2026-04-01", tz="UTC")
    end = pd.Timestamp("2026-04-02", tz="UTC")
    df = fetch_compound_events(start=start, end=end, sample_every_n_blocks=600)
    # 24h ~ 7200 blocks; sample_every_n_blocks=600 -> ~12 rows
    assert 5 <= len(df) <= 50, f"expected 5-50 sampled rows, got {len(df)}"
    assert (df["protocol"] == "compound_v3").all()
    assert (df["source"] == "rpc").all()
    validate_event_frame(df)
    assert df["lending_rate_apr"].between(0.001, 0.30).all(), (
        f"supply APR outside plausible range: "
        f"min={df['lending_rate_apr'].min()} max={df['lending_rate_apr'].max()}"
    )
