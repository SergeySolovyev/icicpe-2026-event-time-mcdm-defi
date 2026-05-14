# Deep Research Report: Predictive MCDM Allocation Across Aave v3 and Compound v3 — Whitepaper Enrichment

---

## I. Executive Summary

This report enriches a Master's-level project at HSE / WorldQuant whose locked scope is a **predictive Multi-Criteria Decision Making (MCDM) allocator** for USDC supply yield across **Aave v3** and **Compound v3**, built on the `fractal-defi` framework (Logarithm-Labs, v1.3.2, released May 6 2026, DOI 10.5281/zenodo.20049904). The novel contribution — replacing the reactive EMA-smoothed rate observation with a short-horizon learned forecast inspired by the author's prior DA-BiGRU-CNN limit-order-book work — is defensible and structurally under-explored in the literature. Six headline findings:

1. **The DeFi lending-rate forecasting niche is genuinely empty.** The closest 2022–2026 academic work treats DeFi rates either as (a) the *output* of a learned controller to be designed (AgileRate 2024 arXiv:2410.13105; Auto.gov 2023 arXiv:2302.09551; "From Rules to Rewards" 2025 arXiv:2506.00505) or (b) as an *equilibrium variable* in cointegration analysis (Gudgeon et al. 2020 arXiv:2006.13922). No published paper applies a deep-learning *forecaster* to Aave/Compound supply rates for downstream multi-protocol allocation. The closest analogue inside fractal-defi itself is `examples/ml_funding_rate_forecasting/` — a CatBoost pipeline for Binance funding rates — which is structurally the same problem class and provides the in-framework pipeline template to mirror.

2. **The three instructor-provided baseline papers are entirely AMM/perp-microstructure; none addresses lending.** Urusov–Berezovskiy–Yanovich (2024, arXiv:2410.09983) and Urusov–Berezovskiy–Krestenko–Kornilov–Yanovich (2025 v1 / 2026 v2, arXiv:2505.15338) target Concentrated Liquidity Market Makers on Uniswap v3. Krestenko–Butov–Berezovskiy–Bolotin (2026, arXiv:2605.05089) targets spot-perpetual basis trading on permissionless venues. The project therefore complements — does not compete with — this Vega Institute / HSE / Skoltech research line by extending the same fractal-defi infrastructure to a third on-chain microstructure: utilization-driven lending rates.

3. **Concrete fractal-defi extension points exist.** The repo ships `BaseLendingEntity`, a concrete `AaveEntity`, an Aave V3 GraphQL loader (with a sign-flip bug fixed in v1.4.0), and `LendingHistory` as a typed loader return struct. There is **no Compound v3 loader and no forecast-enabled lending entity** — both are credible Extra+1 / Extra+2 PR opportunities. The `examples/ml_funding_rate_forecasting/` pipeline is the structural prototype to mimic.

4. **Honest forecast-quality expectation.** DeFi supply rates are deterministic functions of utilization (kinked piecewise-linear curves in Aave v3 / Compound v3), so prediction is effectively a utilization-and-regime-shift forecast. At the 12-hour horizon, autocorrelation from supply/borrow inertia is informative but exogenous shocks (e.g., March-2023 DAI utilization spike on Aave) cap achievable R². A realistic out-of-sample R² target is **0.15 – 0.40**, based on TradFi short-rate ML benchmarks (Orlando–Mininni–Bufalo 2020; Nunes et al. 2026 LSTM-LagLasso) and on the funding-rate analogue inside fractal-defi.

5. **The dual-branch (price/volume → rate/utilization) transposition is conceptually sound** but requires re-justification — utilization is bounded in [0,1] and structurally clamped at the kink, qualitatively different from unbounded LOB volume. The architectural skeleton (BiGRU + CNN per branch + late fusion) carries over; the branching semantic should be *(rate-residual-after-kink) × (utilization)* rather than directly *(price) × (volume)*.

6. **Strategic positioning.** The strongest rhetorical move available in the whitepaper is to explicitly cast the project as the "lending panel" of a Vega-Institute / HSE / Skoltech triptych across on-chain microstructures: CLMM (Uniswap v3 — Urusov 2024/2025) → perp-basis (permissionless venues — Krestenko 2026) → lending (Aave/Compound v3 — this work), all on the same `fractal-defi` substrate.

---

## II. Related Work (whitepaper Section 3 source material)

### II.A — DeFi Yield Optimization and Multi-Protocol Allocation

**Industry systems.** Yearn Finance (Cronje 2020 onwards) pioneered automated yield aggregation; its yvUSDC vault historically allocated across Aave, Compound, and Curve via off-chain strategy proposals voted by YFI holders — *not* an explicit learned forecast. Beefy Finance scales the same auto-compounding pattern across 25+ chains but is fundamentally rate-reactive. Idle Finance offers two allocation modes — Best-Yield (greedy rate-max) and Risk-Adjusted (multi-protocol distribution) — the closest existing system to a multi-criteria allocator, though without published MCDM formalism. Almanak, Sommelier, Harvest 2.0 and other agentic platforms increasingly use ML-based allocators but rarely publish methodology. **None of these systems publishes a forecast-driven multi-protocol allocator in academic form.**

**Academic / preprint work directly on DeFi lending.**

- **Gudgeon, Perez, Harz, Livshits, Gervais (2020). *DeFi Protocols for Loanable Funds: Interest Rates, Liquidity and Market Efficiency.* arXiv:2006.13922.** Empirical examination of Compound, Aave, dYdX interest-rate rules; Johansen multiple-trace cointegration test finds at most two cointegrating relationships across the three. Compound and dYdX share a long-run relationship; Aave and dYdX share a long-run relationship. Critically: Aave adjusts faster (speed of adjustment 0.607) than dYdX (0.115); a shock to Compound's USDC borrowing rate has a permanent effect on Aave's. *Relevance:* the structural premise — that an Aave–Compound spread exists, is mean-reverting, and is led by Compound — is exactly what justifies a switching allocator at all.

- **"From Rules to Rewards: Reinforcement Learning for Interest Rate Adjustment in DeFi Lending" (2025). arXiv:2506.00505.** Trains a TD3-BC offline RL agent to *adjust* Aave v2/v3 borrow rates on a Mar 2021–Feb 2025 daily Ethereum dataset (the most complete public Aave dataset to date; full pre-processing in their Appendix C). Reports smoother, more granular rate adjustment vs Aave's step-like kinked function. *Relevance:* validates DL methods work end-to-end on Aave rate data; their dataset construction is replicable. Orthogonal contribution: they propose the controller, we propose the forecaster feeding a separate analytical allocator.

- **AgileRate: Bringing Adaptivity and Robustness to DeFi Lending Markets (2024). arXiv:2410.13105.** Recursive least squares (RLS)-based adaptive controller fitted on Compound demand/supply curves at 3-hour intervals from Feb 2024–Feb 2025. *Relevance:* validates 3-hour resolution as informative for DeFi rates and provides the most directly reproducible Compound dataset; the project's 12-hour horizon is conservative against this benchmark.

- **Xu, Vadgama et al. (2023). Auto.gov: Learning-based Governance for DeFi. arXiv:2302.09551.** RL agent for parameter governance in Aave-like protocols; reports 14% outperformance over benchmarks and ~10× over static. *Relevance:* establishes the on-chain-RL plausibility envelope; their state-action encoding is reusable scaffolding.

- **"Automated Risk Management Mechanisms in DeFi Lending Protocols: A Crosschain Comparative Analysis of Aave and Compound" (2025). arXiv:2506.12855.** Empirical TVL / total reserves study of Aave and Compound v2 vs v3 across chains. *Relevance:* quantifies that v3 protocols have more frequent but better-managed liquidations and confirms 2024–2026 USDC market characteristics are stable enough to backtest meaningfully.

- **Bertomeu, Martin, Sall (2024). *Measuring DeFi risk.* Finance Research Letters 63C.** General DeFi risk taxonomy useful for the risk register section.

**Open-source implementations.** There is no widely-used public GitHub repository implementing a DL forecaster for Aave/Compound supply rates. CryptoRLPM (multi-asset crypto RL portfolio manager, Jiang et al. 2017 lineage) is the closest open-source RL analogue but operates on prices, not lending rates. The fractal-defi `examples/ml_funding_rate_forecasting/` is the only in-framework open-source ML-rate pipeline available.

**Gap explicitly identified.** No paper combines (a) a deep-learning supply-rate forecaster with (b) an MCDM allocator across (c) two specific on-chain lending markets. This is the project's claimable novelty.

### II.B — Machine Learning for Interest-Rate Forecasting (TradFi → DeFi transfer)

**TradFi short-rate ML and classical baselines.**

- **Vasicek, O. (1977). *An equilibrium characterization of the term structure.* Journal of Financial Economics 5(2):177–188.** Ornstein-Uhlenbeck short-rate model. *DeFi applicability:* structurally inappropriate as the headline because Vasicek allows negative rates (impossible by smart-contract enforcement). Use only as a calibration sanity-check.

- **Cox, J. C., Ingersoll Jr., J. E., Ross, S. A. (1985). *A Theory of the Term Structure of Interest Rates.* Econometrica 53(2):385–408.** CIR √r diffusion. *DeFi applicability:* better than Vasicek because the √r term enforces non-negativity, but it still assumes pure Brownian stochasticity and misses the deterministic kink in Aave/Compound v3 — useful as a baseline forecaster (one of three), not as a centerpiece.

- **Hull, J., White, A. (1990). *Pricing interest-rate-derivative securities.* Review of Financial Studies 3(4).** Extension of Vasicek with time-dependent drift for fit to initial term structure. *DeFi applicability:* limited — DeFi has no "term structure" in the same sense (no maturity curve), so the time-dependent-drift machinery does not transfer cleanly.

- **Orlando, Mininni, Bufalo (2020). *Forecasting interest rates through Vasicek and CIR models: a partitioning approach.* Journal of Forecasting 39(4):569–579. (arXiv:1901.02246).** Shows that classical one-factor mean-reverting models retain forecast skill when augmented with regime partitioning (cluster the historical series into low/mid/high-rate regimes, fit CIR per regime, recombine). *Relevance:* directly motivates a regime-aware utilization head in the project, and is the right reference for the "classical baseline beaten by ML" framing.

- **Nunes et al. (2026). *Deep Learning for Bond Yield Forecasting: The LSTM-LagLasso.* International Journal of Finance & Economics (Wiley) doi 10.1002/ijfe.3116.** Four-step LSTM + LagLasso for sovereign bond yields, with explainability via Lasso regression on internal LSTM signals. Empirically supports LSTM over GRU for *long*-term dependency capture (citing Fischer & Krauss 2018), though for short-horizon work the simpler-architecture GRU is competitive. *Relevance:* template for combining DL forecasts with interpretable post-hoc analysis; LSTM-LagLasso reports in-sample R² 0.4–0.6 and out-of-sample ~0.2 for 1-month sovereign yields — a useful empirical anchor for the project's expected R² range.

**Stochastic-volatility and regime-switching extensions** (queried explicitly in scope).

- **Heston (1993)** stochastic volatility — relevant as an option-pricing benchmark but unsuited to short-rate without modification. Not applicable directly.

- **Chen, L. (1996)** extended-CIR with stochastic mean and stochastic volatility ("Chen model"). *DeFi applicability:* the rate volatility *is* clearly state-dependent in Aave/Compound (rate volatility spikes during utilization-near-100% episodes), so a Chen-style stochastic-vol extension is the right classical model to cite, even if not implemented as a baseline. Worth a footnote.

- **Hamilton (1989) regime-switching** and modern Markov-switching ARMA / GARCH variants. *DeFi applicability:* high — the empirical AgileRate series shows clear regime breaks. A Markov-switching baseline (2 or 3 regimes calibrated on utilization-quantile cuts) is a strong simple comparator and adds little engineering cost.

- **Smith, Naik, Tsai (2006)** Markov-modulated short-rate models — bridges CIR with regime switching; the right citation if the project explicitly compares regime-switching CIR to the DA-BiGRU-CNN.

**LOB / microstructure DL** (the author's home territory; included for the architectural backbone reused here).

- The author's own prior paper: **"When Less Is More: Domain-Aware Dual-Branch Recurrent Networks for Limit Order Book Mid-Price Prediction" (DA-BiGRU-CNN).** The architectural backbone reused in this project.
- **Sirignano, J. (2016). *Deep Learning for Limit Order Books.* arXiv:1601.01987.** Foundational MLP-on-LOB; establishes deep architectures can outperform classical Cont–Stoikov stochastic LOB models.
- **Wallbridge, J. et al. (2020). *Transformers for Limit Order Books.* arXiv:2003.00130.** Causal-CNN + masked-self-attention; demonstrates Transformer-on-LOB but on the large FI-2010 dataset (~10^6 events). The project's smaller dataset argues *against* Transformers as headline.
- **Mäkinen, M., Kanniainen, J., Gabbouj, M., Iosifidis, A. (2018). *Forecasting of Jump Arrivals in Stock Prices using LOB Data.* arXiv:1810.10845.** CNN + LSTM + attention for jump arrivals — relevant precedent for the *anomaly head* in any dual-head extension.
- **Wu, Mahfouz, Magazzeni, Veloso (2021). *Towards Robust Representation of Limit Orders Books for Deep Learning Models.* arXiv:2110.05479.** JP Morgan AI Research; representation-design lessons.

### II.C — Domain Decomposition / Dual-Branch Architectures in Time Series

- **Simonyan, K., Zisserman, A. (2014). *Two-Stream Convolutional Networks for Action Recognition in Videos.* NeurIPS 2014.** Foundational two-stream architecture: a spatial-RGB branch and an optical-flow temporal branch with late fusion. *The conceptual ancestor of the author's DA-BiGRU-CNN.* The justification — that the two streams encode physically distinct generative processes — is the exact argument that needs re-instantiation for the DeFi case.

- **Feichtenhofer, Pinz, Zisserman (2016). *Convolutional Two-Stream Network Fusion for Video Action Recognition.* CVPR.** Refinement showing fusion topology matters more than stream depth. *Relevance:* informs choice of late vs early fusion in the dual-branch lending forecaster.

- **Multi-branch Transformer variants for time series.** Recent works such as **Crossformer (Zhang & Yan, ICLR 2023)** and **PatchTST (Nie et al., ICLR 2023)** instantiate two-stage attention (cross-time + cross-variate). *Relevance:* if the project ever scales beyond two protocols / two features, these are the right architectures to consider; for the current 2-protocol scope, BiGRU + CNN with late fusion is the right complexity tier.

- **Explainable Dual LSTM-Autoencoders with Exogenous Features (review in PMC 12661012, 2025).** Dual-head LSTM where one head forecasts the target and the other detects anomalies via autoencoder reconstruction error. *Relevance:* a directly transferable template — utilization-spike detection is naturally a second head in this project, even though the headline contribution focuses on the forecast head only.

- **BiLSTM + NARX (review in the same PMC piece).** Integration of bidirectional LSTM output to a dynamic NARX regressor for combining internal temporal patterns with exogenous stimuli. *Relevance:* structural sibling of the proposed rate-residual + utilization branches feeding a fused decoder.

### II.D — MCDM in Financial Allocation

- **Hwang, C. L., Yoon, K. (1981). *Multiple Attribute Decision Making: Methods and Applications.* Springer.** Original TOPSIS formulation.
- **Saaty, T. L. (1980). *The Analytic Hierarchy Process.* McGraw-Hill.** AHP foundations.
- **Brans, J. P., Vincke, P. (1985). *A Preference Ranking Organisation Method (PROMETHEE).* Management Science 31(6).** PROMETHEE foundations.

- **Aljinović, Z., Marasović, B., Šestanović, T. (2021). *Cryptocurrency Portfolio Selection — A Multicriteria Approach.* Mathematics 9(14):1677 (MDPI).** PROMETHEE II on nine cryptos with seven criteria (return, std dev, VaR, CVaR, volume, market cap, attractiveness) over Jan 2017–Feb 2020, computing 32 monthly optimal portfolios. *Relevance:* establishes the MCDM-in-crypto precedent; the project's criteria (forecasted APY, utilization headroom, TVL safety, protocol risk score) is a direct DeFi-flavored adaptation with one fewer dimension.

- **Hosseinzadeh, Sarpoolaki, Hosseinzadeh (2023). *An asymmetric PROMETHEE II for cryptocurrency portfolio allocation based on return prediction.* Computers & Operations Research, ScienceDirect S156849462200878X.** *The most structurally similar prior art.* Combines return *prediction* with PROMETHEE; the project performs the analogous "forecast → MCDM" pipeline one layer deeper (lending-rate prediction + protocol allocation). This is the most important paper to cite head-to-head.

- **Babaei, Bamdad et al. (2023). CLUS-MCDA II for cryptocurrency portfolio.** Omega 115, ScienceDirect S0305048322001943. Extension of CLUS-MCDA with DBSCAN + VIKOR + Prophet forecasting on >70 cryptocurrencies. *Relevance:* over-engineered for two-protocol scope but worth citing as the maximal-MCDM-DeFi comparator.

- **TOPSIS + ARAS + GP + GA hybrid.** Scientific Reports 15 (Nature, 2025) doi 10.1038/s41598-025-17604-y. Multi-criteria + optimization stacking. *Relevance:* shows the maximalist end of MCDM-portfolio integration. The project should explicitly state it stops at TOPSIS (the author's prior choice) on parsimony grounds.

- The author's own prior work: **"AI-Managed ERC-4626 Yield Vault with Multi-Criteria Decision Making: Design, Implementation, and Formal Verification."** Provides the on-chain MCDM allocator that this project extends with a forecast input. The key methodological extension claim is: "MCDM-with-EMA → MCDM-with-DL-forecast."

---

## III. Positioning vs the Three Instructor Baseline Papers

### III.A — Urusov, Berezovskiy, Yanovich (2024), arXiv:2410.09983 — "Backtesting Framework for Concentrated Liquidity Market Makers on Uniswap V3"

**Methodology.** Parametric reconstruction of historical liquidity distribution from swap-event data (no liquidity-snapshot dependency). The backtester estimates rewards by approximating the liquidity curve at each point in time; reported reward-modeling error <1% across 2023 Uniswap v3 USDC/ETH, stablecoin, and altcoin pools. GPU-accelerated.

**Data used.** Swap-event data from Uniswap v3 subgraph for pools at multiple fee tiers, 2023 calendar year.

**Metrics.** Reward-approximation error vs realized pool fees; pool-by-pool error percentages.

**What it does well.** Solves the historical-state-reconstruction problem for CLMMs, which had been the binding obstacle to academic AMM backtesting. Methodologically rigorous parametric approximation.

**What it leaves unaddressed.** Pure backtester — no allocation logic, no forecasting, no multi-pool decisions; confined to AMM fee revenue; lending markets entirely out of scope.

**Complementarity framing.** The current project provides the lending-microstructure counterpart. It reconstructs supply-rate dynamics from on-chain rate/utilization events (a *simpler* reconstruction problem because Aave/Compound expose `liquidityIndex` and `supplyIndex` directly, so we inherit the state for free) and adds the layer this paper deliberately omits — an active *strategy*.

### III.B — Urusov, Berezovskiy, Krestenko, Kornilov, Yanovich (2025 v1 / 2026 v2), arXiv:2505.15338 — "Dynamic Liquidity Provision in Decentralized Markets"

**Methodology.** Builds on III.A's parametric reconstruction (here reporting ~2% approximation error). Evaluates τ-reset strategies — dynamic liquidity reallocation in response to price moves — across multiple Uniswap v3 pools. Uses machine learning to optimize strategy *parameters* (the τ thresholds) by market regime. Reports **13–23% fee outperformance vs uniform allocation benchmarks**.

**Data used.** Historical Uniswap v3 swap data for WETH/USD pools on Base chain across Uniswap, Aerodrome, PancakeSwap, SushiSwap (per the citation in the WETH/USD CLMM paper that builds on this work).

**Metrics.** Realized fee revenue vs uniform-allocation baseline; impermanent loss decomposition; asymmetric-strategy capital-preservation analysis.

**Baseline.** Uniform allocation (passive full-range liquidity provision).

**What it does well.** First published academic application of ML-tuned dynamic LP strategy in fractal-defi family; clean separation between reconstruction, strategy, and parameter learning; honest treatment of impermanent loss as dominant risk factor.

**What it leaves unaddressed.** Strategy parameters are *tuned*, not the underlying market variable *forecasted*. The ML role is hyperparameter selection across market regimes, not state prediction.

**Complementarity framing.** The project moves one rung up the abstraction ladder: instead of learning *parameters* of a reactive strategy, it learns to *predict the state variable* (rate) that drives allocation, leaving the allocator analytical (TOPSIS-style MCDM). Direct concept mapping:

| Urusov et al. (2025) | This project |
|---|---|
| τ (rebalance threshold) | MCDM weights + rebalance trigger |
| Realized fee revenue | Supply APY |
| Impermanent loss | Slippage + gas cost on rebalance |
| Price (the driving state) | Utilization rate (the driving state) |
| ML *tunes* a reactive controller | ML *forecasts* the state directly |

**Citation framing for whitepaper:** *"Whereas Urusov et al. (2025) treat liquidity-provision strategy parameters as the learnable object given observed prices, we treat the rate process itself as the learnable forecast, leaving the allocator analytical. This is the same family of decisions across a structurally complementary on-chain microstructure."*

### III.C — Krestenko, Butov, Berezovskiy, Bolotin (2026), arXiv:2605.05089 — "Dynamic Collateral Control for Permissionless Spot Perpetual Basis Trading"

**Methodology.** Three-part contribution. (1) Static control problem for the collateral share between spot inventory and derivative margin, showing a risk-constrained formulation is more robust than the economic optimum; in comparative calibration, required collateral rises monotonically under volatility stress, lowest for BTC and highest for long-tail assets (LINK, DOGE). (2) Asymmetric dynamic extension: solvency-driven lower boundary, carry-loss-vs-rebalancing-cost upper boundary; Monte Carlo shows the lower boundary is structurally relevant, while meaningful interior upper triggers survive mainly under high-carry / low-cost regimes. (3) Execution-aware implementation with live routed execution and historical backtests showing realized wedges are significant and worse on the basis-sell side, justifying a minimum effective rebalancing size and a positive execution buffer.

**Data used.** Live routed execution traces plus historical backtests on perpetual venues; assets include BTC, ETH, LINK, DOGE.

**Metrics.** Realized vs theoretical wedge; carry-loss; rebalance frequency; Monte Carlo survival of boundaries.

**Baselines.** Static economic-optimum collateral share; fixed control rule.

**What it does well.** Mathematically elegant control-theoretic framing; clean separation of static vs dynamic problems; rigorous on execution costs; directly authored by `fractal-defi`'s lead contributor (Anatoly Krestenko, the framework's first author per CITATION.cff). The paper *demonstrates* the in-framework methodology pattern that this project should follow.

**What it leaves unaddressed.** The paper's key empirical finding — that under a fixed control rule, realized performance is **predominantly explained by the funding environment** — implies a learned funding forecast would have first-order P&L impact. *But the paper does not build one.* The fractal-defi `examples/ml_funding_rate_forecasting/` directory (CatBoost on Binance funding) is the un-academic-paper'd companion piece.

**Complementarity framing — the strongest single citation for the whitepaper:**

> *"Krestenko et al. (2026) demonstrate that for spot–perpetual basis trading on-chain, realized performance under fixed collateral control is dominated by the funding environment, implying that a learned funding forecast would be first-order valuable. We make the analogous argument for two-protocol lending allocation: under fixed reactive-EMA control, realized performance is dominated by the supply-rate environment, and we therefore replace the reactive observation with a learned 12-hour-ahead forecast. This positions the present work as the lending counterpart to the basis-trading control problem, both within the fractal-defi framework's typed entity-strategy abstraction."*

---

## IV. Fractal-defi Technical Deep Dive

(Source: `README.md` and `ARCHITECTURE.md`, version 1.3.2, latest commit `612aa0635f`, May 6 2026; 32 commits, 40 stars, 11 forks, 14 open issues, 7 open PRs at time of report.)

### IV.A — Repository structure

```
fractal/
├── core/
│   ├── base/           # Entity / Strategy / Observation contracts
│   ├── entities/       # Aave, Hyperliquid, Uniswap V2/V3, stETH, simple/*
│   └── pipeline.py     # MLflow grid-search pipelines
├── loaders/            # Binance / Hyperliquid / Aave (GraphQL) / GMX / TheGraph / sims
└── strategies/         # BasisTrading, HyperliquidBasis, TauReset
examples/               # quick_start, holder, basis, tau_reset, agentic_trader,
                        # ml_funding_rate_forecasting
tests/
├── core/               # offline unit + invariant + e2e synthetic
├── loaders/            # real-API loader tests
└── mlflow_tests/       # Docker MLflow + end-to-end pipeline scripts
```

Listed in `README.md`: four generic entity base classes — `BasePerpEntity`, `BaseLendingEntity`, `BasePoolEntity`, `BaseSpotEntity`. **A lending strategy abstraction does not exist** — the `strategies/` directory contains only `BasisTrading`, `HyperliquidBasis`, and `TauReset`. **This is the single most important gap.**

### IV.B — Core architectural pattern (entity-as-state-machine)

Per ARCHITECTURE.md, each entity is a deterministic transition function `T : (IS, GS, A) → IS'`:
- `IS` (`InternalState`) — user position: collateral, debt, LP token amounts, cash. Owned by the entity for the run lifetime; mutated by action methods.
- `GS` (`GlobalState`) — market context: prices, lending/borrowing rates, funding, pool TVL/fees/liquidity. Read-only from the entity perspective; produced upstream by the data pipeline and applied via `update_state(GS)`. Replaced wholesale each observation.
- `A` (`Action`) — method name + kwargs payload.

Action methods are auto-discovered by prefix: any method whose name starts with `action_` is dispatchable via `BaseEntity.execute(Action(name, args))`. Validation precedes mutation (atomic per action); the framework does **not** wrap a sequence of actions in a transaction (intentionally — fail loud). The step-level loop in ARCHITECTURE.md is:

```python
for observation in observations:
    for entity_name, gs in observation.states.items():
        entity.update_state(gs)              # IS, GS → IS', new GS
    actions = strategy.predict()             # entity states → list of (entity, A)
    for action in actions:
        entity.execute(action)               # IS', GS, A → IS''
    snapshot per-entity (IS', GS)
```

A backtest is thus a deterministic replay of `(IS₀, GS₀) → … → (ISₙ, GSₙ)` fully described by `(initial state, observation sequence, strategy)`.

**Delegate-resolved arguments** are the killer feature: action arg values may be callables that the framework resolves at execute-time, after prior actions in the same step have mutated state. Essential for multi-leg actions where leg 2 depends on cash freed by leg 1.

### IV.C — Strategy pattern

```python
@dataclass
class LendingParams(BaseStrategyParams):
    INITIAL_BALANCE: float = 10_000.0
    LENDING_APY: float = 0.05

class PassiveLender(BaseStrategy[LendingParams]):
    def set_up(self) -> None:
        self.register_entity(NamedEntity("LENDING", SimpleLendingEntity()))
    def predict(self) -> List[ActionToTake]:
        ...
```

Three required hooks: `set_up()` (one-time registration), `predict()` (per-observation decisions), `step(observation)` / `run(observations)` (framework-driven). The `BaseStrategy[Params]` generic sets `PARAMS_CLS`, which `set_params` uses to coerce dict-shaped grid cells (MLflow grid search just feeds it dicts).

**Pattern for subclassing with extra params:** `HyperliquidBasis` extends `BasisTradingStrategy` by overriding `PARAMS_CLS = HyperliquidBasisParams`. The project's `PredictiveMCDMStrategy` should extend a (to-be-written) `BaseLendingAllocationStrategy` similarly.

### IV.D — Loaders and typed data structures

Loaders implement `extract → transform → load` with deterministic caching under `<DATA_PATH>/fractal_data/<class>/<key>.<ext>`. `run()` is `extract → transform → load`; `read(with_run=False)` reads cache; `read(with_run=True)` re-fetches.

Return types live in `fractal.loaders.structs`:

- `PriceHistory` — `price`, `DatetimeIndex` named `time`
- `FundingHistory` / `RateHistory` — `rate`
- **`LendingHistory` — `lending_rate` + `borrowing_rate`** *(the project's primary target struct)*
- `PoolHistory` — `tvl`, `volume`, `fees`, `liquidity`, optional `price`
- `KlinesHistory` — OHLCV
- `TrajectoryBundle` — Monte-Carlo bundles

All are `pd.DataFrame` subclasses with a UTC `DatetimeIndex` named `time` for join-compatibility.

**Sign convention (uniform across loaders, per ARCHITECTURE.md):**

| Quantity | Positive ⇒ |
|---|---|
| `lending_rate` | collateral grows per step |
| `borrowing_rate` | debt grows per step |
| `funding_rate` | longs pay shorts |
| `trading_fee` | execution cost on traded notional |

ARCHITECTURE.md explicitly flags: *"The Aave V3 loader historically flipped `borrowing_rate` sign — that was a bug, fixed in v1.4.0; see CHANGELOG.md."* The project **must** be on v1.4.0+ before any backtest is meaningful. Pin in `requirements.txt`.

### IV.E — MLflow grid pipeline

`DefaultPipeline` wraps `(strategy, observations, params_grid)` into one MLflow experiment, one run per grid cell. Each run logs:

| Per run |
|---|
| `params` — all fields of grid cell (via `_params_to_dict` coercion) |
| `metrics` — `accumulated_return`, `apy`, `sharpe`, `max_drawdown` |
| artifact `strategy_backtest_data.csv` — full per-step DataFrame |
| artifact `window_trajectories_metrics.csv` (if `window_size` set) — per-window metrics |
| secondary metrics (if `window_size`) — mean / q05 / q95 / cvar05 across sliding windows |
| artifact `logs/` (if `debug=True`) — strategy loguru directory |

A self-contained Docker MLflow stack lives under `tests/mlflow_tests/docker-compose.yml`; start with `bash tests/mlflow_tests/scripts/start_mlflow.sh` (sqlite backend, filesystem artifact store, proxy artifact serving, port 5500). Pipeline connection is **lazy** — `__init__` does not open MLflow; first `run()` call triggers `_ensure_connected`, making the pipeline trivially testable.

For sliding-window stability analysis use `window_size=24*7` for weekly windows on hourly data, or `window_size=14` for two-week windows on 12-hour data.

### IV.F — Existing ML example to model the project after

**`examples/ml_funding_rate_forecasting/`** — described in the README as *"ML pipeline: forecasting Binance funding rates with feature engineering + CatBoost"*. This is structurally the closest precedent in the repo. **The project's prediction pipeline should mirror its layout** (data → features → CatBoost baseline → strategy integration → grid search) and then *replace* the CatBoost with the DA-BiGRU-CNN as the experimental arm, with CatBoost remaining as a baseline. Mirroring the in-framework house style maximizes the probability that the resulting PR is merge-ready.

### IV.G — Gaps mapped to Extra+1 / Extra+2 PR opportunities

**Extra+1 candidates (small, defensible PRs):**

1. **Compound v3 GraphQL loader.** The repo has only an Aave V3 loader (`fractal/loaders/`). Adding a Compound v3 loader returning `LendingHistory` is cleanly scoped. Subgraph endpoint: Messari maintains the canonical Compound v3 subgraph; the loader queries `Market.rates`, `Market.totalDepositBalanceUSD` / `totalBorrowBalanceUSD`, and `marketHourlySnapshots` on the relevant USDC-base market (cUSDCv3 Ethereum proxy `0xc3d688B66703497DAA19211EEdff47f25384cdc3`). This is the cleanest single-PR contribution.

2. **Regression test for the Aave V3 sign-convention fix.** CHANGELOG.md flags the v1.4.0 borrowing_rate fix but it is not obvious from the open Issues that a lock-in test (in the ARCHITECTURE.md "Lock-in tests" sense) exists. Adding one is low-risk and welcomed by the project's testing philosophy.

3. **Shared `apy_to_per_step_rate()` utility** under `fractal/core/entities/lending_utils.py`. The QuickStart README hardcodes `lending_rate=0.05/hours` — there is no shared helper for converting annualized APY to per-step rate; centralizing it removes a footgun and improves consistency across examples.

**Extra+2 candidates (substantive contribution):**

1. **`BaseLendingAllocationStrategy` abstraction in `fractal/strategies/`.** A multi-lending-protocol allocator base class with hooks for (a) criterion-vector construction, (b) MCDM aggregation, (c) rebalance trigger, (d) gas/slippage modeling. The project's `PredictiveMCDMStrategy` would be its first concrete subclass. There is no analogue to `BasisTradingStrategy` for lending — a clear void. **This is the strongest Extra+2 candidate.**

2. **`ForecastedLendingEntity` (a `BaseLendingEntity` variant exposing a forecasted rate alongside the realized rate).** The current `AaveEntity` reads rate from `GS.lending_rate` only. A subclass that reads both `lending_rate` (current) and `lending_rate_forecast` (next-horizon) from an extended `GlobalState` enables forecast-driven strategies generically and respects the ARCHITECTURE.md "no silent dependence on environment" rule (the forecast must enter through the observation, not through a hidden fetch).

3. **Morpho or Spark integration** as a third lending entity is technically feasible but goes outside the locked two-protocol scope; should be listed as future work, not delivered in this project.

### IV.H — Specific code references to lift patterns from

- **`examples/quick_start/quick_start.py`** — minimum-viable lending strategy template (the full code is inlined in README.md).
- **`examples/basis/backtest.py`** and **`examples/basis/grid.py`** — pattern for `predict()` returning multi-leg ordered actions with delegate-resolved args; canonical pattern for MLflow grid invocation.
- **`examples/tau_reset/backtest.py`** — most relevant strategy structurally, since τ-reset is the canonical "act when state crosses threshold" pattern; the project's rebalance trigger is the same pattern with a forecast-augmented threshold.
- **`examples/ml_funding_rate_forecasting/`** — the ML-pipeline template (feature engineering, CatBoost training, integration with a strategy entity).
- **`fractal/loaders/structs.py`** — the `LendingHistory` definition.
- **`tests/core/e2e/test_e2e_leveraged_long.py`** — pattern for end-to-end testing a lending strategy with the `collateral_is_volatile=True` flag (not directly used here for stable-collateral USDC supply, but the test scaffolding pattern is reusable).
- **`tests/core/invariant_testing/`** — randomized property tests; the project should add an invariant that *total USDC supplied across both protocols never exceeds initial balance + accumulated yield*, an obvious conservation property.
- **`tests/core/test_step_immutability.py`** — referenced in ARCHITECTURE.md for snapshot-fidelity testing.
- **`CHANGELOG.md`** — verify the v1.4.0 Aave borrowing_rate sign fix is in the version pinned by the project.

---

## V. Data Sourcing Concrete Guide

### V.A — Aave v3 USDC supply rates

**Primary source — Aave's official subgraph** (TheGraph network, `aave-v3-ethereum`). The fractal-defi Aave loader uses this; the loader's required env var per ARCHITECTURE.md is `THE_GRAPH_API_KEY`. The relevant subgraph entity is `Reserve` (one per supplied asset). Core query template:

```graphql
query AaveUSDCRates($skip: Int!, $first: Int!) {
  reserveParamsHistoryItems(
    first: $first, skip: $skip,
    orderBy: timestamp, orderDirection: asc,
    where: {
      reserve_: { underlyingAsset: "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48" }
    }
  ) {
    timestamp
    liquidityRate          # RAY (1e27 scaled), per-second annualized
    variableBorrowRate     # RAY (1e27), per-second annualized
    utilizationRate        # WAD (1e18), unitless [0,1]
    totalLiquidity
    totalVariableDebt
  }
}
```

`liquidityRate` and `variableBorrowRate` are stored in RAY (1e27) decimal precision (Aave convention; see Aave docs and the Ancilar Medium deep dive). Conversion to APY:

```python
apy = ((1 + liquidityRate / 1e27 / 31_536_000) ** 31_536_000) - 1
```

**Secondary — Dune Analytics.** Dune ships maintained tables for Aave v3:

- `aave_v3_ethereum.reserve_data_*` (rates and utilization keyed by block).
- `aave_v3_ethereum.LendingPool_evt_ReserveDataUpdated` (raw `ReserveDataUpdated(reserve, liquidityRate, stableBorrowRate, variableBorrowRate, liquidityIndex, variableBorrowIndex)` events; canonical ground truth).

Example Dune SQL:

```sql
SELECT
  date_trunc('hour', evt_block_time) AS time,
  AVG(liquidityRate       / 1e27) AS supply_rate_continuous,
  AVG(variableBorrowRate  / 1e27) AS borrow_rate_continuous
FROM aave_v3_ethereum.LendingPool_evt_ReserveDataUpdated
WHERE reserve = 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48 -- USDC
  AND evt_block_time >= TIMESTAMP '2024-01-01'
GROUP BY 1
ORDER BY 1
```

To annualize: `POWER(1 + supply_rate_continuous / 31536000, 31536000) - 1`.

### V.B — Compound v3 USDC supply rates

**No fractal-defi loader exists** — one of the Extra+1 opportunities. Data sources:

- **Messari subgraph for Compound v3.** Schema entity is `Market` with `rates` array (one per side); per-block snapshots via `marketDailySnapshots` and `marketHourlySnapshots`. Ethereum market: cUSDCv3 (proxy `0xc3d688B66703497DAA19211EEdff47f25384cdc3`).
- **On-chain events.** Compound v3 emits `Supply`, `Withdraw`, `SupplyCollateral`, `WithdrawCollateral` etc.; the `Comet` contract's `getSupplyRate(utilization)` and `getBorrowRate(utilization)` view functions are deterministic functions of utilization. The cleanest historical reconstruction is to (a) sample `Comet.totalsBasic()` (returns the utilization-relevant counters) at a chosen cadence and (b) apply the rate functions. This is effectively free of approximation error and is the canonical approach.
- **Dune.** Tables `compound_v3_ethereum.Comet_*` exist; community queries are published on the platform (search "Compound III USDC").

**Compound v3 quirks to handle:**

1. Compound v3 explicitly switched to *per-second* accrual with 1e18 scaling (vs Compound v2's per-block). Both Aave v3 and Compound v3 are now per-second-based, but their internal scaling factors differ (RAY 1e27 vs WAD 1e18). The loader must normalize.
2. The kink and slope parameters are stored as packed fields in the Configurator and change on governance proposals — the loader should fetch them from the on-chain config struct, not hardcode them.
3. Compound v3 markets are *single-base-asset*: only the base asset (USDC on cUSDCv3) earns supply yield. Collateral assets (WETH, WBTC, etc.) do not. For this project (USDC supply only) this simplifies things — *but document it*.

### V.C — USDC market characteristics (2024–2026)

Drawing on the cited industry surveys and academic datasets (AgileRate 2024 hourly Compound data; "From Rules to Rewards" 2025 Aave Mar 2021–Feb 2025 daily; Yearn yvUSDC industry reporting), the consensus picture for the relevant window:

- **Supply APY ranges (USDC).** Aave v3 and Compound v3 supply APYs both range broadly **3% – 14%** over 2024–2026, with periodic spikes higher during high-utilization events.
- **TVL.** Each protocol's USDC market holds hundreds of millions to low billions USD.
- **Utilization.** Aave v3 USDC utilization typically sits 40–85%; occasional spikes near 95% during high-demand events. The March-2023 DAI utilization-near-100% spike (cited by RareSkills and Krayondigital) is a useful prior-period stress event though predating the locked window.
- **Crossover frequency.** Aave > Compound or vice versa flips empirically frequently at the 12-hour scale. Gudgeon et al. (2020) documents cointegration with Compound leading and Aave adjusting at speed 0.607 — the structural reason a switching allocator beats single-protocol allocation.

### V.D — Update cadence and how on-chain rates change

**On-chain update mechanics:**
- **Aave v3.** Rates are recomputed and emitted via `ReserveDataUpdated` events *on every state-modifying interaction* with the reserve (supply, withdraw, borrow, repay, liquidate). Between such events, the `liquidityIndex` accrues continuously according to the last-emitted `liquidityRate`. So the rate is *event-driven*, but the *yield earned* is per-second continuous.
- **Compound v3.** Similarly event-driven on Comet state changes; per-second continuous accrual via `baseSupplyIndex` / `baseBorrowIndex`. Rate function is recomputed on every `accrue()` call.

**Implication for sampling.** Both protocols can be cleanly resampled to any cadence by forward-filling the most recent emitted rate between events. The 12-hour bar the project uses is well above the typical event frequency on USDC markets (events occur every few blocks during active hours), so aliasing is not a concern.

### V.E — Known data quirks

1. **Aave v3 stable borrow rate is deprecated** in v3.x — only `variableBorrowRate` is meaningful for current data; older series have stable-rate columns that should be ignored.
2. **Reserve factor and protocol fees** mean realized supply rate ≠ utilization × borrow rate; always use the on-chain `liquidityRate` directly rather than recomputing from utilization and borrow rate.
3. **Block timestamp irregularity.** Ethereum block times average ~12s but vary; resampling to hourly or 12-hourly bars requires forward-fill (rates only change on `ReserveDataUpdated`).
4. **aUSDC ↔ USDC scaling.** Aave's aToken supply grows via `liquidityIndex`; if the project ever needs precise balance reconciliation it must track this index, not just the rate. For the strategy logic this is hidden because `AaveEntity.update_state` handles it.
5. **THE_GRAPH_API_KEY rate limits.** TheGraph's hosted service tightened API access in 2024; historical bulk pulls should paginate (`skip` in ≤1000-row chunks) and cache locally — exactly what fractal-defi's loader-cache pattern already does.
6. **Governance changes mid-window.** Both protocols' kink, slope1, slope2, and reserve factor parameters can change via DAO votes. A correct loader logs the parameter set as a feature.

### V.F — Comparable academic datasets

- **"From Rules to Rewards" (arXiv:2506.00505).** Aave v2/v3 dataset: Mar 18 2021 – Feb 25 2025, daily, Ethereum. Pre-processing pipeline in their Appendix C. Worth citing as a comparator even though the project uses higher-frequency 12-hour bars.
- **AgileRate (arXiv:2410.13105).** Compound dataset: Feb 2024 – Feb 2025, 3-hour intervals. **The most directly comparable academic dataset.** The project should reproduce at least their overlapping period for a like-for-like comparison.
- **Aave/Compound automated-risk-management paper (arXiv:2506.12855).** TVL series and liquidation events; complementary.

---

## VI. Methodology Recommendations

### VI.A — Which forecasting approach is best supported by literature for 12–24h DeFi rate prediction?

A **cascaded ensemble** of three model tiers is the safest empirically-supported choice:

**Tier 1 — Baselines (must include all).**
1. *Naive*: last observed rate (random walk).
2. *EMA-smoothed*: the strategy this project is replacing — the existence baseline.
3. *CIR-calibrated forecast*: Orlando–Mininni–Bufalo (2020) partitioning style; one regime per utilization-quintile.
4. *Markov-switching short-rate*: 2- or 3-state regime model on utilization.
5. *CatBoost on hand-crafted features*: mirror `examples/ml_funding_rate_forecasting/` exactly so the comparison to fractal's house style is apples-to-apples.

**Tier 2 — Headline model.**
DA-BiGRU-CNN dual-branch adapted with a **utilization branch** + **rate-residual branch** (see §VI.B).

**Tier 3 — Optional regularizer / ensemble.**
A simple AR(1) + GARCH on the model residual to capture heteroscedasticity that DL models notoriously underrepresent — Chen (1996) is the right classical reference for state-dependent volatility.

**Why not Transformers as headline?** They overfit aggressively on the relatively short series available (~year of hourly Compound data ≈ 8,760 points; comparable for Aave). Transformer architectures typically need ≥10⁵ samples to outperform GRU on financial series; Wallbridge et al. (2020) show the win for LOB but on FI-2010 with ~10⁶ events. Save Transformer experiments for a follow-up paper.

### VI.B — Does dual-branch decomposition make sense for rate/utilization vs price/volume?

**Yes, with a re-justified branching scheme.** The original DA-BiGRU-CNN branches correspond to two distinct generative processes (price-level vs volume-imbalance). For DeFi lending the analogous decomposition is:

- **Branch A — Rate residual.** Target: `r_t − f_kink(U_t)`, where `f_kink` is the protocol-known piecewise-linear curve. This branch sees only the *unexplained* portion of the supply rate after subtracting the deterministic protocol function. Generative model: small reserve-factor adjustments + governance noise + index-rounding artifacts. Well-suited to a short BiGRU.
- **Branch B — Utilization.** Target: `U_{t+h}`. Driven by exogenous borrow demand with clear regime-shift structure. Well-suited to BiGRU + CNN (CNN catches sudden flow-spike patterns; BiGRU catches slow regime drift).
- **Fusion.** Reconstruct `r̂_{t+h} = f_kink(Û_{t+h}) + ε̂_{t+h}^{(A)}`.

**Three advantages over a single-branch black box:**
1. Hard domain prior — the kink is known up to governance changes.
2. Each branch has a smaller, more identifiable target.
3. Interpretability — the user can attribute forecast errors to "got utilization wrong" vs "kink shifted via governance change" vs "residual blowup".

**Honest caveat for the whitepaper:** the dual-branch reasoning is *re-derived* for DeFi rather than *transferred* from LOB. Volume in LOB is unbounded and signed; utilization in DeFi is bounded [0,1] and unsigned. The architectural skeleton (BiGRU + CNN per branch + late fusion) carries over; the data preprocessing and loss formulation must differ.

### VI.C — Loss functions

The author's prior LOB paper uses **weighted Pearson correlation** as auxiliary loss to encourage direction-correctness over level-correctness. Honest assessment for DeFi:

- **Pearson-style direction loss is appropriate** because the MCDM allocator's downstream sensitivity is to *relative* ranking of Aave vs Compound APY, not absolute level — a forecast that systematically over-predicts both rates by 1% but preserves ranking still produces the right allocation.
- **Recommended composite:**
  ```
  L = α·MSE(r, r̂) + β·(1 − WeightedPearson(r, r̂)) + γ·QuantileLoss(r, r̂; q=0.9)
  ```
  with the quantile term to control downside-error (under-predicting yield on the *chosen* protocol is worse than over-predicting on the rejected one — asymmetric impact).
- **Avoid pure MAE** — it under-weights the spike events that matter most (March-2023-style episodes).
- **Sanity-check with cross-entropy on the binary `Aave > Compound at t+h` label.** If the forecaster cannot achieve >55% accuracy on this single-bit task, the regression loss is misleading.

### VI.D — Honest assessment of likely forecast quality

Based on (i) the AgileRate paper's RLS fit implicit R², (ii) the LSTM-LagLasso bond-yield R² (Nunes 2026: in-sample 0.4–0.6, out-of-sample ~0.2 for 1-month sovereign yields), and (iii) Krestenko et al. (2026)'s observation that the funding environment fully explains fixed-rule P&L variance:

- **Expected out-of-sample R² for 12-hour Aave/Compound USDC supply rate: 0.15 – 0.40.** The upper end requires explicit regime conditioning and is not guaranteed.
- **Expected direction-accuracy for "which protocol pays more in 12h": 55 – 65%.** This is the metric that actually matters for allocation P&L; 60% directional skill paired with a Sharpe-aware MCDM allocator should comfortably beat the EMA baseline.
- **Expected Sharpe improvement vs EMA baseline: 0.2 – 0.5 absolute over 12-month backtest** — on the order of magnitude reported in Urusov et al. (2025) for τ-reset CLMM strategies (13–23% fee improvement).

**The whitepaper must explicitly state:** *"We do not claim predictability beyond what utilization-and-regime structure provides; the contribution is the integration architecture (forecast → MCDM → fractal-defi entity), not a claim of efficient-market-violating predictive skill."* This is essential academic honesty and pre-empts the most likely reviewer concern.

---

## VII. Refined Research Question and Hypothesis

### Current implicit research question (PROJECT_2_PLAN.md draft)
*"Can a predictive MCDM allocator across Aave v3 and Compound v3 outperform a reactive baseline?"*

### Sharpened formulation

**RQ1 (primary).** Does replacing the reactive EMA-smoothed supply-rate observation with a 12-hour-ahead DA-BiGRU-CNN forecast in a TOPSIS-style MCDM allocator across Aave v3 and Compound v3 USDC markets produce a statistically and economically significant improvement in risk-adjusted yield, *after gas and slippage costs*, over a 12-month out-of-sample period?

**RQ2 (secondary).** Which architectural decomposition of the forecaster — single-branch on rates, dual-branch on (rate, utilization), or dual-branch with the protocol-known kink subtracted from the rate branch — yields the most accurate *and most allocation-relevant* forecast under a directional, asymmetric, ranking-oriented composite loss?

**RQ3 (tertiary).** To what extent is the forecast-driven allocator's outperformance attributable to (a) the forecast itself, (b) the MCDM criterion structure independent of forecast, or (c) the specific protocol-pair selection (Aave–Compound) vs alternatives? — addressed by ablations.

**H1 (primary).** Forecast-driven MCDM allocation increases Sharpe ratio by ≥ 0.2 vs the reactive EMA baseline over the 12-month evaluation window, with statistical significance assessed via 1000-bootstrap of monthly Sharpe ratios.

**H2 (secondary).** The dual-branch-with-kink decomposition outperforms a single-branch forecaster on out-of-sample direction accuracy by ≥ 3 percentage points, with significance via McNemar's test.

**H0 (null).** A 12-hour forecast adds no value over EMA observation — i.e., on this horizon the rate process behaves as a martingale conditional on observed utilization, and the protocol's deterministic kink function fully explains predictable variation.

The whitepaper should *explicitly entertain* H0 — it is the honest scientific framing, and given the cointegration finding in Gudgeon et al. (2020) and the high efficiency of mature DeFi rate markets it cannot be ruled out a priori.

---

## VIII. Risk Register Additions and Ablation Refinement

### VIII.A — New risks discovered through literature

1. **Sign-convention bug (data integrity).** The fractal-defi Aave V3 loader had a flipped `borrowing_rate` sign before v1.4.0 (CHANGELOG.md). *Mitigation:* pin version ≥ 1.4.0; add a lock-in test asserting `borrowing_rate ≥ lending_rate` for all timestamps (true by protocol design).
2. **Forecast leakage via subgraph aggregation.** TheGraph's aggregated entities may include data from blocks beyond the intended cutoff if the indexer is slightly ahead. *Mitigation:* filter strictly on `block_number` not `timestamp` for training/test splits.
3. **Governance change shifting the kink.** Aave and Compound governance can vote to change `optimalUtilization`, `slope1`, `slope2`, or `reserveFactor`. A model trained on pre-change data will be miscalibrated post-change. *Mitigation:* pull historical kink parameters from on-chain config events and include them as features.
4. **Regime confounding from CeFi events.** FTX collapse (Nov 2022), USDC depeg (Mar 2023), post-ETH-Merge dynamics — these introduce regime shifts the forecaster will not have seen if the training window misses them. *Mitigation:* report metrics separately for pre/post any major depeg or stress event in-window.
5. **Cointegration-driven non-stationarity in the rate spread** (Gudgeon et al. 2020). The spread `r_Aave_USDC − r_Compound_USDC` is cointegrated, not stationary. Cumulative-spread metrics will look optimistic in trending sub-periods. *Mitigation:* report rolling Sharpe by quarter, not just full-window.
6. **Gas-cost regime variance.** Ethereum mainnet gas during 2024–2026 varies ~10× between calm and congested days. A constant-gas assumption is the single biggest source of unrealistic backtest outperformance in DeFi. *Mitigation:* pull historical gas median from Etherscan or Dune; pass `GS.gas_price_gwei`; have the rebalance trigger explicitly compare forecasted yield-uplift to gas cost.
7. **Execution-bridge risk on rebalance.** Withdraw-from-Aave / supply-to-Compound is not atomic; in the inter-block window funds earn no yield. On Ethereum same-chain this is ~12 s — small but worth modeling. If extended cross-chain this becomes material.
8. **Reserve-factor changes mid-test.** Subsumed in #3 but worth separate mention because the reserve factor wedges `borrowRate × utilization` from realized `liquidityRate`; modeling it incorrectly silently biases all simulated yields.
9. **Overfitting to one calendar year.** The locked window covers fewer than two macro-regime cycles. *Mitigation:* use the 2021–2023 Aave dataset from "From Rules to Rewards" as out-of-distribution stress validation, even though not in primary scope.
10. **Compound v3's per-second-accrual scaling vs Aave v3's RAY scaling.** Easy to mis-normalize when computing cross-protocol spread. *Mitigation:* the Compound v3 loader must explicitly emit both rates in identical units before joining with Aave data.

### VIII.B — Ablations suggested or refined by prior work

Building on the ablations the project plan already includes:

| Ablation | Motivation |
|---|---|
| **No-forecast EMA baseline** (reactive control) | Mandatory; the strawman the novelty rests on. |
| **Naive last-observation forecast** | Tests whether *any* forecast > current observation. |
| **CIR-calibrated forecast** (Orlando et al. 2020 partitioning) | Classical interest-rate-model baseline; tests whether DL adds value. |
| **Markov-switching short-rate** | Regime-aware classical baseline; cheap to implement. |
| **CatBoost forecast** (mirroring `ml_funding_rate_forecasting/`) | In-framework house baseline; clean apples-to-apples vs fractal's own funding-rate work. |
| **Single-branch DA-GRU** (no CNN, no domain decomposition) | Tests value of dual-branch architecture per se. |
| **Dual-branch *without* kink subtraction** | Tests value of the deterministic-protocol prior. |
| **Forecast with ranking-loss only** | Tests whether MSE component adds value over pure direction loss. |
| **MCDM with equal weights** vs **learned/tuned weights** | Tests how much of the edge is in the weights vs the forecast. |
| **Single-protocol benchmark** (Aave-only, Compound-only) | Required to establish that switching matters at all. |
| **Greedy "max forecasted APY" allocation** vs **TOPSIS-MCDM** | Tests whether multi-criteria adds value over simple argmax. |
| **Zero-gas-cost backtest** vs **realistic-gas backtest** | Reports the strategy's break-even gas cost — a useful whitepaper number. |
| **Sliding-window stability** (fractal-defi `window_size`) | Required by `DefaultPipeline`; report mean / q05 / q95 / cvar05 across windows. |
| **OOD test on USDC depeg week (Mar 2023)** | Stress test; expectation: forecaster fails; allocator should fall back gracefully. |
| **Forecast horizon sweep (3h, 6h, 12h, 24h)** | Even though 12h is locked, a single-figure horizon-sensitivity ablation strengthens the choice. |

The author's existing AI-Managed ERC-4626 vault paper provides the on-chain MCDM implementation; the **headline ablation** comparing "MCDM-with-EMA" (the prior paper) vs "MCDM-with-DL-forecast" (this paper) should be the figure on the title page of the whitepaper.

---

## IX. Citation Handoff Block

The works flagged below should be carried into the bibliography by the downstream citation agent. They are listed grouped by section without inline citation markers (per instructions).

**§III — instructor baselines.**
- Urusov, A., Berezovskiy, R., Yanovich, Y. (2024). *Backtesting Framework for Concentrated Liquidity Market Makers on Uniswap V3 Decentralized Exchange.* arXiv:2410.09983. BCRA 2024.
- Urusov, A., Berezovskiy, R., Krestenko, A., Kornilov, A., Yanovich, Y. (2025; v2 2026). *Dynamic Liquidity Provision in Decentralized Markets: Strategy Optimization and Performance Evaluation in Concentrated Liquidity AMMs.* arXiv:2505.15338.
- Krestenko, A., Butov, M., Berezovskiy, R., Bolotin, D. (2026). *Dynamic Collateral Control for Permissionless Spot Perpetual Basis Trading.* arXiv:2605.05089.

**§II.A — DeFi lending.**
- Gudgeon, L., Perez, D., Harz, D., Livshits, B., Gervais, A. (2020). *DeFi Protocols for Loanable Funds.* arXiv:2006.13922.
- *From Rules to Rewards: Reinforcement Learning for Interest Rate Adjustment in DeFi Lending* (2025). arXiv:2506.00505.
- *AgileRate: Bringing Adaptivity and Robustness to DeFi Lending Markets* (2024). arXiv:2410.13105.
- Xu et al. (2023). *Auto.gov: Learning-based Governance for Decentralized Finance.* arXiv:2302.09551.
- *Automated Risk Management Mechanisms in DeFi Lending Protocols: A Crosschain Comparative Analysis of Aave and Compound* (2025). arXiv:2506.12855.
- Bertomeu, J., Martin, X., Sall, I. (2024). *Measuring DeFi risk.* Finance Research Letters 63C.

**§II.B — interest-rate forecasting and classical models.**
- Vasicek, O. (1977). *An equilibrium characterization of the term structure.* J. Financial Economics 5(2).
- Cox, J. C., Ingersoll Jr., J. E., Ross, S. A. (1985). *A Theory of the Term Structure of Interest Rates.* Econometrica 53(2).
- Hull, J., White, A. (1990). *Pricing interest-rate-derivative securities.* Review of Financial Studies 3(4).
- Chen, L. (1996). Stochastic mean and stochastic volatility extension of CIR.
- Orlando, G., Mininni, R. M., Bufalo, M. (2020). *Forecasting interest rates through Vasicek and CIR models: a partitioning approach.* J. Forecasting 39(4); arXiv:1901.02246.
- Nunes et al. (2026). *Deep Learning for Bond Yield Forecasting: The LSTM-LagLasso.* Int. J. Finance & Economics; doi:10.1002/ijfe.3116.
- Hamilton, J. D. (1989). Regime-switching foundations.

**§II.B / II.C — LOB DL backbone and architectures.**
- The author's prior paper: *When Less Is More: Domain-Aware Dual-Branch Recurrent Networks for LOB Mid-Price Prediction (DA-BiGRU-CNN).*
- Sirignano, J. (2016). *Deep Learning for Limit Order Books.* arXiv:1601.01987.
- Wallbridge, J. et al. (2020). *Transformers for Limit Order Books.* arXiv:2003.00130.
- Wu, Y., Mahfouz, M., Magazzeni, D., Veloso, M. (2021). *Towards Robust Representation of Limit Orders Books for Deep Learning Models.* arXiv:2110.05479.
- Mäkinen, M., Kanniainen, J., Gabbouj, M., Iosifidis, A. (2018). *Forecasting of Jump Arrivals in Stock Prices using LOB Data.* arXiv:1810.10845.
- Simonyan, K., Zisserman, A. (2014). *Two-Stream Convolutional Networks for Action Recognition.* NeurIPS.
- Feichtenhofer, Pinz, Zisserman (2016). *Convolutional Two-Stream Network Fusion.* CVPR.
- Zhang, Y., Yan, J. (2023). *Crossformer.* ICLR.
- Nie, Y. et al. (2023). *PatchTST.* ICLR.

**§II.D — MCDM.**
- Hwang, C. L., Yoon, K. (1981). *Multiple Attribute Decision Making.* Springer.
- Saaty, T. L. (1980). *The Analytic Hierarchy Process.* McGraw-Hill.
- Brans, J. P., Vincke, P. (1985). *PROMETHEE.* Management Science 31(6).
- Aljinović, Z., Marasović, B., Šestanović, T. (2021). *Cryptocurrency Portfolio Selection — A Multicriteria Approach.* Mathematics 9(14):1677.
- Hosseinzadeh et al. (2023). *An asymmetric PROMETHEE II for cryptocurrency portfolio allocation based on return prediction.* Computers & Operations Research.
- Babaei et al. (2023). *Cryptocurrency portfolio allocation using a hybrid predictive big-data DSS (CLUS-MCDA II).* Omega 115.
- *An integrated TOPSIS and ARAS method for portfolio optimization* (2025). Scientific Reports 15 (Nature); doi:10.1038/s41598-025-17604-y.
- The author's prior paper: *AI-Managed ERC-4626 Yield Vault with Multi-Criteria Decision Making.*

**§IV — Framework.**
- Krestenko, A. and the Fractal contributors (2026). *Fractal: A Python Research Library for DeFi Strategies*, v1.3.2. DOI 10.5281/zenodo.20049904. BSD-3-Clause.
- Aave v3 Technical Paper / Documentation (Aave Companies).
- Compound v3 (Comet) Documentation (Compound Labs).
- Krayondigital / Ancilar / RareSkills technical write-ups on Aave and Compound v3 interest-rate models (industry references).

---

## Closing Note on Scope Discipline

The locked scope (two protocols, USDC-only, 12-hour horizon, predictive MCDM extension of the AI-Managed ERC-4626 Yield Vault) is *defensible exactly as stated* against all prior art surveyed. The three most likely reviewer pushbacks, with pre-emptive responses:

1. *"Is 12-hour predictability genuinely there?"* — Addressed by the cointegration finding in Gudgeon et al. (2020) and by the AgileRate dataset's demonstration that 3-hour-resolution control is feasible, implying 12-hour-resolution forecasting has at least as much signal.
2. *"Why not Morpho / cross-chain?"* — Answered by scope-locking and explicit follow-up work in the conclusion; cross-chain introduces an entirely different execution-risk profile that would dilute the contribution.
3. *"What is the actual novelty vs the author's own ERC-4626 paper?"* — Answered by (a) the forecast head being net-new, (b) the dual-branch domain decomposition being a genuine architectural contribution, and (c) the explicit structural-analogue framing with Krestenko et al. (2026).

The whitepaper's strongest single rhetorical move is the explicit positioning as the **lending panel** of the Vega-Institute / HSE / Skoltech triptych — CLMM → perp-basis → lending — all built on `fractal-defi`. This frames the work as completing a research program rather than starting one, which is exactly the right posture for a Master's-level whitepaper at HSE.