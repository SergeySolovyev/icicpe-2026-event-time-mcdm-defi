"""Versioned diagnostics retain exact extraction and strict legacy replay."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

from mirage.bytecode import inspect_bytecode, _extractor, UPSTREAM_SHA256
from mirage.chain.oracle import collect_oracle, validate_oracle
from mirage.chain.rpc import BlockAnchor
from mirage.chain.selectors import FACTORY, PRICE


# Synthetic return-42 runtime, followed by the exact metadata trailer observed
# on 0x74aab1207092dcb2837dea4070bc307750b3ddfa at block 25938815.
# Metadata is still passed to the unmodified upstream extractor in full.
TRAILER = "a26469706673582212208ceb6551765ef644f74d294b6828ab559b3cb3bd587f0469a708731c6bdcc02164736f6c634300081a0033"
RUNTIME = "0x602a60005260206000f3fe" + TRAILER
ADDRESS = "0x" + "12" * 20
ANCHOR = BlockAnchor(1, 1_500_000, "0x" + "ab" * 32, 2_000_000)
PREVIOUS = BlockAnchor(1, 500_000, "0x" + "cd" * 32, 1_000_000)


class RecordedCalls:
    def anchor(self, number):
        return {ANCHOR.number: ANCHOR, PREVIOUS.number: PREVIOUS}[number]

    def code(self, address, number):
        return RUNTIME

    def call(self, address, data, number):
        if address.lower() == FACTORY.lower():
            return "0x" + "00" * 32
        if address == ADDRESS and data == PRICE:
            return "0x" + format(42, "064x")
        raise RuntimeError("No recorded getter")


class BytecodeMetadataTests(unittest.TestCase):
    def test_metadata_walk_is_not_runtime_malformation(self):
        result = inspect_bytecode(RUNTIME)
        self.assertEqual(result["diagnostics_version"], 2)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["truncated_push"])
        self.assertGreaterEqual(result["truncated_push_offset"], len(bytes.fromhex(RUNTIME[2:])) - 53)
        self.assertIn("not EVM semantic validity", result["interpretation"])
        self.assertNotIn("eip1167_implementation", result)

    def test_full_unmodified_runtime_still_has_original_70_features(self):
        raw = bytes.fromhex(RUNTIME[2:])
        original = {key: float(value) for key, value in _extractor()._extract_features_single(raw).items()}
        result = inspect_bytecode(raw)
        self.assertEqual(len(original), 70)
        digest = hashlib.sha256(json.dumps(original, sort_keys=True, allow_nan=False).encode()).hexdigest()
        self.assertEqual(result["features_sha256"], digest)
        self.assertEqual(result["code_sha256"], hashlib.sha256(raw).hexdigest())
        vendor = Path(__file__).parents[1] / "mirage/vendor/revert_pro/evm_extractor.py"
        self.assertEqual(hashlib.sha256(vendor.read_bytes()).hexdigest(), UPSTREAM_SHA256)

    def test_legacy_and_version_two_oracle_observations_replay_exactly(self):
        for version in (1, 2):
            observation = collect_oracle(RecordedCalls(), ADDRESS, ANCHOR, bytecode_diagnostics_version=version)
            self.assertEqual(validate_oracle(observation)["bytecode"], observation["bytecode"])
            self.assertEqual(observation["bytecode"]["status"], "malformed" if version == 1 else "ok")
            if version == 1:
                self.assertNotIn("diagnostics_version", observation["bytecode"])
            changed = copy.deepcopy(observation)
            changed["bytecode"]["status"] = "ok" if version == 1 else "malformed"
            with self.assertRaisesRegex(ValueError, "differs from its evidence: bytecode"):
                validate_oracle(changed)

    def test_unknown_versions_reject_without_weakening_raw_comparison(self):
        for invalid in (0, 3, "2", True, None):
            with self.assertRaisesRegex(ValueError, "Unsupported bytecode diagnostics version"):
                inspect_bytecode(RUNTIME, diagnostics_version=invalid)
            observation = collect_oracle(RecordedCalls(), ADDRESS, ANCHOR)
            observation["bytecode"]["diagnostics_version"] = invalid
            with self.assertRaisesRegex(ValueError, "Unsupported bytecode diagnostics version"):
                validate_oracle(observation)

    def test_invalid_hex_is_still_malformed(self):
        self.assertEqual(inspect_bytecode("0xxyz")["status"], "malformed")


if __name__ == "__main__":
    unittest.main()
