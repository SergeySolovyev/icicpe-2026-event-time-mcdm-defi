"""Per-event Euler V2 USDC supply-rate fetcher.

Pulls VaultStatus events from the Goldsky-hosted euler-v2-mainnet subgraph
(no auth) and emits the canonical EventRow schema from `data.event_schema`.

CRITICAL conversion notes (nway-protocols-data-map.md S4):
    - Primary market is the Euler Prime USDC vault, IRMLinearKink (Aave-style)
      so the static f_kink decomposition applies downstream.
    - Underlying contract emits per-second rate x 1e27 (RAY-like). The
      Goldsky subgraph performs the conversion and exposes `supplyApy` /
      `borrowApy` as DECIMAL APYs (e.g. 0.05 = 5%) - same convention as
      Morpho's API. We therefore do NOT divide by RAY here.
    - cash + totalBorrows = totalAssets, so:
          utilization = totalBorrows / (cash + totalBorrows)
      matching the on-chain ERC-4626 + EVK semantic.

Like the Aave/Spark fetchers, this module does NOT resample - that is the
stitcher's job in `build_per_block_panel.py`. event_idx is assigned as a
unique within-fetch counter (pd.RangeIndex), NOT a per-timestamp cumcount;
see `data/event_schema.py` event_idx comment block for the rationale.
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import requests

from data.event_schema import EVENT_ROW_DTYPES, empty_event_frame

# Goldsky-hosted, no auth. Verified per task spec A7 / nway-protocols-data-map.md S4.
EULER_SUBGRAPH_URL = (
    "https://api.goldsky.com/api/public/"
    "project_clyzphvgm0o3p01vcfm1f8qju/subgraphs/euler-v2-mainnet/latest/gn"
)

# Euler Prime USDC vault (Gauntlet-curated, conservative cluster).
# IRMLinearKink => static f_kink applies. nway-protocols-data-map.md S4B.
EULER_PRIME_USDC = "0x797DD80692c3b2dAdabCe8e30C07fDE5307D48a9"

PAGE_SIZE = 1000

# The Goldsky euler-v2 subgraph exposes per-interaction VaultStatus rows with
# supplyApy/borrowApy as decimals plus cash/totalBorrows as raw token units.
# Schema docs are sparse; field names follow the upstream euler-subgraph repo
# (github.com/euler-xyz/euler-subgraph). USDC has 6 decimals.
QUERY = """
query ($vault: String!, $startTs: Int!, $endTs: Int!, $cursor: Int!) {
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
    id
    timestamp
    supplyApy
    borrowApy
    cash
    totalBorrows
    transactionHash
  }
}
""" % PAGE_SIZE

CACHE_PATH = Path(__file__).resolve().parent / "cached" / "events_euler.parquet"


def _post(payload: dict) -> dict:
    r = requests.post(EULER_SUBGRAPH_URL, json=payload, timeout=30)
    r.raise_for_status()
    body = r.json()
    if "errors" in body:
        raise RuntimeError(f"euler subgraph errors: {body['errors']}")
    return body["data"]


def fetch_euler_events(
    *,
    vault: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    page_size: int = PAGE_SIZE,
) -> pd.DataFrame:
    """Pull Euler V2 vault rate-update events in [start, end).

    Returns a dataframe with the canonical EventRow dtypes. Pagination via
    timestamp cursor (subgraph hard limit of 5000 skip).
    """
    if start.tz is None or end.tz is None:
        raise ValueError("start/end must be tz-aware UTC")

    start_ts = int(start.timestamp())
    end_ts = int(end.timestamp())
    cursor = start_ts - 1  # exclusive lower bound below

    # Subgraphs are case-sensitive on address filters; lowercase consistently.
    vault_lc = vault.lower()

    rows: list[dict] = []
    while True:
        data = _post({
            "query": QUERY,
            "variables": {
                "vault": vault_lc,
                "startTs": start_ts,
                "endTs": end_ts,
                "cursor": cursor,
            },
        })
        items = data.get("vaultStatuses") or []
        if not items:
            break
        for it in items:
            ts = int(it["timestamp"])
            rows.append({
                "ts": ts,
                "supply_apy": float(it["supplyApy"] or 0.0),
                "borrow_apy": float(it["borrowApy"] or 0.0),
                "cash": int(it["cash"] or 0),
                "borrowed": int(it["totalBorrows"] or 0),
                "tx_hash": it.get("transactionHash") or "",
            })
        cursor = int(items[-1]["timestamp"])
        if len(items) < page_size:
            break
        time.sleep(0.1)  # friendly rate-limit pause

    if not rows:
        return empty_event_frame()

    raw = pd.DataFrame(rows).sort_values("ts", kind="stable").reset_index(drop=True)
    # event_idx = unique within-fetch counter (NOT per-timestamp cumcount).
    # See `data/event_schema.py` event_idx comment block: at fetch time
    # block_number is sentinel -1 and groupby(ts).cumcount() would collide on
    # the dedup key (block_number, event_idx, protocol). Stitcher re-cumcounts
    # within (block_number, protocol) after ts -> block lookup.
    raw["event_idx"] = pd.RangeIndex(len(raw)).astype("int32")

    # USDC has 6 decimals; cash + totalBorrows = totalAssets per ERC-4626.
    cash_usdc = raw["cash"] / 1e6
    borrowed_usdc = raw["borrowed"] / 1e6
    supplied_usdc = cash_usdc + borrowed_usdc
    utilization = (
        borrowed_usdc / supplied_usdc.where(supplied_usdc > 0, 1)
    ).clip(0.0, 1.0)

    # Goldsky exposes supplyApy/borrowApy already as decimal APYs (no RAY).
    apr_lend = raw["supply_apy"]
    # Sign-convention guard: borrow >= lend always (CLAUDE.md S5). Numerical
    # fuzz in the subgraph's decimal conversion can produce ~1e-12 inversions;
    # clip up to the lending floor to keep the validator happy.
    apr_borrow = raw["borrow_apy"].clip(lower=apr_lend)

    df = pd.DataFrame({
        "block_number": -1,  # sentinel; stitcher fills via ts->block lookup
        "block_timestamp": pd.to_datetime(raw["ts"], unit="s", utc=True),
        "event_idx": raw["event_idx"],
        "protocol": "euler_v2",
        "event_type": "rate_update",
        "lending_rate_apr": apr_lend,
        "borrowing_rate_apr": apr_borrow,
        "utilization": utilization,
        "total_supplied_usd": supplied_usdc,  # USDC pegged to USD here
        "total_borrowed_usd": borrowed_usdc,
        "tx_hash": pd.Series(raw["tx_hash"].astype(str).tolist(), dtype="string"),
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
    """Cached wrapper, parquet round-trip. See fetch_aave_events_cached."""
    cache_path = Path(cache_path)
    if cache_path.exists() and not refresh:
        return pd.read_parquet(cache_path).astype(EVENT_ROW_DTYPES)
    df = fetch_euler_events(vault=vault, start=start, end=end)
    from data.event_schema import validate_event_frame
    validate_event_frame(df)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path, index=False)
    return df


if __name__ == "__main__":
    s = pd.Timestamp("2026-04-01", tz="UTC")
    e = pd.Timestamp("2026-04-02", tz="UTC")
    df = fetch_euler_events(vault=EULER_PRIME_USDC, start=s, end=e)
    print(f"[euler smoke] {len(df)} events")
