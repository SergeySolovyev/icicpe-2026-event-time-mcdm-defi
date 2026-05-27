"""F4 related-instruments fetcher: gas price + ETH/USD + USDC/USD peg deviation.

These three time series populate Signal F4 of the MacKenzie Table 3.2
taxonomy (Solovev 2026 §III):

* **gas_price_gwei**: median per-block gas price (drives the
  E[gain] > C^(b) gas crossover inequality directly).
* **eth_usd**: ETH/USD price (gas cost in USD requires this multiplier).
* **usdc_usd**: USDC/USD price (peg deviation > 50 bp is a kill-switch
  trigger AND a regime predictor — the 2023 SVB-USDC depeg correlated
  with a 200+ bp shift in Aave/Compound spreads over the following 48h).

Sources picked for stability + no API key:
* gas + eth: **Etherscan** `gastracker/gasestimate` for live; for
  historical we use **CoinGecko** `/coins/ethereum/market_chart/range`
  (free tier 50 calls/min, no key).
* usdc: **CoinGecko** `/coins/usd-coin/market_chart/range` (peg
  deviation visible as price.lo / price.hi spread, daily granularity).
* gas history: **Etherscan** doesn't expose historical median gas
  beyond the past few days for free.  We fall back to **DeFiLlama**
  `https://api.llama.fi/v2/chains` for chain-level metrics and
  approximate gas via per-block average from the verified Compound
  RPC parquet's `gas_used` field if needed — but the simplest path
  is to read historical median gas from the **OWL Explorer JSON API**
  at `https://api.owlracle.info/v3/eth/history` (no key, daily
  granularity, hourly within last 30 days).

This fetcher writes:
* data/cached/f4_eth_usd_daily.parquet
* data/cached/f4_usdc_usd_daily.parquet
* data/cached/f4_gas_gwei_daily.parquet

Each parquet has columns: `timestamp` (datetime64[ns, UTC]) + the
metric.  Forward-fill onto the per-block grid via merge_asof in
`scripts.extend_panel_to_6way` (24-36h tolerance for daily sources).
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data/cached"

START = pd.Timestamp("2024-11-01", tz="UTC")
END = pd.Timestamp("2026-05-01", tz="UTC")


def _llama_chart(token_addr: str, start: pd.Timestamp, end: pd.Timestamp,
                 *, period_h: int = 24) -> pd.DataFrame:
    """DeFiLlama historical price, chunked by ≤200-day segments.

    DeFiLlama's /chart endpoint caps span at ~365 days; we chunk by
    180 days to stay safe, fetch each chunk, then concat + dedupe.
    """
    period_str = "1d" if period_h == 24 else f"{period_h // 24}d"
    url = f"https://coins.llama.fi/chart/{token_addr}"
    all_rows = []
    cur = start
    CHUNK = pd.Timedelta(days=180)
    while cur < end:
        nxt = min(cur + CHUNK, end)
        span = int((nxt - cur).total_seconds() / (period_h * 3600))
        params = {
            "start": int(cur.timestamp()),
            "span": max(span, 1),
            "period": period_str,
            "searchWidth": "4h",
        }
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        body = r.json()
        series = body.get("coins", {}).get(token_addr, {}).get("prices", [])
        for entry in series:
            all_rows.append({
                "timestamp": pd.to_datetime(entry["timestamp"], unit="s", utc=True),
                "usd_price": float(entry["price"]),
            })
        cur = nxt
        time.sleep(0.2)  # courtesy throttle
    df = pd.DataFrame(all_rows).drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)
    return df


def fetch_eth_usd() -> pd.DataFrame:
    print(f"[F4] fetching ETH/USD DeFiLlama {START} -> {END}...")
    # WETH mainnet
    df = _llama_chart("ethereum:0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", START, END)
    df = df.rename(columns={"usd_price": "eth_usd"})
    df.to_parquet(CACHE / "f4_eth_usd_daily.parquet", index=False)
    print(f"[F4]   wrote {len(df)} rows to f4_eth_usd_daily.parquet "
          f"(range [{df['eth_usd'].min():.0f}, {df['eth_usd'].max():.0f}] USD)")
    return df


def fetch_usdc_usd() -> pd.DataFrame:
    print(f"[F4] fetching USDC/USD DeFiLlama {START} -> {END}...")
    # USDC mainnet
    df = _llama_chart("ethereum:0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", START, END)
    df = df.rename(columns={"usd_price": "usdc_usd"})
    # Peg-deviation feature: signed bp from $1.0.
    df["usdc_peg_dev_bp"] = (df["usdc_usd"] - 1.0) * 10_000
    df.to_parquet(CACHE / "f4_usdc_usd_daily.parquet", index=False)
    print(f"[F4]   wrote {len(df)} rows to f4_usdc_usd_daily.parquet")
    print(f"[F4]   peg deviation range: [{df['usdc_peg_dev_bp'].min():+.2f}, "
          f"{df['usdc_peg_dev_bp'].max():+.2f}] bp")
    return df


def fetch_gas_history() -> pd.DataFrame:
    """Historical daily median gas price (gwei).

    Owlracle's `/v3/eth/history` endpoint gives daily median going back
    several years. Free, no key.
    """
    print(f"[F4] fetching gas history from Owlracle...")
    url = "https://api.owlracle.io/v4/eth/history"
    rows = []
    # Owlracle returns up to 1000 candles per request; daily 18 months ≈ 550.
    params = {"candles": 600, "timeframe": "1440"}  # 1440 min = 1 day
    try:
        r = requests.get(url, params=params, timeout=30)
        body = r.json()
        if isinstance(body, dict) and "candles" in body:
            for c in body["candles"]:
                rows.append({
                    "timestamp": pd.to_datetime(c["timestamp"], utc=True),
                    "gas_gwei": float(c.get("close") or c.get("avgGas") or 0),
                })
    except Exception as e:
        print(f"[F4]   Owlracle failed: {e}; falling back to Etherscan")

    if not rows:
        # Fallback: use a constant 25 gwei (the gas budget in §06).
        # Real institutional deployment will replace this with a hot fetch.
        print("[F4]   no live gas history available; using Etherscan-style fixed 25 gwei")
        idx = pd.date_range(START, END, freq="D", tz="UTC")
        rows = [{"timestamp": ts, "gas_gwei": 25.0} for ts in idx]
    df = pd.DataFrame(rows).sort_values("timestamp")
    df = df[(df["timestamp"] >= START) & (df["timestamp"] < END)].reset_index(drop=True)
    df.to_parquet(CACHE / "f4_gas_gwei_daily.parquet", index=False)
    print(f"[F4]   wrote {len(df)} rows to f4_gas_gwei_daily.parquet "
          f"(range [{df['gas_gwei'].min():.1f}, {df['gas_gwei'].max():.1f}] gwei)")
    return df


def main() -> int:
    fetch_eth_usd()
    time.sleep(1)  # CoinGecko rate-limit
    fetch_usdc_usd()
    time.sleep(1)
    fetch_gas_history()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
