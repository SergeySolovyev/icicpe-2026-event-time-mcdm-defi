"""Pure oracle evidence checks. Equal samples never prove interval constancy."""
from decimal import Decimal, InvalidOperation, localcontext

from mirage.verdict import Evidence, Finding, Severity


ZERO_ADDRESS = "0x" + "00" * 20
ADDRESS_GETTERS = ("BASE_VAULT", "BASE_FEED_1", "BASE_FEED_2",
                   "QUOTE_VAULT", "QUOTE_FEED_1", "QUOTE_FEED_2")


def _price_uint(value):
    if type(value) is not int and not (isinstance(value, str) and value.isascii() and value.isdigit()):
        raise ValueError("Oracle price must be an integer")
    integer = int(value)
    if not 0 <= integer < 2**256:
        raise ValueError("Oracle price must be a uint256")
    return integer


def normalize_price(raw: int | str, collateral_decimals: int, loan_decimals: int) -> Decimal:
    """Morpho raw-unit price * 10^(collateral decimals - loan decimals) / 1e36."""
    if any(type(value) is not int or not 0 <= value <= 255
           for value in (collateral_decimals, loan_decimals)):
        raise ValueError("Both token decimals must be uint8 integers")
    raw = _price_uint(raw)
    with localcontext() as context:
        context.prec = 100
        return Decimal(raw) * Decimal(10) ** (collateral_decimals - loan_decimals - 36)


def detect(observation: dict, *, reference: dict | None = None, same_asset: bool = False,
           max_deviation_bps: int = 500) -> Finding:
    """Check supported configuration, sample equality and independent deviation.

The deviation threshold is MIRAGE admission policy, not a protocol invariant.
Bytecode feature counts and PUSH candidates never establish oracle correctness.
"""
    if type(max_deviation_bps) is not int or not 0 <= max_deviation_bps <= 10_000:
        raise ValueError("max_deviation_bps must be an integer in [0, 10000]")
    obs = observation
    metrics = {key: obs.get(key) for key in (
        "address", "code_length", "code_sha256", "current_price", "previous_price",
        "previous_block", "factory_verified", "template",
    )}
    metrics.update(max_deviation_bps=max_deviation_bps, same_asset=same_asset,
                   constant_configuration=False, equal_sampled_prices=False,
                   samples_prove_interval_constancy=False, reference_comparable=False)
    if obs.get("bytecode") is not None:
        metrics["bytecode"] = obs["bytecode"]
    metrics["getters"] = obs.get("getters", {})
    metrics["feed_rounds"] = obs.get("feed_rounds", [])
    try:
        evidence = tuple(value if isinstance(value, Evidence) else Evidence(**value)
                         for value in obs.get("evidence", []))
    except (TypeError, ValueError):
        return Finding("oracle_invalid_evidence", Severity.INSUFFICIENT,
                       "Oracle evidence is malformed.", metrics)

    def finding(code, severity, summary):
        return Finding(code, severity, summary, metrics, evidence)

    if type(obs.get("code_length")) is not int or obs["code_length"] <= 0:
        return finding("oracle_code_unavailable", Severity.INSUFFICIENT,
                       "No deployed oracle runtime was observed at the selected block.")
    if obs.get("anchor_verified") is False:
        return finding("oracle_anchor_unconfirmed", Severity.INSUFFICIENT,
                       "The selected block hash could not be rechecked after the oracle observations.")
    try:
        current = _price_uint(obs["current_price"])
        previous = None if obs.get("previous_price") is None else _price_uint(obs["previous_price"])
        if obs.get("previous_anchor_verified") is False:
            previous = None
    except (ValueError, TypeError, KeyError):
        return finding("oracle_price_unavailable", Severity.INSUFFICIENT,
                       "price() did not return a valid uint256; an empty reply is not a frozen price.")
    metrics["equal_sampled_prices"] = previous is not None and current == previous

    getters = obs.get("getters", {})
    if obs.get("factory_verified") is not True or obs.get("template") != "morpho-chainlink-oracle-v2":
        return finding("oracle_template_unsupported", Severity.INSUFFICIENT,
                       "Custom oracle behavior is not established by getter compatibility or bytecode candidates.")
    try:
        for name in ADDRESS_GETTERS:
            value = getters[name]
            if not isinstance(value, str) or len(value) != 42 or not value.startswith("0x"):
                raise ValueError("invalid getter address")
            int(value[2:], 16)
        scale = int(getters["SCALE_FACTOR"])
        samples = [int(getters[name + "_CONVERSION_SAMPLE"])
                   for name in ("BASE_VAULT", "QUOTE_VAULT")]
        if scale <= 0 or min(samples) <= 0:
            raise ValueError("invalid scale/sample")
        for index, name in enumerate(("BASE_VAULT", "QUOTE_VAULT")):
            if getters[name].lower() == ZERO_ADDRESS and samples[index] != 1:
                raise ValueError("zero-vault sample must equal one")
    except (KeyError, ValueError, TypeError):
        return finding("oracle_configuration_incomplete", Severity.INSUFFICIENT,
                       "The supported oracle configuration could not be read consistently.")
    constant = all(getters[name].lower() == ZERO_ADDRESS for name in ADDRESS_GETTERS)
    metrics["constant_configuration"] = constant
    if constant and current != scale:
        return finding("oracle_configuration_inconsistent", Severity.INSUFFICIENT,
                       "Observed price contradicts the factory template with six zero dependencies.")
    if current == 0:
        return finding("oracle_zero_price", Severity.BLOCK,
                       "The supported oracle prices collateral at zero at the selected block.")

    normalized = None
    try:
        normalized = normalize_price(current, obs["collateral_decimals"], obs["loan_decimals"])
        metrics["price_loan_per_collateral"] = str(normalized)
    except (KeyError, ValueError, TypeError, InvalidOperation):
        metrics["price_loan_per_collateral"] = None

    reference_ok = False
    if reference is not None:
        reference_ok = (reference.get("status") == "ok"
                        and reference.get("block_number") == obs.get("block_number")
                        and reference.get("block_hash") == obs.get("block_hash")
                        and reference.get("source") in ("uniswap-v3", "uniswap-v4", "token-identity"))
        if reference.get("source") == "token-identity" and not same_asset:
            reference_ok = False
        try:
            independent = Decimal(reference["price_loan_per_collateral"])
            reference_ok = reference_ok and independent.is_finite() and independent > 0
        except (KeyError, TypeError, ValueError, InvalidOperation):
            reference_ok = False
        if reference_ok and normalized is not None:
            metrics["reference_comparable"] = True
            with localcontext() as context:
                context.prec = 100
                deviation = abs(normalized - independent) / independent * 10_000
            metrics.update(reference_price_loan_per_collateral=str(independent), deviation_bps=str(deviation),
                           reference_source=reference.get("source"))
            if deviation > max_deviation_bps:
                # Include the reference's raw RPC evidence in the same finding.
                try:
                    evidence += tuple(value if isinstance(value, Evidence) else Evidence(**value)
                                      for value in reference.get("evidence", []))
                except (TypeError, ValueError):
                    return finding("oracle_reference_unavailable", Severity.INSUFFICIENT,
                                   "Independent reference evidence is malformed.")
                return finding("oracle_reference_deviation", Severity.BLOCK,
                               "Oracle price differs from the independent reference beyond MIRAGE's admission threshold.")
        else:
            reference_ok = False
    metrics["reference_comparable"] = reference_ok

    # Observe feed timestamps without assuming a universal Chainlink heartbeat.
    # No timestamps from a custom feed imply no trusted liveness observation.
    feeds = {getters[name].lower() for name in ADDRESS_GETTERS if "FEED" in name
             and getters[name].lower() != ZERO_ADDRESS}
    rounds = {row.get("address", "").lower(): row for row in obs.get("feed_rounds", [])}
    if feeds - rounds.keys():
        return finding("oracle_feed_observation_incomplete", Severity.INSUFFICIENT,
                       "One or more configured feeds did not return valid latestRoundData evidence.")
    for feed in feeds:
        row = rounds[feed]
        try:
            if int(row["answer"]) <= 0 or not 0 < int(row["updated_at"]) <= obs["timestamp"]:
                raise ValueError("invalid feed observation")
        except (KeyError, TypeError, ValueError):
            return finding("oracle_feed_round_invalid", Severity.INSUFFICIENT,
                           "A configured feed reports a nonpositive answer or an invalid update timestamp.")

    if same_asset:
        if normalized is None:
            return finding("oracle_units_unavailable", Severity.INSUFFICIENT,
                           "Token decimals are required to verify the same-asset nominal price.")
        if normalized != 1:
            return finding("oracle_same_asset_mispriced", Severity.BLOCK,
                           "The oracle's normalized price is not one for identical collateral and loan assets.")
        return finding("oracle_same_asset_nominal", Severity.PASS,
                       "A nominal price of one is consistent with identical collateral and loan assets.")
    if constant:
        return finding("oracle_constant_configuration", Severity.WARN,
                       "Six zero feed/vault addresses make this supported template return its fixed scale; this alone does not establish mispricing.")
    if reference_ok:
        return finding("oracle_reference_agreement", Severity.PASS,
                       "The supported oracle agrees with the independent reference at the selected block; interval liveness is not proven.")
    if previous is None:
        return finding("oracle_history_unavailable", Severity.INSUFFICIENT,
                       "A historical price sample is unavailable, so the sampled price-change check is incomplete.")
    if current == previous:
        return finding("oracle_equal_samples", Severity.WARN,
                       "The two sampled prices are equal; this does not prove a frozen price between them.")
    return finding("oracle_changed_samples", Severity.PASS,
                   "The supported oracle returned different prices at two sampled blocks; this does not certify all intervening prices.")
