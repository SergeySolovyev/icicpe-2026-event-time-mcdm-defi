"""Capture all Graph-discovered USDC markets with fixed-block, resumable evidence."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from mirage.chain.cache import CachingRpcClient
from mirage.chain.codec import enc_b32
from mirage.chain.rpc import BlockAnchor
from mirage.discovery.subgraph import discover_markets
from mirage.scan import capture, load_snapshot, report_from_snapshot, save_snapshot

GRAPH = "https://api.studio.thegraph.com/query/1759002/mirage-morpho-markets/v0.0.1"
DEPLOYMENT = "QmYkbwLirDouGqfRapedCcQ8YCbM8dzKA13agskDwGzJ6K"
ENDPOINTS = ("https://gateway.tenderly.co/public/mainnet", "https://eth.drpc.org")
SCHEMA, AMOUNT = "mirage-full-scan-run/1", "10000"


def now():
    return datetime.now(timezone.utc).isoformat()


def publish(path, writer):
    pending = path.parent / ".pending"
    pending.mkdir(exist_ok=True)
    temporary = pending / (uuid.uuid4().hex + "-" + path.name)
    try:
        writer(temporary)
        os.link(temporary, path)  # Atomic publication; an existing target is never overwritten.
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path, value, *, immutable=False):
    if immutable:
        publish(path, lambda temporary: write_json(temporary, value))
        return
    target = path.with_name(path.name + ".tmp")
    with target.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    os.replace(target, path)


def verify_anchor(client, anchor):
    # An unavailable verification is fatal too: never continue on an unknown fork.
    if client.anchor(anchor.number) != anchor:
        raise ValueError("Fatal anchor/hash change: run cannot continue")


def validate_manifest(manifest):
    anchor, source = BlockAnchor(**manifest["anchor"]), manifest["source"]
    ids = manifest["market_ids"]
    if (manifest.get("schema") != SCHEMA or manifest.get("amount_usdc") != AMOUNT
            or manifest.get("graph_url") != GRAPH or not isinstance(ids, list) or not ids
            or ids != sorted(set(ids)) or any("0x" + enc_b32(m) != m for m in ids)
            or source.get("kind") != "the-graph" or source.get("deployment") != DEPLOYMENT
            or source.get("market_count") != len(ids) or source.get("query_block") != anchor.number
            or source.get("query_block_hash") != anchor.hash):
        raise ValueError("Invalid run manifest/source/market universe")
    return anchor, source, ids


def validate_checkpoint(snapshot, market, phase, anchor, source):
    rows = snapshot.get("rows", [])
    if (snapshot.get("anchor") != asdict(anchor) or snapshot.get("source") != source
            or len(rows) != 1 or rows[0].get("market_id") != market
            or snapshot.get("scenario_notional_loan") != (AMOUNT if phase == "full" else None)
            or (phase == "full" and not all(key in rows[0] for key in ("oracle", "reference", "rate")))
            or (phase == "accounting" and any(key in rows[0] for key in ("oracle", "reference", "rate")))):
        raise ValueError(f"Invalid checkpoint identity/anchor/source: {market}")
    if phase == "full" and rows[0]["reference"].get("scenario", {}).get("notional_loan") != AMOUNT:
        raise ValueError(f"Invalid checkpoint scenario: expected {AMOUNT} USDC for {market}")
    report_from_snapshot(snapshot)
    return rows[0]


def run(args):
    directory = Path(args.run_dir).resolve()
    manifest_path = directory / "manifest.json"
    if directory.exists() and not manifest_path.exists() and any(directory.iterdir()):
        raise ValueError("Refusing to adopt an existing nonempty directory")
    if args.phase == "full" and not manifest_path.exists():
        raise ValueError("Run --phase accounting first to establish the anchored universe")
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / ".running.lock"
    with lock.open("x", encoding="utf-8") as stream:
        json.dump({"pid": os.getpid(), "phase": args.phase, "created_at": now()}, stream)
        stream.write("\n")
    started, status = time.monotonic(), {"phase": args.phase, "state": "initializing"}

    def emit(**updates):
        status.update(updates, updated_at=now(), elapsed_seconds=round(time.monotonic() - started, 2))
        write_json(directory / "status.json", status)
        line = json.dumps(status, allow_nan=False)
        if getattr(args, "log_progress", False):
            with (directory / "progress.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")
        print(line, flush=True)

    try:
        client = CachingRpcClient(ENDPOINTS, tries=2, timeout=10)
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        else:
            emit(state="discovering")
            anchor = client.anchor("finalized")
            discovery = discover_markets(anchor.number, block_hash=anchor.hash, url=GRAPH)
            manifest = {"schema": SCHEMA, "amount_usdc": AMOUNT, "created_at": now(),
                        "graph_url": GRAPH, "anchor": asdict(anchor),
                        "source": discovery.source, "market_ids": list(discovery.market_ids)}
            validate_manifest(manifest)
            verify_anchor(client, anchor)
            write_json(manifest_path, manifest, immutable=True)
        anchor, source, ids = validate_manifest(manifest)
        verify_anchor(client, anchor)

        checkpoints = {"accounting": {}, "full": {}}
        for phase, rows in checkpoints.items():
            folder = directory / phase
            folder.mkdir(exist_ok=True)
            for path in sorted(folder.glob("*.json.gz")):
                market = path.name.removesuffix(".json.gz")
                if market not in ids:
                    raise ValueError(f"Checkpoint outside the discovered universe: {path.name}")
                snapshot = load_snapshot(path)
                rows[market] = validate_checkpoint(snapshot, market, phase, anchor, source)
        current = checkpoints[args.phase]
        ledger = directory / "failures.jsonl"
        failures = set()
        if ledger.exists():
            for line in ledger.read_text(encoding="utf-8").splitlines():
                item = json.loads(line)
                if item["market_id"] not in ids or item["phase"] not in checkpoints:
                    raise ValueError("Invalid failure ledger entry")
                if item["phase"] == args.phase and item["market_id"] not in current:
                    failures.add(item["market_id"])
        new_attempts, resumed = 0, len(current)
        emit(state="running", block=anchor.number, block_hash=anchor.hash, total=len(ids),
             attempted=len(current) + len(failures), completed=len(current), failed=len(failures),
             resumed=resumed, new_attempts=0, source="the-graph", amount_usdc=AMOUNT)
        for index, market in enumerate(ids):
            if market in current:
                continue
            new_attempts += 1
            emit(market_id=market, position=index + 1, new_attempts=new_attempts,
                 stage="capture", attempted=len(current) + len(failures | {market}))
            try:
                client.begin_market()  # Retry transient failures; retain successful fixed-block reads.
                snapshot = capture(client, anchor, (market,), source,
                                   full_checks=args.phase == "full", scenario_notional_loan=AMOUNT)
                validate_checkpoint(snapshot, market, args.phase, anchor, source)
                publish(directory / args.phase / f"{market}.json.gz",
                        lambda temporary: save_snapshot(temporary, snapshot))
            except (RuntimeError, ValueError, KeyError, TypeError) as error:
                verify_anchor(client, anchor)
                if "hash changed" in str(error).lower() or "hash change" in str(error).lower():
                    raise ValueError("Fatal current/historical block hash change") from error
                failures.add(market)
                record = {"at": now(), "phase": args.phase, "market_id": market,
                          "block": anchor.number, "error_type": type(error).__name__,
                          "error": str(error)[:240],
                          "anchor_reverified": True}
                with ledger.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(record) + "\n")
            else:
                current[market] = snapshot["rows"][0]
                failures.discard(market)
            emit(stage="checkpointed", completed=len(current), failed=len(failures),
                 attempted=len(current) + len(failures))

        verify_anchor(client, anchor)
        rows = [checkpoints["full"].get(m) or checkpoints["accounting"].get(m) for m in ids]
        rows = [row for row in rows if row is not None]
        counts = {"discovered": len(ids), "included": len(rows), "full_checked": len(checkpoints["full"]),
                  "accounting_only": sum(m in checkpoints["accounting"] and m not in checkpoints["full"] for m in ids),
                  "failed_this_phase": len(failures), "missing": len(ids) - len(rows)}
        artifacts = {}
        if rows:
            merged = {"schema": "mirage-snapshot/1", "anchor": asdict(anchor), "rows": rows,
                      "source": {**source, "discovery_market_count": len(ids), "inspected_market_count": len(rows),
                                 "coverage_counts": counts, "failed_market_ids": sorted(failures),
                                 "scope": "Full-checked means collection and replay completed, not all findings passed"},
                      "scenario_notional_loan": AMOUNT if checkpoints["full"] else None}
            stem = args.phase + "-merged-" + uuid.uuid4().hex
            raw_path, report_path = directory / f"{stem}.json.gz", directory / f"{stem}.feed.json"
            publish(raw_path, lambda temporary: save_snapshot(temporary, merged))
            write_json(report_path, report_from_snapshot(merged).to_dict(), immutable=True)
            artifacts = {"snapshot": str(raw_path), "report": str(report_path)}
        emit(state="complete" if len(current) == len(ids) and not failures else "partial",
             stage="finished", market_id=None, counts=counts, failed_market_ids=sorted(failures), **artifacts)
        return 0 if status["state"] == "complete" else 2
    except KeyboardInterrupt:
        emit(state="interrupted", stage="stopped", interruption="KeyboardInterrupt; rerun the same phase to resume")
        raise
    except Exception as error:
        emit(state="aborted", fatal_error=type(error).__name__ + ": " + str(error)[:240])
        raise
    finally:
        lock.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True, help="New directory, or the same directory to resume")
    parser.add_argument("--phase", choices=("accounting", "full"), required=True,
                        help="Establish accounting coverage first; then collect all detectors")
    parser.add_argument("--log-progress", action="store_true", help="Also append progress records to run-dir/progress.jsonl")
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as problem:
        print(type(problem).__name__ + ": " + str(problem), file=sys.stderr, flush=True)
        sys.exit(1)
