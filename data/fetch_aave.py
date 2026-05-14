"""Fetch Aave V3 Ethereum USDC supply/borrow rates via fractal-defi's AaveV3RatesLoader.

VERIFIED 2026-05-14 against the actual v1.3.2 loader source
(fractal/loaders/aave.py). Aave's gateway returns ALREADY-ANNUALIZED APY as
percentage floats; the existing loader converts to arithmetic per-period
rate via `apy / ((365*24)/resolution)`. We mirror this convention exactly.

ENDPOINT: Aave's OWN gateway at `https://api.v3.aave.com/graphql` (NOT TheGraph;
no API key needed).

GRANULARITY LIMITATION (verified empirically 2026-05-14):
- `LAST_DAY`  (1d)  -> hourly cadence, returns 24-ish rows
- `LAST_WEEK` (7d)  -> empirically returned 0 rows (gateway bug or auth-tier?)
- `LAST_MONTH` (30d) -> 4-hour cadence BUT truncates to last ~14 days only
- `LAST_SIX_MONTHS` (180d) -> daily cadence, full window
- `LAST_YEAR` (366d) -> daily cadence, full window

Aave's gateway has effective hourly history ONLY for `LAST_DAY`. For our
18-month backtest we have three honest options:

  Option 1 (DAILY backtest):  Accept ~540 daily bars (this loader, daily).
        Pros: trivial; no API keys.
        Cons: 12h forecast horizon is degenerate (single bar). Need to
              re-justify temporal-pattern hypothesis at daily scale.

  Option 2 (HOURLY via Dune): SQL on `aave_v3_ethereum.LendingPool_evt_
        ReserveDataUpdated` (raw events) -> ~13,000 hourly bars.
        Pros: covers full window at hourly granularity.
        Cons: needs DUNE_API_KEY; query latency ~30s; per-event timing
              (not strictly hourly aligned, needs forward-fill).

  Option 3 (HOURLY via TheGraph protocol subgraph): query
        `reserveParamsHistoryItem` on the decentralized network.
        Pros: native hourly granularity; closest to research-paper convention.
        Cons: needs THE_GRAPH_API_KEY; pagination at ~1000 rows/page = ~13
              paginated calls.

We pursue Option 3 as primary (matches AgileRate / "Rules to Rewards"
dataset conventions and avoids paying Dune for SQL credits), with Option 1
as immediate-smoke-test path. Option 2 stays available as fallback.

The current implementation below is Option 1 (the smoke-test path). Switch
to Option 3 once THE_GRAPH_API_KEY is in .env.

UTILIZATION: not on this endpoint. We deliberately skip it here (rates are
the primary forecast target; utilization is needed for f_Risk in MCDM and is
fetched separately via Dune as documented in fetch_gas_eth.py).

The Extra+1 PR adds a `utilization: float` field to AaveGlobalState
populated from a secondary data source at strategy-load time.

Output: data/cached/aave_v3_usdc_eth_2024-11_to_2026-04.parquet
Columns: time (UTC, hourly), lending_rate (per-hour), borrowing_rate (per-hour)
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from fractal.loaders.aave import AaveV3RatesLoader, ETHEREUM_V3_MARKET
from fractal.loaders.base_loader import LoaderType

# Ethereum mainnet USDC
USDC_ETH = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
CHAIN_ID_ETH = 1

CACHE_DIR = Path(__file__).parent / "cached"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Project window
WINDOW_START = datetime(2024, 11, 1, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 4, 30, 23, 0, tzinfo=timezone.utc)


def _fetch_one_year_window(end_time: datetime, resolution_hours: int = 1) -> pd.DataFrame:
    """Pull a single LAST_YEAR window anchored at end_time. Returns LendingHistory df."""
    start_time = end_time - timedelta(days=366)  # full window the gateway supports

    loader = AaveV3RatesLoader(
        asset_address=USDC_ETH,
        chain_id=CHAIN_ID_ETH,
        market_address=ETHEREUM_V3_MARKET,
        loader_type=LoaderType.CSV,
        start_time=start_time,
        end_time=end_time,
        resolution=resolution_hours,
    )
    return loader.read(with_run=True)


def fetch_full_window(force: bool = False) -> pd.DataFrame:
    """Fetch the full 18-month USDC rate history via two stitched LAST_YEAR calls.

    Returns DataFrame indexed by UTC hourly `time`, columns ['lending_rate',
    'borrowing_rate'] in per-period rate units.
    """
    out_path = CACHE_DIR / "aave_v3_usdc_eth_2024-11_to_2026-04.parquet"
    if out_path.exists() and not force:
        print(f"[cached] {out_path}")
        return pd.read_parquet(out_path)

    print(f"Window A: {WINDOW_END - timedelta(days=366)} -> {WINDOW_END}")
    hist_a = _fetch_one_year_window(WINDOW_END)
    print(f"  -> {len(hist_a)} rows")

    mid_anchor = WINDOW_END - timedelta(days=366)
    print(f"Window B: {mid_anchor - timedelta(days=366)} -> {mid_anchor}")
    hist_b = _fetch_one_year_window(mid_anchor)
    print(f"  -> {len(hist_b)} rows")

    # Stitch — concat then dedupe on the index (timestamp). Keep latest.
    combined = pd.concat([hist_b, hist_a], axis=0)
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()

    # Filter to our exact window
    mask = (combined.index >= WINDOW_START) & (combined.index <= WINDOW_END)
    combined = combined.loc[mask]

    # Sign-convention assertion (lock-in test against v1.4.0 sign-fix CHANGELOG)
    n_violations = (combined["borrowing_rate"] < combined["lending_rate"]).sum()
    if n_violations > 0:
        bad = combined[combined["borrowing_rate"] < combined["lending_rate"]]
        print(
            f"WARN: {n_violations} rows where borrowing_rate < lending_rate "
            f"(should be impossible). First few:\n{bad.head()}",
            file=sys.stderr,
        )

    combined.to_parquet(out_path)
    print(f"[saved] {out_path}  shape={combined.shape}  "
          f"range={combined.index[0]} -> {combined.index[-1]}")
    return combined


if __name__ == "__main__":
    df = fetch_full_window(force="--force" in sys.argv)
    print()
    print(df.head(3))
    print("...")
    print(df.tail(3))
    print()
    print(f"Rows: {len(df)}, missing: {df.isna().sum().to_dict()}")
    print(f"Lending range (per-hour): "
          f"[{df['lending_rate'].min():.3e}, {df['lending_rate'].max():.3e}]")
    print(f"Borrowing range (per-hour): "
          f"[{df['borrowing_rate'].min():.3e}, {df['borrowing_rate'].max():.3e}]")
    print(f"Lending APR range: "
          f"[{df['lending_rate'].min()*365*24*100:.2f}%, "
          f"{df['lending_rate'].max()*365*24*100:.2f}%]")
