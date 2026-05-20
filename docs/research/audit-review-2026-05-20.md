# Audit Batch-Fix Code Quality Review

**Reviewer:** subagent-driven-development code reviewer
**Commit reviewed:** 0416ccf013d8377c88704aadea2fe9a7c1346061
**Date:** 2026-05-20

## Verdict
APPROVED WITH MINOR ISSUES

The six in-scope audit findings (#1, #2, #5, #6, #7, #8) are each addressed
by code that targets the documented root cause (not just the symptom). The
spec's Option 3 ("Explicit annualized columns") is implemented faithfully.
All 41 in-scope pytest cases pass; smoke training shows both Aave and
Compound wPearson positive (qualitative result that the previous run's
compound wPearson = −0.08 catastrophe is fixed). Nothing critical blocks
the next Colab GPU run. A handful of nice-to-have polish items follow.

## Strengths

1. **Spec compliance — Option 3 implemented exactly.** `data/features.py`
   emits `r_aave_annual` / `r_compound_annual` and routes both
   `rate_residual` and `cross_protocol_spread` through them.
   `forecaster/train.py:TARGET_COLS = ("r_aave_annual", "r_compound_annual")`.
   Strategy is unchanged because it already annualizes at the boundary
   (spec §5, lines 99-103 say this is the intended outcome).

2. **Finding #7 root-cause fix, not symptom patch.** Pure-torch
   `f_kink_torch_aave` / `f_kink_torch_compound` mirror the numpy
   `_aave_supply_rate` / `_compound_supply_rate` semantics exactly
   (Compound has no `reserve_factor` multiplication, matching numpy).
   `torch.where(u <= u_opt, below, above)` selects the right branch and
   keeps the computation graph intact. The new contract test
   `test_finding_7_gradient_flows_through_u_hat` directly asserts non-zero
   `grad[..., 0]` on `model_out`, which would have caught the bug.

3. **Finding #8 defense-in-depth.** Two layers of protection:
   (a) `data/clean.py:_clamp_utilization` clamps `u_aave` / `u_compound`
   to [0, 1] in the source parquet (the audit logged 102 rows with
   `u_aave > 1.0`); (b) `reconstruct_rate` applies `torch.sigmoid` to the
   raw u_hat logits before f_kink. Strategy `_run_forecaster` mirrors the
   sigmoid in numpy via `1 / (1 + exp(-x))`. Train and inference are now
   numerically symmetric (verified by smoke parity max|diff| = 1.34e-7).

4. **Finding #5 — z-score with no leakage, persisted, re-applied.**
   `DABiGRUCNNDataset.__init__` either *computes* stats (train fold,
   `stats=None`) or *consumes* them (val/test fold, no leakage).
   `main()` writes `data/cached/feature_stats.json` from the train fold;
   strategy's `_lazy_init_forecaster` loads the same file; constant
   columns (`std <= 1e-6`) bypass division — clean and safe. ONNX-side
   normalization in `_run_forecaster` matches dataset-side exactly
   (`np.where(std > 1e-6, std, 1.0)` mirrors `np.where(std > 1e-6, std, 1.0)`).

5. **Finding #6 reproducibility.** `_seed_all` covers torch, numpy,
   python `random`, and `torch.cuda.manual_seed_all`. Called from both
   `Trainer.__init__` (before optimizer/scheduler construction so AdamW
   state is deterministic) AND `Trainer.fit` (so re-fitting an existing
   Trainer is also reproducible). `TrainConfig.seed = 42` is a stable
   default. The contract test
   `test_finding_6_seed_reproducibility_first_batch_loss` asserts
   `|loss1 − loss2| < 1e-5`, which is the right semantic check.

6. **Tests are non-trivial.** Each new test in `tests/test_unit_contracts.py`
   maps 1:1 to a finding, asserts behavior (not implementation detail),
   and would fail on the broken code. The synthetic generator update in
   `tests/test_data_pipeline.py` (divide by `HOURS_PER_YEAR`) keeps the
   pre-existing `test_extract_features_eps_close_to_zero_for_on_curve_synth`
   test honest after the convention change.

7. **CLAUDE.md constraint #6 respected in new file.**
   `tests/test_unit_contracts.py` puts `import torch` before numpy/pandas
   and does NOT add `from __future__ import annotations` — correct per
   the Windows c10.dll DLL-order workaround.

## Issues (severity-ordered)

### Critical
*(none)*

### Important

- **(Important) Smoke-train wPearson values differ from implementer's
  claim.** The implementer reports
  `val/wpearson_aave=+0.376, val/wpearson_compound=+0.379`. Re-running
  `scripts.local_smoke_train --epochs 1 --max-rows 1500 --force` in this
  review produced `wp_aave=+0.224, wp_compound=+0.551`. The qualitative
  signal (both positive, compound no longer −0.08) is reproduced and
  parity-check (`max|diff|=1.34e-7`) is well under the 1e-4 threshold,
  so the gradient-flow fix is doing real work. But two consecutive
  invocations of a "reproducibility-fixed" trainer giving different val
  metrics suggests `_seed_all` may not be enough to lock down
  smoke-train output ordering (DataLoader worker generators? cuDNN
  determinism? `local_smoke_train`'s outer RNG state?). The contract
  test asserts first-batch *training* loss reproducibility, not full
  val-loop reproducibility. Worth a follow-up to confirm whether
  `scripts/local_smoke_train.py` itself seeds before calling the
  trainer (out of scope for this commit but flagged for the bundle-regen
  task).

- **(Important) ONNX export carries raw logits, but `model.py` docstring
  still calls index 0 "u_hat", not "u_hat_logit".** Lines 25, 138, 165,
  187 of `forecaster/model.py` describe the output as
  `[u_hat | eps_corr]`. After Finding #8, the actual semantics is
  `[u_hat_logit | eps_corr]` (post-sigmoid in train-time
  `reconstruct_rate`, post-sigmoid in strategy `_run_forecaster`). Not a
  bug — train/inference parity is correct — but the next reader of the
  ONNX I/O contract will be misled. One-line docstring fix.

### Nice-to-have

- **(Nice-to-have) `_seed_all` defined before `import numpy as np`.**
  `forecaster/train.py` lines 39-50 define `_seed_all` referencing `np`,
  but `import numpy as np` is at line 52. The function body is only
  evaluated at call time (after numpy is imported, in `Trainer.__init__`),
  so this works. Pure aesthetics — moving the `import numpy as np` block
  above `_seed_all` reads better.

- **(Nice-to-have) Pre-existing `from __future__ import annotations` in
  `forecaster/train.py`:21 violates CLAUDE.md constraint #6.** Per
  CLAUDE.md: "Files that `import torch` must put `import torch` BEFORE
  any other import — Therefore those files cannot use
  `from __future__ import annotations`." Line 21 has the future import
  before `import torch` at line 26. This was NOT introduced by 0416ccf
  (pre-existing), but if a Windows env regresses on c10.dll loading,
  this will bite. The new `tests/test_unit_contracts.py` correctly
  avoids the pattern. Worth a separate cleanup commit.

- **(Nice-to-have) `f_kink_torch_*` boundary case at `u == u_opt`.**
  `torch.where(u <= u_opt, below, above)` evaluates both branches.
  For `u_opt = 0.92` (Aave) and `u_opt = 0.93` (Compound) the
  denominators `(1 - u_opt)` and `(u - kink)` are non-zero in practice.
  If kink params ever land at `u_opt == 1.0`, `above` divides by zero
  → NaN that selects-out via `torch.where`. Defensive `clamp_min(1e-6)`
  on `(1 - u_opt)` would future-proof. Low priority; current params
  are safe.

- **(Nice-to-have) New helper `_seed_all` lacks a type-hint return
  annotation in keeping with the rest of the file's style.** Already
  has `seed: int` argument hint and a docstring — minor.

## Verification results

- **pytest output (network-excluded):**
  `41 passed, 1 deselected in 9.38s`. All 10 new contract tests pass
  alongside the 31 pre-existing tests (no regressions).
- **smoke-train:** `val/wpearson_aave = +0.2240`,
  `val/wpearson_compound = +0.5510`, `ONNX parity max|diff| = 1.341e-07`.
  Both wPearsons positive (vs implementer's claimed +0.376 / +0.379 —
  qualitatively the same result, see Important issue above).
  Direction acc (aave > comp @ t+12h): 0.496.
- **Feature panel cardinality:** `extract_features` emits 26 columns
  on a 500-row joined_clean.parquet sample (≥ 24 expected by spec, plus
  `r_aave_annual` / `r_compound_annual`).
- **Data clamp:** `joined_clean.parquet` now has
  `u_aave.max() <= 1.0 + 1e-9` (was 1.0149 pre-fix).
- **Train/inference parity:** strategy applies sigmoid + same z-score
  stats as training. Contract test for eps magnitude parity passes
  (`|eps_strategy - eps_dataset| < 1e-9`).

## Recommendation for next steps

- [x] Proceed to Task 6 (regenerate Colab bundle).

Optional polish (can ride on a future commit, not blocking):

- [ ] Update `forecaster/model.py` docstrings to call output index 0
  `u_hat_logit` (or `u_hat_raw`) to reflect post-Finding-#8 semantics.
- [ ] Move `import numpy as np` above `_seed_all` in `forecaster/train.py`.
- [ ] Investigate whether `scripts/local_smoke_train.py` seeds before
  invoking the trainer; if not, plumb `cfg.seed` through to reproduce
  the implementer's exact +0.376 / +0.379 numbers.
- [ ] Address pre-existing `from __future__ import annotations` on
  `forecaster/train.py:21` per CLAUDE.md constraint #6.
- [ ] Defensive `clamp_min(1e-6)` on kink denominators in
  `f_kink_torch_aave` / `f_kink_torch_compound` as future-proofing.
