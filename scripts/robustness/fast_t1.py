"""Fast, dependency-light reimplementation of the T1 policy + passive hold.

The production EventReplayEngine builds a BlockState object per block (864k
rows) -- correct but ~5-7 min per run, too slow for the hundreds of runs a
parameter heatmap / permutation-null / PBO study needs. This module runs the
IDENTICAL T1 decision logic in a tight numpy loop (no per-row objects), ~100x
faster, and is validated to reproduce the engine's headline (5.368% net APY,
322 switches, final $1,017,341 on the real-gas test window) to the dollar.

T1 logic (matches decision/t1_threshold.py + replay_per_block.py):
  - accrue current protocol's APR per block (skip NaN), THEN decide
  - dwell = EWMA of inter-crossover block-gaps (state)
  - switch to argmax-APR venue iff position*spread*dwell/BPY > gas_cost_usd
  - gas_cost_usd = gas_used * gas_price_gwei * 1e-9 * eth_price
"""
from __future__ import annotations

import numpy as np

BPY = 365 * 24 * 60 * 60 // 12  # 2,628,000 blocks/yr


def run_t1(apr, gas_gwei, eth, block, p0=1_000_000.0,
           dwell0=1000.0, alpha=0.1, gas_used=200_000, want_equity=False,
           switch_log=None):
    """apr: (n,k) per-block APR (fraction, NaN allowed). Returns (final, n_switches[, equity]).

    If ``switch_log`` is a list, each switch appends ``(block_index, target_venue)``
    in chronological order -- used by the random-destination null exhibit to reuse
    T1's exact switch *cadence* while randomising the *destination*.
    """
    n, k = apr.shape
    # Vectorize the per-row argmax + best-APR (the slow part) outside the loop.
    wins = np.nanargmax(apr, axis=1)
    best = apr[np.arange(n), wins]
    cost_blk = gas_used * gas_gwei * 1e-9 * eth   # gas $ per switch at each block
    pos = p0
    cur = -1
    dwell = float(dwell0)
    last_win = -1
    last_win_blk = -1
    n_sw = 0
    eq = np.empty(n) if want_equity else None
    for i in range(n):
        if cur >= 0:
            a = apr[i, cur]
            if a == a:  # not NaN
                pos *= 1.0 + a / BPY
        win = int(wins[i])
        if last_win < 0:
            last_win, last_win_blk = win, block[i]
        elif win != last_win:
            dwell = alpha * (block[i] - last_win_blk) + (1.0 - alpha) * dwell
            last_win, last_win_blk = win, block[i]
        if cur < 0:
            pos -= cost_blk[i]
            cur = win
            n_sw += 1
            if switch_log is not None:
                switch_log.append((i, win))
        elif win != cur:
            exp_extra = pos * (best[i] - apr[i, cur]) * dwell / BPY
            if exp_extra > cost_blk[i]:
                pos -= cost_blk[i]
                cur = win
                n_sw += 1
                if switch_log is not None:
                    switch_log.append((i, win))
        if want_equity:
            eq[i] = pos
    return (pos, n_sw, eq) if want_equity else (pos, n_sw)


def hold_final(apr_col, p0=1_000_000.0):
    """Passive buy-and-hold final equity (geometric, NaN-safe)."""
    g = 1.0 + np.where(np.isnan(apr_col), 0.0, apr_col / BPY)
    return float(p0 * np.prod(g))
