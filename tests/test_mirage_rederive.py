"""Offline immutable diagnostic migration over the actual saved demo evidence."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import mirage_rederive_snapshot as migration
from mirage.chain.uniswap import replay_reference
from mirage.scan import load_snapshot, report_from_snapshot


SOURCE = Path(__file__).resolve().parents[1] / "mirage/snapshots/mainnet-full-25938082-routes-v2.json.gz"


class RederiveTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name) / "derived.json.gz"
        for target in ("mirage.chain.rpc.post_json", "mirage.discovery.subgraph.post_json"):
            guard = patch(target, side_effect=AssertionError("Migration must never contact a provider"))
            guard.start()
            self.addCleanup(guard.stop)

    def test_actual_demo_changes_only_versioned_diagnostics_and_keeps_parent_proof(self):
        before_bytes = SOURCE.read_bytes()
        before = load_snapshot(SOURCE)
        result = migration.rederive_snapshot(SOURCE, self.output)
        after = load_snapshot(self.output)
        self.assertEqual(SOURCE.read_bytes(), before_bytes)
        self.assertEqual(result["parent_sha256"], hashlib.sha256(before_bytes).hexdigest())
        self.assertEqual(after["derivation"]["parent_filename"], SOURCE.name)
        self.assertEqual(after["derivation"]["new_network_calls"], 0)
        counts = after["derivation"]["recorded_evidence"]
        self.assertEqual(counts["unique_eth_call_results"], 185)
        self.assertEqual(counts["unique_runtime_code_results"], 8)
        self.assertEqual(counts["unique_saved_rpc_results"], 193)
        self.assertEqual(migration.encoded(migration.protected_content(before)),
                         migration.encoded(migration.protected_content(after)))
        for old, new in zip(before["rows"], after["rows"]):
            self.assertEqual(replay_reference(old["reference"]), old["reference"])
            self.assertEqual(new["reference"]["quote_reason_version"], 1)
            for component in ("reference", "oracle", "rate"):
                self.assertEqual(old[component]["evidence"], new[component]["evidence"])
            for field in ("runtime_code", "previous_runtime_code", "code_references"):
                self.assertEqual(old["oracle"][field], new["oracle"][field])
        de_usd = next(row for row in after["rows"] if row["display"]["collateral_symbol"] == "deUSD")
        self.assertEqual(de_usd["reference"]["quote"]["reason"], "no_usable_reference_route")
        self.assertEqual(before["rows"][0]["oracle"]["bytecode"]["status"], "malformed")
        self.assertEqual(after["rows"][0]["oracle"]["bytecode"]["status"], "ok")
        self.assertEqual([market.severity for market in report_from_snapshot(before).markets],
                         [market.severity for market in report_from_snapshot(after).markets])
        without_provenance = copy.deepcopy(after)
        del without_provenance["derivation"]
        self.assertEqual(after["derivation"]["changed_derived_fields"], migration.changes(before, without_provenance))

    def test_code_result_counts_deduplicate_identities_and_reject_conflicts(self):
        source = load_snapshot(SOURCE)
        counts = migration.evidence_counts(source)
        duplicate = copy.deepcopy(source["rows"][0]["oracle"]["code_references"][0])
        source["rows"][0]["oracle"]["code_references"].append(duplicate)
        repeated = migration.evidence_counts(source)
        self.assertEqual(repeated["runtime_code_records"], counts["runtime_code_records"] + 1)
        self.assertEqual(repeated["unique_runtime_code_results"], counts["unique_runtime_code_results"])
        duplicate["sha256"] = "00" * 32
        with self.assertRaisesRegex(ValueError, "Conflicting recorded bytecode"):
            migration.evidence_counts(source)

    def test_corrupt_source_is_rejected_before_rederivation(self):
        source = load_snapshot(SOURCE)
        source["rows"][0]["evidence"][0]["block_hash"] = "0x" + "00" * 32
        bad = Path(self.directory.name) / "corrupt.json"
        bad.write_text(json.dumps(source), encoding="utf-8")
        with patch.object(migration, "inspect_bytecode") as inspect:
            with self.assertRaises(ValueError):
                migration.rederive_snapshot(bad, self.output)
        inspect.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_changed_raw_result_from_replay_is_rejected(self):
        def changed(observation):
            result = replay_reference(observation)
            result["evidence"][0]["result"] = "0x" + "00" * 32
            return result
        with patch.object(migration, "replay_reference", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "Unexpected changed field"):
                migration.rederive_snapshot(SOURCE, self.output)
        self.assertFalse(self.output.exists())

    def test_existing_output_is_never_replaced(self):
        self.output.write_bytes(b"existing immutable artifact")
        with self.assertRaises(FileExistsError):
            migration.rederive_snapshot(SOURCE, self.output)
        self.assertEqual(self.output.read_bytes(), b"existing immutable artifact")

    def test_late_output_collision_keeps_existing_file(self):
        real_link = migration.os.link
        def collision(source, destination):
            Path(destination).write_bytes(b"another publisher won")
            real_link(source, destination)
        with patch.object(migration.os, "link", side_effect=collision):
            with self.assertRaises(FileExistsError):
                migration.rederive_snapshot(SOURCE, self.output)
        self.assertEqual(self.output.read_bytes(), b"another publisher won")
        self.assertEqual(list(Path(self.directory.name).iterdir()), [self.output])


if __name__ == "__main__":
    unittest.main()
