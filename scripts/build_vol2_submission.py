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

# Rewrites applied to main.tex after copy. V1's \input{sections/05_defi_experiment}
# refers to a file V2 swapped out via _SWAP; we point it at the new name so the
# blind-review main.tex stays immutable upstream while V2's version compiles.
_MAIN_TEX_REWRITES: tuple[tuple[str, str], ...] = (
    (r"sections/05_defi_experiment", "sections/05_empirical"),
    # Vol-2 drops the §IV LOB recap entirely (it was a bridge from the
    # hourly DA-BiGRU-CNN story which V2 no longer claims as motivation).
    (r"\\input\{sections/04_lob_recap\.tex\}\s*\n", ""),
    # V2 replaces V1's "Domain-Aware Dual-Branch Recurrent Networks…"
    # title with the V2 event-time MCDM allocator focus.
    (
        r"\\title\[english\]\{Domain-Aware Dual-Branch Recurrent Networks Across TradFi and DeFi:\s*\n?\s*LOB Mid-Price and On-Chain Lending Rate Forecasting\}",
        (
            "\\title[english]{Event-Time MCDM Allocation across DeFi "
            "Lending Protocols:\\\\\n"
            "       An HFT-Inspired Methodology with Walk-Forward "
            "Validation}"
        ),
    ),
    # V2 replaces the V1 LOB-forecasting abstract with the V2 DeFi-
    # allocator abstract. Match starts at \begin{abstract} and ends at
    # \end{abstract} (DOTALL via the (?s) inline flag).
    (
        r"(?s)\\begin\{abstract\}.*?\\end\{abstract\}",
        (
            "\\begin{abstract}\n"
            "We design an event-time, gas-aware multi-protocol allocator "
            "for USDC supply markets across the six largest Ethereum-L1 "
            "lending protocols (Aave V3, Compound V3, Spark, Morpho Blue, "
            "Euler V2, Fluid; $\\sim$67\\% of $\\sim$\\$54B TVL). A "
            "three-tier policy ladder is evaluated on every block: T1 "
            "gas-aware threshold, T2 OU optimal stopping with closed-form "
            "Bellman boundary, T3 Cox proportional-hazards on MacKenzie "
            "(2021) Table 3.2 F1/F3/F4 signal-class features trained with "
            "L\\'opez de Prado AFML methodology (triple-barrier labels, "
            "purged $k$-fold CV with embargo, sample-uniqueness weighting). "
            "Over six non-overlapping three-month walk-forward windows "
            "(Nov 2024 -- Apr 2026), T3 beats passive holds of all six "
            "protocols on the 6-way active panel: $+2.88$\\,pp vs Aave, "
            "$+2.70$\\,pp vs Compound, $+1.85$\\,pp vs Spark, $+2.65$\\,pp "
            "vs Morpho, $+2.70$\\,pp vs Fluid, $+1.53$\\,pp vs Euler "
            "(paired-bootstrap $p<0.05$ on all six; $5$--$6$ of $6$ "
            "windows positive). The Cox model adds $+7.03$\\,bp over T1 "
            "($p=0.015$), closing pre-registered H1c. The Maker DSR "
            "one-hour delta and USDC peg deviation are the strongest non-"
            "fragmentation predictors. A production-grade Python agent "
            "(Flashbots private mempool, Prometheus observability) shares "
            "decision modules bit-identically with the backtest.\n"
            "\\end{abstract}"
        ),
    ),
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

    # Top-level files - verbatim copy from parent, EXCEPT refs.bib which
    # the Plan D dir owns once deanonymized (V1 parent bib stays as the
    # blind-review artifact of record; V2 ships the deanonymized one).
    # main.tex gets a regex rewrite to fix V1's stale \input{} filename.
    for name in _TOP_LEVEL_FILES:
        if name == "refs.bib":
            planD_bib = planD_dir / "refs.bib"
            src = planD_bib if planD_bib.exists() else parent_dir / name
        else:
            src = parent_dir / name
        if not src.exists():
            raise FileNotFoundError(f"parent missing required file: {src}")
        dst = dest_dir / name
        if name == "main.tex":
            text = src.read_text(encoding="utf-8")
            for old, new in _MAIN_TEX_REWRITES:
                # Use a lambda-callable to avoid regex backref expansion in
                # LaTeX-heavy replacement strings (\\s, \\b, \\c, etc.).
                _new = new  # bind in lambda default
                text = re.sub(old, lambda _m, _n=_new: _n, text)
            dst.write_text(text, encoding="utf-8")
        else:
            shutil.copyfile(src, dst)
        written.append(dst)

    # Inherited sections - verbatim from parent, except where planD
    # owns an override (same layering rule as refs.bib / results_macros).
    for name in _INHERIT_VERBATIM:
        planD_section = planD_dir / "sections" / name
        parent_section = parent_dir / "sections" / name
        src = planD_section if planD_section.exists() else parent_section
        if not src.exists():
            raise FileNotFoundError(f"parent missing inherited section: {src}")
        dst = dest_dir / "sections" / name
        shutil.copyfile(src, dst)
        written.append(dst)

    # Inherited sections with xref rewrite - layered: planD owns when
    # present, parent is fallback. xref rewrites are only applied to the
    # parent fallback path; planD-owned sections are assumed to be
    # already V2-internal (no stale labels).
    for name in _INHERIT_REWRITE:
        planD_section = planD_dir / "sections" / name
        parent_section = parent_dir / "sections" / name
        if planD_section.exists():
            shutil.copyfile(planD_section, dest_dir / "sections" / name)
            written.append(dest_dir / "sections" / name)
            continue
        if not parent_section.exists():
            raise FileNotFoundError(
                f"parent missing inherited section: {parent_section}"
            )
        text = parent_section.read_text(encoding="utf-8")
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

    # Results macros - layered (same rule as refs.bib): planD owns when
    # present, parent is fallback. Lets V2 ship fixed/regenerated macros
    # while keeping the V1 parent macros as the blind-review artifact.
    planD_macros = planD_dir / "sections" / "results_macros.tex"
    parent_macros = parent_dir / "sections" / "results_macros.tex"
    macros_src = planD_macros if planD_macros.exists() else parent_macros
    if macros_src.exists():
        macros_dst = dest_dir / "sections" / "results_macros.tex"
        shutil.copyfile(macros_src, macros_dst)
        written.append(macros_dst)

    # T3 sophisticated retrain macros (paired-bootstrap T3 vs T1).
    # Only the planD/v2 source produces this; v1 inherits a no-op via
    # \IfFileExists in main.tex.
    t3_macros_src = planD_dir / "sections" / "t3_macros.tex"
    if t3_macros_src.exists():
        t3_macros_dst = dest_dir / "sections" / "t3_macros.tex"
        shutil.copyfile(t3_macros_src, t3_macros_dst)
        written.append(t3_macros_dst)

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
