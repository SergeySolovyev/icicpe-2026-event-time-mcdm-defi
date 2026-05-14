"""Application-level fetcher: 18-month Compound V3 cUSDCv3 hourly history.

Wraps the staged Extra+1 loader `extras/fractal_pr_compound_loader/
compound.py` with project-specific defaults: cUSDCv3 market, window
2024-11-01 -> 2026-04-30, hourly resolution.

Reads `THE_GRAPH_API_KEY` from `.env` via python-dotenv.

Run: python -m data.fetch_compound [--force]
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "extras" / "fractal_pr_compound_loader"))

from compound import CompoundV3RatesLoader, COMET_USDC_ETH  # noqa: E402
from fractal.loaders.base_loader import LoaderType  # noqa: E402


CACHE_DIR = ROOT / "data" / "cached"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

WINDOW_START = datetime(2024, 11, 1, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 4, 30, 23, 59, 59, tzinfo=timezone.utc)


def fetch_full_window(force: bool = False) -> pd.DataFrame:
    """Pull the full 18-month Compound V3 cUSDCv3 hourly history."""
    out_path = CACHE_DIR / "compound_v3_usdc_eth_2024-11_to_2026-04.parquet"
    if out_path.exists() and not force:
        print(f"[cached] {out_path}")
        return pd.read_parquet(out_path)

    load_dotenv(ROOT / ".env")
    api_key = os.environ.get("THE_GRAPH_API_KEY")
    if not api_key:
        raise SystemExit(
            "THE_GRAPH_API_KEY not set. See docs/CREDENTIALS_SETUP.md."
        )

    print(f"Pulling Compound V3 cUSDCv3: {WINDOW_START} -> {WINDOW_END}")
    loader = CompoundV3RatesLoader(
        api_key=api_key,
        market=COMET_USDC_ETH,
        start_time=WINDOW_START,
        end_time=WINDOW_END,
        resolution=1,                  # hourly
        loader_type=LoaderType.CSV,
    )

    hist = loader.read(with_run=True)
    if hist.empty:
        print(
            "WARN: Compound V3 Messari subgraph returned zero rows for the base\n"
            "      USDC market. Verified 2026-05-14: Messari indexes per-collateral\n"
            "      markets only (Market = Comet base + collateral pair), not the\n"
            "      base market. Historical supply rate is NOT directly queryable\n"
            "      via this subgraph. Three alternatives, in order of effort:\n"
            "        1. Dune Analytics: SQL on compound_v3_ethereum.Comet_evt_*\n"
            "           events (requires DUNE_API_KEY plus query writing).\n"
            "        2. eth_call at periodic blocks against Comet `getSupplyRate`\n"
            "           and `getBorrowRate` view functions (requires RPC).\n"
            "        3. Use a Compound V3 dedicated subgraph if one exists\n"
            "           outside Messari (search github.com/compound-finance/subgraphs).\n"
            "Skipping Compound for now; pipeline will run with Aave-only data\n"
            "and a static-current-rate fallback for Compound."
        )
        # Save an empty parquet to make downstream code's `.exists()` check pass.
        hist.to_parquet(out_path)
        return hist
    print(f"  -> {len(hist)} rows  ({hist.index[0]} -> {hist.index[-1]})")
    hist.to_parquet(out_path)
    print(f"[saved] {out_path}  shape={hist.shape}")
    return hist


if __name__ == "__main__":
    df = fetch_full_window(force="--force" in sys.argv)
    print()
    print("Summary:")
    print(f"  rows               : {len(df)}")
    print(f"  missing            : {df.isna().sum().to_dict()}")
    print(f"  lending APR range  : "
          f"[{df['lending_rate'].min()*365*24*100:.2f}%, "
          f"{df['lending_rate'].max()*365*24*100:.2f}%]")
    print(f"  utilization range  : "
          f"[{df['utilization'].min():.3f}, {df['utilization'].max():.3f}]")
    print(f"  median TVL USD     : ${df['total_supplied_usd'].median()/1e6:.1f}M")
