# Contract audit — `predictive-mcdm-defi`
Date: 2026-05-20
Auditor: Claude (Opus 4.7, 1M ctx)
Scope: type-1 mathematical-contract bugs (unit/scale/convention/reproducibility)
Method: 6-check protocol from `docs/superpowers/specs/2026-05-20-icicpe-cross-domain-paper-design.md`

## Finding #1: R² scale catastrophe — rate residual mixes per-hour and annualized rates (critical)
- **File:line**: `data/features.py:128-140` (`rate_residual`), `data/features.py:194-195` (`extract_features` produces `eps_aave`, `eps_compound`)
- **Symptom**: Trained model produces wPearson_aave_test = 0.6074 BUT R²_aave_test = −7.0×10⁹ and R²_compound_test = −4.6×10¹⁰. The model captures relative ranking (correlation) but absolute level is catastrophically off-scale.
- **Root cause hypothesis**: `joined_clean.parquet` stores `r_aave`, `r_compound` as **per-hour rates** (median ~4.4×10⁻⁶; cf. `data/clean.py:159` `spot_lend = 0.034 / (365*24)`). `f_kink(u; params)` returns **annualized** rate (~2.5×10⁻² at median utilization). `rate_residual = r − f_kink(u)` mixes scales by a factor of 8760, so `eps_*` ≈ −f_kink(u) for all rows. Branch A learns essentially `f_kink(u)` of the past 168h. Then in `reconstruct_rate` (`forecaster/train.py:147-166`) `r_hat = f_kink(u_hat) + eps_corr` lives on the annual scale (~10⁻²) while the target `y = r_aave` (training target via `TARGET_COLS = ("r_aave", "r_compound")`, train.py:89) is per-hour (~10⁻⁶). MSE term in composite loss compares annual prediction vs per-hour target.
- **Evidence**: (from unit-trace diagnostic, command below)
  - Median `r_aave` in joined_clean.parquet = 4.36×10⁻⁶ (per hour)
  - Median `u_aave` = 0.805; `f_kink(0.805, aave_params)` = 2.535×10⁻² (annualized)
  - Median `eps_aave` in extract_features = −2.55×10⁻²  → essentially `−f_kink(u)`, i.e. the per-hour `r_aave` contributes negligibly
  - Std(`eps_aave`) = 1.40×10⁻², std(`r_aave`) = 3.30×10⁻⁶ → 4-orders-of-magnitude mismatch
  - Dataset sample `y[0]` = (5.14×10⁻⁶, 7.35×10⁻⁶) ← per-hour scale
  - `metrics.json`: `test/wpearson_aave=0.6074` (Pearson is scale-invariant) but `test/r2_aave=-7.03e9` (R² is scale-sensitive)
- **Fix**: Introduce explicit `r_aave_annual`, `r_compound_annual` columns in `data/features.py:extract_features` BEFORE residual computation. Use annual columns for both residuals AND for the training target. Minimal patch:
  ```python
  # data/features.py: extract_features
  out["r_aave_annual"]     = df["r_aave"] * 365 * 24
  out["r_compound_annual"] = df["r_compound"] * 365 * 24
  out["eps_aave"]     = rate_residual(out["r_aave_annual"],    df["u_aave"],    params_a)
  out["eps_compound"] = rate_residual(out["r_compound_annual"], df["u_compound"], params_c)
  # cross_protocol_spread inputs must use _annual columns too
  ```
  Then in `forecaster/train.py:89`:
  ```python
  TARGET_COLS = ("r_aave_annual", "r_compound_annual")
  ```
- **Impact**: Without this fix, R² remains in the −10⁹ range, MSE term dominates composite loss by 10¹⁰, alpha/beta balance is meaningless, and the model effectively reduces to a Pearson-only objective. Strategy-side scoring still works (it annualizes via `* 365 * 24`), but the H1 hypothesis cannot be tested with confidence.
- **Disposition**: fix-in-cycle (already designed per task brief)

---

## Audit complete — additional findings

### Finding #2: Train/inference scale mismatch in branch-A residual `eps_*` (critical, depends on Finding #1)
- **File:line**: `strategies/predictive_mcdm.py:151-157` vs `data/features.py:194-195`
- **Symptom**: Even *after* Finding #1 is fixed, the strategy and training pipelines compute `eps_aave` differently:
  - Training (`extract_features`): `eps = r_per_hour − f_kink(u)` (annual) — broken (Finding #1)
  - Inference (`_ingest_observation`): `r_a = lending_rate * 365 * 24`; `eps_a = r_a − f_kink(u_a)` — both annualized, **consistent**
- **Root cause hypothesis**: The strategy author wrote the *correct* annual-vs-annual convention in inference, but `extract_features` was never updated to match. The fix designed for Finding #1 (`r_*_annual` columns) will align the two, but ONLY if the fix uses the annual column for `rate_residual`. If the fix is applied incorrectly (e.g. only changing `TARGET_COLS` but leaving `rate_residual` reading raw `r_aave`), the train/inference mismatch survives and the ONNX model trained on `eps ∈ [−1.5×10⁻¹, −1.0×10⁻²]` will be fed `eps ∈ [−10⁻³, +10⁻³]` at inference, predicting garbage.
- **Evidence**:
  - `strategies/predictive_mcdm.py:151`: `r_a = float(getattr(gs_a, "lending_rate", 0.0)) * 365 * 24`
  - `strategies/predictive_mcdm.py:156`: `eps_a = r_a - float(f_kink(u_a, self._kink_aave))` ⇒ annual − annual
  - `data/features.py:194`: `out["eps_aave"] = rate_residual(df["r_aave"], df["u_aave"], params_a)` ⇒ per_hour − annual
- **Fix**: The Finding #1 fix MUST route `r_*_annual` through `rate_residual` (and through `cross_protocol_spread`'s `r_a`, `r_c` args). After applying:
  ```python
  out["eps_aave"]     = rate_residual(out["r_aave_annual"],     df["u_aave"],    params_a)
  spreads = cross_protocol_spread(out["r_aave_annual"], out["r_compound_annual"], ...)
  ```
- **Impact**: Without verifying both pieces of Finding #1 fix, the trained ONNX will be useless at inference — Branch A receives features outside the distribution it learned on.
- **Disposition**: fix-in-cycle (verify Finding #1 patch covers both training residual AND target)

---

### Finding #3: Compound TVL/debt columns are all zeros — branch B `dTVL_compound_24h` is a dead input (important)
- **File:line**: `data/clean.py:114-115` (rename) and `data/fetch_compound_via_rpc.py` (upstream placeholder)
- **Symptom**: In `joined_clean.parquet`, `tvl_compound` and `debt_compound` are 0.0 for all 13,105 rows (min=0, max=0, std=0). Downstream `dTVL_compound_24h` in the feature panel is therefore identically 0.
- **Root cause hypothesis**: Per CLAUDE.md S3c, the RPC fetcher uses `total_supplied_usd = 0.0` as a placeholder until USD conversion is wired. `data/features.py:208-215` already documents this with `fillna(0.0)` to avoid all-NaN from 0/0 pct_change. So `dTVL_compound_24h` is dead.
- **Evidence**: Diagnostic shows `dTVL_compound_24h` median = 0, std = 0, min = 0, max = 0 across the entire feature panel.
- **Fix**: Either (a) wire USD conversion in `fetch_compound_via_rpc.py` by multiplying base-unit liquidity by 1e−6 (USDC has 6 decimals) and a USD oracle price; or (b) drop `dTVL_compound_24h` from `BRANCH_B_COLS` to free a model input slot for something signal-bearing. Option (b) is faster:
  ```python
  # forecaster/train.py:84-88
  BRANCH_B_COLS = (
      "u_aave", "u_compound",
      "dTVL_aave_24h",      # keep
      "gas_gwei", "tod_sin", "tod_cos",
  )
  # ForecasterConfig.branch_b_input_dim = 6   (in model.py)
  # Also drop from _ingest_observation in strategies/predictive_mcdm.py
  ```
- **Impact**: 1/7 (~14%) of Branch B's input capacity is wasted on a constant zero. Branch B's BiGRU and Conv1d will still train, but with reduced effective context. Not a correctness bug; a capacity/efficiency bug.
- **Disposition**: document-as-limitation OR drop column

---

### Finding #4: `gas_gwei` is constant 30.0 in training data — another dead input (important)
- **File:line**: `data/clean.py` (does NOT add gas), `data/fetch_gas_eth.py:16` (`raise NotImplementedError`), `notebooks/colab/train_da_bigru_cnn_colab.ipynb:449-451` (silently fills 30.0)
- **Symptom**: `data/fetch_gas_eth.py` is a stub (raises NotImplementedError); `data/clean.py` never adds a `gas_gwei` column. The Colab training notebook silently fills `DATA["gas_gwei"] = 30.0` with the warning "stub, constant -> ignored by BiGRU". Branch B input dim 5 (gas_gwei) is therefore constant for the entire training set.
- **Root cause hypothesis**: Gas data integration is deferred (CLAUDE.md "Current blockers" mentions ETHEREUM_RPC_URL). The Colab notebook hand-codes a fallback constant rather than crashing.
- **Evidence**:
  - `data/fetch_gas_eth.py:16`: `raise NotImplementedError("Implement in Week 1 Day 3")`
  - notebook line 410: `"[data] gas_gwei missing -> filled with 30.0 (stub, constant -> ignored by BiGRU)"`
  - Feature panel diagnostic: `gas_gwei  median=3.00e+01  std=0.00e+00  min=3.00e+01  max=3.00e+01`
- **Fix**: Either implement `fetch_gas_eth.py` (Dune query `SELECT date_trunc('hour', evt_block_time), median(gas_price/1e9) FROM gas.gas_price WHERE …`) or drop `gas_gwei` from BRANCH_B_COLS together with the Finding #3 fix (Branch B drops from 7 to 5 cols then). The MCDM cost factor in `compute_criteria_vector` is unaffected (uses spot gas at decision time).
- **Impact**: Wastes another Branch B input. Combined with Finding #3, ~28% of Branch B's input dimension is dead weight. Also: the MCDM `f_cost` term in `predictive_mcdm.py:208` will compute identical cost across train/val/test using gas=30, biasing the cost normalization but matching baseline.
- **Disposition**: fix-in-cycle (implement gas fetcher OR drop column)

---

### Finding #5: No input feature normalization — z-score step from plan §4.4 never implemented (important)
- **File:line**: `forecaster/train.py:92-141` (`DABiGRUCNNDataset.__init__`); plan reference in `data/clean.py:11-12` ("z-score using TRAINING statistics only (no leakage)")
- **Symptom**: Features fed to the GRUs are on wildly different magnitudes:
  - Branch A `eps_aave` ~ 10⁻²; `residual_spread` ~ 10⁻²
  - Branch B: `u_aave` ~ 10⁰, `dTVL_aave_24h` ~ 10⁻³, `gas_gwei` = 30 (constant), `tod_sin/cos` ~ 10⁰
  - `gas_gwei` (30) dominates the BiGRU input by 30× over `u_aave` (~0.8)
- **Root cause hypothesis**: The plan §4.4 step 3 ("z-score using TRAINING statistics only") is documented in clean.py's docstring but no code applies it. Branch A has LayerNorm on its GRU output (`model.py:93`), but the *input* to the GRU is never normalized. Branch B has no input or output LayerNorm.
- **Evidence**: `grep -n "BatchNorm\|LayerNorm\|StandardScaler\|scaler\|normaliz" forecaster/train.py data/features.py` returns nothing (only LayerNorm inside model.py on internal hidden states).
- **Fix**: Compute z-score stats on the training fold and apply consistently:
  ```python
  # forecaster/train.py:DABiGRUCNNDataset.__init__
  self.x_a_mean = self.x_a.mean(axis=0); self.x_a_std = self.x_a.std(axis=0) + 1e-8
  self.x_b_mean = self.x_b.mean(axis=0); self.x_b_std = self.x_b.std(axis=0) + 1e-8
  self.x_a = (self.x_a - self.x_a_mean) / self.x_a_std
  self.x_b = (self.x_b - self.x_b_mean) / self.x_b_std
  ```
  Stats from training set must be persisted (`norm_stats.json`) and applied identically in `strategies/predictive_mcdm.py:_ingest_observation` before pushing to buffer. The ONNX export must either bake the normalization in or ship the stats file.
- **Impact**: GRU activation saturation is a known cause of slow/unstable convergence with un-normalized inputs of mixed scale. May partly explain why `train.elapsed_min = 0.354` (very short) and val_loss plateaus at 0.499.
- **Disposition**: fix-in-cycle

---

### Finding #6: Trainer.fit does not set random seeds — non-reproducible runs (important)
- **File:line**: `forecaster/train.py:291-368` (`Trainer.fit`); `forecaster/train.py:417-461` (`main` entry point)
- **Symptom**: `torch.manual_seed` and `np.random.seed` are called ONLY in `_selftest` (lines 517-518). The production `main()` and `Trainer.fit()` do not seed torch, numpy, or the DataLoader's worker generator. Two consecutive runs with identical hyperparameters will produce different ONNX weights, different val losses, and different metrics.
- **Root cause hypothesis**: Forgotten when factoring the selftest out from `main()`.
- **Evidence**: `grep -n "manual_seed\|np.random.seed" forecaster/train.py` returns only lines 517-518 in `_selftest`. Colab notebook also does not seed.
- **Fix**: Add a `seed: int = 0` field to `TrainConfig`. In `Trainer.__init__`:
  ```python
  torch.manual_seed(cfg.seed)
  np.random.seed(cfg.seed)
  if torch.cuda.is_available():
      torch.cuda.manual_seed_all(cfg.seed)
  # For DataLoader worker reproducibility:
  self._gen = torch.Generator().manual_seed(cfg.seed)
  ```
  Pass `generator=self._gen, worker_init_fn=lambda wid: np.random.seed(cfg.seed + wid)` to the train `DataLoader`.
- **Impact**: Paper-grade reproducibility is broken. Any ablation comparison (15 ablations per plan §13) confounds initialization noise with the ablated variable. H1 bootstrap conclusions depend on a single fixed-seed model that cannot be regenerated.
- **Disposition**: fix-in-cycle (small, mechanical)

---

### Finding #7: `reconstruct_rate` kills gradient through `u_hat` — half of model output is unlearnable (critical)
- **File:line**: `forecaster/train.py:147-166` (`reconstruct_rate`)
- **Symptom**: The model outputs `(u_hat, eps_corr)` per protocol. `reconstruct_rate` does `u_np = u_hat.detach().cpu().numpy().astype(np.float64)` and feeds `u_np` to `f_kink` (numpy). The result is reattached to torch's graph only via `kink_t + eps_corr`. The `kink_t` term has **zero gradient** with respect to `u_hat` (it's a detached numpy constant). Only `eps_corr` carries gradient. Therefore 2 of 4 model outputs (`u_hat_aave`, `u_hat_compound`) cannot be trained — they receive no gradient signal from any loss component.
- **Root cause hypothesis**: The docstring says "Differentiable wrt eps_corr but NOT wrt u_hat (kink is piecewise linear in numpy). For training purposes the gradient signal flowing through eps_corr is sufficient and matches the architecture's intent (kink is a fixed prior, not a learnable transform)." — the author acknowledged the issue but the intent is wrong: even though `f_kink` is a fixed function, the gradient must flow through `u_hat` so the network learns to predict utilization that, when passed through f_kink, produces a useful predicted rate. As written, `u_hat` is a free parameter that the network can set to anything; the gradient never tells it which value of u_hat is good. The two `u_hat` output heads become effectively random.
- **Evidence**:
  - Line 161: `u_np = u_hat.detach().cpu().numpy().astype(np.float64)` ← `.detach()` severs gradient
  - Line 165: `kink_t = torch.from_numpy(kink).to(eps_corr.device)` ← arrives without grad_fn
  - During backward, `loss.backward()` propagates through `eps_corr` only; `u_hat`'s contribution to loss is 0 → its grad is 0.
  - With wPearson_test_aave = 0.61 and wPearson_test_compound = −0.08, the model can fit "easy" Aave rates via `eps_corr_aave` alone (the residual contains the signal — see Finding #1!) but fails on Compound where the signal is weaker.
- **Fix**: Re-implement `f_kink` in pure torch so it is differentiable end-to-end. Both protocols are piecewise-linear in `u`; `torch.where` handles the kink. Sketch:
  ```python
  def f_kink_torch_aave(u: torch.Tensor, p: AaveKinkParams) -> torch.Tensor:
      below = p.base_variable_borrow_rate + p.slope1 * (u / p.optimal_usage_ratio)
      above = (p.base_variable_borrow_rate + p.slope1
               + p.slope2 * (u - p.optimal_usage_ratio) / (1.0 - p.optimal_usage_ratio))
      borrow = torch.where(u <= p.optimal_usage_ratio, below, above)
      return u * borrow * (1.0 - p.reserve_factor)
  ```
  Same for Compound (lines analogous to `data/features.py:_compound_supply_rate`). Then `reconstruct_rate` becomes pure torch with no detach. Also constrain `u_hat` to `(0, 1)` via `torch.sigmoid(...)` on the relevant head output so f_kink doesn't extrapolate.
- **Impact**: This is likely THE reason wPearson on Compound is essentially 0 (−0.08): Branch B's `u_hat` predictions are noise, and `eps_corr_compound` alone can't compensate when Compound's eps signal is small (std of `eps_compound` in panel is only 2.96×10⁻³ vs Aave's 1.40×10⁻²). The architecture promises two heads but trains only one.
- **Disposition**: fix-in-cycle (critical for paper headline)

---

### Finding #8: `u_hat` output is unconstrained — can produce u outside [0, 1] (important)
- **File:line**: `forecaster/model.py:152-155` (`FusionHead.forward`) and `forecaster/train.py:159` (`u_hat = model_out[..., 0]`)
- **Symptom**: The MLP head outputs raw linear-layer activations for `u_hat` (no sigmoid/clamp). `f_kink` extrapolates linearly outside `[0, 1]` — e.g. Aave's `above` branch becomes `0 + 0.04 + 0.10 * (u − 0.92) / 0.08` which goes negative for `u < 0.04` and unbounded for `u > 1`. Also the source data already has `u_aave.max() = 1.0149` (above 100% utilization, oracle glitch on `joined_clean.parquet`).
- **Root cause hypothesis**: Architectural oversight; no activation chosen for the u_hat head specifically.
- **Evidence**:
  - `forecaster/model.py:148`: `nn.Linear(cfg.head_hidden, out_dim)` — raw output, no activation
  - Diagnostic on parquet: `u_aave  min=0.5025 max=1.0149` ← supply utilization >100% violates the protocol invariant (Aave invariant is `totalDebt <= totalLiquidity`)
- **Fix**: Add `torch.sigmoid()` on the u_hat columns of `model_out` inside `reconstruct_rate` (combined with Finding #7's torch rewrite); also tighten `data/clean.py` to reject `u > 1.0` rows or clamp them:
  ```python
  # forecaster/train.py:reconstruct_rate (after Finding #7 torch rewrite)
  u_hat_raw = model_out[..., 0]
  u_hat = torch.sigmoid(u_hat_raw)  # constrain to (0, 1)
  ```
  ```python
  # data/clean.py: in clean_protocol, after _drop_outliers
  bad_util = df["utilization"] > 1.0
  df.loc[bad_util, "utilization"] = 1.0  # or drop
  ```
- **Impact**: Out-of-distribution `u_hat` values produce wildly wrong rate forecasts, particularly during the high-volatility 2024Q4 regime where source u values themselves spike >1.
- **Disposition**: fix-in-cycle (small)

---

### Finding #9: `run_main.py` does not compute per-quarter metrics — regime-dependent behavior hidden (important)
- **File:line**: `backtest/run_main.py:178-242` (`_compute_headline_metrics`), `backtest/run_main.py:315-380` (Sharpe bootstrap)
- **Symptom**: All headline metrics (`net_apy`, `sharpe_annual`, `max_drawdown`, `calmar`, `forecast_hit_rate`) are computed over the entire test window as a single aggregate. The H1 bootstrap pairs monthly Sharpes but does not break out by quarter or regime.
- **Root cause hypothesis**: Plan §16 H1 specifies "monthly Sharpe difference" but per CLAUDE.md "Project regime structure": Q4 2024 std = 5.75 pp vs 2026 Q1 std = 0.57 pp — a 10× volatility variation. Averaging across regimes hides whether the predictive edge concentrates in one regime (the regime-shift quarters 2025 Q3→Q4) or is uniform.
- **Evidence**:
  - `backtest/run_main.py:178-242` produces 1 row per strategy, no quarter axis
  - `_monthly_sharpes` groups by month but the bootstrap aggregates across all months
  - Per CLAUDE.md §"Project regime structure": 7 distinct quarterly regimes 2024Q4 → 2026Q2 with `Aave-higher %` ranging from 24.9% (2025 Q1) to 61.3% (2026 Q2)
- **Fix**: Add a per-quarter breakdown table in `_emit_outputs`:
  ```python
  def _per_quarter_metrics(equity, strategy_df, cfg):
      eq = equity.dropna()
      rows = []
      for q, group in eq.groupby(pd.Grouper(freq="QS")):
          if len(group) < 24: continue
          # compute Sharpe, dir_acc, hit_rate on the quarter slice
          rows.append({"quarter": q, ...})
      return pd.DataFrame(rows)
  ```
  Save as `results/tables/main_per_quarter.csv`. The 4-month test window (Jan–Apr 2026) spans Q1 2026 (calm) and Q2 2026 (Aave-dominant) — at least 2 regimes to compare.
- **Impact**: Without the per-quarter view, a paper conclusion of "PredictiveMCDM Sharpe > MCDM-EMA + 0.2" could be entirely driven by a single high-vol month and masked by calm quarters. Reviewer-level robustness is missing.
- **Disposition**: fix-in-cycle (additive, doesn't change existing outputs)

---

### Finding #10: Composite loss does not log α·MSE / β·(1−WP) / γ·Q90 separately (nice-to-have)
- **File:line**: `forecaster/losses.py:133-139` (component dict); `forecaster/train.py:268-272` (epoch accumulation)
- **Symptom**: The component dict logs `loss/mse`, `loss/wpearson` (raw correlation), and `loss/quantile` — the **bare** component values, not the weighted contributions `α·MSE`, `β·(1−WP)`, `γ·Q90`. So when one component blows up (e.g. MSE under Finding #1 = 10¹⁰× larger than the others), the per-epoch MLflow logs don't immediately show which term dominates the total loss.
- **Root cause hypothesis**: Logging convention chose unscaled components for interpretability; the scaled contributions need a quick mental multiplication by alpha/beta/gamma.
- **Evidence**: `forecaster/losses.py:133-139` — dict keys are bare; no `loss/alpha_mse`, `loss/beta_term`, `loss/gamma_term`.
- **Fix**:
  ```python
  components = {
      "loss/total":         total.item(),
      "loss/mse":           mse_term.item(),
      "loss/wpearson":      wpe_per.mean().item(),
      "loss/quantile":      quantile_term.item(),
      "loss/alpha_mse":     (self.alpha * mse_term).item(),
      "loss/beta_term":     (self.beta * wpearson_term).item(),
      "loss/gamma_term":    (self.gamma * quantile_term).item(),
      "loss/term_ratio_mse": (self.alpha * mse_term / total.clamp_min(1e-9)).item(),
  }
  ```
- **Impact**: Diagnosing Finding #1 would have been immediate from MLflow: `loss/alpha_mse / loss/total ≈ 1.0` (MSE dominates) and `loss/beta_term ≈ 0` would have flagged the scale issue without needing a separate diagnostic script.
- **Disposition**: fix-in-cycle (small)

---

### Finding #11: `_winner_series` uses `aave >= comp` — ties bias toward Aave (nice-to-have)
- **File:line**: `backtest/run_main.py:143`
- **Symptom**: `_winner_series` returns `(aave >= comp).astype(int)`. When both balances are exactly equal (notably at strategy startup when one entity holds INITIAL_BALANCE and the other holds 0, and at any tie post-rebalance), the winner is recorded as Aave (1).
- **Root cause hypothesis**: `>=` chosen for default behavior at startup (DEFAULT_INITIAL_ENTITY="AAVE"). Works at t=0 but biases tie-counting later.
- **Evidence**: line 143 source.
- **Fix**: Either (a) `(aave > comp).astype(int)` plus a separate "initially AAVE" handling, or (b) document the tie-break convention and leave as-is. Option (b) is fine since ties are rare on real data (rates differ at machine precision).
- **Impact**: Tiny: at most ±1 to `n_rebalances`, no material effect on headline metrics.
- **Disposition**: document-as-limitation

---

### Finding #12: 24-row boundary leakage from `pct_change(24)` straddling train/val cut (nice-to-have)
- **File:line**: `data/features.py:210-215`; `forecaster/train.py:435-450` (split by `iloc[:tr_end]`/`iloc[tr_end:val_end]`)
- **Symptom**: `extract_features` computes `dTVL_aave_24h = df["tvl_aave"].pct_change(24)` on the FULL feature panel BEFORE the train/val split is applied. Then the Colab notebook splits via `FEATS.iloc[:tr_end]` / `FEATS.iloc[tr_end:val_end]`. The validation set's first 24 rows of `dTVL_aave_24h` were computed using `tvl_aave` values from the last 24 training rows. This is a (tiny, but real) information leak from train into val.
- **Root cause hypothesis**: Standard timeseries-pitfall — features computed on the joined panel rather than per-fold.
- **Evidence**:
  - `data/features.py:210` `pct_change(24)` runs on full df
  - `forecaster/train.py:445-448` slices the post-extract panel by row index
- **Fix**: Recompute features inside each fold:
  ```python
  # In each fold of forecaster/train.py:main
  feat_tr = extract_features(df.iloc[:tr_end], params_a, params_c)
  feat_va = extract_features(df.iloc[tr_end:val_end], params_a, params_c)
  ```
  Or, simpler: drop the first 24 rows of each non-training fold after the global extract_features to ensure no row uses out-of-fold inputs.
- **Impact**: ~24 of 2749 val samples = 0.87% are mildly contaminated. Effect on val/wPearson is at most ~1%. Real concern is test-set leakage: if the same pattern applies to test (it does, since extract_features runs once), the first 24 test predictions use val-side TVL values. The headline result reports Pearson over 2501 test samples; 24/2501 = 0.96% contamination — small, but a referee will catch it.
- **Disposition**: document-as-limitation or fix-in-cycle (one-line)

---

## Unit trace results

### A. `data/cached/joined_clean.parquet` (raw inputs)

| Column           | Median       | p95          | Min          | Max          | Unit                |
|------------------|--------------|--------------|--------------|--------------|---------------------|
| r_aave           | 4.36e-06     | 1.15e-05     | 1.76e-06     | 5.52e-05     | per-hour rate       |
| rb_aave          | 5.87e-06     | 1.41e-05     | 3.12e-06     | 6.25e-05     | per-hour rate       |
| u_aave           | 0.805        | 0.929        | 0.503        | **1.015**    | unit fraction (>1 = invariant breach) |
| tvl_aave         | 2.98e+15     | 5.72e+15     | 1.41e+15     | 6.01e+15     | base units (raw, not USD) |
| debt_aave        | 2.49e+15     | 4.92e+15     | 1.42e+15     | 5.44e+15     | base units          |
| r_compound       | 4.42e-06     | 1.19e-05     | 2.56e-06     | 3.63e-05     | per-hour rate       |
| rb_compound      | 5.51e-06     | 1.39e-05     | 3.69e-06     | 4.13e-05     | per-hour rate       |
| u_compound       | 0.898        | 0.919        | 0.624        | 0.989        | unit fraction       |
| tvl_compound     | **0**        | 0            | 0            | 0            | **all-zero (placeholder)** |
| debt_compound    | **0**        | 0            | 0            | 0            | **all-zero (placeholder)** |

`r_aave * 8760 = 0.0382` ⇒ ~3.82% APR (matches CLAUDE.md description).

### B. Feature panel after `extract_features` (with `gas_gwei=30` and `eth_usd=3500` hand-added)

| Column           | Median       | Std          | Min          | Max          | Unit                |
|------------------|--------------|--------------|--------------|--------------|---------------------|
| r_aave           | 4.38e-06     | 3.30e-06     | 1.76e-06     | 5.52e-05     | per-hour rate (training TARGET) |
| u_aave           | 0.807        | 0.100        | 0.503        | 1.015        | unit fraction       |
| **eps_aave**     | **-2.55e-02**| 1.40e-02     | -1.45e-01    | -9.88e-03    | **scale-mixed (Finding #1)** — essentially −f_kink(u) |
| eps_compound     | -3.10e-02    | 2.96e-03     | -6.17e-02    | -2.15e-02    | scale-mixed; tighter std due to flatter u distribution |
| rate_spread      | -2.65e-07    | 2.87e-06     | -3.06e-05    | 5.12e-05     | per-hour (r_aave − r_compound) |
| residual_spread  | 4.46e-03     | 1.39e-02     | -1.21e-01    | 3.24e-02     | annualized (eps_a − eps_c) |
| kink_spread      | -4.46e-03    | 1.39e-02     | -3.24e-02    | 1.21e-01     | annualized           |
| util_spread      | -0.0646      | 0.0862       | -0.306       | 0.332        | unit fraction        |
| dTVL_aave_24h    | 7.26e-04     | 2.96e-02     | -0.330       | 0.296        | 24h pct change       |
| **dTVL_compound_24h** | **0**   | 0            | 0            | 0            | **dead (Finding #3)** |
| **gas_gwei**     | **30**       | 0            | 30           | 30           | **dead (Finding #4)** |
| tod_sin          | 1.22e-16     | 0.707        | -1.0         | 1.0          | cyclic               |
| tod_cos          | -1.84e-16    | 0.707        | -1.0         | 1.0          | cyclic               |

### C. `DABiGRUCNNDataset` arrays (input window=168, horizon=12)

| Tensor | Shape (T, F) | Per-col mean (over a 168-h window starting at idx=0)        | Notes |
|--------|--------------|-------------------------------------------------------------|-------|
| x_a    | (168, 3)     | [−0.0366, −0.0312, −0.00536]                                | Branch A: ~annual scale; nearly equal to `−f_kink(u)` |
| x_b    | (168, 7)     | [0.918, 0.906, 0.00113, **0**, **30**, 0, 0]                | cols 4 (dTVL_comp) and 5 (gas) constant |
| y      | (2,)         | [5.14e-06, 7.35e-06]                                        | **per-hour scale (Finding #1)** |

The 4-order-of-magnitude gap between x_a (annual, ~1e−2) and y (per-hour, ~1e−6) is the root cause of negative R² with positive wPearson.

---

## Audit method log

1. Read CLAUDE.md (hard constraints, regime structure, per-hour convention)
2. Read `data/features.py`, `data/clean.py`, `forecaster/train.py`, `forecaster/losses.py`, `backtest/run_main.py`, `strategies/predictive_mcdm.py`, `backtest/observations_builder.py`, `forecaster/model.py`
3. Read `forecaster/trained_models/metrics.json` to confirm scale-bug signature (wP positive + R² ≪ 0)
4. Ran unit-trace diagnostic on `joined_clean.parquet` + extract_features + Dataset
5. Cross-checked `BRANCH_A_COLS` / `BRANCH_B_COLS` ordering between `forecaster/train.py` and `strategies/predictive_mcdm.py:_ingest_observation` — MATCH
6. Searched for normalization, seeding, gas/TVL placeholders, gradient flow in reconstruct_rate

Hard time budget honoured: full audit completed in single pass.

---

## Summary table

| # | Severity      | File                                       | One-line                                                          | Disposition       |
|---|---------------|--------------------------------------------|-------------------------------------------------------------------|-------------------|
| 1 | critical      | data/features.py                           | per-hour r vs annual f_kink → R² catastrophe                       | fix-in-cycle      |
| 2 | critical      | data/features.py + strategies/predictive_mcdm.py | train/inference eps_* convention divergence (depends on #1 fix) | fix-in-cycle      |
| 3 | important     | data/clean.py + RPC fetcher                | tvl_compound all-zero → dTVL_compound_24h dead input               | document/drop col |
| 4 | important     | data/fetch_gas_eth.py + colab nb           | gas_gwei stub constant 30 → dead input                             | fix-in-cycle      |
| 5 | important     | forecaster/train.py                        | no feature z-scoring (plan §4.4 step never wired)                  | fix-in-cycle      |
| 6 | important     | forecaster/train.py                        | Trainer.fit + main() don't seed → non-reproducible                 | fix-in-cycle      |
| 7 | critical      | forecaster/train.py:reconstruct_rate       | u_hat gradient detached → half model outputs untrainable           | fix-in-cycle      |
| 8 | important     | forecaster/model.py + reconstruct_rate     | u_hat unconstrained → f_kink extrapolates outside [0,1]            | fix-in-cycle      |
| 9 | important     | backtest/run_main.py                       | no per-quarter breakdown → regime mixing hides heterogeneity       | fix-in-cycle      |
| 10| nice-to-have  | forecaster/losses.py                       | log scaled α·MSE / β·(1−WP) / γ·Q for diagnosability               | fix-in-cycle      |
| 11| nice-to-have  | backtest/run_main.py                       | `>=` tie-break biases Aave win count                               | document          |
| 12| nice-to-have  | data/features.py + colab nb                | pct_change(24) at fold boundary → 24-row leakage                   | document or fix   |

**Critical-path fix order before next Colab run**: 1 → 2 → 7 → 8 → 5 → 6. Findings 3, 4, 9, 10 are independent and small. 11, 12 can wait.
