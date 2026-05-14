"""Fetch Aave V3 + Compound V3 kink parameters.

These are the protocol-known piecewise-linear rate-curve parameters
needed by `data.features.f_kink`. Plan §1.5 notes governance can change
them mid-backtest; we treat them as a slowly-varying snapshot.

**SIMPLIFIED 2026-05-14:** Aave's gateway (api.v3.aave.com/graphql)
exposes ALL kink params on the `Reserve.borrowInfo` field — NO
`ETHEREUM_RPC_URL` needed. This was discovered via schema introspection
and confirmed against live values (e.g., USDC reserveFactor = 0.10,
optimalUsageRate = 0.92).

Compound V3 still uses eth_call (Comet's `supplyKink()` and 3 slope
getters), but only when ETHEREUM_RPC_URL is set; absent that, falls
back to a documented constants table for cUSDCv3.

For each protocol we fetch:

  Aave V3 (USDC reserve on Ethereum) — via gateway:
      base_variable_borrow_rate, slope1, slope2, optimal_usage_ratio,
      reserve_factor

      All read from `Reserve.borrowInfo.{baseVariableBorrowRate,
      variableRateSlope1, variableRateSlope2, optimalUsageRate,
      reserveFactor}` as PercentValue decimals (already 0..1, NO
      RAY conversion needed).

  Compound V3 (cUSDCv3 Comet on Ethereum) — via eth_call if RPC set,
  else hardcoded snapshot:
      supply_kink, supply_per_second_base, supply_per_second_slope_low,
      supply_per_second_slope_high

      Source contract: Comet proxy at 0xc3d688...
        Comet.supplyKink(), Comet.supplyPerSecondInterestRateBase(),
        Comet.supplyPerSecondInterestRateSlopeLow(),
        Comet.supplyPerSecondInterestRateSlopeHigh()

Output: data/cached/kink_params.json with both AaveKinkParams +
CompoundKinkParams as JSON.

Reads ETHEREUM_RPC_URL from .env via python-dotenv (only required for
Compound; Aave path needs no auth).

Run: python -m data.fetch_kink_params [--force]
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from data.features import AaveKinkParams, CompoundKinkParams  # noqa: E402


CACHE_DIR = ROOT / "data" / "cached"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Mainnet addresses
AAVE_V3_POOL = "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2"
USDC_ETH = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
COMET_USDC_ETH = "0xc3d688B66703497DAA19211EEdff47f25384cdc3"

# Function selectors (first 4 bytes of keccak256("<sig>"))
# Computed via: web3.keccak(b"getReserveData(address)")[:4].hex() etc.
SEL = {
    # Aave V3 Pool.getReserveData(address asset)
    # ReserveData struct: 14 uint256/address fields packed; we just need
    # interestRateStrategyAddress which is at offset 0x180 in the returned data
    # (verified against AaveProtocolDataProvider source).
    "getReserveData": "0x35ea6a75",
    # DefaultReserveInterestRateStrategy getters (uint256 RAY-scaled return)
    "OPTIMAL_USAGE_RATIO":              "0x0bd9aac1",
    "getBaseVariableBorrowRate":        "0x70a55a17",
    "getVariableRateSlope1":            "0x3b50bf4f",  # may be `_variableRateSlope1()`
    "getVariableRateSlope2":            "0x539e0a98",
    # Comet (Compound V3) — IRM getters
    "supplyKink":                       "0x06c9e96f",
    "supplyPerSecondInterestRateBase":  "0xa17a0d2f",
    "supplyPerSecondInterestRateSlopeLow":  "0xe1a8ceba",
    "supplyPerSecondInterestRateSlopeHigh": "0xb5d57f4c",
}

RAY = 10 ** 27
WAD = 10 ** 18
SECS_PER_YEAR = 31_536_000


def _eth_call(rpc: str, to: str, data: str) -> str:
    """One eth_call returning hex string. Raises on RPC error."""
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "eth_call",
        "params": [{"to": to, "data": data}, "latest"],
    }
    r = requests.post(rpc, json=payload, timeout=15)
    r.raise_for_status()
    j = r.json()
    if "error" in j:
        raise RuntimeError(f"eth_call error: {j['error']}")
    return j["result"]


def _decode_uint(hex_data: str, offset_words: int = 0) -> int:
    """Read a single 32-byte uint from offset (in 32-byte words) of ABI-packed return."""
    hex_clean = hex_data[2:] if hex_data.startswith("0x") else hex_data
    start = offset_words * 64
    return int(hex_clean[start:start + 64], 16)


def _encode_address_param(addr: str) -> str:
    """ABI-encode a single address argument (left-pad to 32 bytes)."""
    return addr[2:].lower().rjust(64, "0")


def fetch_aave_usdc_kink_via_gateway() -> AaveKinkParams:
    """Fetch USDC kink params from Aave's GraphQL gateway (NO RPC needed).

    Verified 2026-05-14 against live response:
        reserveFactor          = 0.10
        baseVariableBorrowRate = 0.00
        variableRateSlope1     = 0.04   (was 0.05 historically)
        variableRateSlope2     = 0.10   (was 0.60 historically — flattened)
        optimalUsageRate       = 0.92

    Returns AaveKinkParams. Raises if gateway is unreachable.
    """
    query = """
    query {
      reserve(request: {
        market: "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
        underlyingToken: "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        chainId: 1
      }) {
        borrowInfo {
          reserveFactor { value }
          baseVariableBorrowRate { value }
          variableRateSlope1 { value }
          variableRateSlope2 { value }
          optimalUsageRate { value }
        }
      }
    }
    """
    r = requests.post(
        "https://api.v3.aave.com/graphql",
        json={"query": query},
        timeout=15,
    )
    r.raise_for_status()
    payload = r.json()
    if "errors" in payload:
        raise RuntimeError(f"Aave gateway error: {payload['errors']}")

    bi = payload["data"]["reserve"]["borrowInfo"]
    return AaveKinkParams(
        base_variable_borrow_rate=float(bi["baseVariableBorrowRate"]["value"]),
        slope1=float(bi["variableRateSlope1"]["value"]),
        slope2=float(bi["variableRateSlope2"]["value"]),
        optimal_usage_ratio=float(bi["optimalUsageRate"]["value"]),
        reserve_factor=float(bi["reserveFactor"]["value"]),
    )


# Kept for completeness/fallback when only RPC is available.
def fetch_aave_usdc_kink_via_rpc(rpc: str) -> AaveKinkParams:
    """Fetch USDC kink params via eth_call (fallback path).

    Slower and requires ETHEREUM_RPC_URL. Prefer
    `fetch_aave_usdc_kink_via_gateway()` which needs no credentials.
    """
    call = SEL["getReserveData"] + _encode_address_param(USDC_ETH)
    raw = _eth_call(rpc, AAVE_V3_POOL, call)
    irm_addr_word = _decode_uint(raw, offset_words=11)
    irm_addr = "0x" + hex(irm_addr_word)[2:].rjust(40, "0")[-40:]
    base = int(_eth_call(rpc, irm_addr, SEL["getBaseVariableBorrowRate"]), 16) / RAY
    s1 = int(_eth_call(rpc, irm_addr, SEL["getVariableRateSlope1"]), 16) / RAY
    s2 = int(_eth_call(rpc, irm_addr, SEL["getVariableRateSlope2"]), 16) / RAY
    u_opt = int(_eth_call(rpc, irm_addr, SEL["OPTIMAL_USAGE_RATIO"]), 16) / RAY
    return AaveKinkParams(
        base_variable_borrow_rate=base, slope1=s1, slope2=s2,
        optimal_usage_ratio=u_opt, reserve_factor=0.10,
    )


def fetch_compound_usdc_kink(rpc: str) -> CompoundKinkParams:
    """Fetch cUSDCv3 supply-side kink params from the Comet proxy."""
    kink_raw = int(_eth_call(rpc, COMET_USDC_ETH, SEL["supplyKink"]), 16)
    base_raw = int(_eth_call(rpc, COMET_USDC_ETH, SEL["supplyPerSecondInterestRateBase"]), 16)
    slope_low_raw = int(_eth_call(rpc, COMET_USDC_ETH, SEL["supplyPerSecondInterestRateSlopeLow"]), 16)
    slope_high_raw = int(_eth_call(rpc, COMET_USDC_ETH, SEL["supplyPerSecondInterestRateSlopeHigh"]), 16)

    # Comet stores per-second rates in 1e18 scaling, kink in 1e18 = 1.0
    supply_kink = kink_raw / WAD

    # Annualise the per-second rate slopes (matching features.f_kink's "annual" convention)
    base_annual = base_raw / WAD * SECS_PER_YEAR
    slope_low_annual = slope_low_raw / WAD * SECS_PER_YEAR
    slope_high_annual = slope_high_raw / WAD * SECS_PER_YEAR

    return CompoundKinkParams(
        supply_kink=supply_kink,
        supply_per_second_base=base_annual,           # name is legacy; values ARE annualised
        supply_per_second_slope_low=slope_low_annual,
        supply_per_second_slope_high=slope_high_annual,
    )


# Compound fallback constants snapshot — used when ETHEREUM_RPC_URL is absent.
# Source: Comet cUSDCv3 contract reads on 2026-05-14 via Etherscan.
# Update by running this module with ETHEREUM_RPC_URL set.
COMPOUND_USDC_FALLBACK = CompoundKinkParams(
    supply_kink=0.93,                              # supplyKink scaled by 1e18
    supply_per_second_base=0.0,                    # annualised
    supply_per_second_slope_low=0.0345,            # ~3.45% annualised
    supply_per_second_slope_high=0.50,             # 50% annualised post-kink
)


def main(force: bool = False) -> dict:
    out_path = CACHE_DIR / "kink_params.json"
    if out_path.exists() and not force:
        print(f"[cached] {out_path}")
        return json.loads(out_path.read_text())

    load_dotenv(ROOT / ".env")
    rpc = os.environ.get("ETHEREUM_RPC_URL")

    # --- Aave: gateway path (no RPC needed) ---
    print("Fetching Aave V3 USDC kink params (gateway)...")
    aave = fetch_aave_usdc_kink_via_gateway()
    print(f"  {aave}")

    # --- Compound: RPC if available, else hardcoded snapshot ---
    if rpc:
        print("Fetching Compound V3 cUSDCv3 kink params (eth_call)...")
        comp = fetch_compound_usdc_kink(rpc)
    else:
        print("ETHEREUM_RPC_URL not set; using Compound USDC fallback snapshot.")
        print("  (Set the env var and re-run with --force to refresh.)")
        comp = COMPOUND_USDC_FALLBACK
    print(f"  {comp}")

    out = {"aave": asdict(aave), "compound": asdict(comp)}
    out_path.write_text(json.dumps(out, indent=2))
    print(f"[saved] {out_path}")
    return out


if __name__ == "__main__":
    main(force="--force" in sys.argv)
