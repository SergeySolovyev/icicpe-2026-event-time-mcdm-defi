"""Pure exact-size exit policy. Never interprets reserves or TVL as capacity."""
from decimal import Decimal, InvalidOperation, localcontext

from .reference_price import observation_evidence, positive_decimal
from mirage.verdict import Finding, Severity


def detect(observation: dict, *, max_price_impact_bps: int = 500) -> Finding:
    if type(max_price_impact_bps) is not int or not 0 < max_price_impact_bps <= 10000:
        raise ValueError("Exit threshold must be in (0, 10000] bps")
    if not isinstance(observation, dict) or not isinstance(observation.get("quote", {}), dict):
        return Finding("exit_evidence_invalid", Severity.INSUFFICIENT,
                       "Exit observation and quote must be objects", {})
    quote = observation.get("quote", {})
    candidates = quote.get("candidates", [])
    if not isinstance(candidates, list) or any(not isinstance(item, dict) for item in candidates):
        return Finding("exit_evidence_invalid", Severity.INSUFFICIENT,
                       "Exit route candidates must be a list of objects", {})
    metrics = {"max_price_impact_bps": str(max_price_impact_bps),
               "route": quote.get("route", observation.get("route", [])),
               "amount_in_raw": quote.get("amount_in_raw"),
               "amount_out_raw": quote.get("amount_out_raw"),
               "collateral_decimals": observation.get("collateral_decimals"),
               "loan_decimals": observation.get("loan_decimals"),
               "scenario_notional_loan": observation.get("scenario", {}).get("notional_loan"),
               "quote_status": quote.get("status"),
               "reference_route": observation.get("route", []),
               "route_kind": quote.get("route_kind"),
               "route_selection": quote.get("selection"),
               "candidate_count": quote.get("candidate_count"),
               "routing_policy": observation.get("routing_policy", "direct-first/1"),
               "candidate_routes": [
                   {key: candidate.get(key) for key in (
                       "status", "reason", "route", "route_kind", "amount_in_raw", "amount_out_raw",
                       "route_twap_price_loan_per_collateral", "route_spot_price_loan_per_collateral",
                       "price_impact_bps_vs_spot", "execution_shortfall_bps_vs_twap")}
                   for candidate in candidates
               ],
               "scope": "specified sale on one Uniswap v3 route; fees included, gas excluded"}
    try:
        evidence = observation_evidence(observation)
        if observation.get("status") != "ok" or quote.get("status") != "ok":
            metrics["reason"] = quote.get("reason", observation.get("reason", "unknown"))
            return Finding("exit_depth_unavailable", Severity.INSUFFICIENT,
                           "No complete quote for a specified liquidation size on supported routes", metrics, evidence)
        # Recompute policy metrics from amounts and reference, ignoring supplied
        # presentation fields. Deterministic replay must not trust rounded bps.
        amount_in, amount_out = int(quote["amount_in_raw"]), int(quote["amount_out_raw"])
        if not 0 < amount_in < 2**255 or not 0 < amount_out < 2**256:
            raise ValueError("Invalid quote amount")
        decimals_in, decimals_out = observation["collateral_decimals"], observation["loan_decimals"]
        if any(type(d) is not int or not 0 <= d <= 255 for d in (decimals_in, decimals_out)):
            raise ValueError("Invalid token decimals")
        spot = positive_decimal(quote.get("route_spot_price_loan_per_collateral",
                                          observation["spot_price_loan_per_collateral"]))
        twap = positive_decimal(observation["price_loan_per_collateral"])
        with localcontext() as context:
            context.prec = 80
            execution = Decimal(amount_out) / amount_in * Decimal(10) ** (decimals_in - decimals_out)
            impact = (1 - execution / spot) * 10000
            shortfall = (1 - execution / twap) * 10000
            metrics.update(execution_price_loan_per_collateral=str(execution),
                           price_impact_bps_vs_spot=str(impact),
                           execution_shortfall_bps_vs_twap=str(shortfall))
            if max(impact, shortfall) > max_price_impact_bps:
                return Finding("exit_size_exceeds_policy", Severity.BLOCK,
                               "Specified sale exceeds the allowed execution shortfall on the selected route", metrics, evidence)
        return Finding("exit_size_quoted", Severity.PASS,
                       "Specified sale quotes within policy at this block; future execution is not guaranteed", metrics, evidence)
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return Finding("exit_evidence_invalid", Severity.INSUFFICIENT,
                       "Exit observation is malformed or has mismatched evidence", metrics)
