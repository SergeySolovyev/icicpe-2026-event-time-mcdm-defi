"""Honest expanding-window walk-forward for T3 (fixes leakage finding #1).

The committed `results/models/t3_cox.json` is fit on the FULL panel
(scripts/train_t3_sophisticated.py uses `panel.iloc[::60]` over all
3.9M blocks and `_fit_final_model` samples from the whole design), and
`run_6way_walkforward.py` then applies that one model to every window
W1..W6 -- all inside the training span. The resulting +7.03 bp
T3-over-T1 figure is therefore IN-SAMPLE.

This driver removes the leakage. For each window W_k (k >= 2):

  1. Train the F1+F3 Cox model (same methodology as
     train_t3_sophisticated: triple-barrier labels, sample-uniqueness,
     L2 ridge) on blocks STRICTLY before W_k.start minus a purge gap of
     HORIZON_BLOCKS + EMBARGO_BLOCKS (so no training label can reach into
     the test window).
  2. Replay that per-window T3 model on W_k.
  3. Compare net APY to T1 (training-free) on the same window.

W1 is dropped: there is no data before the panel start, so it cannot be
evaluated out-of-sample. Honest walk-forward N = 5 (W2..W6). The
dominant W6 window is retained and trained on W1..W5.

Outputs:
  results/models/expanding/t3_cox_before_w{k}.json   (per-window model)
  results/institutional/tables/t3_expanding_walkforward.csv
  results/institutional/tables/t3_expanding_stats.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest.replay_per_block import EventReplayEngine
from decision.t1_threshold import T1ThresholdPolicy
from decision.t3_hazard import T3HazardPolicy
from scripts.train_t3_sophisticated import (
    _build_design_matrix_explicit,
    _fit_final_model,
    HORIZON_BLOCKS,
    EMBARGO_BLOCKS,
    PENALIZERS,
)

# Same six windows as run_6way_walkforward.py.
WINDOWS = [
    ("W1", pd.Timestamp("2024-11-01", tz="UTC"), pd.Timestamp("2025-02-01", tz="UTC")),
    ("W2", pd.Timestamp("2025-02-01", tz="UTC"), pd.Timestamp("2025-05-01", tz="UTC")),
    ("W3", pd.Timestamp("2025-05-01", tz="UTC"), pd.Timestamp("2025-08-01", tz="UTC")),
    ("W4", pd.Timestamp("2025-08-01", tz="UTC"), pd.Timestamp("2025-11-01", tz="UTC")),
    ("W5", pd.Timestamp("2025-11-01", tz="UTC"), pd.Timestamp("2026-02-01", tz="UTC")),
    ("W6", pd.Timestamp("2026-02-01", tz="UTC"), pd.Timestamp("2026-04-30 23:59:59", tz="UTC")),
]

PURGE_GAP = HORIZON_BLOCKS + EMBARGO_BLOCKS  # ~46,512 blocks ~ 6.5 days
SUBSAMPLE_STRIDE = 60                        # match train_t3_sophisticated
MIN_TRAIN_ROWS = 2_000                       # Cox needs a reasonable design


def _net_apy(eq_df: pd.DataFrame) -> float:
    initial = float(eq_df["position_usd"].iloc[0])
    final = float(eq_df["position_usd"].iloc[-1])
    n_blocks = len(eq_df)
    years = max(n_blocks / (365 * 24 * 60 * 60 // 12), 1e-9)
    return ((final / initial) ** (1.0 / years) - 1) * 100.0


def _replay(policy, slice_df: pd.DataFrame) -> pd.DataFrame:
    engine = EventReplayEngine(
        initial_capital_usd=1_000_000.0,
        gas_used_estimate=200_000,
        default_gas_price_gwei=25.0,
        default_eth_price_usd=3500.0,
    )
    eq_df, _ = engine.run(panel=slice_df, policy=policy)
    return eq_df


def _paired_bootstrap(deltas: np.ndarray, n_boot: int = 10_000, seed: int = 42):
    rng = np.random.default_rng(seed)
    n = len(deltas)
    means = np.empty(n_boot)
    for b in range(n_boot):
        means[b] = deltas[rng.integers(0, n, n)].mean()
    lo, hi = np.percentile(means, [2.5, 97.5])
    p_one_sided = float((means <= 0).mean())  # H0: mean <= 0
    return float(deltas.mean()), float(lo), float(hi), p_one_sided


def main() -> int:
    t0 = time.time()
    panel = pd.read_parquet(ROOT / "data/cached/per_block_panel.parquet")
    panel["block_timestamp"] = pd.to_datetime(panel["block_timestamp"], utc=True)
    panel = panel.sort_values("block_timestamp").reset_index(drop=True)
    print(f"panel: {len(panel):,} blocks", flush=True)

    # CRITICAL FIX (audit finding #1b): materialise the F1 lead-rate
    # features under the exact names the Cox model was trained on, so the
    # replay engine's aux carries them and T3HazardPolicy actually
    # evaluates its hazard model instead of silently falling back to T1.
    # The panel only ships f1_dsr_apr_frac / f1_dsr_apy_pct, but the model
    # expects f1_dsr_apr / f1_dsr_lag_300 / f1_dsr_lag_1800 /
    # f1_dsr_delta_300 / f1_lead_spread_dsr_vs_top. Use the SAME
    # F1LeadBuilder the training used, so train-time and decision-time F1
    # values are identical by construction.
    from decision.features.f1_lead import F1LeadBuilder
    f1 = F1LeadBuilder().build(panel)[[
        "f1_dsr_apr", "f1_dsr_lag_300", "f1_dsr_lag_1800",
        "f1_dsr_delta_300", "f1_lead_spread_dsr_vs_top",
    ]]
    panel = panel.merge(f1, left_on="block_number", right_index=True, how="left")
    cov = panel["f1_dsr_delta_300"].notna().mean() * 100
    print(f"F1 features merged into panel for replay (coverage {cov:.1f}%)", flush=True)

    model_dir = ROOT / "results/models/expanding"
    model_dir.mkdir(parents=True, exist_ok=True)
    eq_dir = ROOT / "results/institutional/tables/equity_expanding"
    eq_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for k, (wid, s, e) in enumerate(WINDOWS):
        if k == 0:
            print(f"[{wid}] dropped — no pre-window data (panel starts here)", flush=True)
            continue

        test_slice = panel[(panel.block_timestamp >= s) & (panel.block_timestamp < e)].reset_index(drop=True)
        if len(test_slice) < 100:
            print(f"[{wid}] <100 test blocks, skip", flush=True)
            continue
        first_test_block = int(test_slice["block_number"].iloc[0])
        train_end_block = first_test_block - PURGE_GAP
        train_panel = panel[panel.block_number < train_end_block].reset_index(drop=True)
        train_sub = train_panel.iloc[::SUBSAMPLE_STRIDE].reset_index(drop=True)
        print(f"\n[{wid}] test {s.date()}..{e.date()} ({len(test_slice):,} blk)  "
              f"train<block {train_end_block:,} ({len(train_sub):,} subsampled rows, "
              f"purge {PURGE_GAP:,} blk)", flush=True)

        # --- Train F1+F3 Cox strictly on pre-window data ---
        design = _build_design_matrix_explicit(
            train_sub, include_f1=True, include_f3=True, include_f4=False)
        if len(design) < MIN_TRAIN_ROWS:
            print(f"  SKIP: design too small ({len(design)} rows)", flush=True)
            continue
        # Choose penalizer by a quick purged split is overkill here; use the
        # mid penalizer (0.001) that won the original sweep for F1+F3.
        artifact = _fit_final_model(design, penalizer=0.001)
        art_path = model_dir / f"t3_cox_before_{wid.lower()}.json"
        artifact.save_json(art_path)
        print(f"  trained T3 (in-sample C={artifact.c_index:.4f}, "
              f"n_design={len(design):,}) -> {art_path.name}", flush=True)

        # --- Replay per-window T3 vs training-free T1 on the SAME window ---
        t3 = T3HazardPolicy.from_json(art_path)
        t1 = T1ThresholdPolicy()
        eq_t3 = _replay(t3, test_slice)
        eq_t1 = _replay(t1, test_slice)
        eq_t3.merge(test_slice[["block_number"]], on="block_number", how="left").to_parquet(
            eq_dir / f"{wid.lower()}_t3_oos.parquet")

        apy_t3 = _net_apy(eq_t3)
        apy_t1 = _net_apy(eq_t1)
        delta_bp = (apy_t3 - apy_t1) * 100.0
        rows.append({
            "window_id": wid,
            "window_start": s.date().isoformat(),
            "window_end": e.date().isoformat(),
            "train_end_block": train_end_block,
            "n_train_design": len(design),
            "t1_apy_pct": apy_t1,
            "t3_apy_pct": apy_t3,
            "delta_bp": delta_bp,
        })
        print(f"  T1={apy_t1:+.3f}%  T3={apy_t3:+.3f}%  delta={delta_bp:+.2f} bp", flush=True)

    out = pd.DataFrame(rows)
    out_csv = ROOT / "results/institutional/tables/t3_expanding_walkforward.csv"
    out.to_csv(out_csv, index=False)
    print("\n" + out.to_string(), flush=True)

    if len(out) >= 2:
        deltas = out["delta_bp"].to_numpy()
        mean, lo, hi, p = _paired_bootstrap(deltas)
        stats = {
            "method": "expanding-window walk-forward (train strictly pre-window, "
                      f"purge {PURGE_GAP} blocks)",
            "n_windows": int(len(deltas)),
            "windows": out["window_id"].tolist(),
            "mean_delta_bp": mean,
            "ci_low_95_bp": lo,
            "ci_high_95_bp": hi,
            "p_one_sided_le0": p,
            "wins": int((deltas > 0).sum()),
        }
        stats_path = ROOT / "results/institutional/tables/t3_expanding_stats.json"
        stats_path.write_text(json.dumps(stats, indent=2))
        print(f"\n=== HONEST OOS T3-vs-T1 (N={len(deltas)}) ===", flush=True)
        print(f"mean {mean:+.2f} bp  95% CI [{lo:+.2f}, {hi:+.2f}]  "
              f"p={p:.4f}  wins={stats['wins']}/{len(deltas)}", flush=True)
        print(f"wrote {stats_path}", flush=True)

    print(f"\ntotal {time.time()-t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
