"""Per-event Spark (SparkLend) USDC supply-rate fetcher.

Spark is an Aave V3 fork - same subgraph schema, same RAY 1e27 scaling,
same APR conversion. The only differences from fetch_aave_events.py are
the subgraph id and the USDC reserve id.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd
import requests

from data.event_schema import EVENT_ROW_DTYPES, empty_event_frame

# Verified via nway-protocols-data-map.md SparkLend section.
SPARK_SUBGRAPH_ID = "GbKdmBe4ycCYCQLQSjqGg6UHYoYfbyJyq5WrG35pv1si"
USDC_ADDR = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
# Spark pool address - verify on first run; placeholder is the gateway-pool.
SPARK_POOL_ADDR = "0xc13e21b648a5ee794902342038ff3adab66be987"
USDC_RESERVE_ID = USDC_ADDR + SPARK_POOL_ADDR

RAY = 10**27
PAGE_SIZE = 1000

QUERY = """
query ($reserve: String!, $startTs: Int!, $endTs: Int!, $cursor: Int!) {
  reserveParamsHistoryItems(
    first: %d
    where: {
      reserve: $reserve
      timestamp_gte: $startTs
      timestamp_lt: $endTs
      timestamp_gt: $cursor
    }
    orderBy: timestamp
    orderDirection: asc
  ) {
    id
    timestamp
    liquidityRate
    variableBorrowRate
    totalLiquidity
    totalCurrentVariableDebt
    reserve { id }
  }
}
""" % PAGE_SIZE

CACHE_PATH = Path(__file__).resolve().parent / "cached" / "events_spark.parquet"


def _endpoint() -> str:
    key = os.environ.get("THE_GRAPH_API_KEY")
    if not key:
        raise RuntimeError("THE_GRAPH_API_KEY not set")
    return f"https://gateway.thegraph.com/api/{key}/subgraphs/id/{SPARK_SUBGRAPH_ID}"


def _post(payload: dict) -> dict:
    r = requests.post(_endpoint(), json=payload, timeout=30)
    r.raise_for_status()
    body = r.json()
    if "errors" in body:
        raise RuntimeError(f"subgraph errors: {body['errors']}")
    return body["data"]


def fetch_spark_events(
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    page_size: int = PAGE_SIZE,
) -> pd.DataFrame:
    """Pull Spark USDC rate-update events in [start, end). EventRow schema."""
    if start.tz is None or end.tz is None:
        raise ValueError("start/end must be tz-aware UTC")

    start_ts = int(start.timestamp())
    end_ts = int(end.timestamp())
    cursor = start_ts - 1

    rows: list[dict] = []
    while True:
        data = _post({
            "query": QUERY,
            "variables": {
                "reserve": USDC_RESERVE_ID,
                "startTs": start_ts,
                "endTs": end_ts,
                "cursor": cursor,
            },
        })
        items = data["reserveParamsHistoryItems"]
        if not items:
            break
        for it in items:
            ts = int(it["timestamp"])
            rows.append({
                "ts": ts,
                "lend_ray": int(it["liquidityRate"]),
                "borrow_ray": int(it["variableBorrowRate"]),
                "supplied": int(it["totalLiquidity"]),
                "borrowed": int(it["totalCurrentVariableDebt"]),
            })
        cursor = int(items[-1]["timestamp"])
        if len(items) < page_size:
            break
        time.sleep(0.1)

    if not rows:
        return empty_event_frame()

    raw = pd.DataFrame(rows).sort_values("ts", kind="stable").reset_index(drop=True)
    # event_idx = unique within-fetch counter (NOT per-timestamp cumcount).
    # See identical comment in data/fetch_aave_events.py: at fetch time
    # block_number is sentinel -1 and groupby(ts).cumcount() would collide
    # on the dedup key (block_number, event_idx, protocol). Stitcher
    # re-cumcounts within (block_number, protocol) after ts -> block lookup.
    raw["event_idx"] = pd.RangeIndex(len(raw)).astype("int32")

    supplied = raw["supplied"] / 1e6
    borrowed = raw["borrowed"] / 1e6
    utilization = (borrowed / supplied.where(supplied > 0, 1)).clip(0, 1)

    df = pd.DataFrame({
        "block_number": -1,
        "block_timestamp": pd.to_datetime(raw["ts"], unit="s", utc=True),
        "event_idx": raw["event_idx"],
        "protocol": "spark",
        "event_type": "rate_update",
        "lending_rate_apr": raw["lend_ray"] / RAY,
        "borrowing_rate_apr": raw["borrow_ray"] / RAY,
        "utilization": utilization,
        "total_supplied_usd": supplied,
        "total_borrowed_usd": borrowed,
        "tx_hash": pd.Series([""] * len(raw), dtype="string"),
        "source": "subgraph",
    })
    return df.astype(EVENT_ROW_DTYPES)


def fetch_spark_events_cached(
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    cache_path: Path | str = CACHE_PATH,
    refresh: bool = False,
) -> pd.DataFrame:
    """Cached wrapper, parquet round-trip. See fetch_aave_events_cached."""
    cache_path = Path(cache_path)
    if cache_path.exists() and not refresh:
        return pd.read_parquet(cache_path).astype(EVENT_ROW_DTYPES)
    df = fetch_spark_events(start=start, end=end)
    from data.event_schema import validate_event_frame
    validate_event_frame(df)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path, index=False)
    return df


if __name__ == "__main__":
    s = pd.Timestamp("2026-04-01", tz="UTC")
    e = pd.Timestamp("2026-04-02", tz="UTC")
    print(f"[spark smoke] {len(fetch_spark_events(s, e))} events")
