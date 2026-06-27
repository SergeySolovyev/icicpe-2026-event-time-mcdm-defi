"""Self-contained, pure-numpy reproduction core for the Kaggle notebook.

Every decision policy from the paper, reimplemented as a tight scalar loop
over the per-block panel (NO fractal-defi, NO API keys, NO lifelines for the
non-T3 policies). Validated to reproduce results_macros.tex to the dollar:
  B1 Aave hold 3.26% $1,010,605 | B2 Compound 2.69% $1,008,757
  B3 greedy 5.35% 424 | B4 EMA 4.64% 70 | T1 5.37% 322 | T2 5.34% 175
Engine semantics match backtest/replay_per_block.py: accrue current venue's
APR each block (pos*=1+apr/BPY), pay gas (gas_used*gwei*1e-9*eth) on each
switch; cold start = first allocation (one switch). Gas + eth are read PER
BLOCK from the panel (this is what gives \\TOneGasUSD=$68, not constant 25 gwei).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

BPY = 2_628_000          # 365*24*3600 // 12  blocks per year (12s blocks)
GAS_USED = 200_000       # fixed gas units per rebalance (engine default)
PROT = ["aave_v3", "compound_v3", "spark", "morpho_blue", "euler_v2", "fluid"]


def slice_arrays(panel: pd.DataFrame, start: str, end: str, prot=PROT):
    """Return (apr[n,k], gas_gwei[n], eth[n], block[n], util[n,k], tvl[n,k], ts)."""
    p = panel
    if p["block_timestamp"].dt.tz is None:
        p = p.copy(); p["block_timestamp"] = p["block_timestamp"].dt.tz_localize("UTC")
    m = (p["block_timestamp"] >= pd.Timestamp(start, tz="UTC")) & (p["block_timestamp"] < pd.Timestamp(end, tz="UTC"))
    s = p.loc[m].reset_index(drop=True)
    apr = np.column_stack([s[f"{x}_lending_apr"].to_numpy(float) for x in prot])
    util = np.column_stack([s[f"{x}_utilization"].to_numpy(float) for x in prot])
    tvl = np.column_stack([s[f"{x}_tvl_usd"].to_numpy(float) for x in prot])
    gas = s["gas_price_gwei"].to_numpy(float)
    eth = s["eth_usd"].to_numpy(float) if "eth_usd" in s else np.full(len(s), 3500.0)
    blk = s["block_number"].to_numpy(np.int64)
    return apr, gas, eth, blk, util, tvl, s["block_timestamp"]


def gas_cost(gas_gwei, eth, gas_used=GAS_USED):
    return gas_used * gas_gwei * 1e-9 * eth


def hold_final(apr_col, p0=1e6):
    g = 1.0 + np.where(np.isnan(apr_col), 0.0, apr_col / BPY)
    return float(p0 * np.prod(g))


# --------------------------------------------------------------- T1 (validated)
def run_t1(apr, gas_gwei, eth, block, p0=1e6, dwell0=1000.0, alpha=0.1,
           gas_used=GAS_USED, want_equity=False, switch_log=None):
    n, k = apr.shape
    wins = np.nanargmax(apr, axis=1)
    best = apr[np.arange(n), wins]
    cost = gas_used * gas_gwei * 1e-9 * eth
    pos = p0; cur = -1; dwell = float(dwell0); last_win = -1; last_win_blk = -1; nsw = 0
    eq = np.empty(n) if want_equity else None
    for i in range(n):
        if cur >= 0:
            a = apr[i, cur]
            if a == a: pos *= 1.0 + a / BPY
        win = int(wins[i])
        if last_win < 0: last_win, last_win_blk = win, block[i]
        elif win != last_win:
            dwell = alpha * (block[i] - last_win_blk) + (1 - alpha) * dwell
            last_win, last_win_blk = win, block[i]
        if cur < 0:
            pos -= cost[i]; cur = win; nsw += 1
            if switch_log is not None: switch_log.append((i, win))
        elif win != cur:
            if pos * (best[i] - apr[i, cur]) * dwell / BPY > cost[i]:
                pos -= cost[i]; cur = win; nsw += 1
                if switch_log is not None: switch_log.append((i, win))
        if want_equity: eq[i] = pos
    return (pos, nsw, eq) if want_equity else (pos, nsw)


# --------------------------------------------------------------- B1/B2 fixed hold
def run_fixed(apr, gas_gwei, eth, target, p0=1e6, gas_used=GAS_USED, want_equity=False):
    n, k = apr.shape
    cost = gas_used * gas_gwei * 1e-9 * eth
    pos = p0; cur = -1; nsw = 0
    eq = np.empty(n) if want_equity else None
    for i in range(n):
        if cur >= 0:
            a = apr[i, cur]
            if a == a: pos *= 1.0 + a / BPY
        if cur < 0 and apr[i, target] == apr[i, target]:
            pos -= cost[i]; cur = target; nsw += 1
        if want_equity: eq[i] = pos
    return (pos, nsw, eq) if want_equity else (pos, nsw)


# --------------------------------------------------------------- B3 greedy spot
def run_greedy(apr, gas_gwei, eth, p0=1e6, gas_used=GAS_USED, want_equity=False):
    n, k = apr.shape
    wins = np.nanargmax(apr, axis=1)
    cost = gas_used * gas_gwei * 1e-9 * eth
    pos = p0; cur = -1; nsw = 0
    eq = np.empty(n) if want_equity else None
    for i in range(n):
        if cur >= 0:
            a = apr[i, cur]
            if a == a: pos *= 1.0 + a / BPY
        win = int(wins[i])
        if cur < 0:
            pos -= cost[i]; cur = win; nsw += 1
        elif win != cur and apr[i, win] != apr[i, cur]:   # tie-break: hold if equal
            pos -= cost[i]; cur = win; nsw += 1
        if want_equity: eq[i] = pos
    return (pos, nsw, eq) if want_equity else (pos, nsw)


# --------------------------------------------------------------- B4 MCDM-EMA
def run_ema(apr, util, tvl, gas_gwei, eth, p0=1e6, alpha=0.1, thr=0.05,
            gas_used=GAS_USED, want_equity=False):
    n, k = apr.shape
    # EMA-smooth each factor, skip-NaN (matches _update_ema): pandas ewm adjust=False, ignore_na
    def ema(M):
        return pd.DataFrame(M).ewm(alpha=alpha, adjust=False, ignore_na=True).mean().to_numpy()
    aE, uE, tE = ema(apr), ema(util), ema(tvl)
    # per-block scores, fully vectorised; NaN-apr venues -> -inf (never argmax)
    valid = ~np.isnan(aE)
    with np.errstate(invalid="ignore"):
        ma = np.nanmax(np.where(valid, aE, np.nan), axis=1, keepdims=True)
        mu = np.nanmax(np.where(valid, uE, np.nan), axis=1, keepdims=True)
        mt = np.nanmax(np.where(valid, tE, np.nan), axis=1, keepdims=True)
    ma = np.where((ma == 0) | np.isnan(ma), 1.0, ma)
    mu = np.where((mu == 0) | np.isnan(mu), 1.0, mu)
    mt = np.where((mt == 0) | np.isnan(mt), 1.0, mt)
    f_apy = np.where(valid, aE / ma, -np.inf)
    f_risk = np.where(valid, 1 - uE / mu, 0.0)
    f_stab = np.where(valid, tE / mt, 0.0)
    scores = 0.40 * f_apy + 0.25 * f_risk + 0.20 * 1.0 + 0.15 * f_stab
    cost = gas_used * gas_gwei * 1e-9 * eth
    pos = p0; cur = -1; nsw = 0
    eq = np.empty(n) if want_equity else None
    for i in range(n):
        if cur >= 0:
            a = apr[i, cur]
            if a == a: pos *= 1.0 + a / BPY
        best = int(np.argmax(scores[i]))
        if cur < 0:
            pos -= cost[i]; cur = best; nsw += 1
        elif best != cur and (scores[i, best] - scores[i, cur]) > thr:
            pos -= cost[i]; cur = best; nsw += 1
        if want_equity: eq[i] = pos
    return (pos, nsw, eq) if want_equity else (pos, nsw)


# --------------------------------------------------------------- OU MLE + T2
def ou_fit(S):
    S = np.asarray(S, float)
    Sl, Sn = S[:-1], S[1:]
    slb, snb = Sl.mean(), Sn.mean()
    Sxx = np.sum((Sl - slb) ** 2); Sxy = np.sum((Sl - slb) * (Sn - snb))
    if Sxx < 1e-12:
        return 0.0, float(slb), 0.0
    b = Sxy / Sxx; a = snb - b * slb; se2 = np.mean((Sn - a - b * Sl) ** 2)
    if b >= 1 - 1e-9:
        return 0.0, float(Sn.mean()), float(np.sqrt(max(se2, 0.0)))
    kappa = -np.log(max(abs(b), 1e-9)) if b <= 0 else -np.log(b)
    theta = a / (1 - b); denom = 1 - b * b
    sigma = np.sqrt(max(se2 * 2 * kappa / denom, 0.0)) if denom > 0 else 0.0
    return float(kappa), float(theta), float(sigma)


def run_t2(apr, gas_gwei, eth, block, p0=1e6, recalibrate_every=5000, window=5000,
           kappa0=1e-5, theta0=0.0, sigma0=0.001, dwell0=1000.0, alpha=0.1,
           gas_used=GAS_USED, want_equity=False):
    n, k = apr.shape
    wins = np.nanargmax(apr, axis=1); best = apr[np.arange(n), wins]
    sa = np.sort(np.where(np.isnan(apr), -np.inf, apr), axis=1)   # ascending
    spread_top2 = sa[:, -1] - sa[:, -2]                            # top - runner-up
    cost = gas_used * gas_gwei * 1e-9 * eth
    pos = p0; cur = -1; nsw = 0
    kappa, theta, sigma = kappa0, theta0, sigma0
    from collections import deque
    buf = deque(maxlen=window); since = 0          # O(1) ring buffer (was list.pop(0))
    dwell = float(dwell0); last_win = -1; last_win_blk = -1
    KAPPA_FLOOR = 1e-6
    eq = np.empty(n) if want_equity else None
    for i in range(n):
        if cur >= 0:
            a = apr[i, cur]
            if a == a: pos *= 1.0 + a / BPY
        s2 = spread_top2[i]
        if np.isfinite(s2):
            buf.append(s2); since += 1
        if since >= recalibrate_every and len(buf) >= 50:
            kappa, theta, sigma = ou_fit(np.fromiter(buf, float)); since = 0
        win = int(wins[i])
        if last_win < 0: last_win, last_win_blk = win, block[i]
        elif win != last_win:
            dwell = alpha * (block[i] - last_win_blk) + (1 - alpha) * dwell
            last_win, last_win_blk = win, block[i]
        if cur < 0:
            pos -= cost[i]; cur = win; nsw += 1
        elif win != cur:
            spread = best[i] - apr[i, cur]
            if kappa <= KAPPA_FLOOR or not np.isfinite(s2):   # fallback to T1 rule
                if pos * spread * dwell / BPY > cost[i]:
                    pos -= cost[i]; cur = win; nsw += 1
            else:
                Sstar = theta + sigma * np.sqrt((cost[i] / pos) / (kappa * 1.0))
                if spread > Sstar:
                    pos -= cost[i]; cur = win; nsw += 1
        if want_equity: eq[i] = pos
    return (pos, nsw, eq) if want_equity else (pos, nsw)


def net_apy(final, n, p0=1e6):
    return ((final / p0) ** (1 / max(n / BPY, 1e-9)) - 1) * 100


if __name__ == "__main__":
    import sys
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[2]
    panel = pd.read_parquet(ROOT / "data/cached/per_block_panel.parquet")
    apr, gas, eth, blk, util, tvl, ts = slice_arrays(panel, "2026-01-01", "2026-05-01")
    n = len(apr)
    print(f"test window: {n:,} blocks  {ts.iloc[0]}..{ts.iloc[-1]}")
    rows = []
    f, s = run_fixed(apr, gas, eth, PROT.index("aave_v3")); rows.append(("B1 always_aave", f, s))
    f, s = run_fixed(apr, gas, eth, PROT.index("compound_v3")); rows.append(("B2 always_compound", f, s))
    f, s = run_greedy(apr, gas, eth); rows.append(("B3 greedy_spot", f, s))
    f, s = run_ema(apr, util, tvl, gas, eth); rows.append(("B4 mcdm_ema", f, s))
    f, s = run_t1(apr, gas, eth, blk); rows.append(("T1 threshold", f, s))
    f, s = run_t2(apr, gas, eth, blk); rows.append(("T2 optimal_stopping", f, s))
    print(f"\n{'policy':22}{'net APY':>9}{'rebal':>7}{'final $':>14}   macro")
    macro = {"B1 always_aave": "3.26% / $1,010,605", "B2 always_compound": "2.69% / $1,008,757",
             "B3 greedy_spot": "5.35% 424 / $1,017,293", "B4 mcdm_ema": "4.64% 70 / $1,015,028",
             "T1 threshold": "5.37% 322 / $1,017,341", "T2 optimal_stopping": "5.34% 175 / $1,017,242"}
    for name, f, s in rows:
        print(f"{name:22}{net_apy(f,n):8.2f}%{s:7d}{f:14,.0f}   [{macro[name]}]")
