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
        result = await client.call_tool("get_saved_report", {})
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
async def test_live_discovery_gates_full_capture_at_same_hash(monkeypatch, saved):
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
        live_result = await client.call_tool("inspect_market", {"market_id": market})
        saved_result = await client.call_tool("get_saved_report", {})
    assert not live_result.isError
    actual = payload(live_result)
    assert actual["mode"] == "live_capture"
    assert actual["block_hash"] == anchor.hash
    assert actual["source"]["inspected_market_count"] == 1
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
async def test_stdio_full_snapshot_returns_report_and_closes():
    # A fresh child catches first-import native-library stalls hidden by pytest's
    # already-imported scientific dependencies. No live tool is invoked.
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params = StdioServerParameters(command=sys.executable,
                                   args=["-m", "mirage.mcp_server"],
                                   cwd=str(Path(__file__).parents[1]))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=40)) as client:
            await client.initialize()
            result = await client.call_tool("get_saved_report", {})
    assert not result.isError
    actual = payload(result)
    assert actual["mode"] == "saved" and actual["schema"] == "mirage-feed/1"
    assert actual["block_hash"].startswith("0x") and actual["markets"]
