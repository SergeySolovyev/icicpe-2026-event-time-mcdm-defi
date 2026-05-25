"""Test F2: template clone + section swap for Vol-2 submission.

Reality-adjusted from plan-doc: Plan D only produced §V (05_empirical)
and §VI (06_cross_domain) drafts. §III (03_methodology) and §VIII
(08_conclusion) inherit from parent verbatim. §III ALSO has a sibling
03_arch_ladder.tex (from Plan D Task D9) that the destination preserves
across rebuilds.
"""
import hashlib
from pathlib import Path


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def _seed_parent_submission(parent: Path) -> None:
    """Build a tiny but realistic icicpe-2026-submission/ tree."""
    parent.mkdir(parents=True, exist_ok=True)
    (parent / "main.tex").write_text("\\documentclass{IEEEtran}\n", encoding="utf-8")
    (parent / "refs.bib").write_text(
        "@article{stub2024,author={Stub Author},title={Stub},year={2024},}\n",
        encoding="utf-8",
    )
    (parent / "icicpe.sty").write_text("\\ProvidesPackage{icicpe}\n", encoding="utf-8")
    (parent / "ICICPEtran.bst").write_text("% bst stub\n", encoding="utf-8")
    sec = parent / "sections"
    sec.mkdir()
    for stem, body in [
        ("01_introduction", "Intro \\Cref{sec:methodology-mcdm}.\n"),
        ("02_background", "Background.\n"),
        ("03_methodology", "Methodology prose \\Cref{sec:methodology-mcdm}.\n"),
        ("04_lob_recap", "LOB recap \\Cref{sec:methodology-forecaster}.\n"),
        ("05_defi_experiment", "OLD experiment (parent v1).\n"),
        ("06_cross_domain", "OLD cross-domain (parent v1).\n"),
        ("07_limitations", "Limitations.\n"),
        ("08_conclusion", "Conclusion v1.\n"),
        ("results_macros", "% old macros\n"),
    ]:
        (sec / f"{stem}.tex").write_text(body, encoding="utf-8")


def _seed_planD_drafts(planD_dir: Path) -> None:
    """Plan D wrote drafts to papers/icicpe-scopus-vol2/sections/."""
    sec = planD_dir / "sections"
    sec.mkdir(parents=True, exist_ok=True)
    (sec / "05_empirical.tex").write_text(
        "Plan D §V draft -- empirical study.\n",
        encoding="utf-8",
    )
    (sec / "06_cross_domain.tex").write_text(
        "Plan D §VI draft -- cross-domain discussion.\n",
        encoding="utf-8",
    )


def test_build_creates_full_submission_tree(tmp_path):
    from scripts.build_vol2_submission import build

    parent = tmp_path / "icicpe-2026-submission"
    planD = tmp_path / "icicpe-scopus-vol2"
    dest = tmp_path / "icicpe-scopus-vol2-submission"
    _seed_parent_submission(parent)
    _seed_planD_drafts(planD)

    report = build(parent_dir=parent, planD_dir=planD, dest_dir=dest)

    for f in [
        "main.tex", "refs.bib", "icicpe.sty", "ICICPEtran.bst",
        "sections/01_introduction.tex", "sections/02_background.tex",
        "sections/03_methodology.tex", "sections/04_lob_recap.tex",
        "sections/05_empirical.tex", "sections/06_cross_domain.tex",
        "sections/07_limitations.tex", "sections/08_conclusion.tex",
        "sections/results_macros.tex",
    ]:
        assert (dest / f).exists(), f
    assert report.dest_dir == dest


def test_inherited_sections_are_byte_identical(tmp_path):
    from scripts.build_vol2_submission import build

    parent = tmp_path / "icicpe-2026-submission"
    planD = tmp_path / "icicpe-scopus-vol2"
    dest = tmp_path / "icicpe-scopus-vol2-submission"
    _seed_parent_submission(parent)
    _seed_planD_drafts(planD)

    build(parent_dir=parent, planD_dir=planD, dest_dir=dest)

    # 02, 07, 08 are inherited verbatim (no cross-ref to rewrite there).
    assert _md5(dest / "sections/02_background.tex") == \
           _md5(parent / "sections/02_background.tex")
    assert _md5(dest / "sections/07_limitations.tex") == \
           _md5(parent / "sections/07_limitations.tex")
    assert _md5(dest / "sections/08_conclusion.tex") == \
           _md5(parent / "sections/08_conclusion.tex")


def test_swap_sections_come_from_planD(tmp_path):
    from scripts.build_vol2_submission import build

    parent = tmp_path / "icicpe-2026-submission"
    planD = tmp_path / "icicpe-scopus-vol2"
    dest = tmp_path / "icicpe-scopus-vol2-submission"
    _seed_parent_submission(parent)
    _seed_planD_drafts(planD)

    build(parent_dir=parent, planD_dir=planD, dest_dir=dest)

    assert "Plan D §V" in (dest / "sections/05_empirical.tex").read_text(encoding="utf-8")
    assert "Plan D §VI" in (dest / "sections/06_cross_domain.tex").read_text(encoding="utf-8")


def test_cross_references_are_rewritten(tmp_path):
    from scripts.build_vol2_submission import build

    parent = tmp_path / "icicpe-2026-submission"
    planD = tmp_path / "icicpe-scopus-vol2"
    dest = tmp_path / "icicpe-scopus-vol2-submission"
    _seed_parent_submission(parent)
    _seed_planD_drafts(planD)

    build(parent_dir=parent, planD_dir=planD, dest_dir=dest)

    intro = (dest / "sections/01_introduction.tex").read_text(encoding="utf-8")
    lob = (dest / "sections/04_lob_recap.tex").read_text(encoding="utf-8")
    method = (dest / "sections/03_methodology.tex").read_text(encoding="utf-8")
    # Old fine-grained labels no longer exist; rewritten to top-level label.
    assert "sec:methodology-mcdm" not in intro
    assert "sec:methodology-forecaster" not in lob
    assert "sec:methodology-mcdm" not in method
    assert "sec:methodology" in intro
    assert "sec:methodology" in lob


def test_preserved_files_survive_rebuild(tmp_path):
    """D9's 03_arch_ladder.tex must survive both rebuild and --clean."""
    from scripts.build_vol2_submission import build

    parent = tmp_path / "icicpe-2026-submission"
    planD = tmp_path / "icicpe-scopus-vol2"
    dest = tmp_path / "icicpe-scopus-vol2-submission"
    _seed_parent_submission(parent)
    _seed_planD_drafts(planD)

    # Operator places D9 figure in destination BEFORE build runs.
    arch_path = dest / "sections" / "03_arch_ladder.tex"
    arch_path.parent.mkdir(parents=True, exist_ok=True)
    arch_path.write_text("\\begin{tikzpicture}D9 ladder\\end{tikzpicture}\n",
                         encoding="utf-8")
    original_md5 = _md5(arch_path)

    # First build: must preserve.
    report = build(parent_dir=parent, planD_dir=planD, dest_dir=dest)
    assert arch_path.exists()
    assert _md5(arch_path) == original_md5
    assert arch_path in report.files_preserved

    # Second build with --clean: must STILL preserve (stashed before rmtree).
    report2 = build(parent_dir=parent, planD_dir=planD, dest_dir=dest, clean=True)
    assert arch_path.exists()
    assert _md5(arch_path) == original_md5
    assert arch_path in report2.files_preserved


def test_clean_flag_removes_pre_existing_files(tmp_path):
    from scripts.build_vol2_submission import build

    parent = tmp_path / "icicpe-2026-submission"
    planD = tmp_path / "icicpe-scopus-vol2"
    dest = tmp_path / "icicpe-scopus-vol2-submission"
    _seed_parent_submission(parent)
    _seed_planD_drafts(planD)

    dest.mkdir()
    (dest / "stale_artifact.txt").write_text("stale", encoding="utf-8")

    build(parent_dir=parent, planD_dir=planD, dest_dir=dest, clean=True)
    assert not (dest / "stale_artifact.txt").exists()
    assert (dest / "main.tex").exists()


def test_idempotent_without_clean(tmp_path):
    from scripts.build_vol2_submission import build

    parent = tmp_path / "icicpe-2026-submission"
    planD = tmp_path / "icicpe-scopus-vol2"
    dest = tmp_path / "icicpe-scopus-vol2-submission"
    _seed_parent_submission(parent)
    _seed_planD_drafts(planD)

    build(parent_dir=parent, planD_dir=planD, dest_dir=dest)
    h1 = _md5(dest / "sections/05_empirical.tex")
    build(parent_dir=parent, planD_dir=planD, dest_dir=dest)
    h2 = _md5(dest / "sections/05_empirical.tex")
    assert h1 == h2
