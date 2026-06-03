"""Fetch the Fluid fUSDC fToken supply APY from on-chain ERC4626
share-price growth — the user-facing Fluid USDC lending yield (G4 via the
fToken layer).

fUSDC (0x9Fb7b4477576Fe5B32be4C1843aFB1e55F251B33) is an ERC4626 vault;
convertToAssets(shares) gives the USDC value of `shares`. The share price
(price-per-share) grows as lending interest accrues, so the annualized
growth IS the realized supply APY (apyBase-equivalent). We sample daily
and compute a trailing-30-day annualized APY at each point.

ARCHITECTURE NOTE (academically important): the fToken layer is
SUPPLY-ONLY. Borrowing of Fluid USDC happens through Fluid *Vaults*
(separate collateral/debt markets), not the fToken, so there is no
fToken-level borrow rate or utilization. The (borrow, util) fields for
Fluid therefore have no clean Aave-style analog — this is an
architectural property, not a missing fetch.

VALIDATION: the fToken pps-APY is compared to DeFiLlama apyBase
(data/cached/fluid_daily.parquet) — both are the interest layer.

Needs archive ETHEREUM_RPC_URL.
Output: data/cached/f4_fluid_ftoken_daily.parquet
        (timestamp, block_number, pps, supply_apy_30d)
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
OUT = ROOT / "data" / "cached" / "f4_fluid_ftoken_daily.parquet"

FUSDC = "0x9Fb7b4477576Fe5B32be4C1843aFB1e55F251B33"
BLOCKS_PER_DAY = 7200
SEL = "0x" + keccak(text="convertToAssets(uint256)").hex()[:8]
ONE_SHARE = 10**6  # fUSDC has 6 decimals


def _rpc() -> str:
    url = os.environ.get("ETHEREUM_RPC_URL")
    if not url:
        raise RuntimeError("ETHEREUM_RPC_URL not set")
    return url


def _pps(block: int) -> float | None:
    data = SEL + f"{ONE_SHARE:064x}"
    try:
        r = requests.post(_rpc(), json={"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                          "params": [{"to": FUSDC, "data": data}, hex(block)]}, timeout=20).json()
        res = r.get("result")
        if not res or res == "0x":
            return None
        return int(res, 16) / ONE_SHARE  # assets per 1 share
    except Exception:
        return None


def main() -> int:
    panel = pd.read_parquet(PANEL, columns=["block_number", "block_timestamp", "fluid_lending_apr"])
    panel["block_timestamp"] = pd.to_datetime(panel["block_timestamp"], utc=True)
    b0, b1 = int(panel.block_number.min()), int(panel.block_number.max())
    ts0 = panel.block_timestamp.min()
    blocks = list(range(b0, b1, BLOCKS_PER_DAY))
    print(f"sampling {len(blocks)} daily blocks for fUSDC pricePerShare", flush=True)

    rows, miss = [], 0
    for i, blk in enumerate(blocks):
        pps = _pps(blk)
        if pps is None:
            miss += 1
            continue
        ts = ts0 + pd.Timedelta(seconds=(blk - b0) * 12)
        rows.append({"timestamp": ts, "block_number": blk, "pps": pps})
        if i % 80 == 0:
            print(f"  [{i}/{len(blocks)}] block {blk} pps={pps:.6f}", flush=True)
        time.sleep(0.03)

    df = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
    # trailing-30-day annualized APY from pps growth
    df["supply_apy_30d"] = (df["pps"] / df["pps"].shift(30)) ** (365 / 30) - 1
    df.to_parquet(OUT, index=False)
    print(f"\nwrote {OUT} ({len(df)} rows, {miss} misses)", flush=True)
    valid = df["supply_apy_30d"].dropna()
    print(f"fUSDC supply APY (pps, 30d-trailing): mean {valid.mean()*100:.2f}%  "
          f"range {valid.min()*100:.2f}-{valid.max()*100:.2f}%", flush=True)

    # VALIDATION vs DeFiLlama apyBase
    try:
        fd = pd.read_parquet(FLUID_DAILY)
        fd["timestamp"] = pd.to_datetime(fd["timestamp"], utc=True).astype("datetime64[ns, UTC]")
        df["timestamp"] = df["timestamp"].astype("datetime64[ns, UTC]")
        m = pd.merge_asof(df.dropna(subset=["supply_apy_30d"]).sort_values("timestamp"),
                          fd[["timestamp", "apyBase"]].sort_values("timestamp"),
                          on="timestamp", direction="nearest").dropna(subset=["apyBase"])
        corr = (m["supply_apy_30d"] * 100).corr(m["apyBase"])
        mae = (m["supply_apy_30d"] * 100 - m["apyBase"]).abs().mean()
        print(f"VALIDATION (fToken pps-APY vs DeFiLlama apyBase): corr={corr:.3f} MAE={mae:.2f}pp n={len(m)} "
              f"-> {'fToken supply VALIDATED' if corr > 0.5 else 'partial'}", flush=True)
    except Exception as e:
        print(f"validation skipped: {e}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
