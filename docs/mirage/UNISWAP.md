# Uniswap v3 reference and exact-size exit check

MIRAGE queries Ethereum Uniswap v3 as a price reference independent of a Morpho market's configured oracle. It also simulates selling a **specified collateral amount** through QuoterV2. The resulting finding changes the allocator's entry decision. A quote is not a transaction, and no wallet, approval, transfer or swap is requested by this integration.

## Reproduce

From the repository root, using Python 3.11+:

```python
from mirage.chain.rpc import RpcClient
from mirage.chain.uniswap import collect_reference, replay_reference
from mirage.detectors.reference_price import detect as reference_check
from mirage.detectors.exit_depth import detect as exit_check

rpc = RpcClient()
anchor = rpc.anchor(25938110)
observation = collect_reference(
    rpc,
    "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",  # WBTC
    "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
    anchor,
    scenario_notional_loan="10000",
    routing_policy="direct-first/1",  # reproduce the historical example below
)
assert rpc.anchor(anchor.number).hash == anchor.hash
print(reference_check(observation))
print(exit_check(observation))

# Safe offline replay: prices and output amounts are rebuilt from raw calls.
replayed = replay_reference(observation)  # never connects to any RPC
assert replayed["quote"]["amount_out_raw"] == observation["quote"]["amount_out_raw"]
```

`scenario_notional_loan` is an explicitly declared hypothetical sale valued in loan-token units at the collected TWAP. It is **not** the user's position, borrower debt, a dollar guarantee, or total liquidation demand. For an actual specified collateral quantity, use `amount_in_raw=<integer>` instead. The two parameters are mutually exclusive. Omitting both leaves the exit check `insufficient`; MIRAGE does not invent a liquidation size. Omit `routing_policy` for new captures: the default `compare-direct-weth/1` compares direct and WETH exits as described below.

```console
python -m unittest discover -s tests -p test_mirage_uniswap.py -v
```

## Implementation map

| Component | Code |
|---|---|
| Deployment addresses, ABI and all RPC reads | [`mirage/chain/uniswap.py`](../../mirage/chain/uniswap.py), `collect_reference` |
| Signed int56 arrays, wrap handling and mean-tick floor | Same file, `decode_observe`, `consult_values` |
| Human-unit price and token direction | Same file, `tick_price`, `sqrt_price` |
| QuoterV2 tuple and full-input boundary check | Same file, `encode_quote`, `decode_quote` |
| Replay from raw calls with no network fallback | Same file, `replay_reference` |
| Pure oracle/reference comparison | [`mirage/detectors/reference_price.py`](../../mirage/detectors/reference_price.py) |
| Pure specified-sale policy | [`mirage/detectors/exit_depth.py`](../../mirage/detectors/exit_depth.py) |
| Offline and independent ABI regressions | [`tests/test_mirage_uniswap.py`](../../tests/test_mirage_uniswap.py) |

## Bounded route policy

1. Query the canonical Ethereum factory's `getPool` for fee tiers 100, 500, 3000 and 10000. These mean 0.01%, 0.05%, 0.3% and 1%; the factory may enable other tiers, which this version does not search.
2. Verify both token addresses; read `slot0`, active `liquidity` and `observe([1800, 0])` at the same numeric block. A pool with missing history is excluded, even if spot is available. The time window is configurable.
3. Among usable **direct** pools, select the greatest harmonic mean liquidity over that window. Comparing this raw value is valid only between pools with the same token pair. No USD interpretation is attached to `liquidity()`.
4. For a specified sale, also inspect collateral/WETH and WETH/loan even when a direct reference exists. Select each leg independently by harmonic liquidity and multiply the directed human-unit references. The pool addresses differ, so quoting each leg at the same original state models the unsplit path without reusing modified pool state. When no direct reference is usable, the WETH route also supplies the reference.
5. Compute the collateral amount once from the chosen reference TWAP. Quote the direct and WETH candidates for **exactly the same collateral input**, then select the greater loan-token output among complete quotes. Retain both candidates, their route TWAP/spot values and raw call evidence. A failed direct quote does not suppress a successful WETH quote. This remains a bounded comparison, not a global search: other pools, fee tiers, split routes, protocols or redemption facilities may offer better execution.

The maximum search is 12 pools across three pairs and at most three quote calls. All network operations use the existing bounded-retry RPC client. There are no JSON-RPC batches. Each successful read is saved as `(to, data, numeric block, raw result, block hash, method)`.

Reference selection and exit selection are explicit separate fields: `observation.route` is the reference path, and `observation.quote.route` is the selected execution path. Reference selection remains direct-first and is not claimed to be globally optimal. Gas costs are excluded from output comparison.

New observations store `routing_policy: "compare-direct-weth/1"`. Older observations lacking this field replay with `direct-first/1`, preserving the original direct-first behavior and its original numerical outcomes. They are never silently upgraded into evidence that an unrecorded alternative route was inspected. A fresh capture is required to demonstrate the new policy.

## Units and decision rules

The reference is a **geometric time-weighted price**, not an arithmetic average of sampled prices. Compute the arithmetic mean tick from signed cumulative ticks, rounding toward negative infinity. If input is token0, the human output/input price is `1.0001**mean_tick * 10**(decimals_in-decimals_out)`; otherwise invert the tick exponent. Spot comes from `sqrtPriceX96**2 / 2**192` with the same direction and decimal normalization. Decimal arithmetic uses 80 digits of precision; this analytical reference is not an integer swap settlement quote.

QuoterV2 receives the static tuple `(tokenIn, tokenOut, amountIn, fee, sqrtPriceLimitX96)`. Its non-view method is run using `eth_call`; no transaction is submitted. The returned amount includes pool fees. For the scenario, MIRAGE computes:

```text
execution_price = amount_out_raw / amount_in_raw * 10**(decimals_in-decimals_out)
fee_inclusive_impact_bps = (1 - execution_price / selected_exit_route_spot) * 10000
twap_shortfall_bps = (1 - execution_price / reference_twap) * 10000
```

The default exit policy blocks entry when either shortfall exceeds 500 bps. It passes only this quoted size under the stated policy; it never declares the whole market liquid. A read failure, zero quote, missing route, missing size or ambiguous full input consumption is `insufficient`. A failed quote is not evidence that liquidity is literally zero.

The reference policy compares an optional normalized Morpho price against the TWAP, with a default absolute deviation limit of 500 bps. Spot/TWAP disagreement also produces a warning. Identical collateral and loan addresses have a one-to-one identity price, explicitly labeled `token-identity`; this is not represented as a Uniswap observation.

## Verified mainnet example

Collected on 9 September 2026 using individual RPC calls. The selected pool's `token0`, `token1`, `slot0`, `liquidity`, `observe`, and the QuoterV2 call were repeated through a second provider configuration; all six results matched byte for byte. The block hash was independently rechecked.

| Evidence | Value |
|---|---|
| Ethereum block | `25938110` |
| Block hash | `0xc5fc61b689baf4bbb21c0fce9041c7718935bbe89250f5e287d875a1583e2fde` |
| Pair / token decimals | WBTC / USDC; 8 / 6 |
| Selected pool | `0x99ac8ca7087fa4a2a1fb6357269965a2014abc35` |
| Fee / window / mean tick | 3000 / 1800 seconds / 66721 |
| Reference, USDC per WBTC | `78978.9470761540758893518355` |
| Spot, USDC per WBTC | `78984.8434010254583366826062` |
| Hypothetical scenario | `10000` USDC at TWAP |
| Input, WBTC base units | `12661602` = 0.12661602 WBTC |
| Quoted output, USDC base units | `9968488167` = 9968.488167 USDC |
| Fee-inclusive impact against spot | `32.2559368175` bps |
| Shortfall against TWAP | `31.5117757542` bps |
| Initialized ticks crossed | 2 |

These are historical block-bound observations, not current prices. Repeating the example requires an RPC that serves this block. The raw QuoterV2 input and output for this example are:

```json
{
  "to": "0x61ffe014ba17989e743c5f6cb21bf9697530b21e",
  "data": "0xc6a5026a0000000000000000000000002260fac5e5542a773aa44fbcfedf7c193bc2c599000000000000000000000000a0b86991c6218b36c1d19d4a2e9eb0ce3606eb480000000000000000000000000000000000000000000000000000000000c133620000000000000000000000000000000000000000000000000000000000000bb80000000000000000000000000000000000000000000000000000000000000000",
  "block": 25938110,
  "result": "0x00000000000000000000000000000000000000000000000000000002522b0ee7000000000000000000000000000000000000001c190cf2c141745776e4f66a7f0000000000000000000000000000000000000000000000000000000000000002000000000000000000000000000000000000000000000000000000000001f468"
}
```

## Why exit route comparison matters: wstETH

The first version's direct-first policy was too restrictive for the selected wstETH/USDC market: a thin direct pool produced poor execution although a deeper WETH path was available. This was found from live evidence, and the improvement was verified by repeating all three candidate Quoter calls individually through a second RPC provider. The immutable old snapshot remains unchanged and still reproduces the old block verdict.

At Ethereum block **25938082**, hash `0x7647a0738f03a46dd0c957cca4664d73f9bcc7c981405a8ccb00e3bd08ede2cb`, both candidates sold exactly **3220832145173417247 wstETH base units** (3.220832145173417247 wstETH). This amount represents the declared 10,000-USDC scenario at the unchanged reference TWAP of 3104.7876912758 USDC per wstETH.

| Candidate | Quoted output in USDC | Fee-inclusive impact against its own spot |
|---|---:|---:|
| Direct wstETH/USDC, fee 500 | 5927.556111 | 4084.05569 bps |
| wstETH/WETH, fee 100 → WETH/USDC, fee 500 | 10007.772538 | 6.38730 bps |

The WETH path uses `0x109830a1aaad605bbf02a9dfa7b0b92ec2fb7daa` and `0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640`. Its TWAP is 3109.1372205309 and its spot is 3109.1868293538 USDC per wstETH. The new policy selects this path and passes the specified-size exit check; the old direct-only policy blocks it. This difference describes supported route execution, not overall market safety.

The output slightly exceeds the scenario's reference valuation because the two routes have slightly different prices. It is not a realized gain or an arbitrage claim. The selected input amount was never changed between candidates.

## Limits

- A 30-minute TWAP may still be manipulated or economically stale, especially in a thin pool. Selecting the greatest liquidity within a pair does not establish a universal minimum economic security level.
- Only v3 Ethereum pools, direct routes and one WETH intermediate are covered. No Pendle, Curve, Uniswap v2/v4, offchain liquidity or redemption capacity is claimed.
- A one-block quote does not guarantee inclusion, unchanged liquidity, MEV protection, gas cost, liquidator profitability or future execution. Transfer-tax, rebasing, hooks and other nonstandard token behavior are not validated by the Quoter callback simulation.
- QuoterV2 exact-input output does not report the amount actually consumed. If the final square-root price reaches its default min/max boundary, MIRAGE rejects the quote as ambiguous instead of assuming a full fill.
- `replay_reference` recalculates display and policy inputs from raw evidence. It checks consistency and provenance fields; it cannot cryptographically authenticate RPC data fabricated by an adversarial snapshot writer.
- The two pure detectors accept already collected or replayed observations and perform no network operations. Saved observations must pass `replay_reference` before use in the full report.

## Primary references

- [Official Ethereum deployment addresses](https://developers.uniswap.org/docs/protocols/v3/deployments/v3-ethereum-deployments) for the factory, QuoterV2 and WETH.
- [Uniswap OracleLibrary](https://github.com/Uniswap/v3-periphery/blob/main/contracts/libraries/OracleLibrary.sol) for cumulative observations, negative-tick floor and pair-comparable harmonic liquidity.
- [IQuoterV2 interface](https://github.com/Uniswap/v3-periphery/blob/main/contracts/interfaces/IQuoterV2.sol) for tuple field order and returned data.
- [QuoterV2 implementation](https://github.com/Uniswap/v3-periphery/blob/main/contracts/lens/QuoterV2.sol) for callback/revert simulation and the limits of exact-input output.
