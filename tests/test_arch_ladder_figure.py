"""Plan D Task D9: Structural + compile tests for the v2 architecture
figure (T1 -> T2 -> T3 decision-policy ladder) of the SCOPUS Vol-2 paper.

Two layers of test:

1. Structural (no LaTeX needed): the TikZ source file exists, contains the
   expected nodes/labels/formulas, declares the right tikz libraries (or
   defers them to main.tex via a comment marker), and uses the canonical
   ``fig:t1t2t3-ladder`` label.

2. Compile-validate (skipped if ``latexmk`` is not on PATH): build a tiny
   standalone driver that ``\\input{}``s the figure and assert that
   ``latexmk -pdf`` exits 0 and produces a PDF.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIG_PATH = (
    ROOT
    / "papers"
    / "icicpe-scopus-vol2-submission"
    / "sections"
    / "03_arch_ladder.tex"
)
COMPILE_DRIVER = ROOT / "tests" / "_arch_ladder_compile_test.tex"


# ---------------------------------------------------------------------------
# Structural tests
# ---------------------------------------------------------------------------


def test_figure_file_exists() -> None:
    assert FIG_PATH.exists(), f"missing TikZ figure file: {FIG_PATH}"


def test_figure_has_tikz_environment() -> None:
    text = FIG_PATH.read_text(encoding="utf-8")
    assert "\\begin{tikzpicture}" in text
    assert "\\end{tikzpicture}" in text


def test_figure_has_figure_environment() -> None:
    text = FIG_PATH.read_text(encoding="utf-8")
    # Single-column [t]-placed figure per the v2 paper template; figure*
    # would push to full-width / two-column straddle which is not what we
    # want for a §III placement.
    assert "\\begin{figure}[t]" in text
    assert "\\end{figure}" in text


def test_figure_has_canonical_label() -> None:
    text = FIG_PATH.read_text(encoding="utf-8")
    assert "\\label{fig:t1t2t3-ladder}" in text


def test_figure_has_caption() -> None:
    text = FIG_PATH.read_text(encoding="utf-8")
    assert "\\caption{" in text


def test_figure_mentions_t1_t2_t3_tier_labels() -> None:
    text = FIG_PATH.read_text(encoding="utf-8")
    for label in ("T1", "T2", "T3"):
        assert label in text, f"missing decision-policy tier label {label!r}"


def test_figure_mentions_per_block_panel_and_blockstate() -> None:
    text = FIG_PATH.read_text(encoding="utf-8")
    assert "per\\_block\\_panel" in text or "per_block_panel" in text
    assert "BlockState" in text


def test_figure_mentions_event_replay_engine_and_action() -> None:
    text = FIG_PATH.read_text(encoding="utf-8")
    assert "EventReplay" in text
    assert "Action" in text


def test_figure_mentions_onnx_bridge_to_live_agent() -> None:
    text = FIG_PATH.read_text(encoding="utf-8")
    assert "ONNX" in text or "onnx" in text


def test_figure_mentions_t1_threshold_formula() -> None:
    text = FIG_PATH.read_text(encoding="utf-8")
    # E[dwell] * spread > gas  (T1 gas-aware threshold rule)
    assert "dwell" in text
    assert "spread" in text
    assert "gas" in text


def test_figure_mentions_t2_ou_bellman_threshold() -> None:
    text = FIG_PATH.read_text(encoding="utf-8")
    # S > S^*  from OU + Bellman
    assert "S^{*}" in text or "S^*" in text
    assert "OU" in text


def test_figure_mentions_t3_hazard_integral() -> None:
    text = FIG_PATH.read_text(encoding="utf-8")
    # \int_0^\infty E[spread(\tau)] (1 - F(\tau)) d\tau > gas
    assert "\\int_{0}^{\\infty}" in text or "\\int_0^{\\infty}" in text
    assert "F(\\tau)" in text or "1 - F" in text


def test_figure_declares_required_tikz_libraries() -> None:
    text = FIG_PATH.read_text(encoding="utf-8")
    # Either inline-declared in this section file, OR commented as a
    # preamble requirement for main.tex.
    required = ("positioning", "arrows.meta", "fit", "backgrounds", "calc")
    has_inline = "\\usetikzlibrary" in text and all(lib in text for lib in required)
    has_marker = "% requires tikzlibrary" in text and all(lib in text for lib in required)
    assert has_inline or has_marker, (
        "figure must either \\usetikzlibrary{positioning,arrows.meta,fit,"
        "backgrounds,calc} inline, or list those libraries in a "
        "'% requires tikzlibrary ...' comment for main.tex preamble"
    )


# ---------------------------------------------------------------------------
# Compile-validate test  (skipped if latexmk is not in PATH)
# ---------------------------------------------------------------------------


_LATEXMK = shutil.which("latexmk")


@pytest.mark.skipif(_LATEXMK is None, reason="latexmk not in PATH; skip compile check")
def test_figure_compiles_with_latexmk(tmp_path: Path) -> None:
    """Write a minimal standalone driver that \\input{}s the figure and
    compile it with ``latexmk -pdf``.  Assert exit 0 and that a PDF was
    produced.
    """
    driver = COMPILE_DRIVER
    rel_input = FIG_PATH.resolve().as_posix()
    driver.write_text(
        "\\documentclass[conference]{IEEEtran}\n"
        "\\usepackage{tikz}\n"
        "\\usetikzlibrary{positioning,arrows.meta,fit,backgrounds,calc}\n"
        "\\usepackage{amsmath,amssymb}\n"
        "\\usepackage{xcolor}\n"
        "\\begin{document}\n"
        f"\\input{{{rel_input}}}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )

    # Build in an isolated temp dir so we don't litter the repo with .aux
    # / .log / .pdf artefacts.
    env = os.environ.copy()
    result = subprocess.run(
        [
            _LATEXMK,
            "-pdf",
            "-interaction=nonstopmode",
            "-halt-on-error",
            f"-output-directory={tmp_path}",
            str(driver),
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )

    log_tail = (result.stdout or "") + "\n" + (result.stderr or "")
    assert result.returncode == 0, (
        f"latexmk failed (exit {result.returncode}).\n"
        f"--- last 2 KiB of output ---\n{log_tail[-2048:]}"
    )

    pdf = tmp_path / (driver.stem + ".pdf")
    assert pdf.exists() and pdf.stat().st_size > 0, (
        f"expected PDF at {pdf} but none / empty"
    )
