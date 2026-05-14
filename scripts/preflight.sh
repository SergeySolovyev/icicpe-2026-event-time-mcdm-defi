#!/usr/bin/env bash
# Preflight validator for the 3-step Colab finish workflow (Linux/macOS).
# See FINISH.md for the runbook. Mirror of scripts/preflight.ps1.
#
# Usage:
#   ./scripts/preflight.sh
#   ./scripts/preflight.sh --quick   # skip pytest (~12 sec saved)

set -u

QUICK=0
for arg in "$@"; do
    case "$arg" in
        --quick) QUICK=1 ;;
        -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
        *) echo "unknown arg: $arg"; exit 2 ;;
    esac
done

# Color codes
G='\033[32m'  # green
Y='\033[33m'  # yellow
R='\033[31m'  # red
C='\033[36m'  # cyan
D='\033[2m'   # dim
N='\033[0m'   # reset

PASS=0; WARN=0; FAIL=0

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

if [[ -x ".venv/bin/python" ]]; then
    PY=".venv/bin/python"
elif [[ -x ".venv/Scripts/python.exe" ]]; then
    PY=".venv/Scripts/python.exe"   # Git-Bash on Windows fallback
else
    PY=""
fi

result() {
    local status="$1"; shift
    local msg="$1"; shift
    local color
    case "$status" in
        PASS) color="$G"; PASS=$((PASS+1)) ;;
        WARN) color="$Y"; WARN=$((WARN+1)) ;;
        FAIL) color="$R"; FAIL=$((FAIL+1)) ;;
    esac
    printf "${color}[%s]${N} %s\n" "$status" "$msg"
    for rem in "$@"; do
        printf "       ${D}->${N} %s\n" "$rem"
    done
}

section() {
    printf "\n${C}=== %s ===${N}\n" "$1"
}

# ---------------------------------------------------------------------------
section "Pre-Step-1: artifact bundle readiness"
# ---------------------------------------------------------------------------

if [[ -n "$PY" ]]; then
    result PASS "$PY present"
else
    result FAIL ".venv/bin/python (or .venv/Scripts/python.exe) missing" \
        "python3.11 -m venv .venv" \
        ".venv/bin/python -m pip install -r requirements.txt"
fi

if [[ -n "$PY" ]]; then
    ver=$("$PY" -c "import fractal; print(fractal.__version__)" 2>&1)
    if [[ $? -eq 0 && "$ver" == *"1.3.2"* ]]; then
        result PASS "fractal-defi==1.3.2 importable (got $ver)"
    elif [[ $? -eq 0 ]]; then
        result FAIL "fractal-defi version mismatch: got $ver, need 1.3.2" \
            ".venv/bin/python -m pip install -r requirements.txt"
    else
        result FAIL "fractal-defi not importable" \
            ".venv/bin/python -m pip install -r requirements.txt"
    fi
else
    result FAIL "fractal-defi check skipped (no python)"
fi

PARQUET="data/cached/joined_clean.parquet"
if [[ -f "$PARQUET" ]]; then
    if [[ -n "$PY" ]]; then
        rows=$("$PY" -c "import pyarrow.parquet as pq; print(pq.read_table('$PARQUET').num_rows)" 2>&1)
        if [[ $? -eq 0 && "$rows" -gt 10000 ]] 2>/dev/null; then
            result PASS "joined_clean.parquet present ($rows rows)"
        else
            result FAIL "joined_clean.parquet has only $rows rows (need >10000)" "make data"
        fi
    else
        result WARN "joined_clean.parquet present but row count unverified (no python)"
    fi
else
    result FAIL "$PARQUET missing" "make data"
fi

KINK="data/cached/kink_params.json"
if [[ -f "$KINK" ]]; then
    if [[ -n "$PY" ]]; then
        kp_check=$("$PY" -c "import json; d=json.load(open('$KINK')); print('aave' in d, 'compound' in d)" 2>&1)
        if [[ "$kp_check" == "True True" ]]; then
            result PASS "kink_params.json has 'aave' and 'compound' keys"
        else
            result FAIL "kink_params.json missing required keys ($kp_check)" \
                ".venv/bin/python -m data.fetch_kink_params"
        fi
    else
        result WARN "kink_params.json present but keys unverified (no python)"
    fi
else
    result FAIL "$KINK missing" ".venv/bin/python -m data.fetch_kink_params"
fi

missing=()
for f in model.py train.py losses.py export_onnx.py; do
    [[ -f "forecaster/$f" ]] || missing+=("$f")
done
if [[ ${#missing[@]} -eq 0 ]]; then
    result PASS "forecaster/{model,train,losses,export_onnx}.py all present"
else
    result FAIL "forecaster missing: ${missing[*]}" "git status"
fi

if [[ -f "data/features.py" ]]; then
    result PASS "data/features.py present"
else
    result FAIL "data/features.py missing" "git status"
fi

if [[ -n "$PY" ]]; then
    if "$PY" -m scripts.prepare_colab_artifacts --dry-run >/dev/null 2>&1; then
        result PASS "prepare_colab_artifacts --dry-run clean"
    else
        result FAIL "prepare_colab_artifacts --dry-run failed" \
            ".venv/bin/python -m scripts.prepare_colab_artifacts --dry-run"
    fi
else
    result WARN "prepare_colab_artifacts dry-run skipped (no python)"
fi

# ---------------------------------------------------------------------------
section "Pre-Step-2: Colab GPU readiness"
# ---------------------------------------------------------------------------

NB="notebooks/colab/train_da_bigru_cnn_colab.ipynb"
if [[ -f "$NB" ]]; then
    if [[ -n "$PY" ]]; then
        if "$PY" -c "import nbformat; nbformat.validate(nbformat.read('$NB', as_version=4))" >/dev/null 2>&1; then
            result PASS "train_da_bigru_cnn_colab.ipynb exists and nbformat-validates"
        else
            result FAIL "notebook fails nbformat validation" \
                ".venv/bin/python -m nbformat.validate $NB"
        fi
    else
        result WARN "notebook present, nbformat check skipped (no python)"
    fi
else
    result FAIL "$NB missing"
fi

ZIP="predictive-mcdm-defi-artifacts.zip"
if [[ -f "$ZIP" ]]; then
    size=$(stat -c%s "$ZIP" 2>/dev/null || stat -f%z "$ZIP" 2>/dev/null)
    mb=$(awk -v s="$size" 'BEGIN{printf "%.2f", s/1048576}')
    if [[ "$size" -gt 512000 && "$size" -lt 52428800 ]]; then
        result PASS "artifacts zip present ($mb MB, in 0.5-50 MB bounds)"
    else
        result WARN "artifacts zip size suspicious: $mb MB" \
            ".venv/bin/python -m scripts.prepare_colab_artifacts"
    fi
else
    result WARN "predictive-mcdm-defi-artifacts.zip missing -- run prepare_colab_artifacts first" \
        ".venv/bin/python -m scripts.prepare_colab_artifacts"
fi

# ---------------------------------------------------------------------------
section "Pre-Step-3: post-Colab backtest readiness"
# ---------------------------------------------------------------------------

ONNX="forecaster/trained_models/dual_branch_kink.onnx"
if [[ -f "$ONNX" ]]; then
    sz=$(stat -c%s "$ONNX" 2>/dev/null || stat -f%z "$ONNX" 2>/dev/null)
    kb=$(awk -v s="$sz" 'BEGIN{printf "%.1f", s/1024}')
    result PASS "dual_branch_kink.onnx present ($kb KB)"
else
    result WARN "dual_branch_kink.onnx not found" \
        "python -m scripts.local_smoke_train       (CPU dummy, ~3 min)" \
        "or finish Colab GPU training              (~45 min, real quality)"
fi

if [[ -n "$PY" ]]; then
    if "$PY" -c "import backtest.run_main, backtest.run_ablations" >/dev/null 2>&1; then
        result PASS "backtest.run_main and backtest.run_ablations importable"
    else
        result FAIL "backtest modules fail to import" \
            ".venv/bin/python -c 'import backtest.run_main, backtest.run_ablations'"
    fi

    fill_out=$("$PY" -m scripts.fill_whitepaper_results --dry-run 2>&1)
    if [[ $? -eq 0 ]]; then
        result PASS "fill_whitepaper_results --dry-run resolves all macros"
    else
        if echo "$fill_out" | grep -q "results[\\/]tables"; then
            result WARN "fill_whitepaper_results needs backtest CSVs (run Step 3 backtests first)" \
                ".venv/bin/python -m backtest.run_main" \
                ".venv/bin/python -m backtest.run_ablations"
        else
            result FAIL "fill_whitepaper_results --dry-run failed (unmapped macros?)" \
                ".venv/bin/python -m scripts.fill_whitepaper_results --dry-run"
        fi
    fi
else
    result WARN "backtest import + fill_whitepaper_results dry-run skipped (no python)"
fi

MAIN_TEX="whitepaper/main.tex"
if [[ -f "$MAIN_TEX" ]]; then
    unwired=()
    for s in 06_data 09_results 10_discussion; do
        if ! grep -q "\\\\input{sections/$s" "$MAIN_TEX"; then
            unwired+=("sections/$s")
        fi
    done
    if [[ ${#unwired[@]} -eq 0 ]]; then
        result PASS "whitepaper/main.tex wires 06_data, 09_results, 10_discussion"
    else
        result WARN "main.tex missing \\input for: ${unwired[*]}" \
            "add \\input{sections/<file>} to whitepaper/main.tex for: ${unwired[*]}"
    fi
else
    result FAIL "whitepaper/main.tex missing"
fi

if command -v pdflatex >/dev/null 2>&1 && command -v biber >/dev/null 2>&1; then
    result PASS "pdflatex and biber on PATH"
else
    miss=()
    command -v pdflatex >/dev/null 2>&1 || miss+=("pdflatex")
    command -v biber    >/dev/null 2>&1 || miss+=("biber")
    result WARN "LaTeX tools missing: ${miss[*]} (needed for final recompile)" \
        "Install TeX Live or MiKTeX, then add to PATH"
fi

# ---------------------------------------------------------------------------
section "Test suite"
# ---------------------------------------------------------------------------

if [[ $QUICK -eq 1 ]]; then
    result WARN "pytest skipped (--quick)" "./scripts/preflight.sh    # full run"
elif [[ -n "$PY" ]]; then
    if [[ -x ".venv/bin/pytest" ]]; then
        PYTEST=".venv/bin/pytest"
        out=$("$PYTEST" tests/ -m 'not network' -q 2>&1)
    else
        out=$("$PY" -m pytest tests/ -m 'not network' -q 2>&1)
    fi
    rc=$?
    tail=$(echo "$out" | tail -n 3 | tr '\n' ' ')
    if [[ $rc -eq 0 ]]; then
        n=$(echo "$tail" | grep -oE '[0-9]+ passed' | head -1 | grep -oE '[0-9]+')
        n=${n:-0}
        if [[ "$n" -ge 32 ]]; then
            result PASS "pytest tests/ -m 'not network': $n passed"
        else
            result WARN "pytest passed but only $n tests (expected 32+)"
        fi
    else
        result FAIL "pytest failed: $tail" ".venv/bin/pytest tests/ -m 'not network' -v"
    fi
else
    result WARN "pytest skipped (no python)"
fi

# ---------------------------------------------------------------------------
echo ""
printf "${C}============================================================${N}\n"
if [[ $FAIL -gt 0 ]]; then
    verdict="${R}NOT READY${N}"
else
    verdict="${G}Ready for Colab${N}"
fi
printf "PREFLIGHT: %d PASS, %d WARN, %d FAIL -- %b\n" "$PASS" "$WARN" "$FAIL" "$verdict"
printf "${C}============================================================${N}\n"

if [[ $FAIL -gt 0 ]]; then exit 1; else exit 0; fi
