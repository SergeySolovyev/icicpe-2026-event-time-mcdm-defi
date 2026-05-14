"""Package a self-contained artifact zip for the Colab GPU training run.

The companion notebook is ``notebooks/colab/train_da_bigru_cnn_colab.ipynb``.
End-to-end flow:

    1.  Run this script locally::

            python -m scripts.prepare_colab_artifacts

        It produces ``predictive-mcdm-defi-artifacts.zip`` in the repo root.

    2.  Upload that single zip to Google Drive at::

            MyDrive/predictive-mcdm-defi/predictive-mcdm-defi-artifacts.zip

    3.  Open the notebook in Colab, set Runtime -> GPU, and Run All.

The zip contains the *minimum* surface needed for training on Colab without
cloning the full repo:

    data/cached/joined_clean.parquet   - cleaned hourly Aave+Compound panel
    data/cached/kink_params.json       - per-protocol kink coefficients
    data/__init__.py
    data/features.py                   - extract_features (Branch A residuals)
    forecaster/__init__.py
    forecaster/model.py                - DABiGRUCNNForecaster + ForecasterConfig
    forecaster/losses.py               - CompositeForecastLoss
    forecaster/train.py                - Trainer + DABiGRUCNNDataset
    forecaster/export_onnx.py          - ONNX export + parity check

We deliberately do NOT bundle ``fractal-defi``; the notebook installs that
from the pinned git tag (PROJECT_2_PLAN.md errata 1: v1.3.2).
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path
from typing import Iterable

# Repo root resolves to the parent of the ``scripts/`` directory.
ROOT = Path(__file__).resolve().parent.parent

# The set of files (relative to repo root) we want inside the zip. Listed
# explicitly rather than glob'd so that adding new files to the repo does
# not silently inflate the Colab bundle.
REQUIRED_FILES: tuple[str, ...] = (
    "data/cached/joined_clean.parquet",
    "data/cached/kink_params.json",
    "data/__init__.py",
    "data/features.py",
    "forecaster/__init__.py",
    "forecaster/model.py",
    "forecaster/losses.py",
    "forecaster/train.py",
    "forecaster/export_onnx.py",
)

# Files that are nice-to-have but not fatal if missing (the script warns).
OPTIONAL_FILES: tuple[str, ...] = (
    "PROJECT_2_PLAN.md",   # so the notebook can find the repo root by sniffing for it
    "CLAUDE.md",
)

DEFAULT_OUT = ROOT / "predictive-mcdm-defi-artifacts.zip"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_inputs(root: Path, required: Iterable[str]) -> list[Path]:
    """Resolve required paths and raise if any are missing.

    Returns the list of existing absolute paths (in input order).
    """
    missing: list[str] = []
    resolved: list[Path] = []
    for rel in required:
        p = root / rel
        if not p.exists():
            missing.append(rel)
        else:
            resolved.append(p)
    if missing:
        raise FileNotFoundError(
            "Missing required artifacts (run `make data` and `make train` first?):\n  "
            + "\n  ".join(missing)
        )
    return resolved


# ---------------------------------------------------------------------------
# Zip
# ---------------------------------------------------------------------------

def build_zip(
    root: Path,
    out_path: Path,
    required: Iterable[str] = REQUIRED_FILES,
    optional: Iterable[str] = OPTIONAL_FILES,
    *,
    dry_run: bool = False,
) -> tuple[Path, list[str], int]:
    """Build the artifact zip and return (path, members, size_bytes).

    ``dry_run=True`` lists the would-be members without writing the file
    (size_bytes returns the sum of source file sizes as a rough estimate).
    """
    required_paths = validate_inputs(root, required)
    optional_paths: list[Path] = []
    for rel in optional:
        p = root / rel
        if p.exists():
            optional_paths.append(p)
        else:
            print(f"[warn] optional file missing, skipping: {rel}")

    all_paths = required_paths + optional_paths
    members = [str(p.relative_to(root)).replace("\\", "/") for p in all_paths]

    if dry_run:
        raw_size = sum(p.stat().st_size for p in all_paths)
        return out_path, members, raw_size

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # ZIP_DEFLATED keeps the zip small; parquet is already compressed so the
    # win is modest there but real on the .py / .md text files.
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for abs_path, arcname in zip(all_paths, members):
            zf.write(abs_path, arcname=arcname)

    size = out_path.stat().st_size
    return out_path, members, size


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _format_size(n_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n_bytes < 1024:
            return f"{n_bytes:.1f} {unit}"
        n_bytes /= 1024
    return f"{n_bytes:.1f} TB"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: build (or dry-run) the artifact bundle."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"output zip path (default: {DEFAULT_OUT})",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="list files that would be bundled, then exit without zipping",
    )
    args = ap.parse_args(argv)

    try:
        out_path, members, size = build_zip(
            ROOT, args.out, dry_run=args.dry_run,
        )
    except FileNotFoundError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"[dry-run] would bundle {len(members)} files "
              f"(raw size ~{_format_size(size)}) into {out_path}")
    else:
        print(f"[ok] wrote {out_path}  ({_format_size(size)}, {len(members)} files)")

    print("\nBundle contents:")
    for m in members:
        abs_p = ROOT / m
        if abs_p.exists():
            print(f"  {_format_size(abs_p.stat().st_size):>10}  {m}")
        else:
            print(f"  {'-':>10}  {m}")

    if not args.dry_run:
        print("\nNext steps:")
        print(f"  1. Upload {out_path.name} to Google Drive at:")
        print(f"       MyDrive/predictive-mcdm-defi/{out_path.name}")
        print( "  2. Open notebooks/colab/train_da_bigru_cnn_colab.ipynb in Colab")
        print( "  3. Runtime -> Change runtime type -> GPU (A100/H100 preferred)")
        print( "  4. Run All. Expected wall-clock 30-45 min on H100.")
        print( "  5. After training, copy dual_branch_kink.onnx and the .pt")
        print( "     checkpoint from MyDrive/predictive-mcdm-defi/trained_models/")
        print( "     back to your local forecaster/trained_models/.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
