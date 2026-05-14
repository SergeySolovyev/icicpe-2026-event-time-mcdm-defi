"""Fetch historical Compound V3 cUSDCv3 supply/borrow rates via eth_call.

Why this exists: Messari's subgraph indexes per-collateral markets, not
the base Comet market — so `marketHourlySnapshots` returns nothing for
the USDC base market. We work around by querying Comet's view functions
(`getUtilization`, `getSupplyRate`, `getBorrowRate`) directly at historical
block numbers.

ETHEREUM_RPC_URL must be an Alchemy / Infura / similar endpoint that
supports historical state queries (archive data). Alchemy free tier
typically supports last ~128 blocks for state but their growth+ tiers
include archive — adjust `--archive` flag accordingly.

Approach:
  1. Get current block + timestamp.
  2. For each target hourly timestamp T, compute approximate block via
     blk_T ≈ blk_now - (ts_now - T) / 12.05 (Ethereum avg block time).
  3. Batch JSON-RPC: 1000 calls/request × 3 calls/hour = ~330 hours/req.
  4. Decode results, resample to uniform hourly grid.

Selectors (verified via keccak256(text=sig)[:4]):
  getUtilization()                              0x7eb71131
  getSupplyRate(uint256 utilization)            0xd955759d
  getBorrowRate(uint256 utilization)            0x9fa83b5a

Run: python -m data.fetch_compound_via_rpc [--days 540] [--probe]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
CACHE_DIR = ROOT / "data" / "cached"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

COMET_USDC = "0xc3d688B66703497DAA19211EEdff47f25384cdc3"
SEL_GET_UTIL = "0x7eb71131"
SEL_SUPPLY_RATE = "0xd955759d"
SEL_BORROW_RATE = "0x9fa83b5a"

# Ethereum mainnet avg block time (sec). Adjust if your window crosses a
# major hard fork that changed this.
SECONDS_PER_BLOCK = 12.05
WAD = 10 ** 18
SECONDS_PER_YEAR = 31_536_000

WINDOW_START = datetime(2024, 11, 1, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 4, 30, 23, 59, 59, tzinfo=timezone.utc)


def _post(rpc: str, payload, timeout: int = 60) -> dict:
    """POST with retries on connection-reset (Windows urllib3 issue)."""
    for attempt in range(3):
        try:
            r = requests.post(rpc, json=payload, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except (requests.exceptions.ConnectionError,
                requests.exceptions.ReadTimeout) as e:
            if attempt == 2:
                raise
            print(f"  retry {attempt+1}/3 after {e}")
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def _encode_uint(val: int) -> str:
    return hex(val)[2:].zfill(64)


def _decode_uint(hex_str: str) -> int:
    return int(hex_str, 16) if hex_str and hex_str != "0x" else 0


def fetch_current_block(rpc: str) -> tuple[int, int]:
    """Returns (block_number, timestamp_seconds)."""
    bn_hex = _post(rpc, {"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber",
                          "params": []})["result"]
    bn = int(bn_hex, 16)
    blk = _post(rpc, {"jsonrpc": "2.0", "id": 1, "method": "eth_getBlockByNumber",
                       "params": [bn_hex, False]})["result"]
    ts = int(blk["timestamp"], 16)
    return bn, ts


def approximate_block(target_ts: int, now_block: int, now_ts: int) -> int:
    """Compute approximate block number at a target Unix timestamp."""
    return now_block - int((now_ts - target_ts) / SECONDS_PER_BLOCK)


def call_at_block(comet: str, selector: str, block: int, util_arg: int = None) -> dict:
    """Build a single eth_call request body for batched RPC."""
    data = selector
    if util_arg is not None:
        data += _encode_uint(util_arg)
    return {
        "to": comet,
        "data": data,
    }


def probe(rpc: str) -> dict:
    """Smoke test: confirm RPC works, get current Comet state."""
    now_bn, now_ts = fetch_current_block(rpc)
    print(f"Current block: {now_bn} @ {datetime.fromtimestamp(now_ts, timezone.utc)}")

    # Get current util + rate
    util_raw = _post(rpc, {
        "jsonrpc": "2.0", "id": 1, "method": "eth_call",
        "params": [{"to": COMET_USDC, "data": SEL_GET_UTIL}, "latest"],
    })["result"]
    util = _decode_uint(util_raw) / WAD

    supply_raw = _post(rpc, {
        "jsonrpc": "2.0", "id": 1, "method": "eth_call",
        "params": [{"to": COMET_USDC,
                    "data": SEL_SUPPLY_RATE + _encode_uint(_decode_uint(util_raw))},
                   "latest"],
    })["result"]
    supply_per_sec = _decode_uint(supply_raw) / WAD
    supply_apr = supply_per_sec * SECONDS_PER_YEAR

    print(f"Current cUSDCv3 utilization: {util:.4f}")
    print(f"Supply rate per-sec (1e18-scaled): {_decode_uint(supply_raw)}")
    print(f"Supply APR (simple): {supply_apr*100:.4f}%")
    print(f"Supply APY (continuous): {((1 + supply_per_sec)**SECONDS_PER_YEAR - 1)*100:.4f}%")
    return {"block": now_bn, "ts": now_ts, "utilization": util, "supply_apr": supply_apr}


def fetch_hourly_window(rpc: str, start: datetime, end: datetime,
                        batch_size: int = 100,
                        inter_batch_sleep: float = 0.4,
                        skip_existing: set | None = None) -> pd.DataFrame:
    """Fetch hourly utilization + supply/borrow rates over [start, end].

    Args:
        skip_existing: set of UTC datetime hour-rounded timestamps already
            fetched in a previous run. Targets in this set are skipped
            (lets idempotent append-mode fill only missing hours).

    Returns DataFrame with UTC hourly index, columns:
        lending_rate (per-hour decimal), borrowing_rate (per-hour),
        utilization, total_supplied_usd (placeholder 0), total_borrowed_usd (0)
    """
    now_bn, now_ts = fetch_current_block(rpc)
    print(f"Anchor: block {now_bn} @ {datetime.fromtimestamp(now_ts, timezone.utc)}")

    # Build target timestamps (hourly, inclusive both ends), filtering out
    # already-fetched hours when skip_existing is provided.
    n_hours_total = int((end - start).total_seconds() / 3600) + 1
    all_targets = [start + timedelta(hours=i) for i in range(n_hours_total)]
    if skip_existing:
        targets = [t for t in all_targets if t not in skip_existing]
        print(
            f"Window: {start} -> {end}  =  {n_hours_total} hourly targets total; "
            f"{n_hours_total - len(targets)} already have data ({len(targets)} to fetch)"
        )
    else:
        targets = all_targets
        print(f"Window: {start} -> {end}  =  {n_hours_total} hourly targets")
    n_hours = len(targets)
    if n_hours == 0:
        print("Nothing to fetch (all targets already covered).")
        return pd.DataFrame(columns=[
            "lending_rate", "borrowing_rate", "utilization",
            "total_supplied_usd", "total_borrowed_usd",
        ])

    rows = []
    # Phase 1: getUtilization at each target block (1 call per hour)
    # Phase 2: getSupplyRate + getBorrowRate at each target block (2 calls per hour)
    #
    # We'll batch all 3 calls per hour together. So batch_size targets per request.

    for batch_start in range(0, n_hours, batch_size):
        batch = targets[batch_start:batch_start + batch_size]
        payload = []
        rid = 0
        for t in batch:
            blk = approximate_block(int(t.timestamp()), now_bn, now_ts)
            blk_hex = hex(blk)
            # Slot 0..2 for util/supply/borrow
            rid += 1
            payload.append({
                "jsonrpc": "2.0", "id": rid, "method": "eth_call",
                "params": [{"to": COMET_USDC, "data": SEL_GET_UTIL}, blk_hex],
            })
        # Send batch
        try:
            resps = _post(rpc, payload, timeout=120)
            if not isinstance(resps, list):
                resps = [resps]
        except Exception as e:
            print(f"  batch failed: {e}; skipping hours {batch_start}..{batch_start+batch_size}")
            continue

        # Resolve utilization for this batch
        utils = {}
        for resp in resps:
            rid_back = resp.get("id")
            if rid_back is None or "result" not in resp:
                # Possible "execution reverted" — Comet not yet deployed at this
                # historical block, or archive node access denied.
                continue
            try:
                utils[rid_back] = _decode_uint(resp["result"])
            except Exception:
                pass

        # Phase 2: supply + borrow rate at each block with util argument
        payload2 = []
        rid = 0
        for t in batch:
            blk = approximate_block(int(t.timestamp()), now_bn, now_ts)
            blk_hex = hex(blk)
            rid += 1
            u = utils.get(rid)
            if u is None:
                continue
            payload2.extend([
                {"jsonrpc": "2.0", "id": rid * 10, "method": "eth_call",
                 "params": [{"to": COMET_USDC, "data": SEL_SUPPLY_RATE + _encode_uint(u)}, blk_hex]},
                {"jsonrpc": "2.0", "id": rid * 10 + 1, "method": "eth_call",
                 "params": [{"to": COMET_USDC, "data": SEL_BORROW_RATE + _encode_uint(u)}, blk_hex]},
            ])
        # publicnode has a per-request batch-size limit somewhere around
        # 100 calls (200-call batches return HTTP 400). Split phase2's
        # payload into sub-batches of `batch_size` calls each (=batch_size/2
        # hours per sub-batch).
        rate_map = {}
        SUB_MAX = batch_size           # match phase1's call count
        for sub_start in range(0, len(payload2), SUB_MAX):
            sub = payload2[sub_start:sub_start + SUB_MAX]
            try:
                sub_resps = _post(rpc, sub, timeout=180)
                if not isinstance(sub_resps, list):
                    sub_resps = [sub_resps]
            except Exception as e:
                print(f"  phase2 sub-batch failed: {e}")
                continue
            for resp in sub_resps:
                rid_back = resp.get("id")
                if rid_back is None or "result" not in resp:
                    continue
                try:
                    rate_map[rid_back] = _decode_uint(resp["result"])
                except Exception:
                    pass

        # Combine: per target, build row
        for slot, t in enumerate(batch):
            rid = slot + 1
            u = utils.get(rid)
            if u is None:
                continue
            sup = rate_map.get(rid * 10)
            bor = rate_map.get(rid * 10 + 1)
            if sup is None or bor is None:
                continue
            util_dec = u / WAD
            sup_per_sec = sup / WAD
            bor_per_sec = bor / WAD
            # Convert per-sec rate -> per-hour decimal (matches Aave gateway loader)
            # per_hour = per_sec * 3600
            sup_per_hour = sup_per_sec * 3600
            bor_per_hour = bor_per_sec * 3600
            rows.append({
                "date": t,
                "lending_rate": sup_per_hour,
                "borrowing_rate": bor_per_hour,
                "utilization": min(util_dec, 1.05),
                "total_supplied_usd": 0.0,    # not available via eth_call here
                "total_borrowed_usd": 0.0,
            })

        # Throttle: stay under Alchemy free-tier rate limits. Each batch is
        # ~2-3 calls/hour × batch_size = up to 300 calls; with 0.4s pause
        # we keep ~200 RPC calls/sec effective load.
        time.sleep(inter_batch_sleep)

        if (batch_start // batch_size) % 10 == 0:
            print(f"  progress: {batch_start + len(batch):>5}/{n_hours} hours processed, "
                  f"{len(rows)} rows so far")

    if not rows:
        raise SystemExit(
            "No data points returned. Likely cause: Alchemy free tier without "
            "archive access — historical eth_call only works for last ~128 blocks "
            "(~25 minutes). Upgrade to Growth tier or use Alchemy supernode/archive "
            "addon for full history."
        )

    df = pd.DataFrame(rows).set_index("date").sort_index()
    print(f"\nFinal: {len(df)} hours in DataFrame")
    print(f"  utilization range:  [{df['utilization'].min():.3f}, {df['utilization'].max():.3f}]")
    print(f"  lending APR range:  [{df['lending_rate'].min()*365*24*100:.2f}%, "
          f"{df['lending_rate'].max()*365*24*100:.2f}%]")
    return df


def main(force: bool = False, days: int = None,
         append: bool = False, rpc_override: str | None = None,
         batch_size: int = 100, sleep: float = 0.4) -> pd.DataFrame:
    """Fetch or top-up the Compound USDC hourly parquet.

    Modes (mutually exclusive):
      force=True:  delete existing parquet, fetch from scratch.
      append=True: load existing parquet, fetch ONLY hours not yet present,
                   merge results and re-save. Idempotent — repeat runs against
                   different RPC providers fill remaining gaps.
      (default):   if parquet exists and is non-empty, return it as-is.
    """
    out_path = CACHE_DIR / "compound_v3_usdc_eth_2024-11_to_2026-04.parquet"

    existing = pd.DataFrame()
    if out_path.exists():
        existing = pd.read_parquet(out_path)

    if not force and not append:
        if not existing.empty:
            print(f"[cached] {out_path}  ({len(existing)} rows)")
            return existing

    load_dotenv(ROOT / ".env")
    rpc = rpc_override or os.environ.get("ETHEREUM_RPC_URL")
    if not rpc:
        raise SystemExit("ETHEREUM_RPC_URL missing in .env (or pass --rpc)")
    print(f"Using RPC: {rpc[:30]}***{rpc[-6:] if len(rpc) > 36 else ''}")

    if days:
        end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        start = end - timedelta(days=days)
    else:
        start, end = WINDOW_START, WINDOW_END

    # Build skip-set from existing parquet for append mode
    skip_existing: set | None = None
    if append and not existing.empty:
        # Normalise existing index to hourly UTC for set membership tests
        idx = pd.to_datetime(existing.index, utc=True)
        skip_existing = set(idx.to_pydatetime().tolist())
        print(f"[append] Existing parquet has {len(skip_existing)} hours; "
              f"fetching only the gaps.")

    df_new = fetch_hourly_window(
        rpc, start, end,
        batch_size=batch_size, inter_batch_sleep=sleep,
        skip_existing=skip_existing,
    )

    if append and not existing.empty and not df_new.empty:
        # Merge: existing rows take precedence on duplicates (shouldn't happen
        # because we skipped, but defensive).
        combined = pd.concat([existing, df_new]).sort_index()
        combined = combined[~combined.index.duplicated(keep="first")]
        df_out = combined
        print(f"[merged] {len(existing)} existing + {len(df_new)} new = {len(df_out)} total")
    elif append and not existing.empty and df_new.empty:
        # Nothing new fetched (all targets already covered, or RPC silent).
        df_out = existing
        print(f"[append] No new rows; keeping existing {len(existing)}.")
    else:
        df_out = df_new

    df_out.to_parquet(out_path)
    print(f"[saved] {out_path}  ({len(df_out)} rows)")
    return df_out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="Delete existing parquet and refetch from scratch")
    ap.add_argument("--append", action="store_true",
                    help="Load existing parquet, fetch ONLY gaps, merge. "
                         "Idempotent across multiple runs / different RPC providers.")
    ap.add_argument("--days", type=int, default=None,
                    help="If set, fetch only last N days (smoke test)")
    ap.add_argument("--probe", action="store_true",
                    help="Just smoke-test the RPC connection")
    ap.add_argument("--rpc", default=None,
                    help="Override ETHEREUM_RPC_URL (e.g. "
                         "https://ethereum-rpc.publicnode.com for free archive)")
    ap.add_argument("--batch-size", type=int, default=100)
    ap.add_argument("--sleep", type=float, default=0.4,
                    help="Inter-batch sleep seconds")
    args = ap.parse_args()

    if args.probe:
        load_dotenv(ROOT / ".env")
        rpc = args.rpc or os.environ.get("ETHEREUM_RPC_URL")
        if not rpc:
            raise SystemExit("No RPC endpoint. Set ETHEREUM_RPC_URL in .env or pass --rpc")
        print(f"Using RPC: {rpc[:48]}{'...' if len(rpc) > 48 else ''}")
        probe(rpc)
    else:
        main(force=args.force, days=args.days, append=args.append,
             rpc_override=args.rpc, batch_size=args.batch_size, sleep=args.sleep)
