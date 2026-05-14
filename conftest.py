"""Top-level pytest conftest.

Imports torch BEFORE pytest collects any test modules. This is necessary
on Windows with torch 2.12 + numpy 1.26 because numpy's MKL preload
shadows symbols torch's c10.dll needs (manifests as `OSError [WinError
1114] DLL initialization routine failed`).

Without this file, pytest collects test_data_pipeline.py first (which
imports pandas -> numpy via data.features), then test_forecaster_numerical.py
imports torch which crashes. With torch loaded first at the conftest
boundary, both libraries get the load order they need.

This file MUST live at the repo root (NOT inside tests/) so it runs
during the rootdir/session-startup phase, before any individual test
file is collected.
"""
try:
    import torch  # noqa: F401 — side-effect import order
except Exception as e:                  # pragma: no cover
    # If torch can't import at all (CPU-only sandbox without MKL libs),
    # let individual forecaster tests fail with a clearer message rather
    # than collection-time crash.
    import warnings
    warnings.warn(f"torch import failed at conftest: {e}")

# Same DLL-order issue affects onnxruntime: its `onnxruntime_pybind11_state`
# native extension fails to initialise if MKL has been preloaded by numpy
# before onnxruntime arrives. Preload here so backtest tests that import
# strategies.predictive_mcdm (which lazy-loads onnxruntime) don't crash
# during collection or first-fixture setup.
try:
    import onnxruntime  # noqa: F401
except Exception as e:                  # pragma: no cover
    import warnings
    warnings.warn(f"onnxruntime import failed at conftest: {e}")
