"""Pure independent-reference policy; accepts collected observations only."""
from decimal import Decimal, InvalidOperation, localcontext

from mirage.verdict import Evidence, Finding, Severity


def observation_evidence(observation: dict) -> tuple[Evidence, ...]:
    """Only collect correctly anchored evidence; malformed input fails closed."""
    result = []
    for item in observation.get("evidence", []):
        evidence = Evidence(**item)
        if (evidence.block != observation.get("block_number")
                or evidence.block_hash != observation.get("block_hash")):
            raise ValueError("Uniswap evidence anchor mismatch")
        result.append(evidence)
    return tuple(result)


def positive_decimal(value) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite() or result <= 0:
        raise ValueError("Expected positive finite decimal")
    return result


def detect(observation: dict, *, oracle_price_loan_per_collateral=None,
           max_deviation_bps: int = 500) -> Finding:
    if type(max_deviation_bps) is not int or not 0 < max_deviation_bps <= 10000:
        raise ValueError("Reference deviation threshold must be in (0, 10000] bps")
    if not isinstance(observation, dict):
        return Finding("reference_evidence_invalid", Severity.INSUFFICIENT,
                       "Reference observation must be an object", {})
    metrics = {"source": observation.get("source"), "route": observation.get("route", []),
               "window_seconds": observation.get("window_seconds"),
               "max_deviation_bps": str(max_deviation_bps)}
    try:
        evidence = observation_evidence(observation)
        if observation.get("status") != "ok":
            return Finding("reference_unavailable", Severity.INSUFFICIENT,
                           "No usable independent price in the supported Uniswap routes", metrics, evidence)
        reference = positive_decimal(observation["price_loan_per_collateral"])
        spot = positive_decimal(observation["spot_price_loan_per_collateral"])
        with localcontext() as context:
            context.prec = 80
            metrics.update(price_loan_per_collateral=str(reference),
                           spot_price_loan_per_collateral=str(spot),
                           spot_twap_deviation_bps=str(abs(spot / reference - 1) * 10000))
            if oracle_price_loan_per_collateral is not None:
                oracle = positive_decimal(oracle_price_loan_per_collateral)
                deviation = abs(oracle / reference - 1) * 10000
                metrics.update(oracle_price_loan_per_collateral=str(oracle),
                               oracle_deviation_bps=str(deviation))
                if deviation > max_deviation_bps:
                    return Finding("oracle_reference_divergence", Severity.BLOCK,
                                   "Oracle price diverges from the independent reference beyond policy", metrics, evidence)
            if Decimal(metrics["spot_twap_deviation_bps"]) > max_deviation_bps:
                return Finding("reference_market_moving", Severity.WARN,
                               "Spot and time-weighted reference diverge; review market movement", metrics, evidence)
        summary = ("Identical collateral and loan token; conversion is one by identity"
                   if observation.get("source") == "token-identity" else
                   "Uniswap geometric TWAP observed; this is not proof of an unmanipulable oracle")
        return Finding("reference_observed", Severity.PASS, summary, metrics, evidence)
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return Finding("reference_evidence_invalid", Severity.INSUFFICIENT,
                       "Reference observation is malformed or has mismatched evidence", metrics)
