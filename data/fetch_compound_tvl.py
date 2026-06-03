"""Fetch REAL Compound V3 (Comet USDC) TVL via archive eth_call — closes
audit gap G2 (compound_v3_tvl_usd was a constant-0 placeholder).

Comet `totalSupply()` (selector 0x18160ddd) returns the total base asset
(USDC, 6 decimals) supplied to the market; TVL_usd = totalSupply / 1e6
(USDC ~ $1).  Sampled daily across the panel block range and saved for
forward-fill onto the per-block grid.

Needs a paid/free archive `ETHEREUM_RPC_URL` (Alchemy free tier suffices;
verified to serve historical eth_call).

Output: data/cached/f4_compound_tvl_daily.parquet  (timestamp, block_number, tvl_usd)
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data" / "cached" / "per_block_panel.parquet"
OUT = ROOT / "data" / "cached" / "f4_compound_tvl_daily.parquet"

COMET_USDC = "0xc3d688B66703497DAA19211EEdff47f25384cdc3"
SEL_TOTAL_SUPPLY = "0x18160ddd"
BLOCKS_PER_DAY = 7200


def _rpc() -> str:
    url = os.environ.get("ETHEREUM_RPC_URL")
    if not url:
        raise RuntimeError("ETHEREUM_RPC_URL not set")
    return url


def _total_supply(block: int) -> float | None:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
               "params": [{"to": COMET_USDC, "data": SEL_TOTAL_SUPPLY}, hex(block)]}
    try:
        r = requests.post(_rpc(), json=payload, timeout=20).json()
        if "result" in r and r["result"] not in ("0x", None):
            return int(r["result"], 16) / 1e6
    except Exception:
        pass
    return None


def main() -> int:
    panel = pd.read_parquet(PANEL, columns=["block_number", "block_timestamp"])
    panel["block_timestamp"] = pd.to_datetime(panel["block_timestamp"], utc=True)
    b0, b1 = int(panel.block_number.min()), int(panel.block_number.max())
    ts0 = panel.block_timestamp.min()
    blocks = list(range(b0, b1, BLOCKS_PER_DAY))
    print(f"sampling {len(blocks)} daily blocks for Comet totalSupply", flush=True)

    rows, miss = [], 0
    for i, blk in enumerate(blocks):
        tvl = _total_supply(blk)
        if tvl is None:
            miss += 1
            continue
        ts = ts0 + pd.Timedelta(seconds=(blk - b0) * 12)
        rows.append({"timestamp": ts, "block_number": blk, "tvl_usd": tvl})
        if i % 50 == 0:
            print(f"  [{i}/{len(blocks)}] block {blk} -> ${tvl/1e6:.1f}M", flush=True)
        time.sleep(0.03)

    df = pd.DataFrame(rows)
    df.to_parquet(OUT, index=False)
    s = df["tvl_usd"]
    print(f"\nwrote {OUT} ({len(df)} rows, {miss} misses)", flush=True)
    print(f"Compound TVL: mean ${s.mean()/1e6:.0f}M  min ${s.min()/1e6:.0f}M  "
          f"max ${s.max()/1e6:.0f}M", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
