"""Run from a clean repository root: python -m mirage --help."""
import argparse
import json
import sys
from pathlib import Path

from .chain.rpc import RpcClient
from .scan import capture, load_snapshot, report_from_snapshot, save_snapshot


def block_arg(value: str):
    return value if value in ("latest", "finalized", "safe") else int(value, 0)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="MIRAGE pre-allocation checks with raw chain evidence")
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify", help="Read one market with single RPC calls")
    verify.add_argument("market_id")
    verify.add_argument("--block", type=block_arg, default="finalized")
    verify.add_argument("--snapshot", type=Path, help="Save a new immutable snapshot (never overwrite)")
    verify.add_argument("--full", action="store_true", help="Include oracle, Uniswap and rate observations")
    verify.add_argument("--amount", default="10000", help="Hypothetical collateral sale in USDC units")
    scan = commands.add_parser("scan", help="Scan live Graph-discovered USDC markets")
    scan.add_argument("--source", choices=["subgraph"], default="subgraph")
    scan.add_argument("--block", type=block_arg, default="finalized")
    scan.add_argument("--output", type=Path, default=Path("mirage/feed/latest.json"))
    scan.add_argument("--full", action="store_true", help="Run all checks for every discovered market (slow)")
    scan.add_argument("--amount", default="10000")
    demo = commands.add_parser("demo", help="Replay the committed chain snapshot without network")
    demo.add_argument("--offline", action="store_true", required=True)
    demo.add_argument("--snapshot", type=Path)
    web = commands.add_parser("serve", help="Open the local MIRAGE workbench")
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--snapshot", type=Path)
    web.add_argument("--graph-url")
    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            from .server import serve
            serve(port=args.port, snapshot=args.snapshot, graph_url=args.graph_url)
            return 0
        if args.command == "demo":
            snapshot = args.snapshot
            if snapshot is None:
                from .server import default_snapshot
                snapshot = default_snapshot()
            payload = load_snapshot(snapshot)
        else:
            from .chain.cache import CachingRpcClient
            from .allocator import scenario_amount
            scenario_amount(args.amount)
            client = CachingRpcClient()
            anchor = client.anchor(args.block)
            if args.command == "scan":
                from .discovery.subgraph import discover_markets
                discovery = discover_markets(anchor.number, block_hash=anchor.hash)
                ids, source = discovery.market_ids, discovery.source
            else:
                ids, source = (args.market_id,), {"kind": "explicit-market", "market_count": 1}
            payload = capture(client, anchor, ids, source, full_checks=args.full, scenario_notional_loan=args.amount)
        result = json.dumps(report_from_snapshot(payload).to_dict(), indent=2, allow_nan=False)
        if args.command == "scan":
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(result + "\n", encoding="utf-8")
        elif args.command == "verify" and args.snapshot:
            save_snapshot(args.snapshot, payload)
        print(result)
        return 0
    except (ValueError, RuntimeError, KeyError, OSError) as error:
        print(f"MIRAGE: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
