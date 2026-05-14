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

## Project regime structure (CORRECTED 2026-05-14 with full 98.5% coverage)

After publicnode `--append` top-up, Compound coverage rose from 37%
(Ankr-only) to 98.5% (Ankr + publicnode union). The sparse-sample
analysis was concentrated in cluster regions (Nov-Dec 2024 + Jun-Aug
2025) and produced a MISLEADING regime-shift narrative ("2025 Q1→Q2
jump"). The full-coverage analysis shows the true structure.

Real Aave-vs-Compound spread on n=12,895 overlapping hours (~98.5%
coverage of Nov 2024 — Apr 2026):

  Quarter    n_hours  spread_median  spread_std  Aave-higher %
  2024 Q4    1455     -0.591 pp      5.746 pp    45.4%
  2025 Q1    2160     -0.725 pp      1.360 pp    24.9%   <- Compound calm-dominant
  2025 Q2    2184     -0.444 pp      0.883 pp    43.5%   <- Compound mixed
  2025 Q3    2208     -0.218 pp      1.401 pp    39.9%   <- Compound dominant
  2025 Q4    2208     +0.183 pp      2.019 pp    56.3%   <- FIRST Aave-dominant Q
  2026 Q1    1960     -0.240 pp      0.567 pp    27.1%   <- Compound calm
  2026 Q2     720     +0.063 pp      3.605 pp    61.3%   <- Aave dominant (partial)

Overall (full coverage): median -0.232pp, std 2.513pp, 40.7%
Aave-higher, range [-26.79, +44.89] pp.

**Key findings for whitepaper §5/§9 (CORRECTED):**

1. **REAL REGIME SHIFT 2025 Q3 → Q4:** Aave-pays-more share jumps from
   39.9% to 56.3% (16-point shift), and median spread crosses zero from
   -0.22pp to +0.18pp. This is the FIRST quarter where Aave systematically
   pays more than Compound. The previous "Q1→Q2 jump" reported in
   sparse-sample analysis was an artifact of cluster sampling.

2. **VOLATILITY REGIMES:** Q4 2024 std 5.75pp (high-vol shock period) vs
   2026 Q1 0.57pp (calm) → ~10× variation. Plan §6.4 tertile-split
   (ablation #13) has stronger natural anchors than previously thought.

3. **40.7% Aave-higher overall:** profit from TIMING crossovers, not
   structural bias. Random allocator earns 0 alpha; forecast-driven edge
   IS anticipating shifts. Empirical H1 of plan §16.

4. **2026 Q2 partial (720h):** test window starts here. Aave-higher 61% =
   another regime, opposite of 2026 Q1 (27%). Strong test bench for H1.

**Methodology lesson:** sparse-sample analysis can produce false regime
narratives. Whitepaper §5 must report the full-coverage numbers; earlier
sparse-sample claims (in commits before this update) should be flagged
as deprecated in the prose.

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
