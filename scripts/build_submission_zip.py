"""Plan F Task 6 -- submission package.

Produces a single zip at <out_dir>/submission_<git-sha>.zip containing
the main PDF, refs.bib, LLM transcript appendix, every section .tex,
and the three supplementary CSVs from results/tables/. Writes sibling
.sha256 and .manifest.txt files.

Idempotent: zipfile entries are sorted by name and modification times
are pinned to the PKZIP epoch (1980-01-01) so two consecutive runs
produce byte-identical archives.

Reality-adjusted from plan-doc: §VI lives at sections/06_cross_domain.tex
in the actual repo (Plan D D6 chose this filename over '06_discussion.tex').

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
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SUBMISSION = ROOT / "papers" / "icicpe-scopus-vol2-submission"
DEFAULT_RESULTS = ROOT / "results"
DEFAULT_OUT = ROOT

# PKZIP epoch -- earliest representable mtime in a zip entry.
_PKZIP_EPOCH = (1980, 1, 1, 0, 0, 0)

_REQUIRED_TOP_LEVEL = ("main.pdf", "refs.bib", "LLM_TRANSCRIPT.md")
_REQUIRED_SECTIONS = (
    "01_introduction.tex",
    "02_background.tex",
    "03_methodology.tex",
    "04_lob_recap.tex",
    "05_empirical.tex",
    "06_cross_domain.tex",  # reality-adjusted from plan-doc's 06_discussion
    "07_limitations.tex",
    "08_conclusion.tex",
    "results_macros.tex",
)
_REQUIRED_SUPPLEMENTARY = (
    "h1_significance.csv",
    "test_matrix.csv",
    "regime_breakdown.csv",
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
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip() or _fallback_sha()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return _fallback_sha()


def _fallback_sha() -> str:
    return "nogit-" + dt.datetime.utcnow().strftime("%Y%m%d%H%M")


def _gather_files(
    submission_dir: Path, results_dir: Path
) -> list[tuple[str, Path]]:
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
                f"-- run Plan D matrix runner first"
            )
        pairs.append((f"supplementary/{name}", src))
    pairs.sort(key=lambda t: t[0])
    return pairs


def _write_zip(
    zip_path: Path, prefix: str, files: list[tuple[str, Path]]
) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, src in files:
            zi = zipfile.ZipInfo(
                filename=f"{prefix}/{arcname}", date_time=_PKZIP_EPOCH
            )
            zi.compress_type = zipfile.ZIP_DEFLATED
            data = src.read_bytes()
            zf.writestr(zi, data)


def _write_sidecars(
    zip_path: Path, files: list[tuple[str, Path]], prefix: str
) -> str:
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sha_sidecar = zip_path.with_suffix(".zip.sha256")
    sha_sidecar.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")

    manifest_path = zip_path.parent / f"{zip_path.stem}.manifest.txt"
    lines = [
        f"submission archive: {zip_path.name}",
        f"sha256: {digest}",
        f"file count: {len(files)}",
        "",
        "files:",
    ]
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
        msg = "\n".join(
            f"  {f.file_path}:{f.line_number}: [{f.pattern}]" for f in findings
        )
        raise RuntimeError(f"anonymization audit failed:\n{msg}")

    pdf = submission_dir / "main.pdf"
    if pdf.exists():
        pg_report = audit_pages(pdf_path=pdf)
        if not pg_report.passes:
            raise RuntimeError(
                f"page-budget audit failed: {pg_report.render()}"
            )


def build(
    *,
    submission_dir: Path,
    results_dir: Path,
    out_dir: Path,
    git_sha: str | None = None,
    check: bool = False,
) -> SubmissionManifest:
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
    ap.add_argument(
        "--check",
        action="store_true",
        help="run F1/F3/F4 audits before zipping; abort on failure",
    )
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
    sys.exit(_main())
