"""Extend per_block_panel.parquet from 3 protocols to 6.

Adds {compound_v3, spark, fluid}_{lending_apr, borrow_apr, utilization,
tvl_usd} columns by joining the three coarser-cadence rate series onto
the per-block grid via merge_asof (forward-fill within stale-block
tolerance).

Source cadences:
* compound_v3: 1h RPC parquet (data/cached/compound_v3_usdc_eth_*.parquet)
* spark      : 1-3h Sky/Spark Messari subgraph (data/cached/spark_hourly.parquet)
* fluid      : 1d DeFiLlama Yield Pools (data/cached/fluid_daily.parquet)

The active T1/T2/T3 policies can now treat all 6 protocols as
switchable destinations on the per-block grid.  Stale-block tolerance:
2h for hourly sources, 36h for daily Fluid (chosen so that
walk-forward windows always have at least 99% non-null coverage).

Run once whenever the source parquets change; output overwrites
data/cached/per_block_panel.parquet."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data/cached"
PANEL_PATH = CACHE / "per_block_panel.parquet"


def _load_compound() -> pd.DataFrame:
    df = pd.read_parquet(CACHE / "compound_v3_usdc_eth_2024-11_to_2026-04.parquet")
    df = df.reset_index().rename(columns={"date": "timestamp"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    # CRITICAL UNIT CONVENTION: the existing aave/morpho/euler columns
    # store APR as a FRACTION (0.045 = 4.5%), NOT a percent. New
    # columns must match. lending_rate is per-hour fraction → annualize
    # without ×100.
    df["compound_v3_lending_apr"] = df["lending_rate"] * (365 * 24)
    df["compound_v3_borrow_apr"] = df["borrowing_rate"] * (365 * 24)
    df["compound_v3_utilization"] = df["utilization"]
    df["compound_v3_tvl_usd"] = df["total_supplied_usd"]
    return df[["timestamp", "compound_v3_lending_apr", "compound_v3_borrow_apr",
               "compound_v3_utilization", "compound_v3_tvl_usd"]].sort_values("timestamp")


def _load_spark() -> pd.DataFrame:
    df = pd.read_parquet(CACHE / "spark_hourly.parquet")
    df["timestamp"] = pd.to_datetime(df["datetime"], utc=True)
    # lending_apr from Sky Messari subgraph is in PERCENT — divide by 100
    # to match the existing fractional-APR panel convention.
    df["spark_lending_apr"] = df["lending_apr"] / 100.0
    df["spark_borrow_apr"] = np.nan
    df["spark_utilization"] = df["utilization"]
    df["spark_tvl_usd"] = df["tvl_usd"]
    return df[["timestamp", "spark_lending_apr", "spark_borrow_apr",
               "spark_utilization", "spark_tvl_usd"]].sort_values("timestamp")


def _load_dsr() -> pd.DataFrame:
    """F1 lead-rate signal: Maker DSR proxy via sDAI daily APY."""
    df = pd.read_parquet(CACHE / "dsr_sdai_daily.parquet")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["f1_dsr_apy_pct"] = df["apyBase"]
    # Normalize to fraction (panel convention).
    df["f1_dsr_apr_frac"] = df["apyBase"] / 100.0
    return df[["timestamp", "f1_dsr_apr_frac", "f1_dsr_apy_pct"]].sort_values("timestamp")


def _load_eth_usd() -> pd.DataFrame:
    df = pd.read_parquet(CACHE / "f4_eth_usd_daily.parquet")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df[["timestamp", "eth_usd"]].sort_values("timestamp")


def _load_usdc_usd() -> pd.DataFrame:
    df = pd.read_parquet(CACHE / "f4_usdc_usd_daily.parquet")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    # Two F4 features: raw USDC price + signed peg deviation in bp.
    return df[["timestamp", "usdc_usd", "usdc_peg_dev_bp"]].sort_values("timestamp")


def _load_fluid() -> pd.DataFrame:
    df = pd.read_parquet(CACHE / "fluid_daily.parquet")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    # DeFiLlama apyBase / apy are PERCENT — divide by 100 to match
    # the fractional-APR panel convention.
    df["fluid_lending_apr"] = df["apyBase"].fillna(df["apy"]) / 100.0
    df["fluid_borrow_apr"] = np.nan
    # DeFiLlama doesn't expose utilization on this endpoint; approximate
    # via tvlUsd-relative shape (placeholder 0.85 — the long-run mean of
    # Fluid utilization observed empirically). Used only for slippage
    # sanity checks; not consumed by T1/T2/T3 decision functions.
    df["fluid_utilization"] = 0.85
    df["fluid_tvl_usd"] = df["tvlUsd"]
    return df[["timestamp", "fluid_lending_apr", "fluid_borrow_apr",
               "fluid_utilization", "fluid_tvl_usd"]].sort_values("timestamp")


def _join(panel: pd.DataFrame, side: pd.DataFrame, *, tolerance: pd.Timedelta) -> pd.DataFrame:
    # merge_asof requires matching datetime dtypes; panel uses ms-precision
    # while subgraph/RPC sources arrive as ns. Coerce side to match panel.
    side = side.copy()
    side["timestamp"] = pd.to_datetime(side["timestamp"], utc=True).astype("datetime64[ms, UTC]")
    panel = panel.copy()
    panel["block_timestamp"] = pd.to_datetime(panel["block_timestamp"], utc=True).astype("datetime64[ms, UTC]")
    out = pd.merge_asof(
        panel.sort_values("block_timestamp"),
        side,
        left_on="block_timestamp",
        right_on="timestamp",
        direction="backward",
        tolerance=tolerance,
    )
    out = out.drop(columns=["timestamp"])
    return out


def main() -> int:
    print(f"loading panel: {PANEL_PATH}")
    panel = pd.read_parquet(PANEL_PATH)
    panel["block_timestamp"] = pd.to_datetime(panel["block_timestamp"], utc=True)
    panel = panel.sort_values("block_timestamp").reset_index(drop=True)
    print(f"panel rows: {len(panel):,}")

    print("loading compound_v3 hourly RPC parquet...")
    cmp_df = _load_compound()
    print(f"  {len(cmp_df):,} hourly rows, range {cmp_df.timestamp.min()} -> {cmp_df.timestamp.max()}")

    print("loading spark Sky Messari hourly snapshots...")
    spk_df = _load_spark()
    print(f"  {len(spk_df):,} hourly rows, range {spk_df.timestamp.min()} -> {spk_df.timestamp.max()}")

    print("loading fluid DeFiLlama daily APY...")
    flu_df = _load_fluid()
    print(f"  {len(flu_df):,} daily rows, range {flu_df.timestamp.min()} -> {flu_df.timestamp.max()}")

    print("loading F1 Maker DSR (via sDAI)...")
    dsr_df = _load_dsr()
    print(f"  dsr {len(dsr_df):,} rows, APY range "
          f"[{dsr_df.f1_dsr_apy_pct.min():.2f}, {dsr_df.f1_dsr_apy_pct.max():.2f}] %")

    print("loading F4 ETH/USD + USDC peg...")
    eth_df = _load_eth_usd()
    usdc_df = _load_usdc_usd()
    print(f"  eth_usd {len(eth_df):,} rows, range "
          f"[{eth_df.eth_usd.min():.0f}, {eth_df.eth_usd.max():.0f}] USD")
    print(f"  usdc peg deviation range "
          f"[{usdc_df.usdc_peg_dev_bp.min():+.1f}, {usdc_df.usdc_peg_dev_bp.max():+.1f}] bp")

    print("forward-filling each onto per-block grid via merge_asof...")
    # Compound: dense hourly RPC, 2h tolerance OK.
    # Spark: Sky Messari emits on state-change only, so hourly snapshots are
    # sparse (mean gap ~2.5h, p99 ~24h); 24h tolerance recovers 99%+.
    # Fluid + F4 daily series: 36h tolerance.
    panel = _join(panel, cmp_df, tolerance=pd.Timedelta("2h"))
    panel = _join(panel, spk_df, tolerance=pd.Timedelta("24h"))
    panel = _join(panel, flu_df, tolerance=pd.Timedelta("36h"))
    panel = _join(panel, eth_df, tolerance=pd.Timedelta("36h"))
    panel = _join(panel, usdc_df, tolerance=pd.Timedelta("36h"))
    panel = _join(panel, dsr_df, tolerance=pd.Timedelta("36h"))

    new_cols = [c for c in panel.columns if c.startswith(("compound_v3_", "spark_", "fluid_"))]
    cov = {c: (panel[c].notna().mean() * 100) for c in new_cols}
    print("\nNew column non-null coverage:")
    for c, v in cov.items():
        print(f"  {c:32s} {v:6.2f}%")

    out_path = PANEL_PATH
    panel.to_parquet(out_path, index=False)
    print(f"\nwrote {len(panel):,} rows × {len(panel.columns)} cols to {out_path}")
    print("active T1/T2/T3 policies can now treat 6 protocols as switchable destinations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
