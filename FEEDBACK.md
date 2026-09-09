# Uniswap developer feedback — MIRAGE

**Integration:** Ethereum Uniswap v3 factory discovery, pool oracle observations, and QuoterV2 simulation, added to an existing event-time USDC allocator during ETHOnline 2026. MIRAGE uses these results to permit or veto entry into Morpho Blue markets. This file records feedback from implementation and a successful mainnet verification on 9 September 2026. The external Developer Feedback Form is a separate submission step; this file does not claim that form has been submitted.

## What we built and verified

[`mirage/chain/uniswap.py`](mirage/chain/uniswap.py) calls `getPool`, validates token identities, reads `slot0`, `liquidity` and `observe`, then calls `quoteExactInputSingle` using `eth_call`. [`reference_price.py`](mirage/detectors/reference_price.py) compares oracle/reference prices; [`exit_depth.py`](mirage/detectors/exit_depth.py) checks an explicit collateral-sale scenario. Raw call evidence is retained, and [`replay_reference`](mirage/chain/uniswap.py) reconstructs derived values offline.

The [integration guide](docs/mirage/UNISWAP.md) includes exact addresses, formulas, commands, limits and a mainnet reproduction at block 25938110. A 10,000-USDC hypothetical WBTC sale produced a 9,968.488167-USDC quote on the selected 0.3% pool. That is a simulated scenario at one block, not a trade or a guarantee. Six selected-pool and Quoter results were independently repeated and matched exactly.

## What worked well

- The canonical factory plus deployed QuoterV2 let us produce a useful read-only integration without API credentials, wallet approval, or a transaction. Contract addresses were clear in the Ethereum deployment table.
- Raw `observe` data is small enough to preserve in an audit feed. The oracle library source specifies both negative-tick rounding and harmonic liquidity; these details made deterministic cross-language reproduction possible.
- QuoterV2's initialized-tick count and resulting square-root price give more useful evidence than an approximate reserve-based slippage estimate for concentrated liquidity.

## Friction and concrete suggestions

1. **Make tuple-version differences prominent in quoting guides.** `IQuoterV2.QuoteExactInputSingleParams` places `amountIn` before `fee`; v1 examples and function arguments look deceptively similar. A compact v1/v2 ABI comparison with one exact calldata example would prevent quiet integration mistakes. Our independent `eth_abi` test now checks this field order.

2. **Provide an offchain cumulative-observation example that includes negative ticks and mixed decimals.** An example with a negative cumulative delta not divisible by the window, a token0/token1 inversion, and a 6/18-decimal pair would show three failure modes in one place. We specifically test flooring toward minus infinity, canonical int56 sign extension and cumulative wrap semantics. The Solidity source documents these points, but builders using Python need to translate them accurately.

3. **Document what an exact-input quote does not prove.** The callback reports output and final price, but does not return the consumed input. In the general case of price limits or exhaustion of reachable liquidity, consumers should not equate a returned amount with confirmed full consumption. MIRAGE uses the default limits and rejects their terminal boundary values. An explicit completion indicator or amount-consumed output in a future quoting interface would simplify safety-critical consumers.

4. **Add a lending-risk example distinguishing reference liquidity from executable size.** `liquidity()` is active concentrated liquidity, not dollar TVL or an exit-capacity estimate. Pool selection by harmonic liquidity and Quoter-based size checks solve different problems. We encountered this directly: at block 25938082, the same 3.220832145173417247-wstETH input quoted 5927.556111 USDC in the selected direct pool versus 10007.772538 USDC through WETH. Comparing both routes fixed a false refusal caused by limited routing. A sample combining `observe` with exact, equal-input route comparisons would help teams avoid describing one pool's liquidity as market-wide liquidator capacity.

5. **Show missing observation history as a normal integration state.** We preserve `insufficient` when the requested `observe` window cannot be read, including RPC and history failures, and never replace the TWAP with spot while retaining the TWAP label. Documentation could expose a standard result shape for unavailable history, unsupported routes and quote failure, together with guidance for callers who need conservative decisions.

## Scope and next improvement

The implementation searches four direct v3 fee tiers and two-pool WETH paths. Reference selection remains direct-first, while the exit check compares the selected direct and WETH candidates at exactly the same collateral input and chooses the larger quoted output. Each pair contributes its greatest-harmonic-liquidity pool; other fee combinations and split execution are not exhaustively optimized. The next useful extension is explicit comparison against additional routes and economic-liquidity thresholds, with coverage visible in the verdict. No total-market liquidation capacity or universal oracle safety claim is made.

Primary sources used: [Ethereum deployments](https://developers.uniswap.org/docs/protocols/v3/deployments/v3-ethereum-deployments), [OracleLibrary](https://github.com/Uniswap/v3-periphery/blob/main/contracts/libraries/OracleLibrary.sol), [IQuoterV2](https://github.com/Uniswap/v3-periphery/blob/main/contracts/interfaces/IQuoterV2.sol), and [QuoterV2](https://github.com/Uniswap/v3-periphery/blob/main/contracts/lens/QuoterV2.sol).
