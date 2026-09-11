"""Optional SDK integration tests; all network boundaries are stubbed."""
import asyncio
from copy import deepcopy
from datetime import timedelta
from importlib.metadata import version
import json
from pathlib import Path
import sys
import threading
from unittest.mock import Mock

import pytest

pytest.importorskip("mcp.server.fastmcp", reason="Install requirements-mirage-mcp.txt")
sdk_version = tuple(int(part) for part in version("mcp").split(".")[:3])
if sdk_version < (1, 30, 0) or sdk_version >= (2, 0, 0):
    pytest.skip("Install the pinned requirements-mirage-mcp.txt SDK", allow_module_level=True)
memory = pytest.importorskip("mcp.shared.memory")

from mirage import mcp_server
from mirage.allocator import compare
from mirage.chain.rpc import BlockAnchor
from mirage.discovery.subgraph import Discovery
from mirage.scan import load_snapshot, report_from_snapshot


SNAPSHOT = Path(__file__).parents[1] / "mirage/snapshots/mainnet-25937912.json.gz"
connect = memory.create_connected_server_and_client_session


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def saved():
    return load_snapshot(SNAPSHOT)


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("This MCP test must not access a network")
    monkeypatch.setattr("mirage.chain.rpc.post_json", forbidden)
    monkeypatch.setattr("mirage.discovery.subgraph.post_json", forbidden)


def payload(result):
    assert result.structuredContent == json.loads(result.content[0].text)
    json.dumps(result.structuredContent, allow_nan=False)
    return result.structuredContent


@pytest.mark.anyio
async def test_real_tool_listing_and_saved_report_without_network(monkeypatch, saved):
    rpc = Mock(side_effect=AssertionError("RPC client must not be created"))
    graph = Mock(side_effect=AssertionError("Graph must not be called"))
    monkeypatch.setattr(mcp_server, "CachingRpcClient", rpc)
    monkeypatch.setattr(mcp_server, "discover_markets", graph)
    server = mcp_server.create_server(snapshot_path=SNAPSHOT)
    async with connect(server, raise_exceptions=True) as client:
        listing = await client.list_tools()
        tools = {tool.name: tool for tool in listing.tools}
        assert set(tools) == {"get_saved_report", "inspect_market", "preview_saved_allocation"}
        assert tools["inspect_market"].inputSchema["required"] == ["market_id"]
        assert all(tool.annotations.readOnlyHint for tool in tools.values())
        result = await client.call_tool("get_saved_report", {"include_evidence": True})
    assert not result.isError
    actual = payload(result)
    expected = json.loads(json.dumps(report_from_snapshot(saved).to_dict()))
    assert actual["markets"] == expected["markets"]
    assert actual["block_hash"] == saved["anchor"]["hash"]
    assert actual["mode"] == "saved"
    assert all(market["severity"] != "pass" for market in actual["markets"])
    rpc.assert_not_called()
    graph.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("arguments", [
    {"market_id": "0x1234"},
    {"market_id": "0x" + "a" * 40},
    {"market_id": "0x" + "g" * 64},
    {"market_id": "0x" + "a" * 64, "amount_usdc": "NaN"},
    {"market_id": "0x" + "a" * 64, "amount_usdc": "0"},
    {"market_id": "0x" + "a" * 64, "amount_usdc": "1.0000001"},
])
async def test_invalid_inspection_rejected_before_rpc_or_graph(monkeypatch, arguments):
    rpc, graph = Mock(), Mock()
    monkeypatch.setattr(mcp_server, "CachingRpcClient", rpc)
    monkeypatch.setattr(mcp_server, "discover_markets", graph)
    async with connect(mcp_server.create_server(), raise_exceptions=True) as client:
        result = await client.call_tool("inspect_market", arguments)
    assert result.isError
    assert payload(result)["error"]["code"] == "invalid_input"
    rpc.assert_not_called()
    graph.assert_not_called()


@pytest.mark.anyio
async def test_saved_preview_is_real_allocator_replay(saved):
    pytest.importorskip("pandas")
    market = saved["rows"][0]["market_id"]
    async with connect(mcp_server.create_server(snapshot_path=SNAPSHOT), raise_exceptions=True) as client:
        result = await client.call_tool("preview_saved_allocation", {"market_id": market, "amount_usdc": "123"})
    assert not result.isError
    actual = payload(result)
    expected = compare(saved, amount_usdc="123", market_id=market)
    assert actual["original"] == expected["original"]
    assert actual["gated"] == expected["gated"]
    assert actual["scenario_matches"] is False
    assert actual["evidence_mode"] == "saved"


@pytest.mark.anyio
async def test_absent_saved_market_is_explicit_error():
    async with connect(mcp_server.create_server(snapshot_path=SNAPSHOT), raise_exceptions=True) as client:
        result = await client.call_tool("preview_saved_allocation", {"market_id": "0x" + "0" * 64})
    assert result.isError
    assert payload(result)["error"]["code"] == "market_not_saved"


def live_stubs(monkeypatch, saved, market_ids=None):
    anchor = BlockAnchor(**saved["anchor"])
    market = saved["rows"][0]["market_id"]
    source = {"kind": "the-graph", "query_block": anchor.number,
              "query_block_hash": anchor.hash, "deployment": "test-only-deployment"}
    rpc = Mock()
    rpc.anchor.return_value = anchor
    rpc_factory = Mock(return_value=rpc)
    graph = Mock(return_value=Discovery(tuple(market_ids if market_ids is not None else [market]), source))
    monkeypatch.setattr(mcp_server, "CachingRpcClient", rpc_factory)
    monkeypatch.setattr(mcp_server, "discover_markets", graph)
    return anchor, market, rpc, graph


@pytest.mark.anyio
@pytest.mark.parametrize("include_evidence", [False, True])
async def test_live_discovery_gates_full_capture_at_same_hash(monkeypatch, saved, include_evidence):
    anchor, market, rpc, graph = live_stubs(monkeypatch, saved)
    captured = deepcopy(saved)
    captured["rows"] = [captured["rows"][0]]
    def capture(client, block, ids, source, **kwargs):
        graph.assert_called_once_with(anchor.number, block_hash=anchor.hash, url="https://graph.invalid/query")
        assert client is rpc and block == anchor and ids == (market,)
        assert kwargs == {"full_checks": True, "scenario_notional_loan": "10000"}
        captured["source"] = source
        return captured
    capture_mock = Mock(side_effect=capture)
    monkeypatch.setattr(mcp_server, "capture", capture_mock)
    async with connect(mcp_server.create_server(snapshot_path=SNAPSHOT, graph_url="https://graph.invalid/query"),
                       raise_exceptions=True) as client:
        live_result = await client.call_tool("inspect_market", {"market_id": market,
                                                                "include_evidence": include_evidence})
        saved_result = await client.call_tool("get_saved_report", {"include_evidence": True})
    assert not live_result.isError
    actual = payload(live_result)
    assert actual["mode"] == "live_capture"
    assert actual["block_hash"] == anchor.hash
    assert actual["source"]["inspected_market_count"] == 1
    assert actual["schema"] == ("mirage-feed/1" if include_evidence else "mirage-agent-summary/1")
    assert type(actual["captured_at"]) is int
    assert payload(saved_result)["source"] == saved["source"]
    assert payload(saved_result)["mode"] == "saved"
    rpc.anchor.assert_called_once_with("finalized")
    capture_mock.assert_called_once()


@pytest.mark.anyio
async def test_undiscovered_market_never_reaches_capture(monkeypatch, saved):
    _, market, _, _ = live_stubs(monkeypatch, saved, market_ids=[])
    capture_mock = Mock()
    monkeypatch.setattr(mcp_server, "capture", capture_mock)
    async with connect(mcp_server.create_server(), raise_exceptions=True) as client:
        result = await client.call_tool("inspect_market", {"market_id": market})
    assert result.isError
    assert payload(result)["error"]["code"] == "market_not_discovered"
    capture_mock.assert_not_called()


@pytest.mark.anyio
async def test_graph_failure_is_explicit_and_does_not_leak_url(monkeypatch, saved):
    _, market, _, graph = live_stubs(monkeypatch, saved)
    graph.side_effect = RuntimeError("https://provider.invalid/private-key-value")
    capture_mock = Mock()
    monkeypatch.setattr(mcp_server, "capture", capture_mock)
    async with connect(mcp_server.create_server(), raise_exceptions=True) as client:
        result = await client.call_tool("inspect_market", {"market_id": market})
    assert result.isError
    assert payload(result)["error"]["stage"] == "graph_discovery"
    assert "private-key-value" not in result.model_dump_json()
    capture_mock.assert_not_called()


@pytest.mark.anyio
async def test_graph_hash_mismatch_fails_before_market_rpc(monkeypatch, saved):
    _, market, rpc, graph = live_stubs(monkeypatch, saved)
    graph.return_value.source["query_block_hash"] = "0x" + "0" * 64
    async with connect(mcp_server.create_server(), raise_exceptions=True) as client:
        result = await client.call_tool("inspect_market", {"market_id": market})
    assert result.isError
    assert payload(result)["error"]["stage"] == "full_capture"
    assert rpc.method_calls == [("anchor", ("finalized",), {})]


@pytest.mark.anyio
async def test_saved_tools_respond_while_live_worker_waits(monkeypatch, saved):
    _, market, _, graph = live_stubs(monkeypatch, saved)
    entered, release = threading.Event(), threading.Event()
    def stalled_graph(*args, **kwargs):
        entered.set()
        release.wait(10)
        raise RuntimeError("test stops capture")
    graph.side_effect = stalled_graph
    async with connect(mcp_server.create_server(snapshot_path=SNAPSHOT), raise_exceptions=True) as client:
        pending = asyncio.create_task(client.call_tool("inspect_market", {"market_id": market}))
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            result = await asyncio.wait_for(client.call_tool("get_saved_report", {}), timeout=3)
            assert not result.isError
            busy = await client.call_tool("inspect_market", {"market_id": market})
            assert busy.isError and payload(busy)["error"]["code"] == "inspection_busy"
        finally:
            release.set()
            await pending


@pytest.mark.anyio
async def test_missing_snapshot_returns_error_not_an_empty_pass(tmp_path):
    async with connect(mcp_server.create_server(snapshot_path=tmp_path / "absent.json"),
                       raise_exceptions=True) as client:
        result = await client.call_tool("get_saved_report", {})
    assert result.isError
    assert payload(result)["error"]["code"] == "saved_evidence_unavailable"


@pytest.mark.anyio
@pytest.mark.parametrize("launcher", ["module", "absolute_script"])
async def test_stdio_full_snapshot_returns_report_and_closes(launcher, tmp_path):
    # A fresh child catches first-import native-library stalls hidden by pytest's
    # already-imported scientific dependencies. No live tool is invoked.
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    repo = Path(__file__).resolve().parents[1]
    if launcher == "module":
        args, cwd = ["-m", "mirage.mcp_server"], repo
    else:
        args, cwd = [str(repo / "scripts/mirage_mcp_server.py")], tmp_path
    params = StdioServerParameters(command=sys.executable, args=args, cwd=str(cwd))
    # tee-sys capture supplies a stream without a native fileno on Windows.
    async with stdio_client(params, errlog=sys.__stderr__) as (read, write):
        # The budget must exceed the stall this test exists to catch. Cold imports in a
        # fresh child were measured at 54.3-79.3 s on a loaded Windows host, so the former
        # 40 s limit failed there; Linux CI still finishes the file in about nine seconds.
        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=300)) as client:
            await client.initialize()
            compact_result = await client.call_tool("get_saved_report", {})
            full_result = await client.call_tool("get_saved_report", {"include_evidence": True})
    assert not compact_result.isError and not full_result.isError
    compact, full = payload(compact_result), payload(full_result)
    expected = report_from_snapshot(load_snapshot(mcp_server.default_snapshot())).to_dict()
    assert full["markets"] == json.loads(json.dumps(expected["markets"]))
    assert compact["schema"] == "mirage-agent-summary/1" and full["schema"] == "mirage-feed/1"
    assert compact["mode"] == full["mode"] == "saved"
    assert compact["block_number"] == full["block_number"] == expected["block_number"]
    assert compact["block_hash"] == full["block_hash"] == expected["block_hash"]
    assert compact["markets"]
    assert len(compact_result.model_dump_json().encode()) < len(full_result.model_dump_json().encode()) / 4
    print("MCP stdio sizes: " + json.dumps({
        "block": compact["block_number"], "markets": len(compact["markets"]),
        "compact_payload_bytes": len(compact_result.content[0].text.encode("utf-8")),
        "full_payload_bytes": len(full_result.content[0].text.encode("utf-8")),
        "compact_mcp_result_bytes": len(compact_result.model_dump_json(by_alias=True, exclude_none=True).encode("utf-8")),
        "full_mcp_result_bytes": len(full_result.model_dump_json(by_alias=True, exclude_none=True).encode("utf-8")),
    }))


@pytest.mark.anyio
async def test_compact_preserves_verified_facts_and_explicit_omissions():
    # Warm optional extractor on the calling thread, as the stdio entry does.
    from mirage.bytecode import _extractor
    try:
        _extractor()
    except ImportError:
        pass
    async with connect(mcp_server.create_server(), raise_exceptions=True) as client:
        compact_result = await client.call_tool("get_saved_report", {})
        full_result = await client.call_tool("get_saved_report", {"include_evidence": True})
    assert not compact_result.isError and not full_result.isError
    compact, full = payload(compact_result), payload(full_result)
    assert compact["schema"] == "mirage-agent-summary/1"
    assert compact["evidence_included"] is False
    assert compact["market_count"] == len(full["markets"]) == 4
    for name in ("mode", "chain_id", "block_number", "block_hash", "block_timestamp", "source"):
        assert compact[name] == full[name]
    raw_evidence = []
    for brief, original in zip(compact["markets"], full["markets"]):
        for key in ("market_id", "severity", "display", "block_number"):
            assert brief[key] == original[key]
        assert "rate" in brief["omitted_market_fields"]
        for finding, original_finding in zip(brief["findings"], original["findings"]):
            for key in ("code", "severity", "summary"):
                assert finding[key] == original_finding[key]
            assert len(finding["metrics"]) <= 16
            assert all(isinstance(value, (str, int, float, bool, type(None)))
                       for value in finding["metrics"].values())
            assert all(finding["metrics"][key] == original_finding["metrics"][key]
                       for key in finding["metrics"])
            omitted = {item["name"] for item in finding["omitted_metrics"]}
            assert omitted == set(original_finding["metrics"]) - set(finding["metrics"])
            assert finding["metric_count"] == len(original_finding["metrics"])
            assert finding["evidence_count"] == len(original_finding["evidence"])
            assert "evidence" not in finding
            raw_evidence.extend(original_finding["evidence"])
    text = json.dumps(compact)
    def assert_no_raw_fields(value):
        if isinstance(value, dict):
            assert not set(value) & {"evidence", "data", "result", "calldata", "bytecode", "features", "blob"}
            for item in value.values():
                assert_no_raw_fields(item)
        elif isinstance(value, list):
            for item in value:
                assert_no_raw_fields(item)
    assert_no_raw_fields(compact)
    assert all(item["data"] not in text and item["result"] not in text
               for item in raw_evidence if len(item["data"]) > 80 and len(item["result"]) > 80)
    assert compact["evidence_count"] == len(raw_evidence)
    assert compact["evidence_count_scope"] == (
        "sum of finding-attached records; duplicates included; excludes omitted market-rate evidence")
    assert compact["finding_count"] == sum(len(m["findings"]) for m in full["markets"])
    paxg = next(m for m in compact["markets"] if m["display"]["collateral_symbol"] == "PAXG")
    assert paxg["severity"] == "block"
    accounting = next(f for f in paxg["findings"] if f["code"] == "no_free_liquidity")
    assert accounting["metrics"]["available_liquidity_raw"] == "0"
    assert accounting["metrics"]["principal"] is None
    weth = next(m for m in compact["markets"] if m["display"]["collateral_symbol"] == "WETH")
    assert weth["severity"] == "pass"


@pytest.mark.anyio
@pytest.mark.parametrize("include_evidence", [False, True])
async def test_compaction_never_bypasses_full_validation(monkeypatch, saved, include_evidence):
    corrupt = deepcopy(saved)
    corrupt["rows"][0]["evidence"][0]["block_hash"] = "0x" + "0" * 64
    monkeypatch.setattr(mcp_server, "load_snapshot", lambda _: corrupt)
    async with connect(mcp_server.create_server(snapshot_path=SNAPSHOT), raise_exceptions=True) as client:
        result = await client.call_tool("get_saved_report", {"include_evidence": include_evidence})
    assert result.isError
    assert payload(result)["error"]["code"] == "saved_evidence_unavailable"


def test_scalar_summary_bounds_and_opaque_detail_omissions():
    values = {"calldata": "0x12345678", "return_data": "0x01", "features": {"x": 1},
              "blob": "secret", "opaque": "0x" + "1" * 100, "long": "x" * 193,
              "routes": [{"raw": "large"}], "amount_in_raw": "12345"}
    values.update({f"scalar_{number}": number for number in range(20)})
    kept, omitted = mcp_server._scalars(values)
    assert len(kept) == 16 and kept["amount_in_raw"] == "12345"
    assert not set(kept) & {"calldata", "return_data", "features", "blob", "opaque", "long", "routes"}
    omitted_by_name = {item["name"]: item for item in omitted}
    assert omitted_by_name["routes"] == {"name": "routes", "reason": "complex_value", "item_count": 1}
    assert omitted_by_name["features"]["item_count"] == 1
    assert omitted_by_name["scalar_19"]["reason"] == "scalar_limit"
