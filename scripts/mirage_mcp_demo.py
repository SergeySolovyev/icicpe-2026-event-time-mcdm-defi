"""Run a saved-only MIRAGE demonstration through the official MCP stdio client."""
import argparse
import asyncio
from datetime import timedelta
import json
import logging
import os
from pathlib import Path
import re
import sys
import tempfile


REPO = Path(__file__).resolve().parents[1]
CASES = (
    ("PAXG", "0x8eaf7b29f02ba8d8c1d7aeb587403dcb16e2e943e4e2f5f94b0963c2386406c9", "10000"),
    ("WETH", "0x94b823e6bd8ea533b4e33fbc307faea0b307301bc48763acc4d4aa4def7636cd", "10000"),
    ("WETH", "0x94b823e6bd8ea533b4e33fbc307faea0b307301bc48763acc4d4aa4def7636cd", "20000"),
)


def safe_code(value):
    return value if isinstance(value, str) and re.fullmatch(r"[a-z_]{1,80}", value) else "unknown"


async def call(client, name, arguments):
    result = await client.call_tool(name, arguments)
    payload = result.structuredContent
    if not isinstance(payload, dict):
        raise ValueError("Expected structured MCP result")
    if result.isError:
        error = payload.get("error") or {}
        print(f"Tool failed: {name}; code={safe_code(error.get('code'))}; "
              f"stage={safe_code(error.get('stage'))}", file=sys.stderr, flush=True)
        raise RuntimeError("MCP tool reported an error")
    return payload


DEFAULT_TIMEOUT_SECONDS = 300
MIN_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 3600
SERVER_LOG_TAIL_LINES = 15
# WETH/USDC on Morpho Blue; the positive control of the saved demo.
DEFAULT_LIVE_MARKET = "0x94b823e6bd8ea533b4e33fbc307faea0b307301bc48763acc4d4aa4def7636cd"
MARKET_ID_PATTERN = r"0x[0-9a-fA-F]{64}"


def read_server_log(path, limit=SERVER_LOG_TAIL_LINES):
    """Return the tail of the stdio child's error log, or an empty string."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-limit:]).strip()


def resolve_timeout(requested=None):
    """Return the client read timeout, from the flag, then the environment, then the default."""
    raw = requested if requested is not None else os.environ.get("MIRAGE_MCP_TIMEOUT")
    if raw in (None, ""):
        return timedelta(seconds=DEFAULT_TIMEOUT_SECONDS)
    try:
        seconds = int(raw)
    except (TypeError, ValueError):
        raise ValueError("Timeout must be a whole number of seconds")
    if not MIN_TIMEOUT_SECONDS <= seconds <= MAX_TIMEOUT_SECONDS:
        raise ValueError(f"Timeout must be between {MIN_TIMEOUT_SECONDS} and {MAX_TIMEOUT_SECONDS} seconds")
    return timedelta(seconds=seconds)


async def run_demo(timeout, server_log, live_market=None):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=sys.executable,
                                   args=["-m", "mirage.mcp_server"], cwd=str(REPO))
    print("Starting local MCP stdio server; saved evidence replay"
          + (", then one live inspection over the network." if live_market
             else " only, no network calls."), flush=True)
    # The SDK closes the child stdin and waits for shutdown in its finally block.
    # The stdio child imports the scientific stack before it answers `initialize`.
    # Cold imports of mirage.mcp_server were measured at 48.9 s alone and 178.8 s to a
    # completed handshake on a fully loaded Windows host on 11 September 2026, so an
    # earlier 60 s read timeout turned a slow start into an outright failure. The
    # timeout must stay above the worst observed cold start; raise it with --timeout
    # or MIRAGE_MCP_TIMEOUT on a slower machine.
    #
    # The child's stderr goes to a log file rather than to the terminal, so protocol
    # noise stays out of the demo output. It must NOT go to os.devnull: a child that
    # dies during startup then looks exactly like a timeout, and the reason is lost.
    # On failure the caller prints the path to this log.
    with open(server_log, "w", encoding="utf-8") as server_errors:
        async with stdio_client(params, errlog=server_errors) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timeout) as client:
                print(f"Waiting up to {int(timeout.total_seconds())}s for the stdio child's first import.",
                      flush=True)
                initialized = await client.initialize()
                print(f"Initialized: {initialized.serverInfo.name}; protocol={initialized.protocolVersion}", flush=True)
                listing = await client.list_tools()
                print("Tools: " + ", ".join(sorted(tool.name for tool in listing.tools)), flush=True)
                report = await call(client, "get_saved_report", {})
                print(f"Report: mode={report['mode']}; block={report['block_number']}; "
                      f"markets={len(report['markets'])}", flush=True)
                print("Block hash: " + report["block_hash"], flush=True)
                for label, market_id, amount in CASES:
                    preview = await call(client, "preview_saved_allocation", {
                        "market_id": market_id, "amount_usdc": amount})
                    admission = preview.get("admission") or {}
                    print(f"{label} {preview['amount_usdc']} USDC: "
                          f"mode={preview['evidence_mode']}; block={preview['block_number']}; "
                          f"original={preview['original']['kind']}; gated={preview['gated']['kind']}; "
                          f"exact_size={json.dumps(preview['scenario_matches'])}; "
                          f"admission={admission.get('severity', 'unavailable')}", flush=True)
                    findings = [finding["code"] for finding in admission.get("findings", ())
                                if finding["severity"] != "pass"]
                    if findings:
                        print("  Non-pass findings: " + ", ".join(findings), flush=True)
                if live_market:
                    await run_live_inspection(client, live_market)
    print("MCP session closed. Evidence-block replay complete; no funds moved.", flush=True)


async def run_live_inspection(client, market_id):
    """Call inspect_market once so a reviewer can see Graph discovery drive a live capture.

    This is the only part of the demo that uses the network. A failure here is
    reported and does not invalidate the saved replay above it.
    """
    print("", flush=True)
    print("Live inspection: this calls The Graph and Ethereum RPC at the current finalized "
          "block and can take minutes.", flush=True)
    result = await client.call_tool("inspect_market",
                                    {"market_id": market_id, "amount_usdc": "10000"})
    payload = result.structuredContent
    if not isinstance(payload, dict):
        print("Live inspection returned no structured result.", file=sys.stderr, flush=True)
        return
    if result.isError:
        error = payload.get("error") or {}
        print(f"Live inspection did not complete: code={safe_code(error.get('code'))}; "
              f"stage={safe_code(error.get('stage'))}. The saved replay above is unaffected.",
              file=sys.stderr, flush=True)
        return
    source = payload.get("source") or {}
    print(f"Live: mode={payload['mode']}; block={payload['block_number']}; "
          f"discovered={source.get('discovery_market_count')}; "
          f"inspected={source.get('inspected_market_count')}", flush=True)
    print("Live block hash: " + payload["block_hash"], flush=True)
    for market in payload.get("markets", ()):
        print(f"  {market['market_id']}: severity={market['severity']}; "
              f"findings={market.get('finding_count')}", flush=True)
    print("This block is newer than the saved evidence, so its verdict may differ. "
          "A live capture never replaces the saved report.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", default=None,
                        help="Client read timeout in seconds; defaults to MIRAGE_MCP_TIMEOUT "
                             f"or {DEFAULT_TIMEOUT_SECONDS}.")
    parser.add_argument("--live", nargs="?", const=DEFAULT_LIVE_MARKET, default=None,
                        metavar="MARKET_ID",
                        help="After the saved replay, call inspect_market once against the live "
                             "Graph deployment and Ethereum RPC. Uses the network and can take "
                             "minutes; pair it with a longer --timeout. Defaults to the WETH "
                             "market of the saved demo.")
    args = parser.parse_args()
    if args.live is not None and not re.fullmatch(MARKET_ID_PATTERN, args.live):
        print("A market ID is 0x followed by 64 hex digits.", file=sys.stderr)
        return 2
    logging.getLogger("mcp").addHandler(logging.NullHandler())
    logging.getLogger("mcp").propagate = False
    try:
        timeout = resolve_timeout(args.timeout)
    except ValueError as error:
        print(f"Invalid timeout: {error}", file=sys.stderr)
        return 2
    server_log = Path(tempfile.gettempdir()) / "mirage_mcp_server_stderr.log"
    try:
        asyncio.run(run_demo(timeout, server_log, args.live))
    except ImportError:
        print("Install the demo dependencies with this interpreter: python -m pip install "
              "-r requirements-mirage.txt -r requirements-mirage-mcp.txt", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("MCP demo interrupted; closing the local stdio session.", file=sys.stderr)
        return 130
    except Exception:
        print("MCP demo failed. On a loaded machine the usual cause is a slow first import in "
              "the stdio child: close other applications and rerun, or raise the wait with "
              "--timeout. Otherwise confirm this interpreter's SDK with `python -m pip show mcp` "
              "against requirements-mirage-mcp.txt, and check the default saved snapshot.",
              file=sys.stderr)
        tail = read_server_log(server_log)
        if tail:
            print(f"Last lines of the stdio server's own error output ({server_log}):",
                  file=sys.stderr)
            print(tail, file=sys.stderr)
        else:
            print(f"The stdio server wrote nothing to {server_log}, which points at a slow or "
                  "killed start rather than a server-side exception.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
