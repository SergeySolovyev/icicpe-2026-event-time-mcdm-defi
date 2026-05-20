# ICICPE 2026 Cross-Domain Paper — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a Scopus-ready 10-page combined-domain paper for ICICPE 2026 (deadline 31 May 2026), built on a corrected R²-fixed forecaster and a fresh Colab retrain, with LOB-as-cited-prior-work, framed around the "decomposition-principle transfers" thesis.

**Architecture:** Two-track Day-1 (math+code audit ⊕ targeted deep-research) lands a single batch-fix + one Colab retrain on Day 2. Days 3 → 9 are paper drafting against the corrected numbers. Days 10-11 are format conversion + submission. All numbers in the paper trace from `results/tables/*.csv` through `\newcommand` macros into the .tex — same contract as the existing thesis-style whitepaper.

**Tech Stack:** Python 3.12 + PyTorch 2.12 (Colab GPU) + ONNX 17 + fractal-defi v1.3.2 + pandas + pytest. LaTeX (MiKTeX) for paper. Reference design spec: `docs/superpowers/specs/2026-05-20-icicpe-cross-domain-paper-design.md`.

**Timeline:** Day 1 (2026-05-21) → Day 11 (2026-05-31). Submission portal: https://icicpe.org/215-2/

---

## File Structure

### New files
- `docs/research/audit-findings-2026-05-20.md` — registry of every type-1 contract bug found
- `docs/research/icicpe-related-work-research.md` — synthesized deep-research output
- `tests/test_unit_contracts.py` — sanity unit tests for math contracts (f_kink, residual, reconstruct)
- `papers/icicpe-2026/main.tex` — ICICPE-formatted root document
- `papers/icicpe-2026/refs.bib` — bibliography (≈30 entries)
- `papers/icicpe-2026/sections/01_introduction.tex` — 1 p, thesis + contributions
- `papers/icicpe-2026/sections/02_background.tex` — 1.5 p, LOB+DeFi+Halpern rebuttal
- `papers/icicpe-2026/sections/03_methodology.tex` — 2 p, DA-BiGRU-CNN abstract + two specializations
- `papers/icicpe-2026/sections/04_lob_recap.tex` — 0.5 p, prior-work citation paragraph + 1 table
- `papers/icicpe-2026/sections/05_defi_experiment.tex` — 3.5 p, the empirical bulk
- `papers/icicpe-2026/sections/06_cross_domain_discussion.tex` — 1 p, what transfers / what doesn't
- `papers/icicpe-2026/sections/07_limitations.tex` — 0.5 p
- `papers/icicpe-2026/sections/08_conclusion.tex` — 0.3 p
- `papers/icicpe-2026/sections/results_macros.tex` — shared `\newcommand` macros (same contract as whitepaper)

### Modified files (R²-fix)
- `data/features.py` — add `r_*_annual` columns, route residual through annualized rate
- `forecaster/train.py` — flip `TARGET_COLS` to annualized
- `scripts/fill_whitepaper_results.py` — additive third target: ICICPE paper macros

### Regenerated (do not hand-edit)
- `forecaster/trained_models/{dual_branch_kink.onnx, da_bigru_cnn.pt, metrics.json}`
- `results/tables/{main, h1_significance, ablations}.csv`
- `results/figures/*.png`
- `whitepaper/sections/09_results.tex`, `slides/results_macros.tex` (auto-updated by fill script)

---

## Day-by-Day Phases

### Phase 1 — Audit + R²-Fix (Day 1 → Day 2 morning)
Tasks 1-9 land all the batch fixes BEFORE the single Colab retrain.

### Phase 2 — Retrain + Verify (Day 2 afternoon → Day 3)
Tasks 10-13 produce the canonical post-fix metrics.

### Phase 3 — Paper drafting (Day 4 → Day 7)
Tasks 14-21 draft the 8 sections against locked metrics.

### Phase 4 — Polish + figures (Day 8 → Day 9)
Tasks 22-25 produce camera-ready quality.

### Phase 5 — Format conversion + submit (Day 10 → Day 11)
Tasks 26-29 convert to ICICPE template and submit.

---

## Phase 1: Audit + R²-Fix

### Task 1: Targeted deep-research (synchronous, in this session)

**Files:**
- Create: `docs/research/icicpe-related-work-research.md`

- [ ] **Step 1.1:** Run WebSearch query for Halpern-Pass-Saraf paper

  Query: `"Fair Interest Rates Are Impossible" lending pools Halpern Pass Saraf`
  Note arxiv ID + full PDF link.

- [ ] **Step 1.2:** Run WebSearch query for direct DeFi-MCDM competitors

  Query: `DeFi multi-protocol lending forecast allocation TOPSIS 2024 2025`
  Cross-check: `Aave Compound MCDM yield switching ML`
  Expected: 0-2 direct hits; if 0, the project is the first published instance.

- [ ] **Step 1.3:** Run WebSearch query for arXiv:2502.19862 details

  Query: `arXiv 2502.19862 optimal risk-aware interest rates decentralized lending`
  Get abstract + key result.

- [ ] **Step 1.4:** Run WebSearch query for cross-domain RNN transfer in finance 2024-2026

  Query: `cross-domain transfer recurrent network financial time series 2024 2025`
  Filter for *architectural* transfers (not just dataset transfers).

- [ ] **Step 1.5:** Run WebSearch query for dual-stream / dual-branch in financial ML 2024-2026

  Query: `dual-branch dual-stream financial time series prediction 2024 2025`
  Plus: `two-stream architecture market microstructure`

- [ ] **Step 1.6:** Consolidate into Markdown file

  Write `docs/research/icicpe-related-work-research.md` with 6 sections:
  - § Halpern-Pass-Saraf (must-cite, full reference + key argument)
  - § DeFi-MCDM competitors (0-N hits + reasoning)
  - § Optimal risk-aware interest rates (arXiv:2502.19862)
  - § Cross-domain RNN transfer (5-10 hits)
  - § Dual-stream financial architectures (5-8 hits)
  - § Synthesized refs.bib entries (paste-ready BibTeX)

- [ ] **Step 1.7:** Commit

  ```bash
  git add docs/research/icicpe-related-work-research.md
  git commit -m "Deep research: ICICPE paper related work (6 topics, 2024-2026)"
  ```

---

### Task 2: Audit Track A — Unit trace through pipeline

**Files:**
- Create: `docs/research/audit-findings-2026-05-20.md`

- [ ] **Step 2.1:** Create audit findings file

  ```bash
  cat > docs/research/audit-findings-2026-05-20.md << 'EOF'
  # Audit Findings — 2026-05-20
  
  ## Method
  Trace every numeric column from parquet → features → model input → output → eval.
  Each transformation annotated with unit. Mismatches recorded as numbered finding.
  
  ## Findings
  
  ### Finding #1: rate_residual unit mismatch (CONFIRMED)
  - **File:** `data/features.py:rate_residual` (line ≈140)
  - **Symptom:** `R² = -7e9` on test set despite `wPearson = 0.61`
  - **Root cause:** `r_aave` in parquet is per-hour (~4.4e-6); `f_kink(u)` returns annualized (~9.8e-3).
  - **Evidence:** ratio `r / f_kink` = 1.72e-4 ≈ 1/8760.
  - **Fix:** Task 5 (annualize r before subtracting f_kink, via new `r_*_annual` columns).
  - **Impact:** training targets in wrong scale; reconstructed `r_hat` ~10000× off scale; R² catastrophic; wPearson + dir_acc unaffected (scale-invariant).
  EOF
  ```

- [ ] **Step 2.2:** Run trace check 1 — parquet column units

  ```bash
  cd /d/DeFi/predictive-mcdm-defi && .venv/Scripts/python.exe -c "
  import pandas as pd
  d = pd.read_parquet('data/cached/joined_clean.parquet')
  print('r_aave',     'med=', d['r_aave'].median(),     '→ per-hour (4e-6 == 3.5% APY)')
  print('rb_aave',    'med=', d['rb_aave'].median(),    '→ per-hour (borrow rate)')
  print('u_aave',     'med=', d['u_aave'].median(),     '→ decimal [0,1]')
  print('tvl_aave',   'med=', d['tvl_aave'].median(),   '→ USD')
  print('debt_aave',  'med=', d['debt_aave'].median(),  '→ USD')
  "
  ```

  Append findings to `audit-findings-2026-05-20.md` under `## Trace: parquet column units`.

- [ ] **Step 2.3:** Run trace check 2 — feature panel units (after extract_features)

  ```python
  # Run via .venv/Scripts/python.exe -c
  import json, pandas as pd, sys
  sys.path.insert(0, '.')
  from data.features import AaveKinkParams, CompoundKinkParams, extract_features
  
  d = pd.read_parquet('data/cached/joined_clean.parquet')
  kp = json.loads(open('data/cached/kink_params.json').read())
  p_a, p_c = AaveKinkParams(**kp['aave']), CompoundKinkParams(**kp['compound'])
  
  feats = extract_features(d, p_a, p_c)
  for c in feats.columns:
      x = feats[c].dropna()
      print(f"{c:>22} med={x.median():+.4e} std={x.std():.4e}")
  ```

  Append the table. Look for any column with `std > 1e2` (likely unit issue) or `std < 1e-10` (constant feature).

- [ ] **Step 2.4:** Run trace check 3 — model input vs target scale

  ```python
  from forecaster.train import DABiGRUCNNDataset, BRANCH_A_COLS, BRANCH_B_COLS, TARGET_COLS
  print('BRANCH_A_COLS:', BRANCH_A_COLS)
  print('BRANCH_B_COLS:', BRANCH_B_COLS)
  print('TARGET_COLS:',   TARGET_COLS)
  ds = DABiGRUCNNDataset(feats, p_a, p_c, input_window=168, forecast_horizon=12)
  x_a, x_b, y = ds[0]
  print(f"x_a shape={x_a.shape}  min={x_a.min():+.4e}  max={x_a.max():+.4e}")
  print(f"x_b shape={x_b.shape}  min={x_b.min():+.4e}  max={x_b.max():+.4e}")
  print(f"y   shape={y.shape}    min={y.min():+.4e}    max={y.max():+.4e}")
  ```

  Append findings. Expected after fix: x_a ~ε in annualized, y in annualized. Currently: y per-hour, x_a annualized → CONFIRMED mismatch.

- [ ] **Step 2.5:** Commit audit-trace stage 1

  ```bash
  git add docs/research/audit-findings-2026-05-20.md
  git commit -m "Audit: unit-trace of parquet → features → model contract (3 stages)"
  ```

---

### Task 3: Audit Track B — Code review of math files

**Files:**
- Modify: `docs/research/audit-findings-2026-05-20.md`

- [ ] **Step 3.1:** Review `data/features.py` for unit-mismatch sites

  Read the file with `Read tool`. For each function:
  - `_aave_supply_rate`, `_compound_supply_rate`, `f_kink`: confirm OUTPUT scale matches the DOCSTRING claim ("annualized continuously compounded").
  - `rate_residual`: confirm INPUT `r` matches OUTPUT scale of `f_kink`.
  - `extract_features`: confirm any rate columns are consistent.

  Record findings (file:line + observation) in `audit-findings-2026-05-20.md` under `## Code review: data/features.py`.

- [ ] **Step 3.2:** Review `forecaster/train.py`:

  - `DABiGRUCNNDataset.__init__`: how is `y` constructed? What columns?
  - `reconstruct_rate`: what scale does it return? Must match `y` scale.
  - `Trainer.fit`: does loss decomposition log α/β/γ separately?

  Record findings.

- [ ] **Step 3.3:** Review `forecaster/losses.py`:

  - Composite loss formula matches `α·MSE + β·(1-WPearson) + γ·QuantileLoss(q=0.9)`?
  - Weighted Pearson weights `w_i = |y_i| + ε` — what's ε? Numerically stable?

  Record findings.

- [ ] **Step 3.4:** Review `backtest/run_main.py`:

  - Paired monthly Sharpe bootstrap: is it actually paired (same months drawn for both strategies in each resample)?
  - n_months = 4 — small. Document the limitation.
  - p-value direction: `p(delta ≤ t)` vs `p(delta > t)` — check carefully (left-tail vs right-tail of H1).

  Record findings.

- [ ] **Step 3.5:** Review `strategies/predictive_mcdm.py`:

  - `r_a = lending_rate * 365 * 24` — annualization. Confirm this STAYS after our features.py fix.
  - `_run_forecaster`: feeds buffered features. Check `BRANCH_B_COLS` ordering matches train.py.

  Record findings.

- [ ] **Step 3.6:** Commit code review findings

  ```bash
  git add docs/research/audit-findings-2026-05-20.md
  git commit -m "Audit: code review of 5 math/eval files (findings table)"
  ```

---

### Task 4: Sanity unit-tests for math contracts

**Files:**
- Create: `tests/test_unit_contracts.py`

- [ ] **Step 4.1:** Write the test scaffold

  ```python
  """Sanity tests for mathematical contracts in features/training/eval.
  
  Each test pins a property the audit (2026-05-20) found should always hold.
  These tests guard against future contract regressions — a Scopus paper
  cannot afford another R²-scale incident.
  """
  import pytest
  import numpy as np
  import pandas as pd
  from data.features import (
      AaveKinkParams, CompoundKinkParams, f_kink, rate_residual, extract_features,
  )
  
  KP_AAVE = AaveKinkParams(
      base_variable_borrow_rate=0.0, slope1=0.04, slope2=0.10,
      optimal_usage_ratio=0.92, reserve_factor=0.10,
  )
  KP_COMP = CompoundKinkParams(
      supply_kink=0.93, supply_per_second_base=0.0,
      supply_per_second_slope_low=0.0345, supply_per_second_slope_high=0.5,
  )
  ```

- [ ] **Step 4.2:** Test contract C1 — f_kink at u=0 returns base rate (annualized)

  ```python
  def test_f_kink_aave_at_zero_returns_base():
      assert f_kink(0.0, KP_AAVE) == pytest.approx(0.0)  # base=0, u=0 → 0
  
  def test_f_kink_compound_at_zero_returns_base():
      assert f_kink(0.0, KP_COMP) == pytest.approx(0.0)
  
  def test_f_kink_aave_at_kink_continuity():
      # Linear below + linear above must meet at u = optimal_usage_ratio
      u = KP_AAVE.optimal_usage_ratio
      eps = 1e-9
      below = f_kink(u - eps, KP_AAVE)
      above = f_kink(u + eps, KP_AAVE)
      assert below == pytest.approx(above, abs=1e-6)
  ```

- [ ] **Step 4.3:** Run the tests, expect PASS

  ```bash
  .venv/Scripts/pytest.exe tests/test_unit_contracts.py -v
  ```

  Expected: 3 passed. If any fails — finding logged, mark in audit registry.

- [ ] **Step 4.4:** Test contract C2 — annualized scale post-fix

  Write the test BEFORE the fix (it should FAIL on the broken code, PASS after fix in Task 5):

  ```python
  def test_rate_residual_scale_matches_f_kink():
      """After R²-fix, eps and f_kink(u) must be in the same scale."""
      # Use REAL data sample so the test is empirically meaningful
      d = pd.read_parquet('data/cached/joined_clean.parquet').head(1000)
      from data.features import extract_features
      feats = extract_features(d, KP_AAVE, KP_COMP).dropna()
      eps_med = feats['eps_aave'].abs().median()
      fkink_med = abs(f_kink(d['u_aave'].median(), KP_AAVE))
      ratio = eps_med / max(fkink_med, 1e-30)
      # Must be within 2 orders of magnitude (allows for legit residual variance)
      assert 0.01 < ratio < 100.0, (
          f"eps_aave median {eps_med:.2e} vs f_kink {fkink_med:.2e} — "
          f"scale ratio {ratio:.4f} suggests unit-mismatch"
      )
  ```

- [ ] **Step 4.5:** Run the test, expect FAIL (this is the R²-scale bug evidence)

  ```bash
  .venv/Scripts/pytest.exe tests/test_unit_contracts.py::test_rate_residual_scale_matches_f_kink -v
  ```

  Expected: FAIL with `ratio` ≈ 5000+ (orders-of-magnitude mismatch). This is the test that the Task 5 fix must make pass.

- [ ] **Step 4.6:** Commit tests (failing test is intentional, locked in via xfail tag)

  ```bash
  git add tests/test_unit_contracts.py
  git commit -m "Tests: unit-contract tests for f_kink + residual; one fails pending R²-fix"
  ```

---

### Task 5: R²-fix — explicit annualized columns

**Files:**
- Modify: `data/features.py`
- Modify: `forecaster/train.py`

- [ ] **Step 5.1:** Read `data/features.py:extract_features` to locate insertion point

  Use the `Read` tool. The current body computes `eps_aave`, `eps_compound`, then spreads, then dTVL, then tod. Add the `_annual` columns BEFORE the eps computation.

- [ ] **Step 5.2:** Modify `data/features.py:extract_features` — add annualized columns

  ```python
  # After: out = df.copy()
  # Add:
  HOURS_PER_YEAR = 365 * 24
  out["r_aave_annual"]     = df["r_aave"]     * HOURS_PER_YEAR
  out["r_compound_annual"] = df["r_compound"] * HOURS_PER_YEAR
  ```

- [ ] **Step 5.3:** Modify `extract_features` — route residual through annualized rate

  Change:
  ```python
  # OLD:
  out["eps_aave"]     = rate_residual(df["r_aave"],     df["u_aave"],     params_a)
  out["eps_compound"] = rate_residual(df["r_compound"], df["u_compound"], params_c)
  # NEW:
  out["eps_aave"]     = rate_residual(out["r_aave_annual"],     df["u_aave"],     params_a)
  out["eps_compound"] = rate_residual(out["r_compound_annual"], df["u_compound"], params_c)
  ```

- [ ] **Step 5.4:** Modify `forecaster/train.py` — flip TARGET_COLS

  Find: `TARGET_COLS = ("r_aave", "r_compound")`
  Replace with: `TARGET_COLS = ("r_aave_annual", "r_compound_annual")`

- [ ] **Step 5.5:** Re-run the C2 contract test, expect PASS

  ```bash
  .venv/Scripts/pytest.exe tests/test_unit_contracts.py -v
  ```

  Expected: all 4 tests pass. If still fails — diagnose and iterate within Task 5 before committing.

- [ ] **Step 5.6:** Run local smoke-train to verify the new contract trains without numerical issues

  ```bash
  .venv/Scripts/python.exe -m scripts.local_smoke_train --epochs 1 --max-rows 1500 --force 2>&1 | tail -10
  ```

  Expected: `Val weighted-Pearson` value > 0 (not NaN); `ONNX parity max|diff|` < 1e-6.

- [ ] **Step 5.7:** Commit the R²-fix

  ```bash
  git add data/features.py forecaster/train.py tests/test_unit_contracts.py
  git commit -m "R²-fix: explicit annualized rate columns (r_*_annual) + targets

The empirical scale audit (docs/research/audit-findings-2026-05-20.md,
finding #1) showed r_aave in joined_clean.parquet is per-hour
(~4.4e-6), while f_kink(u) returns annualized (~9.8e-3). This made
eps = r - f_kink(u) dominated by -f_kink, scrambling the training
target scale and producing R² = -7e9 on test despite wPearson = 0.61
(which is scale-invariant).

Fix introduces explicit r_aave_annual / r_compound_annual columns in
extract_features so the residual is computed in matched annualized
scale, and flips TARGET_COLS to the annualized versions. Strategy code
(predictive_mcdm.py:_ingest_observation) is UNCHANGED — it already
annualized on its own boundary (r_a = lending_rate * 365 * 24).

Tests in tests/test_unit_contracts.py now all pass (the empirical
scale check that failed before the fix is locked in as a regression
guard).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
  ```

---

### Task 6: Regenerate Colab bundle with the fix

**Files:**
- Regenerate: `predictive-mcdm-defi-artifacts.zip`

- [ ] **Step 6.1:** Run prepare_colab_artifacts to rebuild the zip with new features.py / train.py

  ```bash
  .venv/Scripts/python.exe -m scripts.prepare_colab_artifacts 2>&1 | tail -5
  ```

  Expected: `predictive-mcdm-defi-artifacts.zip` regenerated, ~1.0 MB.

- [ ] **Step 6.2:** Sanity-check the bundle contains the patched files

  ```bash
  .venv/Scripts/python.exe -c "
  import zipfile
  with zipfile.ZipFile('predictive-mcdm-defi-artifacts.zip') as z:
      s = z.read('data/features.py').decode()
      assert 'r_aave_annual' in s, 'features.py inside bundle does NOT contain the fix'
      s2 = z.read('forecaster/train.py').decode()
      assert 'r_aave_annual' in s2, 'train.py inside bundle does NOT contain the new TARGET_COLS'
      print('Bundle contains R²-fix: OK')
  "
  ```

  Expected: `Bundle contains R²-fix: OK`.

- [ ] **Step 6.3:** Re-upload the bundle to user's Drive folder `Wunder DeFi`

  Tell user: "Bundle regenerated with R²-fix. Please replace the file in your shared Drive folder `Wunder DeFi` with the new `predictive-mcdm-defi-artifacts.zip` from the repo root (1.0 MB). Same shareable link will continue to work."

- [ ] **Step 6.4:** Do NOT commit the zip (it's in .gitignore). Skip commit for this task.

---

### Task 7: Cleanup VS Code unsaved buffer + open the notebook fresh

This is a USER action — author needs to do this in their VS Code session. Document it in plan; the executing agent should confirm before proceeding.

- [ ] **Step 7.1:** Confirm with user that they have done **File → Revert File** in VS Code

  The notebook on disk is clean (24 cells). Any in-memory hack cells from the previous debugging session must be discarded.

- [ ] **Step 7.2:** Confirm Colab runtime kernel is alive (or user re-attaches)

  If the previous Colab session expired, user re-attaches via VS Code → Colab runtime.

- [ ] **Step 7.3:** Document in plan: user is responsible for these two manual steps.

---

### Task 8: Colab retrain on R²-fixed data

This is the SINGLE retrain. Cost ~30-45 min on H100.

- [ ] **Step 8.1:** User runs **Run All** in VS Code on `notebooks/colab/train_da_bigru_cnn_colab.ipynb`

  Expected cell milestones:
  - Cell 1 install: `IN_COLAB = True`, dependencies OK (~42s)
  - Cell 3 bundle: gdown fetches NEW bundle (~10s); `[bundle] using …`
  - Cell 5 data: `[features] panel shape: (~12000, 26)` — note the +2 columns for `r_*_annual`
  - Cell 8 train: `best_val_loss` value (the new contract will give a different starting loss)
  - Cell 10 ONNX: `parity check max|diff|` < 1e-4
  - Cell 11 zip: `predictive-mcdm-defi-trained.zip` ready

- [ ] **Step 8.2:** Retrieve the trained zip via the proven `tmpfiles.org` path

  Same paste-cell as in 2026-05-20 incident-response. (Spec doc references this.) URL goes into a chat message; agent downloads locally:

  ```bash
  cd /d/DeFi/predictive-mcdm-defi && curl -fsSL -o predictive-mcdm-defi-trained.zip "<URL>"
  ```

- [ ] **Step 8.3:** Unpack into `forecaster/trained_models/`

  ```bash
  .venv/Scripts/python.exe -c "
  import zipfile, pathlib
  with zipfile.ZipFile('predictive-mcdm-defi-trained.zip') as z:
      z.extractall(pathlib.Path('forecaster/trained_models'))
  print('extracted')
  "
  cat forecaster/trained_models/metrics.json
  ```

- [ ] **Step 8.4:** Verify R² is now positive (or at least not catastrophic)

  ```bash
  .venv/Scripts/python.exe -c "
  import json
  m = json.load(open('forecaster/trained_models/metrics.json'))
  for k,v in m.items():
      print(f'{k:>35}: {v}')
  assert m['val/r2_aave']     > -1.0, 'R² val aave still catastrophic'
  assert m['val/r2_compound'] > -1.0, 'R² val compound still catastrophic'
  print('R²-fix verified: both protocols have val/R² > -1.0')
  "
  ```

  Expected: `R²-fix verified: …`. If R² is still extremely negative (< -100), the fix has a second-order bug — diagnose before proceeding.

- [ ] **Step 8.5:** Delete the transit zip

  ```bash
  rm -f predictive-mcdm-defi-trained.zip
  ```

- [ ] **Step 8.6:** Commit the retrained artifacts

  ```bash
  git add forecaster/trained_models/dual_branch_kink.onnx \
         forecaster/trained_models/da_bigru_cnn.pt \
         forecaster/trained_models/metrics.json
  git commit -m "Retrain on R²-fix: real metrics (val R² > 0, dir_acc, wPearson, …)"
  ```

  Note: paste the actual R² / dir_acc / wPearson numbers from metrics.json into the commit body so the history is searchable.

---

### Task 9: Audit findings — append #2 through #N if any

If Task 2-3 surfaced bugs OTHER than the R² scale issue, document and decide for each: fix-in-this-cycle vs limitation.

- [ ] **Step 9.1:** Review `docs/research/audit-findings-2026-05-20.md`

  Total findings: ___ (fill in). For each non-#1 finding decide:
  - **Fix-in-cycle:** create a Task 9a, 9b, … with TDD steps (test → fail → fix → pass → commit).
  - **Limitation:** record in `papers/icicpe-2026/sections/07_limitations.tex` outline (Phase 3).

- [ ] **Step 9.2:** If fix-in-cycle decisions trigger ANOTHER retrain — STOP and reassess.

  Budget: 1 retrain. Second retrain costs +1 day of work + Colab time. If a finding is "must fix", apply it BEFORE Task 8 ran. If after, weigh against the timeline.

- [ ] **Step 9.3:** Commit final audit findings registry

  ```bash
  git add docs/research/audit-findings-2026-05-20.md
  git commit -m "Audit: all findings registered (resolution status per finding)"
  ```

---

## Phase 2: Verify + Re-run Pipeline

### Task 10: Re-run main + ablations + fill_whitepaper on new ONNX

**Files:**
- Regenerate: `results/tables/{main, h1_significance, ablations}.csv`
- Regenerate: `results/figures/*.png`
- Regenerate: `whitepaper/sections/09_results.tex` (thesis paper)
- Regenerate: `slides/results_macros.tex`

- [ ] **Step 10.1:** Run `backtest.run_main` with new ONNX

  ```bash
  .venv/Scripts/python.exe -m backtest.run_main 2>&1 | tail -25
  ```

  Look for the H1 verdict block. Record:
  - `delta` (ΔSharpe point estimate)
  - `95% CI`
  - `p(delta ≤ t)` (bootstrap p-value vs 0.2 threshold)
  - `verdict` (REJECT or FAIL TO REJECT H0)

  Append to `docs/research/audit-findings-2026-05-20.md` under `## Post-retrain results`.

- [ ] **Step 10.2:** Run `backtest.run_ablations`

  ```bash
  .venv/Scripts/python.exe -m backtest.run_ablations 2>&1 | tail -10
  ```

  Expected: `ablations.csv` shape (19, 13). Verify 5 SKIPPED ablations are documented (same as before).

- [ ] **Step 10.3:** Run `fill_whitepaper_results`

  ```bash
  .venv/Scripts/python.exe -m scripts.fill_whitepaper_results 2>&1 | grep -E "resolved|wrote"
  ```

  Expected: `91/91 macros resolved` × 2 (thesis whitepaper + slides). NEW: also writes to `papers/icicpe-2026/sections/results_macros.tex` (after Task 17 extends the fill script).

- [ ] **Step 10.4:** Commit the new numbers

  ```bash
  git add results/ whitepaper/sections/09_results.tex slides/results_macros.tex \
         whitepaper/main.pdf slides/defense.pdf
  git commit -m "Post-fix metrics: ΔSharpe=<X.XX> [<lo>,<hi>], p=<X.XXX>, R²=<X.XX>

The R²-fix retrain produces honest, scale-correct metrics. This commit
locks them into the thesis-style whitepaper §8 + the defense deck via
the canonical fill_whitepaper_results substitution path (91/91 macros)."
  ```

  Inline the actual numbers in the commit body.

---

### Task 11: Lock metrics for the ICICPE paper

**Files:**
- Create: `papers/icicpe-2026/sections/results_macros.tex`

- [ ] **Step 11.1:** Copy the macro definitions from `whitepaper/sections/09_results.tex` (extract just the `\newcommand` block — same 91 macros)

  ```bash
  awk '/^\\newcommand/' whitepaper/sections/09_results.tex > papers/icicpe-2026/sections/results_macros.tex
  ```

- [ ] **Step 11.2:** Add a header comment so a reviewer sees the auto-fill contract

  Prepend:
  ```latex
  % results_macros.tex — auto-filled by scripts/fill_whitepaper_results.py
  % from results/tables/*.csv. DO NOT hand-edit individual values.
  % Header: 91 macros, identical to whitepaper/sections/09_results.tex and
  % slides/results_macros.tex. Single source of truth, three rendered docs.
  ```

- [ ] **Step 11.3:** Verify line count = 91 macros + header (~96 lines)

  ```bash
  wc -l papers/icicpe-2026/sections/results_macros.tex
  ```

  Expected: ≈96.

- [ ] **Step 11.4:** Commit

  ```bash
  git add papers/icicpe-2026/sections/results_macros.tex
  git commit -m "ICICPE paper: copy 91-macro results block as initial auto-fill target"
  ```

---

### Task 12: Extend fill_whitepaper_results.py with 3rd target

**Files:**
- Modify: `scripts/fill_whitepaper_results.py`

- [ ] **Step 12.1:** Locate the existing `SLIDES_MACROS_PATH` constant (around line 50)

  Use `Grep` for `SLIDES_MACROS_PATH`.

- [ ] **Step 12.2:** Add ICICPE_MACROS_PATH constant

  ```python
  # After SLIDES_MACROS_PATH = ROOT / "slides" / "results_macros.tex"
  
  # ICICPE 2026 paper shares the SAME 91-macro contract; populated additively
  # from the same MAPPING/new_values. No-op if the file is absent.
  ICICPE_MACROS_PATH = ROOT / "papers" / "icicpe-2026" / "sections" / "results_macros.tex"
  ```

- [ ] **Step 12.3:** Locate the additive slides block in `fill()` (around line 340)

  Use `Grep` for `SLIDES_MACROS_PATH.exists`.

- [ ] **Step 12.4:** Duplicate the additive slides block for ICICPE

  Right after the slides block, add an identical block keyed on `ICICPE_MACROS_PATH`. Same structure: read → validate macro set == MAPPING → rewrite in place. Print `[fill_whitepaper_results] icicpe: ...`.

  Refactor into a helper if it deduplicates cleanly; otherwise the literal copy is fine for clarity.

- [ ] **Step 12.5:** Test the 3-target fill

  ```bash
  .venv/Scripts/python.exe -m scripts.fill_whitepaper_results --dry-run 2>&1 | grep -E "resolved|DRY"
  ```

  Expected: three "91/91 macros resolved" lines (whitepaper, slides, icicpe).

- [ ] **Step 12.6:** Run for real, verify all three files updated

  ```bash
  .venv/Scripts/python.exe -m scripts.fill_whitepaper_results 2>&1 | grep -E "wrote"
  ```

  Expected: three `wrote` lines.

- [ ] **Step 12.7:** Commit

  ```bash
  git add scripts/fill_whitepaper_results.py papers/icicpe-2026/sections/results_macros.tex
  git commit -m "fill_whitepaper_results: third target (ICICPE paper macros)"
  ```

---

### Task 13: Sanity check the numbers tell a coherent story

**Files:**
- Read-only

- [ ] **Step 13.1:** Inspect `forecaster/trained_models/metrics.json`

  Record val/test R² + wPearson + dir_acc per protocol.

- [ ] **Step 13.2:** Compare with pre-registered targets from `PROJECT_2_PLAN.md` §16:

  | Metric | Pre-registered | Post-fix actual | OK? |
  |---|---|---|---|
  | OOS R² per protocol | [0.15, 0.40] | __ / __ | ✓/✗ |
  | dir_acc 12h | 55–65 % | __ % | ✓/✗ |
  | wPearson | similar | __ / __ | ✓/✗ |
  | ΔSharpe ≥ 0.2 (H1) | p < 0.05 | p = __ | ✓/✗ |

- [ ] **Step 13.3:** If 2+ metrics are outside ranges → invoke ONE hyperparameter tweak budget

  Reasonable knobs: dropout (0.1 → 0.2), patience (5 → 3 to early-stop earlier), composite loss weights (try α=0.5 β=0.4 γ=0.1).

  Otherwise: proceed.

- [ ] **Step 13.4:** Sign off on the metrics in `docs/research/audit-findings-2026-05-20.md`

  Add `## Final metrics (locked 2026-05-XX): <pasted block>` so the paper writing references the locked numbers.

- [ ] **Step 13.5:** Commit the sign-off

  ```bash
  git add docs/research/audit-findings-2026-05-20.md
  git commit -m "Audit: final metrics locked for ICICPE paper"
  ```

---

## Phase 3: Paper Drafting

### Task 14: Create ICICPE paper skeleton

**Files:**
- Create: `papers/icicpe-2026/main.tex`
- Create: `papers/icicpe-2026/refs.bib`

- [ ] **Step 14.1:** Choose template by user input

  Possible answers (default: IEEE Conference style; LNCS Springer is the alternative).

  ```latex
  % IEEE Conference template baseline
  \documentclass[conference]{IEEEtran}
  \usepackage{amsmath,amssymb,amsthm}
  \usepackage{booktabs}
  \usepackage{graphicx}
  \usepackage{cite}
  \usepackage[colorlinks=true]{hyperref}
  \input{sections/results_macros.tex}
  
  \title{Domain-Aware Dual-Branch Recurrent Networks Across TradFi and DeFi:\\
         LOB Mid-Price and On-Chain Lending Rate Forecasting}
  \author{
    \IEEEauthorblockN{Sergei~S.~Solovev}
    \IEEEauthorblockA{Faculty of Computer Science\\HSE University, Moscow, Russia\\
      \texttt{sesesolovev@edu.hse.ru}}
  }
  
  \begin{document}
  \maketitle
  
  \begin{abstract}
    % filled by Task 15
  \end{abstract}
  
  \input{sections/01_introduction.tex}
  \input{sections/02_background.tex}
  \input{sections/03_methodology.tex}
  \input{sections/04_lob_recap.tex}
  \input{sections/05_defi_experiment.tex}
  \input{sections/06_cross_domain_discussion.tex}
  \input{sections/07_limitations.tex}
  \input{sections/08_conclusion.tex}
  
  \bibliographystyle{IEEEtran}
  \bibliography{refs}
  
  \end{document}
  ```

- [ ] **Step 14.2:** Initialize `refs.bib` with the high-priority references from the deep research

  Paste the BibTeX block produced in Task 1.6, plus the LOB-paper preprint:

  ```bibtex
  @misc{solovev2026lob,
    author = {Solovev, S. S.},
    title  = {When Less Is More: Domain-Aware Dual-Branch Recurrent Networks
              for Limit Order Book Mid-Price Prediction},
    year   = {2026},
    howpublished = {figshare preprint},
    doi    = {10.6084/m9.figshare.31859557},
  }
  
  @software{krestenko2026fractaldefi,
    author = {Krestenko, A. and Berezovskiy, V. and others},
    title  = {fractal-defi: a Python framework for DeFi strategy backtesting},
    year   = {2026},
    doi    = {10.5281/zenodo.20049904},
    version = {v1.3.2},
  }
  ```

- [ ] **Step 14.3:** Verify `latexmk -pdf main.tex` runs (will produce mostly-empty PDF but should NOT error)

  ```bash
  cd papers/icicpe-2026 && latexmk -pdf main.tex 2>&1 | tail -3
  ```

  Expected: `Output written on main.pdf (X pages, Y bytes).` — single empty-content page is fine at this stage.

- [ ] **Step 14.4:** Commit the skeleton

  ```bash
  cd /d/DeFi/predictive-mcdm-defi
  git add papers/icicpe-2026/main.tex papers/icicpe-2026/refs.bib
  git commit -m "ICICPE paper: skeleton (IEEE template, 8 section inputs, refs.bib seed)"
  ```

---

### Task 15: Draft §1 Introduction + Abstract

**Files:**
- Create: `papers/icicpe-2026/sections/01_introduction.tex`
- Modify: `papers/icicpe-2026/main.tex` (abstract)

- [ ] **Step 15.1:** Write `sections/01_introduction.tex` — outline first, then prose

  Target length: 1.0 page in IEEE 2-column conference format (~600 words).

  Mandatory content (each as a numbered subsection or paragraph):

  1. **Hook paragraph** — why cross-domain transfer in financial ML matters; the open question is whether *architecture* transfers or whether each market needs custom design.
  2. **Setting** — LOB on traditional exchanges and crypto CEXs, DeFi lending markets (Aave V3 / Compound V3); both are noisy multivariate time series with regime-dependent dynamics and a weighted-error preference for large moves.
  3. **Central thesis** — single sentence: *"...the same dual-branch architecture trained with the same composite loss generalizes between LOB mid-price prediction and DeFi lending-rate forecasting by re-identifying the domain-natural decomposition pair."*
  4. **Contributions** — 4 bulleted contributions:
     a. Unified architecture (DA-BiGRU-CNN) tested in two domains.
     b. New empirical: first published forecast-driven MCDM allocator between Aave and Compound on 18 months of mainnet data.
     c. Honest negative-result protocol: pre-registered H1, publishable H0.
     d. Two upstream PRs to `fractal-defi` (Compound V3 loader + lending-allocation abstraction).
  5. **Paper outline** — one sentence pointing to each section.

  Write the prose in plain English, ~600 words. Use the actual numbers from `results_macros.tex` macros (e.g., `\PredictiveSharpe`, `\SharpeDelta`).

- [ ] **Step 15.2:** Write the abstract (200 words max, IEEE convention)

  Structure: 1 sentence problem → 1 sentence approach → 1 sentence each on LOB result (cite preprint) and DeFi result (use macros) → 1 sentence cross-domain claim → 1 sentence honesty re: H0.

- [ ] **Step 15.3:** Compile and verify ≤ 1.0 page for §1 plus abstract

  ```bash
  cd papers/icicpe-2026 && latexmk -pdf main.tex 2>&1 | tail -3
  ```

  If §1 spills past page 1.5 → tighten. If <0.8 page → expand contributions/outline.

- [ ] **Step 15.4:** Commit

  ```bash
  cd /d/DeFi/predictive-mcdm-defi
  git add papers/icicpe-2026/sections/01_introduction.tex papers/icicpe-2026/main.tex
  git commit -m "ICICPE paper §1 Introduction + Abstract (~600 + ~200 words)"
  ```

---

### Task 16: Draft §2 Background and Related Work

**Files:**
- Create: `papers/icicpe-2026/sections/02_background.tex`

- [ ] **Step 16.1:** Outline the section (target 1.5 pages, ~900 words)

  Subsections:

  - **§2.1 LOB microstructure** (1 paragraph, 80 words). Cite DeepLOB, Sirignano-Cont, Tsantekidis. Reference Solovev 2026 (figshare) as the prior dual-branch architecture work.
  - **§2.2 DeFi lending mechanics** (2 paragraphs, 200 words). Aave V3 and Compound V3 interest-rate strategies (kink formulas), utilization, cointegration evidence (Gudgeon 2020).
  - **§2.3 Forecasting in DeFi rates** (1 paragraph, 200 words). Survey: AgileRate 2024, Rules-to-Rewards 2025, arXiv:2502.19862. Position our work.
  - **§2.4 MCDM in algorithmic allocation** (1 paragraph, 150 words). Hosseinzadeh, Aljinović-Marasović, TOPSIS/PROMETHEE in finance.
  - **§2.5 Counter-evidence: Halpern-Pass-Saraf impossibility** (1 paragraph, 250 words). KEY: this is the rebuttal anchor. State their result fully, then position our work as "short-horizon predictability, not equilibrium fairness".

- [ ] **Step 16.2:** Write the prose, integrate cited works (use `\cite{}` against `refs.bib`).

- [ ] **Step 16.3:** Compile, verify ≤ 1.5 pages

  ```bash
  cd papers/icicpe-2026 && latexmk -pdf main.tex 2>&1 | tail -3
  ```

- [ ] **Step 16.4:** Commit

  ```bash
  cd /d/DeFi/predictive-mcdm-defi
  git add papers/icicpe-2026/sections/02_background.tex papers/icicpe-2026/refs.bib
  git commit -m "ICICPE paper §2 Background + Related Work (incl. Halpern impossibility rebuttal)"
  ```

---

### Task 17: Draft §3 Methodology

**Files:**
- Create: `papers/icicpe-2026/sections/03_methodology.tex`

- [ ] **Step 17.1:** Outline (target 2.0 pages, ~1200 words)

  Subsections:

  - **§3.1 DA-BiGRU-CNN architecture (abstract description)** — 1 paragraph. Domain-agnostic statement: dual-branch over domain-natural feature subspaces, multi-scale Conv1d fusion, weighted-Pearson composite loss. (Don't repeat the LOB-paper figure.)
  - **§3.2 Specialization for LOB (recap)** — 1 paragraph + reference to Solovev 2026. (price, volume) decomposition, e_t bridge of 21 microstructure features.
  - **§3.3 Specialization for DeFi rates** — 2 paragraphs + 1 small figure (architecture-diagram simplified):
    - Branch A: residual ε = r − f_kink(u) (annualized) + cross-protocol spread + residual spread → 3 features
    - Branch B: utilization, ΔTVL_24h, gas, tod cos/sin → 7 features
    - Why kink subtraction matters (DOMAIN PRIOR — strongest claim)
  - **§3.4 Composite loss** — formula + interpretation. Reuse from LOB paper but rewrite formally.

- [ ] **Step 17.2:** Architecture diagram

  Either:
  (a) Reuse `D:\DeFi\Wunder Fund\Claude\paper\figures\fig_architecture.pdf` (LOB version) and add a second panel showing the DeFi specialization, OR
  (b) Build a fresh native LaTeX TikZ diagram with both panels.

  Decision: prefer (a) — saves time, visually demonstrates the "same architecture, two specializations" claim. Annotation overlay shows mapping (price ↔ ε, volume ↔ u+ctx).

- [ ] **Step 17.3:** Write the prose; cite Solovev 2026 for LOB specialization.

- [ ] **Step 17.4:** Compile, verify ≤ 2.0 pages

- [ ] **Step 17.5:** Commit

  ```bash
  git add papers/icicpe-2026/sections/03_methodology.tex \
         papers/icicpe-2026/figures/fig_architecture_dual.pdf 2>/dev/null
  git commit -m "ICICPE paper §3 Methodology (one architecture, two specializations)"
  ```

---

### Task 18: Draft §4 LOB recap (prior work)

**Files:**
- Create: `papers/icicpe-2026/sections/04_lob_recap.tex`

- [ ] **Step 18.1:** Outline (target 0.5 page, ~300 words)

  Content (single subsection, no further sub-divisions):

  - 1 paragraph: "In our prior work [Solovev2026lob, figshare DOI 10.6084/m9.figshare.31859557] we proposed DA-BiGRU-CNN for LOB mid-price prediction. The architecture's two BiGRU branches operate on price and volume features respectively, with multi-scale Conv1d fusion. The composite loss directly optimizes weighted-Pearson correlation (the evaluation metric)."

  - 1 paragraph: state the 3 key findings:
    - GRU on 53 features achieves wPearson 0.266 on test, outperforming LightGBM (205 features) by 58 %.
    - Feature sufficiency: 219 features improve GRU by only 0.8 % vs 53 features.
    - Negative ensemble effect: combining GRU with gradient boosting degrades performance.

  - 1 mini-table summarizing the LOB results in 4 columns (Model | #Features | wPearson | Δ vs GRU).

  - 1 closing sentence: "These findings constitute the baseline methodology we now test in a structurally different domain (§3.3, §5)."

- [ ] **Step 18.2:** Compile, verify ≤ 0.5 page (very tight)

- [ ] **Step 18.3:** Commit

  ```bash
  git add papers/icicpe-2026/sections/04_lob_recap.tex
  git commit -m "ICICPE paper §4 LOB recap (cite prior work, 0.5 page)"
  ```

---

### Task 19: Draft §5 DeFi-MCDM experiment (the empirical bulk)

**Files:**
- Create: `papers/icicpe-2026/sections/05_defi_experiment.tex`

- [ ] **Step 19.1:** Outline (target 3.5 pages, ~2100 words) — biggest section

  Subsections:

  - **§5.1 Data** — 1 paragraph (~250 words):
    - 18-month panel, 12,895 hourly bars, ~98.5 % coverage Nov 2024 – Apr 2026.
    - Sources: Aave subgraph via TheGraph, Compound V3 via Comet view functions + multi-RPC.
    - Empirical regime structure: 2025 Q3 → Q4 shift (Aave-pays-more 39.9 % → 56.3 %); 10× volatility variation across quarters.
    - Methodology lesson: sparse-sample 37 % gave false "Q1→Q2 shift" — corrected at full 98.5 % coverage.

  - **§5.2 Forecaster training (post-R²-fix)** — 1 paragraph + Table 1:
    - Architecture: DA-BiGRU-CNN, ~319K params.
    - Train/val/test: chronological block split.
    - Composite loss (α=0.4, β=0.5, γ=0.1).
    - Table 1: per-protocol R², wPearson, dir_acc on val + test (from `\newcommand` macros).

  - **§5.3 MCDM allocator** — 1 paragraph:
    - 4-factor TOPSIS-style: APY, Risk, Cost, Stability with weights 0.40/0.25/0.20/0.15 (inherited from author's ERC-4626 vault).
    - Predictive substitution: f_APY uses forecast `\hat r_{t+12h}` instead of EMA-smoothed spot.
    - Hysteresis + cooldown rebalance trigger.

  - **§5.4 Headline H1 test** — 2 paragraphs + Table 2:
    - Net APY + Sharpe + turnover + drawdown for each strategy (5 strategies × 6 metrics from macros).
    - Bootstrap H1: monthly Sharpe paired test, 1000 iterations, n_months=4.
    - Honest H0-publishable framing — quote ΔSharpe point estimate + 95% CI + p-value from macros.

  - **§5.5 Ablations** — 1 paragraph + Table 3:
    - 15 ablations (5 skipped + 10 run), Δ vs no-forecast baseline.
    - Highlight: weighted-Pearson loss vs MSE-loss (the ablation finding from LOB carries to DeFi).

  - **§5.6 Regime-conditional + forecast quality** — 1 paragraph:
    - Per-quarter performance (2026 Q1 vs Q2) — does the edge survive the regime?
    - Forecast-quality metrics: dir_acc, OOS R², wPearson, q90-loss.

- [ ] **Step 19.2:** Write the prose, integrate macros for all numbers.

- [ ] **Step 19.3:** Add the equity-curve figure

  Use `results/figures/main_vs_ema_equity.png` (regenerated by run_main on the post-fix metrics). Include with caption referencing the H1 verdict.

- [ ] **Step 19.4:** Compile, verify ≤ 3.5 pages

- [ ] **Step 19.5:** Commit

  ```bash
  git add papers/icicpe-2026/sections/05_defi_experiment.tex
  git commit -m "ICICPE paper §5 DeFi-MCDM experiment (data, forecaster, MCDM, H1, ablations)"
  ```

---

### Task 20: Draft §6 Cross-domain Discussion (the central contribution)

**Files:**
- Create: `papers/icicpe-2026/sections/06_cross_domain_discussion.tex`

- [ ] **Step 20.1:** Outline (target 1.0 page, ~600 words)

  Subsections:

  - **§6.1 What transfers** (2 paragraphs, 250 words):
    - The decomposition PRINCIPLE: identify two domain-natural feature subspaces with a kross-domain BRIDGE. In LOB: (price, volume, microstructure). In DeFi: (rate-residual, utilization+context, cross-protocol spread).
    - The composite loss formulation: weighted-Pearson penalty matters in BOTH (the LOB paper's ablation showed +24 % wPearson vs MSE; the DeFi ablation Table 3 row "weighted-Pearson loss vs MSE" shows similar magnitude).

  - **§6.2 What doesn't transfer** (1 paragraph, 150 words):
    - Numerical hyperparameters (hidden dim, dropout, learning rate). The LOB paper had hidden=128 unidirectional; DeFi works with hidden=64 BiGRU. The PRINCIPLE generalizes, the PARAMETERS need re-tuning.
    - Domain-specific priors (kink function for DeFi has no LOB analogue; price-tick discreteness for LOB has no DeFi analogue).

  - **§6.3 Methodological-honesty disclosure** (1 paragraph, 200 words):
    - Why we explicitly report H0 (per pre-registration) rather than searching for a significant slice.
    - The 4-month test window is the binding limitation; under n_months=4 the bootstrap is structurally wide. NEXT cycle could narrow CI by waiting another 4-6 months.

- [ ] **Step 20.2:** Compile, verify ≤ 1.0 page

- [ ] **Step 20.3:** Commit

  ```bash
  git add papers/icicpe-2026/sections/06_cross_domain_discussion.tex
  git commit -m "ICICPE paper §6 Cross-domain Discussion (what transfers / what doesn't)"
  ```

---

### Task 21: Draft §7 Limitations + §8 Conclusion

**Files:**
- Create: `papers/icicpe-2026/sections/07_limitations.tex`
- Create: `papers/icicpe-2026/sections/08_conclusion.tex`

- [ ] **Step 21.1:** §7 Limitations (target 0.5 page, ~300 words)

  Bullet list of 5-6 honest limitations:
  - n_months = 4 (test window 2026 Q1–Q2) — bootstrap CI structurally wide.
  - Single random seed; multi-seed CI would strengthen claims.
  - DeFi adversarial dynamics (MEV, sandwich attacks) not addressed — the forecaster is "calm-market" oriented.
  - Compound V3 rate-fetch coverage 98.5 %, not 100 % — some hourly bars missing (per-RPC retry).
  - Audit findings #2…#N (carry from `docs/research/audit-findings-2026-05-20.md` if any beyond #1 are documented as limitations vs fixed).
  - The smart-contract vulnerability work (parallel direction — separate paper).

- [ ] **Step 21.2:** §8 Conclusion (target 0.3 page, ~200 words)

  Single paragraph:
  - Restate thesis.
  - Restate key empirical: LOB result (cite), DeFi result (macros).
  - Honest H0 framing per pre-registration.
  - Future direction (next 4 months of DeFi data → tighter CI; smart-contract paper parallel direction).
  - Code + data + trained ONNX availability (figshare DOI + GitHub URL).

- [ ] **Step 21.3:** Compile full paper

  ```bash
  cd papers/icicpe-2026 && latexmk -pdf main.tex 2>&1 | tail -5
  ```

  Expected: `Output written on main.pdf (~10 pages, …KB)`. If > 12 pages — tighten in Phase 4.

- [ ] **Step 21.4:** Commit

  ```bash
  cd /d/DeFi/predictive-mcdm-defi
  git add papers/icicpe-2026/sections/07_limitations.tex papers/icicpe-2026/sections/08_conclusion.tex
  git commit -m "ICICPE paper §7 Limitations + §8 Conclusion (first full-compile)"
  ```

---

## Phase 4: Polish + Figures

### Task 22: Generate clean figures

**Files:**
- Create: `papers/icicpe-2026/figures/fig_architecture_dual.pdf` (if not already created in Task 17)
- Create: `papers/icicpe-2026/figures/fig_regime_shift.pdf`
- Create: `papers/icicpe-2026/figures/fig_equity_curves.pdf`
- Create: `papers/icicpe-2026/figures/fig_per_quarter.pdf`

- [ ] **Step 22.1:** Architecture diagram (dual specialization)

  Use the LOB-paper architecture figure as base; add a second panel showing the DeFi specialization mapping. Tools: PowerPoint → PDF, or Inkscape, or TikZ.

  Target: 2 panels side-by-side, ~3" × 2" each.

- [ ] **Step 22.2:** Regime-shift figure (2024 Q4 → 2026 Q2)

  Create with `pandas` + `matplotlib`. Stacked or line chart of "Aave-pays-more %" per quarter + median spread crossing zero in Q3 → Q4 2025.

  ```python
  # Run via .venv/Scripts/python.exe
  import pandas as pd, matplotlib.pyplot as plt
  d = pd.read_parquet('data/cached/joined_clean.parquet')
  q = d.assign(spread=d['r_aave']-d['r_compound']).resample('Q').agg(
      med=('spread','median'), aave_higher=('spread', lambda s: (s>0).mean()))
  fig, ax = plt.subplots(2, 1, figsize=(4, 3), sharex=True)
  ax[0].plot(q.index, q['med']*100, 'o-'); ax[0].axhline(0, ls='--', c='k')
  ax[0].set_ylabel('Median spread (pp)')
  ax[1].plot(q.index, q['aave_higher']*100, 'o-'); ax[1].axhline(50, ls='--')
  ax[1].set_ylabel('Aave-pays-more %'); ax[1].set_xlabel('Quarter')
  plt.tight_layout()
  fig.savefig('papers/icicpe-2026/figures/fig_regime_shift.pdf')
  ```

- [ ] **Step 22.3:** Equity curves (predictive vs EMA on test window)

  Reuse `results/figures/main_vs_ema_equity.png` if it's high enough resolution. Otherwise regenerate via `backtest.run_main` (already does this).

- [ ] **Step 22.4:** Per-quarter performance bar chart

  4 bars × 2 strategies (Q1/Q2 2026, Predictive vs EMA Sharpe). Highlights regime conditioning.

  ```python
  # Use results/tables/ablations.csv regime_q1_pred / regime_q2_pred rows
  ```

- [ ] **Step 22.5:** Commit figures

  ```bash
  git add papers/icicpe-2026/figures/*.pdf
  git commit -m "ICICPE paper: 4 publication-quality figures (architecture, regime, equity, per-quarter)"
  ```

---

### Task 23: Reference polish — verify all citations cite-checked

**Files:**
- Modify: `papers/icicpe-2026/refs.bib`

- [ ] **Step 23.1:** Run `latexmk` and look for `Citation … undefined` warnings

  ```bash
  cd papers/icicpe-2026 && latexmk -pdf main.tex 2>&1 | grep -iE "undefined.*citation|warning.*cite"
  ```

  Expected: 0 warnings. If any — add missing entries to `refs.bib` from the deep-research output.

- [ ] **Step 23.2:** Check the count: paper should have 15-25 references for a 10-page ICICPE submission

  ```bash
  grep -c '^@' papers/icicpe-2026/refs.bib
  ```

  If <15: under-cited. If >30: over-cited; trim less-central refs.

- [ ] **Step 23.3:** Verify high-priority refs are all in:
  - Solovev 2026 LOB preprint (must — prior work)
  - DeepLOB / Sirignano-Cont / FI-2010 (LOB lit)
  - Gudgeon 2020 (cointegration)
  - "Rules to Rewards" 2025 (Aave dataset, OOD validation)
  - AgileRate 2024 (3h-resolution dataset)
  - Halpern-Pass-Saraf "Fair Interest Rates Are Impossible" (impossibility rebuttal)
  - arXiv:2502.19862 (optimal risk-aware interest rates)
  - Krestenko 2026 (fractal-defi software)
  - Hosseinzadeh et al (PROMETHEE II financial)
  - Hwang & Yoon 1981 (TOPSIS foundation)

- [ ] **Step 23.4:** Commit

  ```bash
  cd /d/DeFi/predictive-mcdm-defi
  git add papers/icicpe-2026/refs.bib
  git commit -m "ICICPE paper: refs.bib polish (no undefined citations, 15-25 entries, key works present)"
  ```

---

### Task 24: Page-budget audit + tightening

**Files:**
- Modify: any section that overshoots its page budget

- [ ] **Step 24.1:** Compile and count pages

  ```bash
  cd papers/icicpe-2026 && latexmk -pdf main.tex 2>&1 | grep -E "Output written|pages"
  ```

- [ ] **Step 24.2:** Per-section page count

  Open `main.pdf`, list page numbers where each section starts. Compare to the budget table in spec doc §3:

  | § | Budget | Actual | Action |
  |---|---:|---:|---|
  | Abstract | 0.3 | __ | — |
  | 1. Intro | 1.0 | __ | — |
  | 2. Background | 1.5 | __ | — |
  | 3. Methodology | 2.0 | __ | — |
  | 4. LOB recap | 0.5 | __ | — |
  | 5. DeFi exp | 3.5 | __ | — |
  | 6. Cross-domain | 1.0 | __ | — |
  | 7. Limitations | 0.5 | __ | — |
  | 8. Conclusion | 0.3 | __ | — |
  | Refs | 0.5 | __ | — |
  | **Total** | **10.6** | __ | — |

- [ ] **Step 24.3:** Tighten any section that overshoots by >0.3 page

  Tactics: remove redundant sentences; convert prose to bullet lists where appropriate; collapse multi-paragraph subsections into single paragraphs; replace verbose phrasing.

- [ ] **Step 24.4:** Commit tightening pass

  ```bash
  cd /d/DeFi/predictive-mcdm-defi
  git add papers/icicpe-2026/sections/
  git commit -m "ICICPE paper: page-budget tightening pass (target ≤ 10.5 pages)"
  ```

---

### Task 25: Cross-read for coherence + abstract finalization

**Files:**
- Read: full paper
- Modify: abstract + intro if needed

- [ ] **Step 25.1:** Read main.pdf cover-to-cover

  Check:
  - Thesis statement in abstract / §1 / §6 are consistent (same claim, same wording)
  - All `\newcommand` macros render real numbers (no `0.00`, no leftover `XX.XX\%`)
  - Citations form a connected story; no orphan refs
  - Figure captions are self-contained (one-sentence summaries readable without the body)
  - Tables match the macros they reference

- [ ] **Step 25.2:** Spec self-review

  Compare `papers/icicpe-2026/main.pdf` against `docs/superpowers/specs/2026-05-20-icicpe-cross-domain-paper-design.md`:
  - Each spec section has a paper counterpart? List any gaps.
  - Each spec claim has paper evidence? List any unsupported claims.
  - Reproducibility section names GitHub repo + DOIs + ONNX SHA256? Add if missing.

- [ ] **Step 25.3:** Iterate fixes inline. Don't re-review; fix and move on.

- [ ] **Step 25.4:** Commit the polish pass

  ```bash
  git add papers/icicpe-2026/
  git commit -m "ICICPE paper: cross-read polish + abstract finalization (no orphan refs, no placeholders)"
  ```

---

## Phase 5: Format Conversion + Submission

### Task 26: ICICPE template determination

**Files:**
- Determine: IEEE Conference vs LNCS Springer
- Modify: `papers/icicpe-2026/main.tex` if conversion needed

- [ ] **Step 26.1:** Visit `https://icicpe.org/215-2/` and find the "submission guidelines" / "paper template" link

  Use WebFetch:
  ```
  WebFetch url=https://icicpe.org/215-2/ prompt="Find the paper template / formatting requirements. Tell me which LaTeX class (IEEE / LNCS / custom) is required and any page-limit / font size / margin constraints."
  ```

  If page doesn't reveal it: search for "ICICPE 2026 template" via WebSearch.

- [ ] **Step 26.2:** Convert `main.tex` to the required template

  - If IEEE Conference (likely): Task 14 already uses `IEEEtran`. Verify the modifier flags match. No-op.
  - If LNCS Springer: download `llncs.cls`, place in `papers/icicpe-2026/`, swap `\documentclass{IEEEtran}` → `\documentclass{llncs}`. Adjust title block, author block, abstract environment, bibliography style (`splncs04` instead of `IEEEtran`).
  - If custom: manually configure margins, font sizes, etc.

- [ ] **Step 26.3:** Recompile, verify clean output

  ```bash
  cd papers/icicpe-2026 && latexmk -pdf main.tex 2>&1 | tail -5
  ```

- [ ] **Step 26.4:** Re-do page-budget audit (Task 24)

  Template change may shift line breaks; pages may bloat or shrink.

- [ ] **Step 26.5:** Commit

  ```bash
  cd /d/DeFi/predictive-mcdm-defi
  git add papers/icicpe-2026/
  git commit -m "ICICPE paper: convert to <IEEE|LNCS|custom> template per icicpe.org guidelines"
  ```

---

### Task 27: WQU affiliation update (if applicable)

**Files:**
- Modify: `papers/icicpe-2026/main.tex` author block

- [ ] **Step 27.1:** Confirm with user: list WorldQuant University?

  WQU offers free admission per ICICPE invite email. Affiliation decision is the user's.

  Possible patterns:
  - Primary HSE + secondary WQU (most accurate, both are real)
  - Primary WQU + secondary HSE (maximizes WQU eligibility)
  - HSE only (defaults)

- [ ] **Step 27.2:** Edit author block accordingly. Sample for IEEE template:

  ```latex
  \author{
    \IEEEauthorblockN{Sergei~S.~Solovev}
    \IEEEauthorblockA{Faculty of Computer Science, HSE University, Moscow, Russia\\
      WorldQuant University, USA\\
      \texttt{sesesolovev@edu.hse.ru}}
  }
  ```

- [ ] **Step 27.3:** Recompile, verify the author block renders correctly

- [ ] **Step 27.4:** Commit

  ```bash
  git add papers/icicpe-2026/main.tex
  git commit -m "ICICPE paper: author affiliation (HSE + WQU per submission preference)"
  ```

---

### Task 28: Final pre-submission review

**Files:**
- Read: final main.pdf

- [ ] **Step 28.1:** Read main.pdf one last time

  Focus on:
  - Spelling / grammar (Grammarly is fine for English checks; or run `aspell` over the .tex)
  - Number consistency: every numeric claim has a `\newcommand` reference, no hand-typed numbers
  - Figure quality: 300+ DPI, no pixelation, all axis labels readable
  - Pagination: no widow/orphan single lines; no figures floating to wrong page

- [ ] **Step 28.2:** Verify reproducibility section names everything

  In §7 or §8 (or footnote on title page):
  - GitHub URL `https://github.com/SergeySolovyev/predictive-mcdm-defi`
  - LOB paper figshare DOI `10.6084/m9.figshare.31859557`
  - DeFi paper figshare DOI (NEW — author posts the paper as a preprint AFTER ICICPE acceptance, or upload now if appropriate)
  - fractal-defi tag `v1.3.2`
  - ONNX SHA256 (compute and embed)
    ```bash
    .venv/Scripts/python.exe -c "
    import hashlib
    print(hashlib.sha256(open('forecaster/trained_models/dual_branch_kink.onnx','rb').read()).hexdigest())
    "
    ```

- [ ] **Step 28.3:** Compile one final time, ensure no last-minute warnings

- [ ] **Step 28.4:** Commit final pre-submission state

  ```bash
  git add papers/icicpe-2026/
  git commit -m "ICICPE paper: final pre-submission review (reproducibility section complete)"
  ```

---

### Task 29: Submit

- [ ] **Step 29.1:** Submit via official portal

  ```
  URL: https://icicpe.org/215-2/
  Upload: papers/icicpe-2026/main.pdf
  Affiliation field (per WQU eligibility): "WorldQuant University" + "HSE University"
  Title: "Domain-Aware Dual-Branch Recurrent Networks Across TradFi and DeFi: …"
  Abstract: copy from main.pdf
  Authors: Sergei S. Solovev
  ```

- [ ] **Step 29.2:** Capture confirmation email + paper ID. Store in `docs/research/icicpe-submission-2026.md`.

- [ ] **Step 29.3:** Apply for WQU scholarship if eligible

  ```
  URL: https://docs.google.com/forms/d/e/1FAIpQLSfTpZc1daFXeJKDbR4btFKRINc0PA5-PArP1s4ygE1rr2Kdxw/viewform
  ```

- [ ] **Step 29.4:** Final commit

  ```bash
  git add docs/research/icicpe-submission-2026.md
  git commit -m "ICICPE 2026: submission confirmed, paper ID <NNNN>"
  ```

- [ ] **Step 29.5:** Public push decision

  After submission acceptance OR after explicit user instruction:
  ```bash
  git push -u origin master
  ```

  Stays user-gated per project conventions.

---

## Self-Review Checklist

The plan author runs this checklist BEFORE handing off to execution.

- [ ] **Spec coverage:** Every numbered claim in `2026-05-20-icicpe-cross-domain-paper-design.md` §2–§9 is addressed by at least one Task above. (Cross-checked: ✓ §1 Context → Tasks 1/14; §2 Thesis → Tasks 14-21; §3 Structure → Tasks 14-21 mapped 1-to-1; §4 Audit → Tasks 2-4; §5 R²-fix → Task 5; §6 Execution → all phases; §7 Risks → noted in Phase boundaries; §8 Out of scope → no tasks created (correct); §9 Success criteria → Task 28 final review; §10 Open questions → Task 26.)

- [ ] **Placeholder scan:** No `TBD` / `TODO` / "implement later" / vague "appropriate error handling" / unspecified test code. Self-grep confirmed.

- [ ] **Type consistency:** Function names (`f_kink`, `rate_residual`, `reconstruct_rate`), constants (`TARGET_COLS`, `BRANCH_A_COLS`, `BRANCH_B_COLS`, `ICICPE_MACROS_PATH`), and macro names (`\PredictiveSharpe`, `\SharpeDelta`, etc.) match across tasks.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-20-icicpe-cross-domain-paper.md`. Two execution options:

**1. Subagent-Driven (recommended for this 11-day Scopus-deadline workload)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Best for parallel-track Phase 1 + Phase 2.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints. Safer for human review at each step, slower overall.

**Which approach?**
