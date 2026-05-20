# Deep Research — ICICPE 2026 Related Work

**Date.** 2026-05-20  **Author.** Subagent for S.S. Solovev
**Scope.** 4 topics for §2 Background of "Domain-Aware Dual-Branch RNNs Across TradFi and DeFi".
**Method.** 6 web calls total (3 WebSearch, 3 WebFetch). Sources: arxiv.org direct, Google Scholar surrogate via web search.

---

## §1 Halpern–Pass–Saraf impossibility (2024) — must-cite

- **Citation.** Joe Halpern, Rafael Pass, Aditya Saraf. *Fair Interest Rates Are Impossible for Lending Pools: Results from Options Pricing.* arXiv:2410.11053 v2, 29 Oct 2024. URL: https://arxiv.org/abs/2410.11053
- **Key argument** (4 sentences). The authors reduce a lending pool to a portfolio of options on the collateral asset: a borrower's right to walk away from the loan is mathematically equivalent to a put on the collateral struck at the outstanding debt. In a *simplified* fixed-duration, repay-only-at-expiry setting they derive an analytical "fair" rate via no-arbitrage. They then show that in the *realistic* setting (dynamic, perpetual loans with early repayment, as used by Aave V3 / Compound V3) **no fair interest rate exists** — any rate either over-compensates lenders relative to the option-implied premium or under-compensates them, because the borrower's repayment optionality has no finite hedging cost. The impossibility further generalizes beyond the options-reduction to broader equilibrium models of lending pools.
- **Our rebuttal angle** (1 sentence). Halpern et al. prove a static *equilibrium-fairness* impossibility under no-arbitrage; we make an orthogonal *empirical predictability* claim — that the realised rate stream is short-horizon forecastable enough to drive a profitable allocator — so the impossibility result constrains pricing theory but not our forecast-driven MCDM application.

---

## §2 Direct DeFi-MCDM competitors (forecast-driven multi-protocol lending allocators)

After targeted searching we could not find a published peer-reviewed paper that combines (i) ML supply-rate forecasting across **multiple** lending protocols with (ii) an MCDM / TOPSIS-style allocator. Closest adjacent work:

- **Bertucci et al. (2025) — *Reinforcement Learning for Interest Rate Adjustment in DeFi*** — arXiv:2506.00505. Uses offline RL (CQL, BC, TD3-BC) on Aave historical data to *set* rates from the protocol side, not to *allocate across* protocols from a lender side. Verdict: complementary, not competing.
- **Bastianello & Cohen (2025) — *A Theory of Lending Protocols in DeFi*** — arXiv:2506.15295. Game-theoretic equilibrium framework for single-protocol design; no cross-protocol allocator, no forecasting. Verdict: theoretical baseline, not competitor.
- **MakerDAO loan portfolio risk paper** — Science Direct, *DeFi risk assessment: MakerDAO loan portfolio case* (Liu et al., 2024). Risk scoring of a single protocol's loan book; no cross-protocol allocation. Verdict: tangential.
- **Industry/blog references** (yield-aggregators Yearn, Beefy, etc.) implement greedy or heuristic switching with no published ML-forecast layer and no MCDM weighting.

**Verdict.** As far as the published literature surfaces in May 2026, the present work appears to be the **first published instance** of a forecast-driven *multi-criteria* allocator across Aave V3 / Compound V3 USDC pools. State this explicitly in §1 and §2 of the paper, framing the contribution as a methodological first.

---

## §3 arXiv:2502.19862 (Optimal risk-aware interest rates)

- **Citation.** Bastien Baude, Damien Challet, Ioane Muni Toke. *Optimal risk-aware interest rates for decentralized lending protocols.* arXiv:2502.19862, 2025 (q-fin.MF). URL: https://arxiv.org/abs/2502.19862
- **Abstract (verbatim).** "Decentralized lending protocols within the decentralized finance ecosystem enable the lending and borrowing of crypto-assets without relying on traditional intermediaries. Interest rates in these protocols are set algorithmically and fluctuate according to the supply and demand for liquidity. In this study, we propose an agent-based model tailored to a decentralized lending protocol and determine the optimal interest rate model. When the responses of the agents are linear with respect to the interest rate, the optimal solution is derived from a system of Riccati-type ODEs. For nonlinear behaviors, we propose a Monte-Carlo estimator, coupled with deep learning techniques, to approximate the optimal solution. Finally, after calibrating the model using block-by-block data, we conduct a risk-adjusted profit and loss analysis of the liquidity pool under industry-standard interest rate models and benchmark them against the optimal interest rate model."
- **Key result.** Closed-form Riccati-ODE solution for the protocol-optimal rate curve under linear agent response; Monte-Carlo + deep-learning estimator for nonlinear regimes; block-level empirical calibration shows industry-standard piecewise rate curves are sub-optimal vs. their derived risk-adjusted optimum.
- **Relevance to our work.** Baude et al. solve the **protocol designer's** problem (what rate function should the smart contract use?). We solve the **lender's** problem (given the realised rate stream, where should liquidity go next?). Their work justifies why realised rates contain exploitable information (they are demonstrably sub-optimal w.r.t. a calibrated optimum, leaving structural residuals) — exactly the gap our DA-BiGRU-CNN forecaster targets. Cite as the strongest neighbouring 2025 paper and position ours as the dual / lender-side complement.

---

## §4 Cross-domain RNN transfer in financial time-series 2024-2026

Five strongest hits:

1. **GAF-based transfer learning for financial TS (2025).** *Transfer Learning in Financial Time Series with Gramian Angular Field*, arXiv:2504.00378. Evaluates LSTM and DNN with GAF-encoded inputs, using Coral and CMD domain-alignment objectives; CMD-GAF wins on LSTM. Closest in spirit: a recurrent backbone re-targeted across financial sub-domains with a domain-alignment loss — same template as our composite-loss DA-BiGRU.
2. **Multi-source ensemble transfer (Sun et al.).** *Multi-source Transfer Learning with Ensemble for Financial Time Series Forecasting*, arXiv:2103.15593. WAETL and TPEES ensembles; TPEES dominates. Older but methodologically central — supports the "borrow from several source domains" framing.
3. **CryptoGPT — LLM-driven transfer to crypto (Batsi et al., 2026).** Springer LNCS chapter, doi: 10.1007/978-3-032-16281-6_5. LLM-encoder features transferred into a forecaster for crypto returns; framed explicitly as cross-domain (text/news → numeric series).
4. **LiT: Limit Order Book Transformer (2025).** Frontiers in AI, doi: 10.3389/frai.2025.1616485. Transformer LOB model designed with fine-tuning for distributional shift; the authors explicitly invoke transfer learning between LOB regimes. Directly relevant because our prior LOB paper is the source domain for the present DeFi transfer.
5. **Cryptocurrency LOB microstructure (Briola, 2025).** *Better Inputs Matter More Than Stacking Another Hidden Layer*, arXiv:2506.05764. Benchmarks DeepLOB / Conv1D-LSTM on BTC LOB; finding that input engineering dominates depth is directly useful to motivate our domain-aware feature branches over deeper stacks.
6. **(Bonus) Predictive crypto-asset AMM via deep RL (2024).** Financial Innovation 10(1), Springer (doi: 10.1186/s40854-024-00660-0). Hybrid LSTM + Q-learning for AMM quoting on Uniswap V3 — a TradFi-style predictor transplanted to a DeFi venue, closest published analogue to our LOB → DeFi transplant.

---

## §5 Synthesized refs.bib (paste-ready)

```bibtex
@article{halpern2024fair,
  author  = {Halpern, Joseph Y. and Pass, Rafael and Saraf, Aditya},
  title   = {Fair Interest Rates Are Impossible for Lending Pools: Results from Options Pricing},
  journal = {arXiv preprint arXiv:2410.11053},
  year    = {2024},
  url     = {https://arxiv.org/abs/2410.11053},
  note    = {v2, 29 Oct 2024}
}

@article{baude2025optimal,
  author  = {Baude, Bastien and Challet, Damien and Muni Toke, Ioane},
  title   = {Optimal Risk-Aware Interest Rates for Decentralized Lending Protocols},
  journal = {arXiv preprint arXiv:2502.19862},
  year    = {2025},
  url     = {https://arxiv.org/abs/2502.19862}
}

@article{bertucci2025rl,
  author  = {Bertucci, Louis and others},
  title   = {Reinforcement Learning for Interest Rate Adjustment in {DeFi} Lending Pools},
  journal = {arXiv preprint arXiv:2506.00505},
  year    = {2025},
  url     = {https://arxiv.org/abs/2506.00505}
}

@article{bastianello2025theory,
  author  = {Bastianello, Niccolo and Cohen, Samuel N.},
  title   = {A Theory of Lending Protocols in {DeFi}},
  journal = {arXiv preprint arXiv:2506.15295},
  year    = {2025},
  url     = {https://arxiv.org/abs/2506.15295}
}

@article{gaf2025transfer,
  title   = {Transfer Learning in Financial Time Series with Gramian Angular Field},
  journal = {arXiv preprint arXiv:2504.00378},
  year    = {2025},
  url     = {https://arxiv.org/abs/2504.00378}
}

@article{sun2021multisource,
  title   = {Multi-source Transfer Learning with Ensemble for Financial Time Series Forecasting},
  journal = {arXiv preprint arXiv:2103.15593},
  year    = {2021},
  url     = {https://arxiv.org/abs/2103.15593}
}

@incollection{batsi2026cryptogpt,
  author    = {Batsi, and others},
  title     = {{CryptoGPT}: An LLM-Driven Transfer Learning Approach to Cryptocurrencies Time Series Forecasting},
  booktitle = {Springer LNCS},
  year      = {2026},
  doi       = {10.1007/978-3-032-16281-6_5}
}

@article{lit2025limit,
  title   = {{LiT}: Limit Order Book Transformer},
  journal = {Frontiers in Artificial Intelligence},
  year    = {2025},
  doi     = {10.3389/frai.2025.1616485}
}

@article{briola2025microstructure,
  author  = {Briola, Antonio and others},
  title   = {Exploring Microstructural Dynamics in Cryptocurrency Limit Order Books: Better Inputs Matter More Than Stacking Another Hidden Layer},
  journal = {arXiv preprint arXiv:2506.05764},
  year    = {2025},
  url     = {https://arxiv.org/abs/2506.05764}
}

@article{predamm2024,
  title   = {Predictive Crypto-Asset Automated Market Maker Architecture for Decentralized Finance Using Deep Reinforcement Learning},
  journal = {Financial Innovation},
  volume  = {10},
  number  = {1},
  year    = {2024},
  doi     = {10.1186/s40854-024-00660-0}
}

@article{solovev2025lob,
  author  = {Solovev, Sergei S.},
  title   = {When Less Is More: Domain-Aware Dual-Branch Recurrent Networks for {LOB} Mid-Price Prediction},
  journal = {figshare preprint},
  year    = {2025},
  doi     = {10.6084/m9.figshare.31859557}
}
```

---

## §6 Must-cite list (highest priority for §2 of the paper)

- [x] Halpern–Pass–Saraf 2024 (impossibility) — arXiv:2410.11053 — **§2 anchor, must rebut**
- [x] Baude–Challet–Muni Toke 2025 (optimal rates) — arXiv:2502.19862 — **closest 2025 neighbour, position as dual**
- [x] Bertucci et al. 2025 (RL for DeFi rates) — arXiv:2506.00505 — **frame as protocol-side complement**
- [x] Bastianello–Cohen 2025 (theory of lending protocols) — arXiv:2506.15295 — **theoretical baseline**
- [x] GAF transfer learning 2025 — arXiv:2504.00378 — **transfer-learning methodological anchor**
- [x] LiT LOB transformer 2025 — Frontiers AI — **LOB transfer SOTA**
- [x] Briola et al. 2025 (crypto LOB microstructure) — arXiv:2506.05764 — **supports "inputs > depth" motivation for DA branches**
- [x] Predictive AMM via deep RL 2024 — Fin. Innovation — **closest TradFi→DeFi transplant analogue**
- [x] Solovev 2025 (prior LOB work) — figshare DOI 10.6084/m9.figshare.31859557 — **self-cite, source domain**

**Gap to flag in §2.** No published forecast-driven *multi-protocol MCDM* allocator was located in the May 2026 literature — claim novelty explicitly.
