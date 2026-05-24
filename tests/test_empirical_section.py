"""Test D5: structural check on papers/icicpe-scopus-vol2/sections/05_empirical.tex."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SECTION_PATH = ROOT / "papers" / "icicpe-scopus-vol2" / "sections" / "05_empirical.tex"


def test_empirical_section_file_exists():
    assert SECTION_PATH.exists(), f"missing: {SECTION_PATH}"


def test_empirical_section_has_required_subsections():
    text = SECTION_PATH.read_text(encoding="utf-8")
    required = [
        "\\section{Empirical Study}",
        "\\subsection{Data and splits}",
        "\\subsection{Headline results matrix}",
        "\\subsection{Regime-conditional breakdown}",
        "\\subsection{Ablation: signal-class contribution}",
    ]
    for needle in required:
        assert needle in text, f"missing section header: {needle!r}"


def test_empirical_section_cites_required_anchors():
    text = SECTION_PATH.read_text(encoding="utf-8")
    citations = ["lopezdeprado2018", "mackenzie2021", "kissell2014",
                 "krause2005", "ohara1995"]
    for cite in citations:
        assert (f"\\cite{{{cite}" in text
                or f"\\citep{{{cite}" in text
                or f"\\cite[" in text and cite in text), \
            f"missing citation: {cite}"


def test_empirical_section_references_h1_pre_registration():
    text = SECTION_PATH.read_text(encoding="utf-8")
    for h in ["H_{1}^{a}", "H_{1}^{b}", "H_{1}^{c}"]:
        assert h in text, f"missing H1 label: {h}"


def test_empirical_section_references_dsr_gate():
    text = SECTION_PATH.read_text(encoding="utf-8")
    assert "0.95" in text, "missing DSR threshold 0.95"
    assert "Deflated Sharpe" in text


def test_empirical_section_word_count_in_range():
    """Target ~1500 words (constraint: between 1200 and 2200)."""
    text = SECTION_PATH.read_text(encoding="utf-8")
    import re
    body = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?(\{[^}]*\})?", " ", text)
    body = body.replace("{", " ").replace("}", " ")
    words = [w for w in body.split() if any(c.isalpha() for c in w)]
    assert 1200 <= len(words) <= 2200, f"§V word count {len(words)} out of range"


def test_refs_bib_exists():
    refs = ROOT / "papers" / "icicpe-scopus-vol2" / "refs.bib"
    assert refs.exists(), "refs.bib stub must exist"
    text = refs.read_text(encoding="utf-8")
    for key in ["lopezdeprado2018", "mackenzie2021", "kissell2014",
                "krause2005", "ohara1995"]:
        assert key in text, f"refs.bib missing key {key}"
