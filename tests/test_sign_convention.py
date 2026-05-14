"""Lock-in test: borrowing_rate(t) >= lending_rate(t) for all t, both protocols.

Defends against the fractal-defi pre-v1.4.0 Aave loader sign-flip bug
(documented in CHANGELOG.md). Since we pin v1.3.2 (see README ERRATA),
this test reads the real loader output and asserts the protocol-physical
constraint directly. If a future fractal-defi release re-introduces the
bug or the subgraph schema flips, our backtest crashes here BEFORE any
P&L numbers get computed wrong.

Two layers of defence:
1. test_loader_smoke_short_window: pull last 2 days from Aave's gateway
   (no API key needed), assert no row violates the convention.
2. test_cached_full_window_sign: if data/cached/joined_clean.parquet
   exists from a prior real-data fetch, scan it. Skipped otherwise.

Run: pytest tests/test_sign_convention.py -v
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest


CACHE_DIR = Path(__file__).parent.parent / "data" / "cached"


@pytest.mark.network
def test_aave_loader_smoke_short_window():
    """Pull last 2 days from Aave's gateway (no API key); assert sign convention.

    Marked `network` — skip when offline by running `pytest -m 'not network'`.
    """
    from fractal.loaders.aave import AaveV3RatesLoader, ETHEREUM_V3_MARKET
    from fractal.loaders.base_loader import LoaderType

    USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=2)

    loader = AaveV3RatesLoader(
        asset_address=USDC, chain_id=1, market_address=ETHEREUM_V3_MARKET,
        loader_type=LoaderType.CSV,
        start_time=start, end_time=end, resolution=1,
    )
    hist = loader.read(with_run=True)
    assert len(hist) > 0, "Aave gateway returned no rows for last 2 days"

    bad = hist["borrowing_rate"] < hist["lending_rate"]
    n_bad = int(bad.sum())
    assert n_bad == 0, (
        f"Aave loader returned {n_bad} rows where borrowing_rate < lending_rate "
        f"(protocol-impossible). Sign-flip bug suspected. "
        f"Pinned fractal-defi version: {_fractal_version()}"
    )


def test_cached_aave_subgraph_sign_if_exists():
    """If the 18-month Aave subgraph parquet exists, scan every row."""
    path = CACHE_DIR / "aave_v3_subgraph_usdc_eth_2024-11_to_2026-04.parquet"
    if not path.exists():
        pytest.skip(f"{path} not yet built (run fetch_aave_subgraph first)")
    df = pd.read_parquet(path)
    bad = df["borrowing_rate"] < df["lending_rate"]
    assert int(bad.sum()) == 0, f"{bad.sum()} sign-violating rows in {path.name}"


def test_cached_compound_sign_if_exists():
    """If the Compound parquet exists, scan every row."""
    path = CACHE_DIR / "compound_v3_usdc_eth_2024-11_to_2026-04.parquet"
    if not path.exists():
        pytest.skip(f"{path} not yet built (run fetch_compound first)")
    df = pd.read_parquet(path)
    bad = df["borrowing_rate"] < df["lending_rate"]
    assert int(bad.sum()) == 0, f"{bad.sum()} sign-violating rows in {path.name}"


def test_cached_joined_sign_if_exists():
    """If the joined-clean parquet exists, both protocol legs respect sign."""
    path = CACHE_DIR / "joined_clean.parquet"
    if not path.exists():
        pytest.skip(f"{path} not yet built (run data.clean first)")
    df = pd.read_parquet(path)
    for proto, r_col, rb_col in [("AAVE", "r_aave", "rb_aave"),
                                  ("COMPOUND", "r_compound", "rb_compound")]:
        valid = df[r_col].notna() & df[rb_col].notna()
        bad = (df.loc[valid, rb_col] < df.loc[valid, r_col]).sum()
        assert bad == 0, f"{proto}: {bad} rows where borrowing < lending"


def _fractal_version() -> str:
    try:
        import fractal
        return getattr(fractal, "__version__", "unknown")
    except Exception:
        return "import-failed"
