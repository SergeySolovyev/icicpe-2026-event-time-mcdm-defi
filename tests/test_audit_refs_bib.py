"""Test F1: refs.bib audit catches missing keys and Anonymous authors."""
from pathlib import Path

import pytest


def _write_bib(p: Path, entries: list[tuple[str, str, str]]) -> None:
    """entries = [(bibtype, key, author_field_value), ...]"""
    lines = []
    for bibtype, key, author in entries:
        lines.append("@" + bibtype + "{" + key + ",")
        lines.append("  author = {" + author + "},")
        lines.append("  title = {Synthetic " + key + "},")
        lines.append("  year = {2024},")
        lines.append("}")
    p.write_text("\n".join(lines), encoding="utf-8")


def _write_tex(p: Path, cite_keys: list[str]) -> None:
    body = ["\\section{Stub}"]
    for k in cite_keys:
        body.append("See \\cite{" + k + "} for details.")
    p.write_text("\n".join(body), encoding="utf-8")


def test_passes_when_all_keys_resolve_and_no_anonymous(tmp_path):
    from scripts.audit_refs_bib import audit

    section_dir = tmp_path / "sections"
    section_dir.mkdir()
    bib = tmp_path / "refs.bib"
    _write_bib(bib, [
        ("article", "lopez2018afml", "Marcos Lopez de Prado"),
        ("book", "mackenzie2021trading", "Donald MacKenzie"),
    ])
    _write_tex(section_dir / "01_intro.tex", ["lopez2018afml"])
    _write_tex(section_dir / "05_empirical.tex", ["mackenzie2021trading"])

    report = audit(bib_path=bib, section_dir=section_dir)
    assert report.passes
    assert report.missing_keys == ()
    assert report.anonymous_entries == ()
    assert "lopez2018afml" in report.cited_keys
    assert "lopez2018afml" in report.defined_keys


def test_fails_when_cite_key_is_missing_from_bib(tmp_path):
    from scripts.audit_refs_bib import audit

    section_dir = tmp_path / "sections"
    section_dir.mkdir()
    bib = tmp_path / "refs.bib"
    _write_bib(bib, [("article", "lopez2018afml", "Marcos Lopez de Prado")])
    _write_tex(section_dir / "05_empirical.tex",
               ["lopez2018afml", "kissell2014mtca"])  # second is missing

    report = audit(bib_path=bib, section_dir=section_dir)
    assert not report.passes
    assert "kissell2014mtca" in report.missing_keys


def test_fails_when_bib_entry_author_is_anonymous(tmp_path):
    from scripts.audit_refs_bib import audit

    section_dir = tmp_path / "sections"
    section_dir.mkdir()
    bib = tmp_path / "refs.bib"
    _write_bib(bib, [
        ("article", "lopez2018afml", "Marcos Lopez de Prado"),
        ("article", "sol2026defi", "Anonymous"),
    ])
    _write_tex(section_dir / "05_empirical.tex",
               ["lopez2018afml", "sol2026defi"])

    report = audit(bib_path=bib, section_dir=section_dir)
    assert not report.passes
    assert "sol2026defi" in report.anonymous_entries


def test_supports_citet_citep_and_multikey_cite(tmp_path):
    from scripts.audit_refs_bib import audit

    section_dir = tmp_path / "sections"
    section_dir.mkdir()
    bib = tmp_path / "refs.bib"
    _write_bib(bib, [
        ("article", "a", "Author A"),
        ("article", "b", "Author B"),
        ("article", "c", "Author C"),
    ])
    (section_dir / "x.tex").write_text(
        "Sentence \\citet{a,b} and \\citep{c}.\n",
        encoding="utf-8",
    )
    report = audit(bib_path=bib, section_dir=section_dir)
    assert {"a", "b", "c"} <= report.cited_keys
    assert report.passes


def test_unused_keys_are_warning_only(tmp_path):
    """Defined-but-not-cited keys do NOT block submission."""
    from scripts.audit_refs_bib import audit

    section_dir = tmp_path / "sections"
    section_dir.mkdir()
    bib = tmp_path / "refs.bib"
    _write_bib(bib, [
        ("article", "used", "Author X"),
        ("article", "unused", "Author Y"),
    ])
    _write_tex(section_dir / "x.tex", ["used"])
    report = audit(bib_path=bib, section_dir=section_dir)
    assert report.passes
    assert "unused" in report.unused_keys
    assert "unused" not in report.missing_keys


def test_render_includes_pass_or_fail_marker(tmp_path):
    from scripts.audit_refs_bib import audit

    section_dir = tmp_path / "sections"
    section_dir.mkdir()
    bib = tmp_path / "refs.bib"
    _write_bib(bib, [("article", "a", "Real Author")])
    _write_tex(section_dir / "x.tex", ["a"])
    rep = audit(bib_path=bib, section_dir=section_dir)
    assert "PASS" in rep.render()


def test_audit_raises_when_paths_missing(tmp_path):
    from scripts.audit_refs_bib import audit

    section_dir = tmp_path / "sections"
    section_dir.mkdir()
    with pytest.raises(FileNotFoundError, match="refs.bib"):
        audit(bib_path=tmp_path / "nope.bib", section_dir=section_dir)
    bib = tmp_path / "refs.bib"
    bib.write_text("", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="sections dir"):
        audit(bib_path=bib, section_dir=tmp_path / "no_sections")
