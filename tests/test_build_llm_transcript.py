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
    assert report.n_messages == 0


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

    long_text = "x" * 3000  # ~3KB per message
    for i in range(5):
        _write_session(projects / f"s{i}.jsonl", [
            {"type": "user", "timestamp": f"2026-05-2{i+1}T09:00:00Z",
             "message": {"content": f"msg{i}: {long_text}"}},
        ])

    build(projects_dir=projects, out_path=out, max_chars=15_000)
    text = out.read_text(encoding="utf-8")
    # Newest session should be kept.
    assert "msg4" in text
    # Either elision note appears, or older messages are absent.
    assert "msg0" not in text or "elided" in text.lower()


def test_api_key_redacted(tmp_path):
    """Privacy sanitizer: sk-ant-XXX must be redacted."""
    from scripts.build_llm_transcript import build

    projects = tmp_path / "projects" / "D--DeFi"
    out = tmp_path / "LLM_TRANSCRIPT.md"
    _write_session(projects / "x.jsonl", [
        {"type": "user", "timestamp": "2026-05-26T12:00:00Z",
         "message": {"content": "My key is sk-ant-abc123def456ghi"}},
    ])
    build(projects_dir=projects, out_path=out)
    text = out.read_text(encoding="utf-8")
    assert "sk-ant-abc123def456ghi" not in text
    assert "sk-ant-<REDACTED>" in text


def test_tool_use_records_skipped(tmp_path):
    """tool_use + tool_result types must not appear in transcript."""
    from scripts.build_llm_transcript import build

    projects = tmp_path / "projects" / "D--DeFi"
    out = tmp_path / "LLM_TRANSCRIPT.md"
    _write_session(projects / "x.jsonl", [
        {"type": "tool_use", "timestamp": "2026-05-26T12:00:00Z",
         "message": {"content": "INTERNAL_TOOL_INVOCATION"}},
        {"type": "tool_result", "timestamp": "2026-05-26T12:00:02Z",
         "message": {"content": "INTERNAL_TOOL_RESULT"}},
        {"type": "user", "timestamp": "2026-05-26T12:00:05Z",
         "message": {"content": "real user content"}},
    ])
    build(projects_dir=projects, out_path=out)
    text = out.read_text(encoding="utf-8")
    assert "INTERNAL_TOOL_INVOCATION" not in text
    assert "INTERNAL_TOOL_RESULT" not in text
    assert "real user content" in text
