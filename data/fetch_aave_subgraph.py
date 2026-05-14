"""Application-level fetcher: 18-month Aave V3 USDC hourly history.

Wraps the staged Extra+1 loader `extras/fractal_pr_compound_loader/
aave_v3_subgraph.py` with our project-specific defaults: USDC reserve on
Ethereum mainnet, window 2024-11-01 -> 2026-04-30, hourly resolution,
parquet cache under `data/cached/`.

Reads `THE_GRAPH_API_KEY` from `.env` via python-dotenv.

Run: python -m data.fetch_aave_subgraph [--force]
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

# Add staging dir to import path (will become a regular import once the
# Extra+1 PR is merged and `fractal-defi` is upgraded).
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "extras" / "fractal_pr_compound_loader"))

from aave_v3_subgraph import AaveV3ProtocolSubgraphRatesLoader, USDC_ETH  # noqa: E402
from fractal.loaders.base_loader import LoaderType  # noqa: E402


CACHE_DIR = ROOT / "data" / "cached"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

WINDOW_START = datetime(2024, 11, 1, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 4, 30, 23, 59, 59, tzinfo=timezone.utc)


def fetch_full_window(force: bool = False) -> pd.DataFrame:
    """Pull the full 18-month Aave V3 USDC hourly history.

    Returns a DataFrame indexed by UTC hourly `time` with columns:
        lending_rate, borrowing_rate, utilization, total_liquidity,
        total_variable_debt.
    """
    out_path = CACHE_DIR / "aave_v3_subgraph_usdc_eth_2024-11_to_2026-04.parquet"
    if out_path.exists() and not force:
        print(f"[cached] {out_path}")
        return pd.read_parquet(out_path)

    load_dotenv(ROOT / ".env")
    api_key = os.environ.get("THE_GRAPH_API_KEY")
    if not api_key:
        raise SystemExit(
            "THE_GRAPH_API_KEY not set. See docs/CREDENTIALS_SETUP.md for "
            "the 3-minute signup at https://thegraph.com/studio."
        )

    print(f"Pulling Aave V3 USDC: {WINDOW_START} -> {WINDOW_END}")
    loader = AaveV3ProtocolSubgraphRatesLoader(
        api_key=api_key,
        reserve=USDC_ETH,
        start_time=WINDOW_START,
        end_time=WINDOW_END,
        resolution=1,                  # hourly
        loader_type=LoaderType.CSV,    # what's actually supported on v1.3.2
    )

    hist = loader.read(with_run=True)
    print(f"  -> {len(hist)} rows  ({hist.index[0]} -> {hist.index[-1]})")

    # Save in parquet (preserves timezone + dtype better than CSV)
    hist.to_parquet(out_path)
    print(f"[saved] {out_path}  shape={hist.shape}")
    return hist


if __name__ == "__main__":
    df = fetch_full_window(force="--force" in sys.argv)
    print()
    print("Summary:")
    print(f"  rows               : {len(df)}")
    print(f"  rate column missing: {df.isna().sum().to_dict()}")
    print(f"  lending APR range  : "
          f"[{df['lending_rate'].min()*365*24*100:.2f}%, "
          f"{df['lending_rate'].max()*365*24*100:.2f}%]")
    print(f"  utilization range  : "
          f"[{df['utilization'].min():.3f}, {df['utilization'].max():.3f}]")
    print(f"  median TVL (USDC)  : "
          f"${df['total_liquidity'].median()/1e6:.1f}M (raw scale, NOT USDC-decimals-adjusted)")
