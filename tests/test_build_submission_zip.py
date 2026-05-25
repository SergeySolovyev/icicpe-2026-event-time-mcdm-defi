"""Test F6: submission zip packager."""
import hashlib
import zipfile
from pathlib import Path

import pytest


def _seed_submission(submission_dir: Path) -> None:
    (submission_dir / "sections").mkdir(parents=True, exist_ok=True)
    (submission_dir / "main.pdf").write_bytes(b"%PDF-1.5\n%stub\n")
    (submission_dir / "refs.bib").write_text(
        "@article{x,author={Y},title={Z},year={2024},}\n", encoding="utf-8"
    )
    (submission_dir / "LLM_TRANSCRIPT.md").write_text(
        "# LLM transcript appendix\n", encoding="utf-8"
    )
    for n in [
        "01_introduction", "02_background", "03_methodology",
        "04_lob_recap", "05_empirical", "06_cross_domain",
        "07_limitations", "08_conclusion", "results_macros",
    ]:
        (submission_dir / "sections" / f"{n}.tex").write_text(
            f"% {n}\n", encoding="utf-8"
        )


def _seed_supplementary(results_dir: Path) -> None:
    tables = results_dir / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    for n in ["h1_significance", "test_matrix", "regime_breakdown"]:
        (tables / f"{n}.csv").write_text(
            "policy,metric\nstub,0.0\n", encoding="utf-8"
        )


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
    assert "submission_abc1234/sections/06_cross_domain.tex" in names
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

    report = build(
        submission_dir=submission, results_dir=results,
        out_dir=out_dir, git_sha="abc1234",
    )

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

    build(
        submission_dir=submission, results_dir=results,
        out_dir=out_dir, git_sha="abc1234",
    )

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

    r1 = build(
        submission_dir=submission, results_dir=results,
        out_dir=out_dir1, git_sha="abc1234",
    )
    r2 = build(
        submission_dir=submission, results_dir=results,
        out_dir=out_dir2, git_sha="abc1234",
    )

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
        build(
            submission_dir=submission, results_dir=results,
            out_dir=tmp_path / "out", git_sha="abc1234",
        )


def test_check_flag_runs_audits_and_aborts_on_failure(tmp_path):
    from scripts.build_submission_zip import build

    submission = tmp_path / "submission"
    results = tmp_path / "results"
    out_dir = tmp_path / "out"
    _seed_submission(submission)
    _seed_supplementary(results)

    # Sabotage: anonymization leak in §V.
    (submission / "sections" / "05_empirical.tex").write_text(
        "We proposed a hazard-ladder.\n", encoding="utf-8"
    )

    with pytest.raises(RuntimeError, match="audit"):
        build(
            submission_dir=submission, results_dir=results,
            out_dir=out_dir, git_sha="abc1234", check=True,
        )


def test_manifest_includes_per_file_sha256(tmp_path):
    """Each line in the manifest must include a 64-hex sha256 of the source file."""
    from scripts.build_submission_zip import build

    submission = tmp_path / "submission"
    results = tmp_path / "results"
    out_dir = tmp_path / "out"
    _seed_submission(submission)
    _seed_supplementary(results)

    build(
        submission_dir=submission, results_dir=results,
        out_dir=out_dir, git_sha="abc1234",
    )

    manifest = (out_dir / "submission_abc1234.manifest.txt").read_text(
        encoding="utf-8"
    )
    # Compute expected sha256 of main.pdf and grep it.
    pdf_sha = hashlib.sha256(
        (submission / "main.pdf").read_bytes()
    ).hexdigest()
    assert pdf_sha in manifest
