"""Export the trained DA-BiGRU-CNN forecaster to ONNX for runtime inference.

Why ONNX:
    Decouples PyTorch training from runtime so the strategy path can load via
    onnxruntime (CPU) without pulling torch into the backtest process.
    Matches the runtime constraint from Solovev 2026a (1 CPU, ~60 min total).

Default I/O contract:
    Inputs:
        x_branch_a  : (B, 168, 3)   float32
        x_branch_b  : (B, 168, 7)   float32
    Output:
        y_pred      : (B, 2, 2)     float32   [protocol][u_hat | eps_corr]

    Sequence length (168) is locked into the graph; batch dim is dynamic.

Usage::

    python -m forecaster.export_onnx
    python -m forecaster.export_onnx --ckpt forecaster/trained_models/da_bigru_cnn.pt
"""
from __future__ import annotations

# torch MUST be imported before numpy/pandas on Windows -- see forecaster/train.py.
import torch

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from forecaster.model import DABiGRUCNNForecaster, ForecasterConfig

ROOT = Path(__file__).parent.parent
DEFAULT_CKPT = ROOT / "forecaster" / "trained_models" / "da_bigru_cnn.pt"
DEFAULT_ONNX = ROOT / "forecaster" / "trained_models" / "dual_branch_kink.onnx"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class ExportConfig:
    """Knobs for the ONNX export."""
    ckpt_path: Path = DEFAULT_CKPT
    onnx_path: Path = DEFAULT_ONNX
    opset: int = 17
    atol: float = 1e-4
    rtol: float = 1e-4


# ---------------------------------------------------------------------------
# Core export
# ---------------------------------------------------------------------------

def _load_model(ckpt_path: Path) -> DABiGRUCNNForecaster:
    """Load a checkpoint produced by ``forecaster.train.Trainer.fit``.

    Restores both the ``model_cfg`` (architecture hyperparameters) and the
    ``model_state_dict`` (trained weights), then switches the model into
    inference mode (disables dropout / freezes batchnorm stats).
    """
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    model_cfg = ckpt.get("model_cfg")
    cfg = ForecasterConfig(**model_cfg) if isinstance(model_cfg, dict) else ForecasterConfig()
    model = DABiGRUCNNForecaster(cfg)
    state = ckpt.get("model_state_dict", ckpt)        # tolerate raw state_dicts too
    model.load_state_dict(state)
    model.train(False)                                # inference mode (no dropout)
    return model


def export_to_onnx(model: DABiGRUCNNForecaster, onnx_path: Path, *, opset: int = 17) -> None:
    """torch.onnx.export with batch-dynamic, sequence-fixed axes."""
    onnx_path.parent.mkdir(parents=True, exist_ok=True)
    seq = model.cfg.sequence_length
    dummy_a = torch.zeros(1, seq, model.cfg.branch_a_input_dim, dtype=torch.float32)
    dummy_b = torch.zeros(1, seq, model.cfg.branch_b_input_dim, dtype=torch.float32)

    export_kwargs = dict(
        input_names=["x_branch_a", "x_branch_b"],
        output_names=["y_pred"],
        dynamic_axes={
            "x_branch_a": {0: "batch"},
            "x_branch_b": {0: "batch"},
            "y_pred": {0: "batch"},
        },
        opset_version=opset,
        do_constant_folding=True,
    )
    # torch>=2.5 routes through the new dynamo-based exporter by default and
    # pulls in `onnxscript`; the legacy TorchScript path is still available
    # and adequate for this fixed-graph model. Try the legacy path first;
    # fall back to dynamo if the keyword is not recognised on older torch.
    try:
        torch.onnx.export(model, (dummy_a, dummy_b), str(onnx_path),
                          dynamo=False, **export_kwargs)
    except TypeError:
        torch.onnx.export(model, (dummy_a, dummy_b), str(onnx_path),
                          **export_kwargs)


def validate_onnx(model: DABiGRUCNNForecaster, onnx_path: Path, *,
                  atol: float = 1e-4, rtol: float = 1e-4, seed: int = 0) -> None:
    """Compare a single-sample inference between torch and onnxruntime."""
    import onnxruntime as ort                          # local import

    rng = np.random.default_rng(seed)
    seq = model.cfg.sequence_length
    x_a = rng.standard_normal((1, seq, model.cfg.branch_a_input_dim)).astype(np.float32)
    x_b = rng.standard_normal((1, seq, model.cfg.branch_b_input_dim)).astype(np.float32)

    with torch.no_grad():
        y_torch = model(torch.from_numpy(x_a), torch.from_numpy(x_b)).cpu().numpy()

    sess = ort.InferenceSession(
        str(onnx_path), providers=["CPUExecutionProvider"],
    )
    y_onnx = sess.run(None, {"x_branch_a": x_a, "x_branch_b": x_b})[0]

    max_abs = float(np.max(np.abs(y_torch - y_onnx)))
    if not np.allclose(y_torch, y_onnx, atol=atol, rtol=rtol):
        raise AssertionError(
            f"ONNX vs torch mismatch: max|diff|={max_abs:.3e} "
            f"(atol={atol}, rtol={rtol})"
        )
    print(f"[validate] torch <-> onnxruntime allclose OK (max|diff|={max_abs:.3e})")


def export(cfg: ExportConfig) -> Path:
    """End-to-end: load -> export -> validate -> return artifact path."""
    if not cfg.ckpt_path.exists():
        raise FileNotFoundError(
            f"Checkpoint not found: {cfg.ckpt_path}. Train first via "
            f"`python -m forecaster.train`."
        )
    print(f"[load] {cfg.ckpt_path}")
    model = _load_model(cfg.ckpt_path)
    print(f"[load] n_params={model.n_params():,}")

    print(f"[export] -> {cfg.onnx_path}  (opset={cfg.opset})")
    export_to_onnx(model, cfg.onnx_path, opset=cfg.opset)

    validate_onnx(model, cfg.onnx_path, atol=cfg.atol, rtol=cfg.rtol)
    print(f"[done] {cfg.onnx_path}")
    return cfg.onnx_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ckpt", type=Path, default=DEFAULT_CKPT,
                    help="path to .pt checkpoint")
    ap.add_argument("--onnx", type=Path, default=DEFAULT_ONNX,
                    help="output .onnx path")
    ap.add_argument("--opset", type=int, default=17)
    ap.add_argument("--atol", type=float, default=1e-4)
    args = ap.parse_args(argv)

    cfg = ExportConfig(ckpt_path=args.ckpt, onnx_path=args.onnx,
                       opset=args.opset, atol=args.atol)
    try:
        export(cfg)
    except FileNotFoundError as exc:
        print(f"[skip] {exc}")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(_main())
