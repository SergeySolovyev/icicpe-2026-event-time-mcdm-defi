"""Per-event (per-sampled-block) Fluid USDC rate fetcher (Task A8).

Fluid has NO production subgraph -- we sample via RPC eth_call against
FluidLendingResolver.getOverallTokenData(USDC). One sample = one EventRow.

CRITICAL unit note: Fluid uses its own RATE_PRECISION = 1e12 for rates,
NOT RAY (1e27, Aave) and NOT WAD (1e18, Compound). Watch units when
cross-checking values.

The FLUID_LENDING_RESOLVER address below is a PLACEHOLDER per
docs/research/nway-protocols-data-map.md and MUST be verified on first
run against:
    github.com/Instadapp/fluid-contracts-public/contracts/config/mainnet.json
Same discipline as CLAUDE.md S3 for the Aave/Compound subgraph IDs.

ABI layout assumed for getOverallTokenData(address) return data
(verify on first live run; adjust slice offsets if parsing fails):
    [0   :  32]  supplyRate         (uint256, scaled by RATE_PRECISION=1e12)
    [32  :  64]  borrowRate         (uint256, scaled by RATE_PRECISION=1e12)
    [64  :  96]  utilization        (uint256, scaled by 1e4)
    [96  : 128]  totalSupplied      (uint256, USDC has 6 decimals)

Batch cap 100 per JSON-RPC request (CLAUDE.md S3e free-RPC cap), same
pattern as data/fetch_compound_events.py.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import requests
from eth_utils import keccak

from data.event_schema import EVENT_ROW_DTYPES, empty_event_frame

# PLACEHOLDER -- verify against Instadapp fluid-contracts-public mainnet.json
# on first live run. See module docstring.
FLUID_LENDING_RESOLVER = "0xafe26eb7945c4d8403a0b3afdc5b3a4f1c8c0e6f"
USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"

# Fluid's own scaling -- NOT RAY, NOT WAD.
RATE_PRECISION = 10**12
UTIL_PRECISION = 10**4

# Selector for getOverallTokenData(address) -- computed at import time so
# any keccak/eth_utils mismatch surfaces immediately.
SEL_GET_OVERALL = "0x" + keccak(text="getOverallTokenData(address)").hex()[:8]

# Post-merge block-time anchor (matches data/fetch_compound_events.py).
POS_GENESIS_TS = 1663224162   # 2022-09-15 block 15_537_393
POS_GENESIS_BLOCK = 15_537_393
BLOCK_TIME_SEC = 12

RPC_BATCH_CAP = 100

CACHE_PATH = Path(__file__).resolve().parent / "cached" / "events_fluid.parquet"


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
        by_id = {b["id"]: b for b in body}
        out.extend(by_id[req["id"]] for req in chunk)
    return out


def _ts_to_block(ts: int) -> int:
    """Approximate block lookup; 12s/block since Sept 2022 PoS merge."""
    return POS_GENESIS_BLOCK + (ts - POS_GENESIS_TS) // BLOCK_TIME_SEC


def _block_to_ts(block: int) -> int:
    return POS_GENESIS_TS + (block - POS_GENESIS_BLOCK) * BLOCK_TIME_SEC


def fetch_fluid_events(
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    sample_every_n_blocks: int = 100,
) -> pd.DataFrame:
    """Sample Fluid USDC rates via RPC eth_call in [start, end).

    Parameters
    ----------
    start, end : tz-aware UTC pd.Timestamp
    sample_every_n_blocks : int
        Default 100 (~20 min apart). One EventRow per sampled block.

    Returns
    -------
    EventRow dataframe (canonical schema). block_number is the REAL
    Ethereum block number (not the -1 sentinel used by subgraph fetchers),
    so event_idx=0 is unique per (block_number, protocol).
    """
    if start.tz is None or end.tz is None:
        raise ValueError("start/end must be tz-aware UTC")

    blk_start = _ts_to_block(int(start.timestamp()))
    blk_end = _ts_to_block(int(end.timestamp()))
    blocks = list(range(blk_start, blk_end, sample_every_n_blocks))
    if not blocks:
        return empty_event_frame()

    # eth_call payload: selector + 32-byte left-padded USDC address.
    addr_padded = "0" * 24 + USDC[2:].lower()
    data_payload = SEL_GET_OVERALL + addr_padded

    reqs = [
        {
            "jsonrpc": "2.0", "id": i, "method": "eth_call",
            "params": [
                {"to": FLUID_LENDING_RESOLVER, "data": data_payload},
                hex(b),
            ],
        }
        for i, b in enumerate(blocks)
    ]
    resps = _batch_call(reqs)

    rows: list[dict] = []
    for b, r in zip(blocks, resps):
        result_hex = r.get("result") or "0x"
        if not result_hex.startswith("0x"):
            continue
        try:
            result = bytes.fromhex(result_hex[2:])
        except ValueError:
            continue
        # Need at least 4 * 32B fields. Resolver may return more.
        if len(result) < 128:
            continue
        supply_rp = int.from_bytes(result[0:32], "big")
        borrow_rp = int.from_bytes(result[32:64], "big")
        util_raw = int.from_bytes(result[64:96], "big")
        supplied = int.from_bytes(result[96:128], "big")
        rows.append({
            "block": b,
            "ts": _block_to_ts(b),
            "supply_rate": supply_rp,
            "borrow_rate": borrow_rp,
            "util": util_raw / UTIL_PRECISION,
            "supplied": supplied,
        })

    if not rows:
        return empty_event_frame()

    raw = pd.DataFrame(rows)
    apr_supply = raw["supply_rate"] / RATE_PRECISION
    apr_borrow = raw["borrow_rate"] / RATE_PRECISION

    df = pd.DataFrame({
        "block_number": raw["block"].astype("int64"),
        "block_timestamp": pd.to_datetime(raw["ts"], unit="s", utc=True),
        # Real block_number is unique per sample, so event_idx=0 is fine
        # (the (block_number, event_idx, protocol) dedup key remains unique).
        "event_idx": 0,
        "protocol": "fluid",
        "event_type": "rate_update",
        "lending_rate_apr": apr_supply,
        "borrowing_rate_apr": apr_borrow.clip(lower=apr_supply),
        "utilization": raw["util"].clip(0.0, 1.0),
        "total_supplied_usd": raw["supplied"] / 1e6,  # USDC 6 decimals
        "total_borrowed_usd": float("nan"),
        "tx_hash": pd.Series([""] * len(raw), dtype="string"),
        "source": "rpc",
    })
    return df.astype(EVENT_ROW_DTYPES)


def fetch_fluid_events_cached(
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    sample_every_n_blocks: int = 100,
    cache_path: Path | str = CACHE_PATH,
    refresh: bool = False,
) -> pd.DataFrame:
    """Cached wrapper around fetch_fluid_events with parquet round-trip."""
    cache_path = Path(cache_path)
    if cache_path.exists() and not refresh:
        return pd.read_parquet(cache_path).astype(EVENT_ROW_DTYPES)
    df = fetch_fluid_events(
        start=start, end=end,
        sample_every_n_blocks=sample_every_n_blocks,
    )
    from data.event_schema import validate_event_frame
    validate_event_frame(df)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path, index=False)
    return df


if __name__ == "__main__":
    s = pd.Timestamp("2026-04-01", tz="UTC")
    e = pd.Timestamp("2026-04-02", tz="UTC")
    out = fetch_fluid_events(start=s, end=e)
    print(f"[fluid smoke] {len(out)} sampled rows")
