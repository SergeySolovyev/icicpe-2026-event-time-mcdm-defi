"""Evidence-block cold-start replay through the existing allocator's T1 policy."""
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
import math

from .scan import report_from_snapshot
from .verdict import Finding, MarketReport, MarketVerdict, Severity


def scenario_amount(value) -> str:
    try:
        amount = Decimal(str(value))
        if (not amount.is_finite() or not Decimal("0.000001") <= amount <= 10**9
                or amount != amount.quantize(Decimal("0.000001"))):
            raise ValueError("Amount must be 0.000001–1000000000 USDC, at most six decimals")
        return format(amount, "f")
    except (InvalidOperation, TypeError):
        raise ValueError("Invalid USDC scenario amount") from None


def compare(snapshot: dict, *, amount_usdc="10000", market_id=None) -> dict:
    import pandas as pd
    from decision.base import BlockState
    from decision.t1_threshold import T1ThresholdPolicy
    from mirage.gate import MirageGatedPolicy

    amount = scenario_amount(amount_usdc)
    report = report_from_snapshot(snapshot)
    verified_rates = {market.market_id: market.rate or {} for market in report.markets}
    rows = snapshot["rows"]
    if market_id is not None:
        rows = [row for row in rows if row["market_id"].lower() == market_id.lower()]
        if not rows:
            raise ValueError("Market is not in the inspected evidence set")
    rates, utilization, mapping = {}, {}, {}
    for row in rows:
        market = row["market_id"].lower()
        # Explicit market identifiers preserve the original six-protocol venue
        # mapping: the existing morpho_blue label is never repurposed for PAXG.
        venue = "morpho:" + market
        rate = verified_rates[market]
        apr = float(rate["supply_apr"]) if rate.get("status") == "ok" else float("nan")
        rates[venue] = apr if math.isfinite(apr) and apr >= 0 else float("nan")
        utilization[venue] = float(rate.get("utilization", 0))
        mapping[venue] = market
    state = BlockState(
        block_number=report.block_number,
        block_timestamp=pd.Timestamp(snapshot["anchor"]["timestamp"], unit="s", tz="UTC"),
        protocols=tuple(rates), lending_apr=rates, utilization=utilization,
        tvl_usd={venue: 0.0 for venue in rates},  # T1 cold start never reads TVL.
        current_protocol=None, position_usd=float(amount), gas_price_gwei=0.0,
        eth_price_usd=0.0, gas_used_estimate=0,
    )
    original = T1ThresholdPolicy().decide(state)
    matched = {}
    for market in report.markets:
        exit_check = next((f for f in market.findings if f.code.startswith("exit_")), None)
        observed = exit_check.metrics.get("scenario_notional_loan") if exit_check else None
        matched[market.market_id] = (observed is not None
                                    and exit_check.metrics.get("quote_status") == "ok"
                                    and Decimal(observed) == Decimal(amount))
    scenario_matches = all(matched[m] for m in mapping.values())
    if not scenario_matches:
        finding = Finding("exit_scenario_not_checked", Severity.INSUFFICIENT,
                          "Refresh evidence for this exact hypothetical sale amount", {"amount_usdc": amount})
        verdicts = tuple(MarketVerdict(m.market_id, m.block_number,
                                      m.findings + (() if matched[m.market_id] else (finding,)), m.display, m.rate)
                         for m in report.markets)
        report = MarketReport(report.chain_id, report.block_number, report.block_hash, report.source, verdicts)
    gated = MirageGatedPolicy(T1ThresholdPolicy(), report, venue_to_market=mapping).decide(state)
    selected = mapping.get(original.target_protocol)
    return {"original": asdict(original), "gated": asdict(gated), "amount_usdc": amount,
            "market_id": selected, "block_number": report.block_number, "block_hash": report.block_hash,
            "mode": "evidence-block replay", "policy": "decision.t1_threshold.T1ThresholdPolicy",
            "scenario_matches": scenario_matches, "candidate_count": len(rows),
            "candidates": [{"market_id": mapping[v], "supply_apr": str(rates[v]) if math.isfinite(rates[v]) else None}
                           for v in rates],
            "scope": "Cold start on the explicitly inspected Morpho markets; no transactions or historical P&L. "
                     "T1 uses APR, not accounting supply. The gate vetoes entry and does not select an alternative."}
