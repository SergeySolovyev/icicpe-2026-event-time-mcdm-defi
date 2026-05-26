"""CLI: tables CSVs + Jinja templates -> 8 Markdown chapters in
docs/institutional/.

Idempotent. The walk-forward chapter renders a placeholder when
walk_forward.csv hasn't been produced yet (24-cell replay is slow)."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from jinja2 import Environment, FileSystemLoader


ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = Path(__file__).resolve().parent / "templates"


def _load_metric_row(metrics: pd.DataFrame, policy: str) -> pd.Series:
    if policy not in metrics["policy"].values:
        raise RuntimeError(f"metrics CSV missing policy row: {policy}")
    return metrics.set_index("policy").loc[policy]


def _wf_t1_vs_b1(walk: pd.DataFrame):
    """Return (wf_directional, wf_mean, wf_p, mean_boots_or_None, n).

    Computes paired bootstrap over per-window (T1 - B1) Sharpe deltas.
    Returns five Nones if walk_forward.csv is empty or missing
    required policies."""
    if walk.empty:
        return 0, 0.0, 1.0, None, 0
    pivot = walk.pivot_table(
        index="window_id", columns="policy",
        values="sharpe", aggfunc="first",
    )
    if "t1_threshold" not in pivot.columns or "b1_always_aave" not in pivot.columns:
        return 0, 0.0, 1.0, None, 0
    delta = (pivot["t1_threshold"] - pivot["b1_always_aave"]).dropna()
    n = len(delta)
    if n == 0:
        return 0, 0.0, 1.0, None, 0
    rng = np.random.default_rng(42)
    d = delta.to_numpy()
    boots = np.empty(2000)
    for i in range(2000):
        idx = rng.integers(0, n, size=n)
        boots[i] = d[idx].mean()
    return (
        int((delta > 0).sum()),
        float(delta.mean()),
        float((boots <= 0).mean()),
        boots,
        n,
    )


def render_all(*, tables_dir: Path, out_dir: Path) -> None:
    tables_dir = Path(tables_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        trim_blocks=True, lstrip_blocks=True, autoescape=False,
    )

    metrics = pd.read_csv(tables_dir / "institutional_metrics.csv")
    walk_path = tables_dir / "walk_forward.csv"
    walk = pd.read_csv(walk_path) if walk_path.exists() else pd.DataFrame()
    cap = pd.read_csv(tables_dir / "capacity_curve.csv")
    cost = pd.read_csv(tables_dir / "cost_attribution.csv")

    t1 = _load_metric_row(metrics, "t1_threshold")
    b1 = _load_metric_row(metrics, "b1_always_aave")

    wf_directional, wf_mean, wf_p, mean_boots, wf_n = _wf_t1_vs_b1(walk)

    # 00 one-pager
    tpl = env.get_template("00_one_pager.md.j2")
    (out_dir / "00_one_pager.md").write_text(tpl.render(
        t1_apy=round(t1.net_apy_pct, 2), b1_apy=round(b1.net_apy_pct, 2),
        t1_sharpe=round(t1.sharpe, 2), b1_sharpe=round(b1.sharpe, 2),
        t1_sortino="∞" if not np.isfinite(t1.sortino) else round(t1.sortino, 2),
        b1_sortino="∞" if not np.isfinite(b1.sortino) else round(b1.sortino, 2),
        t1_calmar="∞" if not np.isfinite(t1.calmar) else int(t1.calmar),
        b1_calmar="∞" if not np.isfinite(b1.calmar) else int(b1.calmar),
        t1_mdd=round(t1.max_drawdown_pct, 3), b1_mdd=round(b1.max_drawdown_pct, 3),
        t1_ir=round(t1.information_ratio_vs_benchmark, 2),
        wf_directional=wf_directional, wf_n=wf_n if wf_n else 6,
        wf_mean=round(wf_mean, 2), wf_p=round(wf_p, 3),
    ), encoding="utf-8")

    # 01 performance
    tpl = env.get_template("01_performance_dossier.md.j2")
    (out_dir / "01_performance_dossier.md").write_text(tpl.render(
        metrics_rows=metrics.to_dict(orient="records"),
    ), encoding="utf-8")

    # 02 walk-forward
    tpl = env.get_template("02_walk_forward_robustness.md.j2")
    has_data = not walk.empty and wf_n > 0
    if has_data:
        sharpe_by_policy = {}
        window_ids = sorted(walk["window_id"].unique())
        for policy in walk["policy"].unique():
            sharpe_by_policy[policy] = walk[walk.policy == policy].set_index(
                "window_id")["sharpe"].to_dict()
        delta_results = [{
            "policy": "t1_threshold",
            "delta_mean": wf_mean,
            "ci_low_95": float(np.percentile(mean_boots, 2.5)),
            "ci_high_95": float(np.percentile(mean_boots, 97.5)),
            "nominal_p": wf_p,
            "directional_consistency": wf_directional,
        }]
    else:
        sharpe_by_policy = {}
        window_ids = []
        delta_results = []
    (out_dir / "02_walk_forward_robustness.md").write_text(tpl.render(
        has_data=has_data,
        sharpe_by_policy=sharpe_by_policy,
        window_ids=window_ids,
        delta_results=delta_results,
        n_windows=wf_n,
    ), encoding="utf-8")

    # 03 capacity
    tpl = env.get_template("03_capacity_analysis.md.j2")
    sizes = sorted(cap["position_size_usd"].unique())

    def _pick(p, s, col):
        sub = cap[(cap.policy == p) & (cap.position_size_usd == s)]
        return float(sub[col].iloc[0]) if not sub.empty else 0.0

    (out_dir / "03_capacity_analysis.md").write_text(tpl.render(
        position_sizes=sizes,
        t1_apy_by_size={s: _pick("t1_threshold", s, "net_apy_pct") for s in sizes},
        b1_apy_by_size={s: _pick("b1_always_aave", s, "net_apy_pct") for s in sizes},
        t1_slippage_by_size={s: _pick("t1_threshold", s, "slippage_bp_avg") for s in sizes},
    ), encoding="utf-8")

    # 04 cost attribution
    tpl = env.get_template("04_cost_attribution.md.j2")
    t1_cost = cost[cost.policy == "t1_threshold"].copy()
    (out_dir / "04_cost_attribution.md").write_text(tpl.render(
        cost_rows=t1_cost.to_dict(orient="records"),
    ), encoding="utf-8")

    # 05-07 static text
    for name in ("05_risk_register.md.j2", "06_operational_runbook.md.j2",
                 "07_live_trial_plan.md.j2"):
        tpl = env.get_template(name)
        (out_dir / name.replace(".j2", "")).write_text(
            tpl.render(), encoding="utf-8",
        )


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tables", default="results/institutional/tables")
    ap.add_argument("--out", default="docs/institutional")
    args = ap.parse_args(argv)
    render_all(tables_dir=Path(args.tables), out_dir=Path(args.out))
    print(f"rendered 8 chapters to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
