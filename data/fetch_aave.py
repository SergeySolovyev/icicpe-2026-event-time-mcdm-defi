"""Fetch Aave V3 Ethereum USDC supply/borrow rates via fractal-defi's AaveV3RatesLoader.

VERIFIED 2026-05-14 against the actual v1.3.2 loader source
(fractal/loaders/aave.py):

ENDPOINT: Aave's OWN gateway at `https://api.v3.aave.com/graphql` — this is
NOT TheGraph. NO `THE_GRAPH_API_KEY` needed for Aave. (The protocol-subgraphs
on the decentralized network are a separate path requiring a key, but the
fractal-defi loader does not use them.)

QUERY SHAPE: the loader does NOT use `reserveParamsHistoryItem` pagination.
Instead it sends one GraphQL request with two variables
(`BorrowAPYHistoryRequest`, `SupplyAPYHistoryRequest`), each parameterized by
{market, underlyingToken, window, chainId}. The `window` enum (`LAST_DAY`,
`LAST_WEEK`, `LAST_MONTH`, `LAST_QUARTER`, `LAST_HALF_YEAR`, `LAST_YEAR`)
selects the smallest covering range. For our 18-month window we issue 2
calls (LAST_YEAR + LAST_HALF_YEAR) and stitch.

SCALING: Aave's gateway returns **already-annualized APY** as a percentage
float (e.g. 5.25 means 5.25% APR). The loader divides by `(365*24)/resolution`
to get **arithmetic per-period rate** — NOT continuous compounding. We must
match this convention exactly in the Compound loader so cross-protocol
spreads are computed in identical units.

UTILIZATION: NOT a native field on this endpoint. The Aave gateway returns
only APY series. For utilization we have to use a different data source:
- Option A: Aave's own subgraph (would need separate auth)
- Option B: Compute from on-chain via `eth_call` on aUSDC.totalSupply() and
            VariableDebtToken.totalSupply(); slow but no API key.
- Option C: Dune Analytics table `aave_v3_ethereum.reserve_data_*` (the
            most pragmatic — already maintained, hourly granularity)

Going with Option C for our backtest data; Extra+1 PR will additionally
fold a `utilization` field into AaveGlobalState computed at load time.

Output: data/cached/aave_v3_usdc_eth_2024-11_to_2026-04.parquet
Columns: time (UTC, hourly), lending_rate, borrowing_rate, utilization,
         total_liquidity, total_variable_debt

Run: python -m data.fetch_aave
"""
# TODO Week 1 Day 1 (18 May 2026)
raise NotImplementedError("Implement in Week 1 Day 1")
