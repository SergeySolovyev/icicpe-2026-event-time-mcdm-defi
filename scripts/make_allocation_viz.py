"""Allocation-flow visualization data + static figure (REAL data).

Extracts from the T1 test-window replay (results/tables/equity/
equity_t1_threshold.parquet, 864k blocks, 321 real switches):

1. The exact allocation SEGMENTS: contiguous runs of current_protocol
   with start/end day-offsets and equity -- the true "asset hops"
   between the six venues. ~322 segments, lossless.
2. Downsampled per-protocol APR curves from the panel (the rate
   crossovers that DRIVE the hops).
3. Downsampled T1 equity + passive-Aave equity for contrast.

Outputs:
  results/figures/allocation_flow.json      (compact, for the animation)
  results/figures/allocation_timeline.png   (static, paper-grade)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PROTOCOLS = ["aave_v3", "compound_v3", "spark", "morpho_blue", "euler_v2", "fluid"]
PRETTY = {"aave_v3": "Aave V3", "compound_v3": "Compound V3", "spark": "Spark",
          "morpho_blue": "Morpho Blue", "euler_v2": "Euler V2", "fluid": "Fluid"}
COLORS = {"aave_v3": "#7c5cff", "compound_v3": "#00b4d8", "spark": "#ff9f1c",
          "morpho_blue": "#4361ee", "euler_v2": "#2ec4b6", "fluid": "#e63946"}
N_APR_POINTS = 240  # downsample target for curves


def main() -> int:
    eq = pd.read_parquet(ROOT / "results/tables/equity/equity_t1_threshold.parquet")
    eq["block_timestamp"] = pd.to_datetime(eq["block_timestamp"], utc=True)
    t0 = eq["block_timestamp"].iloc[0]
    eq["day"] = (eq["block_timestamp"] - t0).dt.total_seconds() / 86400.0

    # ---- 1. exact allocation segments (lossless run-length encoding) ----
    proto = eq["current_protocol"].to_numpy()
    change = np.flatnonzero(proto[1:] != proto[:-1]) + 1
    starts = np.concatenate([[0], change])
    ends = np.concatenate([change, [len(eq)]])
    segments = []
    for s, e in zip(starts, ends):
        segments.append({
            "p": PROTOCOLS.index(proto[s]),
            "d0": round(float(eq["day"].iloc[s]), 3),
            "d1": round(float(eq["day"].iloc[e - 1]), 3),
            "eq0": round(float(eq["position_usd"].iloc[s]), 0),
            "eq1": round(float(eq["position_usd"].iloc[e - 1]), 0),
        })
    n_switches = len(segments) - 1
    print(f"segments: {len(segments)} (switches {n_switches})", flush=True)

    # ---- 2. APR curves, downsampled ----
    panel = pd.read_parquet(ROOT / "data/cached/per_block_panel.parquet",
                            columns=["block_timestamp"]
                            + [f"{p}_lending_apr" for p in PROTOCOLS])
    panel["block_timestamp"] = pd.to_datetime(panel["block_timestamp"], utc=True)
    win = panel[(panel.block_timestamp >= t0)
                & (panel.block_timestamp <= eq["block_timestamp"].iloc[-1])]
    step = max(1, len(win) // N_APR_POINTS)
    ds = win.iloc[::step]
    days = ((ds["block_timestamp"] - t0).dt.total_seconds() / 86400.0).round(2).tolist()
    apr = {p: [None if np.isnan(v) else round(v * 100, 3)
               for v in ds[f"{p}_lending_apr"]] for p in PROTOCOLS}

    # ---- 3. equity curves, downsampled ----
    eq_b1 = pd.read_parquet(ROOT / "results/tables/equity/equity_b1_always_aave.parquet",
                            columns=["position_usd"])
    estep = max(1, len(eq) // N_APR_POINTS)
    eq_days = eq["day"].iloc[::estep].round(2).tolist()
    eq_t1 = eq["position_usd"].iloc[::estep].round(0).tolist()
    eq_aave = eq_b1["position_usd"].iloc[::estep].round(0).tolist()

    out = {
        "meta": {"start": str(t0.date()), "end": str(eq["block_timestamp"].iloc[-1].date()),
                 "n_blocks": len(eq), "n_switches": n_switches,
                 "final_t1": round(float(eq["position_usd"].iloc[-1]), 0),
                 "final_aave": round(float(eq_b1["position_usd"].iloc[-1]), 0),
                 "gas_usd": 67.97, "source": "equity_t1_threshold.parquet (real replay)"},
        "protocols": [PRETTY[p] for p in PROTOCOLS],
        "colors": [COLORS[p] for p in PROTOCOLS],
        "segments": segments,
        "apr_days": days, "apr": apr,
        "eq_days": eq_days, "eq_t1": eq_t1, "eq_aave": eq_aave,
    }
    fig_dir = ROOT / "results/figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    jpath = fig_dir / "allocation_flow.json"
    jpath.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"[ok] {jpath} ({jpath.stat().st_size/1024:.0f} KB)", flush=True)

    # ---- 4. static paper-grade figure ----
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True,
                             gridspec_kw={"height_ratios": [3, 1.2, 2.2]})
    dts = ds["block_timestamp"]

    ax = axes[0]
    for p in PROTOCOLS:
        ax.plot(dts, [v if v is not None else np.nan for v in apr[p]],
                color=COLORS[p], lw=1.1, label=PRETTY[p])
    ax.set_ylabel("Supply APR (%)")
    ax.legend(ncol=3, fontsize=8, loc="upper left", framealpha=0.9)
    ax.set_title("T1 event-time allocation across six venues — real replay, "
                 f"Jan–Apr 2026 ({n_switches} switches, \\$68 real gas)")

    ax = axes[1]
    for seg in segments:
        ax.axvspan(t0 + pd.Timedelta(days=seg["d0"]), t0 + pd.Timedelta(days=seg["d1"]),
                   color=COLORS[PROTOCOLS[seg["p"]]], lw=0)
    ax.set_yticks([])
    ax.set_ylabel("held venue", fontsize=8)

    ax = axes[2]
    ax.plot(eq["block_timestamp"].iloc[::estep], eq_t1, color="#111", lw=1.6,
            label=f"T1 active → ${out['meta']['final_t1']:,.0f}")
    ax.plot(eq["block_timestamp"].iloc[::estep], eq_aave, color=COLORS["aave_v3"],
            lw=1.3, ls="--", label=f"hold Aave → ${out['meta']['final_aave']:,.0f}")
    ax.set_ylabel("equity (USD)")
    ax.legend(fontsize=9, loc="upper left")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))

    fig.tight_layout()
    ppath = fig_dir / "allocation_timeline.png"
    fig.savefig(ppath, dpi=200)
    print(f"[ok] {ppath}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
