"""Bounded Ethereum Uniswap v3 observations; only single, numeric-block calls.

No transactions are sent. A QuoterV2 simulation is a scenario at one block, not
an execution guarantee or a measure of total collateral exit capacity. See
docs/mirage/UNISWAP.md for route selection, units and limitations.
"""
from dataclasses import asdict
from decimal import Decimal, InvalidOperation, localcontext

from .codec import enc_addr, hex_bytes, uint_word, word_addr, words
from .rpc import BlockAnchor, RpcClient
from mirage.verdict import Evidence

FACTORY = "0x1f98431c8ad98523631ae4a59f267346ea31f984"
QUOTER_V2 = "0x61ffe014ba17989e743c5f6cb21bf9697530b21e"
WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
ZERO = "0x" + "00" * 20
FEE_TIERS = (100, 500, 3000, 10000)
GET_POOL = "0x1698ee82"
OBSERVE = "0x883bdbfd"
SLOT0 = "0x3850c7bd"
LIQUIDITY = "0x1a686502"
TOKEN0 = "0x0dfe1681"
TOKEN1 = "0xd21220a7"
DECIMALS = "0x313ce567"
QUOTE_SINGLE = "0xc6a5026a"
MIN_SQRT_RATIO = 4295128739
MAX_SQRT_RATIO = 1461446703485210103287273052203988822378723970342
MAX_TICK = 887272
ROUTING_POLICY = "compare-direct-weth/1"
LEGACY_ROUTING_POLICY = "direct-first/1"


def _uint(value: int, bits: int) -> int:
    if type(value) is not int or not 0 <= value < 2**bits:
        raise ValueError(f"Expected uint{bits}")
    return value


def decode_signed(value: int, bits: int) -> int:
    """Require canonical 256-bit sign extension, including negative int24/56."""
    _uint(value, 256)
    low = value & (2**bits - 1)
    signed = low - 2**bits if low >= 2**(bits - 1) else low
    if value != signed % 2**256:
        raise ValueError(f"Noncanonical int{bits} padding")
    return signed


def encode_observe(window: int) -> str:
    if _uint(window, 32) == 0:
        raise ValueError("TWAP window must be positive")
    return OBSERVE + b"".join(map(uint_word, (32, 2, window, 0))).hex()


def decode_observe(result: str) -> tuple[tuple[int, int], tuple[int, int]]:
    """Decode the two canonical dynamic arrays for observe([window, 0])."""
    data = words(result, 8)
    if (data[0], data[1], data[2], data[5]) != (64, 160, 2, 2):
        raise ValueError("Invalid observe offsets or array lengths")
    return ((decode_signed(data[3], 56), decode_signed(data[4], 56)),
            (_uint(data[6], 160), _uint(data[7], 160)))


def consult_values(result: str, window: int) -> tuple[int, int]:
    encode_observe(window)
    ticks, liquidity = decode_observe(result)
    # Solidity 0.7 int56/uint160 subtraction wraps. These accumulators wrap
    # legitimately; subtraction in unbounded Python must reproduce that rule.
    delta = (ticks[1] - ticks[0] + 2**55) % 2**56 - 2**55
    tick = delta // window  # floor toward -infinity, not Solidity truncation
    if not -MAX_TICK <= tick <= MAX_TICK:
        raise ValueError("TWAP tick outside v3 range")
    seconds_delta = (liquidity[1] - liquidity[0]) % 2**160
    if seconds_delta == 0:
        raise ValueError("Zero seconds-per-liquidity delta")
    harmonic = window * (2**160 - 1) // (seconds_delta << 32)
    if not 0 < harmonic < 2**128:
        raise ValueError("Invalid harmonic mean liquidity")
    return tick, harmonic


def tick_price(tick: int, token_in_is_token0: bool,
               decimals_in: int, decimals_out: int) -> Decimal:
    """Human tokenOut/tokenIn geometric price; Decimal avoids binary floats."""
    if type(tick) is not int or not -MAX_TICK <= tick <= MAX_TICK:
        raise ValueError("Tick outside v3 range")
    _uint(decimals_in, 8)
    _uint(decimals_out, 8)
    with localcontext() as context:
        context.prec = 80
        power = tick if token_in_is_token0 else -tick
        return Decimal("1.0001") ** power * Decimal(10) ** (decimals_in - decimals_out)


def sqrt_price(sqrt_x96: int, token_in_is_token0: bool,
               decimals_in: int, decimals_out: int) -> Decimal:
    if not MIN_SQRT_RATIO <= sqrt_x96 < MAX_SQRT_RATIO:
        raise ValueError("Uninitialized or out-of-range sqrt price")
    with localcontext() as context:
        context.prec = 80
        price = Decimal(sqrt_x96) ** 2 / Decimal(2) ** 192
        if not token_in_is_token0:
            price = 1 / price
        return price * Decimal(10) ** (decimals_in - decimals_out)


def encode_quote(token_in: str, token_out: str, amount_in: int, fee: int) -> str:
    # QuoterV2 tuple differs from Quoter v1: amountIn PRECEDES fee.
    _uint(amount_in, 255)  # v3 Pool uses int256 amountSpecified internally
    _uint(fee, 24)
    if not amount_in:
        raise ValueError("Quote input amount must be positive")
    return (QUOTE_SINGLE + enc_addr(token_in) + enc_addr(token_out)
            + b"".join(map(uint_word, (amount_in, fee, 0))).hex())


def decode_quote(result: str) -> dict:
    amount, sqrt_after, ticks_crossed, gas = words(result, 4)
    _uint(sqrt_after, 160)
    _uint(ticks_crossed, 32)
    # Exact-input QuoterV2 does not return amount actually consumed. Reaching
    # the default sqrt boundary can mean a partial fill; never call it full.
    if not MIN_SQRT_RATIO + 1 < sqrt_after < MAX_SQRT_RATIO - 1:
        raise ValueError("Quote reaches price boundary; full input consumption unknown")
    if amount == 0:
        raise ValueError("Zero quote output")
    return {"amount_out_raw": str(amount), "sqrt_price_x96_after": str(sqrt_after),
            "initialized_ticks_crossed": ticks_crossed, "gas_estimate": str(gas)}


def _decimal(value: Decimal) -> str:
    return format(value, "f")


def collect_reference(client: RpcClient, collateral_token: str, loan_token: str,
                      anchor: BlockAnchor, *, amount_in_raw: int | None = None,
                      window: int = 1800, scenario_notional_loan: str | None = None,
                      routing_policy: str = ROUTING_POLICY,
                      quote_reason_version: int = 1) -> dict:
    """Collect TWAP and an optional exact-size exit scenario with raw evidence.

    Search four direct fee tiers. Select the usable pool with greatest harmonic
    mean liquidity (comparable ONLY for the same token pair). If none has usable
    history, attempt two WETH legs. For a specified sale, compare that direct
    route and a WETH route using the SAME collateral input derived once from
    the reference. The reference and selected exit route may differ. Legacy
    replay explicitly retains the original direct-first routing behavior.
    Quote reason version 0 preserves the old no-route/notional placeholder;
    version 1 distinguishes an unavailable reference from an unspecified size.
    The returned evidence is JSON-safe and all amounts are decimal strings.
    """
    enc_addr(collateral_token)
    enc_addr(loan_token)
    encode_observe(window)
    if routing_policy not in (ROUTING_POLICY, LEGACY_ROUTING_POLICY):
        raise ValueError("Unsupported Uniswap routing policy")
    if type(quote_reason_version) is not int or quote_reason_version not in (0, 1):
        raise ValueError("Unsupported Uniswap quote reason version")
    if amount_in_raw is not None and (_uint(amount_in_raw, 255) == 0):
        raise ValueError("Liquidation scenario amount must be positive")
    if amount_in_raw is not None and scenario_notional_loan is not None:
        raise ValueError("Specify either raw collateral amount or a loan-token scenario")
    scenario = None
    if scenario_notional_loan is not None:
        try:
            scenario = Decimal(scenario_notional_loan)
            if not scenario.is_finite() or not 0 < scenario < 2**128:
                raise ValueError("Scenario must be positive, finite and below 2**128 loan tokens")
        except (InvalidOperation, TypeError) as problem:
            raise ValueError("Invalid loan-token scenario") from problem
    collateral, loan = collateral_token.lower(), loan_token.lower()
    observation = {
        "schema": "mirage-uniswap-v3/1", "source": "uniswap-v3", "routing_policy": routing_policy,
        "method": "geometric-twap", "status": "insufficient",
        "chain_id": anchor.chain_id, "block_number": anchor.number,
        "block_hash": anchor.hash, "block_timestamp": anchor.timestamp, "window_seconds": window,
        "collateral_token": collateral, "loan_token": loan,
        "collateral_decimals": None, "loan_decimals": None,
        "price_loan_per_collateral": None, "spot_price_loan_per_collateral": None,
        "tokens": [], "route": [], "pools": [], "evidence": [], "errors": [],
        "quote": {"status": "insufficient", "reason": "liquidation_size_not_specified"},
        "coverage": ("v3 direct four fee tiers; compare direct and WETH unsplit exits for the same input"
                     if routing_policy == ROUTING_POLICY else
                     "v3 direct four fee tiers; WETH fallback; one unsplit route"),
    }
    if quote_reason_version:
        observation["quote_reason_version"] = quote_reason_version
    if scenario is not None:
        observation["scenario"] = {"notional_loan": _decimal(scenario),
                                   "basis": "hypothetical sale in loan-token units; not borrower debt or user position"}

    def read(to: str, data: str) -> str:
        result = client.call(to, data, anchor.number)
        observation["evidence"].append(asdict(Evidence(to, data, anchor.number, result, anchor.hash)))
        return result

    def error(where: str, problem: Exception):
        # RpcClient errors are sanitized. Record type only; do not leak URLs,
        # credentials, or provider text from alternative caller implementations.
        observation["errors"].append({"where": where, "error_type": type(problem).__name__})

    decimals = {}

    def token_decimals(token: str) -> int:
        if token not in decimals:
            decimals[token] = _uint(words(read(token, DECIMALS), 1)[0], 8)
            observation["tokens"].append({"address": token, "decimals": decimals[token]})
        return decimals[token]

    if ZERO in (collateral, loan):
        observation["reason"] = "zero_token_address"
        return observation
    try:
        observation["collateral_decimals"] = token_decimals(collateral)
        observation["loan_decimals"] = token_decimals(loan)
    except (RuntimeError, ValueError) as problem:
        error("token_decimals", problem)
        observation["reason"] = "token_decimals_unavailable"
        return observation
    if collateral == loan:
        observation.update(status="ok", source="token-identity", method="identity",
                           price_loan_per_collateral="1", spot_price_loan_per_collateral="1")
        observation["quote"]["reason"] = "same_token_no_swap_required"
        return observation

    def pools_for(token_in: str, token_out: str) -> list[dict]:
        found = []
        for fee in FEE_TIERS:
            pool = {"token_in": token_in, "token_out": token_out, "fee": fee,
                    "status": "insufficient", "address": None}
            observation["pools"].append(pool)
            try:
                calldata = GET_POOL + enc_addr(token_in) + enc_addr(token_out) + uint_word(fee).hex()
                address = word_addr(words(read(FACTORY, calldata), 1)[0])
                pool["address"] = address
                if address == ZERO:
                    pool["reason"] = "pool_not_created"
                    continue
                token0 = word_addr(words(read(address, TOKEN0), 1)[0])
                token1 = word_addr(words(read(address, TOKEN1), 1)[0])
                if (token0, token1) != tuple(sorted((token_in, token_out))):
                    raise ValueError("Pool token identity mismatch")
                pool.update(token0=token0, token1=token1)
                slot = words(read(address, SLOT0), 7)
                current_tick = decode_signed(slot[1], 24)
                for value in slot[2:5]:
                    _uint(value, 16)
                _uint(slot[5], 8)
                if slot[6] != 1 or not -MAX_TICK <= current_tick <= MAX_TICK:
                    raise ValueError("Invalid or locked pool slot0")
                active = _uint(words(read(address, LIQUIDITY), 1)[0], 128)
                pool.update(sqrt_price_x96=str(slot[0]), spot_tick=current_tick,
                            observation_cardinality=slot[3], active_liquidity_raw=str(active))
                if not active or not slot[3]:
                    pool["reason"] = "no_active_liquidity_or_observations"
                    continue
                try:
                    twap_tick, harmonic = consult_values(read(address, encode_observe(window)), window)
                except (RuntimeError, ValueError) as problem:
                    error(address + ":observe", problem)
                    pool["reason"] = "observation_window_unavailable_or_invalid"
                    continue
                in_dec, out_dec = token_decimals(token_in), token_decimals(token_out)
                spot = sqrt_price(slot[0], token_in == token0, in_dec, out_dec)
                twap = tick_price(twap_tick, token_in == token0, in_dec, out_dec)
                pool.update(status="ok", mean_tick=twap_tick,
                            harmonic_mean_liquidity_raw=str(harmonic),
                            price_out_per_in=_decimal(twap), spot_price_out_per_in=_decimal(spot))
                found.append(pool)
            except (RuntimeError, ValueError) as problem:
                error(f"pool:{token_in}:{token_out}:{fee}", problem)
                pool["reason"] = "pool_read_unavailable_or_invalid"
        return found

    def deepest(pools: list[dict]) -> dict:
        return max(pools, key=lambda p: (int(p["harmonic_mean_liquidity_raw"]), -p["fee"]))

    direct = pools_for(collateral, loan)
    route = [deepest(direct)] if direct else []
    exit_routes = [route] if route else []
    compare_weth = routing_policy == ROUTING_POLICY and (scenario is not None or amount_in_raw is not None)
    if (not route or compare_weth) and WETH not in (collateral, loan):
        try:
            token_decimals(WETH)
            first, second = pools_for(collateral, WETH), pools_for(WETH, loan)
            if first and second:
                weth_route = [deepest(first), deepest(second)]
                exit_routes.append(weth_route)
                if not route:
                    route = weth_route
        except (RuntimeError, ValueError) as problem:
            error("weth_route", problem)
    if not route:
        observation["reason"] = "no_usable_reference_route"
        if amount_in_raw is not None or (quote_reason_version == 1 and scenario is not None):
            observation["quote"] = {"status": "insufficient", "reason": "no_usable_reference_route"}
            if amount_in_raw is not None:
                observation["quote"]["amount_in_raw"] = str(amount_in_raw)
        return observation
    with localcontext() as context:
        context.prec = 80
        twap, spot = Decimal(1), Decimal(1)
        for pool in route:
            twap *= Decimal(pool["price_out_per_in"])
            spot *= Decimal(pool["spot_price_out_per_in"])
        observation.update(status="ok", price_loan_per_collateral=_decimal(twap),
                           spot_price_loan_per_collateral=_decimal(spot),
                           route=[p["address"] for p in route],
                           route_selection="maximum harmonic liquidity per pair; direct preferred")
        if scenario is not None:
            amount_in_raw = int(scenario / twap * Decimal(10) ** decimals[collateral])
            if not 0 < amount_in_raw < 2**255:
                observation["quote"]["reason"] = "scenario_raw_amount_out_of_range"
                return observation
        if amount_in_raw is None:
            return observation
        def quote_route(candidate_route):
            route_twap, route_spot = Decimal(1), Decimal(1)
            for pool in candidate_route:
                route_twap *= Decimal(pool["price_out_per_in"])
                route_spot *= Decimal(pool["spot_price_out_per_in"])
            quote = {"status": "insufficient", "amount_in_raw": str(amount_in_raw),
                     "route": [p["address"] for p in candidate_route], "legs": [],
                     "route_kind": "direct" if len(candidate_route) == 1 else "weth",
                     "route_twap_price_loan_per_collateral": _decimal(route_twap),
                     "route_spot_price_loan_per_collateral": _decimal(route_spot),
                     "reference_route": observation["route"],
                     "reference_price_loan_per_collateral": _decimal(twap),
                     "scope": "specified collateral sale at anchored state; fees included, gas excluded"}
            if scenario is not None:
                quote["scenario_notional_loan"] = _decimal(scenario)
                quote["scenario_basis"] = observation["scenario"]["basis"]
            amount = amount_in_raw
            for pool in candidate_route:
                try:
                    leg = decode_quote(read(QUOTER_V2, encode_quote(pool["token_in"], pool["token_out"],
                                                                 amount, pool["fee"])))
                    leg.update(pool=pool["address"], token_in=pool["token_in"], token_out=pool["token_out"],
                               fee=pool["fee"], amount_in_raw=str(amount))
                    quote["legs"].append(leg)
                    amount = int(leg["amount_out_raw"])
                except (RuntimeError, ValueError) as problem:
                    error("quoter:" + pool["address"], problem)
                    quote["reason"] = "quote_unavailable_or_full_input_consumption_unknown"
                    return quote
            input_human = Decimal(amount_in_raw) / Decimal(10) ** decimals[collateral]
            output_human = Decimal(amount) / Decimal(10) ** decimals[loan]
            execution_price = output_human / input_human
            quote.update(status="ok", amount_out_raw=str(amount),
                         execution_price_loan_per_collateral=_decimal(execution_price),
                         price_impact_bps_vs_spot=_decimal((1 - execution_price / route_spot) * 10000),
                         execution_shortfall_bps_vs_twap=_decimal((1 - execution_price / twap) * 10000))
            return quote

        candidates = [quote_route(candidate) for candidate in exit_routes]
        complete = [candidate for candidate in candidates if candidate["status"] == "ok"]
        # All candidates start with the same input. Never select a route by
        # comparing nominal scenarios independently converted at different TWAPs.
        chosen = max(complete, key=lambda q: int(q["amount_out_raw"])) if complete else candidates[0]
        observation["quote"] = {**chosen, "candidates": candidates,
                                "selection": ("greatest quoted loan output for the same collateral input; gas excluded"
                                              if routing_policy == ROUTING_POLICY else "legacy direct-first route"),
                                "candidate_count": len(candidates)}
    return observation


def replay_reference(observation: dict) -> dict:
    """Rebuild derived prices/quote from saved raw calls, with no RPC fallback.

    Snapshots are evidence records, not signed attestations: this checks internal
    consistency, not whether a malicious writer fabricated the raw RPC results.
    A missing required call produces INSUFFICIENT, never a network request.
    """
    if not isinstance(observation, dict) or observation.get("schema") != "mirage-uniswap-v3/1":
        raise ValueError("Unsupported Uniswap observation schema")
    anchor = BlockAnchor(observation["chain_id"], observation["block_number"],
                         observation["block_hash"], observation.get("block_timestamp", 0))
    raw_calls = {}
    for item in observation.get("evidence", []):
        evidence = Evidence(**item)
        if (evidence.method != "eth_call" or type(evidence.block) is not int
                or evidence.block != anchor.number or evidence.block_hash != anchor.hash):
            raise ValueError("Uniswap saved call provenance mismatch")
        enc_addr(evidence.to)
        hex_bytes(evidence.data)
        hex_bytes(evidence.result)
        key = (evidence.to.lower(), evidence.data.lower())
        if key in raw_calls and raw_calls[key] != evidence.result.lower():
            raise ValueError("Conflicting saved Uniswap call results")
        raw_calls[key] = evidence.result.lower()

    class EvidenceClient:
        def call(self, to, data, block):
            if type(block) is not int or block != anchor.number:
                raise ValueError("Uniswap replay block mismatch")
            key = (to.lower(), data.lower())
            if key not in raw_calls:
                raise RuntimeError("Required single-call evidence is missing")
            return raw_calls[key]

    scenario = observation.get("scenario", {}).get("notional_loan")
    # An explicit scenario determines its size from the rebuilt TWAP. Otherwise
    # amountIn is the declared scenario input, matched against Quoter calldata.
    amount = observation.get("quote", {}).get("amount_in_raw")
    return collect_reference(EvidenceClient(), observation["collateral_token"],
                             observation["loan_token"], anchor,
                             amount_in_raw=int(amount) if scenario is None and amount is not None else None,
                             scenario_notional_loan=scenario, window=observation["window_seconds"],
                             routing_policy=observation.get("routing_policy", LEGACY_ROUTING_POLICY),
                             quote_reason_version=observation.get("quote_reason_version", 0))
