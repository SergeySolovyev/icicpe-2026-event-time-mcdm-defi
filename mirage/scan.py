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
        findings = [detect(state, evidence=evidence)]
        if "oracle" in row and "reference" in row:
            from .detectors import frozen_price, reference_price, exit_depth
            from .chain.uniswap import replay_reference
            from .chain.oracle import validate_oracle
            reference = replay_reference(row["reference"])
            oracle = validate_oracle(row["oracle"])
            for key in ("collateral_decimals", "loan_decimals"):
                if key in reference:
                    oracle[key] = reference[key]
            for observation in (oracle, reference):
                if (observation.get("block_number") != anchor.number
                        or observation.get("block_hash") != anchor.hash):
                    raise ValueError("Detector observation block mismatch")
            if oracle.get("address", "").lower() != params.oracle:
                raise ValueError("Oracle observation address mismatch")
            if (reference.get("collateral_token") != params.collateral_token
                    or reference.get("loan_token") != params.loan_token):
                raise ValueError("Reference token pair mismatch")
            oracle_finding = frozen_price.detect(oracle, reference=reference,
                                                same_asset=params.loan_token == params.collateral_token)
            findings.append(oracle_finding)
            oracle_human = None
            if oracle.get("current_price") is not None and reference.get("collateral_decimals") is not None:
                try:
                    oracle_human = frozen_price.normalize_price(oracle["current_price"],
                                      reference["collateral_decimals"], reference["loan_decimals"])
                except (TypeError, ValueError):
                    oracle_human = None
            findings.extend((reference_price.detect(reference, oracle_price_loan_per_collateral=oracle_human),
                             exit_depth.detect(reference)))
        else:
            findings.append(Finding("remaining_checks_pending", Severity.INSUFFICIENT,
                                    "This saved observation contains accounting checks only", {}, ()))
        rate = None
        if "rate" in row:
            from .chain.rates import replay_rate
            rate = replay_rate(row["rate"], params, state, anchor)
        verdicts.append(MarketVerdict(market_id, anchor.number, tuple(findings), row.get("display"), rate))
    return MarketReport(anchor.chain_id, anchor.number, anchor.hash, source, tuple(verdicts))


def capture(client: RpcClient, anchor: BlockAnchor, market_ids, source: dict, *,
            full_checks=False, scenario_notional_loan="10000", progress=None) -> dict:
    _validate_source(anchor, source)
    rows = []
    market_ids = tuple(market_ids)
    for index, market_id in enumerate(market_ids):
        if progress:
            progress(index, len(market_ids), market_id)
        params, state, evidence = read_market(client, market_id, anchor)
        row = {"market_id": market_id.lower(), "evidence": [asdict(item) for item in evidence]}
        if full_checks:
            from .chain.oracle import collect_oracle
            from .chain.uniswap import collect_reference
            from .chain.rates import collect_rate
            from .chain.token import symbol
            reference = collect_reference(client, params.collateral_token, params.loan_token, anchor,
                                          scenario_notional_loan=scenario_notional_loan)
            oracle = collect_oracle(client, params.oracle, anchor)
            oracle.update({key: reference[key] for key in ("loan_decimals", "collateral_decimals")
                           if type(reference.get(key)) is int})
            row.update(oracle=oracle, reference=reference, rate=collect_rate(client, params, state, anchor),
                       display={"collateral_symbol": symbol(client, params.collateral_token, anchor.number),
                                "loan_symbol": "USDC", "oracle_address": params.oracle,
                                "collateral_address": params.collateral_token,
                                "loan_address": params.loan_token})
        rows.append(row)
    if progress:
        progress(len(rows), len(market_ids), None)
    if client.anchor(anchor.number).hash != anchor.hash:
        raise ValueError("Block hash changed during capture")
    return {"schema": "mirage-snapshot/1", "anchor": asdict(anchor), "source": source, "rows": rows,
            "scenario_notional_loan": str(scenario_notional_loan) if full_checks else None}


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
