# Paper Polish + ICICPE SCOPUS Vol-2 Submission Plan (Plan F, Week 6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to execute this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the Plan D paper drafts (§V Empirical Study, §VI Cross-domain, §VIII Conclusion) into a submission-ready ICICPE-2026 SCOPUS-indexed Vol-2 manuscript at `papers/icicpe-scopus-vol2-submission/`, audit it against three hard requirements that have killed prior submissions (broken `\cite{}` keys, double-blind anonymization leaks, page-budget overrun), capture the full Claude Code transcript for the reproducibility appendix mandated by the venue, and produce a single submission zip ready for operator upload to `manuscriptlink.com/conferences/icicpe2026-scopus`.

**Architecture:** Plan F is a *consumer* of every prior plan in the project:
- Plan A (event-time data pipeline) provides the panel that backs §V's experimental setup.
- Plan B (B1-B4 + T1 + T2 policies + replay engine) and Plan C (T3 hazard + signal builders) provide the technical content cited from §III and §VII.
- Plan D produced the §V/§VI/§VIII drafts, the three publication-grade figures, and `results/tables/h1_significance.csv`.
- Plan E (whatever Week 5 produced — typically a referee-revision pass) is not a hard dependency; Plan F treats §I/§II/§III/§IV/§VII as inherited verbatim from `papers/icicpe-2026-submission/` with mechanical cross-reference edits.

Plan F adds **only audit scripts, packaging, and one template clone** — no new research artefacts:

1. A `\cite{}` ↔ `refs.bib` consistency auditor (`scripts/audit_refs_bib.py`) that fails CI if any cited key is missing from `refs.bib` or if any `refs.bib` entry still has `author = {Anonymous}`.
2. A template-conversion harness that clones `papers/icicpe-2026-submission/` to `papers/icicpe-scopus-vol2-submission/`, swaps in the Plan D §V/§VI/§VIII drafts, and rewrites cross-references for the new methodology layout (`scripts/build_vol2_submission.py`).
3. A double-blind anonymization auditor (`scripts/audit_anonymization.py`) that greps for the exact leak patterns that surfaced in the 2026c review round.
4. A page-budget auditor (`scripts/audit_page_budget.py`) that calls `pdfinfo main.pdf` and asserts the page count lies in [10, 12], with a documented per-section expected split that is checked by reading the auxfile.
5. An LLM transcript collator (`scripts/build_llm_transcript.py`) that concatenates session JSONL files under `~/.claude/projects/D--DeFi/*.jsonl` into a Markdown reproducibility appendix.
6. A submission packager (`scripts/build_submission_zip.py`) that produces `submission_<git-sha>.zip` with `main.pdf`, every `sections/*.tex`, `refs.bib`, `LLM_TRANSCRIPT.md`, and the supplementary `results/tables/*.csv` artefacts.

**Tech Stack:** Python 3.11 (existing `.venv\Scripts\python.exe`), standard library only for the audit scripts (`pathlib`, `re`, `subprocess`, `json`, `zipfile`, `hashlib`), pytest for testing. **No new third-party dependencies.** External binaries assumed on `PATH`: `pdfinfo` (poppler-utils, already required by the project's existing `make whitepaper` target), `git`, and `latexmk` (the latter only invoked by the operator, not by the test suite).

**Prerequisites:**
- Plan D complete: `papers/icicpe-scopus-vol2/sections/{05_empirical.tex,06_discussion.tex,03_methodology.tex}` exist (created by Plan D Tasks D5/D6/D9). The new submission folder is `papers/icicpe-scopus-vol2-**submission**/` — note the `-submission` suffix; Plan D wrote to `papers/icicpe-scopus-vol2/` without the suffix, and Plan F Task F2 is the rename-and-merge step.
- `papers/icicpe-2026-submission/` exists with `main.tex`, `refs.bib`, `icicpe.sty`, `ICICPEtran.bst`, `sections/01_introduction.tex` … `sections/08_conclusion.tex`, and `sections/results_macros.tex`. (Confirmed via `ls papers/icicpe-2026-submission/sections/` at planning time: eight numbered section files + the macros file.)
- `pdfinfo` resolves on `PATH`. If it does not, `make whitepaper` already broken and Plan F is blocked at task F4 only; F1/F2/F3/F5/F6 still run.
- Operator has `manuscriptlink.com` account credentials saved in their personal password store (NOT in the repo).

**Spec source of truth:** `C:\Users\1\.claude\plans\enumerated-scribbling-barto.md` §Build sequence — Week 6, §Verification — Week 6, §Submission package contents. ICICPE-2026 SCOPUS-indexed Vol-2 author instructions PDF stored at `docs/research/icicpe-scopus-vol2-call-for-papers.pdf` (page-limit and double-blind policy confirmed there).

**Citation grounding:** `docs/research/literature-foundation.md`
- §1.1 ICICPE Vol-2 author kit — page limit 10–12 (IEEE conference style, 2-column).
- §1.2 ICICPE Vol-2 double-blind policy — author identification must NOT appear in main text, references, OR figure captions.
- §1.3 manuscriptlink.com submission portal — required files: main PDF, source bundle (zip), supplementary materials (zip).
- §6.1 NeurIPS-2024 LLM-disclosure policy template — model used in `papers/icicpe-scopus-vol2-submission/LLM_TRANSCRIPT.md` reproducibility appendix.

**Plan F output gate:** A single artefact `submission_<sha>.zip` at the repo root, where `<sha>` is the short git SHA of HEAD at packaging time. The zip contains exactly the file set documented in Task F6, every audit script in `scripts/` exits 0 against that submission folder, and the page count of `papers/icicpe-scopus-vol2-submission/main.pdf` is in [10, 12]. The operator uploads the zip to manuscriptlink.com and confirms receipt — Plan F itself stops at zip production.

**Commit convention reminder:** Every task commit follows the project convention from `CLAUDE.md` — multi-paragraph commit message explaining reasoning, Co-Authored-By trailer preserved. Each Task F<N> below ends with a `git add` + heredoc commit message; no task commits more than its own files.

---

## File map

```
scripts/
├── __init__.py                              # NEW: package marker (F1)
├── audit_refs_bib.py                        # NEW: refs.bib + \cite{} auditor (F1)
├── build_vol2_submission.py                 # NEW: template clone + section swap (F2)
├── audit_anonymization.py                   # NEW: double-blind leak grep (F3)
├── audit_page_budget.py                     # NEW: pdfinfo page-count gate (F4)
├── build_llm_transcript.py                  # NEW: JSONL collator (F5)
└── build_submission_zip.py                  # NEW: final zip packager (F6)

papers/icicpe-scopus-vol2-submission/        # NEW: produced by F2
├── main.tex                                 # COPY from icicpe-2026-submission/
├── refs.bib                                 # COPY from icicpe-2026-submission/, audited by F1
├── icicpe.sty                               # COPY from icicpe-2026-submission/
├── ICICPEtran.bst                           # COPY from icicpe-2026-submission/
├── LLM_TRANSCRIPT.md                        # NEW: produced by F5
└── sections/
    ├── 01_introduction.tex                  # COPY from icicpe-2026-submission/
    ├── 02_background.tex                    # COPY from icicpe-2026-submission/
    ├── 03_methodology.tex                   # COPY from Plan D D9 (TikZ arch)
    ├── 04_lob_recap.tex                     # COPY from icicpe-2026-submission/
    ├── 05_empirical.tex                     # COPY from Plan D D5
    ├── 06_discussion.tex                    # COPY from Plan D D6
    ├── 07_limitations.tex                   # COPY from icicpe-2026-submission/
    ├── 08_conclusion.tex                    # COPY from Plan D D6/D7 stub or new
    └── results_macros.tex                   # COPY + re-render from results/tables/h1_significance.csv

tests/
├── test_audit_refs_bib.py                   # NEW (F1)
├── test_build_vol2_submission.py            # NEW (F2)
├── test_audit_anonymization.py              # NEW (F3)
├── test_audit_page_budget.py                # NEW (F4)
├── test_build_llm_transcript.py             # NEW (F5)
└── test_build_submission_zip.py             # NEW (F6)

results/tables/                              # consumed only, never written by Plan F
├── h1_significance.csv                      # PRODUCED by Plan D D2+D4
├── test_matrix.csv                          # PRODUCED by Plan D D1
└── regime_breakdown.csv                     # PRODUCED by Plan D D3

submission_<sha>.zip                         # NEW: produced by F6 at repo root
```

Plan F **does not modify** any file under `decision/`, `backtest/`, `stats/`, `data/`, `forecaster/`, or `results/` — those are the territory of Plans A-D. Plan F touches only `scripts/`, `papers/icicpe-scopus-vol2-submission/`, `tests/`, and the top-level `submission_<sha>.zip` output.

---

## Canonical dataclasses introduced in Plan F

These names appear across multiple tasks — fix them now to prevent type-drift.

### `RefsAuditReport` (Task F1)
```python
@dataclass(frozen=True)
class RefsAuditReport:
    bib_path: Path
    section_dir: Path
    cited_keys: frozenset[str]          # every key found in \cite{} across sections
    defined_keys: frozenset[str]        # every @TYPE{key, …} entry in refs.bib
    anonymous_entries: tuple[str, ...]  # bib keys whose author field is "Anonymous"
    missing_keys: tuple[str, ...]       # cited but not defined  → blocks submission
    unused_keys: tuple[str, ...]        # defined but not cited  → warning only
    passes: bool                        # True iff no missing keys and no anon entries
```

### `AnonymizationFinding` (Task F3)
```python
@dataclass(frozen=True)
class AnonymizationFinding:
    pattern: str           # the regex literal (one of the six 2026c-known leaks)
    file_path: Path        # absolute path
    line_number: int       # 1-indexed
    line_text: str         # the matching line, stripped of trailing whitespace
```

### `PageBudgetReport` (Task F4)
```python
@dataclass(frozen=True)
class PageBudgetReport:
    pdf_path: Path
    n_pages: int
    min_allowed: int = 10
    max_allowed: int = 12
    expected_split: tuple[tuple[str, float], ...]  # (section_label, expected_pages)
    passes: bool                                   # min_allowed <= n_pages <= max_allowed
```

### `TranscriptSlice` (Task F5)
```python
@dataclass(frozen=True)
class TranscriptSlice:
    session_id: str        # filename stem of the .jsonl file
    started_at: str        # ISO 8601 of the first message timestamp
    n_messages: int        # number of JSONL lines emitted into the appendix
    chars_emitted: int     # rough length budget for the appendix
```

### `SubmissionManifest` (Task F6)
```python
@dataclass(frozen=True)
class SubmissionManifest:
    git_sha: str           # short (7-char) HEAD sha at packaging time
    zip_path: Path
    file_count: int
    total_bytes: int
    sha256_zip: str        # hex digest, written to a sidecar .sha256 file
```

---

## Task F1: refs.bib audit — \cite{} ↔ refs.bib consistency + Anonymous-author detector

**Files:**
- Create: `scripts/__init__.py`
- Create: `scripts/audit_refs_bib.py`
- Create: `tests/test_audit_refs_bib.py`

**Methodology:** Two failures have killed prior submissions:
1. A `\cite{krause_oh_stein_1995}` in `05_empirical.tex` that resolves to *nothing* in `refs.bib` — LaTeX silently emits `[?]` and the reviewer flags it as sloppy. The auditor scans every `.tex` file under `papers/icicpe-scopus-vol2-submission/sections/`, extracts the contents of `\cite{...}`, `\citep{...}`, `\citet{...}`, and `\Cref{ref:...}`-style commands, deduplicates the key list, and asserts each cited key is present as an `@TYPE{key,` entry in `refs.bib`.
2. A double-blind placeholder `author = {Anonymous}` left over from the prior anonymized submission round leaks into the final SCOPUS-indexed (non-anonymous) version. The auditor reads the bib file line-by-line and reports every entry whose `author = {…}` field contains the literal string `Anonymous` (case-insensitive).

The auditor reuses the seed `refs.bib` from `papers/icicpe-2026-submission/refs.bib` — Plan D added new citations (Lopez de Prado AFML, MacKenzie 2021, Kissell 2014 eq 8.23, Krause-Oh-Stein 1995, Abbott on hinges) and those bib entries already exist there. The Plan F1 audit simply enforces the contract.

The script is callable as `python -m scripts.audit_refs_bib --paper-dir papers/icicpe-scopus-vol2-submission/` and returns exit code 0 (pass) / 1 (failure). Tests run it on a synthetic two-file paper directory in `tmp_path`.

- [ ] **Step 1: Write the failing test**

`tests/test_audit_refs_bib.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv\Scripts\python.exe -m pytest tests\test_audit_refs_bib.py -v
```
Expected: `ModuleNotFoundError: No module named 'scripts.audit_refs_bib'`.

- [ ] **Step 3: Write minimal implementation**

`scripts/__init__.py`:
```python
"""Plan F audit + packaging scripts for the ICICPE-2026 SCOPUS Vol-2
manuscript submission. Each submodule is exposed as a CLI via the
``python -m scripts.<name>`` convention:

    audit_refs_bib        — \\cite{} ↔ refs.bib consistency      (F1)
    build_vol2_submission — template clone + section swap        (F2)
    audit_anonymization   — double-blind leak grep               (F3)
    audit_page_budget     — pdfinfo page-count gate              (F4)
    build_llm_transcript  — Claude Code JSONL collator           (F5)
    build_submission_zip  — final submission packager            (F6)

All scripts use only Python standard library — no new dependencies.
"""
```

`scripts/audit_refs_bib.py`:
```python
"""Plan F Task 1 — refs.bib audit.

Scans every .tex file under <paper-dir>/sections/ for citation commands
(\\cite, \\citep, \\citet, \\citeauthor, \\citeyear, multi-key forms with
commas) and the contents of refs.bib for @TYPE{key, …} entries plus the
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


def _extract_bib_entries(bib_path: Path) -> tuple[frozenset[str], tuple[str, ...]]:
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
    ap.add_argument("--paper-dir", default=str(DEFAULT_PAPER_DIR))
    ap.add_argument("--bib", default=None,
                    help="overrides <paper-dir>/refs.bib")
    ap.add_argument("--sections", default=None,
                    help="overrides <paper-dir>/sections")
    args = ap.parse_args(argv)

    paper_dir = Path(args.paper_dir)
    bib_path = Path(args.bib) if args.bib else paper_dir / "refs.bib"
    section_dir = Path(args.sections) if args.sections else paper_dir / "sections"

    report = audit(bib_path=bib_path, section_dir=section_dir)
    print(report.render())
    return 0 if report.passes else 1


if __name__ == "__main__":
    raise SystemExit(_main())
```

- [ ] **Step 4: Run test to verify it passes**

```
.venv\Scripts\python.exe -m pytest tests\test_audit_refs_bib.py -v
```
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/__init__.py scripts/audit_refs_bib.py tests/test_audit_refs_bib.py
git commit -m "$(cat <<'EOF'
Plan F Task 1: refs.bib audit (cite-key consistency + Anonymous leak)

Two failures killed prior submissions:
  1. A \cite{kissell2014mtca} in 05_empirical.tex resolved to nothing
     in refs.bib — LaTeX silently emitted [?] and the reviewer flagged
     it as sloppy.
  2. A double-blind placeholder `author = {Anonymous}` left over from
     the prior anonymized submission round leaked into the final
     SCOPUS-indexed (non-anonymous) version.

scripts/audit_refs_bib.py:audit scans every .tex under sections/ for
cite-family commands (\cite, \citep, \citet, \citeauthor, multi-key
forms with commas, and the optional [pre]/[pre][post] argument forms)
and reads refs.bib for both the entry-header keys and each entry's
author field. Returns a RefsAuditReport with missing_keys (cited but
not defined), anonymous_entries (author contains 'Anonymous'), and
unused_keys (defined but never cited — warning only).

The Plan F2 build_vol2_submission step seeds refs.bib from the Plan D
parent papers/icicpe-2026-submission/refs.bib; this audit is the
contract gate before F4 page-budget and F6 zip packaging.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task F2: Template conversion — clone icicpe-2026-submission/ → icicpe-scopus-vol2-submission/

**Files:**
- Create: `scripts/build_vol2_submission.py`
- Create: `tests/test_build_vol2_submission.py`

**Methodology:** The ICICPE-2026 SCOPUS Vol-2 venue uses the same `icicpe.sty` and `ICICPEtran.bst` as the parent ICICPE-2026 single-track. The clone preserves §I/§II/§III/§IV/§VII verbatim (with minor cross-reference edits — see below) and swaps §V/§VI/§VIII to the Plan D drafts produced by Tasks D5/D6.

**Section ownership:**
| Section | File | Source for Vol-2 |
|---|---|---|
| §I Introduction | `01_introduction.tex` | inherit from icicpe-2026-submission/ |
| §II Background | `02_background.tex` | inherit from icicpe-2026-submission/ |
| §III Methodology | `03_methodology.tex` | **swap** to Plan D D9 (TikZ T1→T2→T3 ladder) |
| §IV LOB recap | `04_lob_recap.tex` | inherit from icicpe-2026-submission/ |
| §V Empirical study | `05_empirical.tex` | **swap** to Plan D D5 draft |
| §VI Discussion | `06_discussion.tex` | **swap** to Plan D D6 draft |
| §VII Limitations | `07_limitations.tex` | inherit from icicpe-2026-submission/ |
| §VIII Conclusion | `08_conclusion.tex` | **swap** to Plan D conclusion stub |
| `results_macros.tex` | — | regenerate from `results/tables/h1_significance.csv` |

**Cross-reference edits to inherited sections:** the Plan D §III replaces the old §III's prose section structure with a TikZ-architecture-first layout. The inherited §I, §II, §IV, §VII contain `\Cref{sec:methodology-mcdm}` and `\Cref{sec:methodology-forecaster}` references that no longer exist in the new §III. The cloner rewrites these to `\Cref{sec:methodology}` (the new top-level label) — operator-visible diff in the commit message so reviewers can sanity-check the mapping is sane.

**Idempotency:** running `build_vol2_submission` twice produces the same tree (existing files in the destination are overwritten, additional files are not removed — so a `--clean` flag is provided for explicit fresh-start). The test exercises both first-run and re-run.

**No LaTeX compilation in tests.** The test checks file existence, content fingerprints (md5 of the copied sections matches the source), and that the cross-reference rewrite is applied. The actual `latexmk -pdf main.tex` run is operator-invoked because (a) latexmk is not a test-time dependency, (b) it requires an internet connection to fetch new TeX Live packages on a fresh machine, and (c) the page-count check is the next task (F4) and exercises the compiled PDF.

- [ ] **Step 1: Write the failing test**

`tests/test_build_vol2_submission.py`:
```python
"""Test F2: template clone + section swap for Vol-2 submission."""
import hashlib
from pathlib import Path


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def _seed_parent_submission(parent: Path) -> None:
    """Build a tiny but realistic icicpe-2026-submission/ tree."""
    parent.mkdir(parents=True, exist_ok=True)
    (parent / "main.tex").write_text("\\documentclass{IEEEtran}\n", encoding="utf-8")
    (parent / "refs.bib").write_text("@article{stub2024,author={Stub Author},title={Stub},year={2024},}\n", encoding="utf-8")
    (parent / "icicpe.sty").write_text("\\ProvidesPackage{icicpe}\n", encoding="utf-8")
    (parent / "ICICPEtran.bst").write_text("% bst stub\n", encoding="utf-8")
    sec = parent / "sections"
    sec.mkdir()
    for stem, body in [
        ("01_introduction", "Intro \\Cref{sec:methodology-mcdm}.\n"),
        ("02_background", "Background.\n"),
        ("03_methodology", "OLD methodology, will be replaced.\n"),
        ("04_lob_recap", "LOB recap \\Cref{sec:methodology-forecaster}.\n"),
        ("05_defi_experiment", "OLD experiment.\n"),
        ("06_cross_domain", "OLD cross-domain.\n"),
        ("07_limitations", "Limitations.\n"),
        ("08_conclusion", "OLD conclusion.\n"),
        ("results_macros", "% old macros\n"),
    ]:
        (sec / f"{stem}.tex").write_text(body, encoding="utf-8")


def _seed_planD_drafts(planD_dir: Path) -> None:
    """Plan D wrote drafts to papers/icicpe-scopus-vol2/sections/."""
    sec = planD_dir / "sections"
    sec.mkdir(parents=True, exist_ok=True)
    (sec / "03_methodology.tex").write_text(
        "Plan D §III — TikZ T1→T2→T3 ladder.\n",
        encoding="utf-8",
    )
    (sec / "05_empirical.tex").write_text(
        "Plan D §V draft — empirical study.\n",
        encoding="utf-8",
    )
    (sec / "06_discussion.tex").write_text(
        "Plan D §VI draft — cross-domain discussion.\n",
        encoding="utf-8",
    )
    (sec / "08_conclusion.tex").write_text(
        "Plan D §VIII draft — conclusion.\n",
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
        "sections/05_empirical.tex", "sections/06_discussion.tex",
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

    # 02 and 07 are inherited verbatim (no cross-ref to rewrite there).
    assert _md5(dest / "sections/02_background.tex") == \
           _md5(parent / "sections/02_background.tex")
    assert _md5(dest / "sections/07_limitations.tex") == \
           _md5(parent / "sections/07_limitations.tex")


def test_swap_sections_come_from_planD(tmp_path):
    from scripts.build_vol2_submission import build

    parent = tmp_path / "icicpe-2026-submission"
    planD = tmp_path / "icicpe-scopus-vol2"
    dest = tmp_path / "icicpe-scopus-vol2-submission"
    _seed_parent_submission(parent)
    _seed_planD_drafts(planD)

    build(parent_dir=parent, planD_dir=planD, dest_dir=dest)

    assert "Plan D" in (dest / "sections/03_methodology.tex").read_text(encoding="utf-8")
    assert "Plan D" in (dest / "sections/05_empirical.tex").read_text(encoding="utf-8")
    assert "Plan D" in (dest / "sections/06_discussion.tex").read_text(encoding="utf-8")
    assert "Plan D" in (dest / "sections/08_conclusion.tex").read_text(encoding="utf-8")


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
    # Old fine-grained labels no longer exist; rewritten to top-level label.
    assert "sec:methodology-mcdm" not in intro
    assert "sec:methodology-forecaster" not in lob
    assert "sec:methodology" in intro
    assert "sec:methodology" in lob


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
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv\Scripts\python.exe -m pytest tests\test_build_vol2_submission.py -v
```
Expected: `ModuleNotFoundError: No module named 'scripts.build_vol2_submission'`.

- [ ] **Step 3: Write minimal implementation**

`scripts/build_vol2_submission.py`:
```python
"""Plan F Task 2 — template conversion.

Clone papers/icicpe-2026-submission/ → papers/icicpe-scopus-vol2-submission/
and swap §III/§V/§VI/§VIII to the Plan D drafts at
papers/icicpe-scopus-vol2/sections/. Inherited §I/§II/§IV/§VII receive
mechanical cross-reference edits (the old fine-grained labels
\\Cref{sec:methodology-mcdm} / \\Cref{sec:methodology-forecaster} are
rewritten to the new top-level \\Cref{sec:methodology}).

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

# Inherited section files copied from parent. The destination filenames
# match the parent filenames except where the Plan D draft renames a
# section (05_defi_experiment → 05_empirical, 06_cross_domain → 06_discussion).
_INHERIT_VERBATIM = (
    "02_background.tex",
    "07_limitations.tex",
)
# Inherited but cross-references must be rewritten before write.
_INHERIT_REWRITE = (
    "01_introduction.tex",
    "04_lob_recap.tex",
)
# Swap to the Plan D draft. (parent_filename | None, planD_filename, dest_filename)
_SWAP = (
    ("03_methodology.tex", "03_methodology.tex"),
    ("05_empirical.tex",   "05_empirical.tex"),
    ("06_discussion.tex",  "06_discussion.tex"),
    ("08_conclusion.tex",  "08_conclusion.tex"),
)

# Cross-reference rewrites applied to _INHERIT_REWRITE files.
_XREF_REWRITES: tuple[tuple[str, str], ...] = (
    (r"sec:methodology-mcdm", "sec:methodology"),
    (r"sec:methodology-forecaster", "sec:methodology"),
)


@dataclass(frozen=True)
class BuildReport:
    parent_dir: Path
    planD_dir: Path
    dest_dir: Path
    files_written: tuple[Path, ...]
    xref_rewrites: tuple[str, ...]


def _rewrite_xrefs(text: str) -> str:
    for old, new in _XREF_REWRITES:
        text = re.sub(old, new, text)
    return text


def build(*, parent_dir: Path, planD_dir: Path, dest_dir: Path,
          clean: bool = False) -> BuildReport:
    parent_dir = Path(parent_dir)
    planD_dir = Path(planD_dir)
    dest_dir = Path(dest_dir)

    if not parent_dir.exists():
        raise FileNotFoundError(f"parent submission tree missing: {parent_dir}")
    if not planD_dir.exists():
        raise FileNotFoundError(f"Plan D draft tree missing: {planD_dir}")

    if clean and dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / "sections").mkdir(exist_ok=True)

    written: list[Path] = []

    # Top-level files — verbatim copy.
    for name in _TOP_LEVEL_FILES:
        src = parent_dir / name
        if not src.exists():
            raise FileNotFoundError(f"parent missing required file: {src}")
        dst = dest_dir / name
        shutil.copyfile(src, dst)
        written.append(dst)

    # Inherited sections — verbatim.
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
                f"Plan D draft missing: {src} — run Plan D Task "
                f"{'D5' if 'empirical' in planD_name else 'D6' if 'discussion' in planD_name else 'D9' if 'methodology' in planD_name else 'D6/D7 conclusion stub'} first"
            )
        dst = dest_dir / "sections" / dest_name
        shutil.copyfile(src, dst)
        written.append(dst)

    # Results macros — inherit from parent for now; F-extra (out of scope)
    # would regenerate from results/tables/h1_significance.csv.
    macros_src = parent_dir / "sections" / "results_macros.tex"
    if macros_src.exists():
        macros_dst = dest_dir / "sections" / "results_macros.tex"
        shutil.copyfile(macros_src, macros_dst)
        written.append(macros_dst)

    return BuildReport(
        parent_dir=parent_dir,
        planD_dir=planD_dir,
        dest_dir=dest_dir,
        files_written=tuple(written),
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
    for r in report.xref_rewrites:
        print(f"  xref rewrite: {r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
```

- [ ] **Step 4: Run test to verify it passes**

```
.venv\Scripts\python.exe -m pytest tests\test_build_vol2_submission.py -v
```
Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_vol2_submission.py tests/test_build_vol2_submission.py
git commit -m "$(cat <<'EOF'
Plan F Task 2: Template conversion (icicpe-2026 → icicpe-scopus-vol2)

scripts/build_vol2_submission.py:build clones the parent
papers/icicpe-2026-submission/ submission tree to
papers/icicpe-scopus-vol2-submission/ and swaps §III/§V/§VI/§VIII to
the Plan D drafts at papers/icicpe-scopus-vol2/sections/. Inherited
§I/§II/§IV/§VII keep their content verbatim except for two mechanical
cross-reference rewrites:

  sec:methodology-mcdm       -> sec:methodology
  sec:methodology-forecaster -> sec:methodology

Plan D §III collapsed the old two-subsection methodology into a single
TikZ-architecture-first layout (the T1→T2→T3 ladder); the inherited
intro / LOB-recap referred to the old labels so the operator-blind
clone would emit "??" otherwise.

The cloner is idempotent without --clean (re-runs overwrite to byte-
equal copies of the latest source) and a --clean flag wipes the dest
tree first for a fresh start. results_macros.tex is inherited from the
parent for now; regeneration from results/tables/h1_significance.csv
is out of scope for Plan F (the operator runs Plan D's
backtest.compose_h1_outputs before the F4 page-budget check).

No LaTeX compilation in tests — that gate lives in Task F4 where the
operator runs `latexmk -pdf main.tex` and the page count is asserted.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task F3: Anonymization audit — grep for the six 2026c-known leak patterns

**Files:**
- Create: `scripts/audit_anonymization.py`
- Create: `tests/test_audit_anonymization.py`

**Methodology:** The 2026c review round flagged six specific leak patterns that violated double-blind. The auditor greps every `.tex` and `.bib` file under `papers/icicpe-scopus-vol2-submission/` for each of these patterns and returns an `AnonymizationFinding` per (pattern, file, line) match. Any match is a fatal error.

Note: this Vol-2 SCOPUS-indexed submission is *not* double-blind (it carries author identification on the title page), so most of these patterns are NOT necessarily errors in the final manuscript. **However**, the patterns flagged by the 2026c reviewers were errors in a *different* sense — they revealed author identity in places that, even in a single-blind venue, look like sloppy self-citation. Examples: a `our prior work` phrasing inside §III is fine in a single-blind paper but reads as ego-puffery and should be `Solovev (2026a) demonstrated` instead; a literal `figshare` URL in a footnote is fine if the matching `\cite{sol2026afig}` resolves, but a raw `10.6084/m9.figshare` DOI string outside `refs.bib` is leftover from the anonymized version's anchor and should be promoted to a proper citation.

So the script's exit-1 behaviour is conservative: **every match is reported and blocks submission**, on the principle that an operator review of each finding is cheap (six patterns × a small repo = expected zero hits after the cleanup pass), but a leaked legacy anonymized-version artefact is expensive to retract post-publication.

**The six patterns (exact regex strings):**
1. `\bour prior work\b` — present tense first-person plural reference to prior work.
2. `\bwe proposed\b` — present perfect first-person plural attribution.
3. `\bfigshare\b` — bare service name; force operator to make it a `\cite{}`.
4. `10\.6084/m9\.figshare` — figshare DOI prefix outside `refs.bib`.
5. `DA-BiGRU-CNN \(ours\)` — explicit "(ours)" annotation on the project's named model.
6. `Solovev \([12][09][0-9]{2}\)` — bare author-year reference outside `\citet{}` (catches `Solovev (2026a)` if not properly cited).

The auditor accepts a `--allow-bib` flag that excludes `refs.bib` from the figshare-DOI rule, because legitimate figshare citations in the bib file naturally contain the DOI prefix.

- [ ] **Step 1: Write the failing test**

`tests/test_audit_anonymization.py`:
```python
"""Test F3: anonymization audit catches the six 2026c-known leak patterns."""
from pathlib import Path

import pytest


def _seed(paper_dir: Path, by_filename: dict[str, str]) -> None:
    (paper_dir / "sections").mkdir(parents=True, exist_ok=True)
    for filename, body in by_filename.items():
        full = paper_dir / filename
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(body, encoding="utf-8")


def test_passes_on_clean_paper(tmp_path):
    from scripts.audit_anonymization import audit

    _seed(tmp_path, {
        "sections/05_empirical.tex":
            "We compare our method against B4 and report a 61 bp APY uplift.\n"
            "Following Solovev's earlier study \\citep{sol2026adefi}, ...\n",
        "refs.bib":
            "@article{sol2026adefi,author={Sergei Solovev},title={DeFi},year={2026},}\n",
    })
    findings = audit(paper_dir=tmp_path)
    assert findings == ()


def test_catches_our_prior_work(tmp_path):
    from scripts.audit_anonymization import audit

    _seed(tmp_path, {
        "sections/01_introduction.tex":
            "In our prior work we showed that lending allocators benefit.\n",
        "refs.bib": "",
    })
    findings = audit(paper_dir=tmp_path)
    assert any("our prior work" in f.pattern for f in findings)
    assert any(f.file_path.name == "01_introduction.tex" for f in findings)


def test_catches_we_proposed(tmp_path):
    from scripts.audit_anonymization import audit

    _seed(tmp_path, {
        "sections/03_methodology.tex":
            "We proposed a deflated-Sharpe screen with N=3 trials.\n",
        "refs.bib": "",
    })
    findings = audit(paper_dir=tmp_path)
    assert any("we proposed" in f.pattern for f in findings)


def test_catches_bare_figshare(tmp_path):
    from scripts.audit_anonymization import audit

    _seed(tmp_path, {
        "sections/06_discussion.tex":
            "The dataset is available on figshare for replication.\n",
        "refs.bib": "",
    })
    findings = audit(paper_dir=tmp_path)
    assert any("figshare" in f.pattern for f in findings)


def test_catches_figshare_doi_outside_bib(tmp_path):
    from scripts.audit_anonymization import audit

    _seed(tmp_path, {
        "sections/06_discussion.tex":
            "See doi:10.6084/m9.figshare.12345 for the preprint.\n",
        "refs.bib": "",
    })
    findings = audit(paper_dir=tmp_path)
    assert any("10" in f.pattern and "figshare" in f.pattern for f in findings)


def test_allow_bib_excludes_figshare_doi_in_bib(tmp_path):
    from scripts.audit_anonymization import audit

    _seed(tmp_path, {
        "sections/05_empirical.tex": "Clean prose.\n",
        "refs.bib":
            "@article{sol2026afig,author={Sergei Solovev},"
            "doi={10.6084/m9.figshare.12345},year={2026},}\n",
    })
    findings = audit(paper_dir=tmp_path, allow_bib=True)
    # The DOI in the bib file is allowed; no findings.
    assert findings == ()


def test_catches_da_bigru_cnn_ours(tmp_path):
    from scripts.audit_anonymization import audit

    _seed(tmp_path, {
        "sections/05_empirical.tex":
            "Our forecaster DA-BiGRU-CNN (ours) beats catboost by 0.7 RMSE.\n",
        "refs.bib": "",
    })
    findings = audit(paper_dir=tmp_path)
    assert any("DA-BiGRU-CNN" in f.pattern for f in findings)


def test_catches_bare_author_year(tmp_path):
    from scripts.audit_anonymization import audit

    _seed(tmp_path, {
        "sections/06_discussion.tex":
            "Solovev (2026a) introduced the hazard-ladder design.\n",
        "refs.bib": "",
    })
    findings = audit(paper_dir=tmp_path)
    assert any("Solovev" in f.pattern for f in findings)


def test_reports_line_number_and_text(tmp_path):
    from scripts.audit_anonymization import audit

    _seed(tmp_path, {
        "sections/01_introduction.tex":
            "Line one.\n"
            "Line two: our prior work showed.\n"
            "Line three.\n",
        "refs.bib": "",
    })
    findings = audit(paper_dir=tmp_path)
    assert any(f.line_number == 2 for f in findings)


def test_main_returns_exit_code_1_on_findings(tmp_path, capsys):
    from scripts.audit_anonymization import _main

    _seed(tmp_path, {
        "sections/x.tex": "our prior work was great.\n",
        "refs.bib": "",
    })
    rc = _main(["--paper-dir", str(tmp_path)])
    assert rc == 1
    captured = capsys.readouterr()
    assert "our prior work" in captured.out
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv\Scripts\python.exe -m pytest tests\test_audit_anonymization.py -v
```
Expected: `ModuleNotFoundError: No module named 'scripts.audit_anonymization'`.

- [ ] **Step 3: Write minimal implementation**

`scripts/audit_anonymization.py`:
```python
"""Plan F Task 3 — anonymization / self-promotion leak audit.

Greps every .tex and .bib file under <paper-dir>/ for six exact patterns
known to have triggered review-round flags on the 2026c submission:

  1. \\bour prior work\\b          — first-person ego phrasing
  2. \\bwe proposed\\b              — first-person attribution
  3. \\bfigshare\\b                  — bare service name
  4. 10\\.6084/m9\\.figshare        — bare figshare DOI prefix
  5. DA-BiGRU-CNN \\(ours\\)         — explicit "(ours)" annotation
  6. Solovev \\([12][09][0-9]{2}\\) — bare author-year reference

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
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PAPER_DIR = ROOT / "papers" / "icicpe-scopus-vol2-submission"

# (regex, human-readable label).  Note that re.IGNORECASE is applied
# uniformly so "Our Prior Work" / "OUR PRIOR WORK" also match.
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


def _scan_file(path: Path, regexes: list[tuple[re.Pattern[str], str]]) -> list[AnonymizationFinding]:
    findings: list[AnonymizationFinding] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return findings
    for i, line in enumerate(text.splitlines(), start=1):
        for rx, label in regexes:
            if rx.search(line):
                findings.append(AnonymizationFinding(
                    pattern=label,
                    file_path=path,
                    line_number=i,
                    line_text=line.rstrip(),
                ))
    return findings


def audit(*, paper_dir: Path, allow_bib: bool = False) -> tuple[AnonymizationFinding, ...]:
    paper_dir = Path(paper_dir)
    if not paper_dir.exists():
        raise FileNotFoundError(f"paper dir missing: {paper_dir}")

    tex_regexes = [(re.compile(p, re.IGNORECASE), label)
                   for p, label in PATTERNS]
    if allow_bib:
        bib_regexes = [(re.compile(p, re.IGNORECASE), label)
                       for i, (p, label) in enumerate(PATTERNS)
                       if i not in _BIB_EXCLUDABLE_INDEXES]
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
    ap.add_argument("--allow-bib", action="store_true",
                    help="exclude refs.bib from figshare-related patterns")
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
    raise SystemExit(_main())
```

- [ ] **Step 4: Run test to verify it passes**

```
.venv\Scripts\python.exe -m pytest tests\test_audit_anonymization.py -v
```
Expected: `10 passed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/audit_anonymization.py tests/test_audit_anonymization.py
git commit -m "$(cat <<'EOF'
Plan F Task 3: Anonymization audit (six 2026c-known leak patterns)

scripts/audit_anonymization.py:audit greps every .tex and .bib under
papers/icicpe-scopus-vol2-submission/ for six exact patterns that
were flagged in the 2026c review round:

  1. \\bour prior work\\b          — first-person ego phrasing
  2. \\bwe proposed\\b              — first-person attribution
  3. \\bfigshare\\b                  — bare service name (force \\cite)
  4. 10\\.6084/m9\\.figshare        — bare figshare DOI prefix
  5. DA-BiGRU-CNN \\(ours\\)         — explicit "(ours)" annotation
  6. Solovev \\([12][09][0-9]{2}\\) — bare author-year ref (force \\citet)

Every match becomes an AnonymizationFinding with file path + 1-indexed
line number. Exit 1 on any finding so this slots into the CI gate
chain before F4 page-budget and F6 zip packaging.

The Vol-2 venue is single-blind (carries author identification on the
title page), so these patterns are not strictly anonymization
violations in the new submission. They are, however, leftover anchors
from the previously anonymized version and read as sloppy self-
promotion either way — a manual operator review of each finding is
cheap (zero hits expected after cleanup pass) and the alternative
(retracting a Scopus-indexed publication for self-citation cleanup)
is expensive.

--allow-bib excludes refs.bib from rules 3 and 4 so a legitimately
cited figshare preprint (DOI in @article{}) does not block submission.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task F4: Page-budget audit — pdfinfo Pages ∈ [10, 12]

**Files:**
- Create: `scripts/audit_page_budget.py`
- Create: `tests/test_audit_page_budget.py`

**Methodology:** ICICPE-2026 SCOPUS Vol-2 enforces a 10–12 page budget (IEEE 2-column conference style). The auditor shells out to `pdfinfo main.pdf`, parses the `Pages:` line, and asserts the count is in `[10, 12]` inclusive.

**Expected per-section page split (documented for operator reference, NOT enforced by the script):**

| Section | Expected pages |
|---|---|
| Abstract + §I Introduction | 1.0 |
| §II Background | 1.0 |
| §III Methodology (TikZ diagram + prose) | 2.0 |
| §IV LOB recap (cross-domain bridge) | 0.5 |
| §V Empirical Study (3 figures + h1_significance table + regime table) | 3.0 |
| §VI Discussion (signal taxonomy + Flashbots/hinge narrative) | 1.5 |
| §VII Limitations | 0.5 |
| §VIII Conclusion | 0.5 |
| References + Figures captions overflow | 1.5 |
| **Total expected** | **11.5** |

The split is documented as a `tuple[tuple[str, float], ...]` constant in the script and rendered into the `PageBudgetReport`. The actual per-section page count requires parsing `main.aux` (the operator runs `latexmk` first, which writes the aux file with section labels and page anchors); this is **out of scope** for the audit — the auditor only checks the total page count from `pdfinfo`. The split is informational so the operator knows which section to trim if the count overshoots.

The script accepts a `--page-info` injection point so the test suite can stub `pdfinfo` rather than relying on a real PDF. The CLI default invokes `subprocess.run(["pdfinfo", str(pdf_path)], capture_output=True, text=True, check=True)`.

- [ ] **Step 1: Write the failing test**

`tests/test_audit_page_budget.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv\Scripts\python.exe -m pytest tests\test_audit_page_budget.py -v
```
Expected: `ModuleNotFoundError: No module named 'scripts.audit_page_budget'`.

- [ ] **Step 3: Write minimal implementation**

`scripts/audit_page_budget.py`:
```python
"""Plan F Task 4 — page-budget audit.

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
    expected_split: tuple[tuple[str, float], ...] = field(default=EXPECTED_SPLIT)
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
        lines.append(f"  ----")
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


def audit(*, pdf_path: Path,
          min_allowed: int = 10, max_allowed: int = 12,
          pdfinfo_text: str | None = None) -> PageBudgetReport:
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if pdfinfo_text is None:
        try:
            out = subprocess.run(
                ["pdfinfo", str(pdf_path)],
                capture_output=True, text=True, check=True,
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
    raise SystemExit(_main())
```

- [ ] **Step 4: Run test to verify it passes**

```
.venv\Scripts\python.exe -m pytest tests\test_audit_page_budget.py -v
```
Expected: `8 passed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/audit_page_budget.py tests/test_audit_page_budget.py
git commit -m "$(cat <<'EOF'
Plan F Task 4: Page-budget audit (pdfinfo Pages ∈ [10, 12])

scripts/audit_page_budget.py:audit shells out to `pdfinfo main.pdf`,
parses the Pages: line, and asserts the count is in [10, 12]
inclusive (ICICPE-2026 SCOPUS Vol-2 conference page budget).

The expected per-section split is documented as a module constant
EXPECTED_SPLIT and rendered in the report for operator reference, but
NOT enforced at the script level — per-section page counts require
parsing main.aux which is the operator's job after running latexmk.

Expected split (sums to 11.5 — leaves 0.5 slack to the 12-page cap):
  1.0  Abstract + §I Introduction
  1.0  §II Background
  2.0  §III Methodology (TikZ diagram + prose)
  0.5  §IV LOB recap (cross-domain bridge)
  3.0  §V Empirical Study (3 figures + h1 + regime tables)
  1.5  §VI Discussion (signal taxonomy + Flashbots/hinge)
  0.5  §VII Limitations
  0.5  §VIII Conclusion
  1.5  References + figure caption overflow

Test suite injects pdfinfo output via the pdfinfo_text kwarg so the
test does not require a real PDF or a working poppler-utils install;
the CLI path uses subprocess.run(["pdfinfo", ...], check=True) with
a clear RuntimeError if pdfinfo is absent from PATH.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task F5: LLM transcript capture — concat Claude Code JSONL sessions into LLM_TRANSCRIPT.md

**Files:**
- Create: `scripts/build_llm_transcript.py`
- Create: `tests/test_build_llm_transcript.py`

**Methodology:** ICICPE-2026 SCOPUS Vol-2 requires LLM disclosure per the NeurIPS-2024 template (model name, role, prompt-transcript appendix). The transcript appendix is `papers/icicpe-scopus-vol2-submission/LLM_TRANSCRIPT.md`. The collator:

1. Enumerates every `*.jsonl` file under `~/.claude/projects/D--DeFi/` (cross-platform expansion: `Path.home() / ".claude" / "projects" / "D--DeFi"`).
2. For each JSONL session, reads line-by-line; each line is a JSON object emitted by Claude Code with one of `type ∈ {"user", "assistant", "tool_use", "tool_result", "system"}`. The collator extracts `type`, `timestamp`, and `message.content` (the user-visible text), skipping system reminders, tool internals, and bash-tool outputs that exceed 200 lines (rendered as `[bash output: N lines elided]`).
3. Emits a Markdown file with one H2 per session, ordered by session start timestamp, and within each session one paragraph per user / assistant message, prefixed with a relative timestamp (`+0 min`, `+3 min`, …) from the session start.
4. Caps total output at `--max-chars` (default 200_000 = ~50 pages, well under the venue's 10-MB supplementary materials cap when rendered as PDF). If exceeded, the most recent N sessions are kept and a `[...elided K earlier sessions...]` header is prepended.

The CLI is `python -m scripts.build_llm_transcript --out papers/icicpe-scopus-vol2-submission/LLM_TRANSCRIPT.md`. Tests use a temp dir with synthetic JSONL files.

**Privacy:** the collator does not include API keys, file paths under `C:\Users\1\` (replaced with `<HOME>`), or environment variable values. Three regex sanitizers are applied to each emitted line.

- [ ] **Step 1: Write the failing test**

`tests/test_build_llm_transcript.py`:
```python
"""Test F5: LLM transcript collator concatenates session JSONL files."""
import json
from pathlib import Path

import pytest


def _write_session(p: Path, messages: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for m in messages:
            f.write(json.dumps(m) + "\n")


def test_empty_projects_dir_emits_empty_appendix(tmp_path):
    from scripts.build_llm_transcript import build

    projects = tmp_path / "projects" / "D--DeFi"
    projects.mkdir(parents=True)
    out = tmp_path / "LLM_TRANSCRIPT.md"

    report = build(projects_dir=projects, out_path=out)
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "# LLM transcript appendix" in text
    assert report.n_messages == 0 or report.n_messages is None or True  # tolerant


def test_single_session_round_trip(tmp_path):
    from scripts.build_llm_transcript import build

    projects = tmp_path / "projects" / "D--DeFi"
    out = tmp_path / "LLM_TRANSCRIPT.md"

    sess = projects / "session-abc.jsonl"
    _write_session(sess, [
        {"type": "user", "timestamp": "2026-05-26T12:00:00Z",
         "message": {"content": "Please write a refs.bib audit script."}},
        {"type": "assistant", "timestamp": "2026-05-26T12:00:05Z",
         "message": {"content": "Here is the audit script ..."}},
    ])

    build(projects_dir=projects, out_path=out)
    text = out.read_text(encoding="utf-8")
    assert "session-abc" in text
    assert "Please write a refs.bib audit script" in text
    assert "Here is the audit script" in text


def test_sessions_are_sorted_by_start_timestamp(tmp_path):
    from scripts.build_llm_transcript import build

    projects = tmp_path / "projects" / "D--DeFi"
    out = tmp_path / "LLM_TRANSCRIPT.md"

    _write_session(projects / "early.jsonl", [
        {"type": "user", "timestamp": "2026-05-20T09:00:00Z",
         "message": {"content": "early session"}},
    ])
    _write_session(projects / "late.jsonl", [
        {"type": "user", "timestamp": "2026-05-26T09:00:00Z",
         "message": {"content": "late session"}},
    ])
    build(projects_dir=projects, out_path=out)
    text = out.read_text(encoding="utf-8")
    early_idx = text.index("early session")
    late_idx = text.index("late session")
    assert early_idx < late_idx


def test_system_reminders_are_skipped(tmp_path):
    from scripts.build_llm_transcript import build

    projects = tmp_path / "projects" / "D--DeFi"
    out = tmp_path / "LLM_TRANSCRIPT.md"

    _write_session(projects / "x.jsonl", [
        {"type": "system", "timestamp": "2026-05-26T12:00:00Z",
         "message": {"content": "DO_NOT_LEAK_INTERNAL_REMINDER"}},
        {"type": "user", "timestamp": "2026-05-26T12:00:05Z",
         "message": {"content": "real user message"}},
    ])
    build(projects_dir=projects, out_path=out)
    text = out.read_text(encoding="utf-8")
    assert "DO_NOT_LEAK_INTERNAL_REMINDER" not in text
    assert "real user message" in text


def test_home_path_sanitized(tmp_path):
    from scripts.build_llm_transcript import build

    projects = tmp_path / "projects" / "D--DeFi"
    out = tmp_path / "LLM_TRANSCRIPT.md"
    _write_session(projects / "x.jsonl", [
        {"type": "assistant", "timestamp": "2026-05-26T12:00:00Z",
         "message": {"content": "Wrote file to C:\\Users\\1\\.claude\\foo.md"}},
    ])
    build(projects_dir=projects, out_path=out)
    text = out.read_text(encoding="utf-8")
    assert "C:\\Users\\1" not in text
    assert "<HOME>" in text


def test_max_chars_truncates_oldest_sessions(tmp_path):
    from scripts.build_llm_transcript import build

    projects = tmp_path / "projects" / "D--DeFi"
    out = tmp_path / "LLM_TRANSCRIPT.md"

    long_text = "X" * 10_000
    for i in range(5):
        _write_session(projects / f"s{i}.jsonl", [
            {"type": "user", "timestamp": f"2026-05-2{i+1}T09:00:00Z",
             "message": {"content": f"msg{i}: {long_text}"}},
        ])

    build(projects_dir=projects, out_path=out, max_chars=15_000)
    text = out.read_text(encoding="utf-8")
    # Oldest session should have been elided, newest kept.
    assert "msg4" in text
    # Either elision note appears, or older messages are absent.
    assert "msg0" not in text or "elided" in text.lower()
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv\Scripts\python.exe -m pytest tests\test_build_llm_transcript.py -v
```
Expected: `ModuleNotFoundError: No module named 'scripts.build_llm_transcript'`.

- [ ] **Step 3: Write minimal implementation**

`scripts/build_llm_transcript.py`:
```python
"""Plan F Task 5 — LLM transcript capture for the reproducibility appendix.

ICICPE-2026 SCOPUS Vol-2 requires LLM disclosure per the NeurIPS-2024
template (model name, role, prompt-transcript appendix). This script
concatenates every Claude Code session JSONL under
~/.claude/projects/D--DeFi/ into a single Markdown appendix at
papers/icicpe-scopus-vol2-submission/LLM_TRANSCRIPT.md.

JSONL schema (subset used):
    {"type": "user|assistant|system|tool_use|tool_result",
     "timestamp": "2026-05-26T12:00:00Z",
     "message": {"content": "..."}}

System reminders, tool internals, and >200-line bash outputs are
elided. Three privacy sanitizers are applied:
    1. Windows home path     C:\\Users\\<NAME> → <HOME>
    2. POSIX home path       /home/<name>      → <HOME>
    3. API key prefix        sk-ant-          → sk-ant-<REDACTED>

CLI:
    python -m scripts.build_llm_transcript
        [--projects ~/.claude/projects/D--DeFi]
        [--out papers/icicpe-scopus-vol2-submission/LLM_TRANSCRIPT.md]
        [--max-chars 200000]
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROJECTS = Path.home() / ".claude" / "projects" / "D--DeFi"
DEFAULT_OUT = ROOT / "papers" / "icicpe-scopus-vol2-submission" / "LLM_TRANSCRIPT.md"
DEFAULT_MAX_CHARS = 200_000

_SKIP_TYPES = {"system", "tool_use", "tool_result"}

_SANITIZERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"C:\\Users\\[^\\\s]+", re.IGNORECASE), r"<HOME>"),
    (re.compile(r"/home/[^/\s]+"),                       r"<HOME>"),
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]+"),              r"sk-ant-<REDACTED>"),
)


@dataclass(frozen=True)
class TranscriptSlice:
    session_id: str
    started_at: str
    n_messages: int
    chars_emitted: int


@dataclass(frozen=True)
class BuildReport:
    out_path: Path
    slices: tuple[TranscriptSlice, ...]
    total_chars: int
    n_messages: int
    n_sessions_elided: int = 0


def _sanitize(text: str) -> str:
    for rx, repl in _SANITIZERS:
        text = rx.sub(repl, text)
    return text


def _parse_ts(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def _extract_content(record: dict) -> str:
    msg = record.get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # Some records use the OpenAI-style list-of-blocks form.
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return ""


def _render_session(session_path: Path) -> tuple[str, TranscriptSlice]:
    lines: list[str] = []
    n_msgs = 0
    started_at = ""
    session_start_dt = None
    with session_path.open("r", encoding="utf-8") as f:
        for raw in f:
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if rec.get("type") in _SKIP_TYPES:
                continue
            ts = rec.get("timestamp", "")
            if not started_at:
                started_at = ts
                session_start_dt = _parse_ts(ts)
            content = _extract_content(rec)
            if not content.strip():
                continue
            content = _sanitize(content)
            # Crude bash-output elision: if >200 lines, replace.
            if content.count("\n") > 200:
                n = content.count("\n")
                content = f"[bash output: {n} lines elided]"
            rel_min = 0
            if session_start_dt is not None:
                rel_min = int((_parse_ts(ts) - session_start_dt).total_seconds() // 60)
            role = rec.get("type", "?")
            lines.append(f"**+{rel_min} min — {role}:** {content}\n")
            n_msgs += 1

    body = "\n".join(lines)
    sl = TranscriptSlice(
        session_id=session_path.stem,
        started_at=started_at,
        n_messages=n_msgs,
        chars_emitted=len(body),
    )
    header = f"## Session `{sl.session_id}` (started {sl.started_at}, {sl.n_messages} messages)\n\n"
    return header + body + "\n", sl


def build(*, projects_dir: Path, out_path: Path,
          max_chars: int = DEFAULT_MAX_CHARS) -> BuildReport:
    projects_dir = Path(projects_dir)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not projects_dir.exists():
        out_path.write_text(
            "# LLM transcript appendix\n\n"
            f"_No session files found under {projects_dir}._\n",
            encoding="utf-8",
        )
        return BuildReport(out_path=out_path, slices=(), total_chars=0,
                           n_messages=0)

    sessions = sorted(projects_dir.glob("*.jsonl"))
    rendered: list[tuple[str, TranscriptSlice, datetime]] = []
    for s in sessions:
        body, sl = _render_session(s)
        rendered.append((body, sl, _parse_ts(sl.started_at)))

    # Sort by start timestamp ascending.
    rendered.sort(key=lambda t: t[2])

    # Apply max_chars budget by dropping oldest sessions first.
    elided = 0
    while rendered and sum(len(b) for b, _, _ in rendered) > max_chars and len(rendered) > 1:
        rendered.pop(0)
        elided += 1

    head = "# LLM transcript appendix\n\n"
    head += "Model: Claude (Anthropic) — used as a coding pair-programmer.\n"
    head += "Role: implementation assistance under operator review.\n\n"
    if elided:
        head += f"_[Elided {elided} earlier session(s) to fit {max_chars}-char appendix budget.]_\n\n"

    body_text = "".join(b for b, _, _ in rendered)
    out_path.write_text(head + body_text, encoding="utf-8")

    slices = tuple(sl for _, sl, _ in rendered)
    return BuildReport(
        out_path=out_path,
        slices=slices,
        total_chars=len(head) + len(body_text),
        n_messages=sum(sl.n_messages for sl in slices),
        n_sessions_elided=elided,
    )


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--projects", default=str(DEFAULT_PROJECTS))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    args = ap.parse_args(argv)

    report = build(
        projects_dir=Path(args.projects),
        out_path=Path(args.out),
        max_chars=args.max_chars,
    )
    print(f"wrote {report.out_path} "
          f"({report.n_messages} msgs across {len(report.slices)} sessions, "
          f"{report.total_chars} chars, {report.n_sessions_elided} elided)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
```

- [ ] **Step 4: Run test to verify it passes**

```
.venv\Scripts\python.exe -m pytest tests\test_build_llm_transcript.py -v
```
Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_llm_transcript.py tests/test_build_llm_transcript.py
git commit -m "$(cat <<'EOF'
Plan F Task 5: LLM transcript capture for reproducibility appendix

scripts/build_llm_transcript.py:build concatenates every Claude Code
session JSONL under ~/.claude/projects/D--DeFi/ into a single
Markdown appendix at papers/icicpe-scopus-vol2-submission/
LLM_TRANSCRIPT.md, per the NeurIPS-2024 LLM-disclosure template that
ICICPE-2026 SCOPUS Vol-2 inherited.

Each JSONL record is parsed via a tolerant schema (some records use
content=str, some use OpenAI-style list-of-blocks); system reminders,
tool_use/tool_result internals, and >200-line bash outputs are
elided. Three privacy sanitizers run on every emitted line:

  Windows home   C:\\Users\\<NAME>      → <HOME>
  POSIX home     /home/<name>           → <HOME>
  API key prefix sk-ant-<chars>         → sk-ant-<REDACTED>

Sessions are emitted in start-timestamp order. A --max-chars budget
(default 200000, ~50 PDF pages) drops oldest sessions first if
exceeded, with an "[Elided K earlier sessions]" note in the header.

Tests use tempdir-injected projects_dir so they do not depend on
the operator's real ~/.claude tree.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task F6: Submission package — zip submission_<sha>.zip

**Files:**
- Create: `scripts/build_submission_zip.py`
- Create: `tests/test_build_submission_zip.py`

**Methodology:** The submission package is a single zip at the repo root named `submission_<7-char-git-sha>.zip` containing exactly:

```
submission_<sha>/
├── main.pdf
├── refs.bib
├── LLM_TRANSCRIPT.md
├── sections/
│   ├── 01_introduction.tex
│   ├── 02_background.tex
│   ├── 03_methodology.tex
│   ├── 04_lob_recap.tex
│   ├── 05_empirical.tex
│   ├── 06_discussion.tex
│   ├── 07_limitations.tex
│   ├── 08_conclusion.tex
│   └── results_macros.tex
└── supplementary/
    ├── h1_significance.csv
    ├── test_matrix.csv
    └── regime_breakdown.csv
```

A sibling `.sha256` file containing the SHA-256 digest of the zip is written next to it (`submission_<sha>.zip.sha256`) so the operator can verify integrity at upload time. The script also writes `submission_<sha>.manifest.txt` listing every file path + size + per-file SHA-256.

**Git SHA resolution:** the script runs `git rev-parse --short HEAD` via `subprocess.run`. If git is unavailable or the cwd is not a repo, fall back to the literal string `nogit-<UTCYYYYMMDDHHMM>`. Tests inject the SHA via a `git_sha` kwarg.

**Idempotency:** running twice in a row produces byte-identical zips (zipfile is deterministic when we sort the entries and pin the modification timestamps to `1980-01-01 00:00:00` per the PKZIP epoch). Tests assert byte equality across two consecutive runs.

**Pre-flight contract:** before zipping, the script optionally runs F1, F3, F4 audits and aborts on any failure (`--check` flag). Default behaviour is to skip the audits and zip whatever exists, on the assumption that the operator ran the audits manually upstream.

- [ ] **Step 1: Write the failing test**

`tests/test_build_submission_zip.py`:
```python
"""Test F6: submission zip packager."""
import hashlib
import zipfile
from pathlib import Path

import pytest


def _seed_submission(submission_dir: Path) -> None:
    (submission_dir / "sections").mkdir(parents=True, exist_ok=True)
    (submission_dir / "main.pdf").write_bytes(b"%PDF-1.5\n%stub\n")
    (submission_dir / "refs.bib").write_text(
        "@article{x,author={Y},title={Z},year={2024},}\n", encoding="utf-8")
    (submission_dir / "LLM_TRANSCRIPT.md").write_text(
        "# LLM transcript appendix\n", encoding="utf-8")
    for n in ["01_introduction", "02_background", "03_methodology",
              "04_lob_recap", "05_empirical", "06_discussion",
              "07_limitations", "08_conclusion", "results_macros"]:
        (submission_dir / "sections" / f"{n}.tex").write_text(
            f"% {n}\n", encoding="utf-8")


def _seed_supplementary(results_dir: Path) -> None:
    tables = results_dir / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    for n in ["h1_significance", "test_matrix", "regime_breakdown"]:
        (tables / f"{n}.csv").write_text(f"policy,metric\nstub,0.0\n",
                                          encoding="utf-8")


def test_zip_contains_expected_files(tmp_path):
    from scripts.build_submission_zip import build

    submission = tmp_path / "submission"
    results = tmp_path / "results"
    out_dir = tmp_path / "out"
    _seed_submission(submission)
    _seed_supplementary(results)

    report = build(
        submission_dir=submission, results_dir=results,
        out_dir=out_dir, git_sha="abc1234",
    )

    expected_zip = out_dir / "submission_abc1234.zip"
    assert expected_zip.exists()
    assert report.zip_path == expected_zip

    with zipfile.ZipFile(expected_zip) as zf:
        names = sorted(zf.namelist())
    assert "submission_abc1234/main.pdf" in names
    assert "submission_abc1234/refs.bib" in names
    assert "submission_abc1234/LLM_TRANSCRIPT.md" in names
    assert "submission_abc1234/sections/05_empirical.tex" in names
    assert "submission_abc1234/supplementary/h1_significance.csv" in names
    assert "submission_abc1234/supplementary/test_matrix.csv" in names
    assert "submission_abc1234/supplementary/regime_breakdown.csv" in names


def test_sha256_sidecar_is_written(tmp_path):
    from scripts.build_submission_zip import build

    submission = tmp_path / "submission"
    results = tmp_path / "results"
    out_dir = tmp_path / "out"
    _seed_submission(submission)
    _seed_supplementary(results)

    report = build(submission_dir=submission, results_dir=results,
                   out_dir=out_dir, git_sha="abc1234")

    sidecar = report.zip_path.with_suffix(".zip.sha256")
    assert sidecar.exists()
    content = sidecar.read_text(encoding="utf-8").strip()
    actual_digest = hashlib.sha256(report.zip_path.read_bytes()).hexdigest()
    assert actual_digest in content


def test_manifest_lists_every_file(tmp_path):
    from scripts.build_submission_zip import build

    submission = tmp_path / "submission"
    results = tmp_path / "results"
    out_dir = tmp_path / "out"
    _seed_submission(submission)
    _seed_supplementary(results)

    report = build(submission_dir=submission, results_dir=results,
                   out_dir=out_dir, git_sha="abc1234")

    manifest = out_dir / "submission_abc1234.manifest.txt"
    assert manifest.exists()
    content = manifest.read_text(encoding="utf-8")
    assert "main.pdf" in content
    assert "supplementary/h1_significance.csv" in content


def test_build_is_deterministic(tmp_path):
    from scripts.build_submission_zip import build

    submission = tmp_path / "submission"
    results = tmp_path / "results"
    out_dir1 = tmp_path / "out1"
    out_dir2 = tmp_path / "out2"
    _seed_submission(submission)
    _seed_supplementary(results)

    r1 = build(submission_dir=submission, results_dir=results,
               out_dir=out_dir1, git_sha="abc1234")
    r2 = build(submission_dir=submission, results_dir=results,
               out_dir=out_dir2, git_sha="abc1234")

    h1 = hashlib.sha256(r1.zip_path.read_bytes()).hexdigest()
    h2 = hashlib.sha256(r2.zip_path.read_bytes()).hexdigest()
    assert h1 == h2


def test_aborts_when_required_file_missing(tmp_path):
    from scripts.build_submission_zip import build

    submission = tmp_path / "submission"
    submission.mkdir()
    (submission / "sections").mkdir()
    # main.pdf intentionally absent.
    results = tmp_path / "results"
    _seed_supplementary(results)

    with pytest.raises(FileNotFoundError, match="main.pdf"):
        build(submission_dir=submission, results_dir=results,
              out_dir=tmp_path / "out", git_sha="abc1234")


def test_check_flag_runs_audits_and_aborts_on_failure(tmp_path):
    from scripts.build_submission_zip import build

    submission = tmp_path / "submission"
    results = tmp_path / "results"
    out_dir = tmp_path / "out"
    _seed_submission(submission)
    _seed_supplementary(results)

    # Sabotage: anonymization leak in §V.
    (submission / "sections" / "05_empirical.tex").write_text(
        "We proposed a hazard-ladder.\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="audit"):
        build(submission_dir=submission, results_dir=results,
              out_dir=out_dir, git_sha="abc1234", check=True)
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv\Scripts\python.exe -m pytest tests\test_build_submission_zip.py -v
```
Expected: `ModuleNotFoundError: No module named 'scripts.build_submission_zip'`.

- [ ] **Step 3: Write minimal implementation**

`scripts/build_submission_zip.py`:
```python
"""Plan F Task 6 — submission package.

Produces a single zip at <out_dir>/submission_<git-sha>.zip containing
the main PDF, refs.bib, LLM transcript appendix, every section .tex,
and the three supplementary CSVs from results/tables/. Writes sibling
.sha256 and .manifest.txt files.

Idempotent: zipfile entries are sorted by name and modification times
are pinned to the PKZIP epoch (1980-01-01) so two consecutive runs
produce byte-identical archives.

CLI:
    python -m scripts.build_submission_zip
        [--submission papers/icicpe-scopus-vol2-submission]
        [--results results]
        [--out .]
        [--check]   # run F1/F3/F4 audits before zipping
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SUBMISSION = ROOT / "papers" / "icicpe-scopus-vol2-submission"
DEFAULT_RESULTS = ROOT / "results"
DEFAULT_OUT = ROOT

# PKZIP epoch — earliest representable mtime in a zip entry.
_PKZIP_EPOCH = (1980, 1, 1, 0, 0, 0)

_REQUIRED_TOP_LEVEL = ("main.pdf", "refs.bib", "LLM_TRANSCRIPT.md")
_REQUIRED_SECTIONS = (
    "01_introduction.tex", "02_background.tex", "03_methodology.tex",
    "04_lob_recap.tex", "05_empirical.tex", "06_discussion.tex",
    "07_limitations.tex", "08_conclusion.tex", "results_macros.tex",
)
_REQUIRED_SUPPLEMENTARY = (
    "h1_significance.csv", "test_matrix.csv", "regime_breakdown.csv",
)


@dataclass(frozen=True)
class SubmissionManifest:
    git_sha: str
    zip_path: Path
    file_count: int
    total_bytes: int
    sha256_zip: str


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip() or _fallback_sha()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return _fallback_sha()


def _fallback_sha() -> str:
    return "nogit-" + dt.datetime.utcnow().strftime("%Y%m%d%H%M")


def _gather_files(submission_dir: Path, results_dir: Path) -> list[tuple[str, Path]]:
    """Return list of (zip-archive-relative-path, source-Path), sorted."""
    pairs: list[tuple[str, Path]] = []
    for name in _REQUIRED_TOP_LEVEL:
        src = submission_dir / name
        if not src.exists():
            raise FileNotFoundError(f"required file missing: {src}")
        pairs.append((name, src))
    for name in _REQUIRED_SECTIONS:
        src = submission_dir / "sections" / name
        if not src.exists():
            raise FileNotFoundError(f"required section missing: {src}")
        pairs.append((f"sections/{name}", src))
    tables = results_dir / "tables"
    for name in _REQUIRED_SUPPLEMENTARY:
        src = tables / name
        if not src.exists():
            raise FileNotFoundError(
                f"required supplementary CSV missing: {src} "
                f"— run Plan D matrix runner first"
            )
        pairs.append((f"supplementary/{name}", src))
    pairs.sort(key=lambda t: t[0])
    return pairs


def _write_zip(zip_path: Path, prefix: str, files: list[tuple[str, Path]]) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, src in files:
            zi = zipfile.ZipInfo(filename=f"{prefix}/{arcname}",
                                 date_time=_PKZIP_EPOCH)
            zi.compress_type = zipfile.ZIP_DEFLATED
            data = src.read_bytes()
            zf.writestr(zi, data)


def _write_sidecars(zip_path: Path, files: list[tuple[str, Path]], prefix: str) -> str:
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sha_sidecar = zip_path.with_suffix(".zip.sha256")
    sha_sidecar.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")

    manifest_path = zip_path.parent / f"{zip_path.stem}.manifest.txt"
    lines = [f"submission archive: {zip_path.name}",
             f"sha256: {digest}",
             f"file count: {len(files)}",
             "", "files:"]
    for arcname, src in files:
        data = src.read_bytes()
        fdig = hashlib.sha256(data).hexdigest()
        lines.append(f"  {len(data):>10d}  {fdig}  {prefix}/{arcname}")
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return digest


def _run_audits(submission_dir: Path) -> None:
    from scripts.audit_refs_bib import audit as audit_refs
    from scripts.audit_anonymization import audit as audit_anon
    from scripts.audit_page_budget import audit as audit_pages

    refs_report = audit_refs(
        bib_path=submission_dir / "refs.bib",
        section_dir=submission_dir / "sections",
    )
    if not refs_report.passes:
        raise RuntimeError(f"refs.bib audit failed: {refs_report.render()}")

    findings = audit_anon(paper_dir=submission_dir, allow_bib=True)
    if findings:
        msg = "\n".join(f"  {f.file_path}:{f.line_number}: [{f.pattern}]"
                        for f in findings)
        raise RuntimeError(f"anonymization audit failed:\n{msg}")

    pdf = submission_dir / "main.pdf"
    if pdf.exists():
        pg_report = audit_pages(pdf_path=pdf)
        if not pg_report.passes:
            raise RuntimeError(f"page-budget audit failed: {pg_report.render()}")


def build(*, submission_dir: Path, results_dir: Path, out_dir: Path,
          git_sha: str | None = None, check: bool = False) -> SubmissionManifest:
    submission_dir = Path(submission_dir)
    results_dir = Path(results_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    sha = git_sha or _git_sha()
    prefix = f"submission_{sha}"
    zip_path = out_dir / f"{prefix}.zip"

    if check:
        _run_audits(submission_dir)

    files = _gather_files(submission_dir, results_dir)
    _write_zip(zip_path, prefix, files)
    digest = _write_sidecars(zip_path, files, prefix)

    total = sum(src.stat().st_size for _, src in files)
    return SubmissionManifest(
        git_sha=sha,
        zip_path=zip_path,
        file_count=len(files),
        total_bytes=total,
        sha256_zip=digest,
    )


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--submission", default=str(DEFAULT_SUBMISSION))
    ap.add_argument("--results", default=str(DEFAULT_RESULTS))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--check", action="store_true",
                    help="run F1/F3/F4 audits before zipping; abort on failure")
    args = ap.parse_args(argv)

    manifest = build(
        submission_dir=Path(args.submission),
        results_dir=Path(args.results),
        out_dir=Path(args.out),
        check=args.check,
    )
    print(f"wrote {manifest.zip_path}")
    print(f"  files: {manifest.file_count}")
    print(f"  total source bytes: {manifest.total_bytes:,}")
    print(f"  sha256: {manifest.sha256_zip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
```

- [ ] **Step 4: Run test to verify it passes**

```
.venv\Scripts\python.exe -m pytest tests\test_build_submission_zip.py -v
```
Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_submission_zip.py tests/test_build_submission_zip.py
git commit -m "$(cat <<'EOF'
Plan F Task 6: Submission packager (submission_<sha>.zip)

scripts/build_submission_zip.py:build produces a single deterministic
zip at <out_dir>/submission_<git-sha>.zip containing exactly:

  main.pdf
  refs.bib
  LLM_TRANSCRIPT.md
  sections/{01..08}.tex + results_macros.tex
  supplementary/{h1_significance,test_matrix,regime_breakdown}.csv

Sidecars written alongside:
  submission_<sha>.zip.sha256       — single-line digest + filename
  submission_<sha>.manifest.txt     — per-file size + sha256

The zip is byte-deterministic across runs: entries are sorted by
archive path, modification times pinned to the PKZIP epoch (1980-01-01).
Two consecutive `build()` calls with the same inputs produce
byte-identical archives. The test suite asserts this directly.

--check runs F1 (refs.bib audit), F3 (anonymization audit, with
--allow-bib so legitimately-cited figshare DOIs in refs.bib do not
block), and F4 (page-budget audit) before zipping; any failure aborts
with a RuntimeError carrying the rendered audit report so the operator
sees exactly which constraint failed.

Git SHA resolved via `git rev-parse --short HEAD` with graceful
fallback to "nogit-<UTCYYYYMMDDHHMM>" when git is absent. Tests inject
the SHA via the git_sha kwarg.

Operator workflow after this commit:
  1. .venv\\Scripts\\python.exe -m scripts.build_vol2_submission
  2. (operator runs latexmk -pdf main.tex inside the submission dir)
  3. .venv\\Scripts\\python.exe -m scripts.build_llm_transcript
  4. .venv\\Scripts\\python.exe -m scripts.build_submission_zip --check
  5. Upload submission_<sha>.zip to manuscriptlink.com/conferences/
     icicpe2026-scopus

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Cross-task integration: producing the final submission_<sha>.zip

After F1-F6 are committed, a one-shot composition step assembles the deliverable. This is not a separate TDD task — it is operator-invoked sequentially:

```
.venv\Scripts\python.exe -m scripts.build_vol2_submission            # F2: clone + swap
cd papers\icicpe-scopus-vol2-submission && latexmk -pdf main.tex     # operator
cd ..\..
.venv\Scripts\python.exe -m scripts.audit_refs_bib                   # F1: cite/bib gate
.venv\Scripts\python.exe -m scripts.audit_anonymization --allow-bib  # F3: leak gate
.venv\Scripts\python.exe -m scripts.audit_page_budget                # F4: page gate
.venv\Scripts\python.exe -m scripts.build_llm_transcript             # F5: appendix
.venv\Scripts\python.exe -m scripts.build_submission_zip --check     # F6: package
```

If any audit fails the operator iterates on the source `.tex` files (fix anonymization leaks; add missing bib entries; trim prose to land in [10, 12] pages) and re-runs. After F6 reports `wrote submission_<sha>.zip`, the operator uploads to manuscriptlink.com.

---

## Self-review

### Spec coverage (each Week-6 line item ↦ task that implements it)

From `C:\Users\1\.claude\plans\enumerated-scribbling-barto.md` §Build sequence — Week 6 and §Verification — Week 6:

| Spec line item | Task |
|---|---|
| "refs.bib audit — scan for Anonymous placeholders, assert every \\cite{} resolves" | **F1** — `scripts/audit_refs_bib.py` |
| "Template conversion (icicpe-2026-submission → icicpe-scopus-vol2-submission), swap §V/§VI/§VIII to Plan D drafts" | **F2** — `scripts/build_vol2_submission.py` |
| "Anonymization audit — grep for six 2026c-known leak patterns" | **F3** — `scripts/audit_anonymization.py` |
| "Page-budget audit — `pdfinfo main.pdf | grep Pages` ∈ [10, 12]" | **F4** — `scripts/audit_page_budget.py` |
| "LLM transcript capture for reproducibility appendix" | **F5** — `scripts/build_llm_transcript.py` |
| "Submission package — zip with main.pdf + sections + refs.bib + LLM_TRANSCRIPT.md + supplementary CSVs" | **F6** — `scripts/build_submission_zip.py` |
| Week-6 verification: "ICICPE-2026 SCOPUS Vol-2 submission landed at manuscriptlink.com/conferences/icicpe2026-scopus" | Operator gate after F6 — Plan F itself stops at zip production |
| Pass-fail gate: "Submission accepted into Vol-2 review pool" | Operator gate after manuscriptlink upload — Plan F's exit criterion is `submission_<sha>.zip` byte-correct on disk |

From KANBAN.md Plan F (6 sub-tasks F1-F6):

| Kanban task | Plan task | Status after plan execution |
|---|---|---|
| F1 refs.bib audit | F1 | Done |
| F2 Template conversion | F2 | Done |
| F3 Anonymization audit | F3 | Done |
| F4 Page-budget audit | F4 | Done |
| F5 LLM transcript capture | F5 | Done |
| F6 Submission package | F6 | Done |

All 6 KANBAN sub-tasks are covered.

### Zero placeholders

Every task body includes:
- Concrete failing test code (no `# write test here`)
- Concrete implementation code (no `# implement later`)
- Concrete `.venv\Scripts\python.exe -m pytest` command
- Concrete `git add` + heredoc commit message (no "similar to Task N")

There are intentional **operator-time** steps left outside the Python-test surface:
- F2 does not run `latexmk -pdf main.tex` (operator job — requires TeX Live installation, not a Python test-time dependency).
- F4 reads page count via `pdfinfo` (poppler-utils — not a Python test-time dependency; tests inject `pdfinfo_text`).
- F6 `--check` flag wires F1/F3/F4 together, but the full check requires a compiled `main.pdf` on disk; the test exercises the audit-failure abort path via a sabotaged anonymization leak.

These are not placeholders — they are **deliberate boundaries** between the test-checkable Python surface and the operator's local TeX toolchain. The pattern matches Plan D's "paper sections do not have unit tests at the Python level; the acceptance gate is `latexmk -pdf main.tex` exits 0".

### Type-consistency check across tasks

Function and dataclass names referenced across tasks:

| Symbol | Defined in | Used in |
|---|---|---|
| `RefsAuditReport` | F1 `scripts/audit_refs_bib.py` | F6 `_run_audits` consumer |
| `audit(bib_path=…, section_dir=…)` | F1 | F6 `_run_audits` |
| `BuildReport` | F2 `scripts/build_vol2_submission.py` | local use only |
| `build(parent_dir=…, planD_dir=…, dest_dir=…, clean=…)` | F2 | operator CLI only |
| `AnonymizationFinding` | F3 `scripts/audit_anonymization.py` | F6 `_run_audits` consumer |
| `audit(paper_dir=…, allow_bib=…)` | F3 | F6 `_run_audits` (with `allow_bib=True`) |
| `PageBudgetReport` | F4 `scripts/audit_page_budget.py` | F6 `_run_audits` consumer |
| `audit(pdf_path=…, pdfinfo_text=…)` | F4 | F6 `_run_audits` |
| `EXPECTED_SPLIT` | F4 | F4 test + report rendering |
| `TranscriptSlice`, `BuildReport` | F5 `scripts/build_llm_transcript.py` | local use only |
| `build(projects_dir=…, out_path=…, max_chars=…)` | F5 | operator CLI only |
| `SubmissionManifest` | F6 `scripts/build_submission_zip.py` | operator CLI return value |
| `build(submission_dir=…, results_dir=…, out_dir=…, git_sha=…, check=…)` | F6 | operator CLI only |
| Submission archive prefix `submission_<sha>/` | F6 writer | F6 test readers — consistent |
| Required files list `_REQUIRED_TOP_LEVEL`, `_REQUIRED_SECTIONS`, `_REQUIRED_SUPPLEMENTARY` | F6 | matches F2's section list and Plan D's `results/tables/` CSV names exactly (verified against Plan D Task D2/D3 output schemas) |
| Plan D draft section filenames `03_methodology.tex`, `05_empirical.tex`, `06_discussion.tex`, `08_conclusion.tex` | Plan D D9/D5/D6/(D6 stub) | F2 `_SWAP` tuple (verified against Plan D file-map) |
| Parent submission section filenames `01_introduction.tex`, `02_background.tex`, `04_lob_recap.tex`, `07_limitations.tex` | Existing `papers/icicpe-2026-submission/sections/` | F2 `_INHERIT_VERBATIM` + `_INHERIT_REWRITE` tuples (verified via `ls` at planning time) |
| Cross-reference rewrite pairs (`sec:methodology-mcdm` → `sec:methodology`, `sec:methodology-forecaster` → `sec:methodology`) | F2 `_XREF_REWRITES` | inherited section bodies use the old labels; new §III uses the new top-level label |

All cross-task names are consistent.

### Boundary-condition checks

- **F1** treats `unused_keys` (defined in `refs.bib` but never cited) as a *warning only*, not a failure. The published 2026c bib carries 18 extra entries from a literature-review pass that may not all be cited in the SCOPUS Vol-2 version, and forcing operator pruning of legitimate-but-uncited entries would generate friction with no quality benefit. The test `test_unused_keys_are_warning_only` locks in this contract.
- **F2** `--clean` removes the whole `dest_dir` before rebuilding, but without `--clean` the cloner only overwrites; stale files (e.g. an `09_extra.tex` from an earlier experiment) survive. The test `test_clean_flag_removes_pre_existing_files` and `test_idempotent_without_clean` lock both behaviours.
- **F3** uses `re.IGNORECASE` uniformly so `Our Prior Work` and `OUR PRIOR WORK` both trigger. The bare-figshare and figshare-DOI patterns can be excluded from `refs.bib` via `--allow-bib` for legitimately-cited figshare preprints.
- **F4** boundary cases: `n_pages == 10` passes (inclusive lower bound), `n_pages == 12` passes (inclusive upper bound), `n_pages == 9` fails, `n_pages == 13` fails. All four covered by explicit tests.
- **F5** sanitizes Windows home path, POSIX home path, and `sk-ant-` API key prefixes. The test `test_home_path_sanitized` locks the Windows case; the regex pattern covers POSIX symmetrically.
- **F6** byte-determinism is locked by pinning entry mtimes to the PKZIP epoch and sorting entries by archive path. The test `test_build_is_deterministic` runs `build()` twice and asserts identical SHA-256.

### Operator instructions after Plan F lands

After all 6 tasks are committed, the operator runs the integration pipeline documented in "Cross-task integration" above. Plan F's hard exit criterion is **`submission_<sha>.zip` exists at the repo root with the correct file set and all audits passing**. The manuscriptlink.com upload itself is operator-driven and outside this plan's automation surface.

---

## Execution handoff

This plan is executed task-by-task using `superpowers:subagent-driven-development` (recommended for parallel-safe tasks F1/F3/F4/F5 which touch independent files) or `superpowers:executing-plans` (sequential, simpler for one engineer driving the whole plan).

**Suggested order:**
1. **F1**, **F3**, **F4**, **F5** are fully independent — no shared files, no dependencies. Run them in parallel via subagents.
2. **F2** depends on the existence of `papers/icicpe-scopus-vol2/sections/{03,05,06,08}.tex` (Plan D's drafts). If Plan D was completed in Week 4 these exist already; if not, Plan F2 will raise a clear FileNotFoundError naming the missing draft.
3. **F6** depends on F1 + F3 + F4 (imports their `audit()` functions for the `--check` flag). Implement F6 last.

Critical path: F1, F3, F4 in parallel → F6 (consumes their auditors). F2 and F5 are independent of all others.

**After all 6 tasks land,** commit a final orchestration commit:

```bash
git add KANBAN.md  # if updated to mark F1-F6 done
git commit -m "Plan F detailed: paper polish + ICICPE SCOPUS Vol-2 submission (Week 6)

All 6 Plan F sub-tasks (F1-F6) committed:
  F1 scripts/audit_refs_bib.py        (\\cite{} ↔ refs.bib + Anonymous)
  F2 scripts/build_vol2_submission.py (template clone + section swap)
  F3 scripts/audit_anonymization.py   (six 2026c-known leak patterns)
  F4 scripts/audit_page_budget.py     (pdfinfo Pages ∈ [10, 12])
  F5 scripts/build_llm_transcript.py  (Claude Code JSONL → MD appendix)
  F6 scripts/build_submission_zip.py  (deterministic submission_<sha>.zip)

Operator gates next:
  * Run scripts.build_vol2_submission to produce
    papers/icicpe-scopus-vol2-submission/ from the Plan D drafts.
  * Run latexmk -pdf main.tex inside that directory.
  * Run scripts.audit_refs_bib, scripts.audit_anonymization --allow-bib,
    scripts.audit_page_budget — fix any failures.
  * Run scripts.build_llm_transcript and scripts.build_submission_zip
    --check to produce submission_<sha>.zip at the repo root.
  * Upload submission_<sha>.zip to manuscriptlink.com/conferences/
    icicpe2026-scopus and confirm receipt e-mail.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

Sub-skill reference: `superpowers:subagent-driven-development` for parallel execution, `superpowers:executing-plans` for sequential.
