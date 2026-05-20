# Cross-Domain Paper for ICICPE 2026 — Design Spec

**Date.** 2026-05-20
**Author.** S. S. Solovev (HSE FCS) — brainstorming with Claude
**Target.** ICICPE 2026 (Chiang Mai, 19–21 Aug 2026), Scopus-indexed proceedings, **deadline 31 May 2026**.
**Status.** Draft — pending user review.

---

## 1. Context

- **One combined paper** unifies two domains the author has worked on:
  - **Prior work (LOB)** — figshare DOI `10.6084/m9.figshare.31859557` — DA-BiGRU-CNN for limit-order-book mid-price prediction (already published as preprint). **Cited as prior work, not re-proved.**
  - **New work (DeFi)** — the `predictive-mcdm-defi` project (this repo): the same architecture applied to Aave V3 / Compound V3 USDC lending-rate forecasting, driving a 4-factor MCDM allocator.
- **A separate paper on smart-contract vulnerability detection** is in flight independently (`Solovev_SS_Multi-Level_Smart_Contract_Defense.tex`) — out of scope for THIS spec.

## 2. Central thesis

> **Domain-aware dual-branch recurrent architectures, designed for one financial time-series problem, transfer to a structurally analogous but adversarially different problem without architectural redesign — by re-identifying the domain-natural pair of feature subspaces. The same composite loss is invariant under the move.**

Three supporting claims, evidence-anchored:

| # | Claim | Evidence |
|---|---|---|
| 1 | **Decomposition principle.** The pair (price, volume) for LOB and (rate-residual ε=r−f_kink(u), utilization+context) for DeFi are domain-natural decompositions. One architecture, two specialisations. | Same DA-BiGRU-CNN config (BiGRU×2 d=96 per branch, Conv1d k∈{3,5,7}, 192→96→48); ablations in each domain show single-branch and no-fusion hurt by similar magnitudes. |
| 2 | **Loss invariance.** α·MSE + β·(1−WPearson) + γ·Q90 with (0.4, 0.5, 0.1) is the trained objective in both domains. | LOB result: wPearson 0.266 beats LightGBM 0.168 by +58 %. DeFi result: post-R²-fix wPearson and dir_acc; loss decomposition log shows consistent component magnitudes. |
| 3 | **Empirical transfer.** Same training recipe, fresh dataset, no hand-tuning of hyper-parameters: forecaster trains, ONNX-exports with torch↔ort parity, and feeds an MCDM allocator. H1 honestly pre-registered, H0 publishable per project plan §16. | Bootstrap on n=4 monthly Sharpe → point estimate ΔSharpe>0 in favor of predictive, CI wide, p≈0.30 (FAIL TO REJECT H0). Honest negative result is the contract. |

## 3. Paper structure (ICICPE format, target ≈10 pages)

| § | Pages | Content |
|---|---:|---|
| Abstract | 0.3 | Thesis + two domains + new empirical contribution + honest H0 framing |
| 1. Introduction | 1.0 | Motivation for cross-domain transfer; thesis stated explicitly; contributions list |
| 2. Background & Related Work | 1.5 | LOB microstructure (brief); DeFi lending mechanics; Halpern-Pass-Saraf rebuttal; deep-research findings |
| 3. Methodology | 2.0 | DA-BiGRU-CNN abstract description + two specialisations side-by-side; composite loss; weighted-Pearson metric |
| **4. LOB recap (prior work)** | **0.5** | One paragraph + one results table from Solovev 2026 (figshare DOI). **No re-derivation; no figures from prior paper.** |
| **5. DeFi-MCDM experiment** | **3.5** | Data (12,895 hours, regime shift 2025 Q3→Q4); model; ablations (15 from plan §10); H1 bootstrap; regime-conditional split; forecast-quality (post-R²-fix) |
| 6. Cross-domain Discussion | 1.0 | What transfers (decomposition + loss); what doesn't (numerical parameters); methodological-honesty disclosure |
| 7. Limitations + Future Work | 0.5 | n_months=4 limits power; MEV/adversarial DeFi unaddressed; single seed; smart-contract paper as parallel direction |
| 8. Conclusion | 0.3 | One paragraph |

**Why this structure works for Scopus:** keeps novelty concentrated (~5 of ~10 pages on the new DeFi work + the transfer argument), uses prior work efficiently as a citation rather than padding, and matches reviewer expectations (clear thesis + experiments + honest discussion).

## 4. Audit methodology (Phase 1 — must complete BEFORE retraining)

The `R²=−7×10⁹` artefact is a type-1 bug (mathematical contract violation). One bug found ⇒ assume others exist. Run six systematic checks across five files **before** any retrain:

### Six checks

| # | Check | Pass criterion |
|---|---|---|
| 1 | **Unit trace** — annotate units of every numeric column from parquet → features → model input → model output → eval. | Each transformation labelled `[per-hour]` / `[annualized]` / `[decimal]` / `[bp]` consistently; mismatches flagged. |
| 2 | **Sanity unit-tests** for each public function in `data/features.py`, `forecaster/train.py`, `backtest/run_main.py`. | `f_kink(0)≈base`; `rate_residual` median ≈0; `reconstruct_rate(0,u)=f_kink(u)`; bootstrap on simulated H0 gives uniform p. |
| 3 | **Predictions histogram + scatter** — `hist(y_truth)` vs `hist(y_pred)`; scatter with x=y line. | Same scale; no order-of-magnitude offset; reasonable spread. |
| 4 | **Loss decomposition** — log α·MSE, β·(1−WPearson), γ·Q90 separately per epoch. | No term dominates by ×100; all components decreasing through training. |
| 5 | **Per-quarter sanity** — dir_acc by quarter across val/test, using CLAUDE.md regime structure (Q3'25 → Q4'25 → Q1'26 → Q2'26). | Variance explainable by regime, not by silent bugs. |
| 6 | **Reproducibility** — fix seed; smoke-train locally twice; MD5 the .pt checkpoints. | Bit-identical (or within tolerance) on identical seed + identical data. |

### Five file targets

- `data/features.py` — `rate_residual`, `extract_features`, `f_kink` formulas (where the R² bug lives)
- `data/clean.py` — what's per-hour vs annualized in parquet
- `forecaster/train.py` — `DABiGRUCNNDataset` `y` construction, `reconstruct_rate`
- `forecaster/losses.py` — composite loss formulation
- `backtest/run_main.py` — paired monthly-Sharpe bootstrap

### Findings registry

All bugs found get recorded in `docs/research/audit-findings-2026-05-20.md` with: file:line, hypothesis, evidence, fix, and impact on metrics. The R² scale bug is finding #1, pre-recorded.

## 5. R² scale-bug fix (must accompany audit fixes)

### Root cause (verified empirically)

- `r_aave` median in `joined_clean.parquet` = `4.36e-06` (per-hour rate, fractal-defi convention per CLAUDE.md note 4)
- `f_kink_aave(u=0.5)` = `9.78e-03` (annualized, since `AaveKinkParams.slope1=0.04` is annualized APR)
- Ratio ≈ 1/5800 ≈ 1/8760 — the `365×24` factor.
- `rate_residual = r − f_kink(u)` mixes per-hour vs annualized → ε dominated by −f_kink → wrong scale → R² catastrophic.

### Chosen fix — **Option 3: Explicit annualized columns**

`data/features.py:extract_features` adds two explicit columns:

```python
out["r_aave_annual"]     = df["r_aave"]     * 365 * 24  # per-hour → annualized
out["r_compound_annual"] = df["r_compound"] * 365 * 24
```

and `rate_residual` is called on the annualized rates:

```python
out["eps_aave"]     = rate_residual(out["r_aave_annual"], df["u_aave"], params_a)
out["eps_compound"] = rate_residual(out["r_compound_annual"], df["u_compound"], params_c)
```

`forecaster/train.py:TARGET_COLS` updated to `("r_aave_annual", "r_compound_annual")`. `reconstruct_rate` semantics unchanged — both ε and f_kink(u) are now in annualized scale → reconstructed `r_hat` is annualized → matches the new annualized target.

### Why Option 3 (not 1 or 2)

- **Unit-in-name** — column names carry units explicitly. The next reviewer / future-author / linter cannot silently mismatch.
- **MSE numerical scale ~1e-4** — well-conditioned gradients (per-hour scale would be ~1e-12 → underflow risk).
- Touches only `features.py` + one constant in `train.py`. Strategy code (`predictive_mcdm.py`) is **unchanged** because it already annualizes on its own boundary (`lending_rate * 365 * 24`) — confirmed consistent after audit check.

### Expected metrics after fix + retrain

Pre-registered targets from `PROJECT_2_PLAN.md` §16 + §9:

- OOS R² per protocol ∈ **[0.15, 0.40]** (currently catastrophic negative → expected to land in range)
- wPearson similar or higher than current (currently 0.61 Aave / −0.08 Compound on test — Compound likely to improve with correct scale)
- Direction accuracy 55–65 % (currently 76.5 % — may regress slightly when scale is correct; H1 power should improve)
- H1 ΔSharpe ≥ 0.2 — likelihood goes UP after fix because correct scale changes MCDM behaviour; we cannot pre-judge, but the test is honest.

## 6. Execution plan — parallel tracks (11 days)

```
Day 1     │ Audit Track A (math): 6 checks against 5 files
          │ Audit Track B (code): line-by-line of the same 5 files
          │ ── parallel ──
          │ Deep research subagent runs in background (5+1 topics, 2023-2026 lit)
Day 2     │ Consolidate audit findings → batch-fix in one PR-style commit
          │ Start Colab retrain (background, ~30 min) with all fixes applied
          │ Paper outline drafted while retrain runs
Day 3     │ Verify post-fix metrics (R² > 0, others within pre-registered ranges)
          │ If outside ranges → ONE more retrain with hyperparameter tweak (capped)
          │ Lock in metrics → fill_whitepaper_results substitutes 91 macros
Day 4-5   │ Draft §1 Introduction + §2 Background+Related Work (using deep-research output)
          │ Draft §3 Methodology
Day 6-7   │ Draft §4 LOB recap (concise) + §5 DeFi-MCDM experiment (3.5 pages, the bulk)
Day 8-9   │ Draft §6 Cross-domain Discussion + §7 Limitations + §8 Conclusion
          │ All figures finalized (architecture, equity curves, per-quarter, forecast-quality)
Day 10    │ Format conversion: NeurIPS-style → ICICPE template (IEEE or LNCS — TBD)
          │ Reference polish; figure captions; abstract finalization
Day 11    │ Final review pass; submission via icicpe.org portal; WQU affiliation flagged
```

**Critical path:** audit completion (Day 1–2) gates the retrain (Day 2). Retrain gates the metrics (Day 3). Metrics gate the experiment section (Day 6–7). Format conversion can be deferred to Day 10.

**Slack:** Day 11 is buffer; Day 3 has a one-retrain hyper-parameter tweak budget.

## 7. Risks & mitigations

| Risk | Probability | Mitigation |
|---|---|---|
| Audit finds 3+ additional bugs requiring multiple retrains | Medium | Cap at 2 retrains; if more bugs surface, document them as "limitations" rather than fix all |
| Post-fix R² still outside [0.15, 0.40] | Medium | Honest reporting; H0-publishable framing is **already** the contract |
| Deep-research returns weak related-work | Low | Author has extensive prior reading; backstop is `DEEP_RESEARCH.md` already in repo |
| Format conversion (NeurIPS → ICICPE) takes longer than 1 day | Low | Day 11 buffer absorbs slip |
| WQU affiliation paperwork unclear | Low | User checks `icicpe.org` directly; not our blocker |
| Colab session expires before zip retrieval | Already-mitigated | Notebook cell 11 auto-zips for one-shot pull |
| Co-author / advisor signoff required | Unknown | User confirms |

## 8. Out of scope

- The smart-contract vulnerability paper (`Solovev_SS_Multi-Level_Smart_Contract_Defense.tex`) — **separate submission**.
- Extra+1 / Extra+2 PRs to `Logarithm-Labs/fractal-defi` upstream — may be referenced as side-deliverables but not the paper subject.
- Public push to `github.com/SergeySolovyev/predictive-mcdm-defi` — user controls timing; spec-doc doesn't decide.
- WQU affiliation paperwork — user's logistics.

## 9. Success criteria

- ICICPE submission accepted into the portal by **2026-05-31 23:59 (author's local)**.
- Paper ≤ 12 pages in ICICPE template.
- All numerical claims in the paper are traceable to a CSV in `results/tables/` AND to a `\newcommand` in `whitepaper/sections/09_results.tex`.
- Reproducibility section names: GitHub repo URL, figshare DOIs (LOB + this), exact `fractal-defi` git tag, exact ONNX SHA256.
- No `R² < 0` artifact; no `0.00 \%` placeholder; no unit-mismatch warning in audit registry by submission.

## 10. Open questions for user review

- [ ] ICICPE template: IEEE Conference style or LNCS Springer? (Determines column count + reference style — affects Day 10 work.)
- [ ] WQU affiliation: list `WorldQuant University` as primary or secondary affiliation? (Determines free-attendance eligibility but is a footnote.)
- [ ] After this spec is approved → invoke `writing-plans` skill to produce the Day-by-day implementation plan.

---

**Next step after user approves this spec:** invoke `superpowers:writing-plans` to generate the detailed implementation plan (TDD-style, file-by-file, day-by-day).
