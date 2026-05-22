# Project Kanban — Event-Time HFT-Style DeFi Lending Allocator

> **Single source of truth for all 6-week build.** Subagents read this before acting.
> Updated by commits, not by hand. Visual mirror in Notion (if connected).

**Specs:**
- Design: `C:\Users\1\.claude\plans\enumerated-scribbling-barto.md`
- Literature: `docs/research/literature-foundation.md`
- Plan A (detailed TDD): `docs/superpowers/plans/2026-05-21-event-time-data-pipeline.md`

**Legend:** 🟦 Backlog · 🟨 In Progress · 🟪 Review · 🟩 Done · ⬜ Deferred

---

## Plan A — Per-event data pipeline (Week 1)

| # | Task | Status | Owner | Files | Notes |
|---|---|---|---|---|---|
| A1 | EventRow schema + validator | 🟨 In Progress | inline | `data/event_schema.py`, `tests/test_event_schema.py` | Locks shared contract before fork. Test written; impl next. |
| A2 | Aave V3 per-event 1-day smoke | 🟦 Backlog | subagent-A2 | `data/fetch_aave_events.py`, `tests/test_fetch_aave_events.py` | Template for A4 (Spark) clone. RAY 1e27. |
| A3 | Aave V3 18-month cached | 🟦 Backlog | subagent-A2 | (same) | Cached parquet round-trip. |
| A4 | Spark per-event (Aave fork) | 🟦 Backlog | subagent-A4 | `data/fetch_spark_events.py`, `tests/test_fetch_spark_events.py` | Same schema as Aave, new subgraph id. |
| A5 | Compound V3 RPC sample | 🟦 Backlog | subagent-A5 | `data/fetch_compound_events.py`, `tests/test_fetch_compound_events.py` | Messari subgraph has no base-Comet rates. WAD 1e18. |
| A6 | Morpho Blue per-event | 🟦 Backlog | subagent-A6 | `data/fetch_morpho_events.py`, `tests/test_fetch_morpho_events.py` | api.morpho.org/graphql. AdaptiveCurve IRM — no static f_kink. |
| A7 | Euler V2 per-event | 🟦 Backlog | subagent-A7 | `data/fetch_euler_events.py`, `tests/test_fetch_euler_events.py` | Goldsky subgraph (no auth). |
| A8 | Fluid RPC sample | 🟦 Backlog | subagent-A8 | `data/fetch_fluid_events.py`, `tests/test_fetch_fluid_events.py` | No production subgraph. RATE_PRECISION 1e12. |
| A9 | Maker DSR (Signal F1) | 🟦 Backlog | subagent-A9 | `data/fetch_dsr_events.py`, `tests/test_fetch_dsr_events.py` | Pot.File events. Signal F1 futures-lead analog. |
| A10 | build_per_block_panel.py stitcher | 🟦 Backlog | inline | `data/build_per_block_panel.py`, `tests/test_build_per_block_panel.py` | Depends on A1. Forward-fill onto uniform block grid. |
| A11 | 2026c parity verification | 🟦 Backlog | inline | `tests/test_event_parity.py` | Depends on A10. Hourly resample of new panel matches `joined_clean.parquet` within 5 bp. |

**Critical path:** A1 → {A2…A9 parallel} → A10 → A11.
**Output:** `data/cached/per_block_panel.parquet` (~3.9M rows, ~28 cols, gitignored).

---

## Plan B — T1+T2 decision policies + replay engine (Week 2)

| # | Task | Status | Owner | Files | Notes |
|---|---|---|---|---|---|
| B1 | DecisionPolicy ABC | ⬜ Deferred (post Plan A) | TBD | `decision/base.py`, `tests/test_decision_base.py` | `decide(state) → {hold, switch_to_i}`. |
| B2 | T1 gas-aware threshold rule | ⬜ Deferred | TBD | `decision/t1_threshold.py`, tests | Rule: `E[dwell]·spread > gas/position`. EWMA dwell. |
| B3 | OU spread model | ⬜ Deferred | TBD | `decision/ou_calibrator.py`, tests | `dS = κ(θ−S)dt + σdW`. Rolling-window MLE. |
| B4 | T2 optimal stopping Bellman threshold | ⬜ Deferred | TBD | `decision/t2_optimal_stopping.py`, tests | Closed-form S* from (κ,θ,σ,K,gas). Kissell eq 8.23 benchmark. |
| B5 | Per-block replay engine | ⬜ Deferred | TBD | `backtest/replay_per_block.py`, tests | Streaming replay; O(1) state. Embargo 0.01·T per AFML. |
| B6 | B1-B4 baseline runners | ⬜ Deferred | TBD | `backtest/run_baselines.py` | Always-Aave, Always-Compound, Greedy spot, MCDM-EMA event-time. |
| B7 | Validation slice (Sep-Dec 2025) | ⬜ Deferred | TBD | `results/tables/val_matrix.csv` | Iterate hyperparams until T1 beats B4 by ≥10 bp. |

**Gate:** T1 net-APY > B4 net-APY by ≥10 bp on Sep-Dec 2025.

---

## Plan C — T3 hazard model + Signal builders F1-F4 (Week 3)

| # | Task | Status | Owner | Files | Notes |
|---|---|---|---|---|---|
| C1 | Mempool/Flashbots historic snapshot fetcher | ⬜ Deferred | TBD | `data/fetch_mempool_traces.py` | For Signal F2. Coverage validation BEFORE committing F2. |
| C2 | Curve 3pool + Chainlink ETH/USD streams | ⬜ Deferred | TBD | `data/fetch_curve_3pool.py`, `data/fetch_chainlink_eth.py` | F1, F4 inputs. |
| C3 | Feature builder F1 (lead) | ⬜ Deferred | TBD | `decision/features/f1_lead.py`, tests | DSR rate, sDAI, Curve 3pool swap rate, lag features. |
| C4 | Feature builder F2 (order-book dynamics) | ⬜ Deferred | TBD | `decision/features/f2_orderbook.py`, tests | Mempool deposit/withdraw/borrow aggregates. |
| C5 | Feature builder F3 (fragmentation) | ⬜ Deferred | TBD | `decision/features/f3_fragmentation.py`, tests | 15 pairwise spreads (6-way). Dominant signal. |
| C6 | Feature builder F4 (related) | ⬜ Deferred | TBD | `decision/features/f4_related.py`, tests | ETH price, peg deviations, top-LP activity. |
| C7 | Cox/Weibull hazard training pipeline | ⬜ Deferred | TBD | `decision/t3_hazard_train.py` | Self-exciting cross-protocol arrivals. Hawkes 1971 cite. |
| C8 | T3 hazard inference + ONNX export | ⬜ Deferred | TBD | `decision/t3_hazard.py`, tests | Identical interface to T1/T2. ONNX for agent reuse. |
| C9 | Signal ablation (F1/F2/F3/F4 LOO) | ⬜ Deferred | TBD | `results/tables/signal_ablation.csv` | Expected: F3 dominant. |

**Gate:** T3 net-APY > T2 net-APY by ≥3 bp on validation. F3 confirmed dominant.

---

## Plan D — Empirical study + paper draft (Week 4)

| # | Task | Status | Owner | Files | Notes |
|---|---|---|---|---|---|
| D1 | Full matrix on test window (Jan-Apr 2026) | ⬜ Deferred | TBD | `results/tables/test_matrix.csv` | 7 strategies × 6 protocols. |
| D2 | 1000-bootstrap paired monthly Sharpe | ⬜ Deferred | TBD | `results/tables/h1_significance.csv` | CIs for H1a / H1b / H1c. |
| D3 | Per-quarter regime-conditional breakdown | ⬜ Deferred | TBD | `results/tables/regime_breakdown.csv` | T3≥T2≥T1≥B4 in ≥3 of 4 quarters. |
| D4 | Deflated Sharpe Ratio computation | ⬜ Deferred | TBD | (same h1_significance) | DSR > 0.95 (AFML, NOT nominal p<0.05). |
| D5 | Paper §V (Empirical Study) draft | ⬜ Deferred | TBD | `papers/icicpe-scopus-vol2/sections/05_empirical.tex` | ~1500 words. |
| D6 | Paper §VI (Cross-domain / signal taxonomy) draft | ⬜ Deferred | TBD | `papers/icicpe-scopus-vol2/sections/06_discussion.tex` | Hinge framing (MacKenzie pp 93-94). |
| D7 | Equity-curves figure (per-protocol) | ⬜ Deferred | TBD | `results/figures/equity_curves.png` | 7 panels. |
| D8 | Signal-heatmap figure | ⬜ Deferred | TBD | `results/figures/signal_heatmap.png` | F1-F4 vs τ-to-flip. |
| D9 | Architecture figure (TikZ) | ⬜ Deferred | TBD | `papers/icicpe-scopus-vol2/sections/03_methodology.tex` | Reuse 2026c TikZ recipe. |

**Gate:** Paper compiles 10+ pages with zero undefined refs.

---

## Plan E — Agent event-time re-architecture (Week 5)

| # | Task | Status | Owner | Files | Notes |
|---|---|---|---|---|---|
| E1 | Agent decision/ symlink/copy from paper repo | ⬜ Deferred | TBD | `D:\DeFi\DeFi-Vega Project\agent\decision\` | **Bit-identical** modules from paper repo. |
| E2 | ProtocolReaders for Spark/Morpho/Fluid/Euler | ⬜ Deferred | TBD | `agent/protocols/spark.py`, `morpho.py`, `fluid.py`, `euler.py` | Live mirrors of fetchers from Plan A. |
| E3 | per_block_loop.py (replace hourly main.py) | ⬜ Deferred | TBD | `agent/per_block_loop.py` | Block-by-block re-evaluate. |
| E4 | Flashbots private mempool submit | ⬜ Deferred | TBD | `agent/mempool.py` | `eth_sendPrivateTransaction`. MacKenzie pp 200-203 asymmetric-bump analog. |
| E5 | Live signal builders F1-F4 | ⬜ Deferred | TBD | `agent/signal/` | Mirror of paper's `decision/features/`. |
| E6 | History persistence (T2/T3 rolling window) | ⬜ Deferred | TBD | `agent/state/history.parquet` | Survives restart. |
| E7 | Sepolia 1-week paper-trade | ⬜ Deferred | TBD | `agent/logs/paper_trade_2026_07_<wk>.json` | ≥10 rebalances. |

**Gate:** Agent runs 1 week on Sepolia without errors; Flashbots tx submit verified.

---

## Plan F — Paper polish + submit (Week 6)

| # | Task | Status | Owner | Files | Notes |
|---|---|---|---|---|---|
| F1 | refs.bib audit (no Anonymous) | ⬜ Deferred | TBD | `papers/icicpe-scopus-vol2/refs.bib` | Reuse hygiene from 2026c (commit e4660a3). |
| F2 | ICICPE template conversion | ⬜ Deferred | TBD | `papers/icicpe-scopus-vol2-submission/` | Reuse procedure from 2026c (commit d383d51). |
| F3 | Anonymization audit | ⬜ Deferred | TBD | same | Strip "our prior work", figshare DOIs. |
| F4 | Page-budget audit | ⬜ Deferred | TBD | same | Target 10-12 pages. |
| F5 | LLM transcript capture | ⬜ Deferred | TBD | `LLM_TRANSCRIPT.md` | Requirement 15 artifact. |
| F6 | Submit to ICICPE SCOPUS Vol-2 | ⬜ Deferred | user | manuscriptlink portal | Deadline Nov 20, 2026. |

---

## Cross-plan critical milestones

| Date | Milestone | Plan | Status |
|---|---|---|---|
| 2026-05-27 | per_block_panel.parquet exists, parity passes | A | 🟦 |
| 2026-06-03 | T1 beats B4 by ≥10 bp on validation | B | ⬜ |
| 2026-06-10 | T3 ablation done; F3 confirmed dominant | C | ⬜ |
| 2026-06-17 | Paper §V/§VI drafts done | D | ⬜ |
| 2026-06-24 | Agent 1-week Sepolia run done | E | ⬜ |
| 2026-06-30 | Submission package ready | F | ⬜ |

---

## Active subagents

| Subagent ID | Task | Started | Status | Output file |
|---|---|---|---|---|
| _(none yet)_ | | | | |

---

## Recent commits (auto-updated)

See `git log --oneline -20` for current state.
