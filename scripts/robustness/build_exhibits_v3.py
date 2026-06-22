"""Two physicist-grade additions the red-team flagged as the highest-value gaps.

The skeptic's two sharpest, currently-unanswered questions:
  1. "Your p<1e-4 resamples 6 autocorrelated window means as if IID. What is your
     EFFECTIVE N, and did you account for serial correlation?"
  2. "You ran ~18 contrasts. Of course one looks good -- show me a real
     multiple-testing correction, not a prose claim."

This script answers both with computed numbers (no prose hand-waving):

  G1. MOVING-BLOCK BOOTSTRAP on the daily T1-minus-benchmark excess-return series
      (block length preserves within-day/week autocorrelation), plus an explicit
      autocorrelation-adjusted effective sample size N_eff. This is the honest
      serial-correlation-aware CI a quant expects.
  G2. HOLM family-wise correction actually run over the 6 paired-bootstrap
      one-sided p-values (T1 vs each venue), turning the paper's prose claim into
      a verifiable artifact.

Writes results/figures/robustness/robustness_v3.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "robustness"))
from fast_t1 import run_t1, BPY  # noqa: E402

PROT = ["aave_v3", "compound_v3", "spark", "morpho_blue", "euler_v2", "fluid"]
PRETTY = ["Aave V3", "Compound V3", "Spark", "Morpho Blue", "Euler V2", "Fluid"]
OUT = ROOT / "results" / "figures" / "robustness"
WIN = ("2026-01-01", "2026-05-01")


def holm(pvals, names, alpha=0.05):
    """Holm-Bonferroni step-down. Returns adjusted p-values + survivors."""
    m = len(pvals)
    order = np.argsort(pvals)
    adj = np.empty(m)
    running = 0.0
    for rank, idx in enumerate(order):
        v = (m - rank) * pvals[idx]
        running = max(running, v)        # enforce monotone non-decreasing
        adj[idx] = min(running, 1.0)
    return [{"name": names[i], "p_raw": round(float(pvals[i]), 5),
             "p_holm": round(float(adj[i]), 5), "survives_0.05": bool(adj[i] <= alpha)}
            for i in range(m)]


def moving_block_bootstrap(x, B=10000, block=5, seed=42):
    """Mean of x via moving-block bootstrap (preserves serial correlation)."""
    rng = np.random.default_rng(seed)
    n = len(x)
    nblocks = int(np.ceil(n / block))
    starts_max = n - block
    means = np.empty(B)
    for b in range(B):
        starts = rng.integers(0, starts_max + 1, size=nblocks)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n]
        means[b] = x[idx].mean()
    return means


def effective_n(x, max_lag=None):
    """N_eff = N / (1 + 2*sum rho_k), integrated-autocorrelation-time style."""
    n = len(x)
    x = x - x.mean()
    var = np.dot(x, x) / n
    if var == 0:
        return float(n), 0
    max_lag = max_lag or min(n // 4, 60)
    tau = 1.0
    for k in range(1, max_lag + 1):
        rho = np.dot(x[:-k], x[k:]) / (n * var)
        if rho < 0.05:           # truncate at first small/insignificant lag
            break
        tau += 2.0 * rho * (1 - k / n)
    return float(n / tau), k


def main() -> int:
    print("[load] panel...", flush=True)
    p = pd.read_parquet(ROOT / "data/cached/per_block_panel.parquet")
    p["block_timestamp"] = pd.to_datetime(p["block_timestamp"], utc=True)
    s = p[(p.block_timestamp >= WIN[0]) & (p.block_timestamp < WIN[1])].reset_index(drop=True)
    apr = np.column_stack([s[f"{x}_lending_apr"].to_numpy() for x in PROT])
    gas = s["gas_price_gwei"].to_numpy()
    eth = s["eth_usd"].to_numpy() if "eth_usd" in s else np.full(len(s), 3500.0)
    blk = s["block_number"].to_numpy()
    summary = {"window": f"{WIN[0]}..{WIN[1]}"}

    # ---------- G1. MOVING-BLOCK BOOTSTRAP + effective N ----------
    print("[G1] moving-block bootstrap on daily excess returns...", flush=True)
    fin, nsw, eqT1 = run_t1(apr, gas, eth, blk, want_equity=True)
    growth = 1.0 + np.where(np.isnan(apr), 0.0, apr / BPY)
    eqHold = 1e6 * np.cumprod(growth, axis=0)        # per-block equity of each passive hold
    day = s["block_timestamp"].dt.floor("D")
    res = {}
    for bench_name, bench_eq in [("Aave V3 hold", eqHold[:, 0]),
                                 ("best single hold", eqHold[:, int(np.argmax(eqHold[-1]))])]:
        df = pd.DataFrame({"day": day.values, "t1": eqT1, "bh": bench_eq})
        dd = df.groupby("day").last()
        rT1 = np.diff(np.log(dd["t1"].to_numpy()))
        rBH = np.diff(np.log(dd["bh"].to_numpy()))
        excess = rT1 - rBH                            # daily log excess return
        boot = moving_block_bootstrap(excess, B=10000, block=5)
        neff, lag = effective_n(excess)
        ci = np.percentile(boot, [2.5, 97.5])
        res[bench_name] = {
            "n_days": int(len(excess)),
            "mean_daily_excess_bp": round(float(excess.mean()) * 1e4, 3),
            "annualised_excess_pp": round(float(excess.mean()) * 365 * 100, 3),
            "block_boot_ci_daily_bp": [round(ci[0] * 1e4, 3), round(ci[1] * 1e4, 3)],
            "block_boot_p_le0": round(float((boot <= 0).mean()), 4),
            "effective_n": round(neff, 1), "autocorr_trunc_lag": int(lag),
            "frac_days_positive": round(float((excess > 0).mean()), 3)}
        print(f"   vs {bench_name}: {len(excess)}d, mean +{excess.mean()*1e4:.2f}bp/day, "
              f"block-boot 95% CI [{ci[0]*1e4:.2f},{ci[1]*1e4:.2f}]bp, p(<=0)={(boot<=0).mean():.4f}, "
              f"N_eff={neff:.0f} (lag {lag})", flush=True)
    summary["G1_block_bootstrap"] = res

    # ---------- G2. HOLM on the 6 paired-bootstrap p-values ----------
    print("[G2] Holm correction on T1-vs-each-venue paired bootstrap...", flush=True)
    pb = pd.read_csv(ROOT / "results/institutional/tables/walk_forward_paired_bootstrap_all.csv")
    pvals = pb["p_one_sided_le0"].to_numpy().astype(float)
    names = [c.replace("T1 vs ", "").replace(" hold", "") for c in pb["contrast"]]
    h = holm(pvals, names)
    n_surv = sum(r["survives_0.05"] for r in h)
    summary["G2_holm"] = {"n_tests": len(h), "n_survive_0.05": n_surv, "rows": h}
    for r in h:
        print(f"   {r['name']:<14} p_raw={r['p_raw']:.4f} -> p_holm={r['p_holm']:.4f} "
              f"{'OK' if r['survives_0.05'] else 'n.s.'}", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "robustness_v3.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n[ok] wrote {OUT}/robustness_v3.json", flush=True)
    print(json.dumps({"G2_holm_survive": f"{n_surv}/{len(h)}"}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
