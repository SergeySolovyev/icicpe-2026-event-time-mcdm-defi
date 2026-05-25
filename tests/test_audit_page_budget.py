"""Test F4: page-budget audit asserts pdfinfo Pages ∈ [10, 12]."""
from pathlib import Path

import pytest


def _stub_pdfinfo(n_pages: int) -> str:
    """Return a realistic pdfinfo stdout block with the given page count."""
    return (
        "Producer:        pdfTeX-1.40.25\n"
        "CreationDate:    Mon May 26 12:00:00 2026\n"
        f"Pages:           {n_pages}\n"
        "Encrypted:       no\n"
        "Page size:       612 x 792 pts (letter)\n"
        "File size:       1234567 bytes\n"
        "PDF version:     1.5\n"
    )


def test_passes_on_11_pages(tmp_path):
    from scripts.audit_page_budget import audit

    pdf = tmp_path / "main.pdf"
    pdf.write_bytes(b"%PDF-1.5\n%stub\n")
    report = audit(pdf_path=pdf, pdfinfo_text=_stub_pdfinfo(11))
    assert report.passes
    assert report.n_pages == 11
    assert report.min_allowed == 10
    assert report.max_allowed == 12


def test_passes_on_boundary_min_10(tmp_path):
    from scripts.audit_page_budget import audit

    pdf = tmp_path / "main.pdf"
    pdf.write_bytes(b"%PDF-1.5\n")
    report = audit(pdf_path=pdf, pdfinfo_text=_stub_pdfinfo(10))
    assert report.passes


def test_passes_on_boundary_max_12(tmp_path):
    from scripts.audit_page_budget import audit

    pdf = tmp_path / "main.pdf"
    pdf.write_bytes(b"%PDF-1.5\n")
    report = audit(pdf_path=pdf, pdfinfo_text=_stub_pdfinfo(12))
    assert report.passes


def test_fails_below_min(tmp_path):
    from scripts.audit_page_budget import audit

    pdf = tmp_path / "main.pdf"
    pdf.write_bytes(b"%PDF-1.5\n")
    report = audit(pdf_path=pdf, pdfinfo_text=_stub_pdfinfo(9))
    assert not report.passes


def test_fails_above_max(tmp_path):
    from scripts.audit_page_budget import audit

    pdf = tmp_path / "main.pdf"
    pdf.write_bytes(b"%PDF-1.5\n")
    report = audit(pdf_path=pdf, pdfinfo_text=_stub_pdfinfo(13))
    assert not report.passes


def test_expected_split_sums_to_11_5(tmp_path):
    from scripts.audit_page_budget import EXPECTED_SPLIT

    total = sum(p for _, p in EXPECTED_SPLIT)
    assert total == pytest.approx(11.5, abs=1e-6)
    # Each label is non-empty.
    for label, pages in EXPECTED_SPLIT:
        assert label
        assert pages > 0


def test_missing_pdf_raises(tmp_path):
    from scripts.audit_page_budget import audit

    with pytest.raises(FileNotFoundError):
        audit(pdf_path=tmp_path / "absent.pdf", pdfinfo_text="")


def test_unparseable_pdfinfo_raises(tmp_path):
    from scripts.audit_page_budget import audit

    pdf = tmp_path / "main.pdf"
    pdf.write_bytes(b"%PDF-1.5\n")
    with pytest.raises(ValueError, match="Pages:"):
        audit(pdf_path=pdf, pdfinfo_text="Producer: x\nFile size: 1234\n")


def test_render_includes_expected_split_label(tmp_path):
    """The report rendering must list each expected-split row so the
    operator can see which section to trim if the count overshoots."""
    from scripts.audit_page_budget import audit

    pdf = tmp_path / "main.pdf"
    pdf.write_bytes(b"%PDF-1.5\n")
    report = audit(pdf_path=pdf, pdfinfo_text=_stub_pdfinfo(11))
    rendered = report.render()
    assert "Empirical Study" in rendered
    assert "total (expected)" in rendered
