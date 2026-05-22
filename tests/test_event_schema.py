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


def test_pre_stitcher_sentinel_with_unique_event_idx_passes():
    """Regression test for the Task A2 dedup bug.

    At fetch time, all rows from a single fetcher share
    (block_number=-1, protocol="aave_v3"). The dedup key
    (block_number, event_idx, protocol) must still be unique, which
    requires fetchers to assign a globally-unique event_idx (e.g.
    RangeIndex), NOT a per-timestamp cumcount. This test locks that
    contract in.
    """
    rows = []
    for i in range(50):
        row = _good_row()
        row["block_number"] = -1  # pre-stitcher sentinel
        row["event_idx"] = i  # globally unique within fetch
        row["block_timestamp"] = pd.Timestamp(
            "2024-11-01 00:00:00", tz="UTC"
        ) + pd.Timedelta(seconds=i * 30)
        rows.append(row)
    df = pd.DataFrame(rows).astype(EVENT_ROW_DTYPES)
    validate_event_frame(df)  # should not raise -- this is the post-fix contract


def test_pre_stitcher_with_clashing_event_idx_raises():
    """The flip side: if a fetcher accidentally re-uses event_idx values
    across rows in the same fetch (the OLD groupby(ts).cumcount() bug),
    the validator catches it before parquet write."""
    rows = []
    for i in range(5):
        row = _good_row()
        row["block_number"] = -1
        row["event_idx"] = 0  # BAD: all rows claim idx 0 -- the old bug
        row["block_timestamp"] = pd.Timestamp(
            "2024-11-01 00:00:00", tz="UTC"
        ) + pd.Timedelta(seconds=i * 30)
        rows.append(row)
    df = pd.DataFrame(rows).astype(EVENT_ROW_DTYPES)
    with pytest.raises(ValueError, match="duplicate"):
        validate_event_frame(df)
