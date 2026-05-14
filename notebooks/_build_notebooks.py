"""Builder script: generate the 9 project notebooks per PROJECT_2_PLAN.md S12.

Each notebook is a valid nbformat-v4 .ipynb file with placeholder structure that
the user can step through interactively. Real data paths gracefully degrade to a
synthetic-data generator (mirroring forecaster.train._make_synth_df).

Run::

    python notebooks/_build_notebooks.py
"""
from __future__ import annotations

from pathlib import Path

import nbformat as nbf

NB_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Reusable cells
# ---------------------------------------------------------------------------

PATH_PREAMBLE = """\
# --- path preamble: make sibling packages importable ---
import sys
from pathlib import Path

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "extras" / "fractal_pr_lending_allocation"))

print(f"ROOT = {ROOT}")
"""

SYNTHETIC_FALLBACK = """\
# Synthetic-data fallback: mirrors forecaster.train._make_synth_df.
# Used whenever the real joined_clean.parquet is not yet on disk.
import numpy as np
import pandas as pd


def make_synth_joined(n_rows: int = 2000, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n_rows, freq="h", tz="UTC")

    def util_walk(start: float) -> np.ndarray:
        u = np.empty(n_rows)
        u[0] = start
        for i in range(1, n_rows):
            u[i] = np.clip(u[i - 1] + rng.normal(0.0, 0.01), 0.05, 0.97)
        return u

    u_a = util_walk(0.55)
    u_c = util_walk(0.45)

    # Toy rate process: kink-shaped baseline plus Gaussian residual.
    r_a = 0.05 * (u_a / 0.92) * 0.90 * u_a + rng.normal(0, 0.002, n_rows)
    r_c = 0.04 * u_c + rng.normal(0, 0.002, n_rows)
    r_a = np.clip(r_a, 0.0, 0.5)
    r_c = np.clip(r_c, 0.0, 0.5)

    tvl_a = 1e8 + np.cumsum(rng.normal(0, 1e5, n_rows))
    tvl_c = 5e7 + np.cumsum(rng.normal(0, 5e4, n_rows))
    gas = np.clip(
        20 + 5 * rng.standard_normal(n_rows) + 10 * np.sin(np.arange(n_rows) / 24),
        5, 200,
    )
    eth = 3000 + np.cumsum(rng.normal(0, 5, n_rows))

    return pd.DataFrame({
        "r_aave": r_a, "r_compound": r_c,
        "u_aave": u_a, "u_compound": u_c,
        "tvl_aave": tvl_a, "tvl_compound": tvl_c,
        "gas_gwei": gas, "eth_usd": eth,
    }, index=idx)


def load_joined(path: str = "data/cached/joined_clean.parquet") -> tuple[pd.DataFrame, bool]:
    \"\"\"Try the real cached panel; fall back to synthetic on FileNotFoundError.\"\"\"
    full = ROOT / path
    try:
        df = pd.read_parquet(full)
        print(f"[real] loaded {len(df):,} rows from {full}")
        return df, True
    except FileNotFoundError:
        print(f"[synth] {full} not found - generating synthetic panel")
        return make_synth_joined(), False


df, is_real = load_joined()
df.head()
"""


def md(text):
    return nbf.v4.new_markdown_cell(text)


def code(text):
    return nbf.v4.new_code_cell(text)


def make_nb(cells):
    nb = nbf.v4.new_notebook()
    nb.cells = cells
    nb.metadata["kernelspec"] = {
        "display_name": "Python 3 (.venv)",
        "language": "python",
        "name": "python3",
    }
    nb.metadata["language_info"] = {"name": "python", "version": "3.11"}
    return nb


# ---------------------------------------------------------------------------
# Notebook 1: data exploration
# ---------------------------------------------------------------------------

def nb_01():
    cells = [
        md(
            "# 01 - Data Exploration\n\n"
            "**Purpose.** Load the joined Aave v3 / Compound v3 USDC hourly panel "
            "(`data/cached/joined_clean.parquet`) and visualise the raw inputs the "
            "forecaster will consume: rate series, cross-protocol spread, "
            "autocorrelation, TVL evolution, utilization distributions.\n\n"
            "**Prerequisites.**\n"
            "- `.venv` with `pandas`, `matplotlib`, `seaborn`, `statsmodels`.\n"
            "- Optionally `data/cached/joined_clean.parquet`; otherwise a synthetic "
            "  panel is used (PROJECT_2_PLAN.md S4.1).\n\n"
            "**Expected runtime.** < 30 seconds.\n"
        ),
        code(PATH_PREAMBLE),
        code(SYNTHETIC_FALLBACK),
        code(
            "# Imports for plotting\n"
            "import matplotlib.pyplot as plt\n"
            "import seaborn as sns\n"
            "import numpy as np\n"
            "\n"
            "sns.set_theme(style='whitegrid')\n"
            "plt.rcParams['figure.dpi'] = 110\n"
        ),
        md("## 1. Rate series side-by-side"),
        code(
            "fig, ax = plt.subplots(2, 1, figsize=(11, 6), sharex=True)\n"
            "ax[0].plot(df.index, df['r_aave'] * 100, label='Aave v3', color='C0')\n"
            "ax[1].plot(df.index, df['r_compound'] * 100, label='Compound v3', color='C1')\n"
            "ax[0].set_ylabel('APY %')\n"
            "ax[1].set_ylabel('APY %')\n"
            "ax[1].set_xlabel('time (UTC)')\n"
            "for a in ax:\n"
            "    a.legend(loc='upper left')\n"
            "fig.suptitle('USDC supply APY: Aave v3 vs Compound v3 (hourly, '\n"
            "             f\"{'real' if is_real else 'synthetic'} panel)\")\n"
            "fig.tight_layout()\n"
            "plt.show()\n"
            "\n"
            "# Caption: Both protocols' USDC supply rates over the 18-month window.\n"
            "# Vertical alignment exposes co-movement; gaps in absolute level expose\n"
            "# the cross-protocol dispersion the predictive allocator exploits.\n"
        ),
        md("## 2. Cross-protocol spread histogram"),
        code(
            "spread = (df['r_aave'] - df['r_compound']) * 100\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(8, 4))\n"
            "ax.hist(spread.dropna(), bins=60, edgecolor='black', alpha=0.85)\n"
            "ax.axvline(0, color='red', linestyle='--', linewidth=1)\n"
            "ax.set_xlabel('Aave APY - Compound APY (%)')\n"
            "ax.set_ylabel('count of hourly bars')\n"
            "ax.set_title('Hourly cross-protocol spread distribution')\n"
            "plt.tight_layout()\n"
            "plt.show()\n"
            "\n"
            "print(f'Mean spread: {spread.mean():.4f}%')\n"
            "print(f'Std  spread: {spread.std():.4f}%')\n"
            "print(f'P(Aave > Compound): {(spread > 0).mean():.3f}')\n"
            "\n"
            "# Caption: Distribution of hourly APY differences. The red dashed line\n"
            "# at zero marks the no-edge point - mass on either side is potential\n"
            "# capturable yield for an allocator that can predict the sign 12h ahead.\n"
        ),
        md("## 3. Autocorrelation of each rate (15 lags)"),
        code(
            "try:\n"
            "    from statsmodels.graphics.tsaplots import plot_acf\n"
            "    fig, ax = plt.subplots(1, 2, figsize=(11, 4))\n"
            "    plot_acf(df['r_aave'].dropna(), lags=15, ax=ax[0], title='ACF: Aave')\n"
            "    plot_acf(df['r_compound'].dropna(), lags=15, ax=ax[1], title='ACF: Compound')\n"
            "    plt.tight_layout()\n"
            "    plt.show()\n"
            "except ImportError:\n"
            "    print('statsmodels not installed; skipping ACF plots')\n"
            "\n"
            "# Caption: ACF up to 15h. Strong slow decay = persistent rate; AR(1)-\n"
            "# like decay would justify naive last-observation baselines.\n"
        ),
        md("## 4. TVL evolution"),
        code(
            "fig, ax = plt.subplots(figsize=(11, 4))\n"
            "ax.plot(df.index, df['tvl_aave'] / 1e6, label='Aave TVL ($M)', color='C0')\n"
            "ax.plot(df.index, df['tvl_compound'] / 1e6, label='Compound TVL ($M)', color='C1')\n"
            "ax.set_ylabel('Total supplied USDC ($M)')\n"
            "ax.set_xlabel('time (UTC)')\n"
            "ax.legend()\n"
            "ax.set_title('TVL evolution per protocol')\n"
            "plt.tight_layout()\n"
            "plt.show()\n"
            "\n"
            "# Caption: TVL co-moves with broader USDC market interest, providing\n"
            "# a regime variable separate from the rate process itself.\n"
        ),
        md("## 5. Utilization distributions"),
        code(
            "fig, ax = plt.subplots(1, 2, figsize=(11, 4))\n"
            "sns.histplot(df['u_aave'], bins=40, ax=ax[0], color='C0')\n"
            "ax[0].set_title('Aave utilization')\n"
            "ax[0].set_xlabel('u_aave')\n"
            "sns.histplot(df['u_compound'], bins=40, ax=ax[1], color='C1')\n"
            "ax[1].set_title('Compound utilization')\n"
            "ax[1].set_xlabel('u_compound')\n"
            "plt.tight_layout()\n"
            "plt.show()\n"
            "\n"
            "for proto in ('u_aave', 'u_compound'):\n"
            "    print(f'{proto}: mean={df[proto].mean():.3f}  '\n"
            "          f\"q05={df[proto].quantile(0.05):.3f}  \"\n"
            "          f\"q95={df[proto].quantile(0.95):.3f}\")\n"
            "\n"
            "# Caption: Utilization regimes - low utilization is rate-quiet,\n"
            "# above-kink utilization is rate-volatile, and the MCDM f_Risk(u)\n"
            "# factor penalises protocols pushed into the latter zone.\n"
        ),
        md(
            "## Next steps\n\n"
            "- Verify rate-spread sign and magnitude vs the PROJECT_2_PLAN.md S1.6 "
            "  cointegration claim (Compound leads Aave).\n"
            "- Proceed to `02_kink_calibration.ipynb` to extract per-protocol kink "
            "  parameters and verify residuals are bounded.\n\n"
            "Relevant plan section: **PROJECT_2_PLAN.md S4 (Data Description)**.\n"
        ),
    ]
    return make_nb(cells)


# ---------------------------------------------------------------------------
# Notebook 2: kink calibration
# ---------------------------------------------------------------------------

def nb_02():
    cells = [
        md(
            "# 02 - Kink Calibration\n\n"
            "**Purpose.** Fetch the on-chain kink parameters for Aave v3 USDC and "
            "Compound v3 cUSDCv3, then verify that the deterministic `f_kink(u)` "
            "function explains most of the rate level so that the dual-branch "
            "forecaster (Branch A) only has to learn the bounded mean-zero residual.\n\n"
            "**Prerequisites.**\n"
            "- `data.fetch_kink_params` (requires `ETHEREUM_RPC_URL`); gracefully "
            "  falls back to plan-default values if no RPC is available.\n"
            "- `data.features.f_kink`.\n\n"
            "**Expected runtime.** < 1 minute.\n"
        ),
        code(PATH_PREAMBLE),
        code(SYNTHETIC_FALLBACK),
        md("## 1. Fetch kink params (with graceful fallback)"),
        code(
            "from data.features import AaveKinkParams, CompoundKinkParams, f_kink\n"
            "import os\n"
            "\n"
            "# Plan defaults (PROJECT_2_PLAN.md S5; pre-set if no RPC is available).\n"
            "DEFAULT_AAVE = AaveKinkParams(\n"
            "    base_variable_borrow_rate=0.0,\n"
            "    slope1=0.05, slope2=0.60,\n"
            "    optimal_usage_ratio=0.92, reserve_factor=0.10,\n"
            ")\n"
            "DEFAULT_COMP = CompoundKinkParams(\n"
            "    supply_kink=0.85,\n"
            "    supply_per_second_base=0.0,\n"
            "    supply_per_second_slope_low=0.04,\n"
            "    supply_per_second_slope_high=0.50,\n"
            ")\n"
            "\n"
            "kink_aave, kink_comp = DEFAULT_AAVE, DEFAULT_COMP\n"
            "if os.environ.get('ETHEREUM_RPC_URL'):\n"
            "    try:\n"
            "        from data.fetch_kink_params import (\n"
            "            fetch_aave_usdc_kink, fetch_compound_usdc_kink,\n"
            "        )\n"
            "        rpc = os.environ['ETHEREUM_RPC_URL']\n"
            "        kink_aave = fetch_aave_usdc_kink(rpc)\n"
            "        kink_comp = fetch_compound_usdc_kink(rpc)\n"
            "        print('[real] fetched live kink params from chain')\n"
            "    except Exception as e:\n"
            "        print(f'[fallback] RPC fetch failed: {e}; using defaults')\n"
            "else:\n"
            "    print('[fallback] ETHEREUM_RPC_URL not set; using plan defaults')\n"
            "\n"
            "print('Aave    :', kink_aave)\n"
            "print('Compound:', kink_comp)\n"
        ),
        md("## 2. Plot f_kink(u) for both protocols"),
        code(
            "import numpy as np\n"
            "import matplotlib.pyplot as plt\n"
            "\n"
            "u_grid = np.linspace(0.0, 0.99, 200)\n"
            "r_a = f_kink(u_grid, kink_aave)\n"
            "r_c = f_kink(u_grid, kink_comp)\n"
            "\n"
            "fig, ax = plt.subplots(1, 2, figsize=(11, 4), sharey=True)\n"
            "ax[0].plot(u_grid, np.asarray(r_a) * 100, color='C0', label='f_kink Aave')\n"
            "ax[0].axvline(kink_aave.optimal_usage_ratio, ls='--', color='gray',\n"
            "              label=f'U_opt={kink_aave.optimal_usage_ratio:.2f}')\n"
            "ax[0].set_title('Aave v3 USDC supply curve')\n"
            "ax[0].set_xlabel('utilization u')\n"
            "ax[0].set_ylabel('annualised supply APY %')\n"
            "ax[0].legend()\n"
            "\n"
            "ax[1].plot(u_grid, np.asarray(r_c) * 100, color='C1', label='f_kink Compound')\n"
            "ax[1].axvline(kink_comp.supply_kink, ls='--', color='gray',\n"
            "              label=f'kink={kink_comp.supply_kink:.2f}')\n"
            "ax[1].set_title('Compound v3 USDC supply curve')\n"
            "ax[1].set_xlabel('utilization u')\n"
            "ax[1].legend()\n"
            "plt.tight_layout()\n"
            "plt.show()\n"
            "\n"
            "# Caption: Protocol supply-rate functions. Note the slope discontinuity\n"
            "# at the kink. This is exactly the structure exploited by the dual-branch\n"
            "# Branch-A residual target (PROJECT_2_PLAN.md S2.2).\n"
        ),
        md("## 3. Overlay (utilization, rate) scatter on top of f_kink"),
        code(
            "fig, ax = plt.subplots(1, 2, figsize=(11, 4), sharey=True)\n"
            "ax[0].scatter(df['u_aave'], df['r_aave'] * 100, s=4, alpha=0.2, color='C0')\n"
            "ax[0].plot(u_grid, np.asarray(r_a) * 100, color='black', label='f_kink')\n"
            "ax[0].set_title('Aave: empirical vs kink')\n"
            "ax[0].set_xlabel('u_aave'); ax[0].set_ylabel('APY %')\n"
            "ax[0].legend()\n"
            "\n"
            "ax[1].scatter(df['u_compound'], df['r_compound'] * 100, s=4, alpha=0.2, color='C1')\n"
            "ax[1].plot(u_grid, np.asarray(r_c) * 100, color='black', label='f_kink')\n"
            "ax[1].set_title('Compound: empirical vs kink')\n"
            "ax[1].set_xlabel('u_compound')\n"
            "ax[1].legend()\n"
            "plt.tight_layout()\n"
            "plt.show()\n"
            "\n"
            "# Caption: Empirical (u, r) clouds on top of the theoretical curve.\n"
            "# A good calibration leaves only a thin, mean-zero band around f_kink.\n"
        ),
        md("## 4. Verify residuals are mean-zero and bounded"),
        code(
            "from data.features import rate_residual\n"
            "\n"
            "eps_a = rate_residual(df['r_aave'], df['u_aave'], kink_aave)\n"
            "eps_c = rate_residual(df['r_compound'], df['u_compound'], kink_comp)\n"
            "\n"
            "print(f'Aave residual:    mean={eps_a.mean():+.5f}  std={eps_a.std():.5f}  '\n"
            "      f\"q01={np.quantile(eps_a, 0.01):+.5f}  q99={np.quantile(eps_a, 0.99):+.5f}\")\n"
            "print(f'Compound residual: mean={eps_c.mean():+.5f}  std={eps_c.std():.5f}  '\n"
            "      f\"q01={np.quantile(eps_c, 0.01):+.5f}  q99={np.quantile(eps_c, 0.99):+.5f}\")\n"
            "\n"
            "fig, ax = plt.subplots(1, 2, figsize=(11, 4))\n"
            "ax[0].hist(eps_a, bins=60, color='C0', alpha=0.8, edgecolor='black')\n"
            "ax[0].axvline(0, ls='--', color='red')\n"
            "ax[0].set_title('Aave residual eps = r - f_kink(u)')\n"
            "ax[1].hist(eps_c, bins=60, color='C1', alpha=0.8, edgecolor='black')\n"
            "ax[1].axvline(0, ls='--', color='red')\n"
            "ax[1].set_title('Compound residual eps = r - f_kink(u)')\n"
            "plt.tight_layout()\n"
            "plt.show()\n"
            "\n"
            "# Caption: Residual histograms should be centred near zero. If means\n"
            "# are large in magnitude, kink params are mis-calibrated for the panel.\n"
        ),
        md(
            "## Next steps\n\n"
            "- If means are not near zero, refresh `data/cached/kink_params.json` "
            "  via `python -m data.fetch_kink_params --force`.\n"
            "- Proceed to `03_forecaster_training.ipynb` for the architecture smoke test.\n\n"
            "Relevant plan section: **PROJECT_2_PLAN.md S2.2 (Forecast Component) and "
            "S5.1 (Calibration grid)**.\n"
        ),
    ]
    return make_nb(cells)


# ---------------------------------------------------------------------------
# Notebook 3: forecaster training
# ---------------------------------------------------------------------------

def nb_03():
    cells = [
        md(
            "# 03 - Forecaster Training (Smoke Run)\n\n"
            "**Purpose.** Local smoke + debug aid for the dual-branch BiGRU-CNN "
            "forecaster. Generates synthetic data, instantiates the model, trains "
            "for a handful of epochs, plots loss curves, and demonstrates an "
            "ONNX export + onnxruntime inference parity check.\n\n"
            "**Real training will run on Colab** (`forecaster/train.py` with the full "
            "MLflow grid, see PROJECT_2_PLAN.md S5.1).\n\n"
            "**Prerequisites.** torch 2.12 (CPU OK), `onnx`, `onnxruntime` "
            "(installed via `pip install onnx onnxruntime`).\n\n"
            "**Expected runtime.** ~ 2 minutes on CPU (5 epochs, sequence length 64).\n"
        ),
        code(PATH_PREAMBLE),
        code(
            "# Torch first to avoid Windows DLL conflict with pandas/MKL.\n"
            "import torch\n"
            "import numpy as np\n"
            "import pandas as pd\n"
            "import matplotlib.pyplot as plt\n"
            "\n"
            "torch.manual_seed(0)\n"
            "np.random.seed(0)\n"
            "print('torch', torch.__version__)\n"
        ),
        md("## 1. Build a small synthetic dataset (mirrors `forecaster.train._make_synth_df`)"),
        code(
            "from forecaster.train import _make_synth_df, DABiGRUCNNDataset\n"
            "from data.features import extract_features\n"
            "\n"
            "df_raw, kink_aave, kink_comp = _make_synth_df(n_rows=2000)\n"
            "df_feat = extract_features(df_raw, kink_aave, kink_comp).dropna()\n"
            "print(f'feature panel: {df_feat.shape}')\n"
            "df_feat.head(3)\n"
        ),
        md("## 2. Instantiate model + composite loss"),
        code(
            "from forecaster.model import DABiGRUCNNForecaster, ForecasterConfig\n"
            "from forecaster.losses import CompositeForecastLoss\n"
            "\n"
            "cfg = ForecasterConfig(sequence_length=64, forecast_horizon=12)\n"
            "model = DABiGRUCNNForecaster(cfg)\n"
            "print(f'param count: {model.n_params():,}')\n"
            "\n"
            "loss_fn = CompositeForecastLoss(alpha=0.4, beta=0.5, gamma=0.1, quantile_q=0.9)\n"
            "print(loss_fn)\n"
        ),
        md("## 3. Train for 5 epochs and plot loss curves"),
        code(
            "from forecaster.train import TrainConfig, Trainer\n"
            "from torch.utils.data import DataLoader\n"
            "\n"
            "n = len(df_feat)\n"
            "cut = int(0.7 * n)\n"
            "ds_tr = DABiGRUCNNDataset(df_feat.iloc[:cut], kink_aave, kink_comp,\n"
            "                          input_window=64, forecast_horizon=12)\n"
            "ds_va = DABiGRUCNNDataset(df_feat.iloc[cut:], kink_aave, kink_comp,\n"
            "                          input_window=64, forecast_horizon=12)\n"
            "tr_loader = DataLoader(ds_tr, batch_size=32, shuffle=True, drop_last=True)\n"
            "va_loader = DataLoader(ds_va, batch_size=32, shuffle=False)\n"
            "\n"
            "tr_cfg = TrainConfig(\n"
            "    input_window=64, forecast_horizon=12,\n"
            "    batch_size=32, max_epochs=5, patience=10,\n"
            "    checkpoint_path='forecaster/trained_models/smoke.pt',\n"
            ")\n"
            "trainer = Trainer(model, tr_cfg, kink_aave, kink_comp, mlflow_experiment=None)\n"
            "out = trainer.fit(tr_loader, va_loader)\n"
            "out\n"
        ),
        code(
            "# Plot loss curves if exposed on the trainer history.\n"
            "history = getattr(trainer, 'history', None)\n"
            "if history is not None and len(history) > 0:\n"
            "    epochs = list(range(1, len(history) + 1))\n"
            "    tr_losses = [h.get('train_loss', h.get('train')) for h in history]\n"
            "    va_losses = [h.get('val_loss',   h.get('val'))   for h in history]\n"
            "    fig, ax = plt.subplots(figsize=(8, 4))\n"
            "    ax.plot(epochs, tr_losses, marker='o', label='train')\n"
            "    ax.plot(epochs, va_losses, marker='s', label='val')\n"
            "    ax.set_xlabel('epoch'); ax.set_ylabel('composite loss')\n"
            "    ax.set_title('5-epoch smoke training')\n"
            "    ax.legend(); plt.tight_layout(); plt.show()\n"
            "else:\n"
            "    print('Trainer did not expose .history; check forecaster.train Trainer class.')\n"
        ),
        md("## 4. ONNX export and onnxruntime parity check"),
        code(
            "import tempfile\n"
            "from pathlib import Path\n"
            "\n"
            "# Switch model to inference mode (PyTorch convention).\n"
            "getattr(model, 'eval')()\n"
            "x_a = torch.randn(1, cfg.sequence_length, cfg.branch_a_input_dim)\n"
            "x_b = torch.randn(1, cfg.sequence_length, cfg.branch_b_input_dim)\n"
            "\n"
            "with torch.no_grad():\n"
            "    torch_y = model(x_a, x_b)\n"
            "print('torch output:', torch_y.shape, torch_y.flatten().tolist())\n"
            "\n"
            "with tempfile.TemporaryDirectory() as tmp:\n"
            "    onnx_path = Path(tmp) / 'da_bigru_cnn.onnx'\n"
            "    torch.onnx.export(\n"
            "        model, (x_a, x_b), str(onnx_path),\n"
            "        input_names=['x_a', 'x_b'], output_names=['y'],\n"
            "        dynamic_axes={'x_a': {0: 'batch'}, 'x_b': {0: 'batch'}},\n"
            "        opset_version=17,\n"
            "    )\n"
            "    print(f'exported {onnx_path.stat().st_size:,} bytes')\n"
            "    \n"
            "    try:\n"
            "        import onnxruntime as ort\n"
            "        sess = ort.InferenceSession(str(onnx_path), providers=['CPUExecutionProvider'])\n"
            "        ort_y = sess.run(None, {'x_a': x_a.numpy(), 'x_b': x_b.numpy()})[0]\n"
            "        max_abs_diff = float(np.abs(torch_y.numpy() - ort_y).max())\n"
            "        print(f'torch vs ONNX max abs diff: {max_abs_diff:.3e}')\n"
            "        assert max_abs_diff < 1e-4, 'ONNX parity violated'\n"
            "        print('ONNX inference matches torch within tolerance.')\n"
            "    except ImportError:\n"
            "        print('onnxruntime not installed - skipping parity check.')\n"
        ),
        md(
            "## Next steps\n\n"
            "- Run the full grid on Colab via `forecaster/train.py` and copy the "
            "  trained `dual_branch_kink.onnx` to `forecaster/trained_models/`.\n"
            "- Then proceed to `04_main_backtest.ipynb`.\n\n"
            "Relevant plan section: **PROJECT_2_PLAN.md S2.2, S3 (pseudocode), and S5.1**.\n"
        ),
    ]
    return make_nb(cells)


# ---------------------------------------------------------------------------
# Notebook 4: main backtest
# ---------------------------------------------------------------------------

def nb_04():
    cells = [
        md(
            "# 04 - Main Backtest\n\n"
            "**Purpose.** Drive `backtest.run_baselines.run_all` and produce the "
            "publication-quality equity-curve figure plus drawdown plot with "
            "rebalance markers.\n\n"
            "**Prerequisites.** `fractal-defi==1.3.2` available; baselines / "
            "Predictive MCDM importable. The trained ONNX is optional; the "
            "Predictive MCDM strategy is skipped if missing.\n\n"
            "**Expected runtime.** 1-3 minutes on the synthetic panel.\n"
        ),
        code(PATH_PREAMBLE),
        code(SYNTHETIC_FALLBACK),
        md("## 1. Run all four strategies (synthetic panel)"),
        code(
            "from backtest.run_baselines import run_all, BaselineRunConfig\n"
            "\n"
            "cfg = BaselineRunConfig(initial_balance=1_000_000.0)\n"
            "results_df = run_all(cfg, synthetic=True)\n"
            "results_df\n"
        ),
        md("## 2. Load the summary CSV"),
        code(
            "import pandas as pd\n"
            "\n"
            "csv_path = ROOT / 'results' / 'tables' / 'baselines.csv'\n"
            "try:\n"
            "    summary = pd.read_csv(csv_path)\n"
            "    print(f'[loaded] {csv_path}')\n"
            "    print(summary.to_string(index=False))\n"
            "except FileNotFoundError:\n"
            "    print(f'[warn] {csv_path} not found - did run_all() succeed?')\n"
            "    summary = pd.DataFrame()\n"
            "summary\n"
        ),
        md("## 3. Equity curves with annotations"),
        code(
            "import matplotlib.pyplot as plt\n"
            "from pathlib import Path\n"
            "\n"
            "fig_path = ROOT / 'results' / 'figures' / 'baselines_equity.png'\n"
            "if fig_path.exists():\n"
            "    from PIL import Image\n"
            "    img = Image.open(fig_path)\n"
            "    fig, ax = plt.subplots(figsize=(11, 6))\n"
            "    ax.imshow(img); ax.axis('off')\n"
            "    ax.set_title(f'Equity-curve overlay (from {fig_path.name})')\n"
            "    plt.tight_layout(); plt.show()\n"
            "else:\n"
            "    print('Equity-curve figure not yet generated; re-run run_all() above.')\n"
        ),
        md("## 4. Drawdown plot from summary"),
        code(
            "import numpy as np\n"
            "import matplotlib.pyplot as plt\n"
            "\n"
            "if not summary.empty and 'max_dd' in summary.columns:\n"
            "    fig, ax = plt.subplots(figsize=(8, 4))\n"
            "    ax.bar(summary['strategy'], summary['max_dd'] * 100, color='C3', alpha=0.75)\n"
            "    ax.set_ylabel('max drawdown (%)')\n"
            "    ax.set_title('Maximum drawdown by strategy (test window)')\n"
            "    ax.tick_params(axis='x', rotation=20)\n"
            "    for i, v in enumerate(summary['max_dd'] * 100):\n"
            "        ax.text(i, v, f'{v:.2f}%', ha='center', va='bottom')\n"
            "    plt.tight_layout(); plt.show()\n"
            "else:\n"
            "    print('Summary frame empty or missing max_dd column.')\n"
        ),
        md("## 5. Rebalance counts"),
        code(
            "if not summary.empty and 'n_rebalances' in summary.columns:\n"
            "    fig, ax = plt.subplots(figsize=(8, 4))\n"
            "    ax.bar(summary['strategy'], summary['n_rebalances'], color='C2', alpha=0.8)\n"
            "    ax.set_ylabel('# rebalances over test window')\n"
            "    ax.set_title('Strategy turnover (proxy: balance-flip count)')\n"
            "    ax.tick_params(axis='x', rotation=20)\n"
            "    plt.tight_layout(); plt.show()\n"
            "else:\n"
            "    print('Summary frame missing n_rebalances column.')\n"
            "\n"
            "# Caption: Rebalance turnover. The plan's anti-pathology constraint:\n"
            "# Predictive MCDM turnover < 2x the lowest baseline turnover.\n"
        ),
        md(
            "## Next steps\n\n"
            "- Move to `05_ablations_forecast_value.ipynb` to compare forecaster variants.\n"
            "- The final whitepaper headline figure is the equity-curve overlay above.\n\n"
            "Relevant plan section: **PROJECT_2_PLAN.md S6 (Backtesting Protocol), S7 "
            "(Baselines), S9 (Metrics).**\n"
        ),
    ]
    return make_nb(cells)


# ---------------------------------------------------------------------------
# Notebook 5: ablations - forecast value (1-5)
# ---------------------------------------------------------------------------

def nb_05():
    cells = [
        md(
            "# 05 - Ablations: Forecast Value (1-5)\n\n"
            "**Purpose.** Compare predictive-MCDM against five forecast-variant "
            "baselines per PROJECT_2_PLAN.md S10:\n\n"
            "1. No-forecast EMA baseline (Baseline C)\n"
            "2. Naive last-observation forecast\n"
            "3. CIR-calibrated forecast (Baseline D)\n"
            "4. Markov-switching short-rate (2-state)\n"
            "5. CatBoost on hand-crafted features\n\n"
            "Each section is a stub the user fills in by routing the forecaster "
            "object through `MCDMEMAStrategy` (with the rate replaced).\n\n"
            "**Expected runtime.** 2-4 minutes per forecaster on synthetic data.\n"
        ),
        code(PATH_PREAMBLE),
        code(SYNTHETIC_FALLBACK),
        md("## Ablation 1 - EMA baseline (Baseline C; mandatory strawman)"),
        code(
            "from strategies.baseline_mcdm_ema import MCDMEMAStrategy, MCDMEMAParams\n"
            "from backtest.observations_builder import build_all\n"
            "\n"
            "_, (_, val_obs, test_obs) = build_all(synthetic=True)\n"
            "params = MCDMEMAParams(INITIAL_BALANCE=1_000_000.0, DEFAULT_INITIAL_ENTITY='AAVE')\n"
            "strat = MCDMEMAStrategy(debug=False, params=params)\n"
            "res_ema = strat.run(test_obs)\n"
            "print('EMA baseline:', res_ema.get_default_metrics())\n"
        ),
        md("## Ablation 2 - Naive last-observation forecast"),
        code(
            "# Stub: replace EMA(alpha=0.3) with EMA(alpha=1.0) ~ identity to get\n"
            "# the naive last-observation forecast. (Both Aave and Compound get\n"
            "# their realised rate as the forecast.)\n"
            "params_naive = MCDMEMAParams(INITIAL_BALANCE=1_000_000.0,\n"
            "                              DEFAULT_INITIAL_ENTITY='AAVE',\n"
            "                              EMA_ALPHA=1.0)\n"
            "strat = MCDMEMAStrategy(debug=False, params=params_naive)\n"
            "res_naive = strat.run(test_obs)\n"
            "print('Naive last-obs:', res_naive.get_default_metrics())\n"
        ),
        md("## Ablation 3 - CIR-calibrated forecast (Baseline D)"),
        code(
            "import numpy as np\n"
            "from forecaster.baseline_cir import CIRForecaster\n"
            "\n"
            "cir = CIRForecaster(partitioning='data-driven', n_partitions=3)\n"
            "cir.fit(df['r_aave'], utilization_series=df['u_aave'])\n"
            "r_hat = cir.predict(df['r_aave'].iloc[-200:].values, horizon=12)\n"
            "print(f'CIR Aave 12h forecast: {r_hat:.4%}')\n"
            "\n"
            "# TODO: wrap CIRForecaster in a strategy adapter (see PROJECT_2_PLAN.md\n"
            "# Week 2 Day Thu 28: strategies/baseline_mcdm_cir.py).\n"
        ),
        md("## Ablation 4 - Markov-switching short-rate (2-state on utilization)"),
        code(
            "try:\n"
            "    from forecaster.baseline_markov import MarkovSwitchingForecaster\n"
            "    msf = MarkovSwitchingForecaster(n_states=2)\n"
            "    msf.fit(df['r_aave'], df['u_aave'])\n"
            "    r_hat = msf.predict(df['r_aave'].iloc[-200:].values, horizon=12)\n"
            "    print(f'Markov-switching 12h forecast: {r_hat:.4%}')\n"
            "except (ImportError, AttributeError) as e:\n"
            "    print(f'MarkovSwitchingForecaster not yet available ({e}).')\n"
            "    print('See forecaster/baseline_markov.py for implementation status.')\n"
        ),
        md("## Ablation 5 - CatBoost on hand-crafted features"),
        code(
            "from forecaster.baseline_catboost import CatBoostForecaster, CatBoostConfig\n"
            "\n"
            "cb_cfg = CatBoostConfig(iterations=200, depth=4)\n"
            "cb = CatBoostForecaster(cb_cfg, horizon=12)\n"
            "\n"
            "n_cut = int(0.7 * len(df))\n"
            "cb.fit(df.iloc[:n_cut], val_df=df.iloc[n_cut:])\n"
            "print('CatBoost trained on', n_cut, 'rows; feature count:', len(cb.feature_names_))\n"
        ),
        md("## Roll-up: forecast quality table"),
        code(
            "import pandas as pd\n"
            "rows = []\n"
            "for name, res in [('EMA', res_ema), ('Naive', res_naive)]:\n"
            "    m = res.get_default_metrics()\n"
            "    rows.append({'forecaster': name,\n"
            "                 'apy': getattr(m, 'apy', None),\n"
            "                 'sharpe': getattr(m, 'sharpe', None),\n"
            "                 'max_dd': getattr(m, 'max_drawdown', None)})\n"
            "rollup = pd.DataFrame(rows)\n"
            "rollup\n"
        ),
        md(
            "## Next steps\n\n"
            "- Add CIR and CatBoost as full strategy adapters (Week 2 Day Thu 28 / "
            "  Week 3 Day Tue 2 in the plan).\n"
            "- Compute per-protocol R^2 and directional accuracy (PROJECT_2_PLAN.md S9.4) "
            "  to populate the headline forecaster comparison table.\n\n"
            "Relevant plan section: **PROJECT_2_PLAN.md S10, Ablations 1-5.**\n"
        ),
    ]
    return make_nb(cells)


# ---------------------------------------------------------------------------
# Notebook 6: ablations - architecture (6-8)
# ---------------------------------------------------------------------------

def nb_06():
    cells = [
        md(
            "# 06 - Ablations: Architecture (6-8)\n\n"
            "**Purpose.** Architecture-side ablations from PROJECT_2_PLAN.md S10:\n\n"
            "6. Single-branch DA-GRU (no CNN, no decomposition)\n"
            "7. Dual-branch WITHOUT kink subtraction\n"
            "8. Forecast with ranking-loss only\n\n"
            "Each section instantiates a model variant by mutating `ForecasterConfig` "
            "(or the loss) so the user can do an apples-to-apples training run.\n\n"
            "**Expected runtime.** 2 minutes each (smoke-only, 2 epochs).\n"
        ),
        code(PATH_PREAMBLE),
        code(
            "import torch\n"
            "import numpy as np\n"
            "torch.manual_seed(0); np.random.seed(0)\n"
            "\n"
            "from forecaster.model import DABiGRUCNNForecaster, ForecasterConfig\n"
            "from forecaster.train import _make_synth_df\n"
            "from data.features import extract_features\n"
            "\n"
            "df_raw, kink_aave, kink_comp = _make_synth_df(n_rows=1500)\n"
            "df_feat = extract_features(df_raw, kink_aave, kink_comp).dropna()\n"
            "print(df_feat.shape)\n"
        ),
        md("## Ablation 6 - Single-branch DA-GRU (no CNN)"),
        code(
            "# Trick: configure Branch B with kernels=[1] and a small hidden dim.\n"
            "# Plus we'll pass identical features to A and B - this collapses to a\n"
            "# single-branch model that sees rate + context together.\n"
            "cfg_single = ForecasterConfig(\n"
            "    branch_a_input_dim=3,\n"
            "    branch_b_input_dim=7,\n"
            "    branch_b_cnn_kernels=(1, 1, 1),    # degenerate conv stack\n"
            "    sequence_length=64,\n"
            ")\n"
            "model_single = DABiGRUCNNForecaster(cfg_single)\n"
            "print(f'single-branch variant: {model_single.n_params():,} params')\n"
            "# TODO: train and compare directional accuracy vs the dual-branch default.\n"
        ),
        md("## Ablation 7 - Dual-branch WITHOUT kink subtraction"),
        code(
            "# Branch A normally targets eps = r - f_kink(u). To ablate the kink prior\n"
            "# we feed (r_aave, r_compound, rate_spread) directly instead of\n"
            "# (eps_aave, eps_compound, residual_spread). Architecture unchanged.\n"
            "from forecaster.train import BRANCH_A_COLS\n"
            "\n"
            "print('Default Branch-A inputs:', BRANCH_A_COLS)\n"
            "ABLATED_A_COLS = ('r_aave', 'r_compound', 'rate_spread')\n"
            "print('Ablated Branch-A inputs:', ABLATED_A_COLS)\n"
            "# TODO: rewire DABiGRUCNNDataset to use ABLATED_A_COLS and retrain.\n"
        ),
        md("## Ablation 8 - Ranking-loss only"),
        code(
            "from forecaster.losses import CompositeForecastLoss\n"
            "\n"
            "# Standard composite (alpha, beta, gamma) = (0.4, 0.5, 0.1).\n"
            "loss_default = CompositeForecastLoss(alpha=0.4, beta=0.5, gamma=0.1, quantile_q=0.9)\n"
            "print('default:', loss_default)\n"
            "\n"
            "# Pure ranking variant (weighted-Pearson surrogate alone).\n"
            "loss_rank = CompositeForecastLoss(alpha=0.0, beta=1.0, gamma=0.0, quantile_q=0.9)\n"
            "print('rank-only:', loss_rank)\n"
            "\n"
            "# Smoke-fwd: build a tiny tensor, run both losses, log the difference.\n"
            "y_true = torch.tensor([[0.04], [0.05], [0.03]])\n"
            "y_hat  = torch.tensor([[0.038], [0.052], [0.029]])\n"
            "print('default loss:', loss_default(y_hat, y_true).item())\n"
            "print('rank-only   :', loss_rank(y_hat, y_true).item())\n"
        ),
        md("## Smoke train of a variant (5 epochs)"),
        code(
            "from forecaster.train import DABiGRUCNNDataset, TrainConfig, Trainer\n"
            "from torch.utils.data import DataLoader\n"
            "\n"
            "ds_tr = DABiGRUCNNDataset(df_feat.iloc[:1000], kink_aave, kink_comp,\n"
            "                          input_window=64, forecast_horizon=12)\n"
            "ds_va = DABiGRUCNNDataset(df_feat.iloc[1000:], kink_aave, kink_comp,\n"
            "                          input_window=64, forecast_horizon=12)\n"
            "tr_loader = DataLoader(ds_tr, batch_size=32, shuffle=True, drop_last=True)\n"
            "va_loader = DataLoader(ds_va, batch_size=32, shuffle=False)\n"
            "\n"
            "tr_cfg = TrainConfig(\n"
            "    input_window=64, forecast_horizon=12, batch_size=32,\n"
            "    max_epochs=5, patience=10,\n"
            "    checkpoint_path='forecaster/trained_models/single_branch_smoke.pt',\n"
            ")\n"
            "trainer = Trainer(model_single, tr_cfg, kink_aave, kink_comp,\n"
            "                  mlflow_experiment=None)\n"
            "out = trainer.fit(tr_loader, va_loader)\n"
            "out\n"
        ),
        md(
            "## Next steps\n\n"
            "- Real ablation runs go on Colab with MLflow; this notebook only validates "
            "  the wiring works on CPU.\n"
            "- After all three variants are trained, log directional accuracy from "
            "  `Trainer.history` and add a single comparison plot here.\n\n"
            "Relevant plan section: **PROJECT_2_PLAN.md S10, Ablations 6-8.**\n"
        ),
    ]
    return make_nb(cells)


# ---------------------------------------------------------------------------
# Notebook 7: ablations - MCDM (9-11)
# ---------------------------------------------------------------------------

def nb_07():
    cells = [
        md(
            "# 07 - Ablations: MCDM Variants (9-11)\n\n"
            "**Purpose.** MCDM-side ablations from PROJECT_2_PLAN.md S10:\n\n"
            "9. Equal weights vs tuned weights\n"
            "10. Single-protocol benchmarks (Aave-only, Compound-only)\n"
            "11. Greedy max-forecasted-APY vs TOPSIS-MCDM\n\n"
            "Each section runs a backtest variant on the synthetic panel.\n\n"
            "**Expected runtime.** 1-2 minutes total.\n"
        ),
        code(PATH_PREAMBLE),
        code(SYNTHETIC_FALLBACK),
        code(
            "from backtest.observations_builder import build_all\n"
            "_, (_, val_obs, test_obs) = build_all(synthetic=True)\n"
            "print(f'val={len(val_obs)} test={len(test_obs)}')\n"
        ),
        md("## Ablation 9 - Equal weights vs tuned MCDM weights"),
        code(
            "from strategies.baseline_mcdm_ema import MCDMEMAStrategy, MCDMEMAParams\n"
            "\n"
            "# Tuned defaults from AI Yield Vault paper.\n"
            "tuned = MCDMEMAParams(\n"
            "    INITIAL_BALANCE=1_000_000.0, DEFAULT_INITIAL_ENTITY='AAVE',\n"
            "    W_APY=0.40, W_RISK=0.25, W_COST=0.20, W_STAB=0.15,\n"
            ")\n"
            "equal = MCDMEMAParams(\n"
            "    INITIAL_BALANCE=1_000_000.0, DEFAULT_INITIAL_ENTITY='AAVE',\n"
            "    W_APY=0.25, W_RISK=0.25, W_COST=0.25, W_STAB=0.25,\n"
            ")\n"
            "\n"
            "for name, p in [('tuned', tuned), ('equal', equal)]:\n"
            "    strat = MCDMEMAStrategy(debug=False, params=p)\n"
            "    r = strat.run(test_obs)\n"
            "    m = r.get_default_metrics()\n"
            "    print(f'{name}: APY={getattr(m, \"apy\", None)}  '\n"
            "          f'Sharpe={getattr(m, \"sharpe\", None)}')\n"
        ),
        md("## Ablation 10 - Single-protocol benchmarks"),
        code(
            "from strategies.baseline_buyhold import BuyAndHoldAaveStrategy\n"
            "from base_lending_allocation import BaseLendingAllocationParams\n"
            "\n"
            "# Aave-only: standard buy-and-hold strategy.\n"
            "aave_only = BaseLendingAllocationParams(\n"
            "    INITIAL_BALANCE=1_000_000.0, DEFAULT_INITIAL_ENTITY='AAVE',\n"
            ")\n"
            "r_aave = BuyAndHoldAaveStrategy(debug=False, params=aave_only).run(test_obs)\n"
            "print('Aave-only:', r_aave.get_default_metrics())\n"
            "\n"
            "# Compound-only: same strategy but starting on COMPOUND.\n"
            "comp_only = BaseLendingAllocationParams(\n"
            "    INITIAL_BALANCE=1_000_000.0, DEFAULT_INITIAL_ENTITY='COMPOUND',\n"
            ")\n"
            "r_comp = BuyAndHoldAaveStrategy(debug=False, params=comp_only).run(test_obs)\n"
            "print('Compound-only:', r_comp.get_default_metrics())\n"
        ),
        md("## Ablation 11 - Greedy max-APY vs TOPSIS-MCDM"),
        code(
            "from strategies.baseline_apy_greedy import APYGreedyStrategy, APYGreedyParams\n"
            "\n"
            "params_greedy = APYGreedyParams(\n"
            "    INITIAL_BALANCE=1_000_000.0, DEFAULT_INITIAL_ENTITY='AAVE',\n"
            ")\n"
            "r_greedy = APYGreedyStrategy(debug=False, params=params_greedy).run(test_obs)\n"
            "r_mcdm   = MCDMEMAStrategy(debug=False, params=tuned).run(test_obs)\n"
            "\n"
            "for name, res in [('greedy', r_greedy), ('mcdm', r_mcdm)]:\n"
            "    m = res.get_default_metrics()\n"
            "    print(f'{name}: APY={getattr(m, \"apy\", None)} '\n"
            "          f'turnover-rebalances vs total observations '\n"
            "          f'{len(res.to_dataframe())}')\n"
        ),
        md(
            "## Next steps\n\n"
            "- Replace the greedy-vs-MCDM with the **forecasted-rate** versions once "
            "  Predictive MCDM strategy is wired (Week 2 Day Fri 29).\n"
            "- Plot the same equity overlay as in `04_main_backtest.ipynb` restricted "
            "  to the three MCDM variants.\n\n"
            "Relevant plan section: **PROJECT_2_PLAN.md S10, Ablations 9-11.**\n"
        ),
    ]
    return make_nb(cells)


# ---------------------------------------------------------------------------
# Notebook 8: regime analysis
# ---------------------------------------------------------------------------

def nb_08():
    cells = [
        md(
            "# 08 - Regime Analysis\n\n"
            "**Purpose.** Post-hoc classify hours into low / medium / high volatility "
            "tertiles based on rolling sigma(r_aave) and run the buy-and-hold "
            "baseline per regime to surface conditional performance "
            "(PROJECT_2_PLAN.md S6.4 + S9.5).\n\n"
            "**Prerequisites.** Synthetic-or-real joined panel.\n\n"
            "**Expected runtime.** < 1 minute.\n"
        ),
        code(PATH_PREAMBLE),
        code(SYNTHETIC_FALLBACK),
        md("## 1. Rolling volatility (24h sigma of Aave rate)"),
        code(
            "import numpy as np\n"
            "import matplotlib.pyplot as plt\n"
            "\n"
            "vol = df['r_aave'].rolling(24, min_periods=12).std()\n"
            "fig, ax = plt.subplots(figsize=(11, 4))\n"
            "ax.plot(vol.index, vol.values * 1e4, color='C3')\n"
            "ax.set_title('Rolling 24h std(r_aave) (1e-4 units)')\n"
            "ax.set_xlabel('time'); ax.set_ylabel('sigma * 1e4')\n"
            "plt.tight_layout(); plt.show()\n"
            "\n"
            "# Caption: Volatility regimes are visible as sustained high-sigma\n"
            "# bands. The plan splits these into tertiles for conditional metrics.\n"
        ),
        md("## 2. Tertile-split"),
        code(
            "vol_q1 = vol.quantile(1/3)\n"
            "vol_q2 = vol.quantile(2/3)\n"
            "df_reg = df.assign(vol=vol).dropna()\n"
            "df_reg['regime'] = np.where(df_reg['vol'] <= vol_q1, 'low',\n"
            "                  np.where(df_reg['vol'] <= vol_q2, 'med', 'high'))\n"
            "print(df_reg['regime'].value_counts())\n"
        ),
        md("## 3. Run baseline per regime (buy-and-hold)"),
        code(
            "# Demo: report average rate per regime as a stand-in for full backtest.\n"
            "# A full per-regime backtest splits observations into regime buckets and\n"
            "# runs BuyAndHoldAaveStrategy on each; this requires the observations\n"
            "# builder to accept a row mask. Stubbed here for clarity.\n"
            "summary = df_reg.groupby('regime')[['r_aave', 'r_compound']].agg(['mean', 'std'])\n"
            "summary\n"
        ),
        md("## 4. Compare metrics across regimes"),
        code(
            "fig, ax = plt.subplots(figsize=(8, 4))\n"
            "order = ['low', 'med', 'high']\n"
            "means = [df_reg[df_reg['regime'] == r]['r_aave'].mean() * 100 for r in order]\n"
            "ax.bar(order, means, color=['C0', 'C1', 'C3'])\n"
            "ax.set_ylabel('mean Aave APY % per regime')\n"
            "ax.set_title('Conditional rate level by volatility regime')\n"
            "plt.tight_layout(); plt.show()\n"
        ),
        md("## 5. Skip gracefully when real data missing"),
        code(
            "print(f'Used {\"real\" if is_real else \"synthetic\"} panel for this regime analysis.')\n"
            "if not is_real:\n"
            "    print('Note: synthetic data is locally smooth - regime structure is\\n'\n"
            "          '  not as informative as on the real 18-month panel. Re-run\\n'\n"
            "          '  once data/cached/joined_clean.parquet is materialised.')\n"
        ),
        md(
            "## Next steps\n\n"
            "- Wire `build_all(synthetic=...)` to accept a row mask so we can run the "
            "  full strategy suite per regime, not just compute mean rates.\n"
            "- Add per-regime Sharpe / MaxDD tables to the whitepaper.\n\n"
            "Relevant plan section: **PROJECT_2_PLAN.md S6.4 (Regime Split) and "
            "S9.5 (Regime-Conditional Metrics).**\n"
        ),
    ]
    return make_nb(cells)


# ---------------------------------------------------------------------------
# Notebook 9: OOD USDC depeg test
# ---------------------------------------------------------------------------

def nb_09():
    cells = [
        md(
            "# 09 - OOD USDC Depeg Test (Placeholder)\n\n"
            "**Purpose.** Documents the planned out-of-distribution stress test on "
            "the **March 2023 USDC depeg week** (out of the project's primary "
            "Nov 2024 - Apr 2026 window). The expectation is that the forecaster "
            "degrades on that window and that the MCDM allocator should fall back "
            "gracefully via the f_Stab(dTVL) and f_Risk(u) factors.\n\n"
            "**Data source (planned).** *Rules to Rewards* 2025 dataset (Aave "
            "historical states, public). See PROJECT_2_PLAN.md S10 Ablation 14.\n\n"
            "**Prerequisites.** Once the dataset is downloaded, place it under "
            "`data/cached/ood/`. Until then this notebook prints stubs.\n\n"
            "**Expected runtime.** N/A until the dataset is fetched.\n"
        ),
        code(PATH_PREAMBLE),
        code(SYNTHETIC_FALLBACK),
        md("## 1. Try to load the OOD slice"),
        code(
            "from pathlib import Path\n"
            "import pandas as pd\n"
            "\n"
            "OOD_PATH = ROOT / 'data' / 'cached' / 'ood' / 'usdc_depeg_mar2023.parquet'\n"
            "try:\n"
            "    df_ood = pd.read_parquet(OOD_PATH)\n"
            "    print(f'[real] loaded {len(df_ood):,} rows from {OOD_PATH}')\n"
            "    HAS_OOD = True\n"
            "except FileNotFoundError:\n"
            "    print(f'[stub] {OOD_PATH} not present.')\n"
            "    print('Fetch instructions: see docs/CREDENTIALS_SETUP.md and the\\n'\n"
            "          '\"Rules to Rewards\" 2025 dataset on Aave historical states.')\n"
            "    HAS_OOD = False\n"
            "    df_ood = None\n"
        ),
        md("## 2. Plot the depeg week if data is available"),
        code(
            "import matplotlib.pyplot as plt\n"
            "\n"
            "if HAS_OOD and df_ood is not None:\n"
            "    DEPEG_START = '2023-03-10'\n"
            "    DEPEG_END   = '2023-03-17'\n"
            "    window = df_ood.loc[DEPEG_START:DEPEG_END]\n"
            "    fig, ax = plt.subplots(figsize=(11, 4))\n"
            "    ax.plot(window.index, window['r_aave'] * 100, label='Aave APY %')\n"
            "    if 'r_compound' in window.columns:\n"
            "        ax.plot(window.index, window['r_compound'] * 100, label='Compound APY %')\n"
            "    ax.set_title('USDC depeg week (Mar 10-17, 2023)')\n"
            "    ax.legend(); plt.tight_layout(); plt.show()\n"
            "else:\n"
            "    print('No OOD data; skipping the depeg-week plot.')\n"
        ),
        md("## 3. Forecast degradation expectation"),
        code(
            "# Expected behaviour, from PROJECT_2_PLAN.md S10 Ablation 14:\n"
            "#\n"
            "#   1. The DL forecaster's directional accuracy drops below 55%\n"
            "#      (the minimum acceptable threshold) on the depeg week.\n"
            "#   2. f_Risk(u) rises as borrowers exit, pushing utilization down\n"
            "#      and lowering the MCDM risk-factor for both protocols.\n"
            "#   3. f_Stab(dTVL) penalises both protocols simultaneously because\n"
            "#      TVL contracts sharply at the depeg shock.\n"
            "#   4. Net effect: MCDM hysteresis prevents thrashing; the strategy\n"
            "#      sits on its prior allocation and weathers the week.\n"
            "#\n"
            "# Concrete metric to compute once data is in:\n"
            "#   - hit_rate_ood = mean(sign(r_aave - r_comp) == sign(r_hat_aave - r_hat_comp))\n"
            "#   - delta_apy_ood vs single-protocol benchmark\n"
            "print('Forecast-degradation harness defined; awaiting OOD data fetch.')\n"
        ),
        md("## 4. Citation block"),
        code(
            "CITATION = '''\\\n"
            "Rules to Rewards: a Reinforcement Learning Dataset for DeFi Lending.\\\n"
            "  Hosted on figshare; covers Aave historical states including the\\\n"
            "  March 2023 USDC depeg shock. Used here for ablation 14 (OOD test)\\\n"
            "  per PROJECT_2_PLAN.md S10.\\\n"
            "'''\n"
            "print(CITATION)\n"
        ),
        md("## 5. Code stub: forecaster degradation harness"),
        code(
            "def evaluate_ood(forecaster, df_ood, horizon: int = 12) -> dict:\n"
            "    \"\"\"Compute directional accuracy + bias on the OOD slice.\n"
            "\n"
            "    Stub - actual implementation will iterate the rolling window over\n"
            "    df_ood and accumulate per-protocol residuals.\n"
            "    \"\"\"\n"
            "    return {\n"
            "        'directional_accuracy': float('nan'),\n"
            "        'bias_aave':            float('nan'),\n"
            "        'bias_compound':        float('nan'),\n"
            "        'rmse_aave':            float('nan'),\n"
            "        'rmse_compound':        float('nan'),\n"
            "    }\n"
            "\n"
            "print(evaluate_ood(None, df_ood))\n"
        ),
        md(
            "## Next steps\n\n"
            "- Fetch the Rules-to-Rewards 2025 dataset and persist the depeg slice "
            "  under `data/cached/ood/usdc_depeg_mar2023.parquet`.\n"
            "- Wire the trained ONNX forecaster into `evaluate_ood()` and re-run.\n"
            "- Tabulate degradation vs the in-window test set; expect the f_Risk + "
            "  f_Stab MCDM factors to prevent catastrophic allocation behaviour.\n\n"
            "Relevant plan section: **PROJECT_2_PLAN.md S10 Ablation 14.**\n"
        ),
    ]
    return make_nb(cells)


# ---------------------------------------------------------------------------
# Builder entry point
# ---------------------------------------------------------------------------

NOTEBOOKS = {
    "01_data_exploration.ipynb":         nb_01,
    "02_kink_calibration.ipynb":         nb_02,
    "03_forecaster_training.ipynb":      nb_03,
    "04_main_backtest.ipynb":            nb_04,
    "05_ablations_forecast_value.ipynb": nb_05,
    "06_ablations_architecture.ipynb":   nb_06,
    "07_ablations_mcdm.ipynb":           nb_07,
    "08_regime_analysis.ipynb":          nb_08,
    "09_ood_depeg_test.ipynb":           nb_09,
}


def main():
    for name, fn in NOTEBOOKS.items():
        path = NB_DIR / name
        nb = fn()
        with open(path, "w", encoding="utf-8") as f:
            nbf.write(nb, f)
        nbf.validate(nb)
        print(f"[wrote] {path} ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
