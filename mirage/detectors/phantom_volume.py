"""Detector 2: accounting anomalies, NOT a principal-reconstruction algorithm.

The historical filename is retained; an abnormal share rate is a warning, not proof
of phantom debt. See docs/mirage/CORRECTIONS_2026-09-09.md.
"""
from decimal import Decimal, localcontext

from mirage.chain.morpho import MarketState
from mirage.verdict import Evidence, Finding, Severity


def ratio(numerator: int, denominator: int) -> str | None:
    if not denominator:
        return None
    with localcontext() as context:
        context.prec = 60
        return format(Decimal(numerator) / Decimal(denominator), ".12f")


def detect(state: MarketState, *, evidence: tuple[Evidence, ...] = (),
           max_share_price_multiple: int = 2) -> Finding:
    if type(max_share_price_multiple) is not int or max_share_price_multiple < 1:
        raise ValueError("Share-rate threshold must be a positive integer")
    values = (state.total_supply_assets, state.total_supply_shares,
              state.total_borrow_assets, state.total_borrow_shares, state.last_update, state.fee)
    if any(type(value) is not int or not 0 <= value < 2**128 for value in values):
        return Finding("invalid_market_state", Severity.INSUFFICIENT,
                       "Invalid uint128 market state", {}, evidence)
    supply, shares, borrow = values[:3]
    if state.last_update == 0:
        return Finding("market_not_created", Severity.INSUFFICIENT,
                       "No created market at this block", {}, evidence)
    if borrow > supply:
        return Finding("accounting_invariant_broken", Severity.INSUFFICIENT,
                       "Borrow assets exceed supply assets; verify the response", {}, evidence)
    # Exact virtual-share conversion, normalized against the initial 1e6 shares/asset.
    numerator, denominator = (supply + 1) * 1_000_000, shares + 1_000_000
    metrics = {
        "unit": "loan-token-base-units",
        "stored_supply_assets_raw": str(supply), "stored_borrow_assets_raw": str(borrow),
        "supply_shares_raw": str(shares), "available_liquidity_raw": str(supply - borrow),
        "utilization": ratio(borrow, supply),
        "share_price_multiple_vs_initial": ratio(numerator, denominator),
        "share_rate_threshold": str(max_share_price_multiple),
        "last_update_timestamp": str(state.last_update),
        "principal": None,
    }
    if supply > 0 and supply == borrow:
        return Finding("no_free_liquidity", Severity.BLOCK,
                       "No pre-existing free liquidity; entry veto under MIRAGE policy", metrics, evidence)
    if numerator > max_share_price_multiple * denominator:
        return Finding("elevated_share_exchange_rate", Severity.WARN,
                       "Elevated share exchange rate requires investigation; principal is unknown", metrics, evidence)
    return Finding("accounting_observed", Severity.PASS,
                   "Accounting check passed; this does not establish oracle or collateral safety", metrics, evidence)
