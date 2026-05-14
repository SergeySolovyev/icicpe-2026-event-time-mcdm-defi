"""Stage Extra+1 PR (Compound V3 loader + utilization field) into a fractal-defi fork.

Prepares a clean working tree mirroring `Logarithm-Labs/fractal-defi`'s package
layout so the user can `git checkout -b ... && git commit && gh pr create`.

This script does NOT push, fork, or open a PR — it only copies files, applies a
one-line dataclass edit, and prints the suggested next-user commands. The user
retains full control over auth + fork choice.

Transformations applied:
    1. Copy `extras/fractal_pr_compound_loader/compound.py`
         -> `<target>/fractal/loaders/compound.py`
    2. Copy `extras/fractal_pr_compound_loader/aave_v3_subgraph.py`
         -> `<target>/fractal/loaders/aave_v3_subgraph.py`
       Both are stripped of any `sys.path.insert` hacks during the copy.
    3. Add `utilization: float = 0.0` field to the `AaveGlobalState` dataclass
       in `<target>/fractal/core/entities/protocols/aave.py`.

Usage:
    python scripts/stage_extra1_pr.py --target ../fractal-defi
    python scripts/stage_extra1_pr.py --target ../fractal-defi --dry-run
    python scripts/stage_extra1_pr.py --target ../fractal-defi --force
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


REPO_ROOT: Path = Path(__file__).resolve().parent.parent
SOURCE_DIR: Path = REPO_ROOT / "extras" / "fractal_pr_compound_loader"

PR_BODY_PATH_HINT: str = "extras/fractal_pr_compound_loader/PR_BODY.md"
SUGGESTED_BRANCH: str = "add-compound-v3-loader"

# (source_relative_to_SOURCE_DIR, target_relative_to_fractal_root)
FILE_COPIES: List[Tuple[str, str]] = [
    ("compound.py", "fractal/loaders/compound.py"),
    ("aave_v3_subgraph.py", "fractal/loaders/aave_v3_subgraph.py"),
]

AAVE_DATACLASS_PATH: str = "fractal/core/entities/protocols/aave.py"
UTILIZATION_FIELD_LINE: str = "    utilization: float = 0.0\n"


@dataclass
class StagingPlan:
    """Computed plan returned by `plan()` for dry-run reporting + execution."""

    target: Path
    copies: List[Tuple[Path, Path, bool]]  # (src, dst, would_overwrite)
    aave_patch_path: Path
    aave_patch_already_applied: bool


def verify_target_is_fractal_defi(target: Path) -> None:
    """Refuse to operate on a directory that doesn't look like a fractal-defi clone.

    Required markers:
        - `fractal/__init__.py`
        - `pyproject.toml` OR `setup.py` (v1.3.2 ships setup.py)
        - `fractal/loaders/` directory

    Raises:
        SystemExit on any missing marker, with a clear diagnostic.
    """
    if not target.exists():
        sys.exit(f"ERROR: target directory does not exist: {target}")
    if not target.is_dir():
        sys.exit(f"ERROR: target is not a directory: {target}")

    fractal_init = target / "fractal" / "__init__.py"
    loaders_dir = target / "fractal" / "loaders"
    pyproject = target / "pyproject.toml"
    setuppy = target / "setup.py"

    if not fractal_init.is_file():
        sys.exit(f"ERROR: missing fractal/__init__.py at {fractal_init}\n"
                 f"       This does not look like a fractal-defi clone.")
    if not loaders_dir.is_dir():
        sys.exit(f"ERROR: missing fractal/loaders/ at {loaders_dir}\n"
                 f"       This does not look like a fractal-defi clone.")
    if not (pyproject.is_file() or setuppy.is_file()):
        sys.exit(f"ERROR: neither pyproject.toml nor setup.py at {target}\n"
                 f"       This does not look like a Python package root.")


def strip_sys_path_hacks(text: str) -> str:
    """Remove `sys.path.insert(...)` lines and any orphaned `import sys` that
    served only as the import for that hack.

    Conservative: only drops `import sys` if it's a bare standalone import on
    its own line AND no other `sys.` reference remains after the strip.
    """
    lines = text.splitlines(keepends=True)
    kept: List[str] = []
    for line in lines:
        stripped = line.strip()
        # Drop sys.path.insert / sys.path.append / sys.path = ... lines
        if re.match(r"^sys\.path\.(insert|append)\s*\(", stripped):
            continue
        if re.match(r"^sys\.path\s*=", stripped):
            continue
        # Drop common "ROOT = Path(__file__)..." idiom that exists ONLY to
        # support a sys.path.insert. Be conservative: only drop it if the
        # next non-blank line was a sys.path line (we'd have skipped it).
        kept.append(line)

    rejoined = "".join(kept)

    # If no `sys.` reference remains, drop a bare `import sys` on its own line.
    if not re.search(r"\bsys\.", rejoined):
        rejoined = re.sub(r"(?m)^import sys\s*\n", "", rejoined)

    return rejoined


def utilization_field_already_present(aave_src: str) -> bool:
    """True iff `AaveGlobalState` already declares a `utilization:` field."""
    # Look for `utilization` somewhere inside the AaveGlobalState dataclass.
    m = re.search(
        r"@dataclass\s*\nclass\s+AaveGlobalState\s*\([^)]*\)\s*:(?P<body>(?:\n[ \t].*|\n)+?)"
        r"(?=\n@|\nclass\s|\Z)",
        aave_src,
    )
    if not m:
        return False
    return bool(re.search(r"^\s*utilization\s*:", m.group("body"), re.MULTILINE))


def insert_utilization_field(aave_src: str) -> str:
    """Append `utilization: float = 0.0` as the last field of `AaveGlobalState`.

    Idempotent: returns unchanged source if the field already exists.

    Strategy: find the AaveGlobalState class block, locate its last
    `name: type = value` field line, and insert our new field after it,
    preserving indentation.
    """
    if utilization_field_already_present(aave_src):
        return aave_src

    # Find the class block. We'll match from the @dataclass line to either
    # the next top-level class/decorator or EOF.
    class_re = re.compile(
        r"(?P<head>@dataclass\s*\nclass\s+AaveGlobalState\s*\([^)]*\)\s*:\n)"
        r"(?P<body>(?:[ \t]+.*\n|\n)+?)"
        r"(?P<tail>(?=@dataclass|\nclass\s|\Z))",
    )
    m = class_re.search(aave_src)
    if not m:
        raise RuntimeError(
            "Could not locate the AaveGlobalState dataclass block in aave.py. "
            "File structure may have changed; refusing to patch."
        )

    body = m.group("body")
    # Find the last field-assignment line (`name: type = ...`)
    field_lines = list(re.finditer(
        r"^(?P<indent>[ \t]+)(?P<name>[A-Za-z_]\w*)\s*:\s*[^=\n]+=\s*[^\n]+\n",
        body,
        re.MULTILINE,
    ))
    if not field_lines:
        raise RuntimeError(
            "Could not find any existing fields in AaveGlobalState. "
            "Refusing to patch — file structure may have changed."
        )

    last = field_lines[-1]
    indent = last.group("indent")
    insert_at = m.start("body") + last.end()
    new_field = f"{indent}utilization: float = 0.0\n"
    return aave_src[:insert_at] + new_field + aave_src[insert_at:]


def plan(target: Path) -> StagingPlan:
    """Build a `StagingPlan` describing every file mutation the script would do."""
    copies: List[Tuple[Path, Path, bool]] = []
    for src_name, dst_rel in FILE_COPIES:
        src = SOURCE_DIR / src_name
        dst = target / dst_rel
        if not src.is_file():
            sys.exit(f"ERROR: source file missing: {src}")
        would_overwrite = dst.exists()
        copies.append((src, dst, would_overwrite))

    aave_path = target / AAVE_DATACLASS_PATH
    if not aave_path.is_file():
        sys.exit(f"ERROR: missing target file: {aave_path}\n"
                 f"       Expected this in a fractal-defi clone.")
    already = utilization_field_already_present(aave_path.read_text(encoding="utf-8"))

    return StagingPlan(
        target=target,
        copies=copies,
        aave_patch_path=aave_path,
        aave_patch_already_applied=already,
    )


def render_plan(p: StagingPlan, force: bool) -> str:
    """Human-readable summary for `--dry-run` output."""
    out = []
    out.append(f"Target: {p.target}")
    out.append("")
    out.append("File copies:")
    for src, dst, exists in p.copies:
        flag = "OVERWRITE" if exists and force else ("BLOCKED (exists, use --force)" if exists else "new")
        out.append(f"  [{flag:>30}]  {src.name}")
        out.append(f"                                  -> {dst}")
        out.append(f"                                  (sys.path hacks stripped on copy)")
    out.append("")
    out.append(f"AaveGlobalState patch:")
    out.append(f"  path:    {p.aave_patch_path}")
    if p.aave_patch_already_applied:
        out.append(f"  status:  ALREADY APPLIED (no-op)")
    else:
        out.append(f"  status:  would insert one line: `{UTILIZATION_FIELD_LINE.strip()}`")
    return "\n".join(out)


def execute(p: StagingPlan, force: bool) -> None:
    """Apply the plan. Refuses to overwrite without `force=True`."""
    # First: check for blockers
    blockers = [dst for src, dst, exists in p.copies if exists and not force]
    if blockers:
        msg = "ERROR: target file(s) already exist (use --force to overwrite):\n"
        for b in blockers:
            msg += f"  {b}\n"
        sys.exit(msg.rstrip())

    # Copy loader files (with sys.path strip)
    for src, dst, _exists in p.copies:
        dst.parent.mkdir(parents=True, exist_ok=True)
        text = src.read_text(encoding="utf-8")
        stripped = strip_sys_path_hacks(text)
        dst.write_text(stripped, encoding="utf-8")
        print(f"  wrote: {dst}")

    # Patch aave.py
    if not p.aave_patch_already_applied:
        original = p.aave_patch_path.read_text(encoding="utf-8")
        patched = insert_utilization_field(original)
        p.aave_patch_path.write_text(patched, encoding="utf-8")
        print(f"  patched: {p.aave_patch_path} (+1 line: utilization field)")
    else:
        print(f"  skipped: {p.aave_patch_path} (utilization field already present)")


def print_next_steps(target: Path) -> None:
    """Print the suggested user commands to finalize and open the PR."""
    # Relative path to PR_BODY from the target (one common shape: sibling dirs)
    print()
    print("=" * 72)
    print("Staging complete. Suggested next-user steps:")
    print("=" * 72)
    print(f"  cd {target}")
    print(f"  git checkout -b {SUGGESTED_BRANCH}")
    print(f"  git add fractal/loaders/compound.py fractal/loaders/aave_v3_subgraph.py")
    print(f"  git add fractal/core/entities/protocols/aave.py")
    print(f'  git commit -m "Add Compound V3 lending loader + utilization field"')
    print(f"  git push -u origin {SUGGESTED_BRANCH}")
    print(f"  gh pr create \\")
    print(f"    --title 'Add Compound V3 lending loader + uniform utilization field' \\")
    print(f"    --body-file {REPO_ROOT / 'extras' / 'fractal_pr_compound_loader' / 'PR_BODY.md'}")
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
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    target: Path = args.target.expanduser().resolve()
    verify_target_is_fractal_defi(target)

    p = plan(target)
    print(render_plan(p, force=args.force))

    if args.dry_run:
        print()
        print("(dry-run; no files modified)")
        return 0

    print()
    execute(p, force=args.force)
    print_next_steps(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
