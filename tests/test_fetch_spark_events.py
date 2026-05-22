import os
import pandas as pd
import pytest
from data.event_schema import validate_event_frame
from data.fetch_spark_events import fetch_spark_events


@pytest.mark.network
def test_fetch_spark_events_one_day_smoke():
    """Pull 24h of Spark USDC events; expect >5 events (Spark < Aave volume)."""
    if not os.environ.get("THE_GRAPH_API_KEY"):
        pytest.skip("THE_GRAPH_API_KEY not set")
    start = pd.Timestamp("2026-04-01", tz="UTC")
    end = pd.Timestamp("2026-04-02", tz="UTC")
    df = fetch_spark_events(start=start, end=end)

    assert len(df) >= 5, f"expected >=5 events in 24h, got {len(df)}"
    assert (df["protocol"] == "spark").all()
    validate_event_frame(df)
    assert df["lending_rate_apr"].between(0.001, 0.30).all()
