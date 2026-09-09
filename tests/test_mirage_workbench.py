"""Workbench boundary tests using committed chain evidence; no network calls."""
import copy
from dataclasses import asdict
from decimal import Decimal
import http.client
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer

from mirage.allocator import compare, scenario_amount
from mirage.chain.codec import uint_word
from mirage.chain.morpho import MarketParams, MarketState
from mirage.chain.rates import BORROW_RATE_VIEW, collect_rate, replay_rate
from mirage.chain.rpc import BlockAnchor, RpcClient
from mirage.scan import load_snapshot
from mirage.server import Application, Sessions, WorkbenchHTTPServer, handler_for, serve

SNAPSHOT = Path(__file__).resolve().parents[1] / "mirage/snapshots/mainnet-25937912.json.gz"
FULL_SNAPSHOT = SNAPSHOT.parent / "mainnet-full-25938082.json.gz"


class RateTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = load_snapshot(SNAPSHOT)
        self.anchor = BlockAnchor(**self.snapshot["anchor"])
        self.row = self.snapshot["rows"][0]
        self.params = MarketParams.decode(self.row["evidence"][0]["result"])
        self.state = MarketState.decode(self.row["evidence"][1]["result"])

    def test_selector_and_tuple_against_independent_abi(self):
        from eth_abi import encode
        from eth_utils import keccak
        from dataclasses import astuple
        signature = "borrowRateView((address,address,address,address,uint256),(uint128,uint128,uint128,uint128,uint128,uint128))"
        expected = "0x" + keccak(text=signature)[:4].hex()
        self.assertEqual(BORROW_RATE_VIEW, expected)
        encoded = expected + encode(["(address,address,address,address,uint256)", "(uint128,uint128,uint128,uint128,uint128,uint128)"],
                                    [astuple(self.params), astuple(self.state)]).hex()
        class Reader:
            def call(inner, to, data, block):
                self.assertEqual((to, data, block), (self.params.irm, encoded, self.anchor.number))
                return "0x" + uint_word(10**9).hex()
        result = collect_rate(Reader(), self.params, self.state, self.anchor)
        self.assertEqual(Decimal(result["supply_apr"]), Decimal("0.031536"))

    def test_replay_ignores_edited_apr_and_rejects_wrong_anchor(self):
        class Reader:
            def call(inner, *args):
                return "0x" + uint_word(10**9).hex()
        result = collect_rate(Reader(), self.params, self.state, self.anchor)
        result["supply_apr"] = "9999999999"
        replayed = replay_rate(result, self.params, self.state, self.anchor)
        self.assertEqual(Decimal(replayed["supply_apr"]), Decimal("0.031536"))
        result["evidence"][0]["block"] += 1
        with self.assertRaises(ValueError):
            replay_rate(result, self.params, self.state, self.anchor)

    def test_missing_rate_does_not_turn_into_zero_apr(self):
        result = replay_rate({}, self.params, self.state, self.anchor)
        self.assertEqual(result["status"], "insufficient")
        self.assertNotIn("supply_apr", result)

    def test_amount_boundary(self):
        for value in ("NaN", "Infinity", "0", "-1", "0.0000001", "1000000001"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                scenario_amount(value)
        self.assertEqual(scenario_amount("123.123456"), "123.123456")

    def test_original_policy_actually_runs_and_gate_vetoes_zero_liquidity(self):
        class Reader:
            def call(inner, *args):
                return "0x" + uint_word(10**9).hex()
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["rows"] = snapshot["rows"][:1]
        snapshot["rows"][0]["rate"] = collect_rate(Reader(), self.params, self.state, self.anchor)
        result = compare(snapshot, amount_usdc="10000")
        self.assertEqual(result["original"]["kind"], "switch")
        self.assertEqual(result["gated"]["kind"], "hold")
        self.assertEqual(result["market_id"], self.row["market_id"])
        self.assertEqual(result["candidate_count"], 1)
        self.assertIn("exit_scenario_not_checked", result["gated"]["rationale"])

    def test_transport_keeps_healthy_endpoint_until_failure(self):
        seen = []
        def post(url, body, **kwargs):
            seen.append(url)
            return {"jsonrpc": "2.0", "id": body["id"], "result": "0x1"}
        with patch("mirage.chain.rpc.post_json", post):
            client = RpcClient(["https://one.invalid", "https://two.invalid"])
            client.rpc("eth_chainId", [])
            client.rpc("eth_chainId", [])
        self.assertEqual(seen, ["https://one.invalid"] * 2)


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Application(SNAPSHOT)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(cls.app))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        result = response.status, response.read()
        connection.close()
        return result

    def test_saved_report_discloses_partial_scope_and_block(self):
        status, body = self.request("GET", "/api/report")
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(data["block_number"], 25937912)
        self.assertEqual(data["source"]["kind"], "explicit-market")
        self.assertIn("partial", data["scope"])

    def test_cross_origin_scan_does_not_start(self):
        with patch.object(self.app, "start_scan") as start:
            status, _ = self.request("POST", "/api/scan", "{}", {"Origin": "https://example.com"})
            self.assertEqual(status, 403)
            start.assert_not_called()

    def test_invalid_scan_amount_is_rejected_before_thread(self):
        status, _ = self.request("POST", "/api/scan", '{"amount_usdc":"NaN"}')
        self.assertEqual(status, 400)
        self.assertEqual(self.app.get_status()["state"], "idle")

    def test_static_routes_cannot_read_repo_or_key(self):
        for path in ("/../README.md", "/.graph-deploy-key", "/mirage/server.py"):
            self.assertEqual(self.request("GET", path)[0], 404)

    def test_html_css_js_are_served(self):
        for path in ("/", "/style.css", "/app.js"):
            status, body = self.request("GET", path)
            self.assertEqual(status, 200)
            self.assertGreater(len(body), 100)


class FullEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = load_snapshot(FULL_SNAPSHOT)

    def test_original_t1_and_gate_diverge_for_paxg_on_real_evidence(self):
        result = compare(self.snapshot, market_id=self.snapshot["rows"][0]["market_id"])
        self.assertEqual((result["original"]["kind"], result["gated"]["kind"]), ("switch", "hold"))
        self.assertIn("no_free_liquidity", result["gated"]["rationale"])

    def test_positive_control_retains_proposal_but_different_size_requires_refresh(self):
        weth = self.snapshot["rows"][3]["market_id"]
        result = compare(self.snapshot, market_id=weth)
        self.assertEqual((result["original"]["kind"], result["gated"]["kind"]), ("switch", "switch"))
        self.assertTrue(result["scenario_matches"])
        changed = compare(self.snapshot, market_id=weth, amount_usdc="1000000")
        self.assertEqual(changed["gated"]["kind"], "hold")
        self.assertFalse(changed["scenario_matches"])

    def test_editing_global_amount_does_not_rebind_quote(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["scenario_notional_loan"] = "1000000"
        result = compare(snapshot, market_id=snapshot["rows"][3]["market_id"], amount_usdc="1000000")
        self.assertEqual(result["gated"]["kind"], "hold")
        self.assertFalse(result["scenario_matches"])

    def test_editing_rate_display_does_not_change_ranking(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["rows"][3]["rate"]["supply_apr"] = "9999999"
        self.assertEqual(compare(snapshot)["market_id"], snapshot["rows"][0]["market_id"])


class PublicSessionTests(unittest.TestCase):
    def test_public_bind_requires_explicit_origin_before_loading_evidence(self):
        with patch("mirage.server.Application") as application:
            with self.assertRaises(ValueError):
                serve(bind="0.0.0.0")
            with self.assertRaises(ValueError):
                serve(bind="0.0.0.0", public_origin="https://demo.example/path")
            application.assert_not_called()

    def test_report_provenance_is_bound_to_snapshot_not_background_status(self):
        app = Application(SNAPSHOT)
        app.status.update(state="complete", mode="live")
        self.assertEqual(app.get_report()["capture_mode"], "saved")
        app.snapshot_mode = "live"
        app.status.update(state="running", mode="saved")
        self.assertEqual(app.get_report()["capture_mode"], "live")
        app.status["state"] = "complete"
        app.reset_demo()
        self.assertEqual(app.get_report()["capture_mode"], "saved")

    def test_server_cannot_share_a_port_with_another_http_application(self):
        app = Application(SNAPSHOT)
        server = WorkbenchHTTPServer(("127.0.0.1", 0), handler_for(app))
        try:
            with self.assertRaises(OSError):
                other = ThreadingHTTPServer(server.server_address, handler_for(app))
                other.server_close()
        finally:
            server.server_close()

    def test_distinct_visitors_cannot_replace_each_others_reports(self):
        sessions = Sessions(lambda: Application(SNAPSHOT))
        token_a, app_a = sessions.get(None)
        token_b, app_b = sessions.get(None)
        app_a.snapshot = {**app_a.snapshot, "rows": app_a.snapshot["rows"][:1]}
        self.assertNotEqual(token_a, token_b)
        self.assertEqual(len(sessions.get(token_a)[1].get_report()["markets"]), 1)
        self.assertEqual(len(sessions.get(token_b)[1].get_report()["markets"]), 2)
        app_a.reset_demo()
        self.assertEqual(len(app_a.get_report()["markets"]), 2)

    def test_reset_cannot_race_an_active_capture(self):
        app = Application(SNAPSHOT)
        app.status["state"] = "running"
        with self.assertRaises(ValueError):
            app.reset_demo()

    def test_session_limit_never_evicts_a_running_capture(self):
        sessions = Sessions(lambda: Application(SNAPSHOT), max_sessions=1)
        token, app = sessions.get(None)
        app.status["state"] = "running"
        with self.assertRaises(RuntimeError):
            sessions.get(None)
        self.assertIs(sessions.get(token)[1], app)

    def test_only_the_exact_public_origin_is_accepted(self):
        app = Application(SNAPSHOT)
        sessions = Sessions(lambda: Application(SNAPSHOT))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(app, public_origin="https://demo.example", sessions=sessions))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            connection.request("GET", "/", headers={"Origin": "https://demo.example"})
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.status, 200)
            cookie = response.getheader("Set-Cookie")
            self.assertIn("Secure", cookie)
            self.assertIn("HttpOnly", cookie)
            connection.close()
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            connection.request("GET", "/style.css", headers={"Host": "demo.example"})
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.status, 200)
            self.assertIsNone(response.getheader("Set-Cookie"))
            connection.close()
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            connection.request("POST", "/api/demo", "{}", {"Origin": "https://demo.example.attacker.invalid", "Cookie": cookie.split(";")[0]})
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.status, 403)
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
