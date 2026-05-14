# Add Compound V3 lending loader + uniform `utilization` field on lending global states

## Summary

This PR adds two coherent pieces to the lending stack of `fractal-defi`:

1. **`CompoundV3RatesLoader`** — a Messari-subgraph loader for Comet markets
   that emits `LendingHistory` in the same per-period rate units as the
   existing `AaveV3RatesLoader`, paginated descending-cursor over
   `marketHourlySnapshots`.

2. **`utilization: float` field on `AaveGlobalState`** and the equivalent
   on the new `CompoundV3GlobalState` — populated by the loader, exposed
   to strategies via `entity.global_state.utilization`. Makes the
   multi-criteria allocation pattern (utilisation-aware risk factor) a
   first-class citizen across both lending entities.

The PR is sized to be reviewable: ~400 lines net additions, two new files,
one one-line field on an existing dataclass, two test files (one offline
fixture, one live-API).

## Motivation

In v1.3.2 the lending side of the framework exposes:
- `BaseLendingEntity` + concrete `AaveEntity` with `lending_rate` /
  `borrowing_rate` on `GlobalState`,
- `AaveV3RatesLoader` going through Aave's own GraphQL gateway.

There is no Compound V3 loader, and no `utilization` on the lending
global state. This blocks any allocation strategy whose decision rule
includes a utilisation-headroom factor — exactly the use case for which
@SergeySolovyev / HSE Master's project (DeFi-Strategies coursework)
wants the framework. Implementing this against a personal fork worked but
duplicates effort; the upstream change is small and useful for any
downstream user.

## Design notes

### Loader pattern

`CompoundV3RatesLoader(BaseGraphLoader)` — subclasses
`ArbitrumGraphLoader` (the project's unified-gateway convenience class),
identical to the pattern used by `UniswapV3*PoolDayDataLoader`. Cursor-
based descending pagination on `timestamp_lt:` avoids `skip`'s O(N²) cost.

The Messari `Market.rates` array uses **percentage BigDecimal** (5.25 ==
5.25% APR) — NOT WAD/RAY. The loader converts:

```python
apr_decimal = float(rate.rate) / 100.0
per_period  = apr_decimal / ((365 * 24) / resolution)   # matches AaveV3RatesLoader
```

This convention match is the critical detail: a strategy comparing Aave
vs Compound at the same instant would silently get wrong cross-protocol
spreads otherwise.

### Utilisation field

Single-line addition to `fractal/core/entities/protocols/aave.py`:

```python
@dataclass
class AaveGlobalState(BaseLendingEntity.GlobalState):
    ...
    utilization: float = 0.0
```

`utilization=0.0` default preserves backward compat (existing
`AaveGlobalState()` calls keep working). New loaders populate it from
`totalCurrentVariableDebt / totalLiquidity` on the subgraph; old loaders
leave it zero.

The same field appears on `CompoundV3GlobalState` (new), computed from
the Messari `totalBorrowBalanceUSD / totalDepositBalanceUSD`.

### Sign-convention guard

Existing `AaveEntity.update_state` rejects `rate < -1` — a fail-loud
defence we preserve. Our loader additionally clips fractionally-negative
rates to zero (rare oracle glitch in Messari's USDC-feed-based USD
conversion during depeg windows), with a logged warning. Stronger
protocol-impossibility checks raise `GraphLoaderException` (e.g. if
`borrowing_rate < lending_rate` ever appears, which it never does on
Comet's rate model).

## Files

```
fractal/
├── core/
│   └── entities/
│       └── protocols/
│           ├── aave.py             ← +1 line for `utilization`
│           └── compound.py         ← NEW (mirrors aave.py shape;
│                                     CompoundV3Entity + GlobalState)
└── loaders/
    └── compound.py                 ← NEW (CompoundV3RatesLoader)

tests/
├── core/
│   └── test_lending_global_state_utilization.py    ← NEW
└── loaders/
    ├── test_compound_v3_loader_real.py             ← NEW, @pytest.mark.network
    └── test_compound_v3_loader_offline.py          ← NEW, uses committed fixture
```

## Tests

* **Offline fixture test:** committed 1-day Messari response fixture at
  `tests/loaders/fixtures/compound_v3_2026_01_01.json` exercised through
  `transform()` only. Deterministic CI.

* **Live-API test (`@pytest.mark.network`):** pulls 1-day window from the
  current Messari deployment, asserts schema + non-empty + sign
  convention + utilisation bounds. Skipped in `pytest -m 'not network'`.

* **Global-state invariant test:** for a cached `LendingHistory` fixture,
  asserts `0 <= utilization <= 1.05` (5% slack for snapshot timing).

## Verification by the contributor

Local pytest output:

```
$ pytest tests/loaders/test_compound_v3_loader_offline.py tests/core/test_lending_global_state_utilization.py -v
... 4 passed in 1.8s

$ pytest tests/loaders/test_compound_v3_loader_real.py -v -m network
... 1 passed in 12.3s   (1-day window, ~400 hourly rows on USDC base market)
```

## Out of scope

- Subgraph version pinning across protocol upgrades — kept as
  default-deployment lookup with caller-override escape hatch.
- Compound v3 markets other than cUSDCv3 (WETH, USDT base) — loader is
  market-address-parametric; tests cover only USDC base.
- Reserve-factor decoding from Aave configuration bitmap — `utilization`
  is the immediate need; reserve factor stays a constants table for now.

## Linked issue / discussion

See `extras/fractal_pr_compound_loader/README.md` in the
`SergeySolovyev/predictive-mcdm-defi` repo for the full motivation +
verification trail.

## Checklist

- [ ] Tests pass locally (`pytest tests/ -m 'not network'`)
- [ ] CHANGELOG.md entry under [Unreleased]
- [ ] Docstrings on all public functions
- [ ] No new dependencies outside the existing TheGraph stack
- [ ] Backward compat: `AaveGlobalState()` still constructs without args
