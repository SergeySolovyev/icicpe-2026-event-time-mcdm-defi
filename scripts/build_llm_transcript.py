"""Plan F Task 5 -- LLM transcript capture for the reproducibility appendix.

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
    1. Windows home path     C:\\Users\\<NAME> -> <HOME>
    2. POSIX home path       /home/<name>      -> <HOME>
    3. API key prefix        sk-ant-          -> sk-ant-<REDACTED>

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
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROJECTS = Path.home() / ".claude" / "projects" / "D--DeFi"
DEFAULT_OUT = (
    ROOT / "papers" / "icicpe-scopus-vol2-submission" / "LLM_TRANSCRIPT.md"
)
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
                rel_min = int(
                    (_parse_ts(ts) - session_start_dt).total_seconds() // 60
                )
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
    header = (
        f"## Session `{sl.session_id}` (started {sl.started_at}, "
        f"{sl.n_messages} messages)\n\n"
    )
    return header + body + "\n", sl


def build(
    *,
    projects_dir: Path,
    out_path: Path,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> BuildReport:
    projects_dir = Path(projects_dir)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not projects_dir.exists():
        out_path.write_text(
            "# LLM transcript appendix\n\n"
            f"_No session files found under {projects_dir}._\n",
            encoding="utf-8",
        )
        return BuildReport(
            out_path=out_path, slices=(), total_chars=0, n_messages=0
        )

    sessions = sorted(projects_dir.glob("*.jsonl"))
    rendered: list[tuple[str, TranscriptSlice, datetime]] = []
    for s in sessions:
        body, sl = _render_session(s)
        rendered.append((body, sl, _parse_ts(sl.started_at)))

    # Sort by start timestamp ascending.
    rendered.sort(key=lambda t: t[2])

    # Apply max_chars budget by dropping oldest sessions first.
    elided = 0
    while (
        rendered
        and sum(len(b) for b, _, _ in rendered) > max_chars
        and len(rendered) > 1
    ):
        rendered.pop(0)
        elided += 1

    head = "# LLM transcript appendix\n\n"
    head += "Model: Claude (Anthropic) — used as a coding pair-programmer.\n"
    head += "Role: implementation assistance under operator review.\n\n"
    if elided:
        head += (
            f"_[Elided {elided} earlier session(s) to fit {max_chars}-char "
            f"appendix budget.]_\n\n"
        )

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
    print(
        f"wrote {report.out_path} "
        f"({report.n_messages} msgs across {len(report.slices)} sessions, "
        f"{report.total_chars} chars, {report.n_sessions_elided} elided)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(_main())
