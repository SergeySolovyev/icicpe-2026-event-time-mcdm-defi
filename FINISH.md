# Finishing the project — manual steps after agents complete

After all subagents land their commits, **THREE concrete user actions** remain
to fill in real numbers and recompile the whitepaper. Total wall time: ~1 hour
on the user side + ~30-45 min Colab H100.

This file is the runbook. Reference `CLAUDE.md` for project conventions.

---

## Step 1 — Package artifacts for Colab (~2 min)

Local machine, `D:\DeFi\predictive-mcdm-defi\`:

```powershell
.venv\Scripts\python -m scripts.prepare_colab_artifacts
```

Produces `predictive-mcdm-defi-artifacts.zip` (~5-10 MB) containing:
- `data/cached/joined_clean.parquet`     (the 13K-row real panel)
- `data/cached/kink_params.json`         (live Aave gateway snapshot)
- `data/features.py`, `data/__init__.py`
- `forecaster/{model.py, losses.py, train.py, export_onnx.py, __init__.py}`

Inspect output:
```powershell
Get-ChildItem predictive-mcdm-defi-artifacts.zip | Format-Table Name, Length
```

---

## Step 2 — Train DA-BiGRU-CNN on Colab H100 (~30-45 min)

1. Open `https://drive.google.com/` → create folder `predictive-mcdm-defi/`
2. Upload `predictive-mcdm-defi-artifacts.zip` to `MyDrive/predictive-mcdm-defi/`
3. Open `notebooks/colab/train_da_bigru_cnn_colab.ipynb` in Colab Pro:
   - File → Upload notebook, or
   - File → Open notebook → GitHub tab → paste `SergeySolovyev/predictive-mcdm-defi` URL
4. Runtime → **Change runtime type → GPU (H100)** (or T4 if budget-conscious)
5. **Runtime → Run all**

The notebook will:
- Install dependencies (~2 min on H100)
- Mount Drive + unzip artifacts
- Load `joined_clean.parquet`, apply `extract_features`
- Train 15 epochs (~25 min on H100, ~75 min on T4)
- Run `forecaster.export_onnx.export()` — verify torch↔onnxruntime parity
- Save `dual_branch_kink.onnx` + `da_bigru_cnn.pt` + `training_metrics.json` back
  to Drive at `MyDrive/predictive-mcdm-defi/trained_models/`

Download `dual_branch_kink.onnx` from Drive to local
`D:\DeFi\predictive-mcdm-defi\forecaster\trained_models\dual_branch_kink.onnx`.

---

## Step 3 — Run the headline backtest + ablations + fill whitepaper (~15 min)

Local machine:

```powershell
# Headline H1 evaluation (predictive vs EMA, 1000-bootstrap)
.venv\Scripts\python -m backtest.run_main

# All 15 ablations on real test window
.venv\Scripts\python -m backtest.run_ablations

# Substitute real numbers into whitepaper §8
.venv\Scripts\python -m scripts.fill_whitepaper_results

# Recompile whitepaper (3-pass for cross-refs)
cd whitepaper
pdflatex -interaction=nonstopmode main.tex
biber main
pdflatex -interaction=nonstopmode main.tex
pdflatex -interaction=nonstopmode main.tex
```

After this, `whitepaper/main.pdf` will be the final 14-16 page paper with all
real numbers substituted. Commit:

```powershell
cd ..
git add results/ whitepaper/sections/09_results.tex whitepaper/main.pdf whitepaper/main.tex
git commit -m "Real-data H1 evaluation: ΔSharpe = <X.XX> [<lo>, <hi>], p = <X.XXX>"
```

---

## What numbers to expect (rough priors)

From CLAUDE.md regime analysis + plan §16 H1 hypothesis:

| Metric | Expected range | Notes |
|---|---|---|
| **Predictive MCDM net APY** | 3.5% – 5.5% | Mostly Aave-driven; Compound switching adds ~50-100 bps on crossover hours |
| **EMA baseline net APY** | 3.0% – 4.5% | Reactive smoothing lags regime shifts |
| **ΔSharpe (pred − ema)** | 0.1 – 0.5 | H1 target: ≥ 0.2 |
| **Bootstrap p-value (H1)** | 0.05 – 0.30 | Honest result either way is publishable |
| **Direction accuracy (12h)** | 55% – 65% | Forecaster's main asset; <50% = H0 confirmed |
| **OOS R² per protocol** | 0.15 – 0.40 | DEEP_RESEARCH §VI.D anchor |

If the bootstrap p-value is > 0.10, **H0 is acceptable** and the paper still
ships: per plan §16, falsification of the methodological transfer is a
publishable negative result. The 2025 Q3→Q4 regime structure (CLAUDE.md)
remains a contribution either way.

---

## Troubleshooting

### "ONNX not found"
After Colab training, double-check you copied the file to
`forecaster/trained_models/dual_branch_kink.onnx` (NOT to `da_bigru_cnn.pt`).

### onnxruntime DLL load fails on Windows
Known issue from the broader project — `conftest.py` already preloads
onnxruntime to fix DLL order for pytest. If you hit it on backtest:
```powershell
.venv\Scripts\python -c "import torch; import onnxruntime"   # preload manually
# Then re-run the failing command
```

### Bootstrap CI very wide
Likely cause: small N of monthly Sharpe samples (only 4 test months: Jan-Apr
2026). Plan §16 H1 anchors on this; widen by including Q4 2025 validation
data if needed.

### Whitepaper §8 still has `XX.XX%` placeholders
Means `fill_whitepaper_results.py` didn't have a mapping for that
`\newcommand`. The script fails loudly on unmapped macros (intentional) —
update the macro dict and re-run.

---

## Extra+1 + Extra+2 PR submission (Week 4, optional)

After whitepaper is final:

```powershell
# Fork the upstream
gh repo fork Logarithm-Labs/fractal-defi --clone

# Copy Extra+1 files into fork
cp extras/fractal_pr_compound_loader/compound.py  ../fractal-defi/fractal/loaders/
cp extras/fractal_pr_compound_loader/aave_v3_subgraph.py  ../fractal-defi/fractal/loaders/thegraph/
# ...similar for Extra+2 BaseLendingAllocationStrategy

# Open PRs from PR_BODY.md
cd ../fractal-defi
git checkout -b add-compound-v3-loader
git commit -am "Add Compound V3 lending loader + utilization field"
git push -u origin add-compound-v3-loader
gh pr create --title "Add Compound V3 lending loader + utilization field" --body-file ../predictive-mcdm-defi/extras/fractal_pr_compound_loader/PR_BODY.md
```

Repeat for Extra+2 (BaseLendingAllocationStrategy).

---

## LLM transparency (Requirement 15)

When ready, save the full chat transcript to `LLM_TRANSCRIPT.md`. The
project's `CLAUDE.md` instructions explain the expected format. This is
deferred per user instruction — no rush.
