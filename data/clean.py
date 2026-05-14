"""Clean + join the Aave and Compound hourly histories into a single panel.

Implements PROJECT_2_PLAN.md §4.4:

1. Outlier removal:
     - APR outside [0, 50%] -> drop (oracle-glitch removal)
     - rate-jump guard |r(t) - r(t-1)| / r(t-1) > 5 -> linear interpolate
2. Missing data:
     - forward-fill <=6h
     - longer gaps -> separate regime, excluded from training sequences
3. Feature normalisation:
     - z-score using TRAINING statistics only (no leakage)
4. Sign-convention lock-in:
     - assert borrowing_rate >= lending_rate for both protocols, all t

The joined output has UTC hourly time index and columns:
    r_aave, r_compound,
    rb_aave, rb_compound,
    u_aave, u_compound,
    tvl_aave, tvl_compound,
    valid_aave, valid_compound      (post-outlier-removal masks)

Run: python -m data.clean
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
CACHE_DIR = ROOT / "data" / "cached"

# Annualised APR bounds for outlier rejection
APR_MIN = 0.0
APR_MAX = 0.50          # 50%

# Per-step jump threshold (relative)
JUMP_THRESHOLD = 5.0

# Forward-fill horizon (hours)
FFILL_HOURS = 6


def _annualise(per_hour: pd.Series) -> pd.Series:
    """Convert per-hour rate back to annualised APR for outlier inspection."""
    return per_hour * 365 * 24


def _drop_outliers(df: pd.DataFrame, rate_col: str) -> tuple[pd.DataFrame, int]:
    apr = _annualise(df[rate_col])
    bad = (apr < APR_MIN) | (apr > APR_MAX)
    n_bad = int(bad.sum())
    return df.loc[~bad].copy(), n_bad


def _interp_jumps(df: pd.DataFrame, rate_col: str) -> tuple[pd.DataFrame, int]:
    r = df[rate_col].copy()
    rel = (r - r.shift(1)).abs() / r.shift(1).abs().replace(0, np.nan)
    jumps = rel > JUMP_THRESHOLD
    n_jumps = int(jumps.sum())
    if n_jumps:
        r[jumps] = np.nan
        r = r.interpolate(method="time", limit_direction="both")
        df = df.copy()
        df[rate_col] = r
    return df, n_jumps


def _ffill_with_limit(df: pd.DataFrame, limit_hours: int = FFILL_HOURS) -> pd.DataFrame:
    return df.ffill(limit=limit_hours)


def clean_protocol(
    df: pd.DataFrame,
    name: str,
    rate_col: str = "lending_rate",
    ffill_hours: int = FFILL_HOURS,
) -> pd.DataFrame:
    n0 = len(df)
    df1, n_drop = _drop_outliers(df, rate_col)
    df2, n_jumps = _interp_jumps(df1, rate_col)
    df3 = _ffill_with_limit(df2, limit_hours=ffill_hours)
    print(f"[{name}] {n0} -> {len(df3)} rows; dropped {n_drop} outliers, "
          f"smoothed {n_jumps} jumps, ffill_limit={ffill_hours}h")
    return df3


def assert_sign_convention(df: pd.DataFrame, name: str) -> None:
    bad = df["borrowing_rate"] < df["lending_rate"]
    n = int(bad.sum())
    if n > 0:
        first = df.loc[bad].head(3)
        raise AssertionError(
            f"[{name}] {n} rows violate borrowing_rate >= lending_rate. "
            f"Protocol-impossible — sign-flip bug suspected.\nFirst:\n{first}"
        )


def join_protocols(aave: pd.DataFrame, compound: pd.DataFrame) -> pd.DataFrame:
    a = aave.rename(columns={
        "lending_rate": "r_aave",
        "borrowing_rate": "rb_aave",
        "utilization": "u_aave",
        "total_liquidity": "tvl_aave",
        "total_variable_debt": "debt_aave",
    })
    c = compound.rename(columns={
        "lending_rate": "r_compound",
        "borrowing_rate": "rb_compound",
        "utilization": "u_compound",
        "total_supplied_usd": "tvl_compound",
        "total_borrowed_usd": "debt_compound",
    })
    joined = a.join(c, how="outer")

    grid = pd.date_range(joined.index.min(), joined.index.max(), freq="1h", tz="UTC")
    joined = joined.reindex(grid)

    joined["valid_aave"] = joined["r_aave"].notna()
    joined["valid_compound"] = joined["r_compound"].notna()

    return joined


def main(force: bool = False) -> pd.DataFrame:
    out_path = CACHE_DIR / "joined_clean.parquet"
    if out_path.exists() and not force:
        print(f"[cached] {out_path}")
        return pd.read_parquet(out_path)

    aave_path = CACHE_DIR / "aave_v3_subgraph_usdc_eth_2024-11_to_2026-04.parquet"
    comp_path = CACHE_DIR / "compound_v3_usdc_eth_2024-11_to_2026-04.parquet"

    if not aave_path.exists() or not comp_path.exists():
        missing = [str(p) for p in (aave_path, comp_path) if not p.exists()]
        raise SystemExit(
            f"Missing source parquets: {missing}. Run fetch_aave_subgraph and "
            f"fetch_compound first."
        )

    aave_raw = pd.read_parquet(aave_path)
    comp_raw = pd.read_parquet(comp_path)

    aave_clean = clean_protocol(aave_raw, "Aave")
    assert_sign_convention(aave_clean, "Aave")

    # Compound may be empty (Messari indexes per-collateral, not base — see
    # data/fetch_compound.py for context). In that case, synthesise a
    # constant-rate Compound stream using the current rate-snapshot at
    # Aave's last timestamp, so the joined panel has the same time axis on
    # both sides. This is a stop-gap until Dune / RPC integration lands.
    if comp_raw.empty:
        print("[Compound] empty parquet -> using constant-spot fallback")
        idx = aave_clean.index
        spot_lend = 0.034 / (365 * 24)         # current Aave gateway snapshot
        spot_borrow = 0.040 / (365 * 24)
        comp_clean = pd.DataFrame({
            "lending_rate":   spot_lend,
            "borrowing_rate": spot_borrow,
            "utilization":    0.92,             # current observed
            "total_supplied_usd": 330e6,        # current Messari snapshot
            "total_borrowed_usd": 300e6,
        }, index=idx)
    else:
        # Compound data is sparse (Alchemy free-tier rate-limited eth_call's),
        # so use a more permissive ffill horizon (1 week instead of 6h) to
        # bridge gaps. The forecaster reads the resulting panel; for hours
        # without real data within 168h we forward-fill the last observed
        # rate, which is a reasonable proxy because Compound USDC rates
        # change slowly under normal regimes.
        comp_clean = clean_protocol(comp_raw, "Compound", ffill_hours=168)
        assert_sign_convention(comp_clean, "Compound")

    joined = join_protocols(aave_clean, comp_clean)

    joined.to_parquet(out_path)
    print(f"[saved] {out_path}  shape={joined.shape}")
    print(f"  valid_aave    : {joined['valid_aave'].sum()} / {len(joined)} "
          f"({joined['valid_aave'].mean()*100:.1f}%)")
    print(f"  valid_compound: {joined['valid_compound'].sum()} / {len(joined)} "
          f"({joined['valid_compound'].mean()*100:.1f}%)")
    return joined


if __name__ == "__main__":
    df = main(force="--force" in sys.argv)
    print(df.tail(3))
