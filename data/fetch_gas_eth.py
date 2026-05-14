"""Fetch auxiliary data: Ethereum gas price (Dune) + ETH/USD price (CoinGecko).

- Gas: `gas.gas_price` table on Dune, hourly median (gwei).
- ETH/USD: CoinGecko free API `/coins/ethereum/market_chart/range`, hourly close.

Both join on UTC hourly `DatetimeIndex` named `time` so they slot into
fractal-defi's `Observation.states` dict alongside Aave/Compound rates.

Output:
- data/cached/eth_gas_gwei_hourly_2024-11_to_2026-04.parquet
- data/cached/eth_usd_hourly_2024-11_to_2026-04.parquet

Run: python -m data.fetch_gas_eth
"""
# TODO Week 1 Day 3 (20 May 2026)
raise NotImplementedError("Implement in Week 1 Day 3")
