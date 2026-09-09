"""Offline core regressions; run with stdlib unittest, without ML dependencies.

Optional eth_abi comparisons independently verify the handwritten ABI subset.
All RPC and Graph interactions below use deterministic fake transports.
"""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mirage.chain.codec import decode_aggregate3, encode_aggregate3, uint_word
from mirage.chain.morpho import MarketParams, MarketState
from mirage.chain.rpc import BlockAnchor, RpcClient
from mirage.chain.selectors import AGGREGATE3, MARKET, MARKET_PARAMS, MORPHO, USDC
from mirage.detectors.phantom_volume import detect
from mirage.discovery.subgraph import discover_markets
from mirage.scan import capture, load_snapshot, report_from_snapshot, save_snapshot
from mirage.verdict import Severity


MARKET_ID = "0x" + "11" * 32
BLOCK_HASH = "0x" + "ab" * 32
OTHER_HASH = "0x" + "cd" * 32
ANCHOR = BlockAnchor(1, 100, BLOCK_HASH, 1_789_000_000)
HAS_ETH_ABI = importlib.util.find_spec("eth_abi") is not None


def abi_words(*values):
    return "0x" + b"".join(uint_word(value) for value in values).hex()


def aggregate_result(results):
    """Canonical ABI fixture builder, compared against eth_abi when available."""
    tuples = []
    offsets = []
    offset = 32 * len(results)
    for success, value in results:
        payload = bytes.fromhex(value[2:])
        encoded = (
            uint_word(int(success)) + uint_word(64) + uint_word(len(payload))
            + payload + b"\0" * (-len(payload) % 32)
        )
        offsets.append(uint_word(offset))
        tuples.append(encoded)
        offset += len(encoded)
    return "0x" + (
        uint_word(32) + uint_word(len(results)) + b"".join(offsets) + b"".join(tuples)
    ).hex()


def valid_snapshot():
    params = abi_words(int(USDC, 16), 2, 3, 4, 860_000_000_000_000_000)
    state = abi_words(1_000_000, 1_000_000_000_000, 300_000, 300_000_000_000, 123, 0)
    evidence = [
        {"to": MORPHO, "data": selector + MARKET_ID[2:], "block": ANCHOR.number,
         "result": raw, "block_hash": BLOCK_HASH, "method": "eth_call"}
        for selector, raw in ((MARKET_PARAMS, params), (MARKET, state))
    ]
    return {
        "schema": "mirage-snapshot/1",
        "anchor": {"chain_id": 1, "number": 100, "hash": BLOCK_HASH, "timestamp": ANCHOR.timestamp},
        "source": {"kind": "explicit-market", "market_count": 1},
        "rows": [{"market_id": MARKET_ID, "evidence": evidence}],
    }


def graph_response(ids=None, *, number=100, block_hash=BLOCK_HASH,
                   deployment="QmTestDeployment", indexing_errors=False):
    data = {"_meta": {"deployment": deployment, "hasIndexingErrors": indexing_errors,
                      "block": {"number": number, "hash": block_hash}}}
    if ids is not None:
        data["markets"] = [{"id": value} for value in ids]
    return {"data": data}


class AbiTests(unittest.TestCase):
    def test_multicall_count_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "count"):
            decode_aggregate3(aggregate_result([(True, "0x12")]), 2)

    def test_multicall_truncated_tuple_body_is_rejected(self):
        encoded = aggregate_result([(True, "0x" + "55" * 64)])
        with self.assertRaisesRegex(ValueError, "Truncated"):
            decode_aggregate3(encoded[:-64], 1)

    def test_multicall_trailing_garbage_and_nonzero_padding_are_rejected(self):
        encoded = aggregate_result([(True, "0x12")])
        for damaged in (encoded + "00" * 32, encoded[:-2] + "01"):
            with self.subTest(damaged=damaged[-66:]):
                with self.assertRaises(ValueError):
                    decode_aggregate3(damaged, 1)

    def test_multicall_bad_offsets_and_bool_are_rejected(self):
        raw = bytearray.fromhex(aggregate_result([(True, "0x12")])[2:])
        for word_offset, new_value in ((64, 0), (96, 2), (128, 96)):
            damaged = bytearray(raw)
            damaged[word_offset:word_offset + 32] = uint_word(new_value)
            with self.subTest(offset=word_offset):
                with self.assertRaises(ValueError):
                    decode_aggregate3("0x" + damaged.hex(), 1)

    def test_multicall_keeps_failure_and_empty_response_distinct(self):
        expected = [(True, "0x"), (False, "0xdeadbeef"), (True, "0x" + "12" * 70)]
        self.assertEqual(decode_aggregate3(aggregate_result(expected), 3), expected)
        self.assertEqual(decode_aggregate3(aggregate_result([]), 0), [])

    @unittest.skipUnless(HAS_ETH_ABI, "optional eth_abi is not installed")
    def test_multicall_encoding_matches_independent_eth_abi(self):
        from eth_abi import decode, encode
        calls = [(USDC, "0x"), (MORPHO, "0x" + "01" * 37)]
        expected_args = [(address.lower(), True, bytes.fromhex(data[2:])) for address, data in calls]
        actual = bytes.fromhex(encode_aggregate3(calls)[len(AGGREGATE3):])
        self.assertEqual(actual, encode(["(address,bool,bytes)[]"], [expected_args]))
        decoded = decode(["(address,bool,bytes)[]"], actual)[0]
        self.assertEqual(tuple((a.lower(), b, c) for a, b, c in decoded), tuple(expected_args))

    @unittest.skipUnless(HAS_ETH_ABI, "optional eth_abi is not installed")
    def test_multicall_decoding_matches_independent_eth_abi(self):
        from eth_abi import encode
        results = [(True, b""), (False, b"bad"), (True, bytes(range(100)))]
        encoded = "0x" + encode(["(bool,bytes)[]"], [results]).hex()
        expected = [(success, "0x" + raw.hex()) for success, raw in results]
        self.assertEqual(decode_aggregate3(encoded, len(results)), expected)
        self.assertEqual(encoded, aggregate_result(expected))

    def test_market_decoding_rejects_empty_and_wrong_width(self):
        for raw in ("0x", abi_words(0, 0, 0, 0, 0), abi_words(2**128, 0, 0, 0, 0, 0)):
            with self.subTest(raw=raw[:20]):
                with self.assertRaises(ValueError):
                    MarketState.decode(raw)
        with self.assertRaisesRegex(ValueError, "padding"):
            MarketParams.decode(abi_words(2**160, 0, 0, 0, 0))


class AccountingTests(unittest.TestCase):
    def test_supply_shares_are_not_deposit_principal_after_interest(self):
        # Alice supplies 1 USDC at genesis; interest doubles assets; Bob supplies
        # 1 USDC and receives shares at the current virtual-share exchange rate.
        alice_shares = 1_000_000 * 1_000_000
        bob_shares = 1_000_000 * (alice_shares + 1_000_000) // (2_000_000 + 1)
        shares = alice_shares + bob_shares
        self.assertNotEqual(shares // 1_000_000, 2_000_000)  # actual deposits = 2 USDC
        finding = detect(MarketState(3_000_000, shares, 1_500_000, 1, 123, 0))
        self.assertIsNone(finding.metrics["principal"])
        self.assertEqual(finding.metrics["available_liquidity_raw"], "1500000")

    def test_virtual_shares_change_small_balance_exchange_rate(self):
        finding = detect(MarketState(2, 1_000_000, 0, 0, 123, 0))
        self.assertEqual(finding.metrics["share_price_multiple_vs_initial"], "1.500000000000")
        self.assertIsNone(finding.metrics["principal"])

    def test_created_empty_market_has_no_nan_or_division_by_zero(self):
        finding = detect(MarketState(0, 0, 0, 0, 123, 0))
        self.assertIsNone(finding.metrics["utilization"])
        self.assertEqual(finding.metrics["share_price_multiple_vs_initial"], "1.000000000000")
        self.assertEqual(finding.severity, Severity.PASS)
        json.dumps(finding.metrics, allow_nan=False)

    def test_uncreated_market_is_insufficient(self):
        finding = detect(MarketState(0, 0, 0, 0, 0, 0))
        self.assertEqual((finding.code, finding.severity), ("market_not_created", Severity.INSUFFICIENT))

    def test_zero_free_liquidity_is_policy_block_not_invented_principal(self):
        finding = detect(MarketState(6_212_914_536_395_500, 93_828_252_743_194_492,
                                    6_212_914_536_395_500, 93_709_222_461_198_075, 123, 0))
        self.assertEqual(finding.code, "no_free_liquidity")
        self.assertEqual(finding.severity, Severity.BLOCK)
        self.assertEqual(finding.metrics["available_liquidity_raw"], "0")
        self.assertIsNone(finding.metrics["principal"])

    def test_elevated_share_rate_is_warning_not_proof_of_phantom_assets(self):
        finding = detect(MarketState(100, 1_000_000, 10, 1, 123, 0))
        self.assertEqual(finding.severity, Severity.WARN)
        self.assertEqual(finding.code, "elevated_share_exchange_rate")

    def test_invalid_accounting_returns_insufficient(self):
        for state in (MarketState(-1, 0, 0, 0, 123, 0),
                      MarketState(1, 0, 2, 0, 123, 0),
                      MarketState(2**128, 0, 0, 0, 123, 0)):
            with self.subTest(state=state):
                self.assertEqual(detect(state).severity, Severity.INSUFFICIENT)

    def test_threshold_rejects_nan_infinity_and_noninteger_values(self):
        for threshold in (float("nan"), float("inf"), 0, -1, 1.5, True):
            with self.subTest(threshold=threshold):
                with self.assertRaises(ValueError):
                    detect(MarketState(1, 1_000_000, 0, 0, 123, 0),
                           max_share_price_multiple=threshold)


class SnapshotTests(unittest.TestCase):
    def test_evidence_replays_exact_raw_values_and_remaining_checks_stay_insufficient(self):
        report = report_from_snapshot(valid_snapshot())
        verdict = report.markets[0]
        self.assertEqual(verdict.findings[0].metrics["available_liquidity_raw"], "700000")
        self.assertEqual(verdict.severity, Severity.INSUFFICIENT)
        self.assertEqual(len(verdict.findings[0].evidence), 2)
        self.assertIsNone(verdict.findings[0].metrics["principal"])
        json.dumps(report.to_dict(), allow_nan=False)

    def test_snapshot_rejects_wrong_target_calldata_block_hash_method_and_count(self):
        changes = {"to": USDC, "data": "0x1234", "block": 99,
                   "block_hash": OTHER_HASH, "method": "eth_getCode"}
        for key, value in changes.items():
            snapshot = valid_snapshot()
            snapshot["rows"][0]["evidence"][0][key] = value
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, "provenance"):
                    report_from_snapshot(snapshot)
        snapshot = valid_snapshot()
        snapshot["rows"][0]["evidence"].pop()
        with self.assertRaisesRegex(ValueError, "provenance"):
            report_from_snapshot(snapshot)

    def test_snapshot_rejects_empty_or_truncated_raw_response(self):
        for result in ("0x", abi_words(1, 2)):
            snapshot = valid_snapshot()
            snapshot["rows"][0]["evidence"][1]["result"] = result
            with self.assertRaises(ValueError):
                report_from_snapshot(snapshot)

    def test_snapshot_rejects_bad_chain_anchor_and_duplicate_market(self):
        for key, value in (("chain_id", 10), ("chain_id", True), ("number", "100"),
                           ("number", -1), ("timestamp", -1), ("hash", "0x1234")):
            snapshot = valid_snapshot()
            snapshot["anchor"][key] = value
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    report_from_snapshot(snapshot)
        snapshot = valid_snapshot()
        snapshot["rows"].append(copy.deepcopy(snapshot["rows"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            report_from_snapshot(snapshot)

    def test_graph_source_must_match_snapshot_anchor_offline(self):
        for block, block_hash in ((99, BLOCK_HASH), (100, OTHER_HASH), (100, None)):
            snapshot = valid_snapshot()
            snapshot["source"] = {"kind": "the-graph", "query_block": block,
                                  "query_block_hash": block_hash}
            with self.assertRaisesRegex(ValueError, "Graph and RPC"):
                report_from_snapshot(snapshot)

    def test_snapshot_requires_market_evidence_and_usdc_loan(self):
        snapshot = valid_snapshot()
        snapshot["rows"] = []
        with self.assertRaisesRegex(ValueError, "no market"):
            report_from_snapshot(snapshot)
        snapshot = valid_snapshot()
        snapshot["rows"][0]["evidence"][0]["result"] = abi_words(2, 2, 3, 4, 0)
        with self.assertRaisesRegex(ValueError, "USDC"):
            report_from_snapshot(snapshot)

    def test_snapshot_save_is_reproducible_and_never_overwrites(self):
        snapshot = valid_snapshot()
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.json.gz"
            second = Path(directory) / "second.json.gz"
            save_snapshot(first, snapshot)
            save_snapshot(second, snapshot)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(load_snapshot(first), snapshot)
            with self.assertRaises(FileExistsError):
                save_snapshot(first, snapshot)


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.ids = ["0x" + f"{value:064x}" for value in range(1, 4)]

    def test_pagination_is_pinned_sorted_and_requests_only_identifiers(self):
        responses = [graph_response(number=105), graph_response(self.ids[:2]),
                     graph_response(self.ids[2:])]
        with patch("mirage.discovery.subgraph.post_json", side_effect=responses) as transport:
            discovery = discover_markets(100, url="https://example.invalid/graph", page_size=2)
        self.assertEqual(discovery.market_ids, tuple(self.ids))
        self.assertEqual(discovery.source["query_block_hash"], BLOCK_HASH)
        self.assertEqual(discovery.source["market_count"], 3)
        calls = [call.args[1] for call in transport.call_args_list[1:]]
        self.assertEqual([call["variables"]["block"] for call in calls], [100, 100])
        self.assertEqual(calls[1]["variables"]["cursor"], self.ids[1])
        for call in calls:
            for forbidden in ("supplyAssets", "borrowAssets", "tvl", "totalSupply", "price"):
                self.assertNotIn(forbidden, call["query"])
            self.assertEqual(call["variables"]["loan"], USDC)

    def test_unindexed_or_indexing_error_stops_before_market_query(self):
        for response in (graph_response(number=99), graph_response(indexing_errors=True)):
            with patch("mirage.discovery.subgraph.post_json", return_value=response) as transport:
                with self.assertRaises(RuntimeError):
                    discover_markets(100, url="https://example.invalid")
            self.assertEqual(transport.call_count, 1)

    def test_graph_error_has_no_fallback_and_does_not_expose_url_secrets(self):
        with patch("mirage.discovery.subgraph.post_json", side_effect=OSError("secret-url-key")):
            with self.assertRaisesRegex(RuntimeError, "no fallback") as caught:
                discover_markets(100, url="https://example.invalid/secret-url-key")
        self.assertNotIn("secret-url-key", str(caught.exception))
        with patch("mirage.discovery.subgraph.post_json", return_value={"errors": [{"message": "no"}]}):
            with self.assertRaises(RuntimeError):
                discover_markets(100, url="https://example.invalid")

    def test_duplicate_or_unordered_ids_are_rejected(self):
        for ids in ([self.ids[1], self.ids[0]], [self.ids[0], self.ids[0]]):
            with patch("mirage.discovery.subgraph.post_json",
                       side_effect=[graph_response(), graph_response(ids)]):
                with self.assertRaisesRegex(ValueError, "pagination"):
                    discover_markets(100, url="https://example.invalid")

    def test_changed_deployment_number_or_hash_is_rejected(self):
        changed_pages = [graph_response(self.ids[1:2], deployment="QmOther"),
                         graph_response(self.ids[1:2], number=101),
                         graph_response(self.ids[1:2], block_hash=OTHER_HASH)]
        for changed in changed_pages:
            with patch("mirage.discovery.subgraph.post_json",
                       side_effect=[graph_response(), graph_response(self.ids[:1]), changed]):
                with self.assertRaises(RuntimeError):
                    discover_markets(100, url="https://example.invalid", page_size=1)

    def test_no_entities_is_failure_not_successful_empty_scan(self):
        with patch("mirage.discovery.subgraph.post_json",
                   side_effect=[graph_response(), graph_response([])]):
            with self.assertRaisesRegex(RuntimeError, "no USDC"):
                discover_markets(100, url="https://example.invalid")

    def test_missing_metadata_and_unknown_indexing_state_fail_closed(self):
        for meta in (None, {"deployment": "x", "block": {"number": 100, "hash": BLOCK_HASH}}):
            with patch("mirage.discovery.subgraph.post_json", return_value={"data": {"_meta": meta}}):
                with self.assertRaises(RuntimeError):
                    discover_markets(100, url="https://example.invalid")


class RpcAnchorTests(unittest.TestCase):
    def test_latest_is_resolved_before_eth_call(self):
        client = RpcClient(endpoints=["https://example.invalid"], tries=1)
        responses = ["0x1", {"number": "0x64", "hash": BLOCK_HASH, "timestamp": "0x123"}, "0x12"]
        with patch.object(client, "rpc", side_effect=responses) as transport:
            anchor = client.anchor("latest")
            self.assertEqual(client.call(USDC, "0x1234", anchor.number), "0x12")
        self.assertEqual(transport.call_args_list[-1].args,
                         ("eth_call", [{"to": USDC, "data": "0x1234"}, "0x64"]))
        for block in ("latest", True, -1):
            with self.assertRaises(ValueError):
                client.call(USDC, "0x1234", block)

    def test_truncated_multicall_recovers_with_single_calls_at_same_block(self):
        client = RpcClient(endpoints=["https://example.invalid"], tries=1)
        calls = [(USDC, "0x1234"), (MORPHO, "0x5678")]
        with patch.object(client, "call", side_effect=["0x", "0x11", "0x22"]) as transport:
            self.assertEqual(client.multicall(calls, 100), [(True, "0x11"), (True, "0x22")])
        self.assertEqual([call.args[-1] for call in transport.call_args_list], [100, 100, 100])
        self.assertEqual(transport.call_args_list[1].args, (USDC, "0x1234", 100))
        self.assertEqual(transport.call_args_list[2].args, (MORPHO, "0x5678", 100))

    def test_capture_uses_two_single_calls_and_rechecks_anchor(self):
        class FakeClient:
            def __init__(self):
                self.calls = []
                self.anchor_requests = []

            def call(self, to, data, block):
                self.calls.append((to, data, block))
                for item in valid_snapshot()["rows"][0]["evidence"]:
                    if data == item["data"]:
                        return item["result"]
                raise AssertionError("Unexpected call")

            def anchor(self, block):
                self.anchor_requests.append(block)
                return ANCHOR

        client = FakeClient()
        snapshot = capture(client, ANCHOR, [MARKET_ID], {"kind": "explicit-market"})
        self.assertEqual([call[-1] for call in client.calls], [100, 100])
        self.assertEqual(client.anchor_requests, [100])
        self.assertEqual(report_from_snapshot(snapshot).markets[0].market_id, MARKET_ID)
        with patch.object(client, "anchor", return_value=BlockAnchor(1, 100, OTHER_HASH, 123)):
            with self.assertRaisesRegex(ValueError, "hash changed"):
                capture(client, ANCHOR, [MARKET_ID], {"kind": "explicit-market"})

    def test_rpc_envelope_id_mismatch_is_rejected_without_secret_leak(self):
        client = RpcClient(endpoints=["https://example.invalid/secret-key"], tries=1)
        with patch("mirage.chain.rpc.post_json", return_value={"jsonrpc": "2.0", "id": 999, "result": "0x1"}):
            with self.assertRaises(RuntimeError) as caught:
                client.rpc("eth_chainId", [])
        self.assertNotIn("secret-key", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
