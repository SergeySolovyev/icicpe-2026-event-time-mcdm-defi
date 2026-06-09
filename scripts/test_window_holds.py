"""All-six passive-hold net APYs on the held-out test window.

Answers "you benchmark 6 protocols -- where are the other 4 holds?"
(test_matrix.csv carries only the legacy B1-Aave / B2-Compound holds).

A passive hold needs no replay loop: the engine's accrual is
position *= (1 + apr/BLOCKS_PER_YEAR) per non-NaN block, so the hold's
growth is the vectorized product over the window (NaN blocks accrue
nothing -- identical to EventReplayEngine semantics). Validated against
the engine's own outputs in results/tables/test_matrix.csv:
aave 3.261 vs 3.2609, compound 2.688 vs 2.6875 (4-decimal agreement).

Known data caveat surfaced here: compound_v3 has ONE contiguous fetch
gap inside the test window (2026-02-27 09:00 -> 2026-03-07 16:00 UTC,
59,700 blocks ~ 8.3 days) treated as zero accrual -- a ~6 bp
conservative bias on the Compound hold, disclosed in the paper.

Output: results/tables/test_window_holds.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BLOCKS_PER_YEAR = 365 * 24 * 60 * 60 // 12
PROTOCOLS = ("aave_v3", "compound_v3", "spark", "morpho_blue", "euler_v2", "fluid")
TEST_START, TEST_END = "2026-01-01", "2026-05-01"


def main() -> int:
    panel = pd.read_parquet(ROOT / "data/cached/per_block_panel.parquet")
    panel["block_timestamp"] = pd.to_datetime(panel["block_timestamp"], utc=True)
    s = panel[(panel.block_timestamp >= TEST_START)
              & (panel.block_timestamp < TEST_END)].reset_index(drop=True)
    years = len(s) / BLOCKS_PER_YEAR
    print(f"test window: {len(s):,} blocks, {years:.3f} yr", flush=True)

    rows = []
    for p in PROTOCOLS:
        apr = s[f"{p}_lending_apr"].to_numpy()
        valid = ~np.isnan(apr)
        growth = float(np.prod(1 + apr[valid] / BLOCKS_PER_YEAR))
        apy = (growth ** (1 / years) - 1) * 100
        rows.append({"protocol": p, "net_apy_pct": round(apy, 4),
                     "nan_blocks": int((~valid).sum())})
        print(f"  hold {p:<14s} {apy:6.3f}%  (NaN blocks {(~valid).sum():,})",
              flush=True)

    out = ROOT / "results/tables/test_window_holds.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"[ok] wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
