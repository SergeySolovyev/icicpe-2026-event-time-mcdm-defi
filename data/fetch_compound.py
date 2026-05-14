"""Fetch Compound V3 (Comet) Ethereum cUSDCv3 supply/borrow rates via Messari subgraph.

VERIFIED 2026-05-14 against:
- Messari schema-lending.graphql in github.com/messari/subgraphs
- Comet USDC proxy at 0xc3d688B66703497DAA19211EEdff47f25384cdc3
- BaseGraphLoader pattern in fractal/loaders/thegraph/base_graph_loader.py

ENDPOINT: The Graph DECENTRALIZED NETWORK (the hosted service was deprecated
in 2024). URL pattern:
    f"https://gateway.thegraph.com/api/{THE_GRAPH_API_KEY}/subgraphs/id/{DEPLOYMENT_ID}"
The deployment ID for Compound V3 Ethereum is read from
github.com/messari/subgraphs deployment.json at fetch time — do NOT hardcode
(deployments get redeployed when subgraphs upgrade).

PATTERN: subclass `BaseGraphLoader` (fractal/loaders/thegraph/base_graph_loader.py:37)
which provides `_make_request(query)` posting + payload unwrapping. Mirror
the paginated pattern used by uniswap_v3 / uniswap_v2 loaders in the same
directory (first=1000, skip=$skip).

SCHEMA: per Messari `schema-lending.graphql`:
- `Market` exposes `rates: [InterestRate!]` (one per side); rate values are
  **BigDecimal PERCENTAGE** (e.g. 5.25 means 5.25% APR — NOT WAD, NOT RAY).
- `marketHourlySnapshots` mirrors `Market` per hour.
- Fields per hourly snapshot: timestamp, rates, totalDepositBalanceUSD,
  totalBorrowBalanceUSD, inputTokenBalance, variableBorrowedTokenBalance.
- Utilization is computed as totalBorrowBalanceUSD / totalDepositBalanceUSD
  (both already-USD-denominated by the indexer).

SCALING / UNITS — CRITICAL to match Aave loader convention:
    Messari rate (BigDecimal, percent) -> APR decimal -> per-period rate

    apr_decimal = float(rate.rate) / 100.0
    per_period = apr_decimal / ((365 * 24) / resolution)   # arithmetic, matches Aave

Negative rates are protocol-impossible but if a corrupt snapshot returns one,
AaveEntity.update_state will crash with `rate >= -1` assertion (fail loud).

CACHE: per fractal-defi convention, under
    $FRACTAL_DATA_PATH/fractal_data/compoundv3rateloader/<cache_key>.parquet
cache_key = f"{chain_id}-{market_address}-{start_iso}-{end_iso}-{resolution}"

This module is the **primary content of the Extra+1 PR** to fractal-defi —
production version lives at `fractal/loaders/compound.py` as
`CompoundV3RatesLoader(BaseGraphLoader)` mirroring the BaseGraphLoader
pattern and emitting `LendingHistory(lending_rates, borrowing_rates, time)`.

Output: data/cached/compound_v3_usdc_eth_2024-11_to_2026-04.parquet
Columns: time (UTC, hourly), lending_rate, borrowing_rate, utilization,
         total_supplied_usd, total_borrowed_usd

Run: python -m data.fetch_compound
"""
# TODO Week 1 Day 2 (19 May 2026) — also begins Extra+1 PR work
raise NotImplementedError(
    "Implement in Week 1 Day 2; productionize as fractal-defi PR by 12 June"
)
