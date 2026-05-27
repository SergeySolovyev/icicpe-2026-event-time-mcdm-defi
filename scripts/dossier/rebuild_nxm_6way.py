"""Rebuild the N×M paired-bootstrap matrix with all 6 protocols.

After Spark/Compound/Fluid per-window APYs landed (from Messari subgraph,
existing hourly RPC, and DeFiLlama respectively), this script recomputes
walk_forward_NxM_contrasts.csv as a 3 policies × 6 protocols = 18-row
matrix.

Also drops the deprecated B4 MCDM-EMA policy: that was the 2026c naive
hourly cliff-edge that produced 2 rebalances in 4 months. Keeping it as
a "benchmark" implicitly validated wrong-resolution and is removed for
ICICPE Vol-2.

Policies (rows): T1 gas-aware threshold, T2 OU optimal-stopping, T3 Cox
proportional-hazards. Each contrasted against passive hold of one of:
Aave V3, Compound V3, Spark, Morpho Blue, Euler V2, Fluid Finance.

Bootstrap: paired by window_id, B=10000, seed=42, one-sided H0 ΔAPY ≤ 0.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TABLES = ROOT / "results/institutional/tables"
EQ_DIR = TABLES / "equity_walk_forward"

WINDOW_IDS = ["W1", "W2", "W3", "W4", "W5", "W6"]
BPY = 365 * 24 * 60 * 60 // 12  # blocks per year at 12s/block


def _policy_apy_per_window(policy: str) -> dict[str, float]:
    """Compute geometric APY per window from the per-block equity parquet."""
    out: dict[str, float] = {}
    for w_idx, wid in enumerate(WINDOW_IDS, start=1):
        f = EQ_DIR / f"w{w_idx}_{policy}.parquet"
        if not f.exists():
            continue
        eq = pd.read_parquet(f)
        initial = float(eq["position_usd"].iloc[0])
        final = float(eq["position_usd"].iloc[-1])
        years = max(len(eq) / BPY, 1e-9)
        out[wid] = ((final / initial) ** (1.0 / years) - 1.0) * 100
    return out


def _hold_apy_per_window() -> dict[str, dict[str, float]]:
    """Load per-window APY for each of the 6 protocol holds.

    Aave/Morpho/Euler from per-block panel (walk_forward_vs_all_holds.csv);
    Compound/Spark/Fluid from separate per_window_apy.csv files.
    """
    holds: dict[str, dict[str, float]] = {}
    pp = pd.read_csv(TABLES / "walk_forward_vs_all_holds.csv")
    for proto in ("aave", "morpho", "euler"):
        holds[proto] = pp.set_index("window_id")[f"{proto}_apy_pct"].to_dict()

    cmp_df = pd.read_csv(TABLES / "compound_per_window_apy.csv")
    holds["compound"] = cmp_df.set_index("window_id")["compound_apy_pct"].to_dict()

    spk_df = pd.read_csv(TABLES / "spark_per_window_apy.csv")
    holds["spark"] = spk_df.set_index("window_id")["spark_apy_pct"].to_dict()

    flu_df = pd.read_csv(TABLES / "fluid_per_window_apy.csv")
    holds["fluid"] = flu_df.set_index("window_id")["fluid_apy_pct"].to_dict()
    return holds


def _bootstrap_contrast(deltas: np.ndarray, *, B: int = 10000,
                        seed: int = 42) -> dict[str, float]:
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
    policies = {
        "t1_threshold": _policy_apy_per_window("t1_threshold"),
        "t2_optimal_stopping": _policy_apy_per_window("t2_optimal_stopping"),
        "t3_hazard": _policy_apy_per_window("t3_hazard"),
    }
    rows: list[dict] = []
    for pol_name, pol_apy in policies.items():
        if not pol_apy:
            print(f"[skip] policy {pol_name} has no equity parquets")
            continue
        for proto, proto_apy in holds.items():
            deltas = []
            for wid in WINDOW_IDS:
                p, h = pol_apy.get(wid), proto_apy.get(wid)
                if p is None or h is None or pd.isna(p) or pd.isna(h):
                    continue
                deltas.append(p - h)
            if not deltas:
                continue
            res = _bootstrap_contrast(np.array(deltas))
            rows.append({
                "policy": pol_name,
                "contrast": f"{pol_name} vs {proto}_hold",
                "protocol_hold": proto,
                **res,
            })
    out = pd.DataFrame(rows)
    out_path = TABLES / "walk_forward_NxM_contrasts.csv"
    out.to_csv(out_path, index=False)
    print(f"wrote {len(out)} rows to {out_path}")
    print(out.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
