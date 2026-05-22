import os
from pathlib import Path

import pandas as pd
import pytest

from data.event_schema import validate_event_frame
from data.fetch_aave_events import (
    CACHE_PATH,
    fetch_aave_events,
    fetch_aave_events_cached,
)


@pytest.mark.network
def test_fetch_aave_events_one_day_smoke():
    """Pull 24h of Aave V3 USDC events; expect >50 events, schema-valid."""
    if not os.environ.get("THE_GRAPH_API_KEY"):
        pytest.skip("THE_GRAPH_API_KEY not set")
    start = pd.Timestamp("2026-04-01 00:00:00", tz="UTC")
    end = pd.Timestamp("2026-04-02 00:00:00", tz="UTC")
    df = fetch_aave_events(start=start, end=end)

    assert len(df) > 50, f"expected >50 events in 24h, got {len(df)}"
    assert (df["protocol"] == "aave_v3").all()
    assert df["block_timestamp"].between(start, end).all()
    validate_event_frame(df)

    # Spot-check rate magnitudes: USDC supply APR should be in [0.001, 0.30]
    apr = df["lending_rate_apr"]
    assert apr.between(0.001, 0.30).all(), (
        f"lending APR outside plausible range: "
        f"min={apr.min()} max={apr.max()}"
    )


@pytest.mark.network
def test_aave_18month_cached_fetch(tmp_path, monkeypatch):
    """Fetch full 18-month window and cache to parquet."""
    if not os.environ.get("THE_GRAPH_API_KEY"):
        pytest.skip("THE_GRAPH_API_KEY not set")

    cache = tmp_path / "events_aave_test.parquet"
    df = fetch_aave_events_cached(
        start=pd.Timestamp("2024-11-01", tz="UTC"),
        end=pd.Timestamp("2025-04-01", tz="UTC"),  # 5-month subset for test speed
        cache_path=cache,
        refresh=True,
    )
    assert len(df) > 10_000, f"expected >10k events in 5 months, got {len(df)}"
    assert cache.exists()

    # Re-load should hit cache and return identical frame.
    df2 = fetch_aave_events_cached(
        start=pd.Timestamp("2024-11-01", tz="UTC"),
        end=pd.Timestamp("2025-04-01", tz="UTC"),
        cache_path=cache,
        refresh=False,
    )
    pd.testing.assert_frame_equal(df, df2)
