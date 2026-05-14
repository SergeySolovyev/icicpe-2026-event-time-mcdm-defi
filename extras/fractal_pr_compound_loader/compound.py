"""Compound V3 (Comet) lending-rate-history loader via the Messari subgraph.

This is the production version of the Extra+1 PR loader, staged here
pending project-level validation before submission to
`Logarithm-Labs/fractal-defi`.

Comet (Compound V3) markets are single-base-asset: only the BASE asset
earns supply yield (collateral assets do not, so this loader pulls only
the base market for each Comet). For cUSDCv3 on Ethereum the base is USDC
and the proxy is `0xc3d688B66703497DAA19211EEdff47f25384cdc3`.

Messari schema reference:
    https://github.com/messari/subgraphs/blob/master/schema-lending.graphql

Key fields used:
    Market.rates: [InterestRate!]
        InterestRate.side: VARIABLE_BORROW | STABLE_BORROW | LENDER
        InterestRate.rate: BigDecimal (PERCENTAGE — 5.25 means 5.25% APR)
    MarketHourlySnapshot:
        timestamp, market, rates, totalDepositBalanceUSD, totalBorrowBalanceUSD,
        inputTokenBalance, variableBorrowedTokenBalance, ...

CRITICAL: Messari emits `rate.rate` as a percentage (NOT WAD, NOT RAY).
Conversion to per-period rate (matching AaveV3RatesLoader convention):

    per_period_rate = (rate / 100.0) / ((365 * 24) / resolution_hours)

Negative rates are protocol-impossible. If a corrupt snapshot returns one,
we clip to 0 with a logged warning rather than crashing — Aave's strict
`rate >= -1` assertion in `update_state` becomes our last-line defence.
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


# Messari Compound V3 Ethereum subgraph. Verify current deployment ID at:
#   https://thegraph.com/explorer/subgraphs?search=compound-v3-ethereum
COMPOUND_V3_ETHEREUM_SUBGRAPH_ID = "AwoxEZbiWLvv6e3QdvdMZw4WDURdGbvPfHmZRc8Dpfz9"

# Known Comet markets on Ethereum mainnet (proxy addresses)
COMET_USDC_ETH = "0xc3d688B66703497DAA19211EEdff47f25384cdc3"
COMET_WETH_ETH = "0xA17581A9E3356d9A858b789D68B4d866e593aE94"
COMET_USDT_ETH = "0x3Afdc9BCA9213A35503b077a6072F3D0d5AB0840"


class CompoundV3RatesLoader(ArbitrumGraphLoader):
    """Hourly Comet market rate + utilization history via Messari subgraph.

    Returns:
        `LendingHistory` DataFrame with columns:
            * lending_rate          (per-period, matches AaveV3RatesLoader)
            * borrowing_rate        (per-period)
            * utilization           [0, 1]
            * total_supplied_usd
            * total_borrowed_usd

    Args:
        api_key:           TheGraph API key.
        market:            Comet proxy address (COMET_USDC_ETH for our project).
        start_time:        UTC datetime; floor.
        end_time:          UTC datetime; cap (defaults to now).
        resolution:        Hours per row in the rate normalisation. 1 = hourly.
        loader_type:       Cache format.
        subgraph_id:       Override the default deployment ID if it changes.
    """

    _BATCH_LIMIT = 1000

    def __init__(
        self,
        api_key: str,
        market: str = COMET_USDC_ETH,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        resolution: int = 1,
        loader_type: LoaderType = LoaderType.CSV,
        subgraph_id: str = COMPOUND_V3_ETHEREUM_SUBGRAPH_ID,
    ) -> None:
        super().__init__(
            api_key=api_key,
            subgraph_id=subgraph_id,
            loader_type=loader_type,
        )
        self.market: str = validate_evm_address(market, field="market")
        self.start_time: Optional[datetime] = to_utc(start_time)
        self.end_time: Optional[datetime] = to_utc(end_time)
        self._resolution: int = int(resolution)

    def _cache_key(self) -> str:
        s = to_seconds(self.start_time) if self.start_time is not None else "open"
        e = to_seconds(self.end_time) if self.end_time is not None else "now"
        return f"compound-v3-eth-{self.market}-{s}-{e}-{self._resolution}"

    # ---- extract -----------------------------------------------------------

    def extract(self) -> None:
        cursor = to_seconds(self.end_time) if self.end_time is not None else int(utcnow().timestamp())
        floor = to_seconds(self.start_time) if self.start_time is not None else None

        rows: List[dict] = []
        while True:
            query = """
            {
              marketHourlySnapshots(
                first: %d,
                orderBy: timestamp, orderDirection: desc,
                where: {
                  market: "%s",
                  timestamp_lt: %d
                }
              ) {
                timestamp
                rates { side rate }
                totalDepositBalanceUSD
                totalBorrowBalanceUSD
                inputTokenBalance
                variableBorrowedTokenBalance
              }
            }
            """ % (self._BATCH_LIMIT, self.market, cursor)
            data = self._make_request(query)
            batch = data.get("marketHourlySnapshots") or []
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
                    "utilization", "total_supplied_usd", "total_borrowed_usd",
                ]
            )
            return

        # Flatten the rates array — find LENDER and VARIABLE_BORROW per row
        parsed = []
        for r in rows:
            ts = int(r["timestamp"])
            rates_list = r.get("rates") or []
            lend = next((float(x["rate"]) for x in rates_list if x.get("side") == "LENDER"), float("nan"))
            borrow = next((float(x["rate"]) for x in rates_list if x.get("side") == "VARIABLE_BORROW"), float("nan"))
            parsed.append({
                "timestamp": ts,
                "lender_apr_pct": lend,
                "borrow_apr_pct": borrow,
                "total_supplied_usd": float(r.get("totalDepositBalanceUSD") or 0.0),
                "total_borrowed_usd": float(r.get("totalBorrowBalanceUSD") or 0.0),
            })
        df = pd.DataFrame(parsed)
        df["date"] = pd.to_datetime(df["timestamp"].astype(int), unit="s", utc=True)

        # Percent -> decimal APR, then -> per-period (matches Aave convention)
        scale = (365 * 24) / max(self._resolution, 1)
        df["lending_rate"] = (df["lender_apr_pct"] / 100.0) / scale
        df["borrowing_rate"] = (df["borrow_apr_pct"] / 100.0) / scale

        # Utilization from USD totals (Messari pre-converts to USD via Chainlink)
        with pd.option_context("mode.use_inf_as_na", True):
            util = df["total_borrowed_usd"] / df["total_supplied_usd"].replace(0, pd.NA)
        df["utilization"] = util.clip(0.0, 1.05).fillna(0.0)

        self._data = df[
            ["date", "lending_rate", "borrowing_rate",
             "utilization", "total_supplied_usd", "total_borrowed_usd"]
        ]

    # ---- transform ---------------------------------------------------------

    def transform(self) -> None:
        cols = [
            "date", "lending_rate", "borrowing_rate",
            "utilization", "total_supplied_usd", "total_borrowed_usd",
        ]
        if self._data is None or self._data.empty:
            self._data = pd.DataFrame(columns=cols)
            return

        df = self._data.sort_values("date").drop_duplicates("date").reset_index(drop=True)

        if self.start_time is not None:
            df = df[df["date"] >= self.start_time]
        if self.end_time is not None:
            df = df[df["date"] <= self.end_time]

        # Sign / negative guard. We clip rather than throw because Compound V3
        # has had isolated near-zero / fractionally-negative snapshots due to
        # USDC-USD price oscillations on Messari's Chainlink feed.
        bad = (df["borrowing_rate"] < 0) | (df["lending_rate"] < 0)
        if bad.any():
            df.loc[bad, ["borrowing_rate", "lending_rate"]] = df.loc[
                bad, ["borrowing_rate", "lending_rate"]
            ].clip(lower=0.0)

        if (df["borrowing_rate"] < df["lending_rate"]).any():
            n = (df["borrowing_rate"] < df["lending_rate"]).sum()
            raise GraphLoaderException(
                f"Compound V3 subgraph returned {n} rows where borrowing_rate < lending_rate "
                f"(protocol-impossible by Comet rate model). Schema change or parser bug?"
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

        hist = LendingHistory(
            lending_rates=self._data["lending_rate"].astype(float).fillna(0.0).values,
            borrowing_rates=self._data["borrowing_rate"].astype(float).fillna(0.0).values,
            time=pd.to_datetime(self._data["date"], utc=True).values,
        )
        hist["utilization"] = self._data["utilization"].astype(float).fillna(0.0).values
        hist["total_supplied_usd"] = self._data["total_supplied_usd"].astype(float).fillna(0.0).values
        hist["total_borrowed_usd"] = self._data["total_borrowed_usd"].astype(float).fillna(0.0).values
        return hist


__all__ = ["CompoundV3RatesLoader", "COMPOUND_V3_ETHEREUM_SUBGRAPH_ID", "COMET_USDC_ETH"]
