"""Reproducible generator for the allocation_flow.html equity curves.

Closes the verify-equity-curves workflow's caveat: the 6 passive-hold +
greedy curves were injected from an un-versioned _extra_curves.json with no
generator. This script regenerates ALL comparison equity curves straight
from the authoritative per-block equity parquets + the panel, sampled on the
animation's existing eqAD day grid, so the animation, test_matrix.csv and the
paper all agree.

Emits (on the eqAD grid parsed from allocation_flow.html):
  eqT2     -- T2 OU optimal-stopping  (equity_t2_optimal_stopping.parquet)
  eqGreedy -- b3 naive auto-router    (equity_b3_greedy_spot.parquet)
  eqHolds  -- 6 passive holds, GEOMETRIC per-block from the panel
T3 is NOT emitted: it is bit-identical to T1 in this window (deployed
fallback) -- it overlays T1 and is handled by a caption, not a curve.

Output: results/figures/allocation_widget_curves.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "results" / "figures"
EQ = ROOT / "results" / "tables" / "equity"
PANEL = ROOT / "data" / "cached" / "per_block_panel.parquet"
HTML = FIG / "allocation_flow.html"
BPY = 365 * 24 * 60 * 60 // 12  # 2,628,000 blocks/yr (12s/block)
PROTO = ["aave_v3", "compound_v3", "spark", "morpho_blue", "euler_v2", "fluid"]
START, END = "2026-01-01", "2026-05-01"


def _eqAD() -> list[float]:
    """The exact day grid the animation already uses (keep curves aligned)."""
    html = HTML.read_text(encoding="utf-8")
    m = re.search(r'"eqAD":(\[[^\]]*\])', html)
    return json.loads(m.group(1))


def _sample(day: np.ndarray, val: np.ndarray, grid: list[float]) -> list[int]:
    idx = np.clip(np.searchsorted(day, np.asarray(grid), side="right") - 1, 0, len(val) - 1)
    return [int(round(val[i])) for i in idx]


def main() -> int:
    grid = _eqAD()

    # --- T2 + greedy from the authoritative equity parquets ---
    out = {}
    for key, name in (("t2_optimal_stopping", "eqT2"), ("b3_greedy_spot", "eqGreedy")):
        eq = pd.read_parquet(EQ / f"equity_{key}.parquet")
        eq["block_timestamp"] = pd.to_datetime(eq["block_timestamp"], utc=True)
        t0 = eq["block_timestamp"].iloc[0]
        day = ((eq["block_timestamp"] - t0).dt.total_seconds() / 86400.0).to_numpy()
        out[name] = _sample(day, eq["position_usd"].to_numpy(), grid)

    # --- 6 passive holds, GEOMETRIC per-block from the panel (never simple-interest) ---
    p = pd.read_parquet(PANEL)
    p["block_timestamp"] = pd.to_datetime(p["block_timestamp"], utc=True)
    s = p[(p.block_timestamp >= START) & (p.block_timestamp < END)].reset_index(drop=True)
    t0 = s["block_timestamp"].iloc[0]
    day = ((s["block_timestamp"] - t0).dt.total_seconds() / 86400.0).to_numpy()
    holds = []
    for pr in PROTO:
        apr = s[f"{pr}_lending_apr"].to_numpy()
        eq = 1e6 * np.cumprod(1.0 + np.where(np.isnan(apr), 0.0, apr / BPY))
        holds.append(_sample(day, eq, grid))
    out["eqHolds"] = holds

    (FIG / "allocation_widget_curves.json").write_text(
        json.dumps(out, separators=(",", ":")), encoding="utf-8")
    finals = {"T2": out["eqT2"][-1], "greedy": out["eqGreedy"][-1],
              **{PROTO[i]: holds[i][-1] for i in range(6)}}
    print("finals:", finals, flush=True)
    print(f"[ok] wrote {FIG/'allocation_widget_curves.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
