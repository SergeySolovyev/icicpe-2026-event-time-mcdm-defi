# Predictive MCDM Allocation across DeFi Lending Protocols

**Project 2 — DeFi Strategies course (HSE FCS)**
**Author:** Sergei Solovev <sesesolovev@edu.hse.ru>
**Status:** Active development (execution window 18 May – 14 June 2026)

A forecast-driven Multi-Criteria Decision Making (MCDM) allocator that
dynamically routes USDC supply capital between **Aave V3** and **Compound V3**
on Ethereum mainnet. Replaces the reactive EMA-smoothed rate observation
of [Solovev 2026b — AI-Managed ERC-4626 Yield Vault](../Wunder%20Fund/) with a
12-hour-ahead learned forecast inspired by the dual-branch architecture
of [Solovev 2026a — DA-BiGRU-CNN-LOB](https://github.com/SergeySolovyev/DA-BiGRU-CNN-LOB).

Implemented on top of the [`fractal-defi`](https://github.com/Logarithm-Labs/fractal-defi)
research framework (Logarithm-Labs).

---

## Headline Research Question

> Does replacing the reactive EMA-smoothed supply-rate observation with a
> 12-hour-ahead DA-BiGRU-CNN forecast in a TOPSIS-style MCDM allocator across
> Aave V3 and Compound V3 USDC markets produce a statistically and economically
> significant improvement in risk-adjusted yield, after gas and slippage costs,
> over a 4-month out-of-sample test period (Jan–Apr 2026)?

**H1.** Sharpe improvement ≥ 0.2 vs the reactive EMA baseline.
**H0 explicitly entertained:** see `PROJECT_2_PLAN.md` §16 and `DEEP_RESEARCH.md` §VI.D.

---

## Repository structure

```
predictive-mcdm-defi/
├── PROJECT_2_PLAN.md       Strategic plan (locked scope)
├── DEEP_RESEARCH.md        Literature review + methodology rationale
├── LLM_TRANSCRIPT.md       Reproducibility transcript (Requirement 15)
├── requirements.txt        Pinned to fractal-defi==1.3.2
├── data/                   Data fetch / clean / feature engineering
├── forecaster/             DA-BiGRU-CNN + classical baselines (CIR, MS-CIR, CatBoost)
├── strategies/             Buy-hold, APY-greedy, MCDM-EMA, MCDM-CIR, Predictive-MCDM
├── backtest/               MLflow grid search + ablation runners
├── notebooks/              9 analysis notebooks (EDA → ablations → OOD)
├── results/                MLflow artifacts, figures, tables
├── whitepaper/             LaTeX source + compiled PDF
├── tests/                  Sign-convention lock-in, strategy logic, data pipeline
└── extras/
    ├── fractal_pr_compound_loader/        Extra+1 PR staging
    └── fractal_pr_lending_allocation/     Extra+2 PR staging
```

---

## Quick start

```bash
# 1. Clone and enter
git clone https://github.com/SergeySolovyev/predictive-mcdm-defi.git
cd predictive-mcdm-defi

# 2. Set up venv
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Environment variables
cp .env.example .env               # then edit
#   THE_GRAPH_API_KEY=...           # for Aave subgraph
#   DUNE_API_KEY=...                # gas + Compound fallback
#   FRACTAL_DATA_PATH=./data/cached/

# 4. Pull data (18 months, ~30 min)
python -m data.fetch_aave
python -m data.fetch_compound
python -m data.fetch_gas_eth

# 5. Train forecaster
python -m forecaster.train         # MLflow grid; logs at mlruns/

# 6. Run baselines
python -m backtest.run_baselines

# 7. Run main strategy
python -m backtest.run_main

# 8. Run all 15 ablations
python -m backtest.run_ablations

# 9. Compile whitepaper
cd whitepaper && latexmk -pdf main.tex
```

---

## ERRATA vs `PROJECT_2_PLAN.md`

The strategic plan was written before live-state verification of
`fractal-defi`. Three corrections apply:

1. **Version pin.** Plan says `fractal-defi v1.4.0+`; actual latest release
   is v1.3.2 (2026-05-06). v1.4.0 is forward-referenced in CHANGELOG.md but
   the tag is unreleased. We pin **v1.3.2** and rely on
   `tests/test_sign_convention.py` to lock in the correct sign convention
   from real data rather than from a version tag.
2. **Entity name.** Plan §3 pseudocode references `AaveV3Entity`. Repo class
   is `AaveEntity` (no V3 suffix). Strategy code uses the actual name.
3. **`utilization` not in `AaveGlobalState`.** Plan's `f_Risk(u_i)` factor
   needs utilization. Resolution: Extra+1 PR includes both the new
   Compound V3 loader **and** a `utilization` field on both Aave and
   Compound `GlobalState` (computed from
   `totalLiquidity` / `totalCurrentVariableDebt` in the subgraph response).
   This converts Extra+1 from "yet another loader" to "loader + uniform
   state interface across lending entities."

---

## Citations

This project builds on:

- **Solovev 2026a** — *When Less Is More: Domain-Aware Dual-Branch Recurrent
  Networks for Limit Order Book Mid-Price Prediction* (DA-BiGRU-CNN-LOB)
- **Solovev 2026b** — *AI-Managed ERC-4626 Yield Vault with Multi-Criteria
  Decision Making: Design, Implementation, and Formal Verification*
- **Gudgeon et al. 2020** — *DeFi Protocols for Loanable Funds* (arXiv:2006.13922)
- **Krestenko et al. 2026** — *Dynamic Collateral Control for Permissionless
  Spot Perpetual Basis Trading* (arXiv:2605.05089)
- **AgileRate 2024** (arXiv:2410.13105); **"From Rules to Rewards" 2025** (arXiv:2506.00505)

Full bibliography in `whitepaper/refs.bib` and `DEEP_RESEARCH.md` §IX.

---

## License

MIT (forthcoming with first whitepaper revision).
