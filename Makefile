# Predictive MCDM DeFi — top-level task runner
#
# Use: make <target>
# All Python invocations go through the venv at .venv/

PY      := .venv/Scripts/python.exe       # Windows; on Linux: .venv/bin/python
PYTEST  := .venv/Scripts/pytest.exe       # Windows; on Linux: .venv/bin/pytest

.PHONY: help install verify-imports data train backtest ablations whitepaper test clean \
        preflight smoke-train colab-bundle fill-results finish

help:
	@echo "Project pipeline (3-step user finish workflow in FINISH.md):"
	@echo ""
	@echo "  preflight       go/no-go check before each step"
	@echo "  colab-bundle    package zip for Colab GPU training (USER ACTION 1)"
	@echo "  smoke-train     local CPU dummy ONNX (validates pipeline before Colab)"
	@echo "  backtest        run_main + run_ablations on real test window"
	@echo "  fill-results    substitute real numbers into whitepaper sec 8"
	@echo "  whitepaper      compile whitepaper PDF (3-pass biber + pdflatex)"
	@echo "  finish          backtest + fill-results + whitepaper in one go"
	@echo ""
	@echo "Lower-level targets:"
	@echo "  install         pip install -r requirements.txt into .venv"
	@echo "  verify-imports  smoke-test that key fractal-defi classes import"
	@echo "  data            fetch + clean all 18 months of data"
	@echo "  train           train DA-BiGRU-CNN forecaster (MLflow grid; use Colab for GPU)"
	@echo "  ablations       run all 15 ablations from plan S10"
	@echo "  test            run pytest"
	@echo "  clean           remove __pycache__ + caches"

install:
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt

verify-imports:
	$(PY) -c "from fractal.core.base.strategy.strategy import BaseStrategy; \
	          from fractal.core.entities.protocols.aave import AaveEntity; \
	          from fractal.loaders.aave import AaveV3RatesLoader; \
	          from fractal.loaders.structs import LendingHistory; \
	          from fractal.core.pipeline import DefaultPipeline; \
	          from fractal.strategies.basis_trading_strategy import BasisTradingStrategy; \
	          print('All key imports OK')"

data:
	$(PY) -m data.fetch_aave
	$(PY) -m data.fetch_compound
	$(PY) -m data.fetch_gas_eth
	$(PY) -m data.clean

train:
	$(PY) -m forecaster.train

backtest:
	$(PY) -m backtest.run_baselines
	$(PY) -m backtest.run_main

ablations:
	$(PY) -m backtest.run_ablations

test:
	$(PYTEST) tests/ -v

whitepaper:
	cd whitepaper && latexmk -pdf main.tex && latexmk -c

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true

# Pipeline targets (see FINISH.md for full workflow)
preflight:
	$(PY) -m scripts.preflight 2>/dev/null || powershell -ExecutionPolicy Bypass -File scripts/preflight.ps1

smoke-train:
	$(PY) -m scripts.local_smoke_train --epochs 2

colab-bundle:
	$(PY) -m scripts.prepare_colab_artifacts

fill-results:
	$(PY) -m scripts.fill_whitepaper_results

# Run the whole post-Colab finish in one shot (assumes ONNX is already in forecaster/trained_models/)
finish:
	$(PY) -m backtest.run_main
	$(PY) -m backtest.run_ablations
	$(PY) -m scripts.fill_whitepaper_results
	cd whitepaper && pdflatex -interaction=nonstopmode main.tex && biber main && pdflatex -interaction=nonstopmode main.tex && pdflatex -interaction=nonstopmode main.tex
