"""Plan F Task 4 -- page-budget audit.

ICICPE-2026 SCOPUS Vol-2 enforces a 10-12 page budget (IEEE 2-column
conference style). This script runs `pdfinfo main.pdf`, parses the
Pages: line, and asserts the count is in [10, 12] inclusive.

The expected per-section split is documented as a constant for
operator reference but NOT enforced at the script level (per-section
page numbers require parsing main.aux which is operator-time work).

CLI:
    python -m scripts.audit_page_budget
        [--pdf papers/icicpe-scopus-vol2-submission/main.pdf]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PDF = ROOT / "papers" / "icicpe-scopus-vol2-submission" / "main.pdf"

EXPECTED_SPLIT: tuple[tuple[str, float], ...] = (
    ("Abstract + §I Introduction",                              1.0),
    ("§II Background",                                          1.0),
    ("§III Methodology (TikZ + prose)",                         2.0),
    ("§IV LOB recap (cross-domain bridge)",                     0.5),
    ("§V Empirical Study (3 figures + h1 + regime tables)",     3.0),
    ("§VI Discussion (signal taxonomy + Flashbots/hinge)",      1.5),
    ("§VII Limitations",                                        0.5),
    ("§VIII Conclusion",                                        0.5),
    ("References + figure caption overflow",                    1.5),
)


@dataclass(frozen=True)
class PageBudgetReport:
    pdf_path: Path
    n_pages: int
    min_allowed: int = 10
    max_allowed: int = 12
    expected_split: tuple[tuple[str, float], ...] = field(
        default=EXPECTED_SPLIT
    )
    passes: bool = False

    def render(self) -> str:
        lines = [
            f"pdf:              {self.pdf_path}",
            f"page count:       {self.n_pages}",
            f"allowed range:    [{self.min_allowed}, {self.max_allowed}]",
            f"verdict:          {'PASS' if self.passes else 'FAIL'}",
            "expected split:",
        ]
        total = 0.0
        for label, pages in self.expected_split:
            lines.append(f"  {pages:>4.1f}  {label}")
            total += pages
        lines.append("  ----")
        lines.append(f"  {total:>4.1f}  total (expected)")
        return "\n".join(lines)


def _parse_pages_from_pdfinfo(text: str) -> int:
    m = re.search(r"^\s*Pages\s*:\s*(\d+)\s*$", text, re.MULTILINE)
    if not m:
        raise ValueError(
            "could not find 'Pages: N' line in pdfinfo output; "
            f"got:\n{text!r}"
        )
    return int(m.group(1))


def audit(
    *,
    pdf_path: Path,
    min_allowed: int = 10,
    max_allowed: int = 12,
    pdfinfo_text: str | None = None,
) -> PageBudgetReport:
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if pdfinfo_text is None:
        try:
            out = subprocess.run(
                ["pdfinfo", str(pdf_path)],
                capture_output=True,
                text=True,
                check=True,
            )
            pdfinfo_text = out.stdout
        except FileNotFoundError as exc:
            raise RuntimeError(
                "pdfinfo not found on PATH (poppler-utils). Install it "
                "or pass --skip if you only want the expected-split table."
            ) from exc
    n_pages = _parse_pages_from_pdfinfo(pdfinfo_text)
    passes = min_allowed <= n_pages <= max_allowed
    return PageBudgetReport(
        pdf_path=pdf_path,
        n_pages=n_pages,
        min_allowed=min_allowed,
        max_allowed=max_allowed,
        passes=passes,
    )


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", default=str(DEFAULT_PDF))
    args = ap.parse_args(argv)

    report = audit(pdf_path=Path(args.pdf))
    print(report.render())
    return 0 if report.passes else 1


if __name__ == "__main__":
    sys.exit(_main())
