"""Fetch Spark (SparkLend) USDC borrow rate via archive eth_call on the
SparkLend Pool — closes audit gap G3 (spark_borrow_apr was missing; the
hourly subgraph source carried only lending_apr).

SparkLend is an Aave V3 fork: Pool.getReserveData(asset) returns the
canonical ReserveData struct. Verified word layout (probed on-chain):
    word[2] = currentLiquidityRate     (lending APR x RAY 1e27)
    word[4] = currentVariableBorrowRate (borrow  APR x RAY 1e27)

ACADEMIC-RIGOUR VALIDATION (built in): we also extract word[2]
(lending) and check it against the existing panel spark_lending_apr at
matched timestamps. If the RPC-decoded lending matches the
subgraph-sourced lending, the decode is proven correct and the borrow
rate (word[4]) is trustworthy. The script prints the validation MAE.

Verified address: SparkLend Pool 0xC13e21B648A5Ee794902342038FF3aDAB66BE987
(Ethereum mainnet; the gateway Pool in fetch_spark_events.py).

Needs archive ETHEREUM_RPC_URL.
Output: data/cached/f4_spark_rates_daily.parquet
        (timestamp, block_number, lending_apr, borrow_apr)
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd
import requests
from eth_utils import keccak

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data" / "cached" / "per_block_panel.parquet"
OUT = ROOT / "data" / "cached" / "f4_spark_rates_daily.parquet"

SPARK_POOL = "0xC13e21B648A5Ee794902342038FF3aDAB66BE987"
USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
RAY = 10**27
BLOCKS_PER_DAY = 7200
SEL = "0x" + keccak(text="getReserveData(address)").hex()[:8]


def _rpc() -> str:
    url = os.environ.get("ETHEREUM_RPC_URL")
    if not url:
        raise RuntimeError("ETHEREUM_RPC_URL not set")
    return url


def _reserve_rates(block: int) -> tuple[float, float] | None:
    data = SEL + "0" * 24 + USDC[2:]
    try:
        r = requests.post(_rpc(), json={"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                          "params": [{"to": SPARK_POOL, "data": data}, hex(block)]},
                          timeout=20).json()
        res = r.get("result")
        if not res or res == "0x":
            return None
        raw = bytes.fromhex(res[2:])
        if len(raw) < 32 * 5:
            return None
        lend = int.from_bytes(raw[64:96], "big") / RAY      # word[2]
        borrow = int.from_bytes(raw[128:160], "big") / RAY  # word[4]
        return lend, borrow
    except Exception:
        return None


def main() -> int:
    panel = pd.read_parquet(PANEL, columns=["block_number", "block_timestamp", "spark_lending_apr"])
    panel["block_timestamp"] = pd.to_datetime(panel["block_timestamp"], utc=True)
    b0, b1 = int(panel.block_number.min()), int(panel.block_number.max())
    ts0 = panel.block_timestamp.min()
    blocks = list(range(b0, b1, BLOCKS_PER_DAY))
    print(f"sampling {len(blocks)} daily blocks; selector {SEL}", flush=True)

    rows, miss = [], 0
    for i, blk in enumerate(blocks):
        rr = _reserve_rates(blk)
        if rr is None:
            miss += 1
            continue
        lend, borrow = rr
        ts = ts0 + pd.Timedelta(seconds=(blk - b0) * 12)
        rows.append({"timestamp": ts, "block_number": blk,
                     "lending_apr": lend, "borrow_apr": borrow})
        if i % 50 == 0:
            print(f"  [{i}/{len(blocks)}] block {blk} lend={lend*100:.2f}% borrow={borrow*100:.2f}%", flush=True)
        time.sleep(0.03)

    df = pd.DataFrame(rows)
    df.to_parquet(OUT, index=False)
    print(f"\nwrote {OUT} ({len(df)} rows, {miss} misses)", flush=True)

    # --- VALIDATION: RPC lending vs panel (subgraph) lending ---
    pl = panel[["block_number", "spark_lending_apr"]].dropna()
    m = pd.merge_asof(df.sort_values("block_number"), pl.sort_values("block_number"),
                      on="block_number", direction="nearest")
    m = m.dropna(subset=["spark_lending_apr"])
    if len(m):
        mae = (m["lending_apr"] - m["spark_lending_apr"]).abs().mean()
        corr = m["lending_apr"].corr(m["spark_lending_apr"])
        print(f"VALIDATION (RPC lending vs panel subgraph lending): "
              f"MAE={mae*1e4:.1f}bp  corr={corr:.4f}  n={len(m)}", flush=True)
        print(f"  -> {'DECODE VALIDATED; borrow trustworthy' if mae < 0.005 else 'WARNING: mismatch, recheck offsets'}", flush=True)
    print(f"borrow_apr: mean {df['borrow_apr'].mean()*100:.2f}%  "
          f"lend mean {df['lending_apr'].mean()*100:.2f}%", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
