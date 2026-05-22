"""Per-event Euler V2 vault rate fetcher (Goldsky subgraph, no auth).

ENDPOINT DISCOVERY (2026-05-22, live probe):
The Goldsky project ID in `docs/research/nway-protocols-data-map.md`
(project_clyzphvgm0o3p01vcfm1f8qju) returns 404 -- that project has
been retired. The current Euler-V2 Goldsky workspace is
`project_cm4iagnemt1wp01xn4gh1agft`. Verified via
https://docs.euler.finance/developers/data-querying/subgraphs/ on
2026-05-22.

Goldsky URL stability: when an org migrates between Goldsky workspaces,
the project_id changes and old URLs 404. Re-verify the docs link on
each major Euler V2 release before re-running an 18-month fetch.

SCHEMA DISCOVERY (2026-05-22):
The first-draft fetcher used a fictional `vaultRateHistories` entity.
The real entity is `vaultStatuses` with fields:
    id: Bytes
    vault: Bytes
    totalShares, totalBorrows, accumulatedFees, cash: BigInt
    interestAccumulator, interestRate, supplyApy, borrowApy: BigInt
    timestamp, blockNumber, blockTimestamp: BigInt
    transactionHash: Bytes

Note: supplyApy and borrowApy are BigInt with RAY (1e27) scaling --
Euler V2 inherits Aave's RAY convention for its IRMLinearKink curves.

Primary market: Euler Prime USDC at 0x797DD80692c3b2dAdabCe8e30C07fDE5307D48a9.
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import requests

from data.event_schema import EVENT_ROW_DTYPES, empty_event_frame, validate_event_frame

ENDPOINT = (
    "https://api.goldsky.com/api/public/"
    "project_cm4iagnemt1wp01xn4gh1agft/"
    "subgraphs/euler-v2-mainnet/latest/gn"
)
EULER_PRIME_USDC = "0x797DD80692c3b2dAdabCe8e30C07fDE5307D48a9"

CACHE_PATH = Path(__file__).resolve().parent / "cached" / "events_euler.parquet"
PAGE_SIZE = 1000
RAY = 10**27

QUERY = """
query ($vault: Bytes!, $startTs: BigInt!, $endTs: BigInt!, $cursor: BigInt!) {
  vaultStatuses(
    first: %d
    where: {
      vault: $vault
      timestamp_gte: $startTs
      timestamp_lt: $endTs
      timestamp_gt: $cursor
    }
    orderBy: timestamp
    orderDirection: asc
  ) {
    timestamp
    blockNumber
    supplyApy
    borrowApy
    totalShares
    totalBorrows
    cash
    transactionHash
  }
}
""" % PAGE_SIZE


def _post(payload: dict) -> dict:
    r = requests.post(ENDPOINT, json=payload, timeout=30)
    r.raise_for_status()
    body = r.json()
    if "errors" in body:
        raise RuntimeError(f"euler gql errors: {body['errors']}")
    return body["data"]


def fetch_euler_events(
    *,
    vault: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """Pull Euler V2 vaultStatuses snapshots in [start, end).

    Returns dataframe with canonical EventRow dtypes. Each vaultStatus
    row has a REAL block_number from the subgraph, so the schema dedup
    invariant is satisfied without the sentinel-then-re-cumcount dance
    that Aave/Spark need.
    """
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
                "vault": vault.lower(),
                "startTs": str(start_ts),
                "endTs": str(end_ts),
                "cursor": str(cursor),
            },
        })
        items = data.get("vaultStatuses") or []
        if not items:
            break
        for it in items:
            rows.append({
                "ts": int(it["timestamp"]),
                "block": int(it["blockNumber"]),
                "supply_ray": int(it["supplyApy"]),
                "borrow_ray": int(it["borrowApy"]),
                "shares": int(it["totalShares"]),
                "borrows": int(it["totalBorrows"]),
                "cash": int(it["cash"]),
                "tx": it.get("transactionHash") or "",
            })
        cursor = int(items[-1]["timestamp"])
        if len(items) < PAGE_SIZE:
            break
        # Friendly rate-limit pause.
        time.sleep(0.1)

    if not rows:
        return empty_event_frame()

    raw = pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)
    # event_idx = unique within-frame counter (canonical schema contract).
    raw["event_idx"] = pd.RangeIndex(len(raw)).astype("int32")

    # USDC has 6 decimals; cash and totalBorrows are in token-units.
    cash_usd = raw["cash"] / 1e6
    borrows_usd = raw["borrows"] / 1e6
    # totalSupplied = cash + totalBorrows (assets-in-pool + assets-out).
    supplied_usd = cash_usd + borrows_usd
    util = (borrows_usd / supplied_usd.where(supplied_usd > 0, 1)).clip(0, 1)

    apr_supply = raw["supply_ray"] / RAY
    apr_borrow = (raw["borrow_ray"] / RAY).clip(lower=apr_supply)

    df = pd.DataFrame({
        "block_number": raw["block"],
        "block_timestamp": pd.to_datetime(raw["ts"], unit="s", utc=True),
        "event_idx": raw["event_idx"],
        "protocol": "euler_v2",
        "event_type": "rate_update",
        "lending_rate_apr": apr_supply,
        "borrowing_rate_apr": apr_borrow,
        "utilization": util,
        "total_supplied_usd": supplied_usd,
        "total_borrowed_usd": borrows_usd,
        "tx_hash": raw["tx"].astype("string"),
        "source": "subgraph",
    })
    return df.astype(EVENT_ROW_DTYPES)


def fetch_euler_events_cached(
    *,
    vault: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    cache_path: Path | str = CACHE_PATH,
    refresh: bool = False,
) -> pd.DataFrame:
    cache_path = Path(cache_path)
    if cache_path.exists() and not refresh:
        return pd.read_parquet(cache_path).astype(EVENT_ROW_DTYPES)
    df = fetch_euler_events(vault=vault, start=start, end=end)
    validate_event_frame(df)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path, index=False)
    return df


if __name__ == "__main__":
    s = pd.Timestamp("2026-04-01", tz="UTC")
    e = pd.Timestamp("2026-04-02", tz="UTC")
    df = fetch_euler_events(vault=EULER_PRIME_USDC, start=s, end=e)
    print(f"[euler smoke] {len(df)} events")
    if not df.empty:
        print(df[["block_timestamp", "block_number", "lending_rate_apr", "utilization"]].head(3))
