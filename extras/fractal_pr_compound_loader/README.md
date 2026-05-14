# Extra+1 PR: Compound V3 Lending Loader + Uniform `utilization` Field

**Target:** `Logarithm-Labs/fractal-defi`
**PR title:** *"Add Compound V3 lending loader + expose `utilization` on lending global states"*
**Status:** scoped, not yet submitted
**Deadline:** 12 June 2026 (PROJECT_2_PLAN.md timeline Week 4 Day 5)

## Scope

Single PR with two coherent components:

### Component A — Compound V3 loader

New file: `fractal/loaders/compound.py`

```python
class CompoundV3RatesLoader(BaseLoader[LendingHistory]):
    """Compound V3 (Comet) lending rate loader via Messari subgraph.

    Pulls hourly snapshots of `Market.rates` and totals from the cUSDCv3
    market (proxy 0xc3d688B66703497DAA19211EEdff47f25384cdc3) on Ethereum.
    Per-second rates in WAD (1e18) are annualized to continuously
    compounded APY matching the AaveV3RatesLoader output convention.
    """
    SUBGRAPH = "https://api.thegraph.com/subgraphs/name/messari/compound-v3-ethereum"
    USDC_MARKET = "0xc3d688B66703497DAA19211EEdff47f25384cdc3"
```

### Component B — `utilization` field on lending global states

Both `AaveGlobalState` and (new) `CompoundV3GlobalState` gain a
`utilization: float` field computed at load time from
`totalLiquidity` / `totalCurrentVariableDebt` (already in the
existing Aave subgraph response per DEEP_RESEARCH.md S V.A).

Justification (per ERRATA in repo root `PROJECT_2_PLAN.md`):
the current `AaveGlobalState` exposes rates and prices but NOT
utilization, blocking risk-aware allocator strategies like ours.
Exposing it uniformly across both lending entities completes the
abstraction.

## Tests

- `tests/loaders/test_compound_v3_loader.py` — real-API test pulling
  1-day window, checking schema + non-empty + sign convention.
- `tests/core/test_lending_global_state_utilization.py` — invariant
  `0 <= utilization <= 1.05` (5% slack for boundary noise) for both
  Aave and Compound on the cached fixture.

## Loader cache convention

Per ARCHITECTURE.md: `<DATA_PATH>/fractal_data/CompoundV3RatesLoader/<key>.parquet`.

## Files staged here

This directory contains the **draft** of the PR — copy out into a
fractal-defi fork at submission time:

```
fractal_pr_compound_loader/
├── README.md                     (this file)
├── compound.py                   (the loader, mirrors aave.py)
├── test_compound_v3_loader.py    (real-API test)
└── test_lending_global_state_utilization.py
```
