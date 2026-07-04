"""Robustness suite, recomputed from the panel (self-contained, reuses notebook_core).

Reproduces the robustness numbers 6-way from per_block_panel:
  walk-forward 6/6, per-venue paired bootstrap + Holm, random-destination null (9sigma),
  strategy-family PBO=0, parameter plateau, gas-cost sweep, moving-block bootstrap + N_eff.
All on the validated fast engine (notebook_core.run_t1 etc.).
"""
from __future__ import annotations

import itertools
from collections import deque

import numpy as np
import pandas as pd

from notebook_core import run_t1, run_greedy, hold_final, slice_arrays, net_apy, BPY, PROT, GAS_USED

PRETTY = ["Aave V3", "Compound V3", "Spark", "Morpho Blue", "Euler V2", "Fluid"]
WINDOWS = [("W1", "2024-11-01", "2025-02-01"), ("W2", "2025-02-01", "2025-05-01"),
           ("W3", "2025-05-01", "2025-08-01"), ("W4", "2025-08-01", "2025-11-01"),
           ("W5", "2025-11-01", "2026-02-01"), ("W6", "2026-02-01", "2026-05-01")]


def walk_forward(panel):
    """T1 net APY vs the best in-hindsight hold in each of 6 non-overlapping windows."""
    rows, deltas = [], {p: [] for p in PRETTY}
    for wid, a, b in WINDOWS:
        apr, gas, eth, blk, _, _, _ = slice_arrays(panel, a, b)
        n = len(apr)
        t1_final, t1_sw = run_t1(apr, gas, eth, blk)
        t1 = net_apy(t1_final, n)
        holds = [net_apy(hold_final(apr[:, i]), n) for i in range(6)]
        bi = int(np.argmax(holds))
        for i, p in enumerate(PRETTY):
            deltas[p].append(t1 - holds[i])
        rows.append({"window": wid, "span": f"{a[:7]}..{b[:7]}", "n_blocks": n,
                     "t1_apy": round(t1, 3), "best_hold": PRETTY[bi], "best_hold_apy": round(holds[bi], 3),
                     "edge_vs_best_pp": round(t1 - holds[bi], 3),
                     "edge_vs_aave_pp": round(t1 - holds[0], 3), "switches": t1_sw})
    return pd.DataFrame(rows), deltas


def _holm(pvals):
    m = len(pvals); order = np.argsort(pvals); adj = np.empty(m); run = 0.0
    for rank, idx in enumerate(order):
        run = max(run, (m - rank) * pvals[idx]); adj[idx] = min(run, 1.0)
    return adj


def paired_bootstrap_holm(deltas, n_boot=10000, seed=42):
    """Per-venue paired bootstrap over the 6 per-window edges + Holm FWER."""
    rng = np.random.default_rng(seed); rows = []
    pvals = []
    for p in PRETTY:
        d = np.array(deltas[p]); n = len(d)
        means = np.array([d[rng.integers(0, n, n)].mean() for _ in range(n_boot)])
        lo, hi = np.percentile(means, [2.5, 97.5])
        pj = float((means <= 0).mean())
        pvals.append(pj)
        rows.append({"venue": p, "mean_pp": round(float(d.mean()), 3),
                     "ci_low": round(float(lo), 3), "ci_high": round(float(hi), 3),
                     "dir": f"{int((d>0).sum())}/6", "p_one_sided": round(pj, 4)})
    holm = _holm(np.array(pvals))
    for i, r in enumerate(rows):
        r["p_holm"] = round(float(holm[i]), 4); r["survives_holm"] = bool(holm[i] <= 0.05)
    return pd.DataFrame(rows)


def random_null(apr, gas, eth, blk, N=5000, seed=7):
    """Same switch cadence + gas as T1, but RANDOM destination venue. T1 vs the null."""
    sw = []; fin0, _ = run_t1(apr, gas, eth, blk, switch_log=sw)
    idxs = [i for i, _ in sw]; venues = [v for _, v in sw]
    cost = GAS_USED * gas * 1e-9 * eth
    logg = np.log1p(np.where(np.isnan(apr), 0.0, apr / BPY))
    clog = np.vstack([np.zeros(6), np.cumsum(logg, axis=0)]); bounds = idxs + [len(apr)]

    def seg(choice):
        pos = 1e6
        for k in range(len(idxs)):
            a, b = idxs[k], bounds[k + 1]
            pos -= cost[a]; pos *= float(np.exp(clog[b, choice[k]] - clog[a, choice[k]]))
        return pos
    t1 = seg(venues); rng = np.random.default_rng(seed)
    rand = np.array([seg(rng.integers(0, 6, len(idxs))) for _ in range(N)])
    z = (t1 - rand.mean()) / rand.std()
    return {"t1": t1, "rand_mean": float(rand.mean()), "rand_max": float(rand.max()),
            "z": float(z), "p": float((rand >= t1).mean()), "n": N, "rand": rand}


def family_pbo(apr, gas, eth, blk, S=8):
    """CSCV PBO over {T1, 6 holds}: P(in-sample-best strategy below-median OOS)."""
    n = len(apr); bnd = np.linspace(0, n, S + 1).astype(int)
    chunks = [(bnd[i], bnd[i + 1]) for i in range(S)]
    combos = list(itertools.combinations(range(S), S // 2))

    def perf(idx):
        a, g, e, bk = apr[idx], gas[idx], eth[idx], np.arange(len(idx))
        out = [(run_t1(a, g, e, bk)[0] / 1e6 - 1) * 100]
        out += [(hold_final(a[:, c]) / 1e6 - 1) * 100 for c in range(6)]
        return np.array(out)
    lam, t1best = [], 0
    for IS in combos:
        iss = set(IS)
        ii = np.concatenate([np.arange(*chunks[i]) for i in IS])
        oo = np.concatenate([np.arange(*chunks[i]) for i in range(S) if i not in iss])
        pi, po = perf(ii), perf(oo); b = int(np.argmax(pi)); t1best += (b == 0)
        rank = min(max((po < po[b]).mean(), 1e-3), 1 - 1e-3)
        lam.append(np.log(rank / (1 - rank)))
    lam = np.array(lam)
    return {"PBO": float((lam <= 0).mean()), "t1_is_best_frac": t1best / len(combos), "n_combos": len(combos)}


def param_plateau(apr, gas, eth, blk, dwells=(250, 500, 1000, 2000, 4000, 8000),
                  alphas=(0.02, 0.05, 0.1, 0.2, 0.4)):
    grid = np.array([[net_apy(run_t1(apr, gas, eth, blk, dwell0=d, alpha=al)[0], len(apr))
                      for d in dwells] for al in alphas])
    return {"grid": grid, "dwells": list(dwells), "alphas": list(alphas),
            "min": float(grid.min()), "max": float(grid.max()), "spread_pp": float(grid.max() - grid.min())}


def gas_sweep(apr, eth, blk, levels=(10, 25, 50, 100, 200)):
    rows = []
    for gw in levels:
        g = np.full(len(apr), float(gw))
        t1f, t1s = run_t1(apr, g, eth, blk); gf, gs = run_greedy(apr, g, eth)
        rows.append({"gwei": gw, "t1_apy": round(net_apy(t1f, len(apr)), 3), "t1_rebal": t1s,
                     "greedy_apy": round(net_apy(gf, len(apr)), 3), "greedy_rebal": gs})
    return pd.DataFrame(rows)


def block_bootstrap(apr, gas, eth, blk, ts, B=10000, block=5, seed=42):
    """Moving-block bootstrap of daily T1-minus-benchmark excess return + N_eff."""
    _, _, eqT1 = run_t1(apr, gas, eth, blk, want_equity=True)
    growth = 1.0 + np.where(np.isnan(apr), 0.0, apr / BPY)
    eqHold = 1e6 * np.cumprod(growth, axis=0)
    day = pd.Series(ts.values).dt.floor("D")
    out = {}
    for name, beq in [("Aave hold", eqHold[:, 0]), ("best hold", eqHold[:, int(np.argmax(eqHold[-1]))])]:
        dd = pd.DataFrame({"day": day.values, "t1": eqT1, "bh": beq}).groupby("day").last()
        ex = np.diff(np.log(dd["t1"].to_numpy())) - np.diff(np.log(dd["bh"].to_numpy()))
        rng = np.random.default_rng(seed); nb = int(np.ceil(len(ex) / block)); sm = len(ex) - block
        means = np.array([ex[(rng.integers(0, sm + 1, nb)[:, None] + np.arange(block)).ravel()[:len(ex)]].mean() for _ in range(B)])
        # effective N
        x = ex - ex.mean(); var = np.dot(x, x) / len(x); tau = 1.0; lag = 0
        for k in range(1, min(len(x) // 4, 60) + 1):
            rho = np.dot(x[:-k], x[k:]) / (len(x) * var); lag = k
            if rho < 0.05: break
            tau += 2 * rho * (1 - k / len(x))
        ci = np.percentile(means, [2.5, 97.5])
        out[name] = {"n_days": len(ex), "mean_bp_day": round(float(ex.mean()) * 1e4, 3),
                     "ci_bp": [round(ci[0] * 1e4, 3), round(ci[1] * 1e4, 3)],
                     "p_le0": round(float((means <= 0).mean()), 4), "n_eff": round(float(len(x) / tau), 1)}
    return out


# Krause-2005 yield-impact: per-protocol IRM kink slope (rate pp per unit utilisation)
IRM_SLOPE = {"aave_v3": 0.04, "compound_v3": 0.05, "spark": 0.04,
             "morpho_blue": 0.06, "euler_v2": 0.05, "fluid": 0.05}


def capacity(panel, sizes=(1e6, 5e6, 2.5e7, 5e7)):
    """T1 net APY vs deposit size under a continuous IRM yield-impact model.

    raw_apy = geometric T1 return across the 6 walk-forward windows (capital
    resets to $1M each window). Depositing P into a pool (TVL, util) costs
    earned rate ~= 1/2 * slope * util * P/(TVL+P); time-weighted across the
    venues T1 actually sits in. net_apy = raw_apy - drag.
    """
    total_blocks = 0; growth = 1.0; proto_blocks = np.zeros(6); n_rebal = 0
    for wid, a, b in WINDOWS:
        apr, gas, eth, blk, _, _, _ = slice_arrays(panel, a, b); n = len(apr)
        sw = []; fin, nsw = run_t1(apr, gas, eth, blk, switch_log=sw)
        growth *= fin / 1e6; total_blocks += n; n_rebal += nsw - 1
        idxs = [i for i, _ in sw] + [n]; vens = [v for _, v in sw]
        for k in range(len(vens)):
            proto_blocks[vens[k]] += idxs[k + 1] - idxs[k]
    raw = (growth ** (1 / (total_blocks / BPY)) - 1) * 100
    share = proto_blocks / total_blocks
    tvl = np.array([panel[f"{p}_tvl_usd"].dropna().mean() for p in PROT])
    util = np.array([panel[f"{p}_utilization"].dropna().mean() for p in PROT])
    slope = np.array([IRM_SLOPE[p] for p in PROT])
    rows = []
    for P in sizes:
        impact_bp = float(np.sum(0.5 * slope * util * P / (tvl + P) * 1e4 * share))
        rows.append({"size_usd": P, "raw_apy": round(raw, 3), "impact_bp": round(impact_bp, 2),
                     "net_apy": round(raw - impact_bp / 100, 3)})
    return raw, n_rebal, pd.DataFrame(rows)


if __name__ == "__main__":
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[2]
    panel = pd.read_parquet(ROOT / "data/cached/per_block_panel.parquet")
    raw, nr, cap = capacity(panel)
    print(f"CAPACITY: T1 raw {raw:.3f}% n_rebal {nr} (macro raw 8.633, n_rebal 1735, net $1M 8.569 / $50M 7.602)")
    print(cap.to_string(index=False))
    apr, gas, eth, blk, _, _, ts = slice_arrays(panel, "2026-01-01", "2026-05-01")
    wf, deltas = walk_forward(panel)
    print("WALK-FORWARD:\n", wf.to_string(index=False))
    print(f"  T1 beats best hold {sum(wf.edge_vs_best_pp>0)}/6 | beats Aave {sum(wf.edge_vs_aave_pp>0)}/6")
    print("\nPAIRED BOOTSTRAP + HOLM:\n", paired_bootstrap_holm(deltas).to_string(index=False))
    rn = random_null(apr, gas, eth, blk)
    print(f"\nRANDOM NULL: T1 ${rn['t1']:,.0f} vs {rn['n']} random (max ${rn['rand_max']:,.0f}) z={rn['z']:.1f} p={rn['p']:.4f}")
    print("FAMILY PBO:", family_pbo(apr, gas, eth, blk))
    pl = param_plateau(apr, gas, eth, blk)
    print(f"PLATEAU: net APY {pl['min']:.3f}-{pl['max']:.3f}% spread {pl['spread_pp']:.3f}pp")
    print("GAS SWEEP:\n", gas_sweep(apr, eth, blk).to_string(index=False))
    print("BLOCK BOOTSTRAP:", block_bootstrap(apr, gas, eth, blk, ts))
