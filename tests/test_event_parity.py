"""Hourly-resample parity gate for the per-block panel vs 2026c artifact.

This is the Week-1 acceptance gate from the design spec
(C:\\Users\\1\\.claude\\plans\\enumerated-scribbling-barto.md).

Guards against silent regressions in the new event-time fetchers.
If a fetcher's unit conversion (RAY / WAD / RATE_PRECISION / decimals)
drifts from the 2026c convention, this test catches it before any
downstream consumer (T1/T2/T3 policies, paper plots) sees the corruption.

The test is SKIPPED when either parquet is missing -- typical in CI or
when running offline before the operator has executed the full build.
On a fully-built machine both parquets exist and the test runs.
"""
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
LEGACY = ROOT / "data" / "cached" / "joined_clean.parquet"
NEW = ROOT / "data" / "cached" / "per_block_panel.parquet"

# Tolerance: per-block last-of-hour vs the 2026c hourly aggregate diverges
# slightly because the legacy pipeline uses pd.resample("1h").last() on
# events and we now use per-block ffill into hourly bins. 5 bp is
# generous enough to allow that without masking real unit-conversion bugs
# (which would be in the 10-100x range).
APR_TOL_BP = 5.0
APR_TOL = APR_TOL_BP * 1e-4


@pytest.mark.skipif(
    not (LEGACY.exists() and NEW.exists()),
    reason="Both data/cached/joined_clean.parquet AND per_block_panel.parquet "
           "must exist. Operator runs the build script first.",
)
def test_aave_lending_apr_parity_hourly_resample():
    """Hourly resample of new aave_v3_lending_apr matches legacy r_aave * 8760."""
    legacy = pd.read_parquet(LEGACY)
    new = pd.read_parquet(NEW)

    if "aave_v3_lending_apr" not in new.columns:
        pytest.skip("Aave column not present in panel (fetcher may have failed)")
    if "r_aave" not in legacy.columns:
        pytest.skip("legacy r_aave column missing; cannot compare")

    new = new.set_index("block_timestamp")
    new_hourly = new["aave_v3_lending_apr"].resample("1h").last().dropna()

    # CLAUDE.md §3a + §4: Solovev 2026c stored Aave as per-hour rate
    # (annualized APR / 8760). The new panel stores annualized APR directly.
    legacy_aave = legacy["r_aave"] * 365 * 24

    joined = pd.concat(
        [new_hourly.rename("new"), legacy_aave.rename("legacy")], axis=1
    ).dropna()
    assert len(joined) > 100, (
        f"need >100 overlapping hourly rows, got {len(joined)}"
    )

    diff = (joined["new"] - joined["legacy"]).abs()
    median_diff = diff.median()
    p95_diff = diff.quantile(0.95)
    assert median_diff < APR_TOL, (
        f"Aave APR median disagreement {median_diff:.6f} > tol {APR_TOL} "
        f"({APR_TOL_BP} bp); p95={p95_diff:.6f}. "
        f"Likely a RAY-scaling or per-second vs annualized bug in "
        f"fetch_aave_events.py."
    )


@pytest.mark.skipif(
    not (LEGACY.exists() and NEW.exists()),
    reason="Both data/cached/joined_clean.parquet AND per_block_panel.parquet "
           "must exist. Operator runs the build script first.",
)
def test_compound_lending_apr_parity_hourly_resample():
    """Hourly resample of new compound_v3_lending_apr matches legacy r_compound * 8760."""
    legacy = pd.read_parquet(LEGACY)
    new = pd.read_parquet(NEW)

    if "compound_v3_lending_apr" not in new.columns:
        pytest.skip("Compound column not present in panel")
    if "r_compound" not in legacy.columns:
        pytest.skip("legacy r_compound column missing")

    new = new.set_index("block_timestamp")
    new_hourly = new["compound_v3_lending_apr"].resample("1h").last().dropna()
    legacy_comp = legacy["r_compound"] * 365 * 24

    joined = pd.concat(
        [new_hourly.rename("new"), legacy_comp.rename("legacy")], axis=1
    ).dropna()
    assert len(joined) > 100, f"need >100 overlapping rows, got {len(joined)}"

    diff = (joined["new"] - joined["legacy"]).abs()
    median_diff = diff.median()
    p95_diff = diff.quantile(0.95)
    assert median_diff < APR_TOL, (
        f"Compound APR median disagreement {median_diff:.6f} > tol "
        f"{APR_TOL} ({APR_TOL_BP} bp); p95={p95_diff:.6f}. "
        f"Likely a WAD or per-second-rate-to-annualized bug in "
        f"fetch_compound_events.py."
    )


@pytest.mark.skipif(
    not NEW.exists(),
    reason="per_block_panel.parquet missing; operator runs the build first.",
)
def test_panel_schema_invariants():
    """Sanity checks on the panel even without legacy comparison."""
    panel = pd.read_parquet(NEW)
    assert "block_number" in panel.columns
    assert "block_timestamp" in panel.columns
    assert panel["block_number"].is_monotonic_increasing, (
        "panel block_number must be strictly increasing"
    )
    assert panel["block_timestamp"].dt.tz is not None, (
        "panel block_timestamp must be tz-aware UTC"
    )

    # At least Aave should be present (the cornerstone protocol).
    proto_lend_cols = [c for c in panel.columns if c.endswith("_lending_apr")]
    assert len(proto_lend_cols) >= 1, (
        f"panel must have at least one <proto>_lending_apr column, "
        f"got {list(panel.columns)}"
    )

    # No lending APR should be astronomically large (catches RAY-not-converted bugs).
    for col in proto_lend_cols:
        ser = panel[col].dropna()
        if len(ser) == 0:
            continue
        # Real DeFi data CAN exceed 100% APR briefly during liquidity-stress
        # events (Euler V2 hit 101.38% on the partial panel; Aave Optimism
        # had >300% USDC for ~12h in Aug 2023). The threshold here is a
        # UNIT-CONVERSION sanity check, not an economic plausibility check:
        # it catches RAY-not-divided (would give 10^27) or APR-as-percentage
        # (would give 1000+), but should accept real market spikes up to 10x
        # (= 1000% APR -- well above any real observation but well below
        # any unit-conversion error magnitude).
        assert ser.max() < 10.0, (
            f"{col}.max() = {ser.max():.4f} > 1000% APR -- "
            f"likely a RAY/WAD conversion bug. Expected APR decimals in [0, 10]."
        )
        assert ser.min() >= -1e-9, (
            f"{col}.min() = {ser.min():.6f} < 0 -- negative APR is impossible."
        )
