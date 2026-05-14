"""Aave V3 protocol-subgraph rate-history loader via TheGraph decentralized network.

This is a SECOND Aave V3 loader, complementing the existing
`fractal.loaders.aave.AaveV3RatesLoader` which uses Aave's own gateway
(`api.v3.aave.com/graphql`). The gateway is convenient (no API key) but has
two limitations:

1. Hourly granularity is restricted to the LAST_DAY window enum;
   LAST_SIX_MONTHS / LAST_YEAR return daily aggregates only.
2. The gateway does NOT expose utilization, total liquidity, total debt —
   only annualized APYs.

For multi-month hourly backtests AND for utilization-driven strategies
(such as our MCDM allocator) we need the protocol-subgraph instead. This
loader queries `reserveParamsHistoryItems` on the decentralized-network
Aave V3 subgraph, paginated, returning a `LendingHistory` PLUS the extra
fields (utilization, total_liquidity, total_variable_debt) as additional
columns on the underlying DataFrame.

NOTE this is an Extra+1 candidate; staged here pending the project's
real-data validation before PR submission. The fractal-defi `LendingHistory`
struct currently exposes only (lending_rate, borrowing_rate, time); the
extra columns ride along on the DataFrame but are NOT part of the typed
return. Productionising would add them to the struct as Optional fields.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import pandas as pd

from fractal.loaders._dt import to_seconds, to_utc, utcnow
from fractal.loaders.base_loader import LoaderType
from fractal.loaders.structs import LendingHistory
from fractal.loaders.thegraph.base_graph_loader import (
    ArbitrumGraphLoader,
    GraphLoaderException,
    validate_evm_address,
)


# Aave V3 Ethereum protocol-subgraph on the decentralized network.
# Verify current deployment ID at:
#   https://thegraph.com/explorer/subgraphs?search=aave-v3-ethereum
# This ID is the long-running official deployment as of 2025-Q4. If it
# breaks, search the explorer and replace; the rest of the loader is
# deployment-agnostic.
AAVE_V3_ETHEREUM_SUBGRAPH_ID = "Cd2gEDVeqnjBn1hSeqFMitw8Q1iiyV9FYUZkLNRcL87g"

# Common reserve addresses (Ethereum mainnet)
USDC_ETH = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
USDT_ETH = "0xdac17f958d2ee523a2206206994597c13d831ec7"
DAI_ETH = "0x6b175474e89094c44da98b954eedeac495271d0f"
WETH_ETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"


class AaveV3ProtocolSubgraphRatesLoader(ArbitrumGraphLoader):
    """Hourly per-reserve rate + utilization + balances history via TheGraph.

    Returns:
        `LendingHistory` (DataFrame subclass) with the protocol-subgraph
        equivalents of the gateway loader's `lending_rate` / `borrowing_rate`
        columns, PLUS three extra columns on the same DataFrame:

            * `utilization`            [0, 1]
            * `total_liquidity`        units of underlying asset (e.g. USDC)
            * `total_variable_debt`    units of underlying asset

        Sign convention matches the existing AaveV3RatesLoader:

            balance *= 1 + rate         applied per period in AaveEntity

        with `lending_rate` and `borrowing_rate` expressed as per-period
        rates: `apr_annual / ((365*24) / resolution_hours)`.

    Args:
        api_key:           TheGraph API key (https://thegraph.com/studio).
        reserve:           Underlying-asset address (e.g. USDC_ETH).
        start_time:        UTC datetime; floor.
        end_time:          UTC datetime; cap (defaults to now).
        resolution:        Hours per row in the rate normalization. 1 = hourly
                           per-period rate. Matches gateway-loader convention.
        loader_type:       Cache format (parquet recommended).
        subgraph_id:       Override the default deployment ID if needed.
    """

    _BATCH_LIMIT = 1000

    # Annualized in RAY (1e27) per-second; we convert to per-period to match
    # the existing gateway loader's units. `_RAY` and `_SECS_PER_YEAR` here:
    _RAY = 10 ** 27
    _SECS_PER_YEAR = 31_536_000  # 365 * 24 * 60 * 60

    def __init__(
        self,
        api_key: str,
        reserve: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        resolution: int = 1,
        loader_type: LoaderType = LoaderType.CSV,
        subgraph_id: str = AAVE_V3_ETHEREUM_SUBGRAPH_ID,
    ) -> None:
        super().__init__(
            api_key=api_key,
            subgraph_id=subgraph_id,
            loader_type=loader_type,
        )
        self.reserve: str = validate_evm_address(reserve, field="reserve")
        self.start_time: Optional[datetime] = to_utc(start_time)
        self.end_time: Optional[datetime] = to_utc(end_time)
        self._resolution: int = int(resolution)

    def _cache_key(self) -> str:
        s = to_seconds(self.start_time) if self.start_time is not None else "open"
        e = to_seconds(self.end_time) if self.end_time is not None else "now"
        return f"aave-v3-eth-{self.reserve}-{s}-{e}-{self._resolution}"

    # ---- extract -----------------------------------------------------------

    def extract(self) -> None:
        """Paginated descending pull of reserveParamsHistoryItems for this reserve."""
        cursor = to_seconds(self.end_time) if self.end_time is not None else int(utcnow().timestamp())
        floor = to_seconds(self.start_time) if self.start_time is not None else None

        rows: List[dict] = []
        while True:
            query = """
            {
              reserveParamsHistoryItems(
                first: %d,
                orderBy: timestamp, orderDirection: desc,
                where: {
                  reserve_: { underlyingAsset: "%s" },
                  timestamp_lt: %d
                }
              ) {
                timestamp
                liquidityRate
                variableBorrowRate
                utilizationRate
                totalLiquidity
                totalCurrentVariableDebt
              }
            }
            """ % (self._BATCH_LIMIT, self.reserve, cursor)
            data = self._make_request(query)
            batch = data.get("reserveParamsHistoryItems") or []
            if not batch:
                break
            rows.extend(batch)
            last_ts = int(batch[-1]["timestamp"])
            if floor is not None and last_ts <= floor:
                break
            if len(batch) < self._BATCH_LIMIT:
                break
            cursor = last_ts

        if not rows:
            self._data = pd.DataFrame(
                columns=[
                    "date", "lending_rate", "borrowing_rate",
                    "utilization", "total_liquidity", "total_variable_debt",
                ]
            )
            return

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["timestamp"].astype(int), unit="s", utc=True)

        # RAY-per-second -> annualized APR (simple, matching how gateway emits it)
        # Then divide by (year-hours / resolution-hours) to get per-period.
        scale_to_period = self._SECS_PER_YEAR / max(self._resolution * 3600, 3600)
        df["lending_rate"] = df["liquidityRate"].astype(float) / self._RAY * self._SECS_PER_YEAR / scale_to_period
        df["borrowing_rate"] = df["variableBorrowRate"].astype(float) / self._RAY * self._SECS_PER_YEAR / scale_to_period

        # utilizationRate is WAD (1e18 = 1.0). Sometimes the subgraph emits it
        # in a different convention; we sanity-clip to [0, 1.05].
        u_raw = df["utilizationRate"].astype(float)
        u = u_raw / 1e18 if u_raw.max() > 2 else u_raw  # heuristic for WAD vs ratio
        df["utilization"] = u.clip(0.0, 1.05)

        df["total_liquidity"] = df["totalLiquidity"].astype(float)
        df["total_variable_debt"] = df["totalCurrentVariableDebt"].astype(float)

        self._data = df[
            ["date", "lending_rate", "borrowing_rate",
             "utilization", "total_liquidity", "total_variable_debt"]
        ]

    # ---- transform ---------------------------------------------------------

    def transform(self) -> None:
        cols = [
            "date", "lending_rate", "borrowing_rate",
            "utilization", "total_liquidity", "total_variable_debt",
        ]
        if self._data is None or self._data.empty:
            self._data = pd.DataFrame(columns=cols)
            return

        df = self._data.sort_values("date").drop_duplicates("date").reset_index(drop=True)

        if self.start_time is not None:
            df = df[df["date"] >= self.start_time]
        if self.end_time is not None:
            df = df[df["date"] <= self.end_time]

        # Sign-convention assertion (the v1.4.0 lock-in test)
        if (df["borrowing_rate"] < df["lending_rate"]).any():
            n = (df["borrowing_rate"] < df["lending_rate"]).sum()
            raise GraphLoaderException(
                f"Aave subgraph returned {n} rows with borrowing_rate < lending_rate "
                f"(protocol-impossible). Sign-flip bug in subgraph schema or our parser?"
            )

        self._data = df[cols].reset_index(drop=True)

    def load(self) -> None:
        self._load(self._cache_key())

    # ---- read --------------------------------------------------------------

    def read(self, with_run: bool = False) -> LendingHistory:
        if with_run:
            self.run()
        else:
            self._read(self._cache_key())
        if self._data is None or self._data.empty:
            return LendingHistory(lending_rates=[], borrowing_rates=[], time=[])

        # Note: LendingHistory.__init__ only takes (lending_rates, borrowing_rates,
        # time). The extra cols stay on the DataFrame because LendingHistory is
        # a DataFrame subclass — we just write them post-construction so
        # downstream consumers can `df.utilization` etc.
        hist = LendingHistory(
            lending_rates=self._data["lending_rate"].astype(float).fillna(0.0).values,
            borrowing_rates=self._data["borrowing_rate"].astype(float).fillna(0.0).values,
            time=pd.to_datetime(self._data["date"], utc=True).values,
        )
        hist["utilization"] = self._data["utilization"].astype(float).fillna(0.0).values
        hist["total_liquidity"] = self._data["total_liquidity"].astype(float).fillna(0.0).values
        hist["total_variable_debt"] = self._data["total_variable_debt"].astype(float).fillna(0.0).values
        return hist


__all__ = ["AaveV3ProtocolSubgraphRatesLoader", "AAVE_V3_ETHEREUM_SUBGRAPH_ID", "USDC_ETH"]
