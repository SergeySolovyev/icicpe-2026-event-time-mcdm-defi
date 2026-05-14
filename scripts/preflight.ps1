<#
.SYNOPSIS
    Preflight validator for the 3-step Colab finish workflow.

.DESCRIPTION
    Runs a battery of checks for FINISH.md Steps 1, 2, 3. Emits color-coded
    PASS / WARN / FAIL lines with remediation commands and a summary.

.PARAMETER Quick
    Skip the pytest run (~12 sec saved).

.EXAMPLE
    .venv\Scripts\python.exe -V  # ensure venv exists
    .\scripts\preflight.ps1
    .\scripts\preflight.ps1 -Quick
#>

[CmdletBinding()]
param(
    [switch]$Quick
)

$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$script:Pass = 0
$script:Warn = 0
$script:Fail = 0

function Write-Result {
    param(
        [ValidateSet('PASS', 'WARN', 'FAIL')] [string]$Status,
        [string]$Message,
        [string[]]$Remediation = @()
    )
    $color = switch ($Status) { 'PASS' { 'Green' } 'WARN' { 'Yellow' } 'FAIL' { 'Red' } }
    Write-Host ("[{0}] " -f $Status) -ForegroundColor $color -NoNewline
    Write-Host $Message
    foreach ($r in $Remediation) {
        Write-Host ("       -> " + $r) -ForegroundColor DarkGray
    }
    switch ($Status) {
        'PASS' { $script:Pass++ }
        'WARN' { $script:Warn++ }
        'FAIL' { $script:Fail++ }
    }
}

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host ("=== {0} ===" -f $Title) -ForegroundColor Cyan
}

$PY = Join-Path $repo '.venv\Scripts\python.exe'

# ---------------------------------------------------------------------------
Write-Section 'Pre-Step-1: artifact bundle readiness'
# ---------------------------------------------------------------------------

if (Test-Path $PY) {
    Write-Result PASS ".venv\Scripts\python.exe present"
} else {
    Write-Result FAIL ".venv\Scripts\python.exe missing" @(
        'py -3.11 -m venv .venv',
        '.venv\Scripts\python.exe -m pip install -r requirements.txt'
    )
}

if (Test-Path $PY) {
    $fractalCheck = & $PY -c "import fractal; print(fractal.__version__)" 2>&1
    if ($LASTEXITCODE -eq 0 -and $fractalCheck -match '1\.3\.2') {
        Write-Result PASS ("fractal-defi==1.3.2 importable (got {0})" -f $fractalCheck.Trim())
    } elseif ($LASTEXITCODE -eq 0) {
        Write-Result FAIL ("fractal-defi version mismatch: got {0}, need 1.3.2" -f $fractalCheck.Trim()) @(
            '.venv\Scripts\python.exe -m pip install -r requirements.txt'
        )
    } else {
        Write-Result FAIL "fractal-defi not importable" @(
            '.venv\Scripts\python.exe -m pip install -r requirements.txt'
        )
    }
} else {
    Write-Result FAIL "fractal-defi check skipped (no python)" @()
}

$parquet = Join-Path $repo 'data\cached\joined_clean.parquet'
if (Test-Path $parquet) {
    if (Test-Path $PY) {
        $rows = & $PY -c "import pyarrow.parquet as pq; print(pq.read_table(r'$parquet').num_rows)" 2>&1
        if ($LASTEXITCODE -eq 0 -and [int]$rows -gt 10000) {
            Write-Result PASS ("joined_clean.parquet present ({0} rows)" -f $rows.Trim())
        } else {
            Write-Result FAIL ("joined_clean.parquet has only {0} rows (need >10000)" -f $rows.Trim()) @(
                'make data'
            )
        }
    } else {
        Write-Result WARN "joined_clean.parquet present but row count unverified (no python)"
    }
} else {
    Write-Result FAIL "data\cached\joined_clean.parquet missing" @('make data')
}

$kink = Join-Path $repo 'data\cached\kink_params.json'
if (Test-Path $kink) {
    try {
        $kp = Get-Content $kink -Raw | ConvertFrom-Json
        $hasAave = $kp.PSObject.Properties.Name -contains 'aave'
        $hasComp = $kp.PSObject.Properties.Name -contains 'compound'
        if ($hasAave -and $hasComp) {
            Write-Result PASS "kink_params.json has 'aave' and 'compound' keys"
        } else {
            Write-Result FAIL ("kink_params.json missing keys (aave={0}, compound={1})" -f $hasAave, $hasComp) @(
                '.venv\Scripts\python.exe -m data.fetch_kink_params'
            )
        }
    } catch {
        Write-Result FAIL "kink_params.json unparseable" @('.venv\Scripts\python.exe -m data.fetch_kink_params')
    }
} else {
    Write-Result FAIL "data\cached\kink_params.json missing" @('.venv\Scripts\python.exe -m data.fetch_kink_params')
}

$forecasterFiles = @('model.py', 'train.py', 'losses.py', 'export_onnx.py')
$missing = @()
foreach ($f in $forecasterFiles) {
    if (-not (Test-Path (Join-Path $repo "forecaster\$f"))) { $missing += $f }
}
if ($missing.Count -eq 0) {
    Write-Result PASS "forecaster/{model,train,losses,export_onnx}.py all present"
} else {
    Write-Result FAIL ("forecaster missing: {0}" -f ($missing -join ', ')) @('git status')
}

if (Test-Path (Join-Path $repo 'data\features.py')) {
    Write-Result PASS "data/features.py present"
} else {
    Write-Result FAIL "data/features.py missing" @('git status')
}

if (Test-Path $PY) {
    $dryOut = & $PY -m scripts.prepare_colab_artifacts --dry-run 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Result PASS "prepare_colab_artifacts --dry-run clean"
    } else {
        Write-Result FAIL "prepare_colab_artifacts --dry-run failed" @(
            '.venv\Scripts\python.exe -m scripts.prepare_colab_artifacts --dry-run'
        )
    }
} else {
    Write-Result WARN "prepare_colab_artifacts dry-run skipped (no python)"
}

# ---------------------------------------------------------------------------
Write-Section 'Pre-Step-2: Colab GPU readiness'
# ---------------------------------------------------------------------------

$nb = Join-Path $repo 'notebooks\colab\train_da_bigru_cnn_colab.ipynb'
if (Test-Path $nb) {
    if (Test-Path $PY) {
        $nbCheck = & $PY -c "import nbformat; nbformat.validate(nbformat.read(r'$nb', as_version=4)); print('ok')" 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Result PASS "train_da_bigru_cnn_colab.ipynb exists and nbformat-validates"
        } else {
            Write-Result FAIL "notebook fails nbformat validation" @('.venv\Scripts\python.exe -m nbformat.validate ' + $nb)
        }
    } else {
        Write-Result WARN "notebook present, nbformat check skipped"
    }
} else {
    Write-Result FAIL "notebooks/colab/train_da_bigru_cnn_colab.ipynb missing" @()
}

$zip = Join-Path $repo 'predictive-mcdm-defi-artifacts.zip'
if (Test-Path $zip) {
    $size = (Get-Item $zip).Length
    $kb = [math]::Round($size / 1KB, 1)
    $mb = [math]::Round($size / 1MB, 2)
    if ($size -gt 500KB -and $size -lt 50MB) {
        Write-Result PASS ("artifacts zip present ({0} MB, in 0.5-50 MB bounds)" -f $mb)
    } else {
        Write-Result WARN ("artifacts zip size suspicious: {0} KB" -f $kb) @(
            '.venv\Scripts\python.exe -m scripts.prepare_colab_artifacts'
        )
    }
} else {
    Write-Result WARN "predictive-mcdm-defi-artifacts.zip missing -- run prepare_colab_artifacts first" @(
        '.venv\Scripts\python.exe -m scripts.prepare_colab_artifacts'
    )
}

# ---------------------------------------------------------------------------
Write-Section 'Pre-Step-3: post-Colab backtest readiness'
# ---------------------------------------------------------------------------

$onnx = Join-Path $repo 'forecaster\trained_models\dual_branch_kink.onnx'
if (Test-Path $onnx) {
    $sz = [math]::Round((Get-Item $onnx).Length / 1KB, 1)
    Write-Result PASS ("dual_branch_kink.onnx present ({0} KB)" -f $sz)
} else {
    Write-Result WARN "dual_branch_kink.onnx not found" @(
        'python -m scripts.local_smoke_train       (CPU dummy, ~3 min)',
        'or finish Colab GPU training              (~45 min, real quality)'
    )
}

if (Test-Path $PY) {
    $impCheck = & $PY -c "import backtest.run_main, backtest.run_ablations; print('ok')" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Result PASS "backtest.run_main and backtest.run_ablations importable"
    } else {
        Write-Result FAIL "backtest modules fail to import" @(
            '.venv\Scripts\python.exe -c "import backtest.run_main, backtest.run_ablations"'
        )
    }

    $fillOut = & $PY -m scripts.fill_whitepaper_results --dry-run 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Result PASS "fill_whitepaper_results --dry-run resolves all macros"
    } else {
        $msg = ($fillOut -join "`n")
        if ($msg -match 'results[\\/]tables') {
            Write-Result WARN "fill_whitepaper_results needs backtest CSVs (run Step 3 backtests first)" @(
                '.venv\Scripts\python.exe -m backtest.run_main',
                '.venv\Scripts\python.exe -m backtest.run_ablations'
            )
        } else {
            Write-Result FAIL "fill_whitepaper_results --dry-run failed (unmapped macros?)" @(
                '.venv\Scripts\python.exe -m scripts.fill_whitepaper_results --dry-run'
            )
        }
    }
} else {
    Write-Result WARN "backtest import + fill_whitepaper_results dry-run skipped (no python)"
}

$mainTex = Join-Path $repo 'whitepaper\main.tex'
if (Test-Path $mainTex) {
    $tex = Get-Content $mainTex -Raw
    $expected = @('sections/06_data', 'sections/09_results', 'sections/10_discussion')
    $wired = @()
    $unwired = @()
    foreach ($e in $expected) {
        if ($tex -match [regex]::Escape("\input{$e")) { $wired += $e } else { $unwired += $e }
    }
    if ($unwired.Count -eq 0) {
        Write-Result PASS "whitepaper/main.tex wires 06_data, 09_results, 10_discussion"
    } else {
        Write-Result WARN ("main.tex missing \\input for: {0}" -f ($unwired -join ', ')) @(
            ("add \input{{sections/<file>}} to whitepaper\main.tex for: {0}" -f ($unwired -join ', '))
        )
    }
} else {
    Write-Result FAIL "whitepaper/main.tex missing" @()
}

$pdflatex = Get-Command pdflatex -ErrorAction SilentlyContinue
$biber = Get-Command biber -ErrorAction SilentlyContinue
if ($pdflatex -and $biber) {
    Write-Result PASS "pdflatex and biber on PATH"
} else {
    $miss = @()
    if (-not $pdflatex) { $miss += 'pdflatex' }
    if (-not $biber)    { $miss += 'biber' }
    Write-Result WARN ("LaTeX tools missing: {0} (needed for final recompile)" -f ($miss -join ', ')) @(
        'Install MiKTeX or TeX Live, then add to PATH'
    )
}

# ---------------------------------------------------------------------------
Write-Section 'Test suite'
# ---------------------------------------------------------------------------

if ($Quick) {
    Write-Result WARN "pytest skipped (--Quick)" @('.\scripts\preflight.ps1   # full run')
} elseif (Test-Path $PY) {
    $pytestExe = Join-Path $repo '.venv\Scripts\pytest.exe'
    if (-not (Test-Path $pytestExe)) { $pytestExe = $PY; $pyArgs = @('-m', 'pytest') } else { $pyArgs = @() }
    $out = & $pytestExe @pyArgs tests/ -m 'not network' -q 2>&1
    $tail = ($out | Select-Object -Last 3) -join ' '
    if ($LASTEXITCODE -eq 0) {
        $m = [regex]::Match($tail, '(\d+)\s+passed')
        $n = if ($m.Success) { [int]$m.Groups[1].Value } else { 0 }
        if ($n -ge 32) {
            Write-Result PASS ("pytest tests/ -m 'not network': {0} passed" -f $n)
        } else {
            Write-Result WARN ("pytest passed but only {0} tests (expected 32+)" -f $n)
        }
    } else {
        Write-Result FAIL ("pytest failed: {0}" -f $tail) @('.venv\Scripts\pytest.exe tests/ -m "not network" -v')
    }
} else {
    Write-Result WARN "pytest skipped (no python)"
}

# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
$verdict = if ($script:Fail -gt 0) { 'NOT READY' } else { 'Ready for Colab' }
$verdictColor = if ($script:Fail -gt 0) { 'Red' } else { 'Green' }
Write-Host ("PREFLIGHT: {0} PASS, {1} WARN, {2} FAIL -- " -f $script:Pass, $script:Warn, $script:Fail) -NoNewline
Write-Host $verdict -ForegroundColor $verdictColor
Write-Host "============================================================" -ForegroundColor Cyan

if ($script:Fail -gt 0) { exit 1 } else { exit 0 }
