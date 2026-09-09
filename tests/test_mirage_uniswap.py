"""Uniswap ABI, direction, history and exact-size policy regressions, offline."""
import copy
from decimal import Decimal
import importlib.util
import json
import unittest

from mirage.chain.codec import uint_word
from mirage.chain.rpc import BlockAnchor
from mirage.chain import uniswap as uni
from mirage.detectors import exit_depth, reference_price
from mirage.verdict import Severity


A = "0x" + "01" * 20
B = "0x" + "02" * 20
POOL = "0x" + "11" * 20
HASH = "0x" + "ab" * 32
ANCHOR = BlockAnchor(1, 25945000, HASH, 1788970000)


def abi(*values):
    return "0x" + b"".join(uint_word(v % 2**256) for v in values).hex()


def observe(tick=0, window=1800, delta=None):
    return abi(64, 160, 2, 0, tick * window if delta is None else delta,
               2, 0, window * 2**128 // 100000)


class PoolClient:
    """Transport fixture with no price logic shared with implementation."""
    def __init__(self, *, pair=(A, B), fee=500, history=True, missing=False,
                 slippage_percent=1, decimals=None):
        self.pair, self.fee, self.history, self.missing = pair, fee, history, missing
        self.slippage_percent = slippage_percent
        self.decimals = decimals or {A: 8, B: 6, uni.WETH: 18}
        self.calls = []

    def call(self, to, data, block):
        assert type(block) is int and block == ANCHOR.number
        self.calls.append((to, data, block))
        if data == uni.DECIMALS:
            return abi(self.decimals[to])
        if data.startswith(uni.GET_POOL):
            pair = tuple("0x" + data[offset + 24:offset + 64] for offset in (10, 74))
            fee = int(data[138:202], 16)
            return abi(int(POOL, 16) if not self.missing and set(pair) == set(self.pair) and fee == self.fee else 0)
        if to == POOL:
            if data == uni.TOKEN0:
                return abi(int(min(self.pair), 16))
            if data == uni.TOKEN1:
                return abi(int(max(self.pair), 16))
            if data == uni.SLOT0:
                return abi(2**96, 0, 1, 2, 2, 0, 1)
            if data == uni.LIQUIDITY:
                return abi(100000)
            if data.startswith(uni.OBSERVE):
                if not self.history:
                    raise RuntimeError("OLD")
                return observe()
        if to == uni.QUOTER_V2 and data.startswith(uni.QUOTE_SINGLE):
            amount = int(data[138:202], 16)
            return abi(amount * (100 - self.slippage_percent) // 100, 2**96, 2, 85000)
        raise AssertionError((to, data))


class MultiRouteClient:
    """Three distinct pools; direct and WETH quotes have different outputs."""
    def __init__(self, direct_slippage=40, direct_failure=False, weth_failure=False):
        self.addresses = [POOL, "0x" + "22" * 20, "0x" + "33" * 20]
        self.clients = [PoolClient(pair=(A, B), slippage_percent=direct_slippage),
                        PoolClient(pair=(A, uni.WETH), slippage_percent=1),
                        PoolClient(pair=(uni.WETH, B), slippage_percent=1)]
        self.direct_failure, self.weth_failure = direct_failure, weth_failure

    def call(self, to, data, block):
        if data == uni.DECIMALS:
            return self.clients[0].call(to, data, block)
        if data.startswith((uni.GET_POOL, uni.QUOTE_SINGLE)):
            pair = tuple("0x" + data[offset + 24:offset + 64] for offset in (10, 74))
            for index, client in enumerate(self.clients):
                if set(pair) == set(client.pair):
                    if data.startswith(uni.QUOTE_SINGLE):
                        if (index == 0 and self.direct_failure) or (index != 0 and self.weth_failure):
                            raise RuntimeError("Quote reverted")
                        return client.call(to, data, block)
                    return client.call(to, data, block).replace(POOL[2:], self.addresses[index][2:])
        if to in self.addresses:
            return self.clients[self.addresses.index(to)].call(POOL, data, block)
        raise AssertionError((to, data))


class AbiTests(unittest.TestCase):
    def test_observe_negative_tick_rounds_down(self):
        self.assertEqual(uni.consult_values(observe(delta=-1801), 1800)[0], -2)
        self.assertEqual(uni.consult_values(observe(delta=-1800), 1800)[0], -1)

    def test_observe_positive_tick_and_harmonic(self):
        tick, harmonic = uni.consult_values(observe(delta=1801), 1800)
        self.assertEqual(tick, 1)
        self.assertTrue(99999 <= harmonic <= 100000)

    def test_cumulative_wraps_like_solidity_07(self):
        before, after = 2**55 - 10, -2**55 + 1790
        result = abi(64, 160, 2, before, after, 2, 2**160 - 100,
                     1800 * 2**128 // 100000 - 100)
        self.assertEqual(uni.consult_values(result, 1800)[0], 1)

    def test_observe_rejects_truncated_overlapping_or_noncanonical(self):
        for result in (observe()[:-2], abi(64, 64, 2, 0, 0, 2, 0, 1),
                       abi(64, 160, 2, 0, 2**56 - 1, 2, 0, 1),
                       abi(64, 160, 2, 0, 0, 2, 0, 2**160)):
            with self.subTest(result=result[:30]), self.assertRaises(ValueError):
                uni.decode_observe(result)

    def test_price_decimal_and_inverse_normalization(self):
        self.assertEqual(uni.tick_price(0, True, 8, 6), Decimal(100))
        self.assertEqual(uni.tick_price(0, False, 6, 8), Decimal("0.01"))
        self.assertEqual(uni.sqrt_price(2**96, True, 18, 6), Decimal(10)**12)
        self.assertAlmostEqual(uni.tick_price(-100, True, 18, 18)
                               * uni.tick_price(-100, False, 18, 18), Decimal(1), places=26)

    def test_signed_padding_and_tick_bounds(self):
        self.assertEqual(uni.decode_signed(2**256 - 1, 24), -1)
        with self.assertRaises(ValueError):
            uni.decode_signed(2**24 - 1, 24)
        for tick in (-887273, 887273):
            with self.assertRaises(ValueError):
                uni.tick_price(tick, True, 18, 18)

    def test_quote_tuple_order(self):
        encoded = uni.encode_quote(A, B, 123456, 500)
        self.assertEqual(encoded[:10], "0xc6a5026a")
        self.assertEqual(int(encoded[138:202], 16), 123456)
        self.assertEqual(int(encoded[202:266], 16), 500)
        self.assertEqual(int(encoded[266:330], 16), 0)

    def test_quote_rejects_partial_fill_boundaries(self):
        for sqrt in (uni.MIN_SQRT_RATIO + 1, uni.MAX_SQRT_RATIO - 1, 0):
            with self.assertRaises(ValueError):
                uni.decode_quote(abi(100, sqrt, 2, 100000))
        with self.assertRaises(ValueError):
            uni.decode_quote(abi(0, 2**96, 0, 1))

    @unittest.skipUnless(importlib.util.find_spec("eth_abi"), "optional independent ABI oracle")
    def test_matches_independent_eth_abi(self):
        from eth_abi import encode
        self.assertEqual(uni.encode_observe(1800), uni.OBSERVE + encode(["uint32[]"], [[1800, 0]]).hex())
        self.assertEqual(uni.encode_quote(A, B, 123, 500), uni.QUOTE_SINGLE +
                         encode(["(address,address,uint256,uint24,uint160)"], [(A, B, 123, 500, 0)]).hex())
        raw = "0x" + encode(["int56[]", "uint160[]"], [[0, -1801], [0, 2**128]]).hex()
        self.assertEqual(uni.decode_observe(raw), ((0, -1801), (0, 2**128)))


class CollectionTests(unittest.TestCase):
    def test_direct_pool_and_raw_evidence_are_block_pinned(self):
        client = PoolClient()
        result = uni.collect_reference(client, A, B, ANCHOR, amount_in_raw=100000000)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(Decimal(result["price_loan_per_collateral"]), Decimal(100))
        self.assertEqual(result["route"], [POOL])
        self.assertEqual(result["quote"]["amount_out_raw"], "99000000")
        self.assertEqual(len(result["evidence"]), len(client.calls))
        self.assertTrue(all(e["block"] == ANCHOR.number and e["block_hash"] == HASH for e in result["evidence"]))
        self.assertEqual(json.loads(json.dumps(result)), result)

    def test_reverse_direction(self):
        result = uni.collect_reference(PoolClient(), B, A, ANCHOR)
        self.assertEqual(Decimal(result["price_loan_per_collateral"]), Decimal("0.01"))

    def test_missing_pool_does_not_become_zero_price(self):
        result = uni.collect_reference(PoolClient(missing=True), A, B, ANCHOR, amount_in_raw=123)
        self.assertEqual(result["status"], "insufficient")
        self.assertIsNone(result["price_loan_per_collateral"])
        self.assertEqual(result["quote"]["status"], "insufficient")

    def test_insufficient_history_never_falls_back_to_spot(self):
        result = uni.collect_reference(PoolClient(history=False), A, B, ANCHOR)
        self.assertEqual(result["status"], "insufficient")
        self.assertIsNone(result["price_loan_per_collateral"])
        self.assertIn("observation_window_unavailable_or_invalid", [p.get("reason") for p in result["pools"]])

    def test_no_size_means_no_depth_claim(self):
        result = uni.collect_reference(PoolClient(), A, B, ANCHOR)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(exit_depth.detect(result).severity, Severity.INSUFFICIENT)

    def test_notional_scenario_converts_down_and_labels_hypothetical(self):
        result = uni.collect_reference(PoolClient(), A, B, ANCHOR, scenario_notional_loan="100.0000009")
        self.assertEqual(result["quote"]["amount_in_raw"], "100000000")
        self.assertEqual(result["quote"]["scenario_notional_loan"], "100.0000009")
        self.assertIn("hypothetical", result["quote"]["scenario_basis"])

    def test_identity_reference_does_not_claim_uniswap_depth(self):
        result = uni.collect_reference(PoolClient(), A, A, ANCHOR, amount_in_raw=123)
        self.assertEqual(result["source"], "token-identity")
        self.assertEqual(result["price_loan_per_collateral"], "1")
        self.assertEqual(exit_depth.detect(result).severity, Severity.INSUFFICIENT)

    def test_unsupported_decimals_and_empty_code_fail_closed(self):
        class EmptyClient:
            def call(self, *_):
                return "0x"
        self.assertEqual(uni.collect_reference(EmptyClient(), A, B, ANCHOR)["status"], "insufficient")

    def test_invalid_inputs_rejected_before_calls(self):
        for kwargs in ({"window": 0}, {"window": -1}, {"window": 2**32},
                       {"amount_in_raw": 0}, {"amount_in_raw": 2**255},
                       {"scenario_notional_loan": "NaN"}, {"scenario_notional_loan": "Infinity"},
                       {"amount_in_raw": 1, "scenario_notional_loan": "100"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                uni.collect_reference(PoolClient(), A, B, ANCHOR, **kwargs)

    def test_weth_fallback_multihop(self):
        pool2 = "0x" + "22" * 20
        first = PoolClient(pair=(A, uni.WETH))
        second = PoolClient(pair=(uni.WETH, B))

        class RouteClient:
            def call(self, to, data, block):
                if data.startswith(uni.GET_POOL):
                    if uni.enc_addr(A) in data:
                        return first.call(to, data, block)
                    result = second.call(to, data, block)
                    return result.replace(POOL[2:], pool2[2:])
                if to == pool2:
                    return second.call(POOL, data, block)
                return first.call(to, data, block)

        result = uni.collect_reference(RouteClient(), A, B, ANCHOR, amount_in_raw=100000000)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["route"], [POOL, pool2])
        self.assertEqual(Decimal(result["price_loan_per_collateral"]), Decimal(100))
        self.assertEqual(result["quote"]["amount_out_raw"], "98010000")

    def test_replay_rebuilds_derived_fields_from_raw_evidence(self):
        result = uni.collect_reference(PoolClient(), A, B, ANCHOR, scenario_notional_loan="10000")
        self.assertEqual(uni.replay_reference(result), result)
        result["price_loan_per_collateral"] = "987654321"
        result["quote"]["amount_out_raw"] = "99999999999999999"
        rebuilt = uni.replay_reference(result)
        self.assertEqual(Decimal(rebuilt["price_loan_per_collateral"]), Decimal(100))
        self.assertEqual(rebuilt["quote"]["amount_out_raw"], "9900000000")

    def test_replay_missing_quote_evidence_fails_closed_without_rpc(self):
        result = uni.collect_reference(PoolClient(), A, B, ANCHOR, amount_in_raw=100000000)
        result["evidence"] = [e for e in result["evidence"] if e["to"] != uni.QUOTER_V2]
        rebuilt = uni.replay_reference(result)
        self.assertEqual(rebuilt["status"], "ok")
        self.assertEqual(rebuilt["quote"]["status"], "insufficient")
        self.assertEqual(exit_depth.detect(rebuilt).severity, Severity.INSUFFICIENT)

    def test_replay_rejects_conflicting_returns_and_wrong_method(self):
        result = uni.collect_reference(PoolClient(), A, B, ANCHOR)
        duplicated = copy.deepcopy(result)
        duplicated["evidence"].append(dict(duplicated["evidence"][0], result=abi(18)))
        with self.assertRaises(ValueError):
            uni.replay_reference(duplicated)
        result["evidence"][0]["method"] = "eth_getCode"
        with self.assertRaises(ValueError):
            uni.replay_reference(result)

    def test_better_weth_exit_does_not_change_reference_or_scenario_amount(self):
        result = uni.collect_reference(MultiRouteClient(), A, B, ANCHOR, scenario_notional_loan="10000")
        quote = result["quote"]
        self.assertEqual(result["routing_policy"], uni.ROUTING_POLICY)
        self.assertEqual(result["route"], [POOL])
        self.assertEqual(quote["route_kind"], "weth")
        self.assertEqual(quote["amount_out_raw"], "9801000000")
        self.assertEqual({q["amount_in_raw"] for q in quote["candidates"]}, {"10000000000"})
        self.assertEqual([q["amount_out_raw"] for q in quote["candidates"]], ["6000000000", "9801000000"])
        self.assertTrue(all(q["reference_route"] == [POOL] for q in quote["candidates"]))
        self.assertEqual(exit_depth.detect(result).severity, Severity.PASS)
        self.assertEqual(len(exit_depth.detect(result).metrics["candidate_routes"]), 2)
        self.assertEqual(uni.replay_reference(result), result)

    def test_direct_exit_is_kept_when_its_output_is_better(self):
        result = uni.collect_reference(MultiRouteClient(direct_slippage=1), A, B, ANCHOR,
                                       scenario_notional_loan="10000")
        self.assertEqual(result["quote"]["route_kind"], "direct")
        self.assertEqual(result["quote"]["candidate_count"], 2)
        self.assertEqual(result["quote"]["amount_out_raw"], "9900000000")

    def test_bad_direct_quote_does_not_suppress_usable_weth_quote(self):
        result = uni.collect_reference(MultiRouteClient(direct_failure=True), A, B, ANCHOR,
                                       amount_in_raw=10000000000)
        self.assertEqual(result["quote"]["status"], "ok")
        self.assertEqual(result["quote"]["route_kind"], "weth")
        self.assertEqual(result["quote"]["candidates"][0]["status"], "insufficient")

    def test_weth_quote_failure_preserves_direct_coverage(self):
        result = uni.collect_reference(MultiRouteClient(direct_slippage=1, weth_failure=True),
                                       A, B, ANCHOR, amount_in_raw=10000000000)
        self.assertEqual(result["quote"]["status"], "ok")
        self.assertEqual(result["quote"]["route_kind"], "direct")
        self.assertEqual(result["quote"]["candidates"][1]["status"], "insufficient")

    def test_legacy_snapshot_preserves_direct_first_routing(self):
        result = uni.collect_reference(MultiRouteClient(), A, B, ANCHOR,
                                       scenario_notional_loan="10000", routing_policy=uni.LEGACY_ROUTING_POLICY)
        self.assertEqual(result["quote"]["route_kind"], "direct")
        self.assertEqual(result["quote"]["candidate_count"], 1)
        self.assertEqual(exit_depth.detect(result).severity, Severity.BLOCK)
        del result["routing_policy"]
        replayed = uni.replay_reference(result)
        self.assertEqual(replayed["routing_policy"], uni.LEGACY_ROUTING_POLICY)
        self.assertEqual(replayed["quote"]["amount_out_raw"], "6000000000")
        self.assertEqual(exit_depth.detect(replayed).severity, Severity.BLOCK)

    def test_unknown_routing_policy_is_not_silently_reinterpreted(self):
        with self.assertRaises(ValueError):
            uni.collect_reference(PoolClient(), A, B, ANCHOR, routing_policy="future-unknown")


class PolicyTests(unittest.TestCase):
    def observation(self, slippage=1):
        return uni.collect_reference(PoolClient(slippage_percent=slippage), A, B, ANCHOR,
                                     amount_in_raw=100000000)

    def test_reference_pass_divergence_block_and_movement_warn(self):
        observation = self.observation()
        self.assertEqual(reference_price.detect(observation, oracle_price_loan_per_collateral="100").severity, Severity.PASS)
        self.assertEqual(reference_price.detect(observation, oracle_price_loan_per_collateral="110").severity, Severity.BLOCK)
        observation["spot_price_loan_per_collateral"] = "120"
        self.assertEqual(reference_price.detect(observation).severity, Severity.WARN)

    def test_exit_within_and_beyond_threshold(self):
        self.assertEqual(exit_depth.detect(self.observation()).severity, Severity.PASS)
        result = exit_depth.detect(self.observation(slippage=6))
        self.assertEqual(result.severity, Severity.BLOCK)
        self.assertEqual(Decimal(result.metrics["price_impact_bps_vs_spot"]), Decimal(600))

    def test_exit_recomputes_impact_and_does_not_trust_display_field(self):
        observation = self.observation(slippage=6)
        observation["quote"]["price_impact_bps_vs_spot"] = "0"
        self.assertEqual(exit_depth.detect(observation).severity, Severity.BLOCK)

    def test_exit_compares_execution_to_twap_as_well_as_spot(self):
        observation = self.observation()
        observation["price_loan_per_collateral"] = "150"
        self.assertEqual(exit_depth.detect(observation).severity, Severity.BLOCK)

    def test_exit_uses_selected_route_spot_with_unchanged_reference_twap(self):
        observation = self.observation()
        observation["spot_price_loan_per_collateral"] = "500"
        # Route spot remains 100; a reference-only spot edit must not become
        # execution price impact on another selected route.
        finding = exit_depth.detect(observation)
        self.assertEqual(finding.severity, Severity.PASS)
        self.assertEqual(Decimal(finding.metrics["price_impact_bps_vs_spot"]), Decimal(100))
        observation["quote"]["route_spot_price_loan_per_collateral"] = "200"
        self.assertEqual(exit_depth.detect(observation).severity, Severity.BLOCK)

    def test_bad_anchors_fail_both_detectors_closed(self):
        observation = self.observation()
        observation["evidence"][0]["block"] += 1
        self.assertEqual(exit_depth.detect(observation).severity, Severity.INSUFFICIENT)
        self.assertEqual(reference_price.detect(observation).severity, Severity.INSUFFICIENT)

    def test_nonfinite_price_is_never_a_pass(self):
        for price in ("NaN", "Infinity", "0", "-1"):
            observation = self.observation()
            observation["price_loan_per_collateral"] = price
            self.assertEqual(exit_depth.detect(observation).severity, Severity.INSUFFICIENT)
            self.assertEqual(reference_price.detect(observation).severity, Severity.INSUFFICIENT)

    def test_detectors_do_not_mutate_observation(self):
        observation = self.observation()
        before = copy.deepcopy(observation)
        reference_price.detect(observation)
        exit_depth.detect(observation)
        self.assertEqual(before, observation)

    def test_malformed_top_level_fails_closed(self):
        for invalid in (None, [], "oops"):
            self.assertEqual(reference_price.detect(invalid).severity, Severity.INSUFFICIENT)
            self.assertEqual(exit_depth.detect(invalid).severity, Severity.INSUFFICIENT)
        self.assertEqual(exit_depth.detect({"quote": []}).severity, Severity.INSUFFICIENT)
        self.assertEqual(exit_depth.detect({"quote": {"candidates": [None]}}).severity, Severity.INSUFFICIENT)


if __name__ == "__main__":
    unittest.main()
