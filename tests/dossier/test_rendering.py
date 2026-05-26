"""Rendering tests: templates produce valid markdown without unrendered Jinja."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture
def fake_tables(tmp_path):
    td = tmp_path / "tables"
    td.mkdir()
    pd.DataFrame({
        "policy": ["b1_always_aave", "t1_threshold"],
        "net_apy_pct": [3.26, 4.60], "sharpe": [1.0, 5.0],
        "sortino": [1.5, 7.0], "calmar": [100, 500],
        "information_ratio_vs_benchmark": [0, 5.05],
        "max_drawdown_pct": [0, -0.005], "max_drawdown_duration_days": [0, 2],
        "time_to_recovery_days": [0, 5],
        "cvar_95_pct": [-0.1, -0.15], "cvar_99_pct": [-0.2, -0.25],
        "skew": [0, 0], "kurtosis_excess": [3, 3],
        "final_equity_usd": [1_010_605, 1_014_880],
    }).to_csv(td / "institutional_metrics.csv", index=False)
    pd.DataFrame({
        "window_id": ["W1", "W2", "W3", "W4", "W5", "W6"],
        "policy": ["t1_threshold"] * 6,
        "sharpe": [4.5, 5.1, 3.2, 4.8, 5.5, 5.0],
        "net_apy_pct": [4.5, 5.0, 3.0, 4.2, 5.1, 4.6],
        "max_drawdown_pct": [-0.01] * 6, "n_rebalances": [10] * 6,
    }).to_csv(td / "walk_forward.csv", index=False)
    pd.DataFrame({
        "position_size_usd": [1e5, 1e6, 5e6, 2.5e7, 5e7],
        "policy": ["t1_threshold"] * 5,
        "net_apy_pct": [4.60, 4.60, 4.55, 4.27, 3.75],
        "slippage_bp_avg": [0.01, 0.1, 0.5, 2.5, 5.0],
        "raw_apy_pct": [4.60, 4.60, 4.60, 4.60, 4.60],
        "slippage_drag_pct": [0.0, 0.0, 0.05, 0.33, 0.85],
        "n_rebalances": [39, 39, 39, 39, 39],
    }).to_csv(td / "capacity_curve.csv", index=False)
    # also seed B1 in capacity for the diff column
    cap_extra = pd.DataFrame({
        "position_size_usd": [1e5, 1e6, 5e6, 2.5e7, 5e7],
        "policy": ["b1_always_aave"] * 5,
        "net_apy_pct": [3.26] * 5,
        "slippage_bp_avg": [0.0] * 5,
        "raw_apy_pct": [3.26] * 5,
        "slippage_drag_pct": [0.0] * 5,
        "n_rebalances": [0] * 5,
    })
    cap_old = pd.read_csv(td / "capacity_curve.csv")
    pd.concat([cap_old, cap_extra], ignore_index=True).to_csv(
        td / "capacity_curve.csv", index=False)
    pd.DataFrame({
        "policy": ["t1_threshold"] * 4,
        "position_size_usd": [1e6] * 4,
        "net_apy_pct": [4.60] * 4,
        "raw_apy_pct": [4.60] * 4,
        "mev_bp": [0.0, 5.0, 15.0, 30.0],
        "n_rebalances": [39] * 4,
        "mev_drag_pct": [0.0, 0.5, 1.5, 3.0],
        "net_apy_post_mev_pct": [4.60, 4.10, 3.10, 1.60],
    }).to_csv(td / "cost_attribution.csv", index=False)
    return td


def test_render_produces_all_8_chapters(tmp_path, fake_tables):
    from scripts.dossier.render_dossier import render_all
    out = tmp_path / "docs_institutional"
    render_all(tables_dir=fake_tables, out_dir=out)
    expected = ["00_one_pager.md", "01_performance_dossier.md",
                "02_walk_forward_robustness.md", "03_capacity_analysis.md",
                "04_cost_attribution.md", "05_risk_register.md",
                "06_operational_runbook.md", "07_live_trial_plan.md"]
    for name in expected:
        p = out / name
        assert p.exists(), f"missing {name}"
        content = p.read_text(encoding="utf-8")
        assert "{{" not in content, f"unrendered Jinja in {name}: {content[:200]}"
        assert "{%" not in content, f"unrendered Jinja block in {name}"
