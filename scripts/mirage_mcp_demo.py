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


async def run_demo():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=sys.executable,
                                   args=["-m", "mirage.mcp_server"], cwd=str(REPO))
    print("Starting local MCP stdio server; saved evidence only, no network calls.", flush=True)
    # The SDK closes the child stdin and waits for shutdown in its finally block.
    # Keep server logs and raw provider/transport exceptions out of demo output.
    with open(os.devnull, "w", encoding="utf-8") as server_errors:
        async with stdio_client(params, errlog=server_errors) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=60)) as client:
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
    print("MCP session closed. Evidence-block replay complete; no funds moved.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    logging.getLogger("mcp").addHandler(logging.NullHandler())
    logging.getLogger("mcp").propagate = False
    try:
        asyncio.run(run_demo())
    except ImportError:
        print("Install the demo dependencies with this interpreter: python -m pip install "
              "-r requirements-mirage.txt -r requirements-mirage-mcp.txt", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("MCP demo interrupted; closing the local stdio session.", file=sys.stderr)
        return 130
    except Exception:
        print("MCP demo failed. Check the pinned requirements and the default saved snapshot. "
              "Raw exceptions and child logs are suppressed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
