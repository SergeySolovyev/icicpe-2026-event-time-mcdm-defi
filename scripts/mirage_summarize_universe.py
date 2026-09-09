"""Offline summary of one evidence-validated MIRAGE snapshot; never overwrites output."""
import argparse
from collections import Counter
from decimal import Decimal
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from mirage.chain.morpho import MarketParams, MarketState
from mirage.chain.selectors import USDC
from mirage.scan import report_from_snapshot


def usdc(raw):
    whole, fraction = divmod(abs(raw), 1_000_000)
    return f"{'-' if raw < 0 else ''}{whole}.{fraction:06d}"


def amount(raw):
    return {"raw_base_units": str(raw), "usdc_units": usdc(raw)}


def summarize(path):
    path = Path(path).resolve()
    payload = path.read_bytes()
    snapshot = json.loads(gzip.decompress(payload) if path.suffix == ".gz" else payload)
    report = report_from_snapshot(snapshot)  # Replays every supplied raw detector observation.
    source = snapshot["source"]
    declared_counts = [source[key] for key in ("discovery_market_count", "market_count") if key in source]
    if any(type(value) is not int or value < len(report.markets) for value in declared_counts):
        raise ValueError("Invalid discovery count in snapshot source")
    if len(set(declared_counts)) > 1:
        raise ValueError("Conflicting discovery counts in snapshot source")
    discovered = declared_counts[0] if declared_counts else None
    cases, findings, examples = [], {}, {}
    full, full_insufficient, rates = 0, 0, 0
    for row, verdict in zip(snapshot["rows"], report.markets):
        if ("oracle" in row) != ("reference" in row):
            raise ValueError("Partially populated detector observation")
        params = MarketParams.decode(row["evidence"][0]["result"])
        state = MarketState.decode(row["evidence"][1]["result"])
        all_checks = "oracle" in row and "reference" in row
        incomplete = any(f.severity.value == "insufficient" for f in verdict.findings)
        full += all_checks
        full_insufficient += all_checks and incomplete
        rates += verdict.rate is not None
        accounting = verdict.findings[0]
        case = {"market_id": verdict.market_id, "status": verdict.severity.value,
                "check_scope": "all_three_recorded" if all_checks else "accounting_only",
                "has_insufficient_finding": incomplete,
                "collateral_token": params.collateral_token, "oracle": params.oracle,
                "stored_supply_assets": amount(state.total_supply_assets),
                "stored_borrow_assets": amount(state.total_borrow_assets),
                "stored_supply_minus_borrow": amount(state.total_supply_assets - state.total_borrow_assets),
                "share_exchange_rate_multiple_vs_initial": accounting.metrics.get("share_price_multiple_vs_initial"),
                "findings": [{"code": f.code, "severity": f.severity.value} for f in verdict.findings]}
        cases.append(case)
        for finding in verdict.findings:
            counts = findings.setdefault(finding.code, Counter())
            counts[finding.severity.value] += 1
            examples.setdefault(finding.code, []).append(case)

    def ranked(values, field, limit=10):
        return sorted(values, key=lambda case: (-int(case[field]["raw_base_units"]), case["market_id"]))[:limit]

    supply = sum(int(case["stored_supply_assets"]["raw_base_units"]) for case in cases)
    borrow = sum(int(case["stored_borrow_assets"]["raw_base_units"]) for case in cases)
    share_cases = [case for case in cases if case["share_exchange_rate_multiple_vs_initial"] is not None]
    share_cases.sort(key=lambda case: (Decimal(case["share_exchange_rate_multiple_vs_initial"]).copy_negate(), case["market_id"]))
    return {
        "schema": "mirage-universe-summary/1", "snapshot": str(path.resolve()),
        "snapshot_sha256": hashlib.sha256(payload).hexdigest(), "anchor": snapshot["anchor"],
        "source": source,
        "validation": "Product report_from_snapshot replayed raw evidence locally; no fresh network verification.",
        "coverage": {
            "discovered_markets_reported_by_source": discovered,
            "discovery_count_basis": "Snapshot source metadata; not independently queried by this offline summary.",
            "included_unique_markets": len(cases), "accounting_checked": len(cases),
            "accounting_only": len(cases) - full, "all_three_checks_recorded": full,
            "all_three_with_insufficient_findings": full_insufficient,
            "all_three_without_insufficient_findings": full - full_insufficient,
            "rate_observations_replayed": rates,
            "missing_from_snapshot": discovered - len(cases) if discovered is not None else None,
            "all_discovered_markets_included": len(cases) == discovered if discovered is not None else None,
            "all_discovered_markets_have_three_checks": full == discovered if discovered is not None else None,
            "meaning": "Recorded means supplied observations were replayed; it includes BLOCK, WARN and INSUFFICIENT outcomes. Missing rows are not assumed to be failed attempts.",
        },
        "accounting": {
            "loan_token": USDC, "loan_token_decimals": 6, "markets_in_sums": len(cases),
            "stored_supply_assets": amount(supply), "stored_borrow_assets": amount(borrow),
            "stored_supply_minus_borrow": amount(supply - borrow),
            "negative_supply_minus_borrow_markets": sum(int(c["stored_supply_minus_borrow"]["raw_base_units"]) < 0 for c in cases),
            "basis": "Sums of decoded stored market() fields at the pinned block; no additional interest accrual is simulated.",
            "labels": "Supply and borrow are accounting asset amounts, not recovered principal or a dollar TVL valuation. Supply minus borrow is the stored free-liquidity balance, not a guaranteed withdrawal amount.",
        },
        "status_counts": {status: sum(case["status"] == status for case in cases)
                          for status in ("pass", "warn", "insufficient", "block")},
        "finding_counts": {code: dict(sorted(counts.items())) for code, counts in sorted(findings.items())},
        "finding_examples": {code: [case["market_id"] for case in ranked(values, "stored_supply_assets", 3)]
                             for code, values in sorted(examples.items())},
        "top_cases": {
            "ranking_basis": "Each list states its ordering; stored balances rank accounting size, not allocator attractiveness or losses.",
            "largest_stored_supply": ranked(cases, "stored_supply_assets"),
            "largest_stored_free_liquidity": ranked(cases, "stored_supply_minus_borrow"),
            "largest_share_exchange_rate_multiple": share_cases[:10],
            "blocked_by_stored_supply": ranked([case for case in cases if case["status"] == "block"], "stored_supply_assets"),
            "insufficient_by_stored_supply": ranked([case for case in cases if case["has_insufficient_finding"]], "stored_supply_assets"),
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--output", type=Path)
    destination.add_argument("--stdout", action="store_true")
    args = parser.parse_args(argv)
    if args.output is not None:
        args.output = args.output.resolve()
        if args.output.exists():
            raise ValueError("--output must be a new path; existing files are never overwritten")
    result = summarize(args.snapshot)
    text = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.stdout:
        print(text, end="")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(".summary-" + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(text)
        os.link(temporary, args.output)
    finally:
        temporary.unlink(missing_ok=True)
    print(json.dumps({"output": str(args.output.resolve()), "coverage": result["coverage"],
                      "status_counts": result["status_counts"]}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as problem:
        print(type(problem).__name__ + ": " + str(problem), file=sys.stderr)
        sys.exit(1)
