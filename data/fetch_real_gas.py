"""Fetch REAL historical Ethereum gas (base fee + priority tip) via
eth_feeHistory on a free archive RPC — no API key required.

Closes audit gap G1: the panel's gas_price_gwei was a flat 25 gwei
placeholder (Owlracle fetch had failed). Two free archive endpoints
(publicnode, drpc) serve eth_feeHistory at historical blocks without
authentication, so we can build a real daily gas series end-to-end
locally.

Effective gas price a rebalance tx pays = base_fee + priority_tip.
We sample one block per ~day and take the 50th-percentile priority
reward, then forward-fill onto the per-block grid downstream.

Output: data/cached/f4_gas_gwei_daily_real.parquet  (timestamp, gas_gwei)
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data" / "cached" / "per_block_panel.parquet"
OUT = ROOT / "data" / "cached" / "f4_gas_gwei_daily_real.parquet"

ENDPOINTS = [
    "https://ethereum-rpc.publicnode.com",
    "https://eth.drpc.org",
]
BLOCKS_PER_DAY = 7200  # 12 s/block


def _fee_history(block_hex: str) -> float | None:
    """Return effective gas price (base + 50th-pct priority) in gwei at a block."""
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "eth_feeHistory",
        "params": ["0x1", block_hex, [50]],
    }
    for ep in ENDPOINTS:
        try:
            r = requests.post(ep, json=payload, timeout=15)
            b = r.json().get("result")
            if not b or "baseFeePerGas" not in b:
                continue
            base = int(b["baseFeePerGas"][0], 16)
            tip = 0
            if b.get("reward") and b["reward"][0]:
                tip = int(b["reward"][0][0], 16)
            return (base + tip) / 1e9
        except Exception:
            continue
    return None


def main() -> int:
    panel = pd.read_parquet(PANEL, columns=["block_number", "block_timestamp"])
    panel["block_timestamp"] = pd.to_datetime(panel["block_timestamp"], utc=True)
    b0, b1 = int(panel.block_number.min()), int(panel.block_number.max())
    ts0 = panel.block_timestamp.min()
    blocks = list(range(b0, b1, BLOCKS_PER_DAY))
    print(f"sampling {len(blocks)} daily blocks [{b0}..{b1}]", flush=True)

    rows = []
    miss = 0
    for i, blk in enumerate(blocks):
        g = _fee_history(hex(blk))
        if g is None:
            miss += 1
            continue
        ts = ts0 + pd.Timedelta(seconds=(blk - b0) * 12)
        rows.append({"timestamp": ts, "block_number": blk, "gas_gwei": g})
        if i % 50 == 0:
            print(f"  [{i}/{len(blocks)}] block {blk} -> {g:.2f} gwei", flush=True)
        time.sleep(0.05)  # be polite to the free endpoint

    df = pd.DataFrame(rows)
    df.to_parquet(OUT, index=False)
    print(f"\nwrote {OUT} ({len(df)} rows, {miss} misses)", flush=True)
    if len(df):
        s = df["gas_gwei"]
        print(f"gas gwei: mean={s.mean():.1f} median={s.median():.1f} "
              f"min={s.min():.1f} max={s.max():.1f}  "
              f">25: {(s>25).mean()*100:.0f}%  >50: {(s>50).mean()*100:.0f}%  "
              f">100: {(s>100).mean()*100:.0f}%", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
