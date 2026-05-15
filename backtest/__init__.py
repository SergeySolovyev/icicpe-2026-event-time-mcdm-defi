"""Backtest entry points: baselines, main strategy, 15 ablations, MLflow grid search.

DLL-order preload (Windows). ``python -m backtest.run_main`` /
``backtest.run_ablations`` execute this package ``__init__`` BEFORE the
entry-point module body runs ``import numpy`` / ``pandas`` / ``fractal``.
Mirrors the repo-root ``conftest.py`` boundary that protects pytest:
numpy's MKL preload shadows symbols ``onnxruntime_pybind11_state`` (and
torch's ``c10.dll``) need, so onnxruntime — lazily imported by
``strategies.predictive_mcdm`` — fails with a Windows DLL load error
unless torch+onnxruntime are imported first. Importing them here gives
both libraries the load order they need, for every backtest entry point,
without adding a torch-first import to the entry modules (which use
``from __future__ import annotations`` — incompatible with the
torch-first workaround per CLAUDE.md).
"""
try:
    import torch  # noqa: F401 — side-effect import order
except Exception as e:                  # pragma: no cover  # noqa: BLE001
    import warnings
    warnings.warn(f"torch import failed at backtest package init: {e}")

try:
    import onnxruntime  # noqa: F401 — side-effect import order
except Exception as e:                  # pragma: no cover  # noqa: BLE001
    import warnings
    warnings.warn(f"onnxruntime import failed at backtest package init: {e}")
