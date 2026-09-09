"""Optional MCP stdio tools over MIRAGE's existing evidence pipeline."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import threading
import time

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from .allocator import compare, scenario_amount
from .chain.cache import CachingRpcClient
from .discovery.subgraph import discover_markets
from .scan import capture, load_snapshot, report_from_snapshot
from .server import GRAPH_URL, default_snapshot


def _result(payload: dict, *, error=False) -> CallToolResult:
    # Reject NaN or non-JSON values before the MCP encoder sees the result.
    text = json.dumps(payload, allow_nan=False, ensure_ascii=True)
    return CallToolResult(content=[TextContent(type="text", text=text)],
                          structuredContent=json.loads(text), isError=error)


def _error(code: str, message: str, stage: str) -> CallToolResult:
    return _result({"schema": "mirage-tool-error/1", "error": {
        "code": code, "message": message, "stage": stage}}, error=True)


def _inputs(market_id, amount_usdc):
    if market_id is not None and (not isinstance(market_id, str)
            or re.fullmatch(r"0x[0-9a-fA-F]{64}", market_id) is None):
        raise ValueError("market_id must be 0x followed by exactly 64 hexadecimal digits")
    if not isinstance(amount_usdc, str) or len(amount_usdc) > 80:
        raise ValueError("amount_usdc must be a decimal USDC string")
    return market_id.lower() if market_id is not None else None, scenario_amount(amount_usdc)


def _report(snapshot, mode):
    result = report_from_snapshot(snapshot).to_dict()
    result.update(mode=mode, block_timestamp=snapshot["anchor"]["timestamp"],
                  scenario_notional_loan=snapshot.get("scenario_notional_loan"))
    return result


def create_server(*, snapshot_path=None, graph_url=None) -> FastMCP:
    """Register tools without loading evidence or contacting any provider."""
    saved_path = Path(snapshot_path) if snapshot_path is not None else None
    endpoint = graph_url or os.environ.get("MIRAGE_SUBGRAPH_URL") or GRAPH_URL
    live_lock = threading.Lock()
    server = FastMCP("MIRAGE", log_level="WARNING", instructions=(
        "Read-only pre-supply evidence for Ethereum Morpho Blue USDC markets. "
        "Always state the block, capture mode, uncertainty and scenario amount. "
        "Saved evidence is historical even when its source is The Graph. "
        "BLOCK or INSUFFICIENT is not a transaction; tools never sign or submit one."))

    def saved_snapshot():
        return load_snapshot(saved_path or default_snapshot())

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                            idempotentHint=True, openWorldHint=False))
    async def get_saved_report() -> CallToolResult:
        """Replay the configured local snapshot with raw evidence and its exact block.

        No network. The result uses mirage-feed/1 with mode=saved; Graph origin
        does not make saved evidence current. Missing checks remain insufficient.
        """
        def work():
            try:
                return _result(_report(saved_snapshot(), "saved"))
            except Exception:
                return _error("saved_evidence_unavailable",
                              "The configured snapshot could not be loaded or validated", "saved_report")
        return await asyncio.to_thread(work)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                            idempotentHint=False, openWorldHint=True))
    async def inspect_market(market_id: str, amount_usdc: str = "10000") -> CallToolResult:
        """Capture one market through live The Graph discovery and finalized mainnet RPC.

        market_id is a 32-byte Morpho ID, not a token/oracle address. amount_usdc
        is an exact hypothetical collateral-sale notional, at most six decimals.
        Discovery must match the finalized RPC block hash and contain this USDC
        market before full accounting/oracle/Uniswap checks. May take minutes.
        Returns mirage-feed/1, mode=live_capture; does not replace saved evidence.
        """
        try:
            market, amount = _inputs(market_id, amount_usdc)
        except ValueError as error:
            return _error("invalid_input", str(error), "validation")

        def work():
            if not live_lock.acquire(blocking=False):
                return _error("inspection_busy", "Another live inspection is running", "validation")
            stage = "finalized_anchor"
            try:
                client = CachingRpcClient(tries=3, timeout=8)
                anchor = client.anchor("finalized")
                stage = "graph_discovery"
                discovery = discover_markets(anchor.number, block_hash=anchor.hash, url=endpoint)
                if market not in discovery.market_ids:
                    return _error("market_not_discovered",
                                  "Market is absent from live Graph USDC discovery at this block", stage)
                source = {**discovery.source, "discovery_market_count": len(discovery.market_ids),
                          "inspected_market_count": 1, "selection": "explicit MCP tool selection"}
                stage = "full_capture"
                snapshot = capture(client, anchor, (market,), source, full_checks=True,
                                   scenario_notional_loan=amount)
                stage = "evidence_validation"
                payload = _report(snapshot, "live_capture")
                payload["captured_at"] = int(time.time())
                return _result(payload)
            except Exception:
                # Provider exceptions can contain credential-bearing URLs.
                return _error("live_inspection_failed",
                              "Live inspection failed; no replacement or passing verdict was produced", stage)
            finally:
                live_lock.release()
        return await asyncio.to_thread(work)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                            idempotentHint=True, openWorldHint=False))
    async def preview_saved_allocation(amount_usdc: str = "10000",
                                       market_id: str | None = None) -> CallToolResult:
        """Replay original T1 versus the MIRAGE entry gate on saved evidence only.

        Optionally restrict to one inspected market. Requires the allocator's
        pandas dependency. Different sale amounts require new exact-size evidence;
        missing evidence stays insufficient. No transaction or historical P&L.
        """
        try:
            market, amount = _inputs(market_id, amount_usdc)
        except ValueError as error:
            return _error("invalid_input", str(error), "validation")

        def work():
            try:
                snapshot = saved_snapshot()
                report_from_snapshot(snapshot)
                if market is not None and market not in {row["market_id"].lower() for row in snapshot["rows"]}:
                    return _error("market_not_saved", "Market is not in the configured saved evidence", "saved_allocation")
                payload = compare(snapshot, amount_usdc=amount, market_id=market)
                payload["evidence_mode"] = "saved"
                return _result(payload)
            except ImportError:
                return _error("allocator_dependency_missing",
                              "Install the existing allocator requirements to preview allocation", "saved_allocation")
            except Exception:
                return _error("saved_allocation_unavailable",
                              "Saved allocation evidence could not be loaded or validated", "saved_allocation")
        return await asyncio.to_thread(work)

    return server


def main():
    parser = argparse.ArgumentParser(description="MIRAGE read-only MCP stdio server")
    parser.add_argument("--snapshot", type=Path, help="Local immutable evidence snapshot")
    args = parser.parse_args()
    # This Windows host can stall when NumPy's native modules first load in a
    # worker. Prepare the optional, unmodified revert.pro extractor on the main
    # thread before stdio starts. No evidence is loaded and no network is used.
    # Missing optional dependencies retain the core's explicit unavailable state.
    try:
        from .bytecode import _extractor
        _extractor()
    except ImportError:
        pass
    # Protocol messages alone belong on stdout. SDK logging uses stderr.
    create_server(snapshot_path=args.snapshot).run(transport="stdio")


if __name__ == "__main__":
    main()
