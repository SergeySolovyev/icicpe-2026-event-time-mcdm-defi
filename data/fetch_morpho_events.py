"""Per-event Morpho Blue market-state fetcher.

Endpoint: https://blue-api.morpho.org/graphql (no auth, decimal APYs).

Note: Morpho's AdaptiveCurve IRM has a time-varying rateAtTarget -- no
static f_kink. We record the live supplyApy / borrowApy as decimals
(NOT RAY-scaled, unlike Aave/Spark). Kink-subtraction is NOT applied
for Morpho; downstream T2/T3 decision policies will treat it differently.

Market choice: start with wstETH/USDC (top TVL USDC market). Other
markets can be passed via the market_id kwarg.
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import requests

from data.event_schema import EVENT_ROW_DTYPES, empty_event_frame, validate_event_frame

ENDPOINT = "https://blue-api.morpho.org/graphql"
MORPHO_WSTETH_USDC = "0xb323495f7e4148be5643a4ea4a8221eef163e4bccfdedc2a6f4696baacbc86cc"

CACHE_PATH = Path(__file__).resolve().parent / "cached" / "events_morpho.parquet"

PAGE_SIZE = 1000

QUERY = """
query ($id: String!, $startTs: Float!, $endTs: Float!, $cursor: Float!) {
  marketByUniqueKey(uniqueKey: $id, chainId: 1) {
    historicalState(
      options: {
        first: 1000
        where: {timestamp_gte: $startTs, timestamp_lt: $endTs, timestamp_gt: $cursor}
        orderBy: timestamp_ASC
      }
    ) {
      timestamp
      supplyApy
      borrowApy
      utilization
      totalSupplyUsd
      totalBorrowUsd
    }
  }
}
"""


def _post(payload: dict) -> dict:
    r = requests.post(ENDPOINT, json=payload, timeout=30)
    r.raise_for_status()
    body = r.json()
    if "errors" in body:
        raise RuntimeError(f"morpho gql errors: {body['errors']}")
    return body["data"]


def fetch_morpho_events(
    *,
    market_id: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """Pull Morpho Blue market historical state in [start, end).

    Returns a dataframe with the canonical EventRow dtypes. Source
    field is 'subgraph' (the Morpho API is GraphQL-indexed, equivalent
    role to a subgraph for our pipeline taxonomy).
    """
    if start.tz is None or end.tz is None:
        raise ValueError("start/end must be tz-aware UTC")
    start_ts = float(start.timestamp())
    end_ts = float(end.timestamp())
    cursor = start_ts - 1.0

    rows: list[dict] = []
    while True:
        data = _post({"query": QUERY, "variables": {
            "id": market_id,
            "startTs": start_ts,
            "endTs": end_ts,
            "cursor": cursor,
        }})
        market = data.get("marketByUniqueKey") or {}
        items = market.get("historicalState") or []
        if not items:
            break
        for it in items:
            rows.append({
                "ts": float(it["timestamp"]),
                "supply_apy": float(it.get("supplyApy") or 0.0),
                "borrow_apy": float(it.get("borrowApy") or 0.0),
                "util": float(it.get("utilization") or 0.0),
                "supplied": float(it.get("totalSupplyUsd") or 0.0),
                "borrowed": float(it.get("totalBorrowUsd") or 0.0),
            })
        cursor = float(items[-1]["timestamp"])
        if len(items) < PAGE_SIZE:
            break
        time.sleep(0.1)

    if not rows:
        return empty_event_frame()

    raw = pd.DataFrame(rows).sort_values("ts", kind="stable").reset_index(drop=True)

    # CRITICAL: event_idx is a UNIQUE within-fetch counter (see long comment
    # block above EVENT_ROW_DTYPES in data/event_schema.py). At fetch time,
    # block_number is sentinel -1 for every row, so per-ts cumcount() would
    # collide on the (block_number, event_idx, protocol) dedup key whenever
    # two timestamps each produce a single row (both would get event_idx=0).
    # pd.RangeIndex guarantees uniqueness; the stitcher re-cumcounts within
    # (block_number, protocol) after ts->block resolution.
    raw["event_idx"] = pd.RangeIndex(len(raw)).astype("int32")

    # Morpho returns decimal APY directly -- no RAY scaling needed.
    # Clip borrow >= supply to satisfy the sign-convention invariant
    # (numerical fuzz at extreme low-utilization can briefly invert).
    supply_apr = raw["supply_apy"]
    borrow_apr = raw["borrow_apy"].clip(lower=supply_apr)
    utilization = raw["util"].clip(0.0, 1.0)

    df = pd.DataFrame({
        "block_number": -1,  # sentinel; stitcher fills via ts->block
        "block_timestamp": pd.to_datetime(raw["ts"], unit="s", utc=True),
        "event_idx": raw["event_idx"],
        "protocol": "morpho_blue",
        "event_type": "rate_update",
        "lending_rate_apr": supply_apr,
        "borrowing_rate_apr": borrow_apr,
        "utilization": utilization,
        "total_supplied_usd": raw["supplied"],
        "total_borrowed_usd": raw["borrowed"],
        "tx_hash": pd.Series([""] * len(raw), dtype="string"),
        "source": "subgraph",
    })

    return df.astype(EVENT_ROW_DTYPES)


def fetch_morpho_events_cached(
    *,
    market_id: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    cache_path: Path | str = CACHE_PATH,
    refresh: bool = False,
) -> pd.DataFrame:
    """Wrapper around fetch_morpho_events with parquet caching.

    If `cache_path` exists and `refresh` is False, return cached frame.
    Otherwise refetch, validate, write, and return.
    """
    cache_path = Path(cache_path)
    if cache_path.exists() and not refresh:
        return pd.read_parquet(cache_path).astype(EVENT_ROW_DTYPES)

    df = fetch_morpho_events(market_id=market_id, start=start, end=end)
    validate_event_frame(df)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path, index=False)
    return df


if __name__ == "__main__":
    s = pd.Timestamp("2026-04-01", tz="UTC")
    e = pd.Timestamp("2026-04-02", tz="UTC")
    df = fetch_morpho_events(market_id=MORPHO_WSTETH_USDC, start=s, end=e)
    print(f"[morpho smoke] fetched {len(df)} events")
