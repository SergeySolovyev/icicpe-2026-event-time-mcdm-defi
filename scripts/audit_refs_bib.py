"""Plan F Task 1 — refs.bib audit.

Scans every .tex file under <paper-dir>/sections/ for citation commands
(\\cite, \\citep, \\citet, \\citeauthor, \\citeyear, multi-key forms with
commas) and the contents of refs.bib for @TYPE{key, ...} entries plus the
literal value of each entry's author field. Fails (exit 1) if any cited
key is undefined in refs.bib or if any entry's author field contains the
literal string "Anonymous" (case-insensitive).

CLI:
    python -m scripts.audit_refs_bib
        [--paper-dir papers/icicpe-scopus-vol2-submission]
        [--bib refs.bib]
        [--sections sections]
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PAPER_DIR = ROOT / "papers" / "icicpe-scopus-vol2-submission"

# Captures the brace-delimited key list of any cite-family command.
# Examples matched:
#   \cite{key}             -> "key"
#   \cite{key1,key2}       -> "key1,key2"
#   \citep[chap. 3]{key}   -> "key"
#   \citet{key}            -> "key"
#   \citeauthor{key}       -> "key"
_CITE_RE = re.compile(
    r"\\cite[a-zA-Z]*(?:\[[^\]]*\])?\{([^}]+)\}"
)

# Captures every bib entry header line: @article{key, OR @book{key, etc.
_BIB_ENTRY_RE = re.compile(
    r"^\s*@([A-Za-z]+)\s*\{\s*([^,\s]+)\s*,",
    re.MULTILINE,
)

# Captures the author = {...} field of each entry (greedy across newlines
# is unsafe; we restrict to a single line, which matches the project
# convention of one field per line in refs.bib).
_AUTHOR_FIELD_RE = re.compile(
    r"^\s*author\s*=\s*\{([^}]*)\}",
    re.MULTILINE | re.IGNORECASE,
)


@dataclass(frozen=True)
class RefsAuditReport:
    bib_path: Path
    section_dir: Path
    cited_keys: frozenset[str]
    defined_keys: frozenset[str]
    anonymous_entries: tuple[str, ...]
    missing_keys: tuple[str, ...]
    unused_keys: tuple[str, ...]
    passes: bool

    def render(self) -> str:
        lines = [
            f"refs.bib:        {self.bib_path}",
            f"sections dir:    {self.section_dir}",
            f"cited keys:      {len(self.cited_keys)}",
            f"defined keys:    {len(self.defined_keys)}",
        ]
        if self.missing_keys:
            lines.append("MISSING (cited but not defined):")
            for k in self.missing_keys:
                lines.append(f"  - {k}")
        if self.anonymous_entries:
            lines.append("ANONYMOUS author leak:")
            for k in self.anonymous_entries:
                lines.append(f"  - {k}")
        if self.unused_keys:
            lines.append(f"unused (warning only): {len(self.unused_keys)} keys")
        lines.append("PASS" if self.passes else "FAIL")
        return "\n".join(lines)


def _extract_cited_keys(section_dir: Path) -> frozenset[str]:
    keys: set[str] = set()
    for tex in sorted(section_dir.glob("*.tex")):
        text = tex.read_text(encoding="utf-8", errors="replace")
        for m in _CITE_RE.finditer(text):
            # Multi-key citations are comma-separated; whitespace tolerated.
            for raw in m.group(1).split(","):
                k = raw.strip()
                if k:
                    keys.add(k)
    return frozenset(keys)


def _extract_bib_entries(
    bib_path: Path,
) -> tuple[frozenset[str], tuple[str, ...]]:
    """Return (defined_keys, anonymous_entry_keys)."""
    text = bib_path.read_text(encoding="utf-8", errors="replace")
    # Split by entry headers so each (key, body) pair can be inspected
    # for the author field. We pre-collect (key, start_offset) then slice.
    matches = list(_BIB_ENTRY_RE.finditer(text))
    defined: set[str] = set()
    anon: list[str] = []
    for i, m in enumerate(matches):
        key = m.group(2).strip()
        defined.add(key)
        start = m.end()
        stop = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:stop]
        am = _AUTHOR_FIELD_RE.search(body)
        if am and "anonymous" in am.group(1).strip().lower():
            anon.append(key)
    return frozenset(defined), tuple(sorted(anon))


def audit(*, bib_path: Path, section_dir: Path) -> RefsAuditReport:
    bib_path = Path(bib_path)
    section_dir = Path(section_dir)
    if not bib_path.exists():
        raise FileNotFoundError(f"refs.bib not found: {bib_path}")
    if not section_dir.exists():
        raise FileNotFoundError(f"sections dir not found: {section_dir}")

    cited = _extract_cited_keys(section_dir)
    defined, anon = _extract_bib_entries(bib_path)
    missing = tuple(sorted(cited - defined))
    unused = tuple(sorted(defined - cited))
    passes = (not missing) and (not anon)
    return RefsAuditReport(
        bib_path=bib_path,
        section_dir=section_dir,
        cited_keys=cited,
        defined_keys=defined,
        anonymous_entries=anon,
        missing_keys=missing,
        unused_keys=unused,
        passes=passes,
    )


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--paper-dir",
        default=str(DEFAULT_PAPER_DIR),
        help="Paper root directory (contains refs.bib + sections/).",
    )
    ap.add_argument("--bib", default="refs.bib", help="bib path relative to --paper-dir")
    ap.add_argument("--sections", default="sections",
                    help="sections dir relative to --paper-dir")
    args = ap.parse_args(argv)

    paper_dir = Path(args.paper_dir)
    report = audit(
        bib_path=paper_dir / args.bib,
        section_dir=paper_dir / args.sections,
    )
    print(report.render())
    return 0 if report.passes else 1


if __name__ == "__main__":
    sys.exit(_main())
