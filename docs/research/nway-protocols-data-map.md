# N-Way Protocols — Data Map for Hourly USDC Lending Rates on Ethereum L1

**Scope.** Extending the existing 2-protocol allocator (Aave V3 + Compound V3,
USDC on Ethereum, hourly, Nov 2024 → Apr 2026, ~13,096 bars) to four additional
protocols: **SparkLend, Morpho Blue, Fluid, Euler V2**.

**Existing conventions to match** (see `data/fetch_aave_subgraph.py` and
`data/fetch_compound_via_rpc.py`):

- Output a parquet under `data/cached/<protocol>_usdc_eth_2024-11_to_2026-04.parquet`
- Hourly UTC index (`label="right", closed="right"`)
- Columns: `lending_rate`, `borrowing_rate`, `utilization`,
  `total_supplied_usd`, `total_borrowed_usd` (mirror Compound RPC fetcher), and
  optionally `total_liquidity`, `total_variable_debt` (mirror Aave subgraph
  fetcher).
- Per-period rate convention: `annualized_apr / ((365 * 24) / resolution)`,
  arithmetic, NOT continuously compounded (locked in by Aave loader).
- `borrowing_rate >= lending_rate` invariant enforced by
  `data/clean.py::assert_sign_convention`.
- API keys read via `python-dotenv` from `.env`:
  `THE_GRAPH_API_KEY`, `ETHEREUM_RPC_URL`.

---

## 1. SparkLend (Maker / Sky-affiliated, Aave V3 fork)

### A) Endpoint

- **Official decentralized subgraph (TheGraph hosted)**:
  `https://gateway.thegraph.com/api/<THE_GRAPH_API_KEY>/subgraphs/id/GbKdmBe4ycCYCQLQSjqGg6UHYoYfbyJyq5WrG35pv1si`
  - Name: *Spark Lend Ethereum* v3.1.0_2.4.0
  - Maintained by the Spark / Phoenix Labs team (Aave V3 schema fork).
  - Auth: yes — uses the same `THE_GRAPH_API_KEY` already in repo env.
- **Messari alternative** (hosted-service style, not on decentralized network):
  `https://subgraphs.messari.io/subgraph?endpoint=messari/spark-lend-ethereum`
  — Messari standardised lending schema (Market, MarketHourlySnapshot,
  MarketDailySnapshot). NOT in the canonical `messari/subgraphs`
  `deployment/deployment.json` (so no decentralized-network query-id).
  Useful as a hourly-snapshot fallback only — uptime weaker than (1).
- **RPC fallback**: SparkLend `Pool` proxy at
  `0xC13e21B648A5Ee794902342038FF3aDAB66BE987` (immutable Aave V3 pool).
  Standard Aave V3 ABI: `getReserveData(address asset)` → struct with
  `currentLiquidityRate` (RAY, per-second × RAY equivalent, see §C/§D).

### B) USDC market identification

- USDC is a top-3 reserve on the main SparkLend pool (onboarded April 2024 per
  Sky governance vote).
- **Reserve ID convention** (Aave-style): the `Reserve` entity ID in the
  subgraph is `<poolAddressLower>-<assetAddressLower>` or just
  `<assetAddressLower>` depending on schema version. For the Spark fork it
  follows Aave's reserveId convention.
- **Underlying asset**: `USDC = 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48`
- **aToken (`spUSDC`)**: discoverable via `pool.getReserveData(USDC).aTokenAddress`
  (don't hardcode — verify on-chain on first run).

### C) Interest rate model

- **Same shape as Aave V3**: piecewise-linear two-slope with kink U*.
- Parameters per reserve are stored in
  `DefaultReserveInterestRateStrategy` (one per asset).
- Typical Spark USDC values (subject to Sky governance updates — fetch live):
  optimalUsageRatio ≈ 0.92 RAY, baseVariableBorrowRate = 0, variableRateSlope1
  ≈ 0.045 RAY, variableRateSlope2 ≈ 0.50 RAY. Liquidity rate =
  borrow_rate × U × (1 − reserveFactor).
- This means a static `f_kink(u)` IS extractable (same as Aave V3 USDC
  in `data/fetch_kink_params.py`); fetcher should call the strategy contract
  once per major parameter change (rare; usually <5 changes over 18 months).

### D) Schema quirks

- `Reserve.liquidityRate` and `Reserve.variableBorrowRate` are **annualized × RAY
  (1e27)**, identical to Aave V3 (CLAUDE.md §3a applies verbatim — first fetch
  could return 47M% APR if you forget the divide-by-1e27-then-annualize step).
- Subgraph emits **event stream** (Deposit, Borrow, RepayBorrow, ReserveDataUpdated)
  not pre-aggregated hourly snapshots. The 18-month event count is ~5–10× lower
  than Aave (smaller protocol) so ~50–150k raw rows.
- Entity to query: `reserveParamsHistoryItems(where: {reserve: <reserveId>,
  timestamp_gte: ..., timestamp_lte: ...}, first: 1000, skip: <n>)` — same
  pagination cap as Aave V3 (1000 rows/query, max skip 5000 — use
  `timestamp_gt` cursor pagination beyond that).
- Messari alternative emits true `marketHourlySnapshots` (pre-aggregated),
  identical schema to messari/aave-v3-ethereum — easier but less reliable.

### E) Data availability

- SparkLend launched **2 May 2023** on Ethereum (Phoenix Labs).
- USDC reserve activated April 2024 → full coverage from Nov 1, 2024 ✓
- No known re-index gaps. Decentralized-network subgraph has been live since
  early 2024.

---

## 2. Morpho Blue (permissionless lending)

### A) Endpoint

- **Morpho-org subgraph is DEPRECATED** (last updated March 2025; explicit
  notice in `docs.morpho.org`). Do not build against it.
- **Official replacement: Morpho REST/GraphQL API at**
  `https://api.morpho.org/graphql` (formerly known as "Blue API")
  - No auth required for read queries (anonymous tier; signed JWT only needed
    for vault-curator mutations).
  - Native rate-limit: ~600 req/min/IP undocumented but observed; well within
    budget for a 13k-bar one-shot fetch.
- Key query: `market(uniqueKey: $id) { historicalState(options:
  { startTimestamp, endTimestamp, interval: HOUR }) { supplyApy { x y }
  borrowApy { x y } utilization { x y } supplyAssetsUsd { x y }
  borrowAssetsUsd { x y } } }`
- **RPC fallback**: Morpho Blue singleton at
  `0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb`. `market(id)` view returns
  `(totalSupplyAssets, totalSupplyShares, totalBorrowAssets, totalBorrowShares,
  lastUpdate, fee)`. Compute utilization = totalBorrow / totalSupply
  off-chain. For rate: query the IRM at `irm.borrowRateView(marketParams,
  market)` — `marketParams` is the tuple (loanToken, collateralToken, oracle,
  irm, lltv).

### B) USDC market identification

Morpho is permissionless — there are 30+ active USDC-loan markets. Pick the
**top-1 by 18-month median TVL**, optionally include a backup. Ranked by
typical TVL through 2025–2026 (USDC-loan, Ethereum L1):

1. **wstETH/USDC**, market id
   `0xb323495f7e4148be5643a4ea4a8221eef163e4bccfdedc2a6f4696baacbc86cc`
   — LLTV 86%, AdaptiveCurveIRM. Largest USDC-loan market by integrated TVL
   over the window (~$300–800M typical).
2. **WBTC/USDC**, market id
   `0x3a85e619751152991742810df6ec69ce473daef99e28a64ab2340d7b7ccfee49`
   (verify by querying `MarketCreated` events on the singleton — wbtc/usdc
   with 86% LLTV).
3. **cbBTC/USDC**, market id
   `0x64d65c9a2d91c36d56fbc42d69e979335320169b3df63bf92789e2c8883fcc64`
   — onboarded mid-2025, grew quickly post-Coinbase routing.

**Recommendation**: fetch all three and emit one parquet per market
(`morpho_blue_usdc_wsteth_eth_2024-11_to_2026-04.parquet` etc.), then a
TVL-weighted composite for the allocator's USDC-supply view.

### C) Interest rate model — the AdaptiveCurveIRM

Contract: `0x870aC11D48B15DB9a138Cf899d20F13F79Ba00BC` (Ethereum mainnet).
Constants (hardcoded, identical across markets):

- `CURVE_STEEPNESS = 4`
- `TARGET_UTILIZATION = 0.9` (90%)
- `INITIAL_RATE_AT_TARGET ≈ 4% APR` (per-second scaled)
- `MIN_RATE_AT_TARGET ≈ 0.1% APR`, `MAX_RATE_AT_TARGET ≈ 200% APR`
- `ADJUSTMENT_SPEED = 50/year` (e-folding rate of the time-varying anchor)

Formula:
```
borrowRate(t) = rateAtTarget(t)  ×  curve( u(t) )
curve(u)      = if u <= U*   :  ((1/4 - 1)/U*) · u + 1              (slope down to (0, 1/4))
                else          :  ((4 - 1)/(1 - U*)) · (u - U*) + 1   (slope up to (1, 4))
d rateAtTarget(t)/dt  =  rateAtTarget(t) · ADJUSTMENT_SPEED · (u(t) - U*) / (1 - U*)   [clamped]
```

**Critical implication for kink-feature engineering**:
`rateAtTarget` is a **time-varying state variable** that drifts with the
integral of (u − U*). Therefore there is **NO static kink curve** to subtract
out — the kink/rate-at-target itself is what we'd want to model. Two options:

1. **Skip kink-subtraction for Morpho** — feed the empirical rate stream into
   the forecaster without the `f_kink(u_t)` residual decomposition that
   Aave/Compound/Spark use. The forecaster has to learn the IRM dynamics
   itself.
2. **Add `rateAtTarget` as a separate feature column** (query
   `irm.rateAtTarget(marketId)` per hour via RPC) and subtract
   `rateAtTarget × curve(u_t)` — this gives a clean residual but doubles the
   per-bar work.

Recommend option 1 for the n-way extension; Morpho residuals stay in the
"empirical noise" channel.

### D) Schema quirks

- **API rates are decimal APY/APR**, NOT RAY-scaled — `supplyApy.y` is e.g.
  `0.0512` for 5.12%. Multiply, don't divide.
- API time series is **emitted as snapshots at the requested interval**
  (not event-streamed). `interval: HOUR` gives one row per hour even if no
  on-chain event happened (synthetic accrual). Already on our target grid.
- USD-denominated columns use Morpho's internal price oracle, which may
  diverge from CoinGecko by ~0.1% — fine for TVL ranking, do not use as ground
  truth FX.
- Pagination: each historical query returns up to ~5000 points; with
  `interval: HOUR` × 18 months = 13096 points, **need to split into 2 calls**
  (e.g. Nov 2024 → Aug 2025 and Aug 2025 → Apr 2026).

### E) Data availability

- Morpho Blue launched **31 Jan 2024** (testnet earlier, but mainnet 31 Jan).
  Full coverage Nov 1, 2024 → Apr 30, 2026 ✓
- Largest USDC markets (wstETH/USDC, WBTC/USDC) were live within weeks of
  launch — no warm-up gaps in the window.
- API has been stable through 2025; no known re-index incidents.

---

## 3. Fluid (Instadapp's lending protocol)

### A) Endpoint

- **No production TheGraph / Goldsky subgraph as of May 2026**. A community
  bounty for an Instadapp/Fluid subgraph has been open on
  `gov.fluid.io` since 2023 and remains in-progress — there is no decentralized
  endpoint we can rely on.
- **Primary path: RPC view-functions via the periphery Resolver contracts**.
  This is the same pattern as `fetch_compound_via_rpc.py` but with different
  contracts.

Resolver contracts (Ethereum mainnet, verified via Etherscan; addresses may be
upgraded — re-verify on first run by following the latest `FluidLiquidityProxy`
admin txns):

- `FluidLiquidityResolver`: returns `getUserSupplyData`, `getOverallTokenData`
  (rates, utilization, total supply/borrow) for each ERC-20 in the Liquidity
  Layer. Typical address on mainnet: `0xD7588F6c99605Ab274C211a0AFeC60947668A8Cb`
  (verify; periphery contracts are upgraded periodically by Instadapp DAO).
- `FluidLendingResolver`: enumerates `fToken` markets (e.g. fUSDC at
  `0x9d1089802eE608BA84C5c98211afE5f37F96B36C`), returns supply rate, total
  assets, exchange rate per fToken. Address (subject to verification):
  `0xC215485C572365AE87f908ad35233EC2572A3BEC`.
- `FluidVaultResolver`: returns per-vault borrow rate, utilization, totalSupply,
  totalBorrow for vaults like wstETH-USDC, WBTC-USDC. Address (verify):
  `0x77648D39be25a1422467060e11E5b979463bEA3d`.

**Action item before fetching**: confirm current resolver addresses by checking
the latest entry in `https://github.com/Instadapp/fluid-contracts-public/blob/main/contracts/config/mainnet.json`
or the Etherscan "Read Contract" page on the `FluidLiquidityProxy` admin.

### B) USDC market identification

- **Supply side (lending protocol)**: fUSDC at
  `0x9d1089802eE608BA84C5c98211afE5f37F96B36C` — ERC-4626 vault, USDC pure
  supply. This is what the allocator competes against for the supply-side rate.
- **Borrow side (vault protocol)**: USDC is the *debt token* in many vaults.
  For an apples-to-apples Aave-comparable borrow rate, the most-liquid USDC
  debt vaults are wstETH-USDC and WBTC-USDC. Borrow rate on USDC in those
  vaults is set by the Liquidity Layer's IRM for USDC, NOT a per-vault model
  — so all USDC borrow rates across Fluid vaults are equal at any block (this
  is Fluid's signature "shared liquidity" property).
- Recommend: report a single Fluid USDC supply rate (from fUSDC /
  LiquidityResolver) and a single borrow rate (from LiquidityResolver
  USDC entry), with utilization being the **Liquidity Layer's total USDC
  utilization** (debt across all vaults / supply across fUSDC + smart-collateral
  positions).

### C) Interest rate model

- Fluid uses a **kink-based two-slope IRM**, parameters per-token stored in
  the Liquidity Layer.
- For USDC (typical values, governance-controlled; fetch live):
  - kink utilization `U* ≈ 0.85`
  - rate at U* (`rateAtKink`) ≈ 5–6% APR
  - rate at 100% utilization ≈ 50–100% APR (steep upper slope)
  - rate at 0% = 0 (no base rate)
- Static `f_kink(u)` IS extractable (Aave-like). One IRM-update event over
  18 months at most — query `LiquidityLayer.rateData(USDC)` once and cache.

### D) Schema quirks

- Rates from resolvers are returned **per-second × 1e12 (per Fluid's "RATE_PRECISION")
  for borrow rate**, and as **bps (×1e2) for some helper getters**. Read the
  contract source comment for the specific getter being called before
  interpreting — there is NO uniform RAY convention.
- Utilization returned as **basis points (1e4 = 100%)** by most resolvers —
  divide by 1e4 to get decimal.
- Total supply / borrow returned in token decimals (USDC: 6) — divide by 1e6.
- No `marketHourlySnapshot` entity exists (no subgraph). The fetcher must:
  1. Approximate the block-at-hour using mainnet block-time anchor (same as
     `fetch_compound_via_rpc.py`).
  2. Batched `eth_call` to `FluidLiquidityResolver.getOverallTokenData(USDC)`
     at each historical block.
- Pagination: not applicable (RPC fetch). Batch size cap: 100 calls/req on
  publicnode/Ankr free tiers (already documented in CLAUDE.md §3e).

### E) Data availability

- Fluid liquidity-layer + lending protocol launched **Q1 2024** (Instadapp);
  the rebrand to "Fluid" was December 2024.
- USDC supply market live throughout the window — full coverage ✓
- Vault protocol (smart-collateral wstETH-USDC etc.) launched **March 2024**
  — covers Nov 1, 2024 onward without gaps.
- **Caveat**: historical RPC access requires archive node (same as Compound
  fetcher). Free public archive RPCs (publicnode, Ankr free) work but cap at
  100 calls/req; budget ~3–5× the Compound fetcher wall-clock because Fluid
  needs more data points per bar (resolver returns rich struct → 1 call/hour
  is enough, but the struct decoding is more involved).

---

## 4. Euler V2 (modular vault kit)

### A) Endpoint

- **Official subgraph (Goldsky-hosted, not on decentralized TheGraph network)**:
  `https://api.goldsky.com/api/public/project_cm4iagnemt1wp01xn4gh1agft/subgraphs/euler-v2-mainnet/latest/gn`
  - No auth required (public Goldsky endpoint).
  - Source code at `github.com/euler-xyz/euler-subgraph` — open source.
- **Decentralized-network alternative**: legacy Euler v1 subgraph
  (`8cLf29KxAedWLVaEqjV8qKomdwwXQxjptBZFrqWNH5u2`) exists but is **v1-only**;
  does NOT cover Euler V2 EVK vaults. Do not use.
- **RPC fallback**: every Euler V2 vault implements ERC-4626 + the Euler Vault
  Kit (EVK) interface. Key view functions: `interestRate()` returns
  per-second rate × 1e27 (RAY-like). `cash()`, `totalBorrows()` for
  utilization. `irm()` returns the IRM contract address.

### B) USDC market identification

- **Euler Prime USDC vault** (Gauntlet-curated, conservative cluster):
  **`0x797DD80692c3b2dAdabCe8e30C07fDE5307D48a9`** — confirmed via
  `app.euler.finance/vault/...?network=ethereum`. This is the highest-liquidity
  USDC vault on Euler V2 mainnet and the right comparator for Aave/Spark.
- **Euler Yield USDC vault** (higher-risk yield cluster):
  `0xe0a80d35bB6618CBA260120b279d357978c42BCE` — secondary; smaller TVL.
- Recommend primary = Prime USDC (`0x797D...48a9`). Optionally include Yield
  USDC as a sensitivity check.

### C) Interest rate model

- Euler V2 vaults have **customizable IRMs** (`IRMLinearKink`,
  `IRMAdaptiveCurve`, custom). Prime USDC uses **`IRMLinearKink`** —
  the classic piecewise-linear Aave-style two-slope model.
- Parameters retrievable via `vault.interestRateModel()` → IRM contract →
  `baseRate, kink, slope1, slope2` getters.
- Typical Prime USDC values (Gauntlet-governance set; fetch live):
  - baseRate = 0
  - kink ≈ 0.9 (90% in WAD)
  - slope1 ≈ 0.04 / SecondsPerYear (i.e. ~4% APR at kink)
  - slope2 ≈ 1.0 / SecondsPerYear (steep above kink)
- Static `f_kink(u)` IS extractable — same shape as Aave V3 / Compound V3 /
  Spark / Fluid. Good news for cross-protocol feature consistency.

### D) Schema quirks

- Subgraph rate fields: `supplyApy` and `borrowApy` are reported as
  **decimal APY** (e.g. 0.05 = 5%), per the Goldsky subgraph schema. **Confirm
  on first fetch** — schema docs are sparse and the underlying contract returns
  per-second × 1e27, so the subgraph performs a conversion that we should
  spot-check against `vault.interestRate()`.
- `interestAccumulator` is RAY-scaled and increases monotonically; useful for
  computing realized supply yield over an interval without rate-sampling drift.
- Snapshot granularity: `vaultStatuses` entity has one row per
  `VaultStatus` event. Frequency is per-interaction (deposit/borrow/repay/
  withdraw) — for USDC Prime, expect ~5–30 events/day depending on traffic.
  ~5,000–25,000 raw rows over 18 months. Fetcher must resample to hourly
  (same `last()` aggregation pattern as Aave subgraph fetcher).
- Pagination: standard Goldsky / TheGraph limit, 1000 rows per query,
  `skip` capped at 5000 → use timestamp-cursor pagination for 18 months of
  events.

### E) Data availability

- **Euler V2 launched 22 August 2024** (vault kit + Prime cluster
  simultaneously). Prime USDC vault was live from day-1.
- Window starts Nov 1, 2024 → **~70 days post-launch** of Prime USDC. Should
  have meaningful TVL and event coverage from Nov 1 onward (Prime USDC crossed
  $100M TVL by mid-October 2024 per DeFiLlama).
- Risk: first 1–2 weeks of November 2024 may have lower transaction frequency
  → hourly resampling will ffill across long gaps. Acceptable as a feature for
  the forecaster (low-volatility regime). Document in clean.py loader as
  "data sparse in 2024-11-01 to 2024-11-15".
- Goldsky subgraph has been continuously deployed since Sep 2024; no known
  re-index gaps.

---

## 5. Fetcher Implementation Strategy

Ordered easiest → hardest (i.e. recommended sprint order so we ship usable
data in days, not weeks).

### Tier 1 — Subgraph clones of the Aave fetcher (1–2 days each)

1. **SparkLend** — *fastest win*. Aave V3 schema is literally the same
   (Spark forked the Aave V3 subgraph). Copy `fetch_aave_subgraph.py` →
   `fetch_spark_subgraph.py`, swap subgraph id `Cd2gEDVeqnjBn1hSeqFMitw8...` →
   `GbKdmBe4ycCYCQLQSjqGg6UHYoYfbyJyq5WrG35pv1si`, keep `USDC_ETH` reserve
   constant. Same RAY conversion, same event-stream → hourly resample.
   **ETA: <1 day**.

2. **Morpho Blue** — slightly more bespoke (REST/GraphQL API at
   `api.morpho.org`, decimal-APY native, no RAY conversion). Write
   `fetch_morpho_api.py` from scratch (no fractal-defi loader exists) but the
   logic is ~80 lines: build the GraphQL query, paginate by date, parse the
   `historicalState.supplyApy.y` array. **ETA: 1–2 days**. Decision: ship one
   parquet per market (wstETH/USDC, WBTC/USDC, cbBTC/USDC) and let the
   allocator compose a TVL-weighted view downstream.

### Tier 2 — RPC clones of the Compound fetcher (2–4 days each)

3. **Euler V2** — subgraph exists (Goldsky) and is cleaner than Morpho's, BUT
   the schema is sparsely documented and rate-scaling is ambiguous. **Two-step**:
   first write `fetch_euler_subgraph.py` using `vaultStatuses` events (~6h),
   then **cross-check** against an RPC probe on a sample block (1h).
   If subgraph rates diverge >0.5% from on-chain `interestRate()`, fall back
   to RPC. **ETA: 2 days** (allowing for subgraph audit).

4. **Fluid** — *hardest*. No subgraph; must replicate the
   `fetch_compound_via_rpc.py` pattern against `FluidLiquidityResolver` and
   `FluidLendingResolver`. Per-second-rate scaling is **not** RAY but Fluid's
   own RATE_PRECISION (1e12) — needs careful unit handling. Also: archive RPC
   batch-size caps (publicnode 100, Ankr 100) constrain throughput; for 13k
   bars × 1 call each = 130 batches × 30ms = ~1 minute net but practical
   wall-clock is ~5 min due to backoff. **ETA: 3–4 days** (incl. resolver
   address verification and unit testing).

### Tier 3 — Optional polish

- Add a `data/fetch_kink_params_nway.py` that collects current IRM parameters
  for Spark/Fluid/Euler V2 USDC (skip Morpho — no static kink). Mirrors
  `fetch_kink_params.py`.
- Add an integration test under `tests/test_nway_loaders.py` checking
  `borrowing_rate >= lending_rate` invariant and `0 <= utilization <= 1.05`
  on each protocol's last 100 hourly bars.
- Extend `data/clean.py` join+ffill pipeline to register the 4 new entities.

### Bottom line for the 4-week sprint

- **Days 1–2**: Spark + Morpho subgraph fetchers → 4 parquets shipped.
- **Days 3–4**: Euler V2 subgraph fetcher + RPC audit → 1 parquet.
- **Days 5–7**: Fluid RPC fetcher → 1 parquet.
- **Day 8**: integration tests, sign-convention checks, kink-param dump.

This puts us at 6 protocols (Aave V3 + Compound V3 + 4 new) with full hourly
coverage by end of week 1 of the n-way extension.

---

## 6. Open / unresolved items

1. **Spark `Reserve.id` exact format**: Aave V3 schema versions have used
   both `<pool>-<asset>` and `<asset>` formats. Resolve by running a
   `{ reserves { id symbol } }` probe query against the Spark subgraph on
   first run (1 minute) — analogous to how the Aave loader was originally
   verified.
2. **Fluid resolver addresses**: addresses listed above are the most-recently
   advertised in Fluid governance posts but periphery contracts are upgraded
   periodically. Verify against the latest `mainnet.json` in
   `Instadapp/fluid-contracts-public` before each fetch run; if upgraded
   mid-window, fetcher needs per-block resolver selection (rare but possible).
3. **Morpho cbBTC/USDC market id**: confirmed `0x64d65c9a...` from
   `app.morpho.org`, but verify by enumerating `MarketCreated` events on
   the singleton if a discrepancy emerges.
4. **Morpho IRM dynamics in the forecaster**: decision made — skip
   kink-subtraction for Morpho (see §2C). Document this in the forecaster
   ablation study as "Morpho-no-residual" vs "Aave/Compound/Spark/Fluid/Euler
   with residual".

---

## 7. Source list

- Spark subgraph: <https://thegraph.com/explorer/subgraphs/GbKdmBe4ycCYCQLQSjqGg6UHYoYfbyJyq5WrG35pv1si>
- Spark Messari alt: <https://subgraphs.messari.io/subgraph?endpoint=messari/spark-lend-ethereum>
- Spark deployments: <https://github.com/sparkdotfi/sparklend-deployments>
- Morpho API: <https://docs.morpho.org/build/borrow/tutorials/get-data>
- Morpho subgraph deprecation: <https://docs.morpho.org/tools/offchain/subgraphs/>
- Morpho AdaptiveCurveIRM: <https://docs.morpho.org/get-started/resources/contracts/irm/>, <https://morpho.org/blog/introducing-the-adaptivecurveirm-efficient-and-autonomous/>
- Morpho Blue IRM repo: <https://github.com/morpho-org/morpho-blue-irm>
- Morpho wstETH/USDC market: <https://app.morpho.org/ethereum/market/0xb323495f7e4148be5643a4ea4a8221eef163e4bccfdedc2a6f4696baacbc86cc/wsteth-usdc>
- Fluid docs: <https://docs.fluid.instadapp.io/>
- Fluid contracts repo: <https://github.com/Instadapp/fluid-contracts-public>
- Fluid subgraph bounty (still open): <https://gov.fluid.io/t/build-the-instadapp-subgraph-in-progress/206>
- Euler V2 subgraph (Goldsky): <https://docs.euler.finance/developers/data-querying/subgraphs/>
- Euler V2 IRMs: <https://docs.euler.finance/creator-tools/interest-rate-models/>
- Euler Prime USDC vault: <https://app.euler.finance/vault/0x797DD80692c3b2dAdabCe8e30C07fDE5307D48a9?network=ethereum>
