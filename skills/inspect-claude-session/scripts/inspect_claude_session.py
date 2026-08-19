#!/usr/bin/env python3
"""Inspect local Claude Code session JSONL transcripts.

This is intentionally read-only. It summarizes sessions stored below
$CLAUDE_HOME or ~/.claude without depending on a stable private API.

Designed for agents coordinating with other agents: every view reports
how long ago the session was last active, the state heuristic accounts
for recency (a transcript updated seconds ago is treated as live), and
--since supports incremental polling without re-reading old events.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
WAIT_RE = re.compile(
    r"\b(waiting for|need(?:s|ed)? (?:you|input|approval|confirmation|clarification)|"
    r"please (?:confirm|clarify|approve|provide)|question for you|can you clarify|"
    r"where do you land|what do you want|do you want me)\b",
    re.IGNORECASE,
)
BLOCKED_RE = re.compile(
    r"\b(i'?m blocked|blocked by|command failed|failed with|error:|cannot proceed|can't proceed)\b",
    re.IGNORECASE,
)

# A transcript updated within this window is treated as actively running.
ACTIVE_WINDOW_SECONDS = 120

VALID_ROLES = {"user", "assistant", "tool", "system"}


@dataclass
class Event:
    timestamp: str
    kind: str
    role: str
    text: str


@dataclass
class SessionSummary:
    path: Path
    id: str = ""
    title: str = ""
    last_prompt: str = ""
    project: str = ""
    cwd: str = ""
    model: str = ""
    git_branch: str = ""
    entrypoint: str = ""
    updated_at: str = ""
    file_mtime: datetime | None = None
    events: list[Event] = field(default_factory=list)
    raw_event_count: int = 0
    child_activity: list[dict[str, Any]] = field(default_factory=list)
    native_agent: dict[str, Any] = field(default_factory=dict)


def claude_home() -> Path:
    return Path(os.environ.get("CLAUDE_HOME", "~/.claude")).expanduser()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect local Claude Code session transcripts from $CLAUDE_HOME or ~/.claude."
    )
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--last", action="store_true", help="Inspect the most recently modified transcript.")
    selector.add_argument("--query", "-q", help="Session id, title, prompt, project substring, or JSONL path.")
    selector.add_argument("--path", help="Direct path to a Claude JSONL file.")
    selector.add_argument("--list", action="store_true", help="List recent Claude session transcripts.")
    parser.add_argument("--limit", "-n", type=int, default=10, help="Number of recent events/sessions to show.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--home", help="Override Claude home directory.")
    parser.add_argument(
        "--include-subagents",
        action="store_true",
        help="Include subagent JSONL files in --list/--last/query results.",
    )
    parser.add_argument(
        "--last-message",
        choices=["assistant", "user", "any"],
        help="Print the latest full user/assistant message instead of the event summary.",
    )
    parser.add_argument(
        "--search",
        help="Search extracted event text and print matching events. Useful for finding prior answers without parsing JSONL by hand.",
    )
    parser.add_argument(
        "--role",
        help="Comma-separated roles to include in event views: user,assistant,system. "
        "Example: --role user,assistant shows just the conversation without hook/attachment noise.",
    )
    parser.add_argument(
        "--since",
        help="Only show events newer than this ISO timestamp (e.g. 2026-06-10T19:35:00Z). "
        "Use the 'Last activity' value from a previous run for incremental polling.",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=600,
        help="Per-event truncation budget in the summary/search views (default 600).",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Print full event text (no truncation) in summary and search views.",
    )
    return parser.parse_args()


def parse_roles(raw: str | None) -> set[str] | None:
    if not raw:
        return None
    roles = {part.strip().lower() for part in raw.split(",") if part.strip()}
    invalid = roles - VALID_ROLES
    if invalid:
        raise SystemExit(f"Invalid --role value(s): {', '.join(sorted(invalid))}. Valid: {', '.join(sorted(VALID_ROLES))}")
    return roles


def parse_iso(timestamp: str) -> datetime | None:
    if not timestamp:
        return None
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def humanize_age(seconds: float) -> str:
    total = max(int(seconds), 0)
    if total < 60:
        return f"{total}s ago"
    if total < 3600:
        return f"{total // 60}m{total % 60:02d}s ago"
    if total < 86400:
        return f"{total // 3600}h{(total % 3600) // 60:02d}m ago"
    return f"{total // 86400}d ago"


def last_activity(summary: SessionSummary) -> tuple[datetime | None, float | None]:
    """Best-effort last-activity instant: max of last event timestamp and file mtime.

    The file mtime usually leads the last parsed timestamp while a session is
    mid-write, so taking the max avoids calling a live session idle.
    """
    candidates = [dt for dt in (parse_iso(summary.updated_at), summary.file_mtime) if dt]
    if not candidates:
        return None, None
    newest = max(candidates)
    age = (datetime.now(timezone.utc) - newest).total_seconds()
    return newest, age


def session_files(home: Path, include_subagents: bool = False) -> list[Path]:
    root = home / "projects"
    if not root.exists():
        return []

    files = list(root.rglob("*.jsonl"))
    main = [path for path in files if "/subagents/" not in str(path)]
    if not include_subagents:
        return main
    # Journals and other NDJSON artifacts are not independently resumable
    # sessions. Only expose actual agent transcripts alongside main sessions.
    children = [
        path
        for path in files
        if "/subagents/" in str(path) and path.name.startswith("agent-")
    ]
    return main + children


def newest_path(paths: Iterable[Path]) -> Path | None:
    candidates = list(paths)
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def file_mtime(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def mtime_iso(path: Path) -> str:
    stamp = file_mtime(path)
    return stamp.isoformat() if stamp else ""


def session_id_from_path(path: Path) -> str:
    match = UUID_RE.search(path.name)
    if match:
        return match.group(0)
    parent_match = UUID_RE.search(str(path.parent))
    return parent_match.group(0) if parent_match else ""


def project_from_path(home: Path, path: Path) -> str:
    try:
        rel = path.relative_to(home / "projects")
    except ValueError:
        return ""
    return rel.parts[0] if rel.parts else ""


def compact(text: str, max_chars: int = 600) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if max_chars <= 0 or len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "..."


def content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    chunks: list[str] = []
    for part in content:
        if isinstance(part, str):
            chunks.append(part)
        elif isinstance(part, dict):
            kind = str(part.get("type") or "")
            if kind == "text" and isinstance(part.get("text"), str):
                chunks.append(part["text"])
            elif kind == "tool_use":
                name = str(part.get("name") or "tool")
                tool_input = part.get("input")
                if tool_input is not None:
                    chunks.append(f"tool_use {name}: {compact(json.dumps(tool_input, default=str), 240)}")
                else:
                    chunks.append(f"tool_use {name}")
            elif kind == "tool_result":
                result = part.get("content")
                chunks.append(f"tool_result: {compact(content_text(result) or str(result or ''), 300)}")
    return "\n".join(chunk for chunk in chunks if chunk)


def attachment_text(attachment: dict[str, Any]) -> str:
    kind = str(attachment.get("type") or "attachment")
    hook_name = str(attachment.get("hookName") or "")
    content = str(attachment.get("content") or "")
    command = str(attachment.get("command") or "")
    if content:
        text = content
    elif command:
        text = command
    else:
        text = json.dumps({k: v for k, v in attachment.items() if k not in {"stdout", "stderr"}}, default=str)
    prefix = f"{kind}:{hook_name}" if hook_name else kind
    return f"{prefix}: {compact(text, 500)}"


def extract_event(line: dict[str, Any]) -> Event | None:
    timestamp = str(line.get("timestamp") or "")
    record_type = str(line.get("type") or "")

    if record_type in {"user", "assistant"}:
        message = line.get("message")
        if isinstance(message, dict):
            role = str(message.get("role") or record_type)
            content = message.get("content")
            text = content_text(content)
            if text:
                # Claude transcripts deliver tool results as user-role messages
                # and emit tool-only assistant turns. Reclassify pure tool
                # traffic as role "tool" so --role user,assistant shows just
                # the human-readable conversation.
                part_types = {
                    str(part.get("type") or "")
                    for part in content
                    if isinstance(part, dict)
                } if isinstance(content, list) else set()
                has_plain_text = isinstance(content, str) or (
                    isinstance(content, list)
                    and any(
                        isinstance(part, str)
                        or (isinstance(part, dict) and str(part.get("type") or "") == "text")
                        for part in content
                    )
                )
                if not has_plain_text and part_types and part_types <= {"tool_result"}:
                    return Event(timestamp, "tool_result", "tool", text)
                if not has_plain_text and part_types and part_types <= {"tool_use"}:
                    return Event(timestamp, "tool_call", "tool", text)
                return Event(timestamp, "message", role, text)

    if record_type == "system":
        subtype = str(line.get("subtype") or "system")
        text = str(line.get("message") or subtype)
        return Event(timestamp, subtype, "system", text)

    attachment = line.get("attachment")
    if isinstance(attachment, dict):
        return Event(timestamp, "attachment", "system", attachment_text(attachment))

    if record_type in {"last-prompt", "ai-title", "permission-mode", "file-history-snapshot"}:
        text = str(line.get("lastPrompt") or line.get("aiTitle") or line.get("permissionMode") or record_type)
        return Event(timestamp, record_type, "system", text)

    return None


def update_metadata(summary: SessionSummary, line: dict[str, Any], home: Path) -> None:
    summary.id = str(line.get("sessionId") or summary.id or session_id_from_path(summary.path))
    summary.cwd = str(line.get("cwd") or summary.cwd)
    summary.git_branch = str(line.get("gitBranch") or summary.git_branch)
    summary.entrypoint = str(line.get("entrypoint") or summary.entrypoint)
    summary.project = summary.project or project_from_path(home, summary.path)

    if line.get("type") == "ai-title":
        summary.title = str(line.get("aiTitle") or summary.title)
    elif line.get("type") == "last-prompt":
        summary.last_prompt = str(line.get("lastPrompt") or summary.last_prompt)

    message = line.get("message")
    if isinstance(message, dict):
        summary.model = str(message.get("model") or summary.model)


def inspect_path(path: Path, home: Path) -> SessionSummary:
    summary = SessionSummary(path=path, id=session_id_from_path(path), project=project_from_path(home, path))
    summary.file_mtime = file_mtime(path)
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError as exc:
        raise SystemExit(f"Could not read {path}: {exc}") from exc

    for raw in lines:
        if not raw.strip():
            continue
        try:
            line = json.loads(raw)
        except json.JSONDecodeError:
            continue
        summary.raw_event_count += 1
        timestamp = str(line.get("timestamp") or "")
        if timestamp:
            summary.updated_at = timestamp
        update_metadata(summary, line, home)
        event = extract_event(line)
        if event:
            summary.events.append(event)

    if not summary.updated_at:
        summary.updated_at = mtime_iso(path)
    summary.child_activity = discover_child_activity(summary)
    summary.native_agent = native_agent_for_summary(summary)
    return summary


_NATIVE_AGENT_CACHE: dict[str, dict[str, Any]] | None = None


def native_agent_index() -> dict[str, dict[str, Any]]:
    """Read Claude 2.1.207+'s public background/interactive agent registry."""
    global _NATIVE_AGENT_CACHE
    if _NATIVE_AGENT_CACHE is not None:
        return _NATIVE_AGENT_CACHE
    _NATIVE_AGENT_CACHE = {}
    if os.environ.get("INSPECT_CLAUDE_SKIP_NATIVE_AGENTS"):
        return _NATIVE_AGENT_CACHE
    try:
        completed = subprocess.run(
            ["claude", "agents", "--json", "--all"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        rows = json.loads(completed.stdout) if completed.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        rows = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            session_id = str(row.get("sessionId") or "")
            if session_id:
                _NATIVE_AGENT_CACHE[session_id.lower()] = row
    return _NATIVE_AGENT_CACHE


def native_agent_for_summary(summary: SessionSummary) -> dict[str, Any]:
    if parent_artifact_root(summary) is None or not summary.id:
        return {}
    return dict(native_agent_index().get(summary.id.lower(), {}))


def parent_artifact_root(summary: SessionSummary) -> Path | None:
    """Return the companion artifact directory for a top-level session.

    Claude's Workflow/Agent tools keep running after the parent turn has
    emitted its assistant message. Their transcripts live below a directory
    named after the parent JSONL stem, beside the parent transcript itself.
    """
    if summary.path.parent.name == summary.path.stem:
        return None
    candidate = summary.path.with_suffix("")
    return candidate if candidate.is_dir() else None


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def workflow_journal_state(journal_path: Path) -> tuple[int, int]:
    started: set[str] = set()
    finished: set[str] = set()
    try:
        lines = journal_path.read_text(errors="replace").splitlines()
    except OSError:
        return 0, 0
    for raw in lines:
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "")
        if row.get("type") == "started" and key:
            started.add(key)
        elif row.get("type") in {"result", "error", "failed", "cancelled"} and key:
            finished.add(key)
    return len(started), len(started - finished)


def discover_child_activity(summary: SessionSummary) -> list[dict[str, Any]]:
    root = parent_artifact_root(summary)
    if root is None:
        return []

    workflows_root = root / "subagents" / "workflows"
    result_root = root / "workflows"
    rows: list[dict[str, Any]] = []
    if workflows_root.exists():
        for workflow_dir in sorted(workflows_root.glob("wf_*")):
            if not workflow_dir.is_dir():
                continue
            workflow_id = workflow_dir.name
            result_path = result_root / f"{workflow_id}.json"
            result = load_json(result_path)
            status = str(result.get("status") or "")
            journal = workflow_dir / "journal.jsonl"
            started, unfinished = workflow_journal_state(journal)
            transcript_paths = list(workflow_dir.glob("agent-*.jsonl"))
            activity_paths = [path for path in [journal, result_path, *transcript_paths] if path.exists()]
            newest = newest_path(activity_paths)
            stamp = file_mtime(newest) if newest else None
            age = (datetime.now(timezone.utc) - stamp).total_seconds() if stamp else None

            if status in {"completed", "failed", "cancelled"}:
                state = status
            elif age is not None and age <= ACTIVE_WINDOW_SECONDS:
                state = "likely running"
            elif unfinished:
                state = "unfinished or stalled"
            else:
                state = "unknown"

            rows.append(
                {
                    "kind": "workflow",
                    "id": workflow_id,
                    "state": state,
                    "status": status,
                    "started_lanes": started,
                    "unfinished_lanes": unfinished,
                    "agent_transcripts": len(transcript_paths),
                    "last_activity": stamp.isoformat() if stamp else "",
                    "age_seconds": round(age) if age is not None else None,
                    "path": str(workflow_dir),
                    "result_path": str(result_path) if result_path.exists() else "",
                }
            )

    # Plain Agent-tool children are siblings of the workflows directory. Avoid
    # double-counting workflow agents, which are summarized per workflow above.
    subagents_root = root / "subagents"
    if subagents_root.exists():
        for transcript in sorted(subagents_root.glob("agent-*.jsonl")):
            stamp = file_mtime(transcript)
            age = (datetime.now(timezone.utc) - stamp).total_seconds() if stamp else None
            rows.append(
                {
                    "kind": "subagent",
                    "id": transcript.stem,
                    "state": "likely running" if age is not None and age <= ACTIVE_WINDOW_SECONDS else "idle or complete",
                    "status": "",
                    "last_activity": stamp.isoformat() if stamp else "",
                    "age_seconds": round(age) if age is not None else None,
                    "path": str(transcript),
                }
            )

    return sorted(rows, key=lambda row: row.get("last_activity") or "", reverse=True)


def resolve_session_path(home: Path, args: argparse.Namespace) -> Path | None:
    files = session_files(home, include_subagents=args.include_subagents)
    if args.path:
        return Path(args.path).expanduser()

    if args.query:
        query = args.query.strip()
        maybe_path = Path(query).expanduser()
        if maybe_path.exists():
            return maybe_path

        # Child transcripts reuse the parent's sessionId. Prefer the canonical
        # top-level <session-id>.jsonl when an explicit UUID is supplied.
        canonical = [path for path in files if path.name.lower() == f"{query.lower()}.jsonl"]
        if canonical:
            return newest_path(canonical)

        exact = [path for path in files if session_id_from_path(path).lower() == query.lower()]
        if exact:
            return newest_path(exact)

        path_matches = [
            path
            for path in files
            if query.lower() in str(path).lower() or query.lower() in session_id_from_path(path).lower()
        ]
        if len(path_matches) == 1:
            return path_matches[0]

        metadata_matches: list[Path] = []
        for path in files:
            try:
                summary = inspect_path(path, home)
            except SystemExit:
                continue
            haystack = " ".join(
                [summary.id, summary.title, summary.last_prompt, summary.project, summary.cwd, str(path)]
            ).lower()
            if query.lower() in haystack:
                metadata_matches.append(path)
        return newest_path(metadata_matches or path_matches)

    if args.last:
        return newest_path(files)

    return None


def heuristic_state(summary: SessionSummary) -> tuple[str, str]:
    native = summary.native_agent
    native_status = str(native.get("status") or "").lower()
    native_state = str(native.get("state") or "").lower()
    native_kind = str(native.get("kind") or "session")
    if native_status == "busy":
        return (
            "likely running",
            f"Claude's native agent registry reports this {native_kind} session as busy.",
        )
    if native_state == "blocked":
        return (
            "blocked",
            f"Claude's native agent registry reports this {native_kind} session as blocked.",
        )
    if native_state == "done":
        return (
            "likely waiting or complete",
            f"Claude's native agent registry reports this {native_kind} session as done.",
        )

    active_children = [row for row in summary.child_activity if row.get("state") == "likely running"]
    unfinished_children = [row for row in summary.child_activity if row.get("state") == "unfinished or stalled"]
    if active_children:
        return (
            "likely running background work",
            f"The parent transcript is not the whole lifecycle: {len(active_children)} child workflow/subagent artifact(s) were written within the active window.",
        )
    if unfinished_children:
        return (
            "background work unfinished or stalled",
            f"{len(unfinished_children)} child workflow(s) have started lanes without a terminal workflow result; inspect their child transcripts before treating the parent as complete.",
        )

    if not summary.events:
        return "unknown", "No readable transcript events were found."

    messages = [event for event in summary.events if event.kind == "message"]
    if not messages:
        return "unknown", "No user/assistant messages were found in the transcript."

    _, age = last_activity(summary)
    recently_active = age is not None and age <= ACTIVE_WINDOW_SECONDS

    if recently_active:
        # A live transcript trumps message-role heuristics: Claude Code writes
        # interim assistant messages mid-turn, so "last message is from the
        # assistant" does NOT mean the turn is over.
        return (
            "likely running",
            f"Transcript was last written {humanize_age(age)}; treat the session as live "
            "and do not modify files it may be working on.",
        )

    last_event = summary.events[-1]
    if last_event.kind in {"attachment", "tool_call", "tool_result"}:
        return (
            "possibly running hooks/tools or stopped mid-turn",
            "The latest visible event is tool or hook activity, "
            f"but the transcript has been idle for {humanize_age(age) if age is not None else 'an unknown time'}.",
        )

    recent_assistant = [event for event in reversed(messages) if event.role == "assistant"]
    if recent_assistant and (WAIT_RE.search(recent_assistant[0].text) or BLOCKED_RE.search(recent_assistant[0].text)):
        text = recent_assistant[0].text
        if WAIT_RE.search(text) or "?" in text:
            return "likely waiting for user", "The latest assistant message appears to request input or confirmation."
        if BLOCKED_RE.search(text):
            return "blocked or errored", "The latest assistant message contains blocker/error language."

    last_message = messages[-1]
    if last_message.role == "assistant":
        return "likely waiting or complete", "The latest visible message is from the assistant and the transcript is idle."
    return "possibly running or awaiting assistant", "The latest visible message is from the user."


def recent_marker_events(summary: SessionSummary) -> list[Event]:
    latest_user_timestamp = ""
    for event in summary.events:
        if event.kind == "message" and event.role == "user":
            latest_user_timestamp = event.timestamp

    markers = [
        event
        for event in summary.events[-80:]
        if event.role == "assistant"
        and (not latest_user_timestamp or event.timestamp >= latest_user_timestamp)
        and (WAIT_RE.search(event.text) or BLOCKED_RE.search(event.text))
    ]
    return markers[-5:]


def filter_events(
    events: list[Event],
    roles: set[str] | None,
    since: datetime | None,
) -> list[Event]:
    selected = events
    if roles is not None:
        selected = [event for event in selected if event.role in roles]
    if since is not None:
        selected = [
            event
            for event in selected
            if (stamp := parse_iso(event.timestamp)) is not None and stamp > since
        ]
    return selected


def list_sessions(home: Path, include_subagents: bool, limit: int, as_json: bool) -> None:
    now = datetime.now(timezone.utc)
    rows = []
    for path in sorted(
        session_files(home, include_subagents=include_subagents),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )[:limit]:
        summary = inspect_path(path, home)
        newest, age = last_activity(summary)
        rows.append(
            {
                "id": summary.id,
                "title": summary.title,
                "last_prompt": compact(summary.last_prompt, 140),
                "project": summary.project,
                "cwd": summary.cwd,
                "updated_at": summary.updated_at or mtime_iso(path),
                "age_seconds": round(age) if age is not None else None,
                "age": humanize_age(age) if age is not None else "unknown",
                "path": str(path),
            }
        )

    if as_json:
        print(json.dumps(rows, indent=2))
        return

    for row in rows:
        title = row["title"] or row["last_prompt"] or "(untitled)"
        print(f"{row['updated_at']}  ({row['age']})  {row['id']}  {title}")
        print(f"  project={row['project']} cwd={row['cwd']}")
        print(f"  {row['path']}")


def summary_to_json(
    summary: SessionSummary,
    limit: int,
    roles: set[str] | None,
    since: datetime | None,
    max_chars: int,
) -> dict[str, Any]:
    state, reason = heuristic_state(summary)
    newest, age = last_activity(summary)
    events = filter_events(summary.events, roles, since)
    effective_running = state in {"likely running", "likely running background work"}
    return {
        "id": summary.id,
        "title": summary.title,
        "last_prompt": summary.last_prompt,
        "project": summary.project,
        "cwd": summary.cwd,
        "model": summary.model,
        "git_branch": summary.git_branch,
        "entrypoint": summary.entrypoint,
        "updated_at": summary.updated_at,
        "last_activity": newest.isoformat() if newest else "",
        "age_seconds": round(age) if age is not None else None,
        "active_recently": effective_running or (age is not None and age <= ACTIVE_WINDOW_SECONDS),
        "path": str(summary.path),
        "state": state,
        "state_reason": reason,
        "raw_event_count": summary.raw_event_count,
        "recent_events": [
            {
                "timestamp": event.timestamp,
                "kind": event.kind,
                "role": event.role,
                "text": compact(event.text, max_chars),
            }
            for event in events[-limit:]
        ],
        "recent_markers": [
            {
                "timestamp": event.timestamp,
                "role": event.role,
                "text": compact(event.text, max_chars),
            }
            for event in recent_marker_events(summary)
        ],
        "child_activity": summary.child_activity,
        "native_agent": summary.native_agent,
    }


def print_summary(
    summary: SessionSummary,
    limit: int,
    roles: set[str] | None,
    since: datetime | None,
    max_chars: int,
) -> None:
    state, reason = heuristic_state(summary)
    newest, age = last_activity(summary)
    title = summary.title or compact(summary.last_prompt, 120) or "(untitled)"
    print(f"Session: {title} ({summary.id or 'unknown id'})")
    print(f"State: {state}")
    print(f"Reason: {reason}")
    if newest:
        print(f"Last activity: {newest.isoformat()} ({humanize_age(age)})")
    else:
        print("Last activity: unknown")
    if summary.project:
        print(f"Project: {summary.project}")
    if summary.cwd:
        print(f"CWD: {summary.cwd}")
    if summary.model:
        print(f"Model: {summary.model}")
    if summary.git_branch:
        print(f"Git branch: {summary.git_branch}")
    print(f"Path: {summary.path}")
    print("")

    if summary.native_agent:
        native = summary.native_agent
        print(
            "Native agent: "
            f"kind={native.get('kind', '')} status={native.get('status', '')} "
            f"state={native.get('state', '')} id={native.get('id', '') or native.get('sessionId', '')}"
        )
        print("")

    if summary.child_activity:
        print("Child activity:")
        for row in summary.child_activity:
            age = humanize_age(float(row["age_seconds"])) if row.get("age_seconds") is not None else "unknown"
            counts = ""
            if row.get("kind") == "workflow":
                counts = f", lanes={row.get('started_lanes', 0)}, unfinished={row.get('unfinished_lanes', 0)}"
            print(f"- {row.get('kind')} {row.get('id')}: {row.get('state')} ({age}{counts})")
            print(f"  {row.get('path')}")
        print("")

    markers = recent_marker_events(summary)
    if markers:
        print("Recent blocker/request markers:")
        for event in markers:
            print(f"- {event.timestamp} {compact(event.text, 240)}")
        print("")

    events = filter_events(summary.events, roles, since)
    shown = events[-limit:]
    label = "Recent events"
    qualifiers = []
    if roles is not None:
        qualifiers.append(f"roles: {','.join(sorted(roles))}")
    if since is not None:
        qualifiers.append(f"since {since.isoformat()}")
    if qualifiers:
        label += f" ({'; '.join(qualifiers)})"
    print(f"{label}:")
    if not shown:
        print("- (no matching events)")
    for event in shown:
        header = f"{event.timestamp} {event.role}/{event.kind}".strip()
        print(f"- {header}: {compact(event.text, max_chars)}")


def latest_message(summary: SessionSummary, role: str) -> Event | None:
    for event in reversed(summary.events):
        if event.kind != "message":
            continue
        if role == "any" or event.role == role:
            return event
    return None


def search_events(summary: SessionSummary, query: str) -> list[Event]:
    query_lower = query.lower()
    return [event for event in summary.events if query_lower in event.text.lower()]


def print_full_message(summary: SessionSummary, role: str, as_json: bool) -> None:
    event = latest_message(summary, role)
    if not event:
        print(f"No {role} message found in {summary.path}", file=sys.stderr)
        raise SystemExit(1)

    newest, age = last_activity(summary)
    payload = {
        "session_id": summary.id,
        "title": summary.title,
        "last_prompt": summary.last_prompt,
        "path": str(summary.path),
        "timestamp": event.timestamp,
        "role": event.role,
        "session_last_activity": newest.isoformat() if newest else "",
        "session_age_seconds": round(age) if age is not None else None,
        "text": event.text,
    }
    if as_json:
        print(json.dumps(payload, indent=2))
        return

    title = summary.title or compact(summary.last_prompt, 120) or "(untitled)"
    print(f"Session: {title} ({summary.id or 'unknown id'})")
    print(f"Message: latest {event.role}")
    print(f"Timestamp: {event.timestamp}")
    if newest:
        print(f"Session last activity: {newest.isoformat()} ({humanize_age(age)})")
    print("")
    print(event.text)


def print_search_results(
    summary: SessionSummary,
    query: str,
    limit: int,
    as_json: bool,
    full: bool,
    roles: set[str] | None,
    since: datetime | None,
    max_chars: int,
) -> None:
    matches = filter_events(search_events(summary, query), roles, since)[-limit:]
    rows = [
        {
            "timestamp": event.timestamp,
            "kind": event.kind,
            "role": event.role,
            "text": event.text if full else compact(event.text, max_chars),
        }
        for event in matches
    ]
    if as_json:
        print(
            json.dumps(
                {
                    "session_id": summary.id,
                    "title": summary.title,
                    "last_prompt": summary.last_prompt,
                    "path": str(summary.path),
                    "query": query,
                    "matches": rows,
                },
                indent=2,
            )
        )
        return

    title = summary.title or compact(summary.last_prompt, 120) or "(untitled)"
    print(f"Session: {title} ({summary.id or 'unknown id'})")
    print(f"Search: {query}")
    print(f"Matches: {len(matches)}")
    print("")
    for row in rows:
        print(f"- {row['timestamp']} {row['role']}/{row['kind']}")
        print(row["text"])
        print("")


def main() -> int:
    args = parse_args()
    home = Path(args.home).expanduser() if args.home else claude_home()
    roles = parse_roles(args.role)
    since = parse_iso(args.since) if args.since else None
    if args.since and since is None:
        print(f"Could not parse --since timestamp: {args.since}", file=sys.stderr)
        return 2
    max_chars = 0 if args.full else args.max_chars

    if args.list:
        list_sessions(home, args.include_subagents, args.limit, args.json)
        return 0

    path = resolve_session_path(home, args)
    if not path:
        print("No session selected. Use --last, --query, --path, or --list.", file=sys.stderr)
        return 2
    if not path.exists():
        print(f"Session transcript not found: {path}", file=sys.stderr)
        return 2

    summary = inspect_path(path, home)
    if args.last_message:
        print_full_message(summary, args.last_message, args.json)
    elif args.search:
        print_search_results(summary, args.search, args.limit, args.json, args.full, roles, since, max_chars)
    elif args.json:
        print(json.dumps(summary_to_json(summary, args.limit, roles, since, max_chars), indent=2))
    else:
        print_summary(summary, args.limit, roles, since, max_chars)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
