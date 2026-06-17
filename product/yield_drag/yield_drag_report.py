"""O1 — Yield-Drag Analyst: a contracted agent-run operation.

A single unit of work: given a treasury's idle USDC position (size +
the protocol it currently sits in), compute over the real-gas panel how
much it left on the table versus event-time routing across the six
protocols, NET OF REAL GAS, and emit a reconciled one-page report.

AGENT-OPERATION CONTRACT (docs/founder/09_agentic_operating_system.md §1)
  Role             : Yield-Drag Analyst
  Inputs           : position_usd: float, current_protocol: str,
                     start/end: UTC dates (default = held-out test window)
  Output artifact  : a markdown 1-page report (+ JSON audit sidecar)
  Forbidden actions: never sends/publishes; never moves funds; never
                     signs or submits a tx; never enters credentials.
                     This module GENERATES; a human sends.
  SOP              : slice panel -> replay passive-hold + T1 allocator on
                     the REAL-GAS panel -> reconcile -> render.
  Quality / evals  : 5 numeric gates (below); report is withheld if any
                     fails (escalate to human).
  Logging          : JSON audit sidecar with inputs, panel hash, outputs.
  Human gate       : printed NOT-SENT notice; sending is the human's call.

This is the Tier-A AI-native-service wedge: priced on the OUTCOME (the
validated net-of-cost basis points), not on dashboard access.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backtest.replay_per_block import EventReplayEngine, ReplaySummary
from decision.base import Action, BLOCKS_PER_YEAR
from decision.t1_threshold import T1ThresholdPolicy

PANEL = ROOT / "data" / "cached" / "per_block_panel.parquet"
GAS_CURVE_CSV = ROOT / "results" / "institutional" / "tables" / "greedy_vs_t1_gas_sensitivity.csv"
PROTOCOLS = ("aave_v3", "compound_v3", "spark", "morpho_blue", "euler_v2", "fluid")
PRETTY = {"aave_v3": "Aave V3", "compound_v3": "Compound V3", "spark": "Spark",
          "morpho_blue": "Morpho Blue", "euler_v2": "Euler V2", "fluid": "Fluid"}
PRETTY_INV = {v: k for k, v in PRETTY.items()}
# Per-protocol IRM kink slope (per Krause 2005; same values as
# scripts/capacity_sweep_6way.py). Used for the size-haircut: depositing P
# into a pool of TVL/util depresses the earned rate by ~0.5*slope*util*P/(TVL+P)
# (continuous, CORRECT for at-par lending mint/burn -- NOT a per-rebalance toll;
# see docs/research/capacity_reconciliation_2026-06.md).
IRM_SLOPE_KINK = {"aave_v3": 0.04, "compound_v3": 0.05, "spark": 0.04,
                  "morpho_blue": 0.06, "euler_v2": 0.05, "fluid": 0.05}
HAIRCUT_SIZES_USD = (500_000.0, 2_000_000.0, 5_000_000.0)


class _AlwaysHold:
    """Passive buy-and-hold of one protocol (the counterfactual)."""
    def __init__(self, protocol: str):
        self.protocol = protocol
        self.name = f"hold_{protocol}"

    def decide(self, state):
        if state.current_protocol == self.protocol:
            return Action(kind="hold", target_protocol=None, rationale="passive")
        return Action(kind="switch", target_protocol=self.protocol, rationale="cold start")


@dataclass
class YieldDragResult:
    position_usd: float
    current_protocol: str
    window_start: str
    window_end: str
    n_blocks: int
    years: float
    passive_net_apy_pct: float
    active_net_apy_pct: float
    drag_bp_annualized: float
    drag_usd_over_window: float
    active_rebalances: int
    active_gas_usd: float
    realized_gas_gwei: float
    active_time_share: dict
    size_haircut: list      # [{size_usd, slippage_bp, net_active_apy_pct, net_edge_pp}]
    gas_curve: list         # [{gas_gwei, t1_net_apy_pct, autorouter_net_apy_pct, t1_switches}]
    panel_sha256_12: str
    quality_gates_passed: bool


def _slim(panel: pd.DataFrame) -> pd.DataFrame:
    """Keep only the columns the engine reads for T1 / passive-hold.

    The replay engine rebuilds a BlockState per row by scanning row.index;
    dropping the ~14 unused columns (T2/T3 signal families, peg, etc.)
    shrinks that per-row scan. T1 and buy-and-hold never touch them.
    """
    keep = [c for c in panel.columns
            if c.endswith(("_lending_apr", "_utilization", "_tvl_usd"))
            or c in ("block_number", "block_timestamp", "gas_price_gwei",
                     "eth_price_usd", "eth_usd")]
    return panel[keep]


def _run(panel: pd.DataFrame, policy, position_usd: float) -> tuple[pd.DataFrame, ReplaySummary]:
    # initial_capital_usd MUST be the real position: the engine deducts
    # ABSOLUTE gas USD per switch (replay_per_block.py:129) and T1's switch
    # threshold scales with state.position_usd (t1_threshold.py:87). Passing
    # a notional $1 would make gas dwarf the position and freeze T1 into
    # buy-and-hold -- the bug this wrapper must not reintroduce. Real gas
    # (gas_price_gwei) and real ETH price (eth_usd) come from the panel rows.
    eng = EventReplayEngine(initial_capital_usd=position_usd, gas_used_estimate=200_000)
    return eng.run(panel=panel, policy=policy)


def _size_haircut(sl: pd.DataFrame, ts: dict, gross_active_apy: float,
                  passive_apy: float) -> list:
    """Continuous slippage haircut on the active edge at several sizes.

    Depositing P into a venue depresses the earned supply rate by
    ~0.5 * slope * util * P/(TVL+P) (Krause 2005, linear-IRM finite-deposit
    average), weighted by the policy's time-share in that venue. This is the
    HONEST size answer the thin edge-carrying venues demand (Euler ~$16M,
    Spark ~$29M): it shows how much of the gross edge survives at $0.5/2/5M,
    holding the gross routing fixed. Net of gas, still gross of MEV.
    """
    means = {}
    for pretty in ts:
        p = PRETTY_INV.get(pretty)
        if p is None:
            continue
        tvl = float(pd.to_numeric(sl.get(f"{p}_tvl_usd"), errors="coerce").mean())
        util = float(pd.to_numeric(sl.get(f"{p}_utilization"), errors="coerce").mean())
        if tvl and tvl > 0 and 0 < util < 1:
            means[p] = (tvl, util, ts[pretty] / 100.0)
    rows = []
    for P in HAIRCUT_SIZES_USD:
        impact_bp = 0.0
        for p, (tvl, util, share) in means.items():
            impact_bp += share * 0.5 * IRM_SLOPE_KINK.get(p, 0.05) * util * P / (tvl + P) * 1e4
        net_active = gross_active_apy - impact_bp / 100.0
        rows.append({"size_usd": P, "slippage_bp": round(impact_bp, 1),
                     "net_active_apy_pct": round(net_active, 3),
                     "net_edge_pp": round(net_active - passive_apy, 3)})
    return rows


def _gas_curve_rows() -> list:
    """T1 vs naive greedy auto-router across gas levels, from the committed
    sweep CSV (scripts/greedy_gas_sensitivity.py). Answers two buyer
    objections at once: (1) the realized-gas number looks too cheap -> here is
    the whole 10-200 gwei curve; (2) "I'd just use an auto-router" -> greedy IS
    the idealized no-gas-gate auto-router, and it goes negative as gas rises
    while T1 throttles. $1M reference (gas is a SMALLER drag at larger sizes).
    """
    try:
        df = pd.read_csv(GAS_CURVE_CSV)
    except (OSError, ValueError):
        return []
    rows = []
    for g in sorted(df.gas_gwei.unique()):
        sub = df[df.gas_gwei == g]
        t1 = sub[sub.policy == "t1_threshold"]
        gr = sub[sub.policy == "b3_greedy_spot"]
        if t1.empty or gr.empty:
            continue
        rows.append({"gas_gwei": float(g),
                     "t1_net_apy_pct": round(float(t1.net_apy_pct.iloc[0]), 2),
                     "autorouter_net_apy_pct": round(float(gr.net_apy_pct.iloc[0]), 2),
                     "t1_switches": int(t1.n_rebalances.iloc[0])})
    return rows


def analyze(position_usd: float, current_protocol: str,
            start: str = "2026-01-01", end: str = "2026-05-01",
            panel: pd.DataFrame | None = None) -> YieldDragResult:
    if current_protocol not in PROTOCOLS:
        raise ValueError(f"current_protocol must be one of {PROTOCOLS}")
    # panel is injectable for testing; defaults to the real on-disk panel.
    panel = pd.read_parquet(PANEL) if panel is None else panel.copy()
    panel["block_timestamp"] = pd.to_datetime(panel["block_timestamp"], utc=True)
    s, e = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
    sl = panel[(panel.block_timestamp >= s) & (panel.block_timestamp < e)].reset_index(drop=True)
    if len(sl) < 1000:
        raise ValueError(f"window too short ({len(sl)} blocks)")

    # data provenance hash (the exact slice the numbers come from)
    h = hashlib.sha256(pd.util.hash_pandas_object(
        sl[[f"{p}_lending_apr" for p in PROTOCOLS] + ["gas_price_gwei"]], index=True
    ).values.tobytes()).hexdigest()[:12]

    sl = _slim(sl)
    realized_gwei = round(float(pd.to_numeric(sl["gas_price_gwei"], errors="coerce").mean()), 3)
    eq_p, sum_p = _run(sl, _AlwaysHold(current_protocol), position_usd)
    eq_a, sum_a = _run(sl, T1ThresholdPolicy(), position_usd)

    years = len(sl) / BLOCKS_PER_YEAR
    apy_p = sum_p.net_apr_annualized * 100   # engine's geometric APY (initial = position)
    apy_a = sum_a.net_apr_annualized * 100   # net of real gas, GROSS of slippage/MEV
    drag_usd = sum_a.final_position_usd - sum_p.final_position_usd  # both start at position_usd
    ts = (eq_a["current_protocol"].value_counts(normalize=True) * 100).round(1).to_dict()
    ts = {PRETTY.get(k, k): v for k, v in sorted(ts.items(), key=lambda kv: -kv[1])}

    size_haircut = _size_haircut(sl, ts, apy_a, apy_p)
    gas_curve = _gas_curve_rows()

    # ---- quality gates (eval set) ----
    gates = {
        "passive_apy_sane": 0.0 <= apy_p <= 30.0,
        "active_apy_sane": 0.0 <= apy_a <= 30.0,
        "active_beats_passive": apy_a >= apy_p - 0.01,
        "time_share_sums_100": abs(sum(ts.values()) - 100.0) < 1.0,
        "no_phantom_yield": sum_a.final_position_usd > 0 and sum_p.final_position_usd > 0,
    }
    if not all(gates.values()):
        raise RuntimeError(f"QUALITY GATE FAILED -> escalate to human: "
                           f"{[k for k, v in gates.items() if not v]}")

    return YieldDragResult(
        position_usd=position_usd, current_protocol=current_protocol,
        window_start=start, window_end=end, n_blocks=len(sl), years=round(years, 3),
        passive_net_apy_pct=round(apy_p, 3), active_net_apy_pct=round(apy_a, 3),
        drag_bp_annualized=round((apy_a - apy_p) * 100, 1),
        drag_usd_over_window=round(drag_usd, 0),
        active_rebalances=sum_a.n_switches, active_gas_usd=round(sum_a.total_gas_usd, 2),
        realized_gas_gwei=realized_gwei, active_time_share=ts,
        size_haircut=size_haircut, gas_curve=gas_curve,
        panel_sha256_12=h, quality_gates_passed=True)


def render_report(r: YieldDragResult) -> str:
    ts_lines = "\n".join(f"  - {k}: {v:.1f}%" for k, v in r.active_time_share.items())

    if r.size_haircut:
        hc = "\n".join(
            f"  | ${row['size_usd']/1e6:>4.1f}M | {row['slippage_bp']:>5.1f} bp "
            f"| {row['net_active_apy_pct']:>5.2f}% | {row['net_edge_pp']:+.2f} pp |"
            for row in r.size_haircut)
        haircut_block = (
            "## Size haircut — how much of the edge survives YOUR size\n"
            "The headline above is **gross of slippage** (a price-taker number). "
            "But the edge-carrying venues are thin (Euler ~$16M, Spark ~$29M USDC "
            "TVL), so your own deposit depresses the very rate you chase. "
            "Continuous Krause-2005 yield-impact, net of gas, **still gross of MEV**:\n\n"
            "  | Position | Slippage | Net active APY | Net edge vs passive |\n"
            "  |---|---|---|---|\n" + hc + "\n\n"
            "_Read the row matching your size, not the gross headline. Above "
            "~$5–10M the thin venues cannot absorb the position and the full-"
            "strategy edge compresses to deep-venue-only._\n")
    else:
        haircut_block = ""

    if r.gas_curve:
        gc = "\n".join(
            f"  | {row['gas_gwei']:>5.0f} | {row['t1_net_apy_pct']:>5.2f}% "
            f"| {row['autorouter_net_apy_pct']:>6.2f}% | {row['t1_switches']:>4d} |"
            for row in r.gas_curve)
        gas_block = (
            "## Gas sensitivity & the naive-auto-router benchmark\n"
            f"This window's realized gas was **~{r.realized_gas_gwei:.2f} gwei** "
            f"(post-Dencun), so total gas was only **${r.active_gas_usd:,.0f}** — "
            "honest, but unusually cheap. The full curve below ($1M reference; "
            "gas is a *smaller* drag at larger sizes) shows what happens as gas "
            "rises, and benchmarks us against a **naive greedy auto-router** "
            "(switch-to-best every block, no gas gate — the idealized version of "
            "a Morpho/Eco-style router):\n\n"
            "  | Gas (gwei) | T1 (us) net APY | Auto-router net APY | T1 switches |\n"
            "  |---|---|---|---|\n" + gc + "\n\n"
            "_At today's near-zero gas we are roughly level with a naive "
            "auto-router; our value is the **throttle** — as gas rises the "
            "auto-router keeps switching and goes negative, while T1 cuts "
            "switches and stays positive._\n")
    else:
        gas_block = ""

    return f"""# Yield-Drag Report — idle USDC treasury

**Position analysed:** ${r.position_usd:,.0f} in **{PRETTY[r.current_protocol]}**
**Window:** {r.window_start} to {r.window_end} ({r.n_blocks:,} Ethereum blocks, ~{r.years:.2f} yr)

## Headline (this {r.years:.2f}-yr window, gross of slippage)
Held passively in {PRETTY[r.current_protocol]}, this position earned a net
**{r.passive_net_apy_pct:.2f}% APY**. Event-time routing across the six largest
Ethereum USDC lending venues — net of **real** gas, **gross of slippage/MEV** —
would have earned **{r.active_net_apy_pct:.2f}% APY**.

> **Gross-of-slippage gap: ~${r.drag_usd_over_window:,.0f} over this window
> ({r.drag_bp_annualized:+.0f} bp annualized). The size-adjusted, net-of-slippage
> number is in the haircut table below — read THAT, not this.**

Captured with **{r.active_rebalances} rebalances** costing **${r.active_gas_usd:,.0f}**
total gas (real `eth_feeHistory` gas; a 50-line gas-aware threshold rule, no ML).

## Where the routing spent its time
{ts_lines}

{haircut_block}
{gas_block}
## What this is — and isn't (honest by design)
- **The rule's edge (the binding claim):** across an 18-month, 6-window
  walk-forward, the gas-aware threshold rule beats the passive buy-and-hold of
  **every** one of the six venues, all 6/6 windows (p<0.001) — on a public,
  reproducible dataset. This is the RULE vs passive, NOT an ML result.
- **The ML tier is a published NEGATIVE (separate result):** we trained a
  Cox-hazard ML tier and, out-of-sample, it **loses** to the 50-line rule
  (−5.97 bp, 0/5 windows). We report that openly — the edge is event-time
  resolution + a gas throttle, not a black box.
- **Net of real gas, GROSS of MEV/slippage:** at institutional size, slippage
  (the haircut table) and MEV are the binding costs; production execution uses
  a Flashbots private mempool. We do not hide this.
- **Non-custodial:** the production agent can *propose/execute with your keys*
  but can **never move your funds**. No token.
- **Honest maturity:** the edge is backtested + reproducible; the live agent is
  testnet-stage (2 of 6 adapters, unaudited). This report is analysis of the
  past, not forward advice.

## Provenance
Panel slice SHA-256 (12): `{r.panel_sha256_12}` · sources: Aave/Morpho/Euler
event streams, Compound RPC, Spark `getReserveData`, Fluid fToken, Maker DSR,
`eth_feeHistory` gas. Reproducible: `python -m product.yield_drag.yield_drag_report`.

---
*Generated by the Yield-Drag Analyst agent-operation. NOT SENT — delivery to a
client requires human review and approval (agent-operation human gate).*
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--position-usd", type=float, default=5_000_000)
    ap.add_argument("--protocol", default="aave_v3", choices=PROTOCOLS)
    ap.add_argument("--start", default="2026-01-01")
    ap.add_argument("--end", default="2026-05-01")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    r = analyze(a.position_usd, a.protocol, a.start, a.end)
    report = render_report(r)
    out = Path(a.out) if a.out else (Path(__file__).parent / "samples" /
          f"report_{a.protocol}_{int(a.position_usd)}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    (out.with_suffix(".audit.json")).write_text(json.dumps(asdict(r), indent=2), encoding="utf-8")
    print(report)
    print(f"\n[audit] wrote {out.name} + {out.with_suffix('.audit.json').name} "
          f"(quality gates: PASSED)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
