"""Independently reread every recorded eth_call and runtime through two RPC URLs.

Read-only; no batching, no fallback to cached snapshot data. Prints only counts
and SHA-256, never configured URLs or credentials. Provider failures are explicit.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path

from mirage.chain.rpc import RpcClient
from mirage.scan import load_snapshot, report_from_snapshot

DEFAULT_PROVIDERS = ("https://gateway.tenderly.co/public/mainnet", "https://eth.drpc.org")


def verify(path: Path, providers=DEFAULT_PROVIDERS):
    snapshot = load_snapshot(path)
    report_from_snapshot(snapshot)
    calls, codes, anchors = {}, {}, {snapshot["anchor"]["number"]: snapshot["anchor"]["hash"]}
    for row in snapshot["rows"]:
        for component in (row, row.get("oracle", {}), row.get("reference", {}), row.get("rate", {})):
            for evidence in component.get("evidence", []):
                key = evidence["to"].lower(), evidence["data"].lower(), evidence["block"]
                if key in calls and calls[key] != evidence["result"]:
                    raise ValueError("Conflicting snapshot calls")
                calls[key] = evidence["result"]
                anchors[evidence["block"]] = evidence["block_hash"]
        oracle = row.get("oracle", {})
        for code_key, block_key in (("runtime_code", "block_number"), ("previous_runtime_code", "previous_block")):
            if oracle.get(code_key) is not None:
                codes[oracle["address"], oracle[block_key]] = oracle[code_key]

    def provider_check(index_url):
        index, url = index_url
        client = RpcClient([url], tries=3, timeout=10)
        failures = []
        checked = 0
        for block, expected_hash in anchors.items():
            try:
                if client.anchor(block).hash != expected_hash:
                    raise ValueError("Block hash mismatch")
            except (RuntimeError, ValueError) as error:
                failures.append({"method": "block_header", "block": block, "error_type": type(error).__name__})
        for (target, data, block), expected in calls.items():
            try:
                if client.call(target, data, block).lower() != expected.lower():
                    raise ValueError("RPC bytes differ")
                checked += 1
            except (RuntimeError, ValueError) as error:
                failures.append({"method": "eth_call", "to": target, "data": data, "block": block,
                                 "error_type": type(error).__name__})
        for (target, block), expected in codes.items():
            try:
                if client.code(target, block).lower() != expected.lower():
                    raise ValueError("Runtime differs")
                checked += 1
            except (RuntimeError, ValueError) as error:
                failures.append({"method": "eth_getCode", "to": target, "block": block,
                                 "error_type": type(error).__name__})
        return {"provider_index": index, "matching_reads": checked, "failures": failures,
                "all_matched": not failures}

    with ThreadPoolExecutor(max_workers=2) as pool:
        checks = list(pool.map(provider_check, enumerate(providers, start=1)))
    return {"snapshot_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "block_number": snapshot["anchor"]["number"], "block_hash": snapshot["anchor"]["hash"],
            "unique_eth_calls": len(calls), "unique_code_reads": len(codes),
            "providers": checks, "all_matched": all(row["all_matched"] for row in checks)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(args.snapshot)
    output = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(json.dumps({**result, "providers": [{**row, "failures": len(row["failures"])}
                                            for row in result["providers"]]}, indent=2))
    return 0 if result["all_matched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
