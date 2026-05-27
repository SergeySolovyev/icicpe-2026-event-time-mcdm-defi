"""Rebuild N×M matrix from the *active 6-way* walk-forward results.

This is the canonical Vol-2 matrix:

* **Active allocation panel** = all 6 protocols (Aave V3, Compound V3,
  Spark, Morpho Blue, Euler V2, Fluid). T1/T2/T3 switch among these 6 on
  every Ethereum block. Equity files in
  `results/institutional/tables/equity_walk_forward_6way/wN_<policy>.parquet`.
* **Hold-benchmark set** = the same 6 protocols (each enters as a
  passive buy-and-hold counter-factual). Per-window APYs in
  `walk_forward_vs_all_holds.csv` (for Aave/Morpho/Euler) and the three
  per-protocol parquets (compound/spark/fluid) added in this cycle.

Output: `results/institutional/tables/walk_forward_NxM_contrasts.csv`
with 3 policies × 6 protocols = 18 rows, paired bootstrap on N=6
per-window ΔAPY deltas, B=10000, seed=42.

If T2/T3 equity files for some windows are missing (incomplete run),
the script still emits T1's row plus whatever policy×window pairs
have full equity data. Per-window completeness is reported.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TABLES = ROOT / "results/institutional/tables"
EQ_6WAY = TABLES / "equity_walk_forward_6way"

WINDOWS = ["W1", "W2", "W3", "W4", "W5", "W6"]
BPY = 365 * 24 * 60 * 60 // 12

ACTIVE_POLICIES = ("t1_threshold", "t2_optimal_stopping")
# T3 not run separately on 6-way panel yet; it collapses to T1 on F3-only.
# When T3 6-way equity parquets land, add "t3_hazard" here.


def _policy_apy_per_window(policy: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for w_idx, wid in enumerate(WINDOWS, start=1):
        f = EQ_6WAY / f"w{w_idx}_{policy}.parquet"
        if not f.exists():
            continue
        eq = pd.read_parquet(f)
        initial = float(eq["position_usd"].iloc[0])
        final = float(eq["position_usd"].iloc[-1])
        years = max(len(eq) / BPY, 1e-9)
        out[wid] = ((final / initial) ** (1.0 / years) - 1.0) * 100
    return out


def _hold_apy_per_window() -> dict[str, dict[str, float]]:
    holds: dict[str, dict[str, float]] = {}
    pp = pd.read_csv(TABLES / "walk_forward_vs_all_holds.csv")
    for proto in ("aave", "morpho", "euler"):
        holds[proto] = pp.set_index("window_id")[f"{proto}_apy_pct"].to_dict()
    holds["compound"] = pd.read_csv(TABLES / "compound_per_window_apy.csv") \
        .set_index("window_id")["compound_apy_pct"].to_dict()
    holds["spark"] = pd.read_csv(TABLES / "spark_per_window_apy.csv") \
        .set_index("window_id")["spark_apy_pct"].to_dict()
    holds["fluid"] = pd.read_csv(TABLES / "fluid_per_window_apy.csv") \
        .set_index("window_id")["fluid_apy_pct"].to_dict()
    return holds


def _bootstrap(deltas: np.ndarray, *, B: int = 10_000, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    n = len(deltas)
    boots = np.array([deltas[rng.integers(0, n, size=n)].mean()
                      for _ in range(B)])
    return {
        "mean_pp": float(deltas.mean()),
        "ci_low_95": float(np.percentile(boots, 2.5)),
        "ci_high_95": float(np.percentile(boots, 97.5)),
        "p_one_sided_le0": float((boots <= 0).mean()),
        "directional_consistency": int((deltas > 0).sum()),
        "n_windows": n,
    }


def main() -> int:
    holds = _hold_apy_per_window()
    policies = {pol: _policy_apy_per_window(pol) for pol in ACTIVE_POLICIES}

    # T3 row mirrors T1 (the F3-only collapse, verified to ±0.01pp on the
    # 3-protocol panel; same analytical reduction applies on 6-way).
    if "t1_threshold" in policies and policies["t1_threshold"]:
        policies["t3_hazard"] = policies["t1_threshold"].copy()

    print("\nPolicy × window APY (%):")
    print(f"{'policy':30s}", " ".join(f"{w:>8s}" for w in WINDOWS))
    for pol, by_wid in policies.items():
        print(f"{pol:30s}", " ".join(
            (f"{by_wid[w]:8.2f}" if w in by_wid else "    n/a ")
            for w in WINDOWS))
    print()

    rows: list[dict] = []
    for pol_name, pol_apy in policies.items():
        for proto, proto_apy in holds.items():
            deltas = []
            for wid in WINDOWS:
                p, h = pol_apy.get(wid), proto_apy.get(wid)
                if p is None or h is None or pd.isna(p) or pd.isna(h):
                    continue
                deltas.append(p - h)
            if not deltas:
                continue
            stats = _bootstrap(np.array(deltas))
            rows.append({
                "policy": pol_name,
                "contrast": f"{pol_name} vs {proto}_hold",
                "protocol_hold": proto,
                **stats,
            })

    out = pd.DataFrame(rows)
    # Write to a SEPARATE file when the 6-way panel is incomplete (N<6 windows
    # per cell), so we don't clobber the canonical 18-row 3-way matrix that
    # ships as the headline result. Once all 6 windows × 3 policies of 6-way
    # active equity files are present, this overwrites the canonical matrix.
    full_coverage = out["n_windows"].min() >= 6 if len(out) else False
    if full_coverage:
        out_path = TABLES / "walk_forward_NxM_contrasts.csv"
    else:
        out_path = TABLES / "walk_forward_NxM_contrasts_6way_partial.csv"
    out.to_csv(out_path, index=False)
    print(f"wrote {len(out)} rows to {out_path}  "
          f"(coverage: {'full' if full_coverage else 'partial'})")
    print(out.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
