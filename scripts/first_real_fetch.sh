#!/usr/bin/env bash
# First real-data pull — bash equivalent of first_real_fetch.ps1.
# Run AFTER .env contains THE_GRAPH_API_KEY.
#
# Usage:  bash scripts/first_real_fetch.sh
#
# What it does (~10 minutes wall-clock):
#   1. Verify .env has THE_GRAPH_API_KEY
#   2. Fetch 18 months of Aave V3 USDC hourly rates
#   3. Fetch 18 months of Compound V3 cUSDCv3 hourly rates
#   4. Refresh kink params from Aave gateway
#   5. data/clean.py to join + ffill + sign-convention lock-in
#   6. Run pytest (sign-convention tests now exercise real data)
#   7. Print on-disk summary
set -euo pipefail
PYTHON="./.venv/bin/python"
# Fallback for Windows-built venv layout
if [[ ! -x "$PYTHON" ]]; then PYTHON="./.venv/Scripts/python.exe"; fi

if [[ ! -f .env ]]; then
    echo "ERROR: .env not found. Create it with:" >&2
    echo "  THE_GRAPH_API_KEY=<your-32-char-hex>" >&2
    echo "See docs/CREDENTIALS_SETUP.md" >&2
    exit 1
fi
if ! grep -qE '^THE_GRAPH_API_KEY=\S{20,}' .env; then
    echo "ERROR: .env present but THE_GRAPH_API_KEY missing or empty." >&2
    exit 1
fi
echo "[1/7] .env OK"

echo "[2/7] Fetching Aave V3 USDC hourly (18 months)..."
"$PYTHON" -m data.fetch_aave_subgraph

echo "[3/7] Fetching Compound V3 cUSDCv3 hourly (18 months)..."
"$PYTHON" -m data.fetch_compound

echo "[4/7] Refreshing kink params (Aave gateway)..."
"$PYTHON" -m data.fetch_kink_params --force

echo "[5/7] Cleaning + joining to hourly UTC grid..."
"$PYTHON" -m data.clean --force

echo "[6/7] Running pytest (sign-convention tests now use REAL data)..."
.venv/bin/pytest tests/ -v -m "not network" || \
    .venv/Scripts/pytest.exe tests/ -v -m "not network" || \
    echo "WARNING: pytest had failures. Inspect before proceeding."

echo "[7/7] Summary:"
"$PYTHON" - <<'PY'
import pandas as pd
from pathlib import Path
for name, path in [
    ('Aave V3 hourly',     'data/cached/aave_v3_subgraph_usdc_eth_2024-11_to_2026-04.parquet'),
    ('Compound V3 hourly', 'data/cached/compound_v3_usdc_eth_2024-11_to_2026-04.parquet'),
    ('joined_clean',       'data/cached/joined_clean.parquet'),
]:
    p = Path(path)
    if p.exists():
        df = pd.read_parquet(p)
        rng = f"{df.index[0]} -> {df.index[-1]}" if hasattr(df.index, "min") else "n/a"
        print(f"  [OK] {name:25s}  {len(df):>6,} rows  {rng}")
    else:
        print(f"  [MISSING] {name:25s}  {path}")
PY

echo
echo "Done. Next: train in Colab (notebooks/colab/train_da_bigru_cnn_colab.ipynb)"
echo "After training -> commit ONNX -> run backtest.run_main on the real test window."
