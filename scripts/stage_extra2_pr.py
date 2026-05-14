"""Stage Extra+2 PR (BaseLendingAllocationStrategy abstraction) into a fractal-defi fork.

Prepares a clean working tree mirroring `Logarithm-Labs/fractal-defi`'s package
layout so the user can `git checkout -b ... && git commit && gh pr create`.

This script does NOT push, fork, or open a PR — it only copies files and prints
the suggested next-user commands. The user retains full control over auth +
fork choice.

Transformations applied:
    1. Copy `extras/fractal_pr_lending_allocation/base_lending_allocation.py`
         -> `<target>/fractal/strategies/base_lending_allocation.py`
    2. (Optional, `--include-mcdm-ema`) Copy `strategies/baseline_mcdm_ema.py`
         -> `<target>/fractal/strategies/mcdm_ema.py` as a concrete subclass
       illustration. The local file has a `sys.path.insert(...)` shim that
       points at `extras/`; this shim is stripped on copy and the import is
       rewritten to the upstream module path.

Usage:
    python scripts/stage_extra2_pr.py --target ../fractal-defi
    python scripts/stage_extra2_pr.py --target ../fractal-defi --dry-run
    python scripts/stage_extra2_pr.py --target ../fractal-defi --include-mcdm-ema
    python scripts/stage_extra2_pr.py --target ../fractal-defi --force
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


REPO_ROOT: Path = Path(__file__).resolve().parent.parent
SOURCE_DIR: Path = REPO_ROOT / "extras" / "fractal_pr_lending_allocation"
LOCAL_STRATEGIES_DIR: Path = REPO_ROOT / "strategies"

PR_BODY_PATH_HINT: str = "extras/fractal_pr_lending_allocation/PR_BODY.md"
SUGGESTED_BRANCH: str = "add-base-lending-allocation-strategy"

# Always-staged file copies (regardless of flags).
# (absolute_source, target_relative_to_fractal_root)
CORE_COPIES: List[Tuple[Path, str]] = [
    (SOURCE_DIR / "base_lending_allocation.py",
     "fractal/strategies/base_lending_allocation.py"),
]

# Optional copy via --include-mcdm-ema. The project's reactive-MCDM baseline
# becomes a community-flavored concrete subclass example under
# `fractal/strategies/mcdm_ema.py` in the upstream tree.
OPTIONAL_MCDM_EMA: Tuple[Path, str] = (
    LOCAL_STRATEGIES_DIR / "baseline_mcdm_ema.py",
    "fractal/strategies/mcdm_ema.py",
)


@dataclass
class StagingPlan:
    """Computed plan returned by `plan()` for dry-run reporting + execution."""

    target: Path
    copies: List[Tuple[Path, Path, bool, bool]]
    # tuple = (src, dst, would_overwrite, needs_import_rewrite)


def verify_target_is_fractal_defi(target: Path) -> None:
    """Refuse to operate on a directory that doesn't look like a fractal-defi clone.

    Required markers:
        - `fractal/__init__.py`
        - `pyproject.toml` OR `setup.py` (v1.3.2 ships setup.py)
        - `fractal/loaders/` directory (sibling of strategies; canary)

    Raises:
        SystemExit on any missing marker, with a clear diagnostic.
    """
    if not target.exists():
        sys.exit(f"ERROR: target directory does not exist: {target}")
    if not target.is_dir():
        sys.exit(f"ERROR: target is not a directory: {target}")

    fractal_init = target / "fractal" / "__init__.py"
    loaders_dir = target / "fractal" / "loaders"
    strategies_dir = target / "fractal" / "strategies"
    pyproject = target / "pyproject.toml"
    setuppy = target / "setup.py"

    if not fractal_init.is_file():
        sys.exit(f"ERROR: missing fractal/__init__.py at {fractal_init}\n"
                 f"       This does not look like a fractal-defi clone.")
    if not loaders_dir.is_dir():
        sys.exit(f"ERROR: missing fractal/loaders/ at {loaders_dir}\n"
                 f"       This does not look like a fractal-defi clone.")
    if not strategies_dir.is_dir():
        sys.exit(f"ERROR: missing fractal/strategies/ at {strategies_dir}\n"
                 f"       This does not look like a fractal-defi clone.")
    if not (pyproject.is_file() or setuppy.is_file()):
        sys.exit(f"ERROR: neither pyproject.toml nor setup.py at {target}\n"
                 f"       This does not look like a Python package root.")


def strip_sys_path_hacks(text: str) -> str:
    """Remove `sys.path.insert(...)` lines and any orphaned `import sys` / ROOT idiom
    that served only to support the path hack.

    Conservative: only drops `import sys` if no other `sys.` reference remains,
    and only drops a `ROOT = Path(__file__)...` line if no other `ROOT` reference
    remains after the strip.
    """
    lines = text.splitlines(keepends=True)
    kept: List[str] = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^sys\.path\.(insert|append)\s*\(", stripped):
            continue
        if re.match(r"^sys\.path\s*=", stripped):
            continue
        kept.append(line)
    rejoined = "".join(kept)

    # Drop `import sys` if no `sys.` reference remains
    if not re.search(r"\bsys\.", rejoined):
        rejoined = re.sub(r"(?m)^import sys\s*\n", "", rejoined)

    # Drop the `ROOT = Path(__file__)...` idiom if no other ROOT reference remains
    # (after path hacks are gone). Only drops single-line assignments to ROOT.
    test_after_root = re.sub(r"(?m)^ROOT\s*=\s*Path\(__file__\)[^\n]*\n", "", rejoined)
    # If after removing ROOT-assignment lines there are no other `ROOT` refs,
    # then the assignment lines really were orphaned — keep the strip.
    if not re.search(r"\bROOT\b", test_after_root):
        rejoined = test_after_root
        # Also drop a now-orphaned `from pathlib import Path` if nothing else uses Path.
        if not re.search(r"\bPath\b", rejoined):
            rejoined = re.sub(r"(?m)^from pathlib import Path\s*\n", "", rejoined)

    return rejoined


def rewrite_extras_imports(text: str) -> str:
    """Rewrite imports that point at the local `extras/` shim into the proper
    upstream module path (`fractal.strategies.base_lending_allocation`).

    The local `strategies/baseline_mcdm_ema.py` uses
        from base_lending_allocation import (
            BaseLendingAllocationParams, BaseLendingAllocationStrategy,
        )
    after a `sys.path.insert` shim. With the shim stripped (above), we
    additionally rewrite the bare `base_lending_allocation` module ref to
    the upstream qualified name.
    """
    # Match `from base_lending_allocation import (...)` and rewrite.
    text = re.sub(
        r"(?m)^from\s+base_lending_allocation\s+import\b",
        "from fractal.strategies.base_lending_allocation import",
        text,
    )
    # Match `import base_lending_allocation` (any aliasing) and rewrite.
    text = re.sub(
        r"(?m)^import\s+base_lending_allocation\b",
        "import fractal.strategies.base_lending_allocation as base_lending_allocation",
        text,
    )
    return text


def plan(target: Path, include_mcdm_ema: bool) -> StagingPlan:
    """Build a `StagingPlan` describing every file mutation the script would do."""
    copies: List[Tuple[Path, Path, bool, bool]] = []

    for src, dst_rel in CORE_COPIES:
        if not src.is_file():
            sys.exit(f"ERROR: source file missing: {src}")
        dst = target / dst_rel
        copies.append((src, dst, dst.exists(), False))

    if include_mcdm_ema:
        src, dst_rel = OPTIONAL_MCDM_EMA
        if not src.is_file():
            sys.exit(f"ERROR: source file missing (for --include-mcdm-ema): {src}")
        dst = target / dst_rel
        copies.append((src, dst, dst.exists(), True))

    return StagingPlan(target=target, copies=copies)


def render_plan(p: StagingPlan, force: bool) -> str:
    """Human-readable summary for `--dry-run` output."""
    out = []
    out.append(f"Target: {p.target}")
    out.append("")
    out.append("File copies:")
    for src, dst, exists, needs_rewrite in p.copies:
        flag = "OVERWRITE" if exists and force else ("BLOCKED (exists, use --force)" if exists else "new")
        out.append(f"  [{flag:>30}]  {src.name}")
        out.append(f"                                  -> {dst}")
        notes = ["sys.path hacks stripped on copy"]
        if needs_rewrite:
            notes.append("extras/ imports rewritten to fractal.strategies.*")
        out.append(f"                                  ({'; '.join(notes)})")
    return "\n".join(out)


def execute(p: StagingPlan, force: bool) -> None:
    """Apply the plan. Refuses to overwrite without `force=True`."""
    blockers = [dst for src, dst, exists, _r in p.copies if exists and not force]
    if blockers:
        msg = "ERROR: target file(s) already exist (use --force to overwrite):\n"
        for b in blockers:
            msg += f"  {b}\n"
        sys.exit(msg.rstrip())

    for src, dst, _exists, needs_rewrite in p.copies:
        dst.parent.mkdir(parents=True, exist_ok=True)
        text = src.read_text(encoding="utf-8")
        text = strip_sys_path_hacks(text)
        if needs_rewrite:
            text = rewrite_extras_imports(text)
        dst.write_text(text, encoding="utf-8")
        print(f"  wrote: {dst}")


def print_next_steps(target: Path, include_mcdm_ema: bool) -> None:
    """Print the suggested user commands to finalize and open the PR."""
    add_paths = ["fractal/strategies/base_lending_allocation.py"]
    if include_mcdm_ema:
        add_paths.append("fractal/strategies/mcdm_ema.py")
    add_line = "git add " + " ".join(add_paths)

    print()
    print("=" * 72)
    print("Staging complete. Suggested next-user steps:")
    print("=" * 72)
    print(f"  cd {target}")
    print(f"  git checkout -b {SUGGESTED_BRANCH}")
    print(f"  {add_line}")
    print(f'  git commit -m "Add BaseLendingAllocationStrategy abstraction"')
    print(f"  git push -u origin {SUGGESTED_BRANCH}")
    print(f"  gh pr create \\")
    print(f"    --title 'Add BaseLendingAllocationStrategy for multi-lending-protocol allocators' \\")
    print(f"    --body-file {REPO_ROOT / 'extras' / 'fractal_pr_lending_allocation' / 'PR_BODY.md'}")
    print()


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else None,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--target",
        type=Path,
        default=Path("../fractal-defi"),
        help="Path to your fork of Logarithm-Labs/fractal-defi (default: ../fractal-defi).",
    )
    p.add_argument("--dry-run", action="store_true",
                   help="Compute and print the plan; do not mutate any files.")
    p.add_argument("--force", action="store_true",
                   help="Overwrite existing files in target without erroring.")
    p.add_argument(
        "--include-mcdm-ema",
        action="store_true",
        help=("Also stage the reactive MCDM-EMA baseline (this project's "
              "strategies/baseline_mcdm_ema.py) as fractal/strategies/mcdm_ema.py "
              "in the target, as a community-flavored concrete subclass example."),
    )
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    target: Path = args.target.expanduser().resolve()
    verify_target_is_fractal_defi(target)

    p = plan(target, include_mcdm_ema=args.include_mcdm_ema)
    print(render_plan(p, force=args.force))

    if args.dry_run:
        print()
        print("(dry-run; no files modified)")
        return 0

    print()
    execute(p, force=args.force)
    print_next_steps(target, include_mcdm_ema=args.include_mcdm_ema)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
