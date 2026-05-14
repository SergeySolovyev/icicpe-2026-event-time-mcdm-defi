# First real-data pull — run AFTER .env contains THE_GRAPH_API_KEY.
#
# Usage:
#   .\scripts\first_real_fetch.ps1
#
# What it does (~10 minutes wall-clock):
#   1. Verify .env has THE_GRAPH_API_KEY
#   2. Fetch 18 months of Aave V3 USDC hourly rates (TheGraph protocol-subgraph)
#   3. Fetch 18 months of Compound V3 USDC hourly rates (Messari subgraph)
#   4. Refresh kink params from Aave gateway (no key needed for this)
#   5. Run data/clean.py to join + ffill + sign-convention lock-in
#   6. Run pytest on the data pipeline (the 3 sign-convention tests that were
#      previously skipped will now run against real data and lock-in correctness)
#   7. Print a summary of what we now have on disk

$ErrorActionPreference = "Stop"
$PYTHON = ".\.venv\Scripts\python.exe"

# Step 1: verify .env
if (-Not (Test-Path ".env")) {
    Write-Host "ERROR: .env not found. Create it with:" -ForegroundColor Red
    Write-Host "  THE_GRAPH_API_KEY=<your-32-char-hex>" -ForegroundColor Yellow
    Write-Host "See docs/CREDENTIALS_SETUP.md for the 3-minute signup."
    exit 1
}
$env_content = Get-Content .env -Raw
if ($env_content -notmatch "THE_GRAPH_API_KEY=\S{20,}") {
    Write-Host "ERROR: .env present but THE_GRAPH_API_KEY missing or empty." -ForegroundColor Red
    exit 1
}
Write-Host "[1/7] .env OK" -ForegroundColor Green

# Step 2: Aave V3 hourly
Write-Host "[2/7] Fetching Aave V3 USDC hourly (18 months)..." -ForegroundColor Cyan
& $PYTHON -m data.fetch_aave_subgraph
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# Step 3: Compound V3 hourly
Write-Host "[3/7] Fetching Compound V3 cUSDCv3 hourly (18 months)..." -ForegroundColor Cyan
& $PYTHON -m data.fetch_compound
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# Step 4: kink params (gateway, no key)
Write-Host "[4/7] Refreshing kink params (Aave gateway, Compound snapshot)..." -ForegroundColor Cyan
& $PYTHON -m data.fetch_kink_params --force
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# Step 5: clean + join
Write-Host "[5/7] Cleaning + joining to hourly UTC grid..." -ForegroundColor Cyan
& $PYTHON -m data.clean --force
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# Step 6: pytest — sign convention now exercised against real data
Write-Host "[6/7] Running pytest (sign-convention tests now use REAL data)..." -ForegroundColor Cyan
& .\.venv\Scripts\pytest.exe tests/ -v -m "not network"
if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNING: pytest had failures. Inspect before proceeding to train." -ForegroundColor Yellow
}

# Step 7: summary
Write-Host "[7/7] Summary:" -ForegroundColor Green
& $PYTHON -c @"
import pandas as pd
from pathlib import Path

for name, path in [
    ('Aave V3 hourly',   'data/cached/aave_v3_subgraph_usdc_eth_2024-11_to_2026-04.parquet'),
    ('Compound V3 hourly','data/cached/compound_v3_usdc_eth_2024-11_to_2026-04.parquet'),
    ('joined_clean',     'data/cached/joined_clean.parquet'),
]:
    p = Path(path)
    if p.exists():
        df = pd.read_parquet(p)
        rng = f'{df.index[0]} -> {df.index[-1]}' if hasattr(df.index, 'min') else 'n/a'
        print(f'  [OK] {name:25s}  {len(df):>6,} rows  {rng}')
    else:
        print(f'  [MISSING] {name:25s}  {path}')
"@

Write-Host ""
Write-Host "Done. Next: run training in Colab (notebooks/colab/train_da_bigru_cnn_colab.ipynb)" -ForegroundColor Green
Write-Host "After training -> commit ONNX -> run backtest.run_main on the real test window."
