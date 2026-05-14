# ERRATA (applied 2026-05-14, after live-state verification of `fractal-defi`)

Three corrections to the strategic plan below, discovered during planning
verification against `Logarithm-Labs/fractal-defi` repo state:

1. **Version pin: v1.4.0 → v1.3.2.** Plan §6.1 and §15 row 12 say
   `fractal-defi v1.4.0+`. Latest release is v1.3.2 (2026-05-06).
   CHANGELOG forward-references v1.4.0 but tag is unreleased. We pin
   `fractal-defi==1.3.2` in `requirements.txt` and rely on
   `tests/test_sign_convention.py` to lock in `borrowing_rate >=
   lending_rate` from real data.

2. **Entity name: `AaveV3Entity` → `AaveEntity`.** Plan §3 pseudocode line 225
   and §6.1 prose reference `AaveV3Entity()`. Actual class in the repo is
   `AaveEntity` in `fractal/core/entities/protocols/aave.py` (no V3 suffix).

3. **`utilization` not in `AaveGlobalState`.** Plan's MCDM `f_Risk(u_i)`
   factor needs utilization. Repo's `AaveGlobalState` exposes only
   `lending_rate`, `borrowing_rate`, `collateral_price`, `debt_price`.
   Resolution: Extra+1 PR is broadened from "Compound V3 loader" to
   **"Compound V3 loader + `utilization` field on both Aave and Compound
   `GlobalState`"**, computed from `totalLiquidity` /
   `totalCurrentVariableDebt` in the existing subgraph response. This
   raises Extra+1 from "yet another loader" to "loader + uniform state
   interface across lending entities."

The remainder of this document is the original locked-scope plan, unchanged.

---

# Project 2 — Predictive MCDM Allocation across DeFi Lending Protocols

**Scope-Fixing Document v2 (post-research)**
**Author:** Sergei Solovev (HSE FCS)
**Course:** DeFi Strategies — Project 2
**Date:** 14 May 2026
**Status:** Locked scope for execution starting 18 May 2026
**Working title of whitepaper:** *"Predictive Multi-Criteria Allocation across DeFi Lending Protocols: A Forecast-Driven Extension of the AI-Managed ERC-4626 Vault on the fractal-defi Substrate"*

---

## 0. Executive Summary

This project transfers high-frequency-trading microstructure forecasting methodology to **dynamic capital allocation between Aave v3 and Compound v3** USDC supply markets. The novel contribution: replacing the reactive EMA-smoothed rate observation in the author's prior on-chain MCDM allocator (AI-Managed ERC-4626 Yield Vault, Solovev 2026b) with a 12-hour-ahead learned forecast inspired by the author's prior dual-branch architecture for LOB mid-price prediction (DA-BiGRU-CNN, Solovev 2026a).

The strategy is implemented in the `fractal-defi` framework (Logarithm-Labs, v1.4.0+) and backtested on 18 months of historical Aave v3 and Compound v3 USDC supply-rate data. Performance is measured against four baselines: buy-and-hold Aave v3, APY-only greedy, reactive MCDM-with-EMA (ported from AI Yield Vault), and CIR-calibrated classical short-rate forecast.

**Strategic positioning:** the project explicitly extends the Vega Institute / HSE / Skoltech `fractal-defi` research program (Urusov et al. 2024, 2025; Krestenko et al. 2026) from AMM/perp microstructure to lending microstructure — three microstructure panels on one substrate.

**Honest expected outcome:** out-of-sample R² of 0.15–0.40 for 12-hour rate forecast, direction accuracy 55–65% on "which protocol pays more in 12h", Sharpe improvement of 0.2–0.5 vs reactive EMA baseline. The null hypothesis (forecast adds no value over EMA on this horizon) is explicitly entertained in the methodology and cannot be ruled out a priori.

---

## 1. Problem Statement

### 1.1 Context

DeFi lending protocols offer supply-side yield that fluctuates with utilization, market demand, and protocol-specific factors. Supply rates on Aave v3 and Compound v3 USDC markets are not synchronized — they cross repeatedly over time. Gudgeon et al. (2020) established empirically that Compound USDC borrowing rates *lead* Aave (cointegration with Compound as leader, Aave adjusting at speed 0.607). A capital provider who can predict these crossovers and rebalance ahead of them captures yield differential that a reactive observer misses.

The problem is structurally analogous to high-frequency mid-price prediction in limit-order books: noisy multivariate time series, regime-dependent dynamics, weighted-error metric (large rate moves matter more than small ones), and a discrete decision rule (rebalance / hold). This isomorphism is the methodological foundation of the project.

### 1.2 Strategy Objective

Maximize risk-adjusted net APY on a stablecoin (USDC) deposit, after gas and execution costs, by predictive routing between two lending protocols on Ethereum mainnet.

### 1.3 Market Assumptions

- Ethereum mainnet only (no L2, no cross-chain)
- Single underlying asset: **USDC**
- Two protocols: **Aave v3** (Pool, `aUSDC`) and **Compound v3** (Comet, USDC base market `0xc3d688B66703497DAA19211EEdff47f25384cdc3`)
- Capital size: $1,000,000 notional (institutional-relevant; large enough that gas costs are small percentage of yield)
- No leverage, no borrowing, supply-side only
- Withdrawal liquidity always available (true historically for USDC supply on both protocols during the chosen 18-month window; documented as assumption)
- Reserve factor and protocol fees applied as protocols apply them on-chain (do not recompute supply rate from utilization × borrow rate; use `liquidityRate` directly)

### 1.4 Target Instruments

- Aave v3 USDC supply position (aUSDC), accruing yield via `liquidityIndex`
- Compound v3 USDC supply position (Comet base), accruing yield via `baseSupplyIndex`

### 1.5 Constraints

- **Cooldown:** ≥ 1 hour between rebalances (anti-thrashing; inherited from AI Yield Vault § 4.4.5)
- **Hysteresis:** MCDM score delta must exceed θ = 0.05 to trigger
- **Gas-cost gate:** expected APY uplift × time-to-next-decision × notional ≥ gas cost
- **No look-ahead:** forecast uses only data available at decision time; train/val/test split uses strict `block_number` filter to defend against subgraph-aggregation leakage
- **Sign-convention assertion:** require `borrowing_rate ≥ lending_rate` for all timestamps (true by protocol; defends against fractal-defi v<1.4.0 sign-flip bug)

### 1.6 Expected Source of Alpha

Two decomposable components:

1. **Microstructure forecast edge.** The DA-BiGRU-CNN-derived 12-hour predictor anticipates short-horizon rate moves better than the EMA baseline. Expected magnitude: 0.5–2% improvement in forecast weighted Pearson correlation on the rate level, 5–10 percentage-point improvement in direction accuracy on the binary "Aave > Compound at t+12h" task. Theoretical basis: Compound-leads-Aave cointegration (Gudgeon et al. 2020) means short-horizon predictability exists at minimum from cross-protocol lead-lag.

2. **Multi-criteria scoring edge.** MCDM correctly avoids high-APY-but-high-risk protocols (e.g., Aave at 95% utilization). Already demonstrated qualitatively in AI Yield Vault paper § 4.4.6 on testnet; this work validates it on mainnet historicals with realistic gas, slippage, and cointegration-driven crossover dynamics.

The headline ablation question: **does combining (1) and (2) outperform reactive MCDM-with-EMA alone, net of costs?**

### 1.7 Risk-Premium Interpretation

The strategy does **not** earn a structural risk premium — the underlying is USDC supply on the two most battle-tested DeFi lending protocols. The edge, if any, is **execution quality**: capturing transient cross-protocol rate dispersion that disappears under reactive allocation. This must be stated explicitly in the whitepaper to pre-empt efficient-market-violation overclaims.

---

## 2. Formal Description

### 2.1 State

At time *t*, observable state for protocol *i* ∈ {Aave, Compound}:

```
x_i(t) = ( r_i(t), u_i(t), TVL_i(t), ΔTVL_i(t), kink_i(t) )
g(t)   = current gas price (gwei)
```

where:
- `r_i` — annualized supply rate (from on-chain `liquidityRate` / `baseSupplyIndex` derivative)
- `u_i` — utilization ∈ [0, 1]
- `TVL_i` — total supplied USDC
- `ΔTVL_i` — relative change of TVL over 24h rolling window
- `kink_i` — protocol-parameter tuple (`optimalUtilization`, `slope1`, `slope2`, `reserveFactor`) sourced from on-chain configuration events; treated as a slowly-varying feature

### 2.2 Forecast Component (Dual-Branch with Kink Subtraction)

Following the deep-research recommendation in §VI.B, the forecaster decomposes into two branches feeding a late-fusion head:

**Branch A — Rate residual.**
- Target: `ε_i(t) = r_i(t) − f_kink_i(u_i(t))`, where `f_kink_i` is the protocol-known piecewise-linear rate function
- Architecture: BiGRU(hidden=64, layers=2) on a 7-day rolling window of residuals + cross-protocol residual spread

**Branch B — Utilization.**
- Target: `û_i(t + Δ)`, where Δ = 12 hours
- Architecture: BiGRU(hidden=64, layers=2) + Conv1d(kernels=[3,5,7]) on a 7-day rolling window of (u, TVL, ΔTVL, gas, time-of-day) per protocol

**Fusion.**
- Reconstruct `r̂_i(t + Δ) = f_kink_i(û_i(t + Δ)) + ε̂_i(t + Δ)`
- Optional small late-fusion MLP corrects systematic bias of the additive reconstruction

**Loss function (composite, per §VI.C of research):**

```
L = α · MSE(r, r̂) + β · (1 − WeightedPearson(r, r̂)) + γ · QuantileLoss(r, r̂; q=0.9)
```

Weights tuned via validation grid search; defaults (α, β, γ) = (0.4, 0.5, 0.1). Sanity-checked by binary cross-entropy on the `r̂_Aave > r̂_Compound` label — minimum acceptable direction accuracy is 55%.

**Justification of branching scheme.** Volume in LOB is unbounded and signed; utilization in DeFi is bounded [0,1] and clamped at the kink. The dual-branch reasoning is *re-derived* for DeFi (not naively transferred) — this is explicitly acknowledged in the whitepaper. The kink-subtraction structure encodes a hard domain prior: the deterministic protocol function does not need to be learned, freeing model capacity for the genuinely stochastic residual.

### 2.3 MCDM Scoring (Inherited and Extended)

For each protocol *i*:

```
Score_i(t) = w_1·f_APY(r̂_i(t+Δ)) + w_2·f_Risk(u_i(t)) + w_3·f_Cost(g(t)) + w_4·f_Stab(ΔTVL_i(t))
```

with default weights (w_1, w_2, w_3, w_4) = (0.40, 0.25, 0.20, 0.15) carried directly from AI Yield Vault Eq. 15. **Critical change vs original:** `f_APY` now uses the **forecast** `r̂_i(t+Δ)`, not spot `r_i(t)` or its EMA `S_i(t)`.

Sub-factors (per AI Yield Vault § 4.4):

```
f_APY(r̂)     = clamp(r̂ / APYmax, 0, 1),       APYmax = 0.20
f_Risk(u)    = 1 − clamp(u, 0, 1)
f_Cost(g)    = 1 − clamp(g·G / gmax, 0, 1),    G = 200_000 gas, gmax = 0.01 ETH
f_Stab(ΔTVL) = 1 − clamp(|ΔTVL| / 0.30, 0, 1)
```

**Why TOPSIS-style weighted-sum rather than PROMETHEE / ARAS / AHP:** parsimony. The author's prior paper established the four-criterion weighted-sum framework; this project's contribution is the forecast head, not the MCDM aggregator. Comparison with PROMETHEE-style allocation is listed as future work, not delivered here.

### 2.4 Decision Rule

```
i*(t) = argmax_i Score_i(t)

Rebalance to i*(t) iff:
    Score_{i*}(t) − Score_{current}(t) > θ                  (θ = 0.05)
    AND  t − t_last_rebalance > τ_cooldown                  (τ = 1 hour)
    AND  expected_uplift × (t_horizon − t) × N ≥ gas_cost × ETH/USD(t)
```

where `N` is notional, `expected_uplift = r̂_{i*} − r̂_{current}`, `gas_cost = 200_000 × g(t) × 10⁻⁹` ETH.

### 2.5 Objective Function

```
maximize  Sharpe(strategy_returns) − λ · MaxDD
subject to  net APY > buy-and-hold(Aave v3)
            net APY > APY-only greedy baseline
            turnover < 2× best baseline turnover  (anti-pathology)
```

λ = 0.5 default; sensitivity reported in ablations.

---

## 3. Pseudocode

```
# === FORECASTER (offline, pre-trained, exported to ONNX) ===

class DualBranchKinkSubtractionForecaster:
    """
    Inputs : history_window (W=168 hours, F features), kink params per protocol
    Outputs: r̂_aave(t+12h), r̂_compound(t+12h)
    """
    def predict(history_window, kink_params):
        # Branch A — rate residual
        resid_features = history_window[:, ["r_aave_resid",
                                            "r_compound_resid",
                                            "spread_resid"]]
        h_A = BiGRU_A(resid_features)                          # → R^{2·64}

        # Branch B — utilization + context
        util_features  = history_window[:, ["u_aave", "u_comp",
                                            "TVL_aave", "TVL_comp",
                                            "dTVL_aave", "dTVL_comp",
                                            "gas_gwei", "tod_sin", "tod_cos"]]
        h_B_gru = BiGRU_B(util_features)                       # → R^{T, 2·64}
        h_B_cnn = MultiScaleConv1d(kernels=[3,5,7])(h_B_gru)   # → R^{2·48}

        # Late fusion
        z = concat([h_A, h_B_cnn])
        û_aave, û_comp, ε_corr = MLP_head(z)

        # Reconstruct via kink function
        r̂_aave = f_kink(û_aave, kink_params["aave"]) + ε_corr[0]
        r̂_comp = f_kink(û_comp, kink_params["comp"]) + ε_corr[1]
        return r̂_aave, r̂_comp


# === STRATEGY (fractal-defi BaseStrategy) ===

@dataclass
class PredictiveMCDMParams(BaseStrategyParams):
    INITIAL_USDC      : float = 1_000_000.0
    THETA_HYSTERESIS  : float = 0.05
    TAU_COOLDOWN_HRS  : float = 1.0
    APYMAX_NORM       : float = 0.20
    GAS_MAX_ETH       : float = 0.01
    GAS_PER_REBALANCE : int   = 200_000
    W_APY             : float = 0.40
    W_RISK            : float = 0.25
    W_COST            : float = 0.20
    W_STAB            : float = 0.15
    FORECAST_MODEL    : str   = "forecaster/trained_models/dual_branch_kink.onnx"


class PredictiveMCDMStrategy(BaseLendingAllocationStrategy):
    """
    Concrete subclass of the (this-project-defined) BaseLendingAllocationStrategy
    abstraction proposed as Extra+2 contribution to fractal-defi.
    """

    def set_up(self):
        self.register_entity(NamedEntity("AAVE",     AaveV3Entity()))
        self.register_entity(NamedEntity("COMPOUND", CompoundV3Entity()))    # Extra+1
        self._fcst   = load_onnx(self._params.FORECAST_MODEL)
        self._buf    = RollingBuffer(window=168)
        self._cur    = None
        self._last_t = None

    def predict(self) -> List[ActionToTake]:
        gs_a, gs_c = self.get_entity("AAVE").global_state, \
                     self.get_entity("COMPOUND").global_state

        self._buf.append(extract_features(gs_a, gs_c, self.now))
        if not self._buf.is_full():
            return []

        r̂_a, r̂_c = self._fcst.predict(self._buf.to_array(), self._fetch_kinks())

        s_a = self._mcdm_score(r̂_a, gs_a.utilization, gs_a.gas_gwei, gs_a.dTVL_24h)
        s_c = self._mcdm_score(r̂_c, gs_c.utilization, gs_c.gas_gwei, gs_c.dTVL_24h)

        best, best_s = ("AAVE", s_a) if s_a > s_c else ("COMPOUND", s_c)
        cur_s        = s_a if self._cur == "AAVE" else s_c

        if (best_s - cur_s) <= self._params.THETA_HYSTERESIS:        return []
        if self._cooldown_active():                                  return []
        if not self._gas_gate(r̂_a, r̂_c):                            return []

        return [
            ActionToTake(self._cur, Action("withdraw", {"amount": lambda: "all"})),
            ActionToTake(best,      Action("supply",   {"amount": lambda e: e.cash})),
        ]
```

---

## 4. Data Description

### 4.1 Period

**18 months: 1 Nov 2024 — 30 Apr 2026.**

Split with strict block-number filter (prevents subgraph-aggregation leakage):
- **Train:** 2024-11-01 → 2025-08-31 (10 months) — forecaster training
- **Validation:** 2025-09-01 → 2025-12-31 (4 months) — model and hyperparameter selection
- **Test (held-out):** 2026-01-01 → 2026-04-30 (4 months) — final backtest

### 4.2 Sources (per §V of research report)

**Primary — Aave v3.** TheGraph official subgraph `aave-v3-ethereum`, entity `reserveParamsHistoryItems` filtered on USDC `0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48`. RAY (1e27) per-second scaling.

**Primary — Compound v3.** Messari subgraph for cUSDCv3 on Ethereum (`0xc3d688B66703497DAA19211EEdff47f25384cdc3`), entity `Market.rates` with hourly snapshots `marketHourlySnapshots`. WAD (1e18) per-second scaling. **The loader for this is one of the project's Extra+1 PR opportunities** — see §11.

**Fallback — Dune Analytics.** Tables `aave_v3_ethereum.LendingPool_evt_ReserveDataUpdated`, `compound_v3_ethereum.Comet_*`. SQL templates in research §V.

**Auxiliary:**
- Gas price: Dune `gas.gas_price` table, hourly median
- ETH/USD (for P&L conversion): CoinGecko free API, hourly close
- Kink parameters per protocol per epoch: on-chain Aave `ReservesUpdated` / Compound `Configurator` events

### 4.3 Resampling

Raw events → **1-hour buckets** via last-observation-carried-forward. Both protocols emit rates on state-modifying interactions; between events the index accrues continuously. The 12-hour decision cadence is well above per-event frequency on USDC markets, so aliasing is not a concern.

**Total observations:**
- Train: ~7,300 hourly bars
- Validation: ~2,900
- Test: ~2,900

### 4.4 Cleaning Procedure

1. **Outlier removal:** APY outside [0, 50%] → oracle-glitch removal; rate-jump guard `|r(t) − r(t−1)| / r(t−1) > 5` → interpolate
2. **Missing data:** forward-fill up to 6 hours; longer gaps marked as separate regime, excluded from training sequences, reported in test as edge cases
3. **Feature normalization:** z-score using training statistics only; applied to val/test (no leakage)
4. **Sign-convention assertion:** `borrowing_rate(t) ≥ lending_rate(t)` for all t (lock-in test against fractal-defi pre-v1.4.0 bug)

### 4.5 Limitations and Assumptions

- **Survivorship bias.** Both protocols existed throughout the period; not exposed to protocol failure risk
- **Liquidity assumption.** Any size up to $1M instantly withdrawable — historically true for USDC during window
- **Gas-cost model.** Flat 200K gas × historical median; gas can spike during stress exactly when forecast confidence is highest — this is a realistic friction, not an excluded scenario
- **MEV / sandwich risk.** USDC supply transactions are not meaningfully sandwich-able — ignored
- **Reserve factor and kink changes.** Tracked as features; documented as events in results
- **Single 18-month window.** Covers fewer than two full macro-regime cycles. OOD test on Mar-2023 depeg (out-of-window) included in ablations (#14)

---

## 5. Calibration

### 5.1 Forecaster Hyperparameters (MLflow grid)

Selection criterion: **validation weighted Pearson + directional accuracy ≥ 55%**.

| Parameter | Grid | Default |
|---|---|---|
| Hidden dim per branch | {32, 64, 96, 128} | 64 |
| BiGRU layers | {1, 2} | 2 |
| CNN kernels (Branch B) | {[3,5,7], [3,5], [5]} | [3,5,7] |
| Dropout | {0.0, 0.1, 0.2} | 0.1 |
| Learning rate | {1e-3, 2e-3, 5e-3} | 2e-3 |
| Batch size | {16, 32, 64} | 32 |
| Sequence length | {72, 168, 336} hours | 168 |
| Loss weights (α, β, γ) | 3-point grid | (0.4, 0.5, 0.1) |

### 5.2 Strategy Hyperparameters (MLflow grid)

Selection criterion: **Sharpe on validation**, turnover constraint < 2× best baseline.

| Parameter | Grid | Default (AI Yield Vault) |
|---|---|---|
| MCDM weights (w₁..w₄) | Dirichlet 20 samples + AI Yield Vault default | (0.40, 0.25, 0.20, 0.15) |
| Hysteresis θ | {0.02, 0.05, 0.08, 0.10} | 0.05 |
| Cooldown τ | {0.5h, 1h, 2h, 6h} | 1h |
| Forecast horizon Δ | {6h, 12h, 24h} | 12h |
| APYmax normalization | {0.10, 0.15, 0.20, 0.25} | 0.20 |

---

## 6. Backtesting Protocol

### 6.1 Framework

`fractal-defi` v1.4.0+ pinned (v1.4.0 required for Aave V3 sign-fix per CHANGELOG.md). Two `BaseLendingEntity` subclass instances (`AaveV3Entity` upstream, `CompoundV3Entity` from this project). Strategy inherits from project-defined `BaseLendingAllocationStrategy`.

### 6.2 Execution Assumptions

- **Decision cadence:** hourly (matches data resolution, well above forecast horizon)
- **Block time:** 12s; decisions emitted as hourly aggregates
- **No slippage** on USDC supply / withdraw (protocol-level operations, not AMM swaps)
- **Transaction cost:** 200,000 gas × `gas_price_gwei` × 10⁻⁹ × ETH/USD per rebalance
- **Execution-bridge friction:** withdraw-then-supply non-atomic ~12s; modeled as zero-yield on migrating notional
- **Funding payments:** N/A (supply-only)
- **Yield accrual:** continuous compounding at active protocol's supply rate, per hour

### 6.3 Rebalancing Rules

Per §3 pseudocode: hysteresis + cooldown + gas-cost gates.

### 6.4 Regime Split for Analysis

Post-hoc classify hours into low / medium / high volatility tertiles of σ(r); report headline metrics per regime. Plus event-flagged windows: any in-window governance event changing kink parameters → breakpoint report; OOD USDC-depeg week (Mar 2023, from "Rules to Rewards" Aave dataset) → ablation #14.

---

## 7. Baselines (Requirement 8)

### Baseline A: Buy-and-hold Aave v3

Deposit $1M at T₀, never rebalance. Naive yield benchmark.

### Baseline B: APY-only greedy

At every hour allocate 100% to whichever protocol has highest spot APY (no hysteresis, no cooldown, no costs). Upper bound for *reactive* switching. Equivalent in spirit to simple-mode Yearn / Beefy.

### Baseline C: Reactive MCDM-with-EMA (AI Yield Vault original)

Port of Solovev (2026b) to mainnet backtest: EMA(α=0.3)-smoothed rate, MCDM with default weights, hysteresis θ=0.05, cooldown 1h. **The strawman the novelty rests on.**

### Baseline D: CIR-calibrated forecast (Orlando et al. 2020 partitioning)

Classical short-rate model: cluster historical series into utilization quintiles, fit CIR per regime, recombine. Feeds same MCDM allocator structure. Tests whether DL adds value over a regime-aware classical model.

---

## 8. Strategy Improvement Narrative (Requirement 9)

| Step | Strategy | Source | New? |
|---|---|---|---|
| 1 | APY-only greedy | Industry standard | — |
| 2 | + Risk-aware (utilization factor) | AI Yield Vault | — |
| 3 | + Cost & Stability factors (full MCDM) | AI Yield Vault | — |
| 4 | + EMA smoothing | AI Yield Vault | — |
| 5 | + Hysteresis + cooldown | AI Yield Vault | — |
| 6 | + **Mainnet historical backtest (vs Sepolia testnet)** | **This work** | ✓ |
| 7 | + **CIR-calibrated forecast replacing EMA** | **This work** (intermediate) | ✓ |
| 8 | + **DA-BiGRU-CNN dual-branch forecast with kink subtraction** | **This work** (headline) | ✓ |

Decomposed improvement claim: predictive MCDM (step 8) dominates reactive MCDM (step 5) on the metric-weighted sample distribution; the dual-branch decomposition (step 8) dominates the single-branch CIR baseline (step 7) on directional accuracy; both improvements survive realistic gas costs.

---

## 9. Metrics (Requirement 10)

### 9.1 Performance
Net APY, cumulative net PnL (USD), Sharpe (annualized daily), Calmar (APY / MaxDD).

### 9.2 Risk
Maximum drawdown, return volatility, worst-day return, rebalance frequency (per month).

### 9.3 Cost & Efficiency
Turnover, total gas spent (USD), gas as % of gross PnL, forecast hit rate (direction sign match), decision precision (% of rebalances where new protocol's realized 24h-forward avg rate > old's).

### 9.4 Forecast Quality
Out-of-sample R² per protocol (rate level), directional accuracy ("Aave > Compound at t+12h"), weighted Pearson correlation (consistency with LOB paper), quantile-90 loss.

### 9.5 Regime-Conditional
All headline metrics by low / med / high volatility tertile + full-period roll-up.

### 9.6 Statistical Significance
Sharpe-difference 1000-bootstrap of monthly Sharpe ratios (H1 test); McNemar's test on directional accuracy (H2 test).

---

## 10. Ablations (15 total)

Three core ablations mirror the three findings from Solovev (2026a) — testing whether his LOB-domain results generalize to DeFi-rate domain.

| # | Ablation | Motivation |
|---|---|---|
| 1 | **No-forecast EMA baseline** (Baseline C) | Mandatory strawman |
| 2 | **Naive last-observation forecast** | Tests whether *any* forecast > current observation |
| 3 | **CIR-calibrated forecast** (Baseline D) | Tests whether DL adds value over classical |
| 4 | **Markov-switching short-rate** (2-state on utilization) | Cheap regime-aware classical comparator |
| 5 | **CatBoost on hand-crafted features** (mirroring `examples/ml_funding_rate_forecasting/`) | In-framework house baseline; apples-to-apples |
| 6 | **Single-branch DA-GRU** (no CNN, no decomposition) | Tests value of dual-branch architecture |
| 7 | **Dual-branch *without* kink subtraction** | Tests value of the protocol-known prior |
| 8 | **Forecast with ranking-loss only** | Tests whether MSE adds value over pure direction loss |
| 9 | **MCDM equal weights vs tuned weights** | Tests where the edge sits — weights or forecast |
| 10 | **Single-protocol benchmark** (Aave-only, Compound-only) | Establishes switching matters at all |
| 11 | **Greedy max-forecasted-APY vs TOPSIS-MCDM** | Tests whether MCDM adds value over argmax-on-forecast |
| 12 | **Zero-gas vs realistic-gas** | Reports break-even gas — useful whitepaper number |
| 13 | **Sliding-window stability** (`window_size=14` 2-week windows) | Required by `DefaultPipeline`; mean / q05 / q95 / cvar05 |
| 14 | **OOD test on USDC depeg week** (Mar 2023, "Rules to Rewards" dataset) | Stress test; expectation: forecaster degrades; allocator should fall back gracefully |
| 15 | **Forecast horizon sweep (3h, 6h, 12h, 24h)** | Horizon-sensitivity ablation justifies the locked 12h choice |

**Headline figure for whitepaper title page:** ablation #1 vs main strategy. One chart, two equity curves, the entire improvement claim distilled.

---

## 11. Extra+1 and Extra+2 Contributions

### Extra+1: Compound v3 GraphQL Loader

**Status of repo:** fractal-defi v1.4.0 has only an Aave v3 GraphQL loader; **no Compound v3 loader exists**. Cleanest possible single-PR contribution, and required for the project's main strategy.

**Implementation:**
- Source: Messari subgraph for Compound v3 on Ethereum
- Endpoint entity: `Market.rates`, `marketHourlySnapshots` on cUSDCv3 (`0xc3d688B66703497DAA19211EEdff47f25384cdc3`)
- Return type: existing `LendingHistory(lending_rate, borrowing_rate)` with UTC `DatetimeIndex`
- Scaling: WAD (1e18) per-second → annualized continuous-compound APY (matching Aave loader's output convention)
- Sign convention per ARCHITECTURE.md (positive `lending_rate` ⇒ collateral grows)
- Caching: follows loader-cache pattern under `<DATA_PATH>/fractal_data/CompoundV3LendingLoader/<key>.parquet`
- Tests: real-API test in `tests/loaders/`, offline fixture test in `tests/core/`

**PR title:** *"Add Compound v3 lending history loader (Messari subgraph)"*

### Extra+2: `BaseLendingAllocationStrategy` Abstraction

**Status of repo:** `fractal/strategies/` has `BasisTrading`, `HyperliquidBasis`, `TauReset` — **no multi-lending-protocol allocator** despite four lending entities being available. The strongest Extra+2 candidate: a substantive, broadly-useful new abstraction.

```python
# fractal/strategies/lending_allocation.py

@dataclass
class BaseLendingAllocationParams(BaseStrategyParams):
    INITIAL_BALANCE          : float
    LENDING_ENTITIES         : tuple[str, ...]
    REBALANCE_COOLDOWN_HOURS : float = 1.0
    HYSTERESIS_THRESHOLD     : float = 0.05

class BaseLendingAllocationStrategy(BaseStrategy[BaseLendingAllocationParams]):
    """
    Abstract multi-lending-protocol allocator with four overridable hooks:
      1. compute_criteria_vector(entity_name) → np.ndarray of criteria
      2. aggregate_criteria(criteria_matrix)  → score per protocol
      3. select_target(scores)                → chosen entity name
      4. should_rebalance(current, target, scores) → bool
    """
    def compute_criteria_vector(self, entity_name: str) -> np.ndarray: ...
    def aggregate_criteria      (self, M:  np.ndarray)               -> np.ndarray: ...
    def select_target           (self, s:  np.ndarray)               -> str: ...
    def should_rebalance        (self, current, target, scores)      -> bool: ...
    def predict                 (self)                               -> List[ActionToTake]: ...
```

The project's `PredictiveMCDMStrategy` becomes the first concrete subclass. **PR title:** *"Add `BaseLendingAllocationStrategy` for multi-lending-protocol allocators"*.

**Optional bonus (if time):** `ForecastedLendingEntity` — `BaseLendingEntity` variant exposing both current and forecasted rate in `GlobalState`, enabling forecast-driven strategies generically while respecting ARCHITECTURE.md's "no silent dependence on environment" rule.

---

## 12. Repo Structure

```
predictive-mcdm-defi/
├── README.md
├── PROJECT_2_PLAN.md
├── LLM_TRANSCRIPT.md
├── requirements.txt
├── data/
│   ├── fetch_aave.py
│   ├── fetch_compound.py            ← also lives in fractal Extra+1 PR
│   ├── fetch_gas_eth.py
│   ├── clean.py
│   ├── features.py                  ← kink subtraction
│   └── cached/
├── forecaster/
│   ├── model.py                     ← DualBranchKinkSubtractionForecaster
│   ├── losses.py                    ← MSE + WPearson + Quantile
│   ├── train.py
│   ├── baseline_cir.py              ← Orlando 2020 partitioning
│   ├── baseline_markov.py
│   ├── baseline_catboost.py         ← mirrors ml_funding_rate_forecasting
│   ├── export_onnx.py
│   └── trained_models/
├── strategies/
│   ├── baseline_buyhold.py
│   ├── baseline_apy_greedy.py
│   ├── baseline_mcdm_ema.py         ← port of AI Yield Vault
│   ├── baseline_mcdm_cir.py
│   └── predictive_mcdm.py           ← main
├── backtest/
│   ├── run_baselines.py
│   ├── run_main.py
│   ├── run_ablations.py
│   └── grid_search.py
├── notebooks/
│   ├── 01_data_exploration.ipynb
│   ├── 02_kink_calibration.ipynb
│   ├── 03_forecaster_training.ipynb
│   ├── 04_main_backtest.ipynb
│   ├── 05_ablations_forecast_value.ipynb
│   ├── 06_ablations_architecture.ipynb
│   ├── 07_ablations_mcdm.ipynb
│   ├── 08_regime_analysis.ipynb
│   └── 09_ood_depeg_test.ipynb
├── results/
│   ├── mlflow/
│   ├── figures/
│   └── tables/
├── whitepaper/
│   ├── main.tex
│   ├── refs.bib                     ← citation handoff from research report
│   ├── figures/                     ← symlink to ../results/figures
│   └── main.pdf
├── tests/
│   ├── test_strategy_logic.py
│   ├── test_forecaster_numerical.py
│   ├── test_data_pipeline.py
│   └── test_sign_convention.py
└── extras/
    ├── fractal_pr_compound_loader/
    └── fractal_pr_lending_allocation/
```

---

## 13. Timeline (4 weeks, starting 18 May 2026)

### Week 1 (18–24 May): Data + Forecaster Foundation

| Day | Deliverable |
|---|---|
| Mon 18 | Aave v3 subgraph queries, Dune fallback, parquet cache |
| Tue 19 | Compound v3 Messari loader (Extra+1 PR work begins in parallel) |
| Wed 20 | Gas + ETH price aux fetchers; full feature pipeline; data-audit notebook |
| Thu 21 | Kink-parameter extraction from on-chain config events; rate-residual computation |
| Fri 22 | `DualBranchKinkSubtractionForecaster` architecture implemented |
| Sat 23 | Composite loss + training loop with MLflow |
| Sun 24 | First end-to-end training run on train + val |

**Week 1 deliverable:** trained forecaster (ONNX exported), validation weighted Pearson and direction accuracy logged, EDA notebook complete.

### Week 2 (25–31 May): Strategy + Initial Backtest

| Day | Deliverable |
|---|---|
| Mon 25 | `BaseLendingAllocationStrategy` abstraction (Extra+2 begins) |
| Tue 26 | Baselines A, B (buy-hold, APY-greedy) |
| Wed 27 | Baseline C (MCDM-EMA) — port from AI Yield Vault Solidity → Python |
| Thu 28 | Baseline D (CIR + MCDM) |
| Fri 29 | `PredictiveMCDMStrategy` end-to-end on validation period |
| Sat 30 | Debug edge cases; transaction-cost model verification |
| Sun 31 | All five strategies running cleanly on validation period |

**Week 2 deliverable:** five-strategy backtest pipeline functional, validation results logged.

### Week 3 (1–7 June): Calibration + Ablations + Test-Set Run

| Day | Deliverable |
|---|---|
| Mon 1 | MLflow grid search for strategy hyperparameters |
| Tue 2 | Ablations 1–5 (forecast variants vs EMA) |
| Wed 3 | Ablations 6–8 (architecture variants — single-branch, no-kink, ranking-loss-only) |
| Thu 4 | Ablations 9–11 (MCDM variants — equal weights, single-protocol, greedy-vs-MCDM) |
| Fri 5 | Ablations 12–13 (gas sensitivity, sliding-window stability) |
| Sat 6 | Ablation 14 (OOD USDC-depeg stress test) + Ablation 15 (horizon sweep) |
| Sun 7 | All regime analysis + figures + tables generated |

**Week 3 deliverable:** complete results on held-out test set, all 15 ablations, regime breakdown, statistical-significance tests.

### Week 4 (8–14 June): Whitepaper + Extras + Defense

| Day | Deliverable |
|---|---|
| Mon 8 | Whitepaper §1–4 (Problem, Background, Related Work, Architecture) |
| Tue 9 | Whitepaper §5–7 (Methodology, Data, Calibration) |
| Wed 10 | Whitepaper §8–9 (Results, Ablations) |
| Thu 11 | Whitepaper §10–12 (Discussion, Limitations, Conclusion) + bib polish |
| Fri 12 | Extra+1 PR finalized & submitted (Compound v3 loader) |
| Sat 13 | Extra+2 PR finalized & submitted (`BaseLendingAllocationStrategy`) |
| Sun 14 | Defense slides, README polish, LLM_TRANSCRIPT.md organized |

**Week 4 deliverable:** PDF whitepaper, public repo, two PRs submitted to fractal-defi, defense slides ready.

---

## 14. Risk Register

| # | Risk | Probability | Impact | Mitigation |
|---|---|---|---|---|
| 1 | Dune rate limits on bulk historical query | Med | Med | Chunk by month; fallback to subgraph pagination |
| 2 | Sign-convention bug (fractal v<1.4.0) | Low | High | Pin v1.4.0+; lock-in test asserts `borrowing_rate ≥ lending_rate` |
| 3 | Forecast has zero edge over EMA (H0 holds) | Low-Med | High | **Honest negative result is publishable** — methodological transfer falsified; baselines + ablations stand |
| 4 | Compound v3 subgraph inconsistency | Low | Med | Verify data quality Week 1 Day 2; cross-check vs on-chain `Comet.totalsBasic()` |
| 5 | Overfitting due to small dataset (~7k train obs) | Med | Med | Strong regularization, walk-forward CV, conservative ~50k-param architecture |
| 6 | Forecast leakage via subgraph aggregation | Low | High | Strict `block_number` filter on splits, not timestamp |
| 7 | Governance change shifting kink mid-test | Med | Med | Pull historical kink params from on-chain events; include as features |
| 8 | Regime confounding from CeFi events | Low (in-window) | Med | Report pre/post-event separately if any in-window event occurs |
| 9 | Cointegration-driven non-stationarity in Aave-Compound spread | Med | Med | Report rolling Sharpe by quarter, not just full-window |
| 10 | Gas-cost regime variance dominates forecast edge | Med | Med | Test on $1M+ size; ablation 12 reports break-even gas |
| 11 | Execution-bridge non-atomicity ~12s | Low | Low | Modeled in backtest as ~12s zero-yield on migrating notional |
| 12 | Reserve-factor changes mid-test | Low | Med | Use `liquidityRate` directly, do not recompute |
| 13 | Single-calendar-window overfitting | Med | Med | OOD validation on "Rules to Rewards" 2021–2023 dataset (ablation 14) |
| 14 | Compound WAD vs Aave RAY mis-normalization | Low | High | Loader emits both rates in identical units; unit test |
| 15 | Fractal API changes between v1.4.0 and project end | Low | Low | Pin exact version in `requirements.txt` |
| 16 | Conference 17 May affects Week 1 productivity | High | Low | Week 1 starts 18 May; structurally accepted |
| 17 | Project 2 collides with Mosoblbank termination mid-June | High | Med | Weeks 1–3 done by June 7; Week 4 is whitepaper + extras, lower cognitive load |
| 18 | TheGraph API key rate limit during bulk fetch | Med | Low | Built-in pagination + caching of fractal loader |

---

## 15. Requirements Mapping (15 items from task PDF)

| Req | Section / Artifact |
|---|---|
| 1 — Problem statement | §1 of this plan; §1 of whitepaper |
| 2 — Formal description | §2; whitepaper §3–4 |
| 3 — Pseudocode | §3; whitepaper §4 algorithm box |
| 4 — Data description | §4; whitepaper §5 |
| 5 — Calibration | §5; whitepaper §6 |
| 6 — Backtesting protocol | §6; whitepaper §7 |
| 7 — Implementation in fractal-defi | `strategies/`, `backtest/`; whitepaper §7 |
| 8 — Baselines | §7; whitepaper §8 (four baselines) |
| 9 — Strategy improvement narrative | §8; whitepaper §8 |
| 10 — Metrics + plots | §9; whitepaper §9 |
| 11 — References | research report citation handoff → `whitepaper/refs.bib` |
| 12 — Uses fractal-defi | yes, v1.4.0+, with own subclasses |
| 13 — Extra+1 verified PR | §11.1; Compound v3 GraphQL loader |
| 14 — Extra+2 significant contribution | §11.2; `BaseLendingAllocationStrategy` abstraction |
| 15 — LLM transparency | `LLM_TRANSCRIPT.md` with full chat including this planning session |

---

## 16. Research Questions and Hypotheses (Sharpened)

### Primary

**RQ1.** Does replacing the reactive EMA-smoothed supply-rate observation with a 12-hour-ahead DA-BiGRU-CNN forecast in a TOPSIS-style MCDM allocator across Aave v3 and Compound v3 USDC markets produce a statistically and economically significant improvement in risk-adjusted yield, after gas and slippage costs, over a 4-month out-of-sample test period (Jan–Apr 2026)?

**H1.** Forecast-driven MCDM allocation increases Sharpe ratio by ≥ 0.2 vs the reactive EMA baseline over the test window, with significance via 1000-bootstrap of monthly Sharpe ratios.

### Secondary

**RQ2.** Which architectural decomposition — single-branch on rates, dual-branch on (rate, utilization), or dual-branch with the protocol-known kink subtracted from the rate branch — yields the most accurate and most allocation-relevant forecast under a directional, asymmetric, ranking-oriented composite loss?

**H2.** The dual-branch-with-kink decomposition outperforms a single-branch forecaster on out-of-sample direction accuracy by ≥ 3 percentage points, with significance via McNemar's test.

### Tertiary

**RQ3.** To what extent is the forecast-driven allocator's outperformance attributable to (a) the forecast itself, (b) the MCDM criterion structure independent of forecast, or (c) the specific protocol-pair selection? Addressed by ablations 1, 9, and 10 respectively.

### Null

**H0.** A 12-hour forecast adds no value over EMA observation — on this horizon the rate process behaves as a martingale conditional on observed utilization, and the protocol's deterministic kink function fully explains predictable variation.

**H0 is explicitly entertained.** Given the cointegration finding in Gudgeon et al. (2020) and the high efficiency of mature DeFi rate markets, H0 cannot be ruled out a priori. If the data support H0, the project still contributes: (i) first rigorous backtest of MCDM-with-EMA on mainnet historicals validating Solovev 2026b on real data, (ii) falsification of methodological transfer from LOB to lending rates is itself a publishable result, (iii) Extra+1 and Extra+2 fractal-defi contributions stand on their own merits.

---

## 17. Bridge to Conference Talk (17 May 2026)

This plan is finalized in the days preceding the author's "Scientific Telegraph" conference presentation of the DA-BiGRU-CNN paper at Central University, Moscow. The final 2–3 minutes of that 10-minute talk explicitly point to this project as the live execution of the Section 6.4 transfer claim from the LOB paper. The whitepaper's introduction reciprocates with a footnote:

> *"This work realizes the methodological transfer outlined in Section 6.4 of Solovev (2026a) and previewed at the Scientific Telegraph Young Researcher Conference, Central University, Moscow, May 17 2026."*

Closing the loop publicly turns the project from coursework into the execution panel of a stated research program — the strongest defensible framing available.

---

## 18. Connection to the Vega Institute / HSE / Skoltech `fractal-defi` Research Program

This project is positioned as the **lending panel** of a three-microstructure research program on the `fractal-defi` substrate:

| Microstructure | Paper | Year | What is learned |
|---|---|---|---|
| Concentrated-liquidity AMM | Urusov, Berezovskiy, Yanovich (arXiv:2410.09983) | 2024 | Backtester reconstruction |
| CLMM with dynamic LP | Urusov, Berezovskiy, Krestenko, Kornilov, Yanovich (arXiv:2505.15338) | 2025–26 | Strategy *parameters* tuned by ML across regimes |
| Spot–perpetual basis | Krestenko, Butov, Berezovskiy, Bolotin (arXiv:2605.05089) | 2026 | Control problem under funding dominance |
| **Lending (this work)** | Solovev (forthcoming) | 2026 | **State variable (rate) forecasted by DL; allocator analytical** |

Each prior paper learns or controls a different aspect of its microstructure; this project completes the matrix by learning the state itself rather than the controller, on a microstructure (lending rates) the prior papers explicitly leave unaddressed.

The whitepaper's strongest single citation framing (per research report §III.C):

> *"Krestenko et al. (2026) demonstrate that for spot–perpetual basis trading on-chain, realized performance under fixed collateral control is dominated by the funding environment, implying that a learned funding forecast would be first-order valuable. We make the analogous argument for two-protocol lending allocation: under fixed reactive-EMA control, realized performance is dominated by the supply-rate environment, and we therefore replace the reactive observation with a learned 12-hour-ahead forecast. This positions the present work as the lending counterpart to the basis-trading control problem, both within the fractal-defi framework's typed entity-strategy abstraction."*

---

## Closing Discipline Note

The locked scope is defensible exactly as stated against all prior art surveyed in the deep research report. The three most likely reviewer concerns and pre-emptive responses:

1. **"Is 12-hour rate predictability genuinely there?"** — Cointegration with Compound-leading-Aave (Gudgeon et al. 2020) provides structural reason; AgileRate (2024) demonstrates 3-hour-resolution control feasibility on Compound, implying 12-hour forecasting has at least as much signal.

2. **"Why not Morpho, Spark, or cross-chain?"** — Explicit scope-locking; cross-chain dilutes execution-risk profile; Morpho integration listed as future work.

3. **"What is the novelty vs the author's own ERC-4626 paper?"** — (i) Forecast head is net-new methodologically and absent from the original; (ii) Dual-branch with kink subtraction is a genuine architectural contribution beyond either prior paper individually; (iii) Mainnet historical backtest (vs Sepolia testnet); (iv) Two fractal-defi contributions (Extra+1, Extra+2) of independent utility.

**Plan locked. Execution begins 18 May 2026.**
