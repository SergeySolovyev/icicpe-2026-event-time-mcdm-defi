"""Plan F Task 3 -- anonymization / self-promotion leak audit.

Greps every .tex and .bib file under <paper-dir>/ for six exact patterns
known to have triggered review-round flags on the 2026c submission:

  1. \\bour prior work\\b          -- first-person ego phrasing
  2. \\bwe proposed\\b              -- first-person attribution
  3. \\bfigshare\\b                  -- bare service name
  4. 10\\.6084/m9\\.figshare        -- bare figshare DOI prefix
  5. DA-BiGRU-CNN \\(ours\\)         -- explicit "(ours)" annotation
  6. Solovev \\([12][09][0-9]{2}\\) -- bare author-year reference

Every match is reported as an AnonymizationFinding with file path and
1-indexed line number. The script returns exit 1 if any findings exist.

This Vol-2 venue is single-blind (author identification carried), but
these patterns survived from the prior anonymized-version anchors and
are sloppy self-promotion in either context. Operator review of each
match is the recommended cleanup pass.

CLI:
    python -m scripts.audit_anonymization
        [--paper-dir papers/icicpe-scopus-vol2-submission]
        [--allow-bib]   # exclude refs.bib from figshare-DOI rule
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PAPER_DIR = ROOT / "papers" / "icicpe-scopus-vol2-submission"

# (regex, human-readable label). re.IGNORECASE is applied uniformly so
# "Our Prior Work" / "OUR PRIOR WORK" also match.
PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bour prior work\b",              "our prior work"),
    (r"\bwe proposed\b",                 "we proposed"),
    (r"\bfigshare\b",                    "figshare"),
    (r"10\.6084/m9\.figshare",           "10.6084/m9.figshare"),
    (r"DA-BiGRU-CNN \(ours\)",           "DA-BiGRU-CNN (ours)"),
    (r"Solovev \([12][09][0-9]{2}",      "Solovev (YYYY"),
)

# Pattern indices that may be excluded from refs.bib under --allow-bib.
_BIB_EXCLUDABLE_INDEXES = frozenset({2, 3})  # "figshare" and the DOI prefix


@dataclass(frozen=True)
class AnonymizationFinding:
    pattern: str
    file_path: Path
    line_number: int
    line_text: str


def _scan_file(
    path: Path,
    regexes: list[tuple[re.Pattern[str], str]],
) -> list[AnonymizationFinding]:
    findings: list[AnonymizationFinding] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return findings
    for i, line in enumerate(text.splitlines(), start=1):
        for rx, label in regexes:
            if rx.search(line):
                findings.append(
                    AnonymizationFinding(
                        pattern=label,
                        file_path=path,
                        line_number=i,
                        line_text=line.rstrip(),
                    )
                )
    return findings


def audit(
    *, paper_dir: Path, allow_bib: bool = False
) -> tuple[AnonymizationFinding, ...]:
    paper_dir = Path(paper_dir)
    if not paper_dir.exists():
        raise FileNotFoundError(f"paper dir missing: {paper_dir}")

    tex_regexes = [
        (re.compile(p, re.IGNORECASE), label) for p, label in PATTERNS
    ]
    if allow_bib:
        bib_regexes = [
            (re.compile(p, re.IGNORECASE), label)
            for i, (p, label) in enumerate(PATTERNS)
            if i not in _BIB_EXCLUDABLE_INDEXES
        ]
    else:
        bib_regexes = tex_regexes

    all_findings: list[AnonymizationFinding] = []
    for tex in sorted(paper_dir.rglob("*.tex")):
        all_findings.extend(_scan_file(tex, tex_regexes))
    for bib in sorted(paper_dir.rglob("*.bib")):
        all_findings.extend(_scan_file(bib, bib_regexes))

    return tuple(all_findings)


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--paper-dir", default=str(DEFAULT_PAPER_DIR))
    ap.add_argument(
        "--allow-bib",
        action="store_true",
        help="exclude refs.bib from figshare-related patterns",
    )
    args = ap.parse_args(argv)

    findings = audit(
        paper_dir=Path(args.paper_dir),
        allow_bib=args.allow_bib,
    )
    if not findings:
        print("anonymization audit: PASS (no findings)")
        return 0
    print(f"anonymization audit: FAIL ({len(findings)} finding(s))")
    for f in findings:
        print(f"  {f.file_path}:{f.line_number}: [{f.pattern}] {f.line_text}")
    return 1


if __name__ == "__main__":
    sys.exit(_main())
