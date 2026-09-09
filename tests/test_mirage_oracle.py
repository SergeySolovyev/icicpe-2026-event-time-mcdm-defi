"""Deterministic oracle edge cases; fake chain data is not mainnet evidence."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from mirage.bytecode import inspect_bytecode, UPSTREAM_SHA256
from mirage.chain.oracle import collect_oracle, validate_oracle, ADDRESS_GETTERS, ORACLE_GETTERS, FACTORY_MEMBERSHIP, ZERO_ADDRESS
from mirage.chain.rpc import BlockAnchor
from mirage.chain.selectors import FACTORY, PRICE
from mirage.detectors.frozen_price import detect, normalize_price
from mirage.verdict import Severity


ADDRESS = "0x" + "12" * 20
FEED = "0x" + "34" * 20
ANCHOR = BlockAnchor(1, 2_000_000, "0x" + "ab" * 32, 1_700_000_000)
PREVIOUS = BlockAnchor(1, 1_000_000, "0x" + "cd" * 32, 1_688_000_000)
HAS_EXTRACTOR = all(importlib.util.find_spec(name) is not None
                    for name in ("pyevmasm", "numpy", "scipy", "sklearn", "pandas", "joblib"))


def word(value):
    return "0x" + int(value).to_bytes(32, "big").hex()


def observation():
    return {
        "address": ADDRESS, "block_number": ANCHOR.number, "block_hash": ANCHOR.hash,
        "timestamp": ANCHOR.timestamp, "code_length": 2598, "code_sha256": "ab" * 32,
        "current_price": str(10**24), "previous_price": str(10**24),
        "previous_block": PREVIOUS.number, "previous_block_hash": PREVIOUS.hash,
        "factory_verified": True, "template": "morpho-chainlink-oracle-v2",
        "getters": {**{name: ZERO_ADDRESS for name in ADDRESS_GETTERS},
                    "SCALE_FACTOR": str(10**24), "BASE_VAULT_CONVERSION_SAMPLE": "1",
                    "QUOTE_VAULT_CONVERSION_SAMPLE": "1"},
        "collateral_decimals": 18, "loan_decimals": 6, "feed_rounds": [], "evidence": [],
    }


def reference(price="1"):
    return {"status": "ok", "source": "uniswap-v3", "price_loan_per_collateral": price,
            "block_number": ANCHOR.number, "block_hash": ANCHOR.hash, "evidence": []}


def dynamic_observation():
    value = observation()
    value["getters"]["BASE_FEED_1"] = FEED
    value["previous_price"] = str(99 * 10**22)
    value["feed_rounds"] = [{"address": FEED, "answer": "100000000", "updated_at": ANCHOR.timestamp - 60}]
    return value


class FakeRpc:
    def __init__(self):
        self.calls = []
        self.responses = {PRICE: word(10**24)}
        self.responses.update({selector: word(0 if name in ADDRESS_GETTERS else
                                              10**24 if name == "SCALE_FACTOR" else 1)
                               for name, selector in ORACLE_GETTERS.items()})
        self.historical_code = "0x60016000f3"
        self.member = 1
        self.hash_changed = False

    def call(self, to, data, block):
        self.calls.append((to, data, block))
        if to.lower() == FACTORY.lower() and data.startswith(FACTORY_MEMBERSHIP):
            return word(self.member)
        value = self.responses.get(data, "0x")
        if isinstance(value, Exception):
            raise value
        return value

    def code(self, to, block):
        return self.historical_code if block == PREVIOUS.number else "0x60016000f3"

    def anchor(self, block):
        if block == ANCHOR.number:
            return PREVIOUS if self.hash_changed else ANCHOR
        return PREVIOUS


class OracleCollectionTests(unittest.TestCase):
    def test_collects_all_nine_getters_and_individual_evidence(self):
        client = FakeRpc()
        value = collect_oracle(client, ADDRESS, ANCHOR)
        self.assertEqual(value["template"], "morpho-chainlink-oracle-v2")
        self.assertEqual(set(value["getters"]), set(ORACLE_GETTERS))
        self.assertEqual(value["current_price"], str(10**24))
        self.assertEqual(value["previous_price"], str(10**24))
        self.assertEqual(len(value["evidence"]), 12)
        self.assertEqual(len(value["code_references"]), 2)
        self.assertEqual(value["code_references"][0]["sha256"], hashlib.sha256(bytes.fromhex("60016000f3")).hexdigest())
        self.assertNotIn("code", value)
        json.dumps(value, allow_nan=False)

    def test_empty_price_response_is_missing_not_frozen(self):
        client = FakeRpc()
        client.responses[PRICE] = "0x"
        value = collect_oracle(client, ADDRESS, ANCHOR)
        self.assertEqual(value["code_length"], 5)
        self.assertIsNone(value["current_price"])
        self.assertEqual(detect(value).severity, Severity.INSUFFICIENT)

    def test_historical_no_code_does_not_become_zero_price(self):
        client = FakeRpc()
        client.historical_code = "0x"
        value = collect_oracle(client, ADDRESS, ANCHOR)
        self.assertIsNone(value["previous_price"])
        self.assertEqual(value["previous_code_length"], 0)
        self.assertFalse(any(data == PRICE and block == PREVIOUS.number for _, data, block in client.calls))

    def test_unknown_factory_uses_bytecode_even_if_getters_match(self):
        client = FakeRpc()
        client.member = 0
        with patch("mirage.chain.oracle.inspect_bytecode", return_value={"status": "ok", "features_extracted": True}) as inspect:
            value = collect_oracle(client, ADDRESS, ANCHOR)
        inspect.assert_called_once_with("0x60016000f3")
        self.assertEqual(value["template"], "unsupported")
        self.assertEqual(detect(value).severity, Severity.INSUFFICIENT)

    def test_noncanonical_address_word_prevents_template_acceptance(self):
        client = FakeRpc()
        client.responses[ORACLE_GETTERS["QUOTE_FEED_2"]] = word(2**160)
        with patch("mirage.chain.oracle.inspect_bytecode", return_value={"status": "ok"}):
            value = collect_oracle(client, ADDRESS, ANCHOR)
        self.assertNotIn("QUOTE_FEED_2", value["getters"])
        self.assertEqual(value["template"], "unsupported")

    def test_reorg_refuses_observation(self):
        client = FakeRpc()
        client.hash_changed = True
        with self.assertRaisesRegex(ValueError, "block hash changed"):
            collect_oracle(client, ADDRESS, ANCHOR)

    def test_transient_historical_recheck_failure_is_not_a_scan_abort(self):
        client = FakeRpc()
        original = client.anchor
        counts = {}
        def unreliable_anchor(number):
            counts[number] = counts.get(number, 0) + 1
            if number == PREVIOUS.number and counts[number] > 1:
                raise RuntimeError("temporary RPC failure")
            return original(number)
        client.anchor = unreliable_anchor
        value = collect_oracle(client, ADDRESS, ANCHOR)
        self.assertFalse(value["previous_anchor_verified"])
        self.assertTrue(value["anchor_verified"])
        self.assertEqual(validate_oracle(value), value)

    def test_transient_current_recheck_failure_cannot_pass(self):
        client = FakeRpc()
        original = client.anchor
        def unreliable_anchor(number):
            if number == ANCHOR.number:
                raise RuntimeError("temporary RPC failure")
            return original(number)
        client.anchor = unreliable_anchor
        value = collect_oracle(client, ADDRESS, ANCHOR)
        self.assertFalse(value["anchor_verified"])
        self.assertEqual(detect(value).severity, Severity.INSUFFICIENT)
        self.assertEqual(validate_oracle(value), value)

    def test_replay_derives_same_oracle_without_network(self):
        value = collect_oracle(FakeRpc(), ADDRESS, ANCHOR)
        self.assertEqual(validate_oracle(value), value)

    def test_replay_rejects_changed_derived_values(self):
        original = collect_oracle(FakeRpc(), ADDRESS, ANCHOR)
        for key, changed in (("current_price", "7"), ("factory_verified", False),
                             ("code_length", 2598), ("code_sha256", "aa" * 32)):
            value = copy.deepcopy(original)
            value[key] = changed
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "differs from its evidence"):
                validate_oracle(value)

    def test_replay_rejects_wrong_historical_evidence_anchor(self):
        value = collect_oracle(FakeRpc(), ADDRESS, ANCHOR)
        value["evidence"][-1]["block_hash"] = ANCHOR.hash
        with self.assertRaisesRegex(ValueError, "recorded block anchor"):
            validate_oracle(value)

    def test_replay_rejects_modified_raw_code_when_digest_is_unchanged(self):
        value = collect_oracle(FakeRpc(), ADDRESS, ANCHOR)
        value["runtime_code"] = "0x60026000f3"
        with self.assertRaisesRegex(ValueError, "differs from its evidence"):
            validate_oracle(value)


class FrozenPriceTests(unittest.TestCase):
    def test_constant_configuration_is_warning_not_automatic_block(self):
        result = detect(observation())
        self.assertEqual(result.severity, Severity.WARN)
        self.assertTrue(result.metrics["constant_configuration"])
        self.assertFalse(result.metrics["samples_prove_interval_constancy"])

    def test_sixth_getter_matters(self):
        value = observation()
        value["getters"]["QUOTE_FEED_2"] = FEED
        result = detect(value)
        self.assertFalse(result.metrics["constant_configuration"])
        self.assertEqual(result.severity, Severity.INSUFFICIENT)

    def test_same_asset_nominal_is_valid(self):
        value = observation()
        value.update(collateral_decimals=6, current_price=str(10**36))
        value["getters"]["SCALE_FACTOR"] = str(10**36)
        self.assertEqual(detect(value, same_asset=True).severity, Severity.PASS)

    def test_same_asset_wrong_nominal_is_blocked(self):
        value = observation()
        value.update(collateral_decimals=6)
        self.assertEqual(detect(value, same_asset=True).severity, Severity.BLOCK)

    def test_equal_samples_of_dynamic_oracle_are_not_frozen_proof(self):
        value = dynamic_observation()
        value["previous_price"] = value["current_price"]
        result = detect(value)
        self.assertEqual(result.code, "oracle_equal_samples")
        self.assertEqual(result.severity, Severity.WARN)
        self.assertFalse(result.metrics["constant_configuration"])

    def test_reference_deviation_blocks_and_uses_human_units(self):
        result = detect(observation(), reference=reference("0.9"))
        self.assertEqual(result.code, "oracle_reference_deviation")
        self.assertEqual(result.severity, Severity.BLOCK)
        self.assertEqual(result.metrics["price_loan_per_collateral"], "1.000000000000000000000000")
        self.assertGreater(float(result.metrics["deviation_bps"]), 1111)

    def test_exact_policy_boundary_is_not_exceeded(self):
        value = observation()
        value["current_price"] = str(105 * 10**22)
        value["getters"]["SCALE_FACTOR"] = value["current_price"]
        self.assertEqual(detect(value, reference=reference("1")).severity, Severity.WARN)

    def test_changed_block_reference_cannot_block_oracle(self):
        independent = reference("0.01")
        independent["block_hash"] = PREVIOUS.hash
        result = detect(observation(), reference=independent)
        self.assertEqual(result.severity, Severity.WARN)
        self.assertFalse(result.metrics["reference_comparable"])

    def test_unknown_template_always_remains_insufficient(self):
        value = observation()
        value["factory_verified"] = False
        self.assertEqual(detect(value, reference=reference("0.1")).severity, Severity.INSUFFICIENT)

    def test_malformed_decimal_references_do_not_block(self):
        for price in ("NaN", "Infinity", "-1", "0", ""):
            with self.subTest(price=price):
                self.assertEqual(detect(observation(), reference=reference(price)).severity, Severity.WARN)

    def test_no_reference_units_no_comparison(self):
        value = observation()
        del value["loan_decimals"]
        result = detect(value, reference=reference("0.1"))
        self.assertEqual(result.severity, Severity.WARN)
        self.assertIsNone(result.metrics["price_loan_per_collateral"])

    def test_configured_feed_invalid_timestamp_is_not_passed(self):
        value = dynamic_observation()
        value["feed_rounds"][0]["updated_at"] = ANCHOR.timestamp + 1
        self.assertEqual(detect(value).severity, Severity.INSUFFICIENT)

    def test_valid_dynamic_oracle_sample_change(self):
        self.assertEqual(detect(dynamic_observation()).code, "oracle_changed_samples")

    def test_morpho_normalization_decimals(self):
        self.assertEqual(normalize_price(10**24, 18, 6), 1)
        self.assertEqual(normalize_price(10**36, 6, 6), 1)
        self.assertEqual(normalize_price(65_000 * 10**34, 8, 6), 65_000)

    def test_fractional_and_boolean_prices_cannot_be_truncated_into_uints(self):
        for price in (True, 1.5, "1.5", -1):
            value = observation()
            value["current_price"] = price
            with self.subTest(price=price):
                self.assertEqual(detect(value).severity, Severity.INSUFFICIENT)


class BytecodeTests(unittest.TestCase):
    def test_vendor_hash_is_exact_upstream_copy(self):
        vendor = Path(__file__).parents[1] / "mirage/vendor/revert_pro/evm_extractor.py"
        self.assertEqual(hashlib.sha256(vendor.read_bytes()).hexdigest(), UPSTREAM_SHA256)

    def test_invalid_and_empty_bytecode_are_explicit(self):
        self.assertEqual(inspect_bytecode("0xzz")["status"], "malformed")
        self.assertEqual(inspect_bytecode("0x")["status"], "empty")
        self.assertFalse(inspect_bytecode("0x")["features_extracted"])

    def test_missing_extractor_does_not_zero_fill(self):
        with patch("mirage.bytecode._extractor", side_effect=ImportError("missing")):
            value = inspect_bytecode("0x6001")
        self.assertEqual(value["status"], "unavailable")
        self.assertFalse(value["features_extracted"])
        self.assertNotIn("structural_features", value)

    @unittest.skipUnless(HAS_EXTRACTOR, "Install requirements-mirage.txt for the original extractor")
    def test_real_original_extractor_invoked_and_candidates_are_bounded(self):
        from mirage.bytecode import _extractor
        original = _extractor()
        code = "0x73" + "73" * 20 + "73" + "34" * 20 + "00"
        with patch.object(original, "_extract_features_single", wraps=original._extract_features_single) as call:
            value = inspect_bytecode(code, max_candidates=1)
        call.assert_called_once()
        self.assertTrue(value["features_extracted"])
        self.assertEqual(value["feature_count"], 70)
        self.assertEqual(value["candidate_count"], 2)
        self.assertEqual(value["push_candidates"][0]["pc"], 0)
        self.assertTrue(value["candidates_truncated"])
        self.assertFalse(any("risk" in key or "vulnerab" in key for key in value["structural_features"]))
        json.dumps(value, allow_nan=False)

    @unittest.skipUnless(HAS_EXTRACTOR, "Install requirements-mirage.txt for the original extractor")
    def test_exact_eip1167_implementation(self):
        code = "0x363d3d373d3d3d363d73" + FEED[2:] + "5af43d82803e903d91602b57fd5bf3"
        self.assertEqual(inspect_bytecode(code)["eip1167_implementation"], FEED)

    @unittest.skipUnless(HAS_EXTRACTOR, "Install requirements-mirage.txt for the original extractor")
    def test_truncated_push_is_malformed_even_if_original_returns_zeros(self):
        result = inspect_bytecode("0x7f01", diagnostics_version=1)
        self.assertTrue(result["truncated_push"])
        self.assertEqual(result["status"], "malformed")


class RecordedMainnetTests(unittest.TestCase):
    """Regression on actual single-call evidence captured 2026-09-09.

    This replays a fixed historical snapshot; it is not a fresh network check.
    """
    @unittest.skipUnless(HAS_EXTRACTOR, "Original extractor needed to replay the custom oracle")
    def test_recorded_mainnet_evidence_replays_without_rpc(self):
        path = Path(__file__).parent / "fixtures/mirage_oracle_mainnet-25937912.json"
        fixture = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(fixture["kind"], "live-mainnet-single-call-capture")
        self.assertEqual(fixture["block_number"], 25937912)
        rows = [validate_oracle(row) for row in fixture["rows"]]
        self.assertEqual(len(rows), 3)
        constant, custom, dynamic = rows
        self.assertEqual(constant["address"], "0x1325eb089ac14b437e78d5d481e32611f6907ef8")
        self.assertEqual(constant["current_price"], str(10**24))
        self.assertEqual(constant["previous_price"], str(10**24))
        self.assertEqual(constant["code_length"], 2598)
        self.assertEqual(detect(constant).code, "oracle_constant_configuration")
        self.assertEqual(detect(custom).severity, Severity.INSUFFICIENT)
        self.assertEqual(custom["bytecode"]["feature_count"], 70)
        self.assertTrue(custom["bytecode"]["features_extracted"])
        self.assertEqual(dynamic["current_price"], "2492790000000000000000000000")
        self.assertEqual(dynamic["previous_price"], "2392342373570000000000000000")
        self.assertEqual(detect(dynamic).code, "oracle_changed_samples")
        self.assertNotIn("runtime_code", detect(constant).metrics)


if __name__ == "__main__":
    unittest.main()
