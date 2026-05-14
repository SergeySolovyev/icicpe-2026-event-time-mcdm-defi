"""Fetch Compound V3 (Comet) Ethereum cUSDCv3 supply/borrow rates via Messari subgraph.

Pulls 18 months (2024-11-01 - 2026-04-30) of `marketHourlySnapshots` for the
cUSDCv3 market (proxy 0xc3d688B66703497DAA19211EEdff47f25384cdc3), with WAD
(1e18) per-second scaling. Sign convention: per fractal-defi ARCHITECTURE.md,
positive `lending_rate` => collateral grows.

Output: data/cached/compound_v3_usdc_eth_2024-11_to_2026-04.parquet
Columns: time (UTC, hourly), lending_rate, borrowing_rate, utilization,
         total_supplied, total_borrowed

This module is the **primary content of the Extra+1 PR** to fractal-defi —
its production version will live at `fractal/loaders/compound.py` as
`CompoundV3RatesLoader(BaseLoader[LendingHistory])` following the Aave
loader pattern in `fractal/loaders/aave.py`.

Per DEEP_RESEARCH.md §V.B for endpoint + scaling details.

Run: python -m data.fetch_compound
"""
# TODO Week 1 Day 2 (19 May 2026) - also begins Extra+1 PR work
raise NotImplementedError("Implement in Week 1 Day 2; productionize as fractal-defi PR by 12 June")
