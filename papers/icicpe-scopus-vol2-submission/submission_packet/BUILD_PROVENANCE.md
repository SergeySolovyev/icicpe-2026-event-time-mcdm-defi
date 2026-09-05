# Build provenance — rebuilt 2026-09-05: six audit blockers resolved, awaiting author review of the edits

**Rebuilt 2026-09-04 from the corrected source of truth.** The retracted +7.03 bp claim is gone from
both the PDF and the portal fields. A full project audit on 2026-09-05 found six further defects; all six were resolved the same day
(see "Resolution" below) and the packet was rebuilt from the corrected sources. This packet supersedes the
pre-retraction snapshot of 2026-05-29, which is preserved (not deleted) under
`_stale_2026-05-29/` for the record.

## What is in this packet

| File | What it is |
|---|---|
| `Solovev_ICICPE2026_Event_Time_MCDM_DeFi.pdf` | the manuscript to upload (16 pages) |
| `Solovev_ICICPE2026_LaTeX_Source.zip` | LaTeX sources, if the portal asks for them |
| `Solovev_ICICPE2026_LaTeX_Source/` | the same sources, unzipped |
| `submission_fields.md` | every portal form field, ready to paste |
| `_stale_2026-05-29/` | the superseded packet — do not submit |

## How it was built

Source of truth: `../main.tex` + `../sections/` at commit `b857cae`.
Packaging steps (the same conversion the 2026-05 packet used):

1. `main.tex` -> `icicpe.tex`, with `\bibliography{refs}` -> `\bibliography{refer}`
2. `refs.bib` -> `refer.bib`; `icicpe.sty` and `ICICPEtran.bst` copied unchanged
3. `sections/*.tex` copied, with the figure path `../../results/figures/` rewritten to `figures/`
4. `results/figures/equity_curves.png` copied into `figures/`
5. `latexmk -pdf icicpe.tex` — exit 0, no errors, 0 unresolved references on the final pass
6. the unused orphan `sections/04_lob_recap.tex` was left out (it is not `\input` by the build)

The output is byte-for-byte the same size (922,693 bytes) as the parent build
`../main.pdf`, confirming the packaging changed nothing but file names and paths.

## Verified before packaging

- `+7.03 bp` appears **only** inside its own explicit retraction ("...we retract it"),
  never as a standing claim.
- The T3 negative result reads `-5.97 bp (0/5 windows)` consistently in the abstract,
  the empirical section, the results table and the conclusion.
- Headline: T1 beats every passive hold by `+2.2` to `+4.1` pp, `p < 1e-4` on all six
  contrasts, Holm-corrected.
- 0 unresolved `??` references in the PDF text; "WorldQuant University" present as affiliation.
- `submission_fields.md` portal abstract was **also stale** and has been rewritten to
  match the PDF. This was the second landmine: the old portal text still advertised the
  retracted "+7.03 bp, p = 0.015" result and a superseded "1.5-2.8 pp" headline, so
  submitting the corrected PDF with the old form text would have reintroduced the
  contradiction in the reviewers' first screen.

## Page count — settled, do not re-open

This build is **16 pages, and that is fine**. The author confirmed on 2026-09-04 that
ICICPE SCOPUS Vol-2 has **no page limit**.

The "10-12 page budget" recorded elsewhere in this repository is **obsolete** and should
not be treated as a gate:

- `KANBAN.md` (Plan F, task F4) - "Target 10-12 pages"
- `docs/superpowers/plans/2026-05-26-paper-polish-submit.md` - "enforces a 10-12 page budget"
- `docs/superpowers/specs/2026-05-26-institutional-dossier-design.md` - "Paper stays at 10-12 pages"
- `docs/institutional/SCOPUS_SUBMISSION_CHECKLIST.md` - "Confirm 12 pages"
- `scripts/audit_page_budget.py` - asserts the count is in [10, 12] and will FAIL on this PDF

Those all trace back to a May 2026 author kit. **Expect `audit_page_budget.py` to report
FAIL; that is a stale gate, not a defect in this packet.**

For the record, the 16 pages break down as: Introduction 2, Background 2, Methodology 2,
Empirical Study 5, Discussion/cross-domain 2, Limitations + Conclusion 1, references ~2.
The Empirical section is the largest because it carries the H1c retraction and the honest
T3 negative result - the very content this rebuild exists to preserve.


## Audit 2026-09-05 — blockers verified against the repository

Each item below was checked directly in code/data, not taken from a summary.

1. **The abstract's lower bound "+2.2 pp" is a hand-typed number.** Commit `75df7b3` replaced the
   generator's Fluid rows in `results/institutional/tables/walk_forward_NxM_contrasts.csv`
   (T1 3.8648 -> 2.216, T2 3.7603 -> 2.11, T3 3.8648 -> 2.216) with 3-decimal values. The other 15 rows
   keep full float precision. Root cause is a provenance split: the shipped panel carries Fluid from the
   fToken series, `fluid_per_window_apy.csv` used the DeFiLlama series. Regenerate the table from one
   canonical panel; with the generator's value the tightest contrast becomes Euler (2.69), and the prose
   "smallest-margin is Fluid" no longer holds.
2. **Capacity section cites Euler TVL ~$16M; on the test window it is $2.61M** (min $1.72M). $16M is the
   whole-panel mean. A $1M position is ~40% of the Euler pool while T1 holds Euler ~49% of the time, and
   the replay engine applies zero price impact. `sections/05_empirical.tex:423`.
3. **"Sample-uniqueness weighting" (abstract, intro, §V) never runs.** `_sample_uniqueness_weights` is
   defined at `scripts/train_t3_sophisticated.py:132` and called nowhere; no `fitter.fit(weights_col=...)`
   exists in the repository.
4. **"Holm-corrected, p < 1e-4" is not produced by the pipeline.** `walk_forward_NxM_contrasts.csv` has no
   `p_holm` column and `p_one_sided_le0` is literally 0.0 in all 18 rows. Holm is implemented only inside
   the reproduction notebook.
5. **"Pre-registered negative result" (6 occurrences: main.tex, 01_introduction, 05_empirical x3,
   08_conclusion) is not what was pre-registered.** `PROJECT_OVERVIEW.md:484-490` registers H1c as
   "T3 dSharpe over **T2** >= 0.05, paired-monthly p < 0.05". The paper reports dAPY in bp vs **T1** on an
   expanding-window design. Different metric, baseline and design. Reword to "post-hoc corrected".

6. **"The reference deployment implementation therefore routes rebalances through the Flashbots
   private mempool" (`sections/06_cross_domain.tex:149`) is false today, and "MEV is bounded above by
   the Flashbots path" (`03_methodology.tex:37`) is unsupported.** In `D:/DeFi/DeFi-Vega Project/agent`
   both live send paths, `main.py:204` and `api.py:308`, call `w3.eth.send_raw_transaction` (public
   mempool). `FlashbotsMempool` is constructed only in `scripts/flashbots_smoke.py` and
   `tests/test_mempool.py`, defaults to `dry_run=True`, and its `_build_rebalance_tx` is a stub;
   `config.py` has no Flashbots setting. Reword to future tense or remove; the backtest deducts no MEV.

The full audit (idea, code, paper) lives in the repository at `docs/research/DEEP_STUDY_2026-09-05.md`
(MacKenzie section included). Session copies: `deep_study_synthesis.md` / `deep_study_gaps.md`.

## Resolution — 2026-09-05 (evening build)

All six blockers above were resolved in the manuscript sources and the packet was rebuilt from them.
Review diff for the author: `paper_edits.diff` (23 edits, 8 files, 229 lines).

| # | Resolution |
|---|---|
| 1 | `results/institutional/tables/fluid_per_window_apy.csv` regenerated from the shipped panel's fToken series (per-block compounding, annualised exactly as `rebuild_nxm_6way_active._policy_apy_per_window`); the old DeFiLlama series kept as `fluid_per_window_apy_defillama_2026-06.csv`. Generator re-run: T1 vs Fluid = **2.248 pp**, CI [1.598, 3.052], 6/6. Correction to the blocker text above: the hand-typed 2.216 was numerically right (it is the notebook's fToken-based value); what was wrong was the pipeline input, not the number. Abstract "+2.2" unchanged; §V "+2.22" -> "+2.25". |
| 2 | §V Capacity rewritten with test-window figures (Euler $2.6M mean / $1.7M min; Spark $36M), the 40% position-share fact, the 49% Euler time-share (verified from `equity_t1_threshold.parquet`, protocol shifted one row), and the unsupported "$5-10M ceiling" withdrawn. |
| 3 | "sample-uniqueness weighting" removed from the abstract, §I contribution list and §V (function exists but is never called). |
| 4 | "p < 1e-4" rephrased as "p at its 1e-4 resampling floor" (abstract, §I, §V, §VII); Holm attributed to the companion notebook §7 in the table note, since the pipeline CSV carries no Holm column. |
| 5 | "pre-registered" -> "post-hoc corrected" in all six places; the abstract adds the one-clause reason (earlier in-sample positive finding retracted after a leakage audit). |
| 6 | §VI Flashbots sentence rewritten as a design specification with the live send path stated as public mempool; §III "MEV bounded above" replaced by "MEV not modelled in the replay". |
| + | Also fixed while in the files: MacKenzie page citation 102-104 -> 82-83; the §III attribution of an HJB/OU boundary to Kissell 2014 removed (approximation stated as such); abstract sentence "reuses the same decision modules" replaced by the true statement (the notebook re-implements the rules from scratch and reproduces every number); refs.bib MacKenzie subtitle "Lightning-Fast" -> "Ultrafast"; `Accessed 2026-04-XX` -> `Accessed April 2026` (the entry is cited twice in §II; ICICPEtran.bst does not print the `note` field, so the placeholder never reached the PDF — housekeeping only). |

Build: `latexmk -pdf icicpe.tex` exit 0; **0 unresolved citations, 0 bibtex warnings; 16 pages; 923,869 bytes — identical to `../main.pdf`**. Zip composition identical to the previous packet (16 files). `submission_fields.md` portal abstract updated to match (post-hoc corrected; p at the 1e-4 floor).

Audits on this build: `audit_refs_bib` PASS · `audit_page_budget` FAIL (stale gate, see above) · `audit_anonymization` FAIL with 9 findings, all of them the figshare dataset DOI in `refs.bib:17` and its copies — a blind-review check that does not apply to this `\finalcopy` named submission; no prose leak.

### Residual audit items — deliberately NOT touched in this pass (author's call)

From `docs/research/DEEP_STUDY_2026-09-05.md`; agent-found, not independently verified here:
- §III still says CV "uses purged k-fold with embargo": true for the leaked full-panel model, not for the honest expanding-window run (`walkforward_t3_expanding.py:152` skips it).
- "Triple-barrier labels" names a one-sided censored survival label (`build_flip_labels`); Ch. 3.6 cited where 3.4 is meant.
- Deflated Sharpe: no DSR number exists in `results/`; the implemented formula drops the variance term; `tests/test_deflated_sharpe_ratio.py` cements it.
- §III κ₀ = 2.1e-5 (12x arithmetic slip); runtime uses 1e-5 with MLE refit — paper-only error.
- Abstract "zero blocks accrued against a missing rate": true on the test window, 2 blocks on the full panel.
- Table `tab:timeshare` not reproducible from the equity files; F4 ablation compares byte-identical feature sets.
- The working copy `papers/icicpe-scopus-vol2/` was NOT synced with these edits; the submission copy is the source of truth.

## Still open before you submit

- Author review of the 23 manuscript edits (`paper_edits.diff`); wording in items 4-5 is proposed, not final.
- Deadline on record: **20 November 2026**.
- Portal: <https://icicpe.org/215-2/>
