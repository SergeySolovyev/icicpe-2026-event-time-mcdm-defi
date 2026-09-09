"""Capture demo evidence with single calls independently checked at two providers.

Run: python -m scripts.mirage_capture_demo --block 25937912
This reads mainnet only. It never signs or sends a transaction.
"""
import argparse
from pathlib import Path

from mirage.chain.rpc import RpcClient
from mirage.scan import capture, report_from_snapshot, save_snapshot

MARKETS = (
    "0x8eaf7b29f02ba8d8c1d7aeb587403dcb16e2e943e4e2f5f94b0963c2386406c9",
    "0xbd1ad3b968f5f0552dbd8cf1989a62881407c5cccf9e49fb3657c8731caf0c1f",
)
PROVIDERS = ("https://ethereum-rpc.publicnode.com", "https://eth.drpc.org",
             "https://gateway.tenderly.co/public/mainnet")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--block", type=int, required=True)
    args = parser.parse_args()
    payload, confirmed = None, []
    for endpoint in PROVIDERS:
        client = RpcClient([endpoint], tries=2, timeout=15)
        try:
            anchor = client.anchor(args.block)
            observed = capture(client, anchor, MARKETS, {"kind": "explicit-market", "market_count": 2})
        except (ValueError, RuntimeError) as error:
            print(f"Provider unavailable: {endpoint} ({type(error).__name__})", flush=True)
            continue
        if payload is not None and (payload["anchor"] != observed["anchor"] or payload["rows"] != observed["rows"]):
            raise RuntimeError("Independent providers disagree; no snapshot saved")
        payload = observed
        confirmed.append(endpoint)
        print(f"Single-call capture confirmed: {endpoint}, block {anchor.number}", flush=True)
        if len(confirmed) == 2:
            break
    if len(confirmed) < 2:
        raise RuntimeError("Two independent provider captures required; no snapshot saved")
    payload["source"]["verification"] = {"method": "independent-single-eth_calls", "providers": confirmed}
    destination = Path(__file__).resolve().parents[1] / "mirage" / "snapshots" / f"mainnet-{args.block}.json.gz"
    save_snapshot(destination, payload)
    print(f"Saved {destination}")
    for verdict in report_from_snapshot(payload).markets:
        metrics = verdict.findings[0].metrics
        print(verdict.market_id, metrics["available_liquidity_raw"], metrics["share_price_multiple_vs_initial"])


if __name__ == "__main__":
    main()
