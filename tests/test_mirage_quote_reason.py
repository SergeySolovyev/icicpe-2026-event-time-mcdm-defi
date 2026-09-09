"""No-route reason regressions over canonical ABI returns, with no network."""
import copy
import unittest

from mirage.chain.rpc import BlockAnchor
from mirage.chain.uniswap import collect_reference, replay_reference
from mirage.detectors.exit_depth import detect
from mirage.verdict import Severity


COLLATERAL = "0x" + "01" * 20
USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
FACTORY = "0x1f98431c8ad98523631ae4a59f267346ea31f984"
ANCHOR = BlockAnchor(1, 25938815,
    "0x6151b63f20f0f5fa115ccd736cf42d08759914eb60748c9b102d38a7ad9ffe00", 1788944843)


class MissingPools:
    """Synthetic valid ABI zero-address responses, never empty RPC results."""
    def __init__(self):
        self.calls = []

    def call(self, to, data, block):
        assert type(block) is int and block == ANCHOR.number
        self.calls.append((to, data, block))
        if data == "0x313ce567":
            assert to in (COLLATERAL, USDC, WETH)
            return "0x" + format(6 if to == USDC else 18, "064x")
        assert to == FACTORY and data.startswith("0x1698ee82") and len(data) == 202
        return "0x" + "00" * 32


class QuoteReasonTests(unittest.TestCase):
    def collect(self, **kwargs):
        return collect_reference(MissingPools(), COLLATERAL, USDC, ANCHOR, **kwargs)

    def test_notional_without_reference_reports_missing_route_not_missing_size(self):
        observation = self.collect(scenario_notional_loan="10000")
        self.assertEqual(observation["quote_reason_version"], 1)
        self.assertEqual(observation["scenario"]["notional_loan"], "10000")
        self.assertEqual(observation["reason"], "no_usable_reference_route")
        self.assertEqual(observation["quote"], {
            "status": "insufficient", "reason": "no_usable_reference_route"})
        self.assertIsNone(observation["price_loan_per_collateral"])
        finding = detect(observation)
        self.assertEqual(finding.code, "exit_depth_unavailable")
        self.assertEqual(finding.severity, Severity.INSUFFICIENT)
        self.assertEqual(finding.metrics["reason"], "no_usable_reference_route")
        self.assertEqual(finding.metrics["scenario_notional_loan"], "10000")
        self.assertIsNone(finding.metrics["amount_in_raw"])

    def test_missing_amount_retains_unspecified_size_reason(self):
        observation = self.collect()
        self.assertEqual(observation["quote"]["reason"], "liquidation_size_not_specified")
        self.assertNotIn("scenario", observation)
        self.assertEqual(detect(observation).severity, Severity.INSUFFICIENT)

    def test_explicit_raw_amount_keeps_its_value_when_no_route_exists(self):
        observation = self.collect(amount_in_raw=123456789)
        self.assertEqual(observation["quote"], {"status": "insufficient",
            "reason": "no_usable_reference_route", "amount_in_raw": "123456789"})
        self.assertNotIn("scenario", observation)

    def test_unversioned_legacy_observation_replays_its_complete_original_dict(self):
        for kwargs in ({}, {"scenario_notional_loan": "10000"}, {"amount_in_raw": 123456789}):
            with self.subTest(kwargs=kwargs):
                legacy = self.collect(quote_reason_version=0, **kwargs)
                original = copy.deepcopy(legacy)
                self.assertNotIn("quote_reason_version", legacy)
                expected = ("no_usable_reference_route" if "amount_in_raw" in kwargs
                            else "liquidation_size_not_specified")
                self.assertEqual(legacy["quote"]["reason"], expected)
                self.assertEqual(replay_reference(legacy), original)
                self.assertEqual(legacy, original)

    def test_versioned_replay_preserves_correct_reasons_and_evidence(self):
        for kwargs in ({}, {"scenario_notional_loan": "10000"}, {"amount_in_raw": 123456789}):
            with self.subTest(kwargs=kwargs):
                observation = self.collect(**kwargs)
                self.assertEqual(replay_reference(observation), observation)

    def test_unknown_reason_version_is_rejected_before_any_call(self):
        for version in (2, -1, True, "1"):
            client = MissingPools()
            with self.subTest(version=version), self.assertRaises(ValueError):
                collect_reference(client, COLLATERAL, USDC, ANCHOR, quote_reason_version=version)
            self.assertFalse(client.calls)


if __name__ == "__main__":
    unittest.main()
