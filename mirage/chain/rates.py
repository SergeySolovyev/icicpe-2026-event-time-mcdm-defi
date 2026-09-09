"""Annualized IRM accrual-rate indication, not a terminal spot rate or forecast.

Interface: morpho-org/morpho-blue/src/interfaces/IIrm.sol, borrowRateView.
Uses the stored Market tuple, exactly as supplied to the IRM. Does not simulate
accrueInterest or claim an executable future lender yield.

AdaptiveCurveIrm.borrowRateView returns avgRate across the interval since
market.lastUpdate; calling it at the current block does not make it instantaneous:
https://github.com/morpho-org/morpho-blue-irm/blob/main/src/adaptive-curve-irm/AdaptiveCurveIrm.sol
See borrowRateView and _borrowRate, especially the trapezoidal average.
"""
from dataclasses import asdict, astuple
from decimal import Decimal, localcontext

from .codec import enc_addr, uint_word, words
from mirage.verdict import Evidence

BORROW_RATE_VIEW = "0x8c00bf6b"
SECONDS_PER_YEAR = 365 * 24 * 60 * 60
WAD = 10**18
ADAPTIVE_CURVE_IRM = "0x870ac11d48b15db9a138cf899d20f13f79ba00bc"


def collect_rate(client, params, state, anchor):
    result = {"status": "insufficient", "basis": "annualized IRM accrual-rate indication on stored market state",
              "block_number": anchor.number, "block_hash": anchor.hash,
              "block_timestamp": anchor.timestamp, "stored_last_update_timestamp": state.last_update,
              "rate_semantics": ("AdaptiveCurveIrm interval-average borrow rate since stored lastUpdate"
                                 if params.irm.lower() == ADAPTIVE_CURVE_IRM else
                                 "borrowRateView return; temporal semantics depend on the configured IRM"),
              "accrual_interval_seconds": None, "evidence": []}
    data = (BORROW_RATE_VIEW + "".join(enc_addr(v) for v in astuple(params)[:4])
            + uint_word(params.lltv).hex()
            + "".join(uint_word(v).hex() for v in astuple(state)))
    try:
        if state.last_update > anchor.timestamp:
            raise ValueError("Stored market update is after the evidence block timestamp")
        result["accrual_interval_seconds"] = anchor.timestamp - state.last_update
        raw = client.call(params.irm, data, anchor.number)
        result["evidence"].append(asdict(Evidence(params.irm, data, anchor.number, raw, anchor.hash)))
        rate = words(raw, 1)[0]
        if state.fee > WAD or state.total_borrow_assets > state.total_supply_assets:
            raise ValueError("Invalid market ratios")
        with localcontext() as context:
            context.prec = 80
            utilization = (Decimal(state.total_borrow_assets) / state.total_supply_assets
                           if state.total_supply_assets else Decimal(0))
            borrow_apr = Decimal(rate) * SECONDS_PER_YEAR / WAD
            supply_apr = borrow_apr * utilization * (1 - Decimal(state.fee) / WAD)
            result.update(status="ok", borrow_rate_per_second_wad=str(rate),
                          borrow_apr=str(borrow_apr), supply_apr=str(supply_apr),
                          utilization=str(utilization))
    except (RuntimeError, ValueError) as error:
        result["reason"] = "irm_rate_unavailable_or_invalid"
        result["error_type"] = type(error).__name__
    return result


def replay_rate(observation, params, state, anchor):
    """Recompute APR from the recorded IRM return; never trust stored APR text."""
    calls = {}
    for raw in observation.get("evidence", []):
        evidence = Evidence(**raw)
        if (evidence.block != anchor.number or evidence.block_hash != anchor.hash
                or evidence.method != "eth_call"):
            raise ValueError("IRM evidence anchor mismatch")
        key = evidence.to.lower(), evidence.data.lower()
        if key in calls and calls[key] != evidence.result:
            raise ValueError("Conflicting IRM evidence")
        calls[key] = evidence.result

    class Recorded:
        def call(self, to, data, block):
            key = to.lower(), data.lower()
            if block != anchor.number or key not in calls:
                raise RuntimeError("IRM read not recorded")
            return calls[key]

    return collect_rate(Recorded(), params, state, anchor)
