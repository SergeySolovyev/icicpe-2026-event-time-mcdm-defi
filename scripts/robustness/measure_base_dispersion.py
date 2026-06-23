"""Is there 'fuel' for a USDC allocator on Base (L2)?

Question from the L2 discussion: cheaper gas lets the agent switch more often,
but the EDGE is the cross-venue spread, not the gas. If Base's USDC lending
venues all pay ~the same rate, an L2 agent would just 'trade for the sake of
trading'. So before building an L2 version, MEASURE the dispersion.

Data: DeFiLlama yields API (free, no key) -- daily historical supply APY
(apyBase) for the largest Base USDC pool of each venue. We align on a daily
grid and quantify:
  - per-venue mean APY and the daily cross-sectional spread (max-min)
  - leadership turnover (how often the best-paying venue changes)
  - the GROSS edge of always sitting in the daily-max venue vs holding the
    best single venue (the dispersion 'fuel ceiling', before costs)
  - the NET edge after L2 gas, at $100 / $10k / $1M and two L2 fee levels
    -> the honest 'does it pay at this size on Base' answer.

Reproducible: python scripts/robustness/measure_base_dispersion.py
Writes results/figures/robustness/base_dispersion.json.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "figures" / "robustness"
LLAMA = "https://yields.llama.fi"
CHAIN = "Base"
# Comparable Base variable-rate USDC lending markets (analogues of the mainnet
# 6-way set). DeFiLlama slugs: 'moonwell-lending', 'fluid-lending'. Euler V2 Base
# is excluded (apyBase 0 -> dormant USDC market). Leverage/vault/RWA pools
# (avantis, harvest, yo, centrifuge, yearn...) are NOT spot lending -> excluded.
WANT = [("aave-v3", "USDC"), ("compound-v3", "USDC"),
        ("fluid-lending", "USDC"), ("moonwell-lending", "USDC")]


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "research/1.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def main() -> int:
    print("[fetch] DeFiLlama /pools ...", flush=True)
    pools = _get(f"{LLAMA}/pools")["data"]
    found = {}
    for proj, sym in WANT:
        cands = [p for p in pools if p.get("chain") == CHAIN
                 and p.get("project") == proj and p.get("symbol") == sym]
        cands.sort(key=lambda p: -(p.get("tvlUsd") or 0))
        if cands:
            c = cands[0]
            found[proj] = c
            print(f"   {proj:13} {sym}: pool={c['pool']}  TVL=${(c.get('tvlUsd') or 0)/1e6:6.1f}M  "
                  f"apyBase_now={c.get('apyBase')}", flush=True)
        else:
            print(f"   {proj:13} {sym}: NOT FOUND on {CHAIN}", flush=True)
    if len(found) < 2:
        print("[abort] need >=2 venues"); return 1

    # historical daily apyBase per venue
    series = {}
    for proj, p in found.items():
        d = _get(f"{LLAMA}/chart/{p['pool']}")["data"]
        s = pd.Series({pd.to_datetime(x["timestamp"]).floor("D"): x.get("apyBase")
                       for x in d if x.get("apyBase") is not None})
        s = s[~s.index.duplicated(keep="last")]
        series[proj] = s
        print(f"   [chart] {proj:13} {len(s)} days  {s.index.min().date()}..{s.index.max().date()}", flush=True)
    df = pd.DataFrame(series).dropna()
    venues = list(df.columns)
    n = len(df)
    print(f"\n[align] {n} overlapping days across {venues}  "
          f"({df.index.min().date()}..{df.index.max().date()})", flush=True)

    # ---- dispersion ----
    daily_spread = (df.max(axis=1) - df.min(axis=1))           # pp/yr, cross-sectional
    leader = df.idxmax(axis=1)
    crossovers = int((leader != leader.shift()).sum())
    lead_share = (leader.value_counts() / n * 100).round(1).to_dict()
    mean_apy = df.mean().round(3).to_dict()

    # ---- gross fuel ceiling: always-daily-max vs best single hold (no gas) ----
    g_daily = 1.0 + df.values / 100.0 / 365.0
    grow_max = float(np.prod(df.max(axis=1).values / 100.0 / 365.0 + 1.0))
    grow_hold = {v: float(np.prod(g_daily[:, i])) for i, v in enumerate(venues)}
    best_hold_v = max(grow_hold, key=grow_hold.get)
    yrs = n / 365.0
    apy_max = (grow_max ** (1 / yrs) - 1) * 100
    apy_besthold = (grow_hold[best_hold_v] ** (1 / yrs) - 1) * 100
    gross_edge_pp = apy_max - apy_besthold

    # ---- net of L2 gas, by capital and fee level (charge gas at each leader change) ----
    net = {}
    for p0 in (100, 10_000, 1_000_000):
        net[p0] = {}
        for gas in (0.15, 0.03):
            final_max = p0 * grow_max - gas * crossovers
            final_hold = p0 * grow_hold[best_hold_v]
            edge_usd = final_max - final_hold
            edge_apy_pp = ((final_max / p0) ** (1 / yrs) - 1) * 100 - apy_besthold
            net[p0][f"gas_{gas}"] = {"net_edge_usd_vs_besthold": round(edge_usd, 2),
                                     "net_edge_pp": round(edge_apy_pp, 3),
                                     "pays_off": bool(edge_usd > 0)}

    summary = {
        "source": "DeFiLlama yields API (apyBase, daily)", "chain": CHAIN,
        "venues": {v: {"pool": found[v]["pool"], "tvl_usd_m": round((found[v].get("tvlUsd") or 0)/1e6, 1)} for v in venues},
        "window": f"{df.index.min().date()}..{df.index.max().date()}", "n_days": n,
        "mean_apy_pct": mean_apy,
        "daily_spread_pp": {"median": round(float(daily_spread.median()), 3),
                            "p90": round(float(daily_spread.quantile(0.9)), 3),
                            "max": round(float(daily_spread.max()), 3)},
        "leader_share_pct": lead_share, "n_crossovers": crossovers,
        "crossovers_per_month": round(crossovers / (n / 30.0), 2),
        "gross_fuel_ceiling": {"always_daily_max_apy": round(apy_max, 3),
                               "best_single_hold": best_hold_v,
                               "best_single_hold_apy": round(apy_besthold, 3),
                               "gross_edge_pp": round(gross_edge_pp, 3)},
        "net_of_l2_gas": net,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "base_dispersion.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # ---- report ----
    print("\n================ BASE USDC DISPERSION ================")
    print(f"venues: {', '.join(f'{v} (${summary['venues'][v]['tvl_usd_m']}M)' for v in venues)}")
    print(f"mean APY: " + ", ".join(f"{v} {mean_apy[v]:.2f}%" for v in venues))
    print(f"daily cross-venue spread (max-min): median {daily_spread.median():.2f}pp, "
          f"p90 {daily_spread.quantile(0.9):.2f}pp, max {daily_spread.max():.2f}pp")
    print(f"leader share: " + ", ".join(f"{k} {v}%" for k, v in lead_share.items()))
    print(f"leadership crossovers: {crossovers} over {n} days = {summary['crossovers_per_month']}/month")
    print(f"\nGROSS fuel ceiling (no gas): always-daily-max {apy_max:.2f}% vs best hold "
          f"{best_hold_v} {apy_besthold:.2f}%  ->  +{gross_edge_pp:.2f}pp")
    print("\nNET of L2 gas (vs best single hold):")
    for p0 in (100, 10_000, 1_000_000):
        row = " | ".join(f"gas ${g.split('_')[1]}: {'+' if net[p0][g]['net_edge_usd_vs_besthold']>=0 else ''}"
                         f"${net[p0][g]['net_edge_usd_vs_besthold']:.2f} "
                         f"({net[p0][g]['net_edge_pp']:+.2f}pp) {'PAYS' if net[p0][g]['pays_off'] else 'no'}"
                         for g in ("gas_0.15", "gas_0.03"))
        print(f"  ${p0:>9,}: {row}")
    print(f"\n[ok] wrote {OUT/'base_dispersion.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
