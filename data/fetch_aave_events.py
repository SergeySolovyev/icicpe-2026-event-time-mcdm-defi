"""Per-event Aave V3 USDC supply-rate fetcher.

Emits the canonical EventRow schema from `data.event_schema`.

CRITICAL conversion note (CLAUDE.md §3a):
    liquidityRate is ANNUALIZED × RAY (1e27), not per-second × RAY.
    apr_decimal = liquidityRate / 1e27

The subgraph emits ~50 rate-update events per hour. This module does NOT
resample — that's the stitcher's job in `build_per_block_panel.py`.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd
import requests

from data.event_schema import EVENT_ROW_DTYPES, empty_event_frame, validate_event_frame

# Verified 2026-05-14 against aave/protocol-subgraphs README (CLAUDE.md §3).
AAVE_V3_SUBGRAPH_ID = "Cd2gEDVeqnjBn1hSeqFMitw8Q1iiyV9FYUZkLNRcL87g"
USDC_ADDR = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
# NOTE: The Aave V3 subgraph keys reserves by PoolAddressesProvider, NOT the
# Pool contract. Empirically verified 2026-05-22: querying with the Pool
# address (0x87870bca...) returns zero rows; the PoolAddressesProvider
# address below matches all reserve.id values returned by the subgraph.
AAVE_POOL_ADDR = "0x2f39d218133afab8f2b819b1066c7e434ad94e9e"
USDC_RESERVE_ID = USDC_ADDR + AAVE_POOL_ADDR

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

CACHE_PATH = Path(__file__).resolve().parent / "cached" / "events_aave.parquet"


def _endpoint() -> str:
    key = os.environ.get("THE_GRAPH_API_KEY")
    if not key:
        raise RuntimeError("THE_GRAPH_API_KEY not set")
    return f"https://gateway.thegraph.com/api/{key}/subgraphs/id/{AAVE_V3_SUBGRAPH_ID}"


def _post(payload: dict) -> dict:
    r = requests.post(_endpoint(), json=payload, timeout=30)
    r.raise_for_status()
    body = r.json()
    if "errors" in body:
        raise RuntimeError(f"subgraph errors: {body['errors']}")
    return body["data"]


def fetch_aave_events(
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    page_size: int = PAGE_SIZE,
) -> pd.DataFrame:
    """Pull all Aave V3 USDC rate-update events in [start, end).

    Returns a dataframe with the canonical EventRow dtypes.

    Pagination via timestamp cursor (subgraph hard limit of 5000 skip).
    """
    if start.tz is None or end.tz is None:
        raise ValueError("start/end must be tz-aware UTC")

    start_ts = int(start.timestamp())
    end_ts = int(end.timestamp())
    cursor = start_ts - 1  # exclusive lower bound below

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
                "block_timestamp_ts": ts,
                "liquidity_rate_ray": int(it["liquidityRate"]),
                "borrow_rate_ray": int(it["variableBorrowRate"]),
                "total_liquidity": int(it["totalLiquidity"]),
                "total_debt": int(it["totalCurrentVariableDebt"]),
                "raw_id": it["id"],
            })
        cursor = int(items[-1]["timestamp"])
        if len(items) < page_size:
            break
        # Friendly rate-limit pause.
        time.sleep(0.1)

    if not rows:
        return empty_event_frame()

    raw = pd.DataFrame(rows)

    # Sort by ts, then assign event_idx within each timestamp (proxy for
    # within-block ordering; subgraph doesn't expose true logIndex on this
    # entity).
    raw = raw.sort_values("block_timestamp_ts", kind="stable").reset_index(drop=True)
    raw["event_idx"] = raw.groupby("block_timestamp_ts").cumcount().astype("int32")

    # Compute fields per the canonical schema.
    apr_lend = raw["liquidity_rate_ray"] / RAY
    apr_borrow = raw["borrow_rate_ray"] / RAY
    supplied_usdc = raw["total_liquidity"] / 1e6  # USDC has 6 decimals
    borrowed_usdc = raw["total_debt"] / 1e6
    utilization = borrowed_usdc.where(supplied_usdc > 0, 0) / supplied_usdc.where(
        supplied_usdc > 0, 1
    )
    utilization = utilization.clip(0.0, 1.0)

    df = pd.DataFrame({
        "block_number": pd.NA,  # subgraph doesn't expose; filled later via ts-to-block
        "block_timestamp": pd.to_datetime(
            raw["block_timestamp_ts"], unit="s", utc=True
        ),
        "event_idx": raw["event_idx"],
        "protocol": "aave_v3",
        "event_type": "rate_update",
        "lending_rate_apr": apr_lend,
        "borrowing_rate_apr": apr_borrow,
        "utilization": utilization,
        "total_supplied_usd": supplied_usdc,  # USDC pegged to USD here
        "total_borrowed_usd": borrowed_usdc,
        "tx_hash": pd.Series([""] * len(raw), dtype="string"),
        "source": "subgraph",
    })

    # block_number assignment via ts->block lookup is deferred to the
    # stitcher (build_per_block_panel.py) so each fetcher stays lightweight.
    df["block_number"] = -1  # sentinel; stitcher fills

    return df.astype(EVENT_ROW_DTYPES)


def fetch_aave_events_cached(
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    cache_path: Path | str = CACHE_PATH,
    refresh: bool = False,
) -> pd.DataFrame:
    """Wrapper around fetch_aave_events with parquet caching.

    If `cache_path` exists and `refresh` is False, return cached frame.
    Otherwise refetch, validate, write, and return.
    """
    cache_path = Path(cache_path)
    if cache_path.exists() and not refresh:
        df = pd.read_parquet(cache_path)
        return df.astype(EVENT_ROW_DTYPES)

    df = fetch_aave_events(start=start, end=end)
    validate_event_frame(df)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path, index=False)
    return df


if __name__ == "__main__":
    s = pd.Timestamp("2026-04-01", tz="UTC")
    e = pd.Timestamp("2026-04-02", tz="UTC")
    df = fetch_aave_events(s, e)
    print(f"[smoke] fetched {len(df)} events {df['block_timestamp'].min()} .. "
          f"{df['block_timestamp'].max()}")
