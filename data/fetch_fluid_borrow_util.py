"""Fetch Fluid USDC borrow rate + utilization via the VERIFIED Fluid
LiquidityResolver — closes audit gaps G4 (fluid_borrow_apr missing,
fluid_utilization was a constant-0.85 placeholder).

Verified address (official Fluid deployments.md, Ethereum mainnet):
    LiquidityResolver = 0xca13A15de31235A37134B4717021C35A3CF25C60
(The agent code used 0x52Aa... — that is the Liquidity CORE/proxy, which
has no getOverallTokenData; it returned 0 bytes. The periphery resolver
above is the correct one.)

getOverallTokenData(address) returns the OverallTokenData struct; the
leading words decode as (validated below):
    w[0] = borrowRate   / 100  (percent)
    w[1] = supplyRate   / 100  (percent)   [= lending APR]
    w[2] = fee          / 1e4  (fraction)
    w[3] = utilization  / 1e4  (fraction)
    w[5] = lastUpdateTimestamp (unix)

DOUBLE VALIDATION (academic rigour):
  (1) INTERNAL identity: supplyRate == borrowRate * util * (1 - fee).
      Confirms all three field scalings simultaneously.
  (2) EXTERNAL: supplyRate vs the independent DeFiLlama fluid_daily APY
      (data/cached/fluid_daily.parquet). Prints MAE.

Needs archive ETHEREUM_RPC_URL.
Output: data/cached/f4_fluid_rates_daily.parquet
        (timestamp, block_number, supply_apr, borrow_apr, utilization, fee)
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
FLUID_DAILY = ROOT / "data" / "cached" / "fluid_daily.parquet"
OUT = ROOT / "data" / "cached" / "f4_fluid_rates_daily.parquet"

RESOLVER = "0xca13A15de31235A37134B4717021C35A3CF25C60"
USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
BLOCKS_PER_DAY = 7200
SEL = "0x" + keccak(text="getOverallTokenData(address)").hex()[:8]


def _rpc() -> str:
    url = os.environ.get("ETHEREUM_RPC_URL")
    if not url:
        raise RuntimeError("ETHEREUM_RPC_URL not set")
    return url


def _overall(block: int):
    data = SEL + "0" * 24 + USDC[2:]
    try:
        r = requests.post(_rpc(), json={"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                          "params": [{"to": RESOLVER, "data": data}, hex(block)]},
                          timeout=25).json()
        res = r.get("result")
        if not res or res == "0x":
            return None
        raw = bytes.fromhex(res[2:])
        if len(raw) < 32 * 4:
            return None
        borrow = int.from_bytes(raw[0:32], "big") / 100.0
        supply = int.from_bytes(raw[32:64], "big") / 100.0
        fee = int.from_bytes(raw[64:96], "big") / 1e4
        util = int.from_bytes(raw[96:128], "big") / 1e4
        return supply, borrow, util, fee
    except Exception:
        return None


def main() -> int:
    panel = pd.read_parquet(PANEL, columns=["block_number", "block_timestamp"])
    panel["block_timestamp"] = pd.to_datetime(panel["block_timestamp"], utc=True)
    b0, b1 = int(panel.block_number.min()), int(panel.block_number.max())
    ts0 = panel.block_timestamp.min()
    blocks = list(range(b0, b1, BLOCKS_PER_DAY))
    print(f"sampling {len(blocks)} daily blocks; resolver {RESOLVER}", flush=True)

    rows, miss, ident_err = [], 0, []
    for i, blk in enumerate(blocks):
        o = _overall(blk)
        if o is None:
            miss += 1
            continue
        supply, borrow, util, fee = o
        ident = borrow * util * (1 - fee)  # expected supply
        ident_err.append(abs(ident - supply))
        ts = ts0 + pd.Timedelta(seconds=(blk - b0) * 12)
        rows.append({"timestamp": ts, "block_number": blk, "supply_apr": supply / 100.0,
                     "borrow_apr": borrow / 100.0, "utilization": util, "fee": fee})
        if i % 50 == 0:
            print(f"  [{i}/{len(blocks)}] blk {blk} supply={supply:.2f}% borrow={borrow:.2f}% "
                  f"util={util*100:.1f}% (identity exp={ident:.2f}%)", flush=True)
        time.sleep(0.03)

    df = pd.DataFrame(rows)
    df.to_parquet(OUT, index=False)
    print(f"\nwrote {OUT} ({len(df)} rows, {miss} misses)", flush=True)

    # (1) INTERNAL identity validation
    import numpy as np
    mae_id = float(np.mean(ident_err)) if ident_err else float("nan")
    print(f"VALIDATION 1 (internal: supply == borrow*util*(1-fee)): "
          f"MAE={mae_id:.4f} pp -> {'OK' if mae_id < 0.05 else 'WARN'}", flush=True)

    # (2) EXTERNAL vs DeFiLlama fluid_daily APY
    try:
        fd = pd.read_parquet(FLUID_DAILY)
        tcol = "timestamp" if "timestamp" in fd.columns else fd.columns[0]
        fd[tcol] = pd.to_datetime(fd[tcol], utc=True)
        fd = fd[[tcol, "apy"]].rename(columns={tcol: "timestamp", "apy": "ll_apy"}).sort_values("timestamp")
        m = pd.merge_asof(df.sort_values("timestamp"), fd, on="timestamp", direction="nearest")
        m = m.dropna(subset=["ll_apy"])
        # df supply_apr is fraction; ll_apy is percent
        mae_ext = (m["supply_apr"] * 100 - m["ll_apy"]).abs().mean()
        corr = (m["supply_apr"] * 100).corr(m["ll_apy"])
        print(f"VALIDATION 2 (external vs DeFiLlama): MAE={mae_ext:.2f}pp corr={corr:.3f} n={len(m)} "
              f"-> {'DECODE VALIDATED' if corr > 0.6 else 'check'}", flush=True)
    except Exception as e:
        print(f"external validation skipped: {e}", flush=True)

    print(f"borrow mean {df['borrow_apr'].mean()*100:.2f}%  util mean {df['utilization'].mean()*100:.1f}%",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
