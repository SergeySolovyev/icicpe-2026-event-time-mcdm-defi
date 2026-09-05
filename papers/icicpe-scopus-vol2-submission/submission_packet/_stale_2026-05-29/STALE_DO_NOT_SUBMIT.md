# ⚠ STALE PACKET — DO NOT SUBMIT

**This packaged submission (PDF + zip) is a pre-retraction snapshot from
commit `511552f` (2026-05-29) and is SUPERSEDED.** It still ships the
**retracted** `+7.03 bp` "T3 dominates T1 (p=0.015)" claim throughout the
abstract, introduction, headline table, and conclusion, with no retraction —
exactly the self-contradiction the 2026-06 project audit
(`docs/research/PROJECT_AUDIT_2026-06.md`) flagged as desk-reject-class.

**The correct, source-of-truth paper** is the parent build
`papers/icicpe-scopus-vol2-submission/main.tex` (+ `sections/`), which as of
2026-06-09 has:
- the retracted `+7.03`/`H1c` claim removed; the T3 row shown as the deployed
  fallback (≡ T1) with the honest out-of-sample T3 *loss* reported separately;
- the headline N×M re-sourced to the canonical
  `results/institutional/tables/walk_forward_NxM_contrasts.csv`
  (T1 +2.69…+4.05 pp, all 6/6, p<1e-4, Holm-corrected);
- the T3 negative quoted at the single reproducible magnitude **−5.97 bp (0/5)**
  everywhere (previously inconsistent: −88 / −88.3 / −5.97).

**At the next submission:** regenerate this packet from the corrected parent
source (copy `../main.tex` + `../sections/*` into the conference template
`icicpe.tex`, rebuild, re-zip). Do not reuse the existing
`Solovev_ICICPE2026_*.pdf` or `.zip` in this directory.
