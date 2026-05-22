"""Per-event Morpho Blue market-state fetcher.

Endpoint: https://blue-api.morpho.org/graphql (no auth, decimal APYs).

SCHEMA DISCOVERY (2026-05-22, live introspection):
Morpho's API does NOT have `marketByUniqueKey` (the first-draft guess).
The correct query is `marketById(marketId, chainId)`, and the
`historicalState` field is NOT a list of timestamped rows -- it's an
object where each metric (supplyApy, borrowApy, utilization, etc.) is
its own timeseries function:

    historicalState {
      supplyApy(options: $opts) { x: timestamp y: decimal }
      borrowApy(options: $opts) { x y }
      utilization(options: $opts) { x y }
      supplyAssetsUsd(options: $opts) { x y }
      borrowAssetsUsd(options: $opts) { x y }
    }

We fetch all five fields with the same TimeseriesOptions window+interval
and join them client-side on x (timestamp). Interval is at most HOUR --
no sub-hour granularity available, which is fine since the stitcher
forward-fills onto the per-block grid.

Morpho's AdaptiveCurve IRM has a time-varying rateAtTarget -- no static
f_kink. We record the live supplyApy / borrowApy as decimals (NOT
RAY-scaled, unlike Aave/Spark). Kink-subtraction is NOT applied for
Morpho; downstream T2/T3 decision policies treat it differently.

Market choice: start with wstETH/USDC (top TVL USDC market). Other
markets can be passed via the market_id kwarg.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

from data.event_schema import EVENT_ROW_DTYPES, empty_event_frame, validate_event_frame

ENDPOINT = "https://blue-api.morpho.org/graphql"
MORPHO_WSTETH_USDC = "0xb323495f7e4148be5643a4ea4a8221eef163e4bccfdedc2a6f4696baacbc86cc"

CACHE_PATH = Path(__file__).resolve().parent / "cached" / "events_morpho.parquet"

# Query matches the live schema verified via __schema introspection.
QUERY = """
query ($id: String!, $opts: TimeseriesOptions) {
  marketById(marketId: $id, chainId: 1) {
    historicalState {
      supplyApy(options: $opts)        { x y }
      borrowApy(options: $opts)        { x y }
      utilization(options: $opts)      { x y }
      supplyAssetsUsd(options: $opts)  { x y }
      borrowAssetsUsd(options: $opts)  { x y }
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


def _series_to_dict(series: list[dict] | None) -> dict[int, float]:
    """[{x: 1.7e9, y: 0.05}, ...]  ->  {1_700_000_000: 0.05}.

    Tolerates None (missing series) by returning {}. Cast x to int (it
    arrives as Float from Morpho API but represents a unix timestamp).
    """
    if not series:
        return {}
    return {int(p["x"]): (float(p["y"]) if p["y"] is not None else float("nan"))
            for p in series}


def fetch_morpho_events(
    *,
    market_id: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    interval: str = "HOUR",
) -> pd.DataFrame:
    """Pull Morpho Blue market historical state in [start, end).

    Returns a dataframe with the canonical EventRow dtypes. Source field
    is 'subgraph' (the Morpho API is GraphQL-indexed, equivalent role
    to a subgraph for our pipeline taxonomy).

    interval: one of HOUR/DAY/WEEK/MONTH/QUARTER/YEAR (TimeseriesInterval
    enum). Default HOUR -- maximum available granularity.
    """
    if start.tz is None or end.tz is None:
        raise ValueError("start/end must be tz-aware UTC")
    if interval not in {"HOUR", "DAY", "WEEK", "MONTH", "QUARTER", "YEAR"}:
        raise ValueError(f"invalid interval {interval!r}")

    opts = {
        "startTimestamp": int(start.timestamp()),
        "endTimestamp":   int(end.timestamp()),
        "interval":       interval,
    }

    data = _post({"query": QUERY, "variables": {"id": market_id, "opts": opts}})
    market = data.get("marketById") or {}
    hist = market.get("historicalState") or {}
    if not hist:
        return empty_event_frame()

    # Pull each timeseries -> dict keyed by timestamp.
    supply = _series_to_dict(hist.get("supplyApy"))
    borrow = _series_to_dict(hist.get("borrowApy"))
    util   = _series_to_dict(hist.get("utilization"))
    sup_usd = _series_to_dict(hist.get("supplyAssetsUsd"))
    bor_usd = _series_to_dict(hist.get("borrowAssetsUsd"))

    # Union of timestamps across all five series; align on the union so
    # missing values become NaN (rather than dropping rows). Sort.
    all_ts = sorted(set().union(supply, borrow, util, sup_usd, bor_usd))
    if not all_ts:
        return empty_event_frame()

    rows = []
    for ts in all_ts:
        rows.append({
            "ts": ts,
            "supply_apy":   supply.get(ts, float("nan")),
            "borrow_apy":   borrow.get(ts, float("nan")),
            "util":         util.get(ts, float("nan")),
            "supplied_usd": sup_usd.get(ts, float("nan")),
            "borrowed_usd": bor_usd.get(ts, float("nan")),
        })

    raw = pd.DataFrame(rows)
    # event_idx = unique within-frame counter per the schema contract
    # (see data/event_schema.py top-of-file comment). The stitcher will
    # re-cumcount within (block_number, protocol) after ts->block lookup.
    raw["event_idx"] = pd.RangeIndex(len(raw)).astype("int32")

    # Ensure borrow >= supply at every row (validator invariant). Clip
    # rare cases where the API may return borrowApy < supplyApy due to
    # rounding (shouldn't happen on Morpho but cheap to guard).
    borrow_clipped = raw["borrow_apy"].clip(lower=raw["supply_apy"])

    df = pd.DataFrame({
        "block_number": -1,
        "block_timestamp": pd.to_datetime(raw["ts"], unit="s", utc=True),
        "event_idx": raw["event_idx"],
        "protocol": "morpho_blue",
        "event_type": "rate_update",
        "lending_rate_apr": raw["supply_apy"],
        "borrowing_rate_apr": borrow_clipped,
        "utilization": raw["util"].clip(0.0, 1.0),
        "total_supplied_usd": raw["supplied_usd"],
        "total_borrowed_usd": raw["borrowed_usd"],
        "tx_hash": pd.Series([""] * len(raw), dtype="string"),
        "source": "subgraph",
    })
    return df.astype(EVENT_ROW_DTYPES)


def fetch_morpho_events_cached(
    *,
    market_id: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    interval: str = "HOUR",
    cache_path: Path | str = CACHE_PATH,
    refresh: bool = False,
) -> pd.DataFrame:
    cache_path = Path(cache_path)
    if cache_path.exists() and not refresh:
        return pd.read_parquet(cache_path).astype(EVENT_ROW_DTYPES)
    df = fetch_morpho_events(market_id=market_id, start=start, end=end, interval=interval)
    validate_event_frame(df)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path, index=False)
    return df


if __name__ == "__main__":
    s = pd.Timestamp("2026-04-01", tz="UTC")
    e = pd.Timestamp("2026-04-02", tz="UTC")
    df = fetch_morpho_events(market_id=MORPHO_WSTETH_USDC, start=s, end=e)
    print(f"[morpho smoke] {len(df)} events")
    if not df.empty:
        print(df[["block_timestamp", "lending_rate_apr", "utilization"]].head(3))
