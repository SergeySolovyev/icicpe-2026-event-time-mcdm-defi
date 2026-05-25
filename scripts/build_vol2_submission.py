"""Plan F Task 2 — template conversion.

Clone papers/icicpe-2026-submission/ -> papers/icicpe-scopus-vol2-submission/
and swap section files to the Plan D drafts at
papers/icicpe-scopus-vol2/sections/.

Reality-adjusted from plan-doc spec:
  * Plan D produced 05_empirical.tex + 06_cross_domain.tex only (not
    03_methodology.tex or 08_conclusion.tex). §VIII conclusion inherits
    verbatim from parent; §III methodology inherits from parent BUT the
    destination's pre-existing sections/03_arch_ladder.tex (from D9) is
    preserved untouched. Plan D's 06_cross_domain.tex is mapped to dest's
    06_cross_domain.tex (not 06_discussion.tex per plan-doc — the actual
    Plan D filename wins).
  * Inherited §I, §II, §IV, §VII receive mechanical cross-reference
    rewrites (sec:methodology-mcdm / sec:methodology-forecaster ->
    sec:methodology) — the new TikZ ladder in §III collapses the old
    fine-grained labels into a single top-level label.

CLI:
    python -m scripts.build_vol2_submission
        [--parent papers/icicpe-2026-submission]
        [--planD papers/icicpe-scopus-vol2]
        [--dest papers/icicpe-scopus-vol2-submission]
        [--clean]
"""
from __future__ import annotations

import argparse
import re
import shutil
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PARENT = ROOT / "papers" / "icicpe-2026-submission"
DEFAULT_PLAND = ROOT / "papers" / "icicpe-scopus-vol2"
DEFAULT_DEST = ROOT / "papers" / "icicpe-scopus-vol2-submission"

# Inherited top-level files copied verbatim from parent.
_TOP_LEVEL_FILES = ("main.tex", "refs.bib", "icicpe.sty", "ICICPEtran.bst")

# Inherited section files copied from parent (verbatim).
_INHERIT_VERBATIM = (
    "02_background.tex",
    "07_limitations.tex",
    "08_conclusion.tex",  # Plan D did not produce a separate VIII draft
)

# Inherited but cross-references must be rewritten before write.
_INHERIT_REWRITE = (
    "01_introduction.tex",
    "04_lob_recap.tex",
    "03_methodology.tex",  # parent prose stays; D9 arch_ladder fig sits alongside
)

# Swap to the Plan D draft. (planD_filename, dest_filename) -- destination
# filename matches the Plan D filename so existing \input{} cross-refs
# from main.tex resolve.
_SWAP = (
    ("05_empirical.tex", "05_empirical.tex"),
    ("06_cross_domain.tex", "06_cross_domain.tex"),
)

# Cross-reference rewrites applied to _INHERIT_REWRITE files. The new
# TikZ-architecture-first §III collapses the old fine-grained labels.
_XREF_REWRITES: tuple[tuple[str, str], ...] = (
    (r"sec:methodology-mcdm", "sec:methodology"),
    (r"sec:methodology-forecaster", "sec:methodology"),
)

# Files in dest that must be preserved across runs (operator-authored or
# Plan-D-direct-write outputs). The build script will refuse to overwrite
# these even when not in --clean mode.
_PRESERVE_IF_EXISTS = (
    "sections/03_arch_ladder.tex",  # D9 figure (commit f1aba8a)
)


@dataclass(frozen=True)
class BuildReport:
    parent_dir: Path
    planD_dir: Path
    dest_dir: Path
    files_written: tuple[Path, ...]
    files_preserved: tuple[Path, ...]
    xref_rewrites: tuple[str, ...]


def _rewrite_xrefs(text: str) -> str:
    for old, new in _XREF_REWRITES:
        text = re.sub(old, new, text)
    return text


def build(
    *,
    parent_dir: Path,
    planD_dir: Path,
    dest_dir: Path,
    clean: bool = False,
) -> BuildReport:
    parent_dir = Path(parent_dir)
    planD_dir = Path(planD_dir)
    dest_dir = Path(dest_dir)

    if not parent_dir.exists():
        raise FileNotFoundError(f"parent submission tree missing: {parent_dir}")
    if not planD_dir.exists():
        raise FileNotFoundError(f"Plan D draft tree missing: {planD_dir}")

    # Stash preserved files BEFORE any rmtree so --clean doesn't kill them.
    preserved_contents: dict[str, bytes] = {}
    for rel in _PRESERVE_IF_EXISTS:
        p = dest_dir / rel
        if p.exists():
            preserved_contents[rel] = p.read_bytes()

    if clean and dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / "sections").mkdir(exist_ok=True)

    written: list[Path] = []
    preserved: list[Path] = []

    # Top-level files - verbatim copy.
    for name in _TOP_LEVEL_FILES:
        src = parent_dir / name
        if not src.exists():
            raise FileNotFoundError(f"parent missing required file: {src}")
        dst = dest_dir / name
        shutil.copyfile(src, dst)
        written.append(dst)

    # Inherited sections - verbatim.
    for name in _INHERIT_VERBATIM:
        src = parent_dir / "sections" / name
        if not src.exists():
            raise FileNotFoundError(f"parent missing inherited section: {src}")
        dst = dest_dir / "sections" / name
        shutil.copyfile(src, dst)
        written.append(dst)

    # Inherited sections with xref rewrite.
    for name in _INHERIT_REWRITE:
        src = parent_dir / "sections" / name
        if not src.exists():
            raise FileNotFoundError(f"parent missing inherited section: {src}")
        text = src.read_text(encoding="utf-8")
        text = _rewrite_xrefs(text)
        dst = dest_dir / "sections" / name
        dst.write_text(text, encoding="utf-8")
        written.append(dst)

    # Swap sections from Plan D drafts.
    for planD_name, dest_name in _SWAP:
        src = planD_dir / "sections" / planD_name
        if not src.exists():
            raise FileNotFoundError(
                f"Plan D draft missing: {src} - run Plan D Task D5/D6 first"
            )
        dst = dest_dir / "sections" / dest_name
        shutil.copyfile(src, dst)
        written.append(dst)

    # Results macros - inherit from parent for now (Plan D Task D-extra
    # would regenerate from results/tables/h1_significance.csv when the
    # full panel materialises).
    macros_src = parent_dir / "sections" / "results_macros.tex"
    if macros_src.exists():
        macros_dst = dest_dir / "sections" / "results_macros.tex"
        shutil.copyfile(macros_src, macros_dst)
        written.append(macros_dst)

    # Restore preserved files (e.g. D9 arch_ladder.tex).
    for rel, content in preserved_contents.items():
        p = dest_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        preserved.append(p)

    return BuildReport(
        parent_dir=parent_dir,
        planD_dir=planD_dir,
        dest_dir=dest_dir,
        files_written=tuple(written),
        files_preserved=tuple(preserved),
        xref_rewrites=tuple(f"{o} -> {n}" for o, n in _XREF_REWRITES),
    )


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--parent", default=str(DEFAULT_PARENT))
    ap.add_argument("--planD", default=str(DEFAULT_PLAND))
    ap.add_argument("--dest", default=str(DEFAULT_DEST))
    ap.add_argument("--clean", action="store_true")
    args = ap.parse_args(argv)

    report = build(
        parent_dir=Path(args.parent),
        planD_dir=Path(args.planD),
        dest_dir=Path(args.dest),
        clean=args.clean,
    )
    print(f"wrote {len(report.files_written)} files to {report.dest_dir}")
    if report.files_preserved:
        print(f"preserved {len(report.files_preserved)} pre-existing files:")
        for p in report.files_preserved:
            print(f"  - {p.relative_to(report.dest_dir)}")
    for r in report.xref_rewrites:
        print(f"  xref rewrite: {r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
