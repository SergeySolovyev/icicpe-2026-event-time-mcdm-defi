"""Substitute real backtest numbers into ``whitepaper/sections/09_results.tex``.

This script reads three CSV artifacts produced by the backtest pipeline:

    results/tables/main.csv             -- per-strategy summary (run_main.py /
                                            run_baselines.py output)
    results/tables/ablations.csv        -- 15-row ablation matrix
    results/tables/h1_significance.csv  -- bootstrap H1 test (one row, columns
                                            p_value, ci_low, ci_high,
                                            sharpe_delta)

and rewrites every ``\\newcommand{\\NAME}{...}`` line in the .tex file in place
with the corresponding real number.

The mapping from macro name to (CSV file, row filter, column) is the
:data:`MAPPING` dict at module top: it is the SINGLE source of truth and is
exhaustively validated against the macros actually defined in the .tex file.
Any macro defined in the .tex that has no entry in MAPPING -- or any macro in
MAPPING that does not appear in the .tex -- is treated as a fatal error so
the developer adds the rule before running the substitution.

After substitution, the script asserts that no ``XX.XX\\%`` placeholder
remains in the file, also as a fatal error.

CLI::

    python scripts/fill_whitepaper_results.py           # rewrite in place
    python scripts/fill_whitepaper_results.py --dry-run # report-only
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
TEX_PATH = ROOT / "whitepaper" / "sections" / "09_results.tex"
TABLES_DIR = ROOT / "results" / "tables"

MAIN_CSV = TABLES_DIR / "main.csv"
ABLATIONS_CSV = TABLES_DIR / "ablations.csv"
H1_CSV = TABLES_DIR / "h1_significance.csv"

# Defense deck shares the SAME \newcommand contract. Populated additively
# from the same MAPPING/new_values so the slides auto-update with the paper.
# No-op if absent (whitepaper path is unaffected either way).
SLIDES_MACROS_PATH = ROOT / "slides" / "results_macros.tex"

# Sentinel still present in unfilled cells.
PLACEHOLDER_TOKEN = r"XX.XX\%"

# ---------------------------------------------------------------------------
# Mapping: macro_name -> (csv_kind, row_filter, column, formatter)
# ---------------------------------------------------------------------------
# csv_kind     :: one of "main", "ablations", "h1"
# row_filter   :: dict of column->value used to select exactly one row
#                 (empty {} means "single-row file", e.g. h1_significance.csv)
# column       :: column of the selected row to extract the value from
# formatter    :: "pct" -> "{:.2f}\\%"  (value already in %, e.g. APY=12.3)
#                 "pct_from_unit" -> multiply by 100 then "{:.2f}\\%"
#                 "raw" -> "{:.2f}\\%" verbatim (Sharpe, Calmar etc.)
#                 "raw_no_pct" -> "{:.2f}" (Sharpe printed without %; we still
#                                emit \% because every newcommand defaults to
#                                XX.XX\% -> downstream prose is consistent)
#                 "money" -> "{:.0f}\\%"
# ---------------------------------------------------------------------------

# Column names below match the ACTUAL backtest CSV schemas (run_main.py /
# run_ablations.py): main.csv -> net_apy/sharpe_annual/max_drawdown/
# turnover_per_month/calmar/gas_spent_usd; h1_significance.csv -> delta/
# bootstrap_p_value/ci_low/ci_high. The baseline strategies (BuyAndHold,
# APYGreedy, CIRMCDM) are NOT in main.csv under `make finish` (which runs
# only run_main + run_ablations, not run_baselines); their equivalents live
# in ablations.csv: BuyAndHold == single_protocol[AAVE] (10a), APYGreedy ==
# greedy_on_forecast (11a), CIRMCDM == cir_forecast (3). Sourcing them from
# ablations keeps the documented finish workflow self-consistent.
MAPPING: Dict[str, Tuple[str, Dict[str, str], str, str]] = {
    # --- Headline H1 test ---
    "PredictiveAPY":     ("main", {"strategy": "PredictiveMCDM"}, "net_apy",       "pct_from_unit"),
    "EMAAPY":            ("main", {"strategy": "MCDMEMA"},        "net_apy",       "pct_from_unit"),
    "PredictiveSharpe":  ("main", {"strategy": "PredictiveMCDM"}, "sharpe_annual", "raw"),
    "EMASharpe":         ("main", {"strategy": "MCDMEMA"},        "sharpe_annual", "raw"),
    "SharpeDelta":       ("h1",   {},                              "delta",        "raw"),
    "BootstrapPvalue":   ("h1",   {},                              "bootstrap_p_value", "raw"),
    "BootstrapCILow":    ("h1",   {},                              "ci_low",       "raw"),
    "BootstrapCIHigh":   ("h1",   {},                              "ci_high",      "raw"),

    # --- Per-strategy table: 5 strategies x 6 metrics ---
    "BuyholdAPY":        ("ablations", {"ablation_id": "10a"},      "net_apy",       "pct_from_unit"),
    "BuyholdSharpe":     ("ablations", {"ablation_id": "10a"},      "sharpe_annual", "raw"),
    "BuyholdDD":         ("ablations", {"ablation_id": "10a"},      "max_drawdown",  "pct_from_unit"),
    "BuyholdCalmar":     ("ablations", {"ablation_id": "10a"},      "calmar",        "raw"),
    "BuyholdTurnover":   ("ablations", {"ablation_id": "10a"},      "turnover_per_month", "raw"),
    "BuyholdGas":        ("ablations", {"ablation_id": "10a"},      "gas_spent_usd", "money"),
    "GreedyAPY":         ("ablations", {"ablation_id": "11a"},      "net_apy",       "pct_from_unit"),
    "GreedySharpe":      ("ablations", {"ablation_id": "11a"},      "sharpe_annual", "raw"),
    "GreedyDD":          ("ablations", {"ablation_id": "11a"},      "max_drawdown",  "pct_from_unit"),
    "GreedyCalmar":      ("ablations", {"ablation_id": "11a"},      "calmar",        "raw"),
    "GreedyTurnover":    ("ablations", {"ablation_id": "11a"},      "turnover_per_month", "raw"),
    "GreedyGas":         ("ablations", {"ablation_id": "11a"},      "gas_spent_usd", "money"),
    "EMADD":             ("main", {"strategy": "MCDMEMA"},        "max_drawdown",  "pct_from_unit"),
    "EMACalmar":         ("main", {"strategy": "MCDMEMA"},        "calmar",        "raw"),
    "EMATurnover":       ("main", {"strategy": "MCDMEMA"},        "turnover_per_month", "raw"),
    "EMAGas":            ("main", {"strategy": "MCDMEMA"},        "gas_spent_usd", "money"),
    "CIRAPY":            ("ablations", {"ablation_id": "3"},        "net_apy",       "pct_from_unit"),
    "CIRSharpe":         ("ablations", {"ablation_id": "3"},        "sharpe_annual", "raw"),
    "CIRDD":             ("ablations", {"ablation_id": "3"},        "max_drawdown",  "pct_from_unit"),
    "CIRCalmar":         ("ablations", {"ablation_id": "3"},        "calmar",        "raw"),
    "CIRTurnover":       ("ablations", {"ablation_id": "3"},        "turnover_per_month", "raw"),
    "CIRGas":            ("ablations", {"ablation_id": "3"},        "gas_spent_usd", "money"),
    "PredictiveDD":      ("main", {"strategy": "PredictiveMCDM"}, "max_drawdown",  "pct_from_unit"),
    "PredictiveCalmar":  ("main", {"strategy": "PredictiveMCDM"}, "calmar",        "raw"),
    "PredictiveTurnover":("main", {"strategy": "PredictiveMCDM"}, "turnover_per_month", "raw"),
    "PredictiveGas":     ("main", {"strategy": "PredictiveMCDM"}, "gas_spent_usd", "money"),
}

# --- 15-ablation mapping is built procedurally (45 entries) ---
# ablation_id N maps to the canonical primary sub-row: ablations 9-12 split
# into a/b variants (run_ablations.py) where the "a" row is the headline
# case (tuned / single-protocol-Aave / greedy / realistic-gas); ids 1-8 and
# 13-15 are plain. Delta is computed in fill() as net_apy minus ablation-1's
# net_apy (the `delta_vs_abl1` quantity run_ablations prints in its markdown
# table) -- there is no such CSV column, and deriving it here avoids
# re-running the ablation battery just to persist a trivially-derived value.
_ABLATION_ORDINALS = [
    "One", "Two", "Three", "Four", "Five",
    "Six", "Seven", "Eight", "Nine", "Ten",
    "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen",
]
_ABLATION_ID_FOR_ORDINAL = {
    9: "9a", 10: "10a", 11: "11a", 12: "12a",
}
for _idx, _word in enumerate(_ABLATION_ORDINALS, start=1):
    _abl_id = _ABLATION_ID_FOR_ORDINAL.get(_idx, str(_idx))
    _filter = {"ablation_id": _abl_id}
    MAPPING[f"Ablation{_word}APY"]    = ("ablations", _filter, "net_apy",       "pct_from_unit")
    MAPPING[f"Ablation{_word}Sharpe"] = ("ablations", _filter, "sharpe_annual", "raw")
    MAPPING[f"Ablation{_word}Delta"]  = ("ablations", _filter, "net_apy",       "delta_vs_abl1")

# --- Regime-conditional (Q1 + Q2 of 2026 test window) ---
MAPPING["QOneSharpePred"] = ("ablations", {"ablation_id": "regime_q1_pred"}, "sharpe_annual", "raw")
MAPPING["QOneAPYPred"]    = ("ablations", {"ablation_id": "regime_q1_pred"}, "net_apy",       "pct_from_unit")
MAPPING["QOneSharpeEMA"]  = ("ablations", {"ablation_id": "regime_q1_ema"},  "sharpe_annual", "raw")
MAPPING["QOneAPYEMA"]     = ("ablations", {"ablation_id": "regime_q1_ema"},  "net_apy",       "pct_from_unit")
MAPPING["QTwoSharpePred"] = ("ablations", {"ablation_id": "regime_q2_pred"}, "sharpe_annual", "raw")
MAPPING["QTwoAPYPred"]    = ("ablations", {"ablation_id": "regime_q2_pred"}, "net_apy",       "pct_from_unit")
MAPPING["QTwoSharpeEMA"]  = ("ablations", {"ablation_id": "regime_q2_ema"},  "sharpe_annual", "raw")
MAPPING["QTwoAPYEMA"]     = ("ablations", {"ablation_id": "regime_q2_ema"},  "net_apy",       "pct_from_unit")

# --- Forecast quality (one synthetic row in ablations.csv) ---
MAPPING["ForecastRsq"]       = ("ablations", {"ablation_id": "forecast_quality"}, "oos_r2",       "raw")
MAPPING["ForecastDirAcc"]    = ("ablations", {"ablation_id": "forecast_quality"}, "dir_acc",      "pct_from_unit")
MAPPING["ForecastWPearson"]  = ("ablations", {"ablation_id": "forecast_quality"}, "w_pearson",    "raw")
MAPPING["ForecastQNineLoss"] = ("ablations", {"ablation_id": "forecast_quality"}, "q90_loss",     "raw")


# ---------------------------------------------------------------------------
# Loaders + formatting helpers
# ---------------------------------------------------------------------------

def _load_csv(path: Path, kind: str) -> pd.DataFrame:
    """Load one of the input CSVs, failing loudly if missing or empty."""
    if not path.exists():
        raise FileNotFoundError(
            f"[fill_whitepaper_results] required CSV missing: {path}\n"
            f"  -> generate it via the relevant backtest stage "
            f"(see PROJECT_2_PLAN.md sec. 9 / sec. 10 for the {kind!r} schema)."
        )
    df = pd.read_csv(path)
    if df.empty:
        raise ValueError(f"[fill_whitepaper_results] CSV is empty: {path}")
    return df


def _format(value: float, formatter: str) -> str:
    """Format a single numeric value into a LaTeX-safe substitution string."""
    if pd.isna(value):
        return r"\textit{n/a}"
    if formatter == "pct":
        return f"{float(value):.2f}\\%"
    if formatter == "pct_from_unit":
        return f"{float(value) * 100.0:.2f}\\%"
    if formatter == "raw":
        # Even Sharpe/Calmar use \% suffix so the prose remains consistent
        # with the placeholder default ("XX.XX\%"). Substituted strings end
        # in \\% so they typeset as e.g. "1.37\%" -- imperfect for Sharpe but
        # matches the template's default style. Whitepaper prose around these
        # macros should be authored accordingly.
        return f"{float(value):.2f}"
    if formatter == "raw_no_pct":
        return f"{float(value):.2f}"
    if formatter == "money":
        return f"{float(value):.0f}"
    raise ValueError(f"unknown formatter {formatter!r}")


def _lookup(df: pd.DataFrame, row_filter: Dict[str, str], column: str,
            macro: str, csv_label: str) -> float:
    """Pull a single value out of a DataFrame, failing loudly if ambiguous."""
    sub = df
    for col, val in row_filter.items():
        if col not in sub.columns:
            raise KeyError(
                f"[fill_whitepaper_results] macro {macro!r}: column {col!r} "
                f"not present in {csv_label}.csv (columns: {list(sub.columns)})"
            )
        sub = sub[sub[col].astype(str) == str(val)]
    if sub.empty:
        raise LookupError(
            f"[fill_whitepaper_results] macro {macro!r}: no row in "
            f"{csv_label}.csv matches filter {row_filter}"
        )
    if len(sub) > 1:
        raise LookupError(
            f"[fill_whitepaper_results] macro {macro!r}: filter "
            f"{row_filter} matched {len(sub)} rows in {csv_label}.csv "
            f"(expected exactly one)"
        )
    if column not in sub.columns:
        raise KeyError(
            f"[fill_whitepaper_results] macro {macro!r}: column {column!r} "
            f"not in {csv_label}.csv (columns: {list(sub.columns)})"
        )
    return float(sub.iloc[0][column])


# ---------------------------------------------------------------------------
# Tex-file scanning
# ---------------------------------------------------------------------------

# Matches \newcommand{\Foo}{...} on a single line. Group(1) is the macro name,
# group(2) is the current value (which we replace).
_NEWCMD_RE = re.compile(r"\\newcommand\{\\([A-Za-z]+)\}\{([^}]*)\}")


def _scan_macros(tex_text: str) -> List[Tuple[str, str]]:
    """Return [(macro_name, current_default)] in document order."""
    return [(m.group(1), m.group(2)) for m in _NEWCMD_RE.finditer(tex_text)]


def _validate_mapping_against_tex(tex_macros: List[str]) -> None:
    """Fail loudly if MAPPING and the .tex disagree on the macro set."""
    tex_set = set(tex_macros)
    map_set = set(MAPPING.keys())

    only_in_tex = sorted(tex_set - map_set)
    only_in_map = sorted(map_set - tex_set)
    errs: List[str] = []
    if only_in_tex:
        errs.append(
            f"macros defined in .tex but missing from MAPPING ({len(only_in_tex)}): "
            + ", ".join(only_in_tex)
        )
    if only_in_map:
        errs.append(
            f"macros in MAPPING but absent from .tex ({len(only_in_map)}): "
            + ", ".join(only_in_map)
        )
    if errs:
        raise RuntimeError("[fill_whitepaper_results] mapping mismatch:\n  - " +
                           "\n  - ".join(errs))


# ---------------------------------------------------------------------------
# Substitution
# ---------------------------------------------------------------------------

def fill(dry_run: bool = False) -> int:
    """Run the substitution. Returns number of macros replaced."""
    # 1. Read .tex
    if not TEX_PATH.exists():
        raise FileNotFoundError(f"template missing: {TEX_PATH}")
    tex_text = TEX_PATH.read_text(encoding="utf-8")

    tex_macros = [name for name, _ in _scan_macros(tex_text)]
    _validate_mapping_against_tex(tex_macros)

    # 2. Load CSVs (only the ones actually referenced by MAPPING)
    used_kinds = {kind for kind, _, _, _ in MAPPING.values()}
    frames: Dict[str, pd.DataFrame] = {}
    if "main" in used_kinds:
        frames["main"] = _load_csv(MAIN_CSV, "main")
    if "ablations" in used_kinds:
        frames["ablations"] = _load_csv(ABLATIONS_CSV, "ablations")
    if "h1" in used_kinds:
        frames["h1"] = _load_csv(H1_CSV, "h1")

    # 3. Resolve every macro's new value.
    #    `delta_vs_abl1` is a derived formatter: value minus ablation-1's
    #    net_apy (run_ablations' `delta_vs_abl1` quantity; no CSV column).
    abl1_net_apy: Optional[float] = None
    if "ablations" in frames:
        try:
            abl1_net_apy = _lookup(
                frames["ablations"], {"ablation_id": "1"}, "net_apy",
                "<delta_vs_abl1 baseline>", "ablations",
            )
        except (KeyError, LookupError):
            abl1_net_apy = None

    new_values: Dict[str, str] = {}
    print(f"[fill_whitepaper_results] resolving {len(MAPPING)} macros...")
    for macro, (kind, row_filter, column, formatter) in MAPPING.items():
        df = frames[kind]
        raw = _lookup(df, row_filter, column, macro, kind)
        if formatter == "delta_vs_abl1":
            if abl1_net_apy is None or pd.isna(raw):
                new_values[macro] = _format(float("nan"), "pct_from_unit")
            else:
                new_values[macro] = _format(raw - abl1_net_apy, "pct_from_unit")
            continue
        new_values[macro] = _format(raw, formatter)

    # 4. Apply substitutions and emit per-line diffs
    substituted = 0
    new_lines: List[str] = []
    for line in tex_text.splitlines(keepends=True):
        match = _NEWCMD_RE.search(line)
        if match is None:
            new_lines.append(line)
            continue
        macro = match.group(1)
        if macro not in new_values:
            new_lines.append(line)
            continue
        old_val = match.group(2)
        new_val = new_values[macro]
        new_line = (
            line[: match.start(2)] + new_val + line[match.end(2) :]
        )
        new_lines.append(new_line)
        substituted += 1
        print(f"  {macro:24s}  {old_val!r:>16s}  ->  {new_val!r}")

    new_text = "".join(new_lines)

    # 5. Post-substitution validation: no placeholders left
    if PLACEHOLDER_TOKEN in new_text:
        leftover = [
            line for line in new_text.splitlines()
            if PLACEHOLDER_TOKEN in line
        ]
        raise RuntimeError(
            "[fill_whitepaper_results] post-substitution validation FAILED: "
            f"{len(leftover)} XX.XX placeholders remain. "
            "First offending line(s):\n  "
            + "\n  ".join(leftover[:5])
        )

    # 6. Write (unless dry-run)
    print(f"[fill_whitepaper_results] {substituted}/{len(MAPPING)} macros "
          f"resolved; placeholder check OK")
    if dry_run:
        print("[fill_whitepaper_results] DRY RUN: no file written")
    else:
        TEX_PATH.write_text(new_text, encoding="utf-8")
        print(f"[fill_whitepaper_results] wrote {TEX_PATH}")

    # 7. ADDITIVE: mirror the SAME resolved values into the defense deck's
    #    shared macro file. Identical \newcommand contract, so one MAPPING
    #    drives both paper and slides. Purely additive: the whitepaper logic
    #    above is unchanged, and a missing slides file is a clean no-op.
    if SLIDES_MACROS_PATH.exists():
        slides_text = SLIDES_MACROS_PATH.read_text(encoding="utf-8")
        # Same strict guard the whitepaper gets: slides macro set == MAPPING.
        _validate_mapping_against_tex(
            [name for name, _ in _scan_macros(slides_text)]
        )
        s_sub = 0
        s_lines: List[str] = []
        for line in slides_text.splitlines(keepends=True):
            m = _NEWCMD_RE.search(line)
            if m is None or m.group(1) not in new_values:
                s_lines.append(line)
                continue
            s_lines.append(
                line[: m.start(2)] + new_values[m.group(1)] + line[m.end(2):]
            )
            s_sub += 1
        s_text = "".join(s_lines)
        if PLACEHOLDER_TOKEN in s_text:
            bad = [ln for ln in s_text.splitlines() if PLACEHOLDER_TOKEN in ln]
            raise RuntimeError(
                "[fill_whitepaper_results] slides post-substitution FAILED: "
                f"{len(bad)} placeholders remain.\n  " + "\n  ".join(bad[:5])
            )
        print(f"[fill_whitepaper_results] slides: {s_sub}/{len(MAPPING)} "
              f"macros resolved; placeholder check OK")
        if dry_run:
            print("[fill_whitepaper_results] DRY RUN: slides file not written")
        else:
            SLIDES_MACROS_PATH.write_text(s_text, encoding="utf-8")
            print(f"[fill_whitepaper_results] wrote {SLIDES_MACROS_PATH}")

    return substituted


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="report which macros would be substituted with which "
             "values, without modifying the .tex file",
    )
    args = ap.parse_args(argv)
    fill(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
