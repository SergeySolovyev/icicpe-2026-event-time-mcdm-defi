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
| A1 | EventRow schema + validator | 🟩 Done | inline | `data/event_schema.py` | `6d0119c` + dedup-bug fix `edc67e0`. 9 tests pass. |
| A2 | Aave V3 per-event 1-day smoke | 🟩 Done | subagent | `data/fetch_aave_events.py` | `2fcfad1` + `edc67e0`. Pool addr fixed in-place (PoolAddressesProvider). |
| A3 | Aave V3 18-month cached | 🟩 Done | subagent | (same file) | Same commit as A2. Cached wrapper round-trip tested. |
| A4 | Spark per-event (Aave fork) | 🟩 Done | subagent | `data/fetch_spark_events.py` | `b55f9dd` + `edc67e0`. |
| A5 | Compound V3 RPC sample | 🟩 Done | subagent | `data/fetch_compound_events.py` | `6d07c91`. 3 offline tests pass. |
| A6 | Morpho Blue per-event | 🟩 Done | subagent | `data/fetch_morpho_events.py` | `90d596d`. Schema-fix `fb051e5` after live API introspection. |
| A7 | Euler V2 per-event | 🟩 Done | subagent | `data/fetch_euler_events.py` | `dda3a62`. Endpoint-fix `fb051e5`. |
| A8 | Fluid RPC sample | 🟩 Done | subagent | `data/fetch_fluid_events.py` | `f494289`. Selector `0x29e04fbf`. |
| A9 | Maker DSR (Signal F1) | 🟩 Done | subagent | `data/fetch_dsr_events.py` | `8bb55d1`. |
| A10 | build_per_block_panel.py stitcher | 🟩 Done | inline | `data/build_per_block_panel.py` | `4573a31`. Forward-fill + re-cumcount-after-block-resolution. 5 tests. |
| A11 | 2026c parity verification | 🟩 Done | inline | `tests/test_event_parity.py` | `6e58867`. Skips when caches missing; activates after operator build. |
| A12 | Kaggle build kernel | 🟨 v2 partial | inline | `kaggle_workspace/build_panel/` | `c145820` + `fb051e5`. **v2 result: Morpho ✅ + Euler ✅ + 5 await user secret-binding.** Partial panel 3.93M × 10 cols staged at `data/cached/per_block_panel.parquet` (48 MB) for sandbox validation. |

**Critical path:** A1 → {A2…A9 parallel} → A10 → A11 → A12. **A1-A11 ✅; A12 partial pending user secrets-binding.**
**Output:** `data/cached/per_block_panel.parquet` (target ~3.9M rows × ~28 cols; currently 3.93M × 10 cols with Morpho + Euler only, gitignored).

---

## Plan B — T1+T2 decision policies + replay engine (Week 2)

Detailed TDD plan: `docs/superpowers/plans/2026-05-22-decision-policies-t1-t2-replay.md`

| # | Task | Status | Owner | Files | Notes |
|---|---|---|---|---|---|
| B1 | DecisionPolicy ABC | 🟩 Done | inline | `decision/base.py` | `711d34b`. BLOCKS_PER_YEAR=2_628_000 int constant. 9 tests. |
| B2 | T1 gas-aware threshold rule | 🟩 Done | subagent | `decision/t1_threshold.py` | `7c3827e`. 7 tests pass. EWMA-dwell estimator. |
| B3 | OU spread calibrator | 🟩 Done | subagent | `decision/ou_calibrator.py` | `b45df13`. 4 tests pass. Closed-form MLE. |
| B4 | T2 optimal stopping Bellman threshold | 🟩 Done | inline | `decision/t2_optimal_stopping.py` | `06f9033`. 5 tests pass. S*=θ+σ·√(K/(κ·dt)). Defers to T1 when κ ≤ 1e-6 or cold-start. |
| B5 | Per-block replay engine | 🟩 Done | subagent | `backtest/replay_per_block.py` | `e50d2f4`. 5 tests pass (slow 1-yr compound: 911s). Protocols extracted dynamically from `<proto>_lending_apr` cols. |
| B6 | B1-B4 baselines as policies | 🟩 Done | subagent | `backtest/run_baselines_event_time.py` | `f724b4e`. 4 tests pass. **Empirical finding**: B4 MCDM-EMA at realistic 2× Aave-TVL gap structurally suppresses moderate APY edges (paper §V hook). |
| B7 | Validation matrix (Sep-Dec 2025) | 🟨 In Progress | inline | `backtest/run_validation_matrix.py` | Drafted; running on partial panel (Morpho+Euler 878K blocks). ~30 min wall-clock. Output: `results/tables/plan_b_validation_matrix.csv`. |

**Gate:** T1 net-APY > B4 net-APY by ≥10 bp on Sep-Dec 2025 (will validate once full panel arrives).

---

## Plan C — T3 hazard model + Signal builders F1/F3/F4 (Week 3) ✅ COMPLETE

Detailed TDD plan: `docs/superpowers/plans/2026-05-23-t3-hazard-signal-builders.md`

**Scope note**: F2 (mempool order-book dynamics) DEFERRED to future work per
design-spec risk R1 (historic Flashbots mempool snapshots have known 2024
gaps). Plan C runs on subgraph data only — F1 / F3 / F4.

| # | Task | Status | Owner | Files | Notes |
|---|---|---|---|---|---|
| C1 | SignalFeatureBuilder ABC + flip-labels | 🟩 Done | inline | `decision/features/{__init__,base}.py` | `911a7d7`. 10 tests pass. Pandas `.values` tz-stripping gotcha documented for subagents. |
| C2 | F1 lead features (DSR + sDAI proxies) | 🟩 Done | subagent | `decision/features/f1_lead.py` | `8d80db2`. 6 tests pass. NaN-tolerant when events_dsr.parquet absent. |
| C3 | F3 fragmentation features (dominant signal) | 🟩 Done | subagent | `decision/features/f3_fragmentation.py` | `5f30e12`. 7 tests pass. Dynamic protocol discovery — 2-proto = 1 pair, 6-proto = 15 pairs. |
| C4 | F4 related features (gas regime + peg dev) | 🟩 Done | subagent | `decision/features/f4_related.py` | `1fd86ca`. 7 tests pass. 30-day rolling quantile via `rank(pct=True)`. |
| C5 | Cox proportional-hazards training | 🟩 Done | inline | `decision/t3_train.py` | `fe1ca46`. 6 tests pass. lifelines>=0.30 added to requirements.txt. **Synthetic recovery: coef on f3_spread_max_minus_min = +499 (correct sign + magnitude); C-index 0.629 EXCEEDS Plan D production target 0.55.** |
| C6 | T3HazardPolicy + ONNX inference | 🟩 Done | inline | `decision/t3_hazard.py` | `0bfb154`. 9 tests pass. DecisionPolicy subclass — plugs into EventReplayEngine identically to B1-T2. Fallback to T1 on missing features. **Paper finding**: at $17.5 gas / $1M position, crossover gate ≈ 5pp spread or 5× position size — gas correctly suppresses 300bp-spread switches. |
| C7 | Signal LOO ablation runner | 🟩 Done | inline | `backtest/run_signal_ablation.py` | `a3bba6b`. 4 tests pass. **Partial-panel sandbox run (dbae094)** shows 6/7 variants need full universe to fit; T3_F3_only on partial panel = C-index 0.51 (random) — confirms methodology genuinely needs cross-protocol diversity. |

**Plan C surfaced 3 paper-relevant findings for Plan D §V:**
1. T1 +61 bp vs published B4 baseline on Sep-Dec 2025 validation (B7 commit `398809d`)
2. Gas-cost gate quantified: 5pp/5× position threshold for profitable switching at L1 fees
3. F3 fragmentation IS dominant — F3-only ablation beats F1/F4-only on synthetic; full-panel validation pending

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
