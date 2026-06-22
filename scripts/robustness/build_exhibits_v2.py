"""Two CLEAN robustness exhibits, replacing the two that degenerated in v1.

v1's permutation null (B) and dwell-PBO (D) both came back 'failing' -- but as
artifacts, not real failures:
  * B (time-shuffle): independently circular-shifting each protocol preserves
    each block's cross-sectional DISPERSION, which is exactly what T1 reacts to.
    The edge survives -> that is the *point* (T1 is contemporaneous, not a
    forecast), but it is the wrong null for "is it curve-fit".
  * D (PBO over dwell): the heatmap (C) shows the 5 dwell values differ by
    <0.02pp -> ranking them is pure noise, so CSCV degenerates to PBO=1.0.
    PBO is meaningful over materially-different *strategies*, not a flat plateau.

This script computes the two tests that actually discriminate:
  E. RANDOM-DESTINATION NULL: reuse T1's exact switch *cadence* (same number of
     switches, same gas), but send each segment to a RANDOM venue instead of the
     highest-rate one. If T1 sits in the far right tail, the *selection* (go to
     the max net of gas) -- not the churning -- is the alpha. Clean, non-
     confounded: the ONLY thing varied is where each switch lands.
  F. STRATEGY-FAMILY PBO (CSCV): over {T1, 6 single-venue holds}. "If you pick
     the best *strategy* on in-sample months, does it stay best out-of-sample?"
     That is the real overfitting question an allocator faces. ~0 = robust.

All on the validated fast_t1 (reproduces the engine to the dollar). Real data.
Writes results/figures/robustness/robustness_v2.json.
"""
from __future__ import annotations

import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "robustness"))
from fast_t1 import run_t1, hold_final, BPY  # noqa: E402

PROT = ["aave_v3", "compound_v3", "spark", "morpho_blue", "euler_v2", "fluid"]
PRETTY = ["Aave V3", "Compound V3", "Spark", "Morpho Blue", "Euler V2", "Fluid"]
OUT = ROOT / "results" / "figures" / "robustness"
WIN = ("2026-01-01", "2026-05-01")  # same test window as v1 B/C/D
GAS_USED = 200_000


def _arrays(s):
    apr = np.column_stack([s[f"{x}_lending_apr"].to_numpy() for x in PROT])
    gas = s["gas_price_gwei"].to_numpy()
    eth = s["eth_usd"].to_numpy() if "eth_usd" in s else np.full(len(s), 3500.0)
    return apr, gas, eth, s["block_number"].to_numpy()


def main() -> int:
    print("[load] panel...", flush=True)
    p = pd.read_parquet(ROOT / "data/cached/per_block_panel.parquet")
    p["block_timestamp"] = pd.to_datetime(p["block_timestamp"], utc=True)
    s = p[(p.block_timestamp >= WIN[0]) & (p.block_timestamp < WIN[1])].reset_index(drop=True)
    apr, gas, eth, blk = _arrays(s)
    n = len(s)
    summary = {"window": f"{WIN[0]}..{WIN[1]}", "n_blocks": n}

    # ---------- E. RANDOM-DESTINATION NULL ----------
    print("[E] random-destination null...", flush=True)
    t0 = time.time()
    sw = []
    fin0, nsw0 = run_t1(apr, gas, eth, blk, switch_log=sw)  # T1's real run + switch cadence
    idxs = [i for i, _ in sw]                                # switch block-indices (chronological)
    venues = [v for _, v in sw]
    cost_blk = GAS_USED * gas * 1e-9 * eth                   # gas $ per switch at each block
    # per-protocol cumulative log-growth -> segment growth = exp(clog[b]-clog[a])
    logg = np.log1p(np.where(np.isnan(apr), 0.0, apr / BPY))
    clog = np.vstack([np.zeros(6), np.cumsum(logg, axis=0)])  # (n+1, 6)
    bounds = idxs + [n]

    def seg_final(choice):  # choice: venue per segment
        pos = 1e6
        for k in range(len(idxs)):
            a, b = idxs[k], bounds[k + 1]
            pos -= cost_blk[a]
            pos *= float(np.exp(clog[b, choice[k]] - clog[a, choice[k]]))
        return pos

    t1_seg = seg_final(venues)                # T1 under the SAME segment accounting (apples-to-apples)
    rng = np.random.default_rng(7)
    N = 5000
    rand_finals = np.array([seg_final(rng.integers(0, 6, size=len(idxs))) for _ in range(N)])
    p_rand = float((rand_finals >= t1_seg).mean())
    z = (t1_seg - rand_finals.mean()) / rand_finals.std()
    summary["E_random_null"] = {
        "n_switches": len(idxs), "n_random": N,
        "t1_engine_final_usd": round(fin0), "t1_segment_final_usd": round(t1_seg),
        "random_mean_usd": round(float(rand_finals.mean())),
        "random_std_usd": round(float(rand_finals.std())),
        "random_p95_usd": round(float(np.percentile(rand_finals, 95))),
        "random_max_usd": round(float(rand_finals.max())),
        "p_value": p_rand, "z_score": round(z, 2),
        "random_finals": np.round(rand_finals).astype(int).tolist()}
    print(f"   T1 ${t1_seg:,.0f} vs {N} random-destination allocators "
          f"(same cadence/gas): mean ${rand_finals.mean():,.0f}, "
          f"max ${rand_finals.max():,.0f} | p={p_rand:.4f} z={z:.1f}  ({time.time()-t0:.0f}s)", flush=True)

    # ---------- F. STRATEGY-FAMILY PBO (CSCV) ----------
    print("[F] strategy-family PBO / CSCV...", flush=True)
    t0 = time.time()
    S = 8
    bnd = np.linspace(0, n, S + 1).astype(int)
    chunks = [(bnd[i], bnd[i + 1]) for i in range(S)]
    combos = list(itertools.combinations(range(S), S // 2))
    names = ["T1"] + PRETTY

    def perf(idx):  # net total-return (%) of each strategy over the block-index set
        a, g, e = apr[idx], gas[idx], eth[idx]
        b = np.arange(len(idx))
        t1f = run_t1(a, g, e, b)[0]
        out = [(t1f / 1e6 - 1) * 100]
        for c in range(6):
            out.append((hold_final(a[:, c]) / 1e6 - 1) * 100)
        return np.array(out)

    lambdas, is_winner = [], []
    for IS in combos:
        ISset = set(IS)
        isidx = np.concatenate([np.arange(*chunks[i]) for i in IS])
        ooidx = np.concatenate([np.arange(*chunks[i]) for i in range(S) if i not in ISset])
        pi, po = perf(isidx), perf(ooidx)
        best = int(np.argmax(pi))
        is_winner.append(best)
        rank = (po < po[best]).mean()  # fraction of strategies IS-best beats OOS
        rank = min(max(rank, 1e-3), 1 - 1e-3)
        lambdas.append(np.log(rank / (1 - rank)))
    lambdas = np.array(lambdas)
    pbo = float((lambdas <= 0).mean())
    t1_is_best = float(np.mean([w == 0 for w in is_winner]))
    summary["F_family_pbo"] = {
        "S_chunks": S, "n_combos": len(combos), "strategies": names,
        "PBO": round(pbo, 4),
        "t1_is_best_in_sample_fraction": round(t1_is_best, 4),
        "logits": np.round(lambdas, 3).tolist(),
        "interpretation": "CSCV over {T1, 6 holds}: P(in-sample-best STRATEGY is below-median OOS). ~0 = the winner generalises."}
    print(f"   family PBO = {pbo:.3f} over {len(combos)} splits | "
          f"T1 is in-sample-best in {t1_is_best*100:.0f}% of splits  ({time.time()-t0:.0f}s)", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "robustness_v2.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n[ok] wrote {OUT}/robustness_v2.json", flush=True)
    print(json.dumps({"E_p_value": p_rand, "E_z": round(z, 1),
                      "F_family_PBO": round(pbo, 4),
                      "F_t1_is_best_frac": round(t1_is_best, 3)}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
