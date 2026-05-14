"""Fetch Aave V3 Ethereum USDC supply/borrow rates via fractal-defi's AaveV3RatesLoader.

Pulls 18 months (2024-11-01 - 2026-04-30) of `reserveParamsHistoryItems`
filtered on USDC (0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48), with RAY (1e27)
per-second scaling, paginated in <=1000-row chunks, cached as parquet under
$FRACTAL_DATA_PATH per fractal-defi loader convention.

Output: data/cached/aave_v3_usdc_eth_2024-11_to_2026-04.parquet
Columns: time (UTC, hourly), lending_rate, borrowing_rate, utilization,
         total_liquidity, total_variable_debt

Per DEEP_RESEARCH.md §V.A GraphQL template and APY conversion formula.

Run: python -m data.fetch_aave
"""
# TODO Week 1 Day 1 (18 May 2026)
raise NotImplementedError("Implement in Week 1 Day 1")
