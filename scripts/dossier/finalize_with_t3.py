"""Finalize the N×M matrix and paper macros after the T3 walk-forward
landed.

Recomputes walk_forward_NxM_contrasts.csv with T3 added as a 4th
policy row (3 protocol contrasts each = 3 new rows in the 12-row
final matrix), re-renders the dossier, re-derives paper macros,
and rebuilds the paper PDF + submission zip.

Triggered manually after `walk_forward_t3.csv` materialises (or
after the equity_walk_forward/w*_t3_hazard.parquet files complete
all 6 windows)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def _t3_apy_per_window() -> dict[str, float]:
    """Read each w*_t3_hazard.parquet file and compute window-level APY
    via the geometric end-equity / initial formula."""
    eq_dir = ROOT / "results/institutional/tables/equity_walk_forward"
    t3_files = sorted(eq_dir.glob("w*_t3_hazard.parquet"))
    if len(t3_files) < 6:
        raise RuntimeError(
            f"expected 6 T3 equity parquets, found {len(t3_files)}: {t3_files}"
        )
    BPY = 365 * 24 * 60 * 60 // 12
    apy = {}
    for f in t3_files:
        wid = f.stem.split("_")[0].upper()  # w1 -> W1
        eq = pd.read_parquet(f)
        initial = float(eq["position_usd"].iloc[0])
        final = float(eq["position_usd"].iloc[-1])
        n_blocks = len(eq)
        years = max(n_blocks / BPY, 1e-9)
        apy[wid] = ((final / initial) ** (1.0 / years) - 1.0) * 100
    return apy


def _extend_nxm_with_t3() -> pd.DataFrame:
    """Recompute the full N×M (now 4 policies × 3 protocols = 12 rows)."""
    t3_by_window = _t3_apy_per_window()
    pp_apy = pd.read_csv(ROOT / "results/institutional/tables/walk_forward_vs_all_holds.csv")
    nxm_existing = pd.read_csv(ROOT / "results/institutional/tables/walk_forward_NxM_contrasts.csv")

    # If T3 already in matrix, just rebuild fresh
    nxm_existing = nxm_existing[nxm_existing.policy != "t3_hazard"].copy()

    holds = {
        "aave": pp_apy.set_index("window_id")["aave_apy_pct"].to_dict(),
        "morpho": pp_apy.set_index("window_id")["morpho_apy_pct"].to_dict(),
        "euler": pp_apy.set_index("window_id")["euler_apy_pct"].to_dict(),
    }
    window_ids = list(pp_apy["window_id"])
    rng = np.random.default_rng(42)
    t3_rows = []
    for hold_name in ["aave", "morpho", "euler"]:
        deltas = []
        for w in window_ids:
            t3_apy = t3_by_window.get(w)
            h_apy = holds[hold_name].get(w)
            if t3_apy is None or h_apy is None:
                continue
            deltas.append(t3_apy - h_apy)
        d = np.array(deltas)
        n = len(d)
        boots = np.array([d[rng.integers(0, n, size=n)].mean() for _ in range(10000)])
        ci_low = float(np.percentile(boots, 2.5))
        ci_high = float(np.percentile(boots, 97.5))
        p = float((boots <= 0).mean())
        wins = int((d > 0).sum())
        t3_rows.append({
            "policy": "t3_hazard",
            "contrast": f"T3 hazard vs {hold_name}_hold",
            "protocol_hold": hold_name,
            "mean_pp": float(d.mean()),
            "ci_low_95": ci_low,
            "ci_high_95": ci_high,
            "p_one_sided_le0": p,
            "directional_consistency": wins,
            "n_windows": n,
        })
    out = pd.concat([nxm_existing, pd.DataFrame(t3_rows)], ignore_index=True)
    out_path = ROOT / "results/institutional/tables/walk_forward_NxM_contrasts.csv"
    out.to_csv(out_path, index=False)

    # Also append T3 to walk_forward.csv so the renderer's existing
    # T2-style processing picks up T3 in the Sharpe / APY pivot tables.
    wf_path = ROOT / "results/institutional/tables/walk_forward.csv"
    wf = pd.read_csv(wf_path)
    wf = wf[wf.policy != "t3_hazard"].copy()

    # Read full T3 per-window stats from equity parquets
    eq_dir = ROOT / "results/institutional/tables/equity_walk_forward"
    new_rows = []
    BPY = 365 * 24 * 60 * 60 // 12
    for w_idx, w in enumerate(window_ids, 1):
        f = eq_dir / f"w{w_idx}_t3_hazard.parquet"
        if not f.exists():
            continue
        eq = pd.read_parquet(f)
        eq["block_timestamp"] = pd.to_datetime(eq["block_timestamp"], utc=True)
        eq_indexed = eq.set_index(pd.DatetimeIndex(eq["block_timestamp"]))["position_usd"]
        eq_daily = eq_indexed.resample("D").last().dropna()
        ret = eq_daily.pct_change().dropna()
        sd = ret.std(ddof=1)
        sharpe = float(ret.mean() / sd * np.sqrt(365)) if sd > 0 else 0.0
        downside = ret[ret < 0]
        if len(downside) > 0:
            dsd = float(np.sqrt((downside ** 2).mean()))
            sortino = float(ret.mean() / dsd * np.sqrt(365)) if dsd > 0 else float("inf")
        else:
            sortino = float("inf")
        running_max = eq_daily.cummax()
        max_dd = float(((eq_daily - running_max) / running_max).min() * 100)
        n_rebalances = int(eq["current_protocol"].ne(
            eq["current_protocol"].shift()).sum() - 1) if "current_protocol" in eq.columns else 0
        initial = float(eq["position_usd"].iloc[0])
        final = float(eq["position_usd"].iloc[-1])
        years = max(len(eq) / BPY, 1e-9)
        apy_pct = ((final / initial) ** (1.0 / years) - 1.0) * 100
        # Pull window date range from any other policy's row
        ref = wf[wf.window_id == w]
        if not ref.empty:
            start = ref.iloc[0]["window_start"]
            end = ref.iloc[0]["window_end"]
            n_blocks = int(ref.iloc[0]["n_blocks"])
        else:
            start = ""
            end = ""
            n_blocks = len(eq)
        new_rows.append({
            "window_id": w, "window_start": start, "window_end": end,
            "policy": "t3_hazard", "n_blocks": n_blocks,
            "net_apy_pct": apy_pct, "sharpe": sharpe, "sortino": sortino,
            "max_drawdown_pct": max_dd, "n_rebalances": n_rebalances,
        })
    if new_rows:
        wf = pd.concat([wf, pd.DataFrame(new_rows)], ignore_index=True)
        wf.to_csv(wf_path, index=False)
        print(f"appended {len(new_rows)} T3 rows to walk_forward.csv")

    return out


def main() -> int:
    py = sys.executable
    print("[1/5] extending N×M matrix with T3 row...")
    df = _extend_nxm_with_t3()
    print(f"      {len(df)} rows now in N×M ({len(df) // 3} policies)")
    # Verify T3 vs T1 collapse hypothesis
    t1_aave = df[(df.policy == "t1_threshold") & (df.protocol_hold == "aave")]
    t3_aave = df[(df.policy == "t3_hazard") & (df.protocol_hold == "aave")]
    if not t1_aave.empty and not t3_aave.empty:
        print(f"      T1 vs Aave: {t1_aave.iloc[0].mean_pp:+.4f}pp")
        print(f"      T3 vs Aave: {t3_aave.iloc[0].mean_pp:+.4f}pp")
        delta = abs(t1_aave.iloc[0].mean_pp - t3_aave.iloc[0].mean_pp)
        print(f"      |T3 - T1| = {delta:.4f}pp "
              f"({'COLLAPSE confirmed' if delta < 0.05 else 'WARNING: divergence'})")

    print("[2/5] re-rendering dossier with T3 row in N×M table...")
    subprocess.run([py, "-m", "scripts.dossier.render_dossier"], cwd=ROOT, check=True)

    print("[3/5] regenerating walk-forward figures...")
    subprocess.run([py, "-m", "scripts.dossier.figures_walk_forward"], cwd=ROOT, check=True)

    print("[4/5] deriving paper macros with T3...")
    subprocess.run([py, "-m", "scripts.dossier.derive_paper_sections"], cwd=ROOT, check=True)

    print("[5/5] rebuilding paper submission tree...")
    subprocess.run([py, "-m", "scripts.build_vol2_submission"], cwd=ROOT, check=True)

    print()
    print("=== Finalize with T3 complete ===")
    print("Next: cd papers/icicpe-scopus-vol2-submission && latexmk -pdf main.tex")
    print("Then: scripts.build_submission_zip --check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
