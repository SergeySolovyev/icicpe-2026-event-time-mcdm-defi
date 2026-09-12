"""Turn one MIRAGE admission decision into a ready-to-send MirageGate transaction.

This script never signs anything and never sees a private key. It reads a saved MIRAGE
report, checks that the decision may honestly be published against the configured
Chainlink feed, and prints the exact `cast send` command for the operator to run.

The interesting work here is the refusal, not the formatting. A Chainlink ETH/USD feed
describes ether. Publishing a wstETH or PAXG decision against it and calling the
resulting difference a "deviation" would be meaningless: wstETH trades at a premium to
ETH by construction, so the comparison would veto every entry for a reason that has
nothing to do with risk. The script therefore refuses any market whose collateral the
feed does not describe, and says why.

Usage:

    python scripts/mirage_chainlink_publish.py --market WETH
    python scripts/mirage_chainlink_publish.py --market 0x94b8... --gate 0xGATE

Add --json to emit a machine-readable record instead of the human runbook.
"""
import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from mirage.allocator import compare  # noqa: E402
from mirage.scan import load_snapshot, report_from_snapshot  # noqa: E402
from mirage.server import default_snapshot  # noqa: E402

# Verdict enum values as declared in contracts/src/MirageGate.sol.
VERDICT_NONE, VERDICT_ALLOW, VERDICT_BLOCKED = 0, 1, 2

# Which collateral a given feed actually describes. A feed may only be used for a market
# whose collateral is listed here, and the check is exact rather than approximate.
FEED_COVERAGE = {
    "ETH / USD": {"WETH", "ETH"},
}

# Chainlink aggregators, by network. Sepolia ETH/USD verified live on 12 September 2026:
# description "ETH / USD", 8 decimals.
KNOWN_FEEDS = {
    "sepolia": {
        "address": "0x694AA1769357215DE4FAC081bf1f309aDC325306",
        "description": "ETH / USD",
        "decimals": 8,
    },
}

SEVERITY_TO_VERDICT = {
    "pass": VERDICT_ALLOW,
    "warn": VERDICT_ALLOW,  # a warning does not by itself cancel an entry offchain
    "block": VERDICT_BLOCKED,
    "insufficient": VERDICT_BLOCKED,
}


class Refused(Exception):
    """Raised when a decision must not be published against this feed."""


def _collateral_symbol(market: dict) -> str:
    display = market.get("display") or {}
    for key in ("collateral_symbol", "collateral", "symbol"):
        value = display.get(key) or market.get(key)
        if isinstance(value, str) and value:
            return value.upper()
    return ""


def _reference_price(market: dict):
    """Reference price MIRAGE used, as a Decimal, or None when it was never established.

    The report keeps it on the finding that recorded it, not on the market, so read it
    from `reference_observed` first and fall back to whichever finding carries the
    reference figure. A market with no reference has nothing to compare against a feed.
    """
    from decimal import Decimal

    findings = market.get("findings") or ()
    for code, field in (
        ("reference_observed", "price_loan_per_collateral"),
        (None, "reference_price_loan_per_collateral"),
    ):
        for finding in findings:
            if code is not None and finding.get("code") != code:
                continue
            raw = (finding.get("metrics") or {}).get(field)
            if raw not in (None, "", "None"):
                return Decimal(str(raw))
    return None


def _scale_to_feed(price, decimals: int) -> int:
    from decimal import Decimal, ROUND_DOWN

    scaled = (price * (Decimal(10) ** decimals)).to_integral_value(rounding=ROUND_DOWN)
    if scaled <= 0:
        raise Refused("Reference price scaled to zero; nothing meaningful to publish.")
    return int(scaled)


def select_market(report: dict, wanted: str) -> dict:
    wanted_upper = wanted.upper()
    for market in report["markets"]:
        if market["market_id"].lower() == wanted.lower():
            return market
        if _collateral_symbol(market) == wanted_upper:
            return market
    known = ", ".join(
        f"{_collateral_symbol(m) or '?'} ({m['market_id'][:10]}...)" for m in report["markets"]
    )
    raise Refused(f"No market matched {wanted!r}. The saved report holds: {known}")


def build(market: dict, report: dict, decision: dict, feed: dict, gate: str, amount_usdc: str) -> dict:
    symbol = _collateral_symbol(market)
    covered = FEED_COVERAGE.get(feed["description"])
    if covered is None:
        raise Refused(
            f"No coverage rule is declared for feed {feed['description']!r}. Add one before publishing."
        )
    if symbol not in covered:
        raise Refused(
            f"Feed {feed['description']!r} describes {sorted(covered)}, not {symbol or 'this collateral'}.\n"
            f"Publishing a {symbol or 'foreign'} decision against it would report a deviation that reflects the\n"
            f"difference between two different assets, not a disagreement about price. Refusing."
        )

    price = _reference_price(market)
    if price is None:
        raise Refused(
            f"{symbol} has no established reference price in this report, so there is nothing to compare\n"
            f"against the feed. A decision can still be taken offchain; it just cannot be published here."
        )

    # The verdict must come from the admission gate evaluated at THIS amount, not from the
    # market's severity, which belongs to whatever scenario the snapshot was captured for.
    # A decision taken for one sale size never authorises another: that is the property the
    # whole product is built around, and publishing would be the easiest place to lose it.
    severity = decision["admission"]["severity"]
    verdict = SEVERITY_TO_VERDICT.get(severity)
    if verdict is None:
        raise Refused(f"Unmapped severity {severity!r}.")

    from decimal import Decimal

    amount_raw = int((Decimal(amount_usdc) * Decimal(10) ** 6).to_integral_value())
    reference_scaled = _scale_to_feed(price, feed["decimals"])

    return {
        "market_id": market["market_id"],
        "collateral": symbol,
        "severity": severity,
        "gated_action": decision["gated"]["kind"],
        "original_action": decision["original"]["kind"],
        "scenario_matches": decision["scenario_matches"],
        "verdict_name": "Allow" if verdict == VERDICT_ALLOW else "Blocked",
        "verdict_enum": verdict,
        "amount_usdc": amount_usdc,
        "amount_raw": amount_raw,
        "evidence_block": report["block_number"],
        "evidence_block_hash": report["block_hash"],
        "reference_price": str(price),
        "reference_price_scaled": reference_scaled,
        "feed": feed,
        "gate": gate,
    }


def runbook(rec: dict) -> str:
    gate = rec["gate"]
    return f"""
MIRAGE decision ready to publish
================================

  market        {rec['collateral']}  {rec['market_id']}
  offchain      original policy {rec['original_action']}  ->  MIRAGE gate {rec['gated_action']}
                admission {rec['severity']}  ->  MirageGate.Verdict.{rec['verdict_name']}
                evidence covers this exact amount: {rec['scenario_matches']}
  amount        {rec['amount_usdc']} USDC  ({rec['amount_raw']} raw, 6 decimals)
  evidence      block {rec['evidence_block']}
                {rec['evidence_block_hash']}
  reference     {rec['reference_price']} USDC per {rec['collateral']}
                {rec['reference_price_scaled']} scaled to the feed's {rec['feed']['decimals']} decimals
  feed          {rec['feed']['description']}  {rec['feed']['address']}

What the contract does with this
--------------------------------
It reads the feed itself, computes the deviation between the reference price above and
the live answer, and stores {rec['verdict_name']} unless that deviation exceeds the bound, in
which case an Allow is stored as Blocked. A stale feed reverts the whole call.

Send it yourself. Nothing here holds your key.
----------------------------------------------

  export SEPOLIA_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com

  cast send {gate} \\
    "submitDecision(bytes32,uint128,uint64,uint256,uint8)" \\
    {rec['market_id']} \\
    {rec['amount_raw']} \\
    {rec['evidence_block']} \\
    {rec['reference_price_scaled']} \\
    {rec['verdict_enum']} \\
    --rpc-url $SEPOLIA_RPC_URL \\
    --interactive

`--interactive` makes cast prompt for the key rather than taking it from a flag or the
environment, so it never lands in your shell history.

Read the stored decision back
-----------------------------

  cast call {gate} \\
    "decisionFor(bytes32,uint128)((uint8,uint128,uint64,uint64,int256,uint80,uint32,bool))" \\
    {rec['market_id']} {rec['amount_raw']} --rpc-url $SEPOLIA_RPC_URL
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", default="WETH",
                        help="collateral symbol or full 32-byte market id (default: WETH)")
    parser.add_argument("--amount", default="10000", help="sale size in USDC (default: 10000)")
    parser.add_argument("--network", default="sepolia", choices=sorted(KNOWN_FEEDS))
    parser.add_argument("--gate", default="<MIRAGE_GATE_ADDRESS>",
                        help="deployed MirageGate address")
    parser.add_argument("--snapshot", default=None, help="saved snapshot path")
    parser.add_argument("--json", action="store_true", help="emit the record as JSON")
    args = parser.parse_args()

    snapshot = load_snapshot(Path(args.snapshot) if args.snapshot else default_snapshot())
    report = report_from_snapshot(snapshot).to_dict()
    feed = KNOWN_FEEDS[args.network]

    try:
        market = select_market(report, args.market)
        decision = compare(snapshot, amount_usdc=args.amount, market_id=market["market_id"])
        record = build(market, report, decision, feed, args.gate, args.amount)
    except Refused as refusal:
        print(f"Refusing to publish.\n\n{refusal}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(record, indent=2))
    else:
        print(runbook(record))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
