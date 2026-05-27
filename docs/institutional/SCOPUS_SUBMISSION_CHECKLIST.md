# SCOPUS Submission Checklist — Vol-2 Paper

Pre-flight checklist before uploading `submission_<sha>.zip` to the
ICICPE SCOPUS-track Vol-2 post-conference portal. Each item must be
✓ before submitting.

---

## ✅ Methodology rigor

- [x] **Pre-registration log**: H1a/H1b/H1c hypotheses documented in
      `docs/research/literature-foundation.md` (commit SHA `354e231`,
      2026-05-21) **before** any walk-forward evaluation.
- [x] **All 3 pre-registered hypotheses now closed**:
      - H1a: T1 vs hourly EMA, +189 bp net APY, p<10⁻⁴ ✓
      - H1b: T2 vs T1, near-tied (small reverse effect from over-trading
            on rich signal space) — **honest negative result, expected
            without F1 covariate** ✓
      - H1c: T3 vs T1, +7.03 bp, paired-bootstrap p = 0.0152, 95% CI
            [+0.48, +14.74] bp, wins 5/6 ✓ NEWLY CLOSED
- [x] **6 non-overlapping 3-month walk-forward windows** (Nov 2024 –
      Apr 2026), no cross-window leakage.
- [x] **Purged k-fold CV with embargo** = 0.01·T ≈ 5.4 days
      (López de Prado AFML Ch.7.4) for T3 Cox training.
- [x] **Sample-uniqueness weighting** (AFML Ch.4.5) for overlapping
      triple-barrier labels.
- [x] **Paired bootstrap** (B = 10,000, seed = 42) for all CI/p-value
      computations.
- [x] **Dual-lens metric** (ΔAPY + ΔSharpe with Sharpe-inflation
      paradox documented).
- [x] **Honest scope separation**: active panel (3 active +6 benchmark)
      vs hold-benchmark set explicitly distinguished.

## ✅ Statistical results

- [x] **N×M paired-bootstrap matrix**: 18 contrasts (3 active policies
      × 6 protocol-holds), all 16 of 18 with p<0.05.
- [x] **T3 with sophisticated retrain dominates T1 on all 6 contrasts**
      (T3 vs Euler: +1.53pp, p=0.011 vs T1's +1.46pp, p=0.026).
- [x] **F1/F3/F4 ablation table** documents per-signal-class
      attribution: F4 (USDC peg + ETH/USD) adds +4.4pp OOF C-index,
      F1 (Maker DSR) adds +1.5pp.
- [x] **No 'honest gap'** remaining — Euler beat by all 3 policies at
      p<0.05 on the 6-way active panel.

## ✅ Data provenance

- [x] **Six protocols**: Aave V3, Compound V3, Spark, Morpho Blue,
      Euler V2, Fluid Finance (~67% of Ethereum L1 USDC lending TVL).
- [x] **Heterogeneous sources** (anti-single-vendor risk):
      per-event subgraphs + hourly RPC + Sky Messari subgraph +
      DeFiLlama Yield Pools.
- [x] **Maker DSR via sDAI proxy** (DeFiLlama pool
      `c8a24fee-ec00-4f38-86c0-9f6daebc4225`, 546 daily snapshots,
      1.25%–11.50% APY range).
- [x] **USDC peg deviation** range [-26.7, +82.8] bp documented.
- [x] **Per-block panel** rebuild script `extend_panel_to_6way.py`
      idempotent and committed.

## ✅ Code reproducibility

- [x] **End-to-end pipeline** in one command:
      `python -m scripts.finalize_6way_pipeline` runs 9 steps from
      walk-forward equity → N×M matrix → paper macros → dossier
      render → submission zip.
- [x] **Sophisticated T3 retrain** in `scripts/train_t3_sophisticated.py`
      reproducible with `python -m scripts.train_t3_sophisticated`.
- [x] **Walk-forward run** in `scripts/run_6way_walkforward.py`
      resumable (skips existing equity files).
- [x] **All test suites pass**: 128/128 on agent side
      (DeFi-Vega Project), 26/3 skip on research side.

## ✅ Paper quality

- [x] **Page count = 12** (within F4 budget [10, 12]).
- [x] **No undefined references** (latex pdflatex × 3 + bibtex clean).
- [x] **Anonymized for blind review**: figshare DOIs redacted, author
      affiliations replaced with "Anonymous Author(s)".
- [x] **B4 hourly MCDM-EMA straw-man** intentionally absent from the
      N×M matrix; mentioned in §V intro for completeness.
- [x] **All 5 figures present**: institutional_summary.png,
      walk_forward_heatmap.png, walk_forward_nxm.png,
      capacity_curve.png, cost_waterfall.png, equity_curves.png,
      signal_heatmap.png.
- [x] **TikZ architecture figure** (T1/T2/T3 ladder) in §III.

## ✅ Institutional dossier

- [x] **8 chapters rendered**: one-pager, performance, walk-forward
      robustness, capacity, risk register, operational runbook, live
      trial plan, reproducibility.
- [x] **SLA targets committed**: 99.5% uptime, <30 block lag P95,
      <5s rebalance latency.
- [x] **Kill-switch protocol** documented (USDC depeg, Forta exploit,
      chain reorg).
- [x] **5-phase live trial plan** with hard rules (>$25M needs 12mo
      mainnet track record).

## ✅ Live agent (Plan E + Tier 5)

- [x] **Per-block loop** with WebSocket subscription.
- [x] **Flashbots private mempool** integration (MEV protection).
- [x] **6 protocol readers** (Aave/Compound/Spark/Morpho/Euler/Fluid).
- [x] **Tier 5 observability**: JSON structured logs, Prometheus
      /metrics endpoint on :9090, append-only audit trail with fsync.
- [x] **128/128 agent tests pass** including 8 Tier 5 + 5 Plan E.
- [x] **Sepolia paper-trade RUNBOOK** committed.

## ⚠️ Optional next-extensions (not required for submission)

These are documented as future work in §VII Limitations:

- [ ] **F2 mempool dynamics** signal class (requires paid Blocknative
      API; ROI undetermined).
- [ ] **Capacity backtest at $5M, $25M, $50M** (Krause IRM curve
      slippage gives analytical bounds; numerical confirmation
      deferred to next compute cycle).
- [ ] **Multi-asset extension** (USDC + USDT + DAI tri-asset
      allocator) — explicit Vol-3 scope.
- [ ] **Live Sepolia paper-trade equity series** (RUNBOOK shipped;
      execution deferred).

## 📋 Submission package contents

| File | Path | Required |
|---|---|---|
| Paper PDF | `submission_<sha>/main.pdf` | ✓ |
| LaTeX source | `submission_<sha>/main.tex` + `sections/*` | ✓ |
| BibTeX | `submission_<sha>/refs.bib` | ✓ |
| Class file | `submission_<sha>/icicpe.sty` + `ICICPEtran.bst` | ✓ |
| Results macros | `sections/results_macros.tex` + `t3_macros.tex` | ✓ |
| F1/F3/F4 audit | passed via `build_submission_zip --check` | ✓ |
| Manifest | `submission_<sha>.manifest.txt` | ✓ |
| Hash | `submission_<sha>.zip.sha256` | ✓ |

## 🎯 Submission protocol

```bash
# 1. Verify clean state
git status                                    # should be clean
git log -1 --pretty=oneline                  # latest commit = 92e378a

# 2. Rebuild submission from canonical source
python -m scripts.finalize_6way_pipeline     # full E2E
ls submission_*.zip | tail -1                # final zip name

# 3. Visual verification
# Open papers/icicpe-scopus-vol2-submission/main.pdf in Adobe
# Confirm 12 pages, all figures present, all references resolved

# 4. Upload to ICICPE SCOPUS portal
# - Track: SCOPUS Vol-2 post-conference
# - Deadline: 2026-11-20
# - Attach: submission_<sha>.zip
# - Cover note: optional — see DRAFT_COVER_LETTER.md
```

## 📅 Timeline

- 2026-05-21: Pre-registration log committed (`354e231`)
- 2026-05-27: All 3 H1 hypotheses closed (today)
- 2026-11-20: SCOPUS-track Vol-2 deadline
- Target: submit ≥ 30 days early (2026-10-20) for buffer.
