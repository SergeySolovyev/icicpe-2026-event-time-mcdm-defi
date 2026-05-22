"""Per-event (per-sampled-block) Compound V3 USDC rate fetcher.

The Messari subgraph does NOT index the base Comet market's rates
(CLAUDE.md S3c) -- `Market.rates` is None for `0xc3d688...`. We must
fall back to RPC view-calls.

We do NOT call eth_call on every block (~3.9M calls = days of wall-clock).
We sample every N blocks (default 100 -> ~12s * 100 = 20 min between samples,
~130k samples over 18 months). The decision-policy backtest still evaluates
per-block by forward-fill between samples.

Rate conversion (CLAUDE.md S3d):
    supply_rate_per_second_wad = getSupplyRate(getUtilization())
    apr_decimal = (supply_rate_per_second_wad / 1e18) * 31_536_000

Selectors verified via keccak256 (CLAUDE.md S3d):
    getUtilization()           = 0x7eb71131
    getSupplyRate(uint256)     = 0xd955759d
    getBorrowRate(uint256)     = 0x9fa83b5a

Batch cap 100 per JSON-RPC request (CLAUDE.md S3e free-RPC cap).
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import requests

from data.event_schema import EVENT_ROW_DTYPES, empty_event_frame

COMET_USDC = "0xc3d688B66703497DAA19211EEdff47f25384cdc3"
SEL_UTIL = "0x7eb71131"
SEL_SUPPLY_RATE = "0xd955759d"
SEL_BORROW_RATE = "0x9fa83b5a"
WAD = 10**18
SECONDS_PER_YEAR = 31_536_000

# Post-merge block-time anchor (CLAUDE.md S3c context).
POS_GENESIS_TS = 1663224162   # 2022-09-15 block 15_537_393
POS_GENESIS_BLOCK = 15_537_393
BLOCK_TIME_SEC = 12

RPC_BATCH_CAP = 100

CACHE_PATH = Path(__file__).resolve().parent / "cached" / "events_compound.parquet"


def _rpc_endpoint() -> str:
    url = os.environ.get("ETHEREUM_RPC_URL")
    if not url:
        raise RuntimeError("ETHEREUM_RPC_URL not set")
    return url


def _batch_call(reqs: list[dict]) -> list[dict]:
    """Send a JSON-RPC batch. Splits at RPC_BATCH_CAP per CLAUDE.md S3e cap."""
    out: list[dict] = []
    for i in range(0, len(reqs), RPC_BATCH_CAP):
        chunk = reqs[i:i + RPC_BATCH_CAP]
        r = requests.post(_rpc_endpoint(), json=chunk, timeout=60)
        r.raise_for_status()
        body = r.json()
        if isinstance(body, dict):
            body = [body]
        # JSON-RPC servers MAY reorder by id -- align back to request order.
        by_id = {b["id"]: b for b in body}
        out.extend(by_id[req["id"]] for req in chunk)
    return out


def _ts_to_block(ts: int) -> int:
    """Approximate block lookup. 12s/block since Sept 2022 PoS merge."""
    return POS_GENESIS_BLOCK + (ts - POS_GENESIS_TS) // BLOCK_TIME_SEC


def _block_to_ts(block: int) -> int:
    """Inverse of _ts_to_block (approximate)."""
    return POS_GENESIS_TS + (block - POS_GENESIS_BLOCK) * BLOCK_TIME_SEC


def fetch_compound_events(
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    sample_every_n_blocks: int = 100,
) -> pd.DataFrame:
    """Sample Compound V3 USDC rates via RPC view-calls in [start, end).

    Parameters
    ----------
    start, end : tz-aware UTC pd.Timestamp
    sample_every_n_blocks : int
        Default 100 (~20 min apart). Reduce for higher resolution at
        proportionally higher RPC cost.

    Returns
    -------
    EventRow dataframe (canonical schema) with one row per sampled block.
    """
    if start.tz is None or end.tz is None:
        raise ValueError("start/end must be tz-aware UTC")

    blk_start = _ts_to_block(int(start.timestamp()))
    blk_end = _ts_to_block(int(end.timestamp()))
    blocks = list(range(blk_start, blk_end, sample_every_n_blocks))
    if not blocks:
        return empty_event_frame()

    # Phase 1: getUtilization() per sampled block.
    util_reqs = [
        {
            "jsonrpc": "2.0", "id": i, "method": "eth_call",
            "params": [
                {"to": COMET_USDC, "data": SEL_UTIL},
                hex(b),
            ],
        }
        for i, b in enumerate(blocks)
    ]
    util_resps = _batch_call(util_reqs)
    utils_wad = [
        int(r["result"], 16) if r.get("result") else 0
        for r in util_resps
    ]

    # Phase 2: getSupplyRate(util) and getBorrowRate(util) per sampled block.
    rate_reqs: list[dict] = []
    for i, (b, u) in enumerate(zip(blocks, utils_wad)):
        data_supply = SEL_SUPPLY_RATE + f"{u:064x}"
        data_borrow = SEL_BORROW_RATE + f"{u:064x}"
        rate_reqs.append({
            "jsonrpc": "2.0", "id": 2 * i, "method": "eth_call",
            "params": [{"to": COMET_USDC, "data": data_supply}, hex(b)],
        })
        rate_reqs.append({
            "jsonrpc": "2.0", "id": 2 * i + 1, "method": "eth_call",
            "params": [{"to": COMET_USDC, "data": data_borrow}, hex(b)],
        })
    rate_resps = _batch_call(rate_reqs)

    supply_per_sec_wad: list[int] = []
    borrow_per_sec_wad: list[int] = []
    for i in range(len(blocks)):
        s = rate_resps[2 * i]
        b = rate_resps[2 * i + 1]
        supply_per_sec_wad.append(int(s["result"], 16) if s.get("result") else 0)
        borrow_per_sec_wad.append(int(b["result"], 16) if b.get("result") else 0)

    apr_supply = [s / WAD * SECONDS_PER_YEAR for s in supply_per_sec_wad]
    apr_borrow = [b / WAD * SECONDS_PER_YEAR for b in borrow_per_sec_wad]
    util = [min(max(u / WAD, 0.0), 1.0) for u in utils_wad]

    block_ts = [_block_to_ts(b) for b in blocks]

    df = pd.DataFrame({
        "block_number": blocks,
        "block_timestamp": pd.to_datetime(block_ts, unit="s", utc=True),
        "event_idx": 0,
        "protocol": "compound_v3",
        "event_type": "rate_update",
        "lending_rate_apr": apr_supply,
        "borrowing_rate_apr": apr_borrow,
        "utilization": util,
        "total_supplied_usd": float("nan"),  # not exposed by Comet view-calls
        "total_borrowed_usd": float("nan"),
        "tx_hash": pd.Series([""] * len(blocks), dtype="string"),
        "source": "rpc",
    })
    return df.astype(EVENT_ROW_DTYPES)


def fetch_compound_events_cached(
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    sample_every_n_blocks: int = 100,
    cache_path: Path | str = CACHE_PATH,
    refresh: bool = False,
) -> pd.DataFrame:
    """Cached wrapper around fetch_compound_events with parquet round-trip."""
    cache_path = Path(cache_path)
    if cache_path.exists() and not refresh:
        return pd.read_parquet(cache_path).astype(EVENT_ROW_DTYPES)
    df = fetch_compound_events(
        start, end, sample_every_n_blocks=sample_every_n_blocks,
    )
    from data.event_schema import validate_event_frame
    validate_event_frame(df)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path, index=False)
    return df


if __name__ == "__main__":
    s = pd.Timestamp("2026-04-01", tz="UTC")
    e = pd.Timestamp("2026-04-02", tz="UTC")
    out = fetch_compound_events(s, e)
    print(f"[compound smoke] {len(out)} sampled rows")
