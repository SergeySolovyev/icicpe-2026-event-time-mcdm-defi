# Claude Code — Project Memory for `predictive-mcdm-defi`

This file is loaded automatically when Claude works in this repo. It captures
project-specific conventions, blockers, and "do/don't" rules accumulated
during development.

## What this project is

Predictive MCDM allocator across **Aave V3** and **Compound V3** USDC supply
markets on Ethereum mainnet. Built on **fractal-defi v1.3.2** as Project 2
of an HSE FCS DeFi-Strategies course (4-week scope: 18 May → 14 June 2026).

Strategic plan: `PROJECT_2_PLAN.md` (740 lines, 18 sections).
Deep research: `DEEP_RESEARCH.md` (~600 lines, 25+ citations).
ERRATA correcting v1.3.2 + endpoint + scaling discrepancies is in the
plan's prepended block.

## Hard constraints (DO NOT change without explicit user instruction)

1. **`fractal-defi==1.3.2`** pinned via git tag (PyPI lacks v1.3.2 as of
   2026-05-14). Do NOT bump to dev / main / unreleased v1.4.0.

2. **`SimpleLendingGlobalState.collateral_price = 1.0`** is a loader
   contract. Any `Observation` for AAVE / COMPOUND MUST set this. The
   abstraction's defensive runtime check will raise `RuntimeError` with
   a clear message if a loader forgets. Do not silence this check.

3. **Subgraph IDs are verified** against the official protocol repos:
   - Aave V3 Ethereum: `Cd2gEDVeqnjBn1hSeqFMitw8Q1iiyV9FYUZkLNRcL87g`
     (verified against `aave/protocol-subgraphs` README, 2026-05-14).
   - Compound V3 Messari: `AwoxEZbiWLvv6e3QdvdMZw4WDURdGbvPfHmZRc8Dpfz9`
     (verified against `messari/subgraphs/deployment/deployment.json`,
     **but indexes per-collateral markets, not base** — see Discovery 3
     below).
   Don't replace these without an external-source check.

3a. **Aave subgraph `liquidityRate` is annualized × RAY, NOT per-second × RAY.**
    Empirically verified 2026-05-14 (first fetch returned 47M% APR until
    the conversion was fixed). Conversion to per-period rate that
    matches `AaveV3RatesLoader` (gateway-loader) convention:
        annualized_apr = liquidityRate / 1e27
        per_period_rate = annualized_apr / ((365 * 24) / resolution)
    Same for `variableBorrowRate`.

3b. **Aave subgraph emits event-stream, not hourly snapshots.**
    ~50 rows/hour over 18 months = 654k raw rows. Loader's `transform()`
    resamples to uniform hourly grid via `df.resample("Nh", label="right",
    closed="right").last()` -> 13,096 hourly bars. Sequence-length=168
    in the forecaster expects "168 HOURS of context", not events.

3c. **Compound V3 Messari `Market` is per-collateral, not per-base.**
    `Market.id` format is `<comet><collateral>` concatenated.
    `marketHourlySnapshots` ONLY has rows for collateral markets.
    The base Comet market (`0xc3d688...`) exists as a `Market` entity
    BUT has zero hourly snapshots and `rates: None` on the schema.
    Workaround in `data/fetch_compound_via_rpc.py`: query Comet's view
    functions (`getUtilization`, `getSupplyRate(u)`, `getBorrowRate(u)`)
    at historical block numbers via batched eth_call (Alchemy archive
    access). ~13k hourly bars × 3 calls / 500 per batch ≈ 80 requests,
    ~3-5 min wall-clock.

3d. **Comet function selectors** (verified via keccak256 in pycryptodome):
    `getUtilization()` = `0x7eb71131`
    `getSupplyRate(uint256)` = `0xd955759d`
    `getBorrowRate(uint256)` = `0x9fa83b5a`
    These differ from the speculative values previously hardcoded in
    `data/fetch_kink_params.py`. Sync that file's `SEL` dict against
    these on next edit.

3e. **Free public archive RPCs have batch-size caps ~100 calls/request.**
    Empirically discovered 2026-05-14:
      Alchemy free:                  no documented limit, but
                                     rate-limited drop ~85% of calls
      publicnode (anon):             100 calls/req hard cap, otherwise
                                     fast and reliable (27ms/call)
      Ankr free (authenticated):     100 calls/req hard cap, slightly
                                     faster than publicnode (19ms/call),
                                     but ~7000 successful eth_call/day
                                     soft limit before throttling kicks
    Our `fetch_compound_via_rpc.py` splits phase-2 (200 calls) into
    sub-batches of `batch_size` (100) calls to fit within these caps.
    For multi-day fetches: split across days or use multiple endpoints.

## Project regime structure (discovered 2026-05-14)

Real Aave-vs-Compound spread analysis on n=4894 overlapping hourly
observations (from 2024-11 to 2026-04, ~37% coverage on Compound):

  Quarter    n_hours  spread_median  spread_std  Aave-pays-more%
  2024 Q4      908     +0.10pp        4.80pp     51%
  2025 Q1     1336     -0.64pp        1.43pp     25%   <- Compound dominant
  2025 Q2     1458     +0.22pp        0.94pp     55%   <- REGIME SHIFT to Aave
  2025 Q3      992     -0.07pp        1.30pp     45%
  2025 Q4      150     -0.15pp        0.76pp     39%
  2026 Q1       50     -0.23pp        0.46pp     38%

Overall: 43.4% Aave-pays-more (close to 50/50 split), spread std 2.34pp,
range -13 to +33pp.

**Key findings for whitepaper §5/§9:**

1. **REGIME SHIFT 2025 Q1 → Q2:** Aave-pays-more share jumps from 25% to
   55%. Exactly the regime structure Markov-switching (ablation #4) and
   DA-BiGRU-CNN Branch B are designed to detect. Empirical existence
   proof for H2 (architectural detection of regimes).

2. **VOLATILITY REGIMES:** Q4 2024 std 4.80pp (high-vol) vs Q3 2025 1.30pp
   (calm) → 4× variation. Plan §6.4's tertile-split (ablation #13) now
   has natural anchor points.

3. **SYMMETRIC SHARE:** 43.4% Aave-pays-more → profit from TIMING the
   crossovers, NOT from any structural bias. Random allocator earns 0
   alpha by design; forecast-driven edge IS anticipating crossovers.
   Empirical version of plan §16 H1.

4. **Aave V3 loader convention**: APY divided by `(365 * 24) / resolution`
   gives the per-period rate (arithmetic, NOT continuously compounded).
   The Compound loader MUST match this convention so cross-protocol
   spreads are in identical units. Don't introduce per-second-rate
   compounding silently.

5. **Sign convention lock-in**: `borrowing_rate >= lending_rate` at every
   timestep for both protocols. Enforced by `tests/test_sign_convention.py`
   and by an exception in `data/clean.py:assert_sign_convention`.

6. **`from __future__ import annotations` is INCOMPATIBLE with the
   Windows torch DLL workaround.** Files that `import torch` (notably
   `forecaster/train.py`, `forecaster/export_onnx.py`, `tests/conftest.py`)
   must put `import torch` BEFORE any other import — that prevents
   numpy/MKL from poisoning torch's c10.dll load order on Windows.
   Therefore those files cannot use `from __future__ import annotations`
   (which must be the first statement after the docstring). Just write
   plain `import` order in those files.

## Coding conventions discovered the hard way

* **Callable delegates passed to `fractal-defi` actions** are resolved as
  `val(self)` — the framework passes the strategy instance as a positional
  arg. So a delegate snapshotting a value MUST be a 2-arg function:
  `def _amount_delegate(_strategy, _amt: float = amount_snapshot)`.
  A `lambda _amt=...:` without a strategy-positional will have its
  default overwritten silently. Lock-in regression test:
  `tests/test_strategy_logic.test_transfer_delegate_returns_snapshot_not_strategy`.

* **`__init_subclass__` PARAMS_CLS auto-detection** only works for direct
  `BaseStrategy[ParamsClass]` subclasses. `BaseLendingAllocationStrategy`
  already concretized its TypeVar, so subclasses MUST declare
  `PARAMS_CLS = MyParams` explicitly as a class attribute. The auto-detect
  silently falls back to the inherited PARAMS_CLS otherwise.

* **`STRICT_OBSERVATIONS = True`** (default on our abstraction) means
  every Observation must have states for every registered entity. The
  `data/clean.py` join+ffill pipeline satisfies this. Subclasses bypassing
  `data/clean.py` should `STRICT_OBSERVATIONS = False`.

* **fractal-defi loader cache** lives under `<DATA_PATH or cwd>/fractal_data/`.
  Both that path AND `data/cached/fractal_data/` are gitignored. If you
  run a loader without setting `DATA_PATH`, it writes to repo root — don't
  commit the resulting `fractal_data/` directory.

## Test conventions

* Mark live-API tests with `@pytest.mark.network` (registered in
  `pytest.ini`). CI runs `pytest -m 'not network'`.

* Per the loader contract, tests that manually trigger rebalance must seed
  the source entity with `collateral` AND `collateral_price = 1.0` before
  calling `predict()`. Use `_seed_funds_in(strategy, name)` helper in
  `tests/test_strategy_logic.py`.

* Float-precision is a real issue at the hysteresis boundary. Tests use
  `0.50 / 0.54` (delta = 0.04) for the "below threshold" case, NOT
  `0.50 / 0.55` (which evaluates to 0.0500000000000004 > 0.05). Don't
  reintroduce boundary-exact tests.

## Build / run

```powershell
make verify-imports        # 7 fractal-defi imports sanity-check
make data                  # fetch_aave + fetch_compound + fetch_gas_eth + clean
make train                 # forecaster.train -> MLflow + .pt checkpoint
make backtest              # baselines + main on test window
make ablations             # 15 ablations
make test                  # pytest tests/
make whitepaper            # latexmk -pdf
```

Smoke test the whole pipeline (no API key required):

```powershell
.venv\Scripts\python -m forecaster.model              # 319K params, smoke OK
.venv\Scripts\python -m forecaster.losses             # composite loss check
.venv\Scripts\python -m forecaster.baseline_cir       # CIR self-test
.venv\Scripts\python -m forecaster.baseline_catboost  # CatBoost self-test
.venv\Scripts\python -m forecaster.train              # 2-epoch synth training
.venv\Scripts\python -m forecaster.export_onnx --ckpt forecaster/trained_models/da_bigru_cnn_selftest.pt
.venv\Scripts\python -m backtest.run_baselines --synthetic
.venv\Scripts\pytest tests/ -v -m "not network"       # 26 pass, 3 skip
```

## Current blockers (state as of 2026-05-14)

* **`THE_GRAPH_API_KEY`** — needed for `data/fetch_aave_subgraph.py` and
  `data/fetch_compound.py`. Setup steps in `docs/CREDENTIALS_SETUP.md`.
  Until it arrives, work proceeds on synthetic data.

* **`ETHEREUM_RPC_URL`** (recommended) — needed for
  `data/fetch_kink_params.py`. Alchemy free tier suffices.

* **GPU access** — DA-BiGRU-CNN training on real data should run on Colab
  Pro or an H100 instance, not the local Windows CPU torch. Plan is
  forecaster training as Week 1 Days 6–7.

## Extra+1 and Extra+2 PRs to fractal-defi

Both staged under `extras/`:

* **Extra+1** (`extras/fractal_pr_compound_loader/`): Compound V3 Messari
  loader + a `utilization: float` field on both AAVE and COMPOUND
  `GlobalState`. Verified against the BaseGraphLoader pattern from
  uniswap_v3 loaders.

* **Extra+2** (`extras/fractal_pr_lending_allocation/`):
  `BaseLendingAllocationStrategy` abstraction with 4 hooks
  (compute_criteria_vector, aggregate_criteria, select_target,
  should_rebalance) + default predict() orchestration via the framework's
  transfer() helper + cooldown infrastructure that the framework lacks.

Both contain `README.md` describing PR scope. The `sys.path.insert` hacks
in the strategy files are deferred to PR-stage cleanup — the production
import path is `from fractal.strategies.base_lending_allocation import ...`
once merged.

## Commit conventions

Co-authored line is preserved. Commit messages are detailed (multi-paragraph)
because this is a research project where reviewers will want to understand
the reasoning. Single-line commit messages are not used.

Don't `git push origin main` without explicit user instruction.
