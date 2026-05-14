# Extra+1 PR: Compound V3 Lending Loader + Uniform `utilization` Field

**Target:** `Logarithm-Labs/fractal-defi`
**PR title:** *"Add Compound V3 lending loader + expose `utilization` on lending global states"*
**Status:** scoped, not yet submitted
**Deadline:** 12 June 2026 (PROJECT_2_PLAN.md timeline Week 4 Day 5)

## Verified prior art (2026-05-14, against fractal-defi v1.3.2 source)

- Existing `AaveV3RatesLoader` does NOT use the BaseGraphLoader / TheGraph
  network. It queries Aave's own gateway (`api.v3.aave.com/graphql`) using
  window-enum queries (`LAST_DAY`..`LAST_YEAR`), not pagination. So it is a
  **poor structural template** for a Messari-subgraph loader.
- The right template is `fractal/loaders/thegraph/base_graph_loader.py`
  (BaseGraphLoader at line 37), with paginated query pattern as shown in
  `fractal/loaders/thegraph/uniswap_v3/` and `uniswap_v2/` loaders.
- `AaveGlobalState` lives at `fractal/core/entities/protocols/aave.py:9-27`
  as a dataclass. Adding `utilization: float = 0.0` is a 1-line change with
  backward compat (default keeps zero-arg construction working).
- `LendingHistory` (`fractal/loaders/structs.py:50`) is the loader return
  type: `pd.DataFrame` subclass with columns `lending_rate`, `borrowing_rate`,
  UTC datetime index named `time`.
- `AaveEntity.update_state` (`...aave.py:390-406`) crashes with
  `EntityException` if `rate < -1`. Our loader must guarantee positive rates.

## Scope (single PR, two coherent components)

### Component A — Compound V3 loader

New file: `fractal/loaders/compound.py`

```python
class CompoundV3RatesLoader(BaseGraphLoader):
    """Compound V3 (Comet) lending rate loader via Messari subgraph.

    Pulls hourly snapshots of Market.rates + totals from the cUSDCv3
    market (proxy 0xc3d688B66703497DAA19211EEdff47f25384cdc3) on Ethereum.

    Messari emits `rates` as BigDecimal PERCENTAGE (5.25 == 5.25% APR);
    we convert to arithmetic per-period rate matching the AaveV3RatesLoader
    output convention:
        per_period = (rate / 100.0) / ((365*24) / resolution)
    """
    DEFAULT_ROOT_URL = "https://gateway.thegraph.com/api"
    USDC_MARKET = "0xc3d688B66703497DAA19211EEdff47f25384cdc3"

    def __init__(
        self,
        api_key: str,
        market_address: str = USDC_MARKET,
        chain_id: int = 1,
        loader_type: LoaderType = LoaderType.PARQUET,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        resolution: int = 1,        # 1 = hourly
        deployment_id: str | None = None,  # auto-resolved from messari/subgraphs if None
    ):
        super().__init__(api_key=api_key, ...)
        ...
```

Key implementation notes:
- Use `BaseGraphLoader._make_request(query)` for the HTTP/GQL plumbing.
- Paginated query against `marketHourlySnapshots(first: 1000, skip: $skip,
  where: { market: <USDC_MARKET> }, orderBy: timestamp, orderDirection: asc)`.
- Returns `LendingHistory(lending_rates=arr, borrowing_rates=arr, time=arr)`.
- Cache key: `f"{chain_id}-{market_address}-{start_iso}-{end_iso}-{resolution}"`.
- Resolve `deployment_id` from `https://raw.githubusercontent.com/messari/subgraphs/master/subgraphs/compound-v3/deployment.json`
  unless caller provides one explicitly (pinned-deployment escape hatch).

### Component B — `utilization` field on lending global states

Diff to `fractal/core/entities/protocols/aave.py:9-27`:
```python
@dataclass
class AaveGlobalState(BaseLendingEntity.GlobalState):
    lending_rate: float = 0.0
    borrowing_rate: float = 0.0
    collateral_price: float = 0.0
    debt_price: float = 0.0
    utilization: float = 0.0           # NEW — backward compat via default
```

New `CompoundV3GlobalState` in `fractal/core/entities/protocols/compound.py`
(if `CompoundV3Entity` is itself the target of a separate PR — verify first;
if `CompoundV3Entity` does not exist in v1.3.2, the Extra+1 PR may need to
add it as well, or we just provide raw `LendingHistory` data and use
`SimpleLendingEntity`).

Loaders populate `utilization` via:
- Aave: from a secondary on-chain or subgraph call exposing
  `totalCurrentVariableDebt / totalLiquidity`. (TheGraph protocol-subgraph is
  the cleanest source — may need to introduce a SECOND Aave loader variant
  if the existing gateway-only loader cannot.)
- Compound: directly from `marketHourlySnapshot.totalBorrowBalanceUSD /
  marketHourlySnapshot.totalDepositBalanceUSD`.

## Tests

Add to `tests/loaders/`:
- `test_compound_v3_loader_real.py` — pulls 1-day window from live subgraph,
  asserts schema + non-empty + sign convention.
- `test_compound_v3_loader_offline.py` — uses a 1-day fixture (committed to
  `tests/loaders/fixtures/compound_v3_2026_01_01.json`) for deterministic CI.

Add to `tests/core/`:
- `test_lending_global_state_utilization.py` — invariant
  `0 <= utilization <= 1.05` (5% slack) for both Aave and Compound on a
  cached fixture. Documents the protocol-physical bound.

## Gotchas to address in PR description

1. **Sign assertion crash** — `rate < -1` crashes `AaveEntity.update_state`;
   our loader pre-clamps to `max(rate, -0.99)` or rejects the snapshot with
   a logged warning.
2. **Deep-copy of GlobalState** per observation (`strategy.py:374-377`) means
   the added `utilization: float` field must stay scalar — no DataFrames /
   complex objects allowed.
3. **STRICT_OBSERVATIONS = True** default — for mixed-frequency lending feeds
   document that consumers may want to set it False on their strategy.

## Files staged here

```
fractal_pr_compound_loader/
├── README.md                     (this file)
├── compound.py                   (loader, follows BaseGraphLoader pattern)
├── test_compound_v3_loader_real.py
├── test_compound_v3_loader_offline.py
├── test_lending_global_state_utilization.py
└── PR_BODY.md                    (final PR description draft)
```
