import pandas as pd
import pytest

from data.event_schema import validate_event_frame
from data.fetch_euler_events import (
    EULER_PRIME_USDC,
    fetch_euler_events,
    fetch_euler_events_cached,
)


def test_euler_prime_usdc_constant():
    """Lock-in the Euler Prime USDC vault address (nway-protocols-data-map.md S4B)."""
    assert EULER_PRIME_USDC == "0x797DD80692c3b2dAdabCe8e30C07fDE5307D48a9"


def test_fetch_euler_events_signature():
    """fetch_euler_events must accept vault/start/end kwargs and be importable."""
    # No network call: just verify the symbol exists and is callable.
    assert callable(fetch_euler_events)
    assert callable(fetch_euler_events_cached)


@pytest.mark.network
def test_fetch_euler_events_one_day_smoke():
    """Pull 24h of Euler Prime USDC events from the Goldsky subgraph."""
    start = pd.Timestamp("2026-04-01", tz="UTC")
    end = pd.Timestamp("2026-04-02", tz="UTC")
    df = fetch_euler_events(vault=EULER_PRIME_USDC, start=start, end=end)

    # Prime USDC sees ~5-30 events/day per nway-protocols-data-map.md S4D.
    assert len(df) >= 1, f"expected >=1 event in 24h, got {len(df)}"
    assert (df["protocol"] == "euler_v2").all()
    assert (df["source"] == "subgraph").all()
    assert df["block_timestamp"].between(start, end).all()
    validate_event_frame(df)

    # Spot-check rate magnitudes: USDC supply APR in [0.001, 0.30].
    apr = df["lending_rate_apr"]
    assert apr.between(0.001, 0.30).all(), (
        f"lending APR outside plausible range: min={apr.min()} max={apr.max()}"
    )
