"""Build fractal-defi Observations from the joined-clean panel.

Loads ``data/cached/joined_clean.parquet`` (produced by ``data.clean``) and
converts each hourly row into an :class:`fractal.core.base.Observation` with
``states = {"AAVE": ..., "COMPOUND": ...}``. Each state is a
:class:`SimpleLendingGlobalState` subclass that also carries the auxiliary
fields (``utilization``, ``gas_gwei``, ``delta_tvl_24h``) that the project's
strategies read via ``getattr`` in ``compute_criteria_vector``.

Loader contract (per ``extras/fractal_pr_lending_allocation/base_lending_allocation.py``):

    ``collateral_price = 1.0`` MUST be set on every GlobalState for
    USDC-denominated stable lending; otherwise
    ``entity.balance = collateral * 0 = 0`` and transfers silently zero out.

Train/Val/Test split per PROJECT_2_PLAN.md S4.1:

    Train:      2024-11-01 -> 2025-08-31
    Validation: 2025-09-01 -> 2025-12-31
    Test:       2026-01-01 -> 2026-04-30

Comparison is strict ``ts >= start AND ts <= end`` UTC.

Run::

    python -m backtest.observations_builder            # uses joined_clean.parquet
    python -m backtest.observations_builder --synthetic  # builds + uses synthetic data
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from fractal.core.base import Observation
from fractal.core.entities import SimpleLendingGlobalState


ROOT = Path(__file__).parent.parent
JOINED_PATH = ROOT / "data" / "cached" / "joined_clean.parquet"

# Plan S4.1 split boundaries (UTC)
TRAIN_START = datetime(2024, 11, 1, tzinfo=timezone.utc)
TRAIN_END = datetime(2025, 8, 31, 23, 59, 59, tzinfo=timezone.utc)
VAL_START = datetime(2025, 9, 1, tzinfo=timezone.utc)
VAL_END = datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
TEST_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
TEST_END = datetime(2026, 4, 30, 23, 59, 59, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Extended state with auxiliary fields the MCDM scorer reads via getattr.
# ---------------------------------------------------------------------------

@dataclass
class LendingGlobalStateExt(SimpleLendingGlobalState):
    """``SimpleLendingGlobalState`` + (utilization, gas_gwei, delta_tvl_24h).

    Subclassing is the cleanest way to expose extra fields while still
    satisfying ``isinstance(s, SimpleLendingGlobalState)`` checks in the
    fractal-defi pipeline.
    """
    utilization: float = 0.0
    gas_gwei: float = 30.0
    delta_tvl_24h: float = 0.0


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_joined_clean(path: Optional[Path] = None) -> pd.DataFrame:
    """Load the joined-clean parquet.

    Raises ``SystemExit`` with the exact rebuild command if not found.
    """
    p = path or JOINED_PATH
    if not p.exists():
        raise SystemExit(
            f"Missing {p}. Build with:\n"
            f"    python -m data.fetch_aave_subgraph\n"
            f"    python -m data.fetch_compound\n"
            f"    python -m data.fetch_gas_eth\n"
            f"    python -m data.clean\n"
            f"Or pass --synthetic to use generated data."
        )
    df = pd.read_parquet(p)
    # Ensure tz-aware UTC index.
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    return df


# ---------------------------------------------------------------------------
# Synthetic-data fallback (for smoke testing without API keys).
# ---------------------------------------------------------------------------

def make_synthetic_joined(out_path: Optional[Path] = None, seed: int = 0) -> pd.DataFrame:
    """Build a synthetic joined_clean panel spanning the full 18-month window.

    Covers Nov-2024 through Apr-2026 inclusive at 1h frequency. Columns
    match those produced by ``data.clean.join_protocols``.
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-11-01", "2026-04-30 23:00:00", freq="1h", tz="UTC")
    n = len(idx)

    def walk(start: float, lo: float, hi: float, step: float) -> np.ndarray:
        x = np.empty(n)
        x[0] = start
        for i in range(1, n):
            x[i] = np.clip(x[i - 1] + rng.normal(0.0, step), lo, hi)
        return x

    # Annualised APRs, per-hour scale.
    r_aave_apr = walk(0.045, 0.005, 0.18, 0.0008)
    r_comp_apr = walk(0.050, 0.005, 0.18, 0.0008)
    rb_aave_apr = r_aave_apr + np.clip(walk(0.02, 0.005, 0.06, 0.0005), 0.001, None)
    rb_comp_apr = r_comp_apr + np.clip(walk(0.02, 0.005, 0.06, 0.0005), 0.001, None)

    # Per-hour rates (continuous-compound annual -> per-step approximation).
    PER_HOUR = 1.0 / (365.0 * 24.0)

    u_aave = np.clip(walk(0.65, 0.10, 0.97, 0.005), 0.10, 0.97)
    u_comp = np.clip(walk(0.55, 0.10, 0.97, 0.005), 0.10, 0.97)

    tvl_aave = np.abs(1e9 + np.cumsum(rng.normal(0, 5e5, n)))
    tvl_comp = np.abs(4e8 + np.cumsum(rng.normal(0, 2e5, n)))

    df = pd.DataFrame({
        "r_aave": r_aave_apr * PER_HOUR,
        "r_compound": r_comp_apr * PER_HOUR,
        "rb_aave": rb_aave_apr * PER_HOUR,
        "rb_compound": rb_comp_apr * PER_HOUR,
        "u_aave": u_aave,
        "u_compound": u_comp,
        "tvl_aave": tvl_aave,
        "tvl_compound": tvl_comp,
        "valid_aave": True,
        "valid_compound": True,
    }, index=idx)

    # Optional aux columns (gas + 24h TVL delta) -- referenced by MCDM cost/stab.
    df["gas_gwei"] = np.clip(25 + 8 * rng.standard_normal(n) + 5 * np.sin(np.arange(n) / 24), 5, 300)
    df["delta_tvl_24h_aave"] = df["tvl_aave"].pct_change(24).fillna(0.0)
    df["delta_tvl_24h_compound"] = df["tvl_compound"].pct_change(24).fillna(0.0)

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out_path)
        print(f"[synthetic] wrote {out_path}  shape={df.shape}")
    return df


# ---------------------------------------------------------------------------
# Observation construction
# ---------------------------------------------------------------------------

def _row_to_state(row: pd.Series, *, prefix: str, gas_col: str = "gas_gwei",
                  dtvl_col: Optional[str] = None) -> LendingGlobalStateExt:
    """Build a LendingGlobalStateExt from a row, prefix in {'aave','compound'}."""
    return LendingGlobalStateExt(
        collateral_price=1.0,                                   # USDC stable
        debt_price=1.0,
        lending_rate=float(row.get(f"r_{prefix}", 0.0) or 0.0),
        borrowing_rate=float(row.get(f"rb_{prefix}", 0.0) or 0.0),
        utilization=float(row.get(f"u_{prefix}", 0.0) or 0.0),
        gas_gwei=float(row.get(gas_col, 30.0) or 30.0),
        delta_tvl_24h=float(row.get(dtvl_col, 0.0) or 0.0) if dtvl_col else 0.0,
    )


def build_observations(df: pd.DataFrame) -> List[Observation]:
    """Convert a joined-clean DataFrame into a list of Observations.

    Rows where ``valid_aave`` or ``valid_compound`` is False are skipped.
    """
    out: List[Observation] = []
    have_dtvl_a = "delta_tvl_24h_aave" in df.columns
    have_dtvl_c = "delta_tvl_24h_compound" in df.columns
    have_gas = "gas_gwei" in df.columns

    for ts, row in df.iterrows():
        if not bool(row.get("valid_aave", True)):
            continue
        if not bool(row.get("valid_compound", True)):
            continue

        # Skip rows with NaN rates (post-outlier or warmup gaps).
        r_a = row.get("r_aave")
        r_c = row.get("r_compound")
        if r_a is None or r_c is None or pd.isna(r_a) or pd.isna(r_c):
            continue

        state_a = _row_to_state(
            row, prefix="aave",
            gas_col="gas_gwei" if have_gas else "_missing_",
            dtvl_col="delta_tvl_24h_aave" if have_dtvl_a else None,
        )
        state_c = _row_to_state(
            row, prefix="compound",
            gas_col="gas_gwei" if have_gas else "_missing_",
            dtvl_col="delta_tvl_24h_compound" if have_dtvl_c else None,
        )

        # Normalise timestamp to a tz-aware datetime.
        if isinstance(ts, pd.Timestamp):
            ts_dt = ts.to_pydatetime()
        else:
            ts_dt = ts
        if ts_dt.tzinfo is None:
            ts_dt = ts_dt.replace(tzinfo=timezone.utc)

        out.append(Observation(
            timestamp=ts_dt,
            states={"AAVE": state_a, "COMPOUND": state_c},
        ))
    return out


def split_observations(
    observations: List[Observation],
) -> Tuple[List[Observation], List[Observation], List[Observation]]:
    """Strict UTC-timestamp split into (train, val, test) lists."""
    tr: List[Observation] = []
    va: List[Observation] = []
    te: List[Observation] = []
    for obs in observations:
        ts = obs.timestamp
        if TRAIN_START <= ts <= TRAIN_END:
            tr.append(obs)
        elif VAL_START <= ts <= VAL_END:
            va.append(obs)
        elif TEST_START <= ts <= TEST_END:
            te.append(obs)
    return tr, va, te


def build_all(synthetic: bool = False) -> Tuple[
    List[Observation],
    Tuple[List[Observation], List[Observation], List[Observation]],
]:
    """Build observations from joined-clean (or synthetic) data.

    Returns ``(all_obs, (train, val, test))``.
    """
    if synthetic:
        df = make_synthetic_joined()
    else:
        df = load_joined_clean()
    all_obs = build_observations(df)
    splits = split_observations(all_obs)
    return all_obs, splits


# ---------------------------------------------------------------------------
# CLI smoke-test
# ---------------------------------------------------------------------------

def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--synthetic", action="store_true",
                    help="generate synthetic joined panel instead of loading the parquet")
    args = ap.parse_args(argv)

    all_obs, (tr, va, te) = build_all(synthetic=args.synthetic)
    print(f"total observations: {len(all_obs)}")
    print(f"  train: {len(tr)}  ({tr[0].timestamp if tr else '-'} .. {tr[-1].timestamp if tr else '-'})")
    print(f"  val  : {len(va)}  ({va[0].timestamp if va else '-'} .. {va[-1].timestamp if va else '-'})")
    print(f"  test : {len(te)}  ({te[0].timestamp if te else '-'} .. {te[-1].timestamp if te else '-'})")

    if all_obs:
        sample = all_obs[0]
        aave = sample.states["AAVE"]
        print(f"sample state @ {sample.timestamp}:")
        print(f"  AAVE: lending_rate={aave.lending_rate:.6e} u={aave.utilization:.3f} "
              f"gas={aave.gas_gwei:.1f} collateral_price={aave.collateral_price}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
