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
