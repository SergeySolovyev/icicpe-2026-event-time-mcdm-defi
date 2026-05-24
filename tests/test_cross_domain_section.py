"""Test D6: structural check on §VI Cross-domain / signal taxonomy."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECTION_PATH = ROOT / "papers" / "icicpe-scopus-vol2" / "sections" / "06_cross_domain.tex"


def test_cross_domain_section_file_exists():
    assert SECTION_PATH.exists(), f"missing: {SECTION_PATH}"


def test_cross_domain_section_has_required_subsections():
    text = SECTION_PATH.read_text(encoding="utf-8")
    required = [
        "\\section{Discussion: Cross-Domain Transfer",
        "\\subsection{Signal-class taxonomy",
        "\\subsection{The hinge:",
        "\\subsection{Limitations:",
    ]
    for needle in required:
        assert needle in text, f"missing subsection: {needle!r}"


def test_cross_domain_references_mackenzie_anchors():
    text = SECTION_PATH.read_text(encoding="utf-8")
    # The four MacKenzie anchor positions:
    anchors = [
        "Table 3.2",
        "hinge",
        "asymmetric speed bump",
        "X^{T} X",  # the XTX = X^T X point (p.176)
    ]
    for a in anchors:
        assert a in text, f"missing MacKenzie anchor: {a!r}"


def test_cross_domain_references_F_taxonomy():
    text = SECTION_PATH.read_text(encoding="utf-8")
    for label in ["F1", "F2", "F3", "F4"]:
        assert label in text, f"missing signal-class label {label}"


def test_cross_domain_word_count_in_range():
    text = SECTION_PATH.read_text(encoding="utf-8")
    import re
    body = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?(\{[^}]*\})?", " ", text)
    body = body.replace("{", " ").replace("}", " ")
    words = [w for w in body.split() if any(c.isalpha() for c in w)]
    assert 1000 <= len(words) <= 1800, f"§VI word count {len(words)} out of range"
