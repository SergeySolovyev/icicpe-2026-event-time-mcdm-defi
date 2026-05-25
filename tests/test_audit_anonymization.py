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
