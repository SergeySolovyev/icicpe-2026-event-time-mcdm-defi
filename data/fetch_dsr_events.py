"""Maker DSR (Dai Savings Rate) rate-change event fetcher.

Signal class F1 from MacKenzie (2021) Table 3.2 ("futures lead" analog):
DSR is the de-facto risk-free rate in the stablecoin ecosystem and
empirically leads Aave/Compound USDC supply rates because Maker is a
major USDC LP.

Source: eth_getLogs on the Pot contract `File(bytes32 indexed what, uint256 data)`
events with `topic1 == keccak('dsr')`. DSR change events are sparse
(typically <50 over an 18-month window), so we look up `block.timestamp`
via per-block `eth_getBlockByNumber` calls.

Conversion: `apr_decimal = (dsr_ray / RAY)**31_536_000 - 1` where RAY = 1e27.

event_idx contract (locked by data/event_schema.py commit edc67e0):
    DSR events come back from eth_getLogs with real block_number values
    (NOT sentinel -1). event_idx is `pd.RangeIndex(len(raw))` -- globally
    unique within the fetch frame.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import requests
from eth_utils import keccak

from data.event_schema import EVENT_ROW_DTYPES, empty_event_frame

POT_ADDR = "0x197E90f9FAD81970bA7976f33CbD77088E5D7cf7"
FILE_EVENT_SIG = "0x" + keccak(text="File(bytes32,uint256)").hex()
DSR_KEY = "0x" + b"dsr".rjust(32, b"\x00").hex()
RAY = 10**27
SECONDS_PER_YEAR = 31_536_000

# Approximate ts->block conversion (12s/block PoS, since Sept 2022 merge).
POS_GENESIS_TS = 1663224162
POS_GENESIS_BLOCK = 15_537_393

CACHE_PATH = Path(__file__).resolve().parent / "cached" / "events_dsr.parquet"


def _rpc_endpoint() -> str:
    url = os.environ.get("ETHEREUM_RPC_URL")
    if not url:
        raise RuntimeError("ETHEREUM_RPC_URL not set")
    return url


def _ts_to_block(ts: int) -> int:
    return POS_GENESIS_BLOCK + (ts - POS_GENESIS_TS) // 12


def _get_block_ts(block: int) -> int:
    """Fetch block.timestamp for one block number."""
    r = requests.post(_rpc_endpoint(), json={
        "jsonrpc": "2.0", "id": 1, "method": "eth_getBlockByNumber",
        "params": [hex(block), False],
    }, timeout=15)
    r.raise_for_status()
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"eth_getBlockByNumber error: {body['error']}")
    return int(body["result"]["timestamp"], 16)


def fetch_dsr_events(*, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Pull all Maker DSR rate-change events in [start, end).

    Returns a dataframe with the canonical EventRow dtypes. Empty frame
    if no DSR changes occurred in the window.
    """
    if start.tz is None or end.tz is None:
        raise ValueError("start/end must be tz-aware UTC")

    blk_start = _ts_to_block(int(start.timestamp()))
    blk_end = _ts_to_block(int(end.timestamp()))

    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "eth_getLogs",
        "params": [{
            "address": POT_ADDR,
            "fromBlock": hex(blk_start),
            "toBlock": hex(blk_end),
            "topics": [FILE_EVENT_SIG, DSR_KEY],
        }],
    }
    r = requests.post(_rpc_endpoint(), json=payload, timeout=60)
    r.raise_for_status()
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"eth_getLogs error: {body['error']}")
    logs = body.get("result") or []
    if not logs:
        return empty_event_frame()

    # Pot's `File(bytes32 indexed what, uint256 data)` puts the indexed
    # `what` in topics[1] and `data` (the new dsr ray) in the log's `data`
    # field since `data` is NOT indexed. Some RPCs may surface a 3rd topic
    # for legacy reasons -- prefer `data`, fall back to topics[2].
    block_ts_cache: dict[int, int] = {}
    rows: list[dict] = []
    for log in logs:
        blk = int(log["blockNumber"], 16)
        data_hex = log.get("data") or "0x"
        if data_hex not in ("0x", ""):
            dsr_ray = int(data_hex, 16)
        elif len(log.get("topics") or []) >= 3:
            dsr_ray = int(log["topics"][2], 16)
        else:
            continue
        if blk not in block_ts_cache:
            block_ts_cache[blk] = _get_block_ts(blk)
        apr = (dsr_ray / RAY) ** SECONDS_PER_YEAR - 1
        rows.append({
            "block": blk,
            "ts": block_ts_cache[blk],
            "apr": apr,
            "tx": log.get("transactionHash", ""),
        })

    if not rows:
        return empty_event_frame()

    raw = pd.DataFrame(rows).sort_values(["ts", "block"]).reset_index(drop=True)
    raw["event_idx"] = pd.RangeIndex(len(raw)).astype("int32")

    lending = raw["apr"].clip(lower=0)
    df = pd.DataFrame({
        "block_number": raw["block"].astype("int64"),
        "block_timestamp": pd.to_datetime(raw["ts"], unit="s", utc=True),
        "event_idx": raw["event_idx"],
        "protocol": "dsr",
        "event_type": "dsr_update",
        "lending_rate_apr": lending,
        "borrowing_rate_apr": lending,  # DSR has no borrow side; validator needs borrow >= lend
        "utilization": float("nan"),
        "total_supplied_usd": float("nan"),
        "total_borrowed_usd": float("nan"),
        "tx_hash": raw["tx"].astype("string"),
        "source": "rpc",
    })
    return df.astype(EVENT_ROW_DTYPES)


def fetch_dsr_events_cached(
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    cache_path: Path | str = CACHE_PATH,
    refresh: bool = False,
) -> pd.DataFrame:
    """Cached wrapper, parquet round-trip. Validates on write."""
    cache_path = Path(cache_path)
    if cache_path.exists() and not refresh:
        return pd.read_parquet(cache_path).astype(EVENT_ROW_DTYPES)
    df = fetch_dsr_events(start=start, end=end)
    from data.event_schema import validate_event_frame
    validate_event_frame(df)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path, index=False)
    return df


if __name__ == "__main__":
    s = pd.Timestamp("2024-11-01", tz="UTC")
    e = pd.Timestamp("2025-05-01", tz="UTC")
    df = fetch_dsr_events(start=s, end=e)
    print(f"[dsr smoke] {len(df)} events "
          f"{df['block_timestamp'].min() if len(df) else 'n/a'} .. "
          f"{df['block_timestamp'].max() if len(df) else 'n/a'}")
