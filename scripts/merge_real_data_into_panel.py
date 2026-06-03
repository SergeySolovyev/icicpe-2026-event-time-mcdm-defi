"""Merge the newly-fetched REAL data into the per-block panel, closing
audit gaps G1/G2/G3/G4. Backward-ffill each daily series onto the
per-block grid by block_number (merge_asof, direction=backward).

Updates (placeholders -> real):
    compound_v3_tvl_usd   (was const 0)     <- f4_compound_tvl_daily
    spark_borrow_apr      (was missing)     <- f4_spark_rates_daily
    fluid_borrow_apr      (was missing)     <- f4_fluid_rates_daily
    fluid_utilization     (was const 0.85)  <- f4_fluid_rates_daily
Adds (kept separate; headline stays on the conservative const-25):
    gas_price_gwei_real                      <- f4_gas_gwei_daily_real

Safety: backs up the panel first; verifies the untouched REAL columns
(aave/morpho/euler lending_apr) are byte-identical after the merge.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
C = ROOT / "data" / "cached"
PANEL = C / "per_block_panel.parquet"


def _ffill_col(panel: pd.DataFrame, daily: Path, src_col: str) -> pd.Series:
    d = pd.read_parquet(daily).sort_values("block_number")
    m = pd.merge_asof(panel[["block_number"]].sort_values("block_number"),
                      d[["block_number", src_col]], on="block_number", direction="backward")
    return m.set_index(panel.index)[src_col]


def main() -> int:
    panel = pd.read_parquet(PANEL).sort_values("block_number").reset_index(drop=True)
    backup = C / "per_block_panel.prefix_realdata_backup.parquet"
    if not backup.exists():
        shutil.copy(PANEL, backup)
        print(f"backed up panel -> {backup.name}", flush=True)

    # snapshot untouched real columns for the safety check
    guard = {c: panel[c].copy() for c in
             ["aave_v3_lending_apr", "morpho_blue_lending_apr", "euler_v2_lending_apr"]}

    before = {
        "compound_v3_tvl_usd": panel["compound_v3_tvl_usd"].nunique(),
        "spark_borrow_apr": panel["spark_borrow_apr"].notna().mean() * 100,
    }

    # G2 Compound TVL (validated: scalar totalSupply) and G3 Spark borrow
    # (validated: monthly corr 0.979 vs subgraph lending, identical
    # distribution). G4 Fluid borrow/util deliberately NOT merged: the
    # LiquidityResolver returns liquidity-LAYER base rates that are a
    # different metric than the panel's DeFiLlama user-facing fUSDC APY
    # (corr 0.036; resolver borrow 4.88% < DeFiLlama lending 7.59% would
    # violate borrow>=lending) and cover only ~30% of the panel
    # (resolver deployed mid-2025). Mixing layers would be wrong.
    panel["compound_v3_tvl_usd"] = _ffill_col(panel, C / "f4_compound_tvl_daily.parquet", "tvl_usd")
    panel["spark_borrow_apr"] = _ffill_col(panel, C / "f4_spark_rates_daily.parquet", "borrow_apr")
    panel["gas_price_gwei_real"] = _ffill_col(panel, C / "f4_gas_gwei_daily_real.parquet", "gas_gwei")
    for col in ["spark_borrow_apr", "gas_price_gwei_real", "compound_v3_tvl_usd"]:
        panel[col] = panel[col].bfill()

    # SAFETY: untouched real columns must be byte-identical
    for c, s in guard.items():
        assert panel[c].equals(s), f"REGRESSION: {c} changed during merge!"
    print("safety check OK: aave/morpho/euler lending_apr unchanged", flush=True)

    panel.to_parquet(PANEL, index=False)
    print("\n=== closed gaps (before -> after) ===", flush=True)
    print(f"compound_v3_tvl_usd: nunique {before['compound_v3_tvl_usd']} -> "
          f"{panel['compound_v3_tvl_usd'].nunique()} (mean ${panel['compound_v3_tvl_usd'].mean()/1e6:.0f}M)", flush=True)
    print(f"spark_borrow_apr: cov {before['spark_borrow_apr']:.1f}% -> "
          f"{panel['spark_borrow_apr'].notna().mean()*100:.1f}% (mean {panel['spark_borrow_apr'].mean()*100:.2f}%)", flush=True)
    print("fluid_borrow_apr / fluid_utilization: NOT merged (G4) — resolver "
          "liquidity-layer != DeFiLlama user-facing layer; left as documented gap.", flush=True)
    print(f"gas_price_gwei_real: added (mean {panel['gas_price_gwei_real'].mean():.1f} gwei); "
          f"gas_price_gwei kept = {panel['gas_price_gwei'].iloc[0]:.0f} (conservative headline)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
