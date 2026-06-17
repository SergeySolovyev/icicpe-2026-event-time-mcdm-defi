"""Tests for the O1 Yield-Drag Analyst agent-operation.

The O1 report is the shippable product wedge; its 5 numeric quality gates
are load-bearing safety logic (a loosened gate would emit an untrusted
report). These tests pin the gate behaviour + the drag arithmetic on a
small synthetic panel (no real parquet, no network), so the suite runs in
CI and a regression in the gates or the accounting fails loudly.
"""
from __future__ import annotations

import pandas as pd
import pytest

from product.yield_drag.yield_drag_report import (
    analyze, render_report, YieldDragResult, PROTOCOLS,
)


def _synthetic_panel(n: int = 3000) -> pd.DataFrame:
    """A per-block panel where Euler spikes to 9% in the second half, so an
    active allocator starting in Aave (flat 3%) provably beats passive-hold.
    """
    ts = pd.date_range("2026-01-05", periods=n, freq="12s", tz="UTC")
    cols = {
        "block_number": range(n),
        "block_timestamp": ts,
        "gas_price_gwei": 0.3,
        "eth_usd": 3500.0,
    }
    half = n // 2
    for p in PROTOCOLS:
        if p == "aave_v3":
            apr = [0.03] * n
        elif p == "euler_v2":
            apr = [0.03] * half + [0.09] * (n - half)  # spike: switching pays
        else:
            apr = [0.02] * n  # never the argmax
        cols[f"{p}_lending_apr"] = apr
        cols[f"{p}_utilization"] = 0.85
        cols[f"{p}_tvl_usd"] = 1e9
    return pd.DataFrame(cols)


def test_active_beats_passive_and_gates_pass():
    r = analyze(1_000_000, "aave_v3", start="2026-01-01", end="2026-02-01",
                panel=_synthetic_panel())
    assert isinstance(r, YieldDragResult)
    assert r.quality_gates_passed is True
    # Euler's 9% second-half spike must lift the active allocator above a
    # passive Aave hold, and the drag (active - passive) is strictly positive.
    assert r.active_net_apy_pct > r.passive_net_apy_pct
    assert r.drag_usd_over_window > 0
    assert r.drag_bp_annualized > 0
    # Passive Aave earns ~3% over the window (geometric annualization).
    assert 2.5 < r.passive_net_apy_pct < 3.6
    assert r.n_blocks == 3000
    assert len(r.panel_sha256_12) == 12
    # The allocator must end up spending time in Euler (the spike venue).
    assert "Euler V2" in r.active_time_share


def test_time_share_reconciles_to_100():
    r = analyze(5_000_000, "aave_v3", start="2026-01-01", end="2026-02-01",
                panel=_synthetic_panel())
    assert abs(sum(r.active_time_share.values()) - 100.0) < 1.0


def test_invalid_protocol_raises():
    with pytest.raises(ValueError):
        analyze(1_000_000, "not_a_protocol", panel=_synthetic_panel())


def test_window_too_short_raises():
    with pytest.raises(ValueError):
        analyze(1_000_000, "aave_v3", start="2026-01-01", end="2026-02-01",
                panel=_synthetic_panel(n=500))  # < 1000-block floor


def test_render_report_has_headline_and_caveats():
    r = analyze(1_000_000, "aave_v3", start="2026-01-01", end="2026-02-01",
                panel=_synthetic_panel())
    md = render_report(r)
    assert "Yield-Drag Report" in md
    assert "Aave V3" in md
    assert f"${r.drag_usd_over_window:,.0f}" in md
    assert "NOT SENT" in md                 # human-approval gate notice
    assert "GROSS of MEV/slippage" in md    # honest caveat preserved
    assert "Size haircut" in md             # critic fix: size-haircut table
    assert "auto-router" in md              # critic fix: auto-router benchmark
    assert "published NEGATIVE" in md       # critic fix: ML separated from rule's 6/6


def test_size_haircut_and_gas_curve_present():
    r = analyze(1_000_000, "aave_v3", start="2026-01-01", end="2026-02-01",
                panel=_synthetic_panel())
    # size haircut: 3 sizes, monotonically larger slippage with size
    assert [row["size_usd"] for row in r.size_haircut] == [500_000.0, 2_000_000.0, 5_000_000.0]
    slips = [row["slippage_bp"] for row in r.size_haircut]
    assert slips[0] <= slips[1] <= slips[2]          # bigger size -> more slippage
    # gas curve comes from the committed sweep CSV (T1 vs greedy auto-router)
    assert len(r.gas_curve) >= 3
    assert all("t1_net_apy_pct" in row and "autorouter_net_apy_pct" in row
               for row in r.gas_curve)
    assert r.realized_gas_gwei > 0
