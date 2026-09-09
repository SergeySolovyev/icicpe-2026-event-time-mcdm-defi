"""Discovery -> chain -> pure accounting checks -> reproducible report."""
import gzip
import json
from dataclasses import asdict
from pathlib import Path

from .chain.codec import enc_b32
from .chain.morpho import MarketParams, MarketState, read_market
from .chain.rpc import BlockAnchor, RpcClient
from .chain.selectors import USDC
from .detectors.phantom_volume import detect
from .verdict import Evidence, Finding, MarketReport, MarketVerdict, Severity


def _validate_source(anchor: BlockAnchor, source: dict):
    if not isinstance(source, dict):
        raise ValueError("Snapshot source must be an object")
    if source.get("kind") == "the-graph":
        if type(source.get("query_block")) is not int or source["query_block"] != anchor.number:
            raise ValueError("Graph and RPC disagree on block number")
        block_hash = source.get("query_block_hash")
        if not isinstance(block_hash, str) or block_hash.lower() != anchor.hash.lower():
            raise ValueError("Graph and RPC disagree on block hash")


def report_for_rows(anchor: BlockAnchor, source: dict, rows: list[dict]) -> MarketReport:
    _validate_source(anchor, source)
    if not rows:
        raise ValueError("Snapshot contains no market evidence")
    verdicts, seen = [], set()
    for row in rows:
        market_id = "0x" + enc_b32(row["market_id"])
        if market_id in seen:
            raise ValueError("Duplicate snapshot market id")
        seen.add(market_id)
        evidence = tuple(Evidence(**value) for value in row["evidence"])
        from .chain.selectors import MARKET, MARKET_PARAMS, MORPHO
        expected_data = (MARKET_PARAMS + market_id[2:], MARKET + market_id[2:])
        if len(evidence) != 2 or any(
            item.block != anchor.number or item.block_hash != anchor.hash
            or item.to.lower() != MORPHO.lower() or item.data != expected
            or item.method != "eth_call"
            for item, expected in zip(evidence, expected_data)
        ):
            raise ValueError("Snapshot evidence provenance mismatch")
        params = MarketParams.decode(evidence[0].result)
        state = MarketState.decode(evidence[1].result)
        if params.loan_token != USDC:
            raise ValueError("Only USDC markets supported in this release")
        finding = detect(state, evidence=evidence)
        incomplete = Finding("remaining_checks_pending", Severity.INSUFFICIENT,
                             "Oracle reference and collateral exit-depth checks not yet implemented", {}, ())
        verdicts.append(MarketVerdict(market_id, anchor.number, (finding, incomplete)))
    return MarketReport(anchor.chain_id, anchor.number, anchor.hash, source, tuple(verdicts))


def capture(client: RpcClient, anchor: BlockAnchor, market_ids, source: dict) -> dict:
    _validate_source(anchor, source)
    rows = []
    for market_id in market_ids:
        _, _, evidence = read_market(client, market_id, anchor)
        rows.append({"market_id": market_id.lower(), "evidence": [asdict(item) for item in evidence]})
    if client.anchor(anchor.number).hash != anchor.hash:
        raise ValueError("Block hash changed during capture")
    return {"schema": "mirage-snapshot/1", "anchor": asdict(anchor), "source": source, "rows": rows}


def report_from_snapshot(snapshot: dict) -> MarketReport:
    if snapshot["schema"] != "mirage-snapshot/1":
        raise ValueError("Unsupported snapshot schema")
    anchor = BlockAnchor(**snapshot["anchor"])
    if anchor.chain_id != 1:
        raise ValueError("Only Ethereum mainnet snapshots supported")
    return report_for_rows(anchor, snapshot["source"], snapshot["rows"])


def save_snapshot(path: Path, snapshot: dict):
    report_from_snapshot(snapshot)  # Validate before creating an immutable file.
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(snapshot, sort_keys=True, indent=2).encode() + b"\n"
    with path.open("xb") as destination:
        if path.suffix == ".gz":
            with gzip.GzipFile(filename="", mode="wb", fileobj=destination, mtime=0) as compressed:
                compressed.write(payload)
        else:
            destination.write(payload)


def load_snapshot(path: Path) -> dict:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as source:
        return json.load(source)
