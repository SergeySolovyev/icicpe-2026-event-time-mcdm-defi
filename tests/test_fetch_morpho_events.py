import pandas as pd
import pytest

from data.event_schema import validate_event_frame
from data.fetch_morpho_events import (
    MORPHO_WSTETH_USDC,
    fetch_morpho_events,
)


@pytest.mark.network
def test_fetch_morpho_events_one_day_smoke():
    """Pull 24h of Morpho Blue wstETH/USDC market state; expect >=1 event."""
    start = pd.Timestamp("2026-04-01", tz="UTC")
    end = pd.Timestamp("2026-04-02", tz="UTC")
    df = fetch_morpho_events(market_id=MORPHO_WSTETH_USDC, start=start, end=end)

    # Morpho records (roughly) daily snapshots; allow as few as 1 row.
    assert len(df) >= 1, f"expected >=1 event in 24h, got {len(df)}"
    assert (df["protocol"] == "morpho_blue").all()
    assert df["block_timestamp"].between(start, end).all()
    validate_event_frame(df)

    # Spot-check rate magnitudes: USDC supply APR should be in [0.001, 0.30].
    apr = df["lending_rate_apr"]
    assert apr.between(0.001, 0.30).all(), (
        f"lending APR outside plausible range: "
        f"min={apr.min()} max={apr.max()}"
    )
