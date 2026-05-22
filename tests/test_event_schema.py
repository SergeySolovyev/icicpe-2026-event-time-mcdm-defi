"""Contract test for the canonical EventRow schema.

Every per-event fetcher (data/fetch_*_events.py) must emit dataframes
matching this contract. The stitcher (data/build_per_block_panel.py)
relies on the invariants enforced here.
"""
import pandas as pd
import pytest
from data.event_schema import EVENT_ROW_DTYPES, validate_event_frame


def _good_row():
    """A minimal EventRow that satisfies every invariant."""
    return {
        "block_number": 19_000_000,
        "block_timestamp": pd.Timestamp("2024-11-01 00:00:00", tz="UTC"),
        "event_idx": 0,
        "protocol": "aave_v3",
        "event_type": "rate_update",
        "lending_rate_apr": 0.0436,
        "borrowing_rate_apr": 0.0512,
        "utilization": 0.79,
        "total_supplied_usd": 1.2e9,
        "total_borrowed_usd": 0.95e9,
        "tx_hash": "0xdead",
        "source": "subgraph",
    }


def test_good_frame_passes():
    df = pd.DataFrame([_good_row()]).astype(EVENT_ROW_DTYPES)
    validate_event_frame(df)  # should not raise


def test_negative_utilization_raises():
    row = _good_row()
    row["utilization"] = -0.01
    df = pd.DataFrame([row]).astype(EVENT_ROW_DTYPES)
    with pytest.raises(ValueError, match="utilization out of"):
        validate_event_frame(df)


def test_borrowing_lt_lending_raises():
    row = _good_row()
    row["borrowing_rate_apr"] = 0.0001  # below lending
    df = pd.DataFrame([row]).astype(EVENT_ROW_DTYPES)
    with pytest.raises(ValueError, match="borrowing_rate_apr.*<.*lending"):
        validate_event_frame(df)


def test_duplicate_key_raises():
    df = pd.DataFrame([_good_row(), _good_row()]).astype(EVENT_ROW_DTYPES)
    with pytest.raises(ValueError, match="duplicate"):
        validate_event_frame(df)


def test_naive_timestamp_raises():
    row = _good_row()
    row["block_timestamp"] = pd.Timestamp("2024-11-01 00:00:00")  # tz-naive
    # Don't coerce dtypes - keep naive.
    df = pd.DataFrame([row])
    with pytest.raises(ValueError, match="tz-aware"):
        validate_event_frame(df)


def test_unknown_protocol_raises():
    row = _good_row()
    row["protocol"] = "uniswap_v3"  # not a lending protocol
    df = pd.DataFrame([row]).astype({**EVENT_ROW_DTYPES, "protocol": "object"})
    with pytest.raises(ValueError, match="unknown protocol"):
        validate_event_frame(df)


def test_missing_column_raises():
    df = pd.DataFrame([{k: v for k, v in _good_row().items() if k != "utilization"}])
    with pytest.raises(ValueError, match="missing columns"):
        validate_event_frame(df)
