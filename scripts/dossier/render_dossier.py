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


def _paired_wf(walk: pd.DataFrame, value_col: str,
               a: str = "t1_threshold", b: str = "b1_always_aave"):
    """Generic per-window paired bootstrap on `value_col` for (a - b).

    Returns dict with: directional, mean_delta, ci_low, ci_high, p,
    boots (None if empty), n. Used for both Sharpe and APY contrasts."""
    null = {"directional": 0, "mean_delta": 0.0, "ci_low": 0.0,
            "ci_high": 0.0, "p": 1.0, "boots": None, "n": 0,
            "deltas": []}
    if walk.empty:
        return null
    pivot = walk.pivot_table(
        index="window_id", columns="policy",
        values=value_col, aggfunc="first",
    )
    if a not in pivot.columns or b not in pivot.columns:
        return null
    delta = (pivot[a] - pivot[b]).dropna()
    n = len(delta)
    if n == 0:
        return null
    rng = np.random.default_rng(42)
    d = delta.to_numpy()
    boots = np.empty(2000)
    for i in range(2000):
        idx = rng.integers(0, n, size=n)
        boots[i] = d[idx].mean()
    return {
        "directional": int((delta > 0).sum()),
        "mean_delta": float(delta.mean()),
        "ci_low": float(np.percentile(boots, 2.5)),
        "ci_high": float(np.percentile(boots, 97.5)),
        "p": float((boots <= 0).mean()),
        "boots": boots,
        "n": n,
        "deltas": delta.to_list(),
    }


def _wf_t1_vs_b1(walk: pd.DataFrame):
    """Backward-compat wrapper for the old Sharpe-only signature."""
    r = _paired_wf(walk, value_col="sharpe")
    return (r["directional"], r["mean_delta"], r["p"], r["boots"], r["n"])


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

    # Two paired-bootstrap lenses on per-window deltas:
    # ΔAPY = binding fund-relevant metric (allocators care about net return)
    # ΔSharpe = secondary lens; B1's near-zero vol inflates its Sharpe,
    # so ΔSharpe under-states T1's edge.
    wf_apy = _paired_wf(walk, value_col="net_apy_pct")
    wf_sharpe = _paired_wf(walk, value_col="sharpe")
    wf_directional, wf_mean, wf_p, mean_boots, wf_n = _wf_t1_vs_b1(walk)

    # 00 one-pager (use ΔAPY as binding directional metric)
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
        wf_directional=wf_apy["directional"], wf_n=wf_apy["n"] if wf_apy["n"] else 6,
        wf_mean=round(wf_apy["mean_delta"], 2), wf_p=round(wf_apy["p"], 3),
    ), encoding="utf-8")

    # 01 performance
    tpl = env.get_template("01_performance_dossier.md.j2")
    (out_dir / "01_performance_dossier.md").write_text(tpl.render(
        metrics_rows=metrics.to_dict(orient="records"),
    ), encoding="utf-8")

    # 02 walk-forward (dual lens: APY primary + Sharpe secondary)
    # Also: per-protocol buy-and-hold comparison from extended tables.
    tpl = env.get_template("02_walk_forward_robustness.md.j2")
    has_data = not walk.empty and wf_apy["n"] > 0
    apy_table = ""
    sharpe_table = ""
    per_protocol_apy_table = ""
    per_protocol_bootstrap_rows = ""
    # Load per-protocol comparisons (computed by inline scripts in this session)
    pp_apy_path = tables_dir / "walk_forward_vs_all_holds.csv"
    pp_boot_path = tables_dir / "walk_forward_paired_bootstrap_all.csv"
    nxm_path = tables_dir / "walk_forward_NxM_contrasts.csv"
    nxm_table = ""
    if pp_apy_path.exists() and pp_boot_path.exists():
        pp_apy = pd.read_csv(pp_apy_path)
        # Per-window matrix: T1 vs each protocol hold (kept for backward-compat)
        header = "| Window | T1 | Aave hold | Morpho hold | Euler hold | ΔvsAave | ΔvsMorpho | ΔvsEuler |\n"
        sep = "|---|---:|---:|---:|---:|---:|---:|---:|\n"
        rows = []
        for _, r in pp_apy.iterrows():
            rows.append(
                f"| {r.window_id} | {r.t1_apy_pct:.2f}% | {r.aave_apy_pct:.2f}% | "
                f"{r.morpho_apy_pct:.2f}% | {r.euler_apy_pct:.2f}% | "
                f"{r.delta_t1_vs_aave:+.2f} | {r.delta_t1_vs_morpho:+.2f} | "
                f"{r.delta_t1_vs_euler:+.2f} |"
            )
        per_protocol_apy_table = header + sep + "\n".join(rows) + "\n"
    if nxm_path.exists():
        # N x M policy x protocol-hold contrast matrix. 6-way protocol coverage:
        # Aave/Compound/Spark/Morpho/Euler/Fluid. B4 hourly MCDM-EMA removed
        # (2026c straw-man, two rebalances in four months — not benchmark-worthy).
        nxm = pd.read_csv(nxm_path)
        policies = ["t1_threshold", "t2_optimal_stopping", "t3_hazard"]
        policies = [p for p in policies if p in nxm.policy.unique()]
        holds = ["aave", "compound", "spark", "morpho", "euler", "fluid"]
        holds = [h for h in holds if h in nxm.protocol_hold.unique()]

        def _cell(policy: str, hold: str) -> str:
            sub = nxm[(nxm.policy == policy) & (nxm.protocol_hold == hold)]
            if sub.empty:
                return "—"
            r = sub.iloc[0]
            sig = "**" if r.p_one_sided_le0 < 0.05 else ""
            return (
                f"{sig}{r.mean_pp:+.2f}pp{sig}<br>"
                f"p={r.p_one_sided_le0:.4f}<br>"
                f"{int(r.directional_consistency)}/{int(r.n_windows)}"
            )

        proto_labels = {
            "aave": "Aave V3", "compound": "Compound V3", "spark": "Spark",
            "morpho": "Morpho Blue", "euler": "Euler V2", "fluid": "Fluid",
        }
        hdr = "| Policy | " + " | ".join(f"vs {proto_labels[h]} hold" for h in holds) + " |\n"
        sep_row = "|---|" + "|".join(["---:"] * len(holds)) + "|\n"
        body_rows = []
        for p in policies:
            label = {
                "t1_threshold": "**T1** threshold",
                "t2_optimal_stopping": "**T2** OU stopping",
                "t3_hazard": "**T3** Cox hazard",
            }.get(p, p)
            cells = [_cell(p, h) for h in holds]
            body_rows.append(f"| {label} | " + " | ".join(cells) + " |")
        nxm_table = hdr + sep_row + "\n".join(body_rows) + "\n"
    if has_data:
        window_ids = sorted(walk["window_id"].unique())
        # Build per-policy lookup once
        def _table(value_col: str, fmt: str) -> str:
            policies_order = ["b1_always_aave",
                              "t1_threshold", "t2_optimal_stopping",
                              "t3_hazard"]
            policies = [p for p in policies_order
                        if p in walk["policy"].unique()]
            header = "| Policy | " + " | ".join(window_ids) + " |\n"
            sep = "|---|" + "|".join(["---:"] * len(window_ids)) + "|\n"
            rows = []
            for p in policies:
                sub = walk[walk.policy == p].set_index("window_id")[value_col].to_dict()
                cells = [
                    (fmt.format(sub[w]) if w in sub else "—")
                    for w in window_ids
                ]
                rows.append(f"| {p} | " + " | ".join(cells) + " |")
            return header + sep + "\n".join(rows) + "\n"

        apy_table = _table("net_apy_pct", "{:.2f}%")
        sharpe_table = _table("sharpe", "{:.2f}")
        delta_apy = {
            "delta_mean": wf_apy["mean_delta"],
            "ci_low_95": wf_apy["ci_low"],
            "ci_high_95": wf_apy["ci_high"],
            "nominal_p": wf_apy["p"],
            "directional_consistency": wf_apy["directional"],
        }
        delta_sharpe = {
            "delta_mean": wf_sharpe["mean_delta"],
            "ci_low_95": wf_sharpe["ci_low"],
            "ci_high_95": wf_sharpe["ci_high"],
            "nominal_p": wf_sharpe["p"],
            "directional_consistency": wf_sharpe["directional"],
        }
    else:
        delta_apy = None
        delta_sharpe = None
    (out_dir / "02_walk_forward_robustness.md").write_text(tpl.render(
        has_data=has_data,
        apy_table=apy_table,
        sharpe_table=sharpe_table,
        delta_apy=delta_apy,
        delta_sharpe=delta_sharpe,
        n_windows=wf_apy["n"] if has_data else 0,
        per_protocol_apy_table=per_protocol_apy_table,
        per_protocol_bootstrap_rows=per_protocol_bootstrap_rows,
        nxm_table=nxm_table,
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
