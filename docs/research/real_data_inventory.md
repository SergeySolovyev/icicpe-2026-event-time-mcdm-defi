# Real Data Inventory — what is REAL vs PLACEHOLDER

**Date:** 2026-06-03. Every row introspected directly from
`data/cached/per_block_panel.parquet` (3,931,200 blocks, Nov 2024–Apr 2026)
and the source files under `data/cached/`. Verdict rule: `nunique<=1` →
PLACEHOLDER; `nunique<100` → REAL-coarse; else REAL.

## Bottom line
The **decision variable — `lending_apr` — is REAL for all six protocols.**
T1/T2/T3 decide on `lending_apr` spreads + gas, so the allocator runs on
real rate data end-to-end. Every placeholder below feeds only secondary
analyses (MCDM-B4 baseline [excluded from headline], capacity, F3
utilization-spread sub-features) or the gas framing — **none invalidates
the binding T1-vs-holds result.**

## Protocol data (6 × 4 fields)

| Protocol | lending_apr | borrow_apr | utilization | tvl_usd | rate cadence | source |
|---|---|---|---|---|---|---|
| **Aave V3** | ✅ REAL (535,740) | ✅ REAL | ✅ REAL | ✅ REAL | ~48 s per-block | Aave subgraph (reserveParamsHistoryItems) |
| **Morpho Blue** | ✅ REAL (13,104) | ✅ REAL | ✅ REAL | ✅ REAL | ~1 h on-interaction | api.morpho.org/graphql |
| **Euler V2** | ✅ REAL (32,395) | ✅ REAL | ✅ REAL | ✅ REAL | ~6 min events | Euler Goldsky subgraph |
| **Compound V3** | ✅ REAL (12,256, 98.5%) | ✅ REAL | ✅ REAL | ⛔ PLACEHOLDER (const 0) | hourly RPC | Comet view-calls |
| **Spark** | ✅ REAL (6,155, 99.6%) | ⛔ PLACEHOLDER (missing) | ✅ REAL | ✅ REAL | hourly | Sky Messari subgraph |
| **Fluid** | ✅ REAL (352, daily, 100%) | ⛔ PLACEHOLDER (missing) | ⛔ PLACEHOLDER (const 0.85) | ✅ REAL (547) | daily | DeFiLlama Yield Pools |

## Signal / aux data

| Column | verdict | detail | source |
|---|---|---|---|
| `eth_usd` | ✅ REAL (546) | $1,470–$4,831 | CoinGecko |
| `usdc_peg` / `usdc_peg_dev_bp` | ✅ REAL (397) | 0.9973–1.0083 | CoinGecko |
| `f1_dsr_apr_frac` / `f1_dsr_apy_pct` | 🟡 REAL-coarse (17) | Maker DSR step rate 1.25–11.5% | `events_dsr.parquet` (546 events) |
| `gas_price_gwei` | ⛔ **PLACEHOLDER (const 25)** | Owlracle fetch failed → hardcoded 25 | `fetch_f4_signals.py:141` |
| `usdt_peg` | ⛔ PLACEHOLDER (all-NaN) | never fetched | — |

## What each placeholder affects (impact triage)

| Placeholder | Affects | Touches binding result? |
|---|---|---|
| `gas_price_gwei` const 25 | gas-cost gate magnitude; "gas-aware" framing | **symmetric across all policies** — gas-sensitivity sweep bounds it; binding *ranking* unaffected |
| `compound_v3_tvl_usd` = 0 | MCDM-B4 (excluded), capacity sweep | no |
| `spark_borrow_apr` missing | nothing the allocator uses (supply-side only) | no |
| `fluid_borrow_apr` / `fluid_utilization` | F3 util-spread sub-features, kink decomp | no (rate-based decision intact) |
| `usdt_peg` missing | one F4 sub-signal (F4 contributes ~0 anyway) | no |
| `f1_dsr` 17-level | F1 lead feature (and the now-retracted T3 claim) | no — T1/T2 don't use F1 |

## What needs SEPARATE COMPUTE (Kaggle / HF / Colab) + which key

All six gaps are RPC/subgraph fetches that need a key the local box lacks.
Ordered by leverage for the *paper + product*:

| # | Gap to close | Compute | Key required | Effort | Why it matters |
|---|---|---|---|---|---|
| **G1** | **Real historical gas** (replace const 25) | Colab/Kaggle notebook; `eth_feeHistory` over the block range, or Etherscan/Dune daily gas | **Etherscan API key** *or* paid archive RPC (`eth_feeHistory` works on many free RPCs — may need no key) | ~1–2 h | **#1** — makes "gas-aware" real; lets us compute the true **net-of-gas** edge the YC critic flagged as the load-bearing product number |
| **G2** | **Compound V3 TVL** (replace const 0) | Kaggle; `totalSupply()`×price at sampled blocks | **archive `ETHEREUM_RPC_URL`** | ~1 h | capacity analysis + MCDM fidelity |
| **G3** | **Spark borrow rate** | Kaggle; add `variableBorrowRate` to the Spark subgraph query | **THE_GRAPH_API_KEY** | ~30 min | completeness; borrow side |
| **G4** | **Fluid borrow + utilization** | Kaggle/Colab; FluidLiquidityResolver `getOverallTokenData` | **archive `ETHEREUM_RPC_URL`** | ~1 h | F3 util-spread fidelity for Fluid |
| **G5** | **Per-block Fluid + Spark + Compound** (upgrade hourly/daily → per-block) | Kaggle; archive RPC sampling at finer stride | **archive `ETHEREUM_RPC_URL`** | ~3–6 h | removes the cadence caveat entirely (true 6×per-block) |
| **G6** | **USDT peg** | trivial; CoinGecko (free, no key) | none | ~10 min | cosmetic F4 completeness |

### Recommended external-compute plan
- **G1 first** (real gas): it is the single highest-leverage closure — it
  converts the gross edge into a defensible **net** edge and removes the
  biggest honesty asterisk. Try `eth_feeHistory` on a free RPC first (may
  need no key at all); fall back to Etherscan daily gas with a free key.
- **G2 + G4** together on one Kaggle notebook (both archive-RPC).
- **G3** on the existing Spark subgraph fetcher (one-line query addition).
- **G6** is free and trivial — fold into the next local run.
- **G5** is the "true per-block 6×" upgrade — biggest compute, lowest
  marginal scientific value (cadence is already disclosed); do last / only
  if a reviewer demands it.

**None of G1–G6 changes the binding T1-vs-holds finding** (real
`lending_apr`, leakage-free). They (a) make "gas-aware" net-honest [G1],
(b) restore secondary-analysis fidelity [G2–G4], (c) optionally remove the
cadence caveat [G5].
