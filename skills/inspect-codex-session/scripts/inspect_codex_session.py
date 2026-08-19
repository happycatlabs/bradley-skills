#!/usr/bin/env python3
"""Inspect local Codex session JSONL transcripts.

This is intentionally read-only. It summarizes sessions stored below
$CODEX_HOME or ~/.codex without depending on a stable private API.

Designed for agents coordinating with other agents. Codex lifecycle events
(`task_started`, `task_complete`, and `turn_aborted`) are authoritative when
present; timestamp and message-role heuristics are only fallbacks for older or
ephemeral transcript formats.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


MARKER_RE = re.compile(
    r"\b(blocked|waiting for|need(?:s|ed)? (?:you|input|approval|confirmation|clarification)|"
    r"please (?:confirm|clarify|approve|provide)|question for you|approval|confirm|clarify|"
    r"cannot|can't|failed|error)\b",
    re.IGNORECASE,
)
SESSION_ID_RE = re.compile(r"019[a-z0-9-]{20,}", re.IGNORECASE)

# A transcript updated within this window is treated as actively running.
ACTIVE_WINDOW_SECONDS = 120

VALID_ROLES = {"user", "assistant", "tool", "system"}
LIFECYCLE_KINDS = {"task_started", "task_complete", "turn_aborted"}
TOOL_CALL_KINDS = {
    "function_call",
    "local_shell_call",
    "custom_tool_call",
    "tool_search_call",
    "web_search_call",
}
TOOL_OUTPUT_KINDS = {f"{kind}_output" for kind in TOOL_CALL_KINDS}
AMBIENT_CONTEXT_RE = re.compile(
    r"<in-app-browser-context\b[^>]*>.*?</in-app-browser-context>\s*",
    re.IGNORECASE | re.DOTALL,
)
USER_REQUEST_MARKERS = ("## My request for Codex:", "## My request:")


@dataclass
class SessionIndexEntry:
    id: str
    thread_name: str = ""
    updated_at: str = ""


@dataclass
class Event:
    timestamp: str
    kind: str
    role: str
    text: str
    phase: str = ""
    turn_id: str = ""


@dataclass
class SessionSummary:
    path: Path
    id: str = ""
    thread_name: str = ""
    cwd: str = ""
    model: str = ""
    updated_at: str = ""
    file_mtime: datetime | None = None
    events: list[Event] = field(default_factory=list)
    delegated_tasks: list[dict[str, Any]] = field(default_factory=list)
    raw_event_count: int = 0
    source: str = "transcript"


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect local Codex task/session transcripts from $CODEX_HOME or ~/.codex."
    )
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--last", action="store_true", help="Inspect the most recently updated session.")
    selector.add_argument("--query", "-q", help="Session id, thread name substring, or rollout JSONL path.")
    selector.add_argument("--path", help="Direct path to a rollout JSONL file.")
    selector.add_argument("--list", action="store_true", help="List recent indexed sessions.")
    parser.add_argument("--limit", "-n", type=int, default=10, help="Number of recent events/sessions to show.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--home", help="Override Codex home directory.")
    parser.add_argument(
        "--last-message",
        choices=["assistant", "user", "final", "any"],
        help="Print the latest full message. 'final' selects the latest Codex final_answer.",
    )
    parser.add_argument(
        "--search",
        help="Search extracted event text and print matching events. Useful for finding prior answers without parsing JSONL by hand.",
    )
    parser.add_argument(
        "--role",
        help="Comma-separated roles to include in event views: user,assistant,tool,system. "
        "Role filters do not hide assistant reasoning; use --conversation for that.",
    )
    parser.add_argument(
        "--conversation",
        action="store_true",
        help="Show only user/assistant messages, excluding reasoning, tools, and lifecycle noise.",
    )
    parser.add_argument(
        "--current-turn",
        action="store_true",
        help="Show only the latest turn, beginning at its task_started event or latest user message.",
    )
    parser.add_argument(
        "--raw-context",
        action="store_true",
        help="Preserve known ambient UI context wrappers in displayed user messages.",
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


def load_index(home: Path) -> list[SessionIndexEntry]:
    path = home / "session_index.jsonl"
    entries: list[SessionIndexEntry] = []
    if not path.exists():
        return entries

    try:
        with path.open(errors="replace") as source:
            for line in source:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                session_id = str(data.get("id") or "")
                if not session_id:
                    continue
                entries.append(
                    SessionIndexEntry(
                        id=session_id,
                        thread_name=str(data.get("thread_name") or ""),
                        updated_at=str(data.get("updated_at") or ""),
                    )
                )
    except OSError:
        return []
    return entries


def session_files(home: Path) -> list[Path]:
    roots = [home / "sessions", home / "archived_sessions"]
    files: list[Path] = []
    for root in roots:
        if root.exists():
            files.extend(root.rglob("rollout-*.jsonl"))
    return files


def file_mtime(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def mtime_iso(path: Path) -> str:
    stamp = file_mtime(path)
    return stamp.isoformat() if stamp else ""


def logs_db_paths(home: Path) -> list[Path]:
    return [home / "logs_2.sqlite", home / "sqlite" / "logs_2.sqlite"]


def newest_path(paths: Iterable[Path]) -> Path | None:
    candidates = list(paths)
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def path_id(path: Path) -> str:
    match = SESSION_ID_RE.search(path.name)
    return match.group(0) if match else ""


def resolve_session_path(home: Path, args: argparse.Namespace, index: list[SessionIndexEntry]) -> Path | None:
    files = session_files(home)
    by_id = {path_id(path): path for path in files if path_id(path)}

    if args.path:
        return Path(args.path).expanduser()

    if args.query:
        query = args.query.strip()
        maybe_path = Path(query).expanduser()
        if maybe_path.exists():
            return maybe_path

        if query in by_id:
            return by_id[query]

        id_matches = [sid for sid in by_id if query.lower() in sid.lower()]
        if len(id_matches) == 1:
            return by_id[id_matches[0]]

        indexed_matches = [
            entry
            for entry in index
            if query.lower() in entry.id.lower() or query.lower() in entry.thread_name.lower()
        ]
        indexed_matches.sort(key=lambda entry: entry.updated_at, reverse=True)
        for entry in indexed_matches:
            if entry.id in by_id:
                return by_id[entry.id]

        name_matches = [path for path in files if query.lower() in path.name.lower()]
        return newest_path(name_matches)

    if args.last:
        if index:
            for entry in sorted(index, key=lambda item: item.updated_at, reverse=True):
                if entry.id in by_id:
                    return by_id[entry.id]
        return newest_path(files)

    return None


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
            text = part.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunk for chunk in chunks if chunk)


def compact(text: str, max_chars: int = 600) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if max_chars <= 0 or len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "..."


def clean_user_text(text: str) -> str:
    """Remove Codex Desktop's known ambient wrapper without altering exact logs."""

    cleaned = AMBIENT_CONTEXT_RE.sub("", text).strip()
    for marker in USER_REQUEST_MARKERS:
        if marker in cleaned:
            cleaned = cleaned.rsplit(marker, 1)[1].strip()
            break
    return cleaned or text.strip()


def display_text(event: Event, raw_context: bool = False) -> str:
    if event.role == "user" and not raw_context:
        return clean_user_text(event.text)
    return event.text


def extract_event(line: dict[str, Any]) -> Event | None:
    timestamp = str(line.get("timestamp") or "")
    record_type = str(line.get("type") or "")
    payload = line.get("payload")
    if not isinstance(payload, dict):
        return None

    if record_type == "response_item":
        item_type = str(payload.get("type") or "")
        role = str(payload.get("role") or "")
        if item_type == "message" and role in {"user", "assistant"}:
            text = content_text(payload.get("content"))
            if text:
                return Event(
                    timestamp,
                    "message",
                    role,
                    text,
                    phase=str(payload.get("phase") or ""),
                    turn_id=str(
                        (payload.get("internal_chat_message_metadata_passthrough") or {}).get("turn_id")
                        if isinstance(payload.get("internal_chat_message_metadata_passthrough"), dict)
                        else ""
                    ),
                )
        if item_type in TOOL_CALL_KINDS:
            name = str(payload.get("name") or payload.get("call_id") or item_type)
            status = str(payload.get("status") or "")
            args = payload.get("arguments") or payload.get("input") or payload.get("query")
            text = f"{name} {status}".strip()
            detail = content_text(args) if not isinstance(args, str) else args
            if detail:
                text = f"{text}: {compact(detail, 240)}"
            return Event(timestamp, "tool_call", "tool", text)
        if item_type in TOOL_OUTPUT_KINDS:
            text = content_text(payload.get("output")) or str(payload.get("output") or "")
            return Event(timestamp, "tool_output", "tool", compact(text, 300))

    if record_type == "event_msg":
        event_type = str(payload.get("type") or "")
        if event_type in {"user_message", "agent_message"}:
            role = "user" if event_type == "user_message" else "assistant"
            text = str(payload.get("message") or "")
            if text:
                return Event(
                    timestamp,
                    "message",
                    role,
                    text,
                    phase=str(payload.get("phase") or ""),
                    turn_id=str(payload.get("turn_id") or ""),
                )
        if event_type in LIFECYCLE_KINDS:
            turn_id = str(payload.get("turn_id") or "")
            if event_type == "task_complete":
                text = str(payload.get("last_agent_message") or "Turn completed.")
            elif event_type == "turn_aborted":
                text = str(payload.get("reason") or payload.get("message") or "Turn aborted.")
            else:
                text = "Turn started."
            return Event(timestamp, event_type, "system", text, turn_id=turn_id)
        if event_type == "agent_reasoning":
            text = content_text(payload.get("text")) or str(payload.get("text") or "")
            if text:
                return Event(timestamp, "reasoning", "assistant", text)
        if event_type in {"error", "warning"}:
            text = str(payload.get("message") or payload)
            return Event(timestamp, event_type, "system", text)

    return None


def append_event(events: list[Event], event: Event) -> None:
    """Deduplicate response_item/event_msg mirrors while retaining richer metadata."""

    if events:
        previous = events[-1]
        previous_time = parse_iso(previous.timestamp)
        event_time = parse_iso(event.timestamp)
        timestamps_match = previous.timestamp == event.timestamp or bool(
            previous_time and event_time and abs((event_time - previous_time).total_seconds()) <= 1
        )
        if (
            previous.kind == event.kind
            and previous.role == event.role
            and previous.text == event.text
            and timestamps_match
        ):
            previous.phase = previous.phase or event.phase
            previous.turn_id = previous.turn_id or event.turn_id
            return
    events.append(event)


def inspect_path(path: Path, index: list[SessionIndexEntry]) -> SessionSummary:
    summary = SessionSummary(path=path)
    summary.id = path_id(path)
    summary.file_mtime = file_mtime(path)
    index_by_id = {entry.id: entry for entry in index}
    if summary.id in index_by_id:
        summary.thread_name = index_by_id[summary.id].thread_name
        summary.updated_at = index_by_id[summary.id].updated_at

    try:
        with path.open(errors="replace") as source:
            for raw in source:
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
                payload = line.get("payload")
                if line.get("type") == "session_meta" and isinstance(payload, dict):
                    summary.id = str(payload.get("id") or summary.id)
                    summary.cwd = str(payload.get("cwd") or summary.cwd)
                    summary.model = str(payload.get("model") or payload.get("model_provider") or summary.model)
                elif line.get("type") == "turn_context" and isinstance(payload, dict):
                    summary.cwd = str(payload.get("cwd") or summary.cwd)
                    summary.model = str(payload.get("model") or summary.model)

                event = extract_event(line)
                if event:
                    append_event(summary.events, event)
    except OSError as exc:
        raise SystemExit(f"Could not read {path}: {exc}") from exc

    if not summary.updated_at:
        summary.updated_at = mtime_iso(path)
    if summary.id in index_by_id and not summary.thread_name:
        summary.thread_name = index_by_id[summary.id].thread_name
    return summary


def timestamp_from_log(ts: int, ts_nanos: int) -> str:
    return datetime.fromtimestamp(ts + (ts_nanos / 1_000_000_000), tz=timezone.utc).isoformat()


def parse_debug_string_after(text: str, marker: str) -> str:
    marker_index = text.find(marker)
    if marker_index < 0:
        return ""
    quote_index = text.find('"', marker_index + len(marker))
    if quote_index < 0:
        return ""

    escaped = False
    for index in range(quote_index + 1, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            raw = text[quote_index : index + 1]
            try:
                return str(json.loads(raw))
            except json.JSONDecodeError:
                return raw.strip('"')
    return ""


def normalize_task_status(status: Any) -> str:
    if isinstance(status, str):
        return status
    if isinstance(status, dict):
        return str(status.get("type") or status.get("status") or "")
    return ""


def extract_delegated_tasks(events: list[Event], source_thread_id: str) -> list[dict[str, Any]]:
    """Find app-managed child tasks explicitly delegated from a side chat."""

    tasks_by_id: dict[str, dict[str, Any]] = {}
    source_marker = f"<source_thread_id>{source_thread_id}</source_thread_id>"

    for event in events:
        if event.kind != "tool_output":
            continue
        try:
            payload = json.loads(event.text)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(payload, dict):
            continue

        candidates: list[dict[str, Any]] = []
        threads = payload.get("threads")
        if isinstance(threads, list):
            candidates.extend(thread for thread in threads if isinstance(thread, dict))
        thread = payload.get("thread")
        if isinstance(thread, dict):
            candidates.append(thread)

        for candidate in candidates:
            task_id = str(candidate.get("id") or candidate.get("threadId") or "")
            preview = str(candidate.get("preview") or "")
            if not task_id or source_marker not in preview:
                continue

            existing = tasks_by_id.get(task_id, {})
            task = {
                "id": task_id,
                "host_id": str(candidate.get("hostId") or existing.get("host_id") or ""),
                "title": str(candidate.get("title") or existing.get("title") or ""),
                "status": normalize_task_status(candidate.get("status")) or str(existing.get("status") or ""),
                "cwd": str(candidate.get("cwd") or existing.get("cwd") or ""),
                "updated_at": candidate.get("updatedAt") or existing.get("updated_at"),
            }
            tasks_by_id[task_id] = task

    return list(tasks_by_id.values())


def resolve_ephemeral_thread_id(db_path: Path, query: str) -> str:
    if not db_path.exists():
        return ""
    like_query = f"{query}%"
    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                """
                SELECT thread_id, max(ts) AS latest_ts
                FROM logs
                WHERE thread_id = ?
                   OR thread_id LIKE ?
                GROUP BY thread_id
                ORDER BY latest_ts DESC
                LIMIT 2
                """,
                (query, like_query),
            ).fetchall()
    except sqlite3.Error:
        return ""

    thread_ids = [str(row[0] or "") for row in rows if row[0]]
    return thread_ids[0] if len(thread_ids) == 1 else ""


def inspect_ephemeral_thread(home: Path, query: str) -> SessionSummary | None:
    if not query:
        return None

    for db_path in logs_db_paths(home):
        thread_id = resolve_ephemeral_thread_id(db_path, query)
        if not thread_id:
            continue

        summary = SessionSummary(
            path=db_path,
            id=thread_id,
            thread_name="(ephemeral side chat)",
            # The log DB mtime is global to all Codex activity, not this side
            # chat. Use only this thread's latest log timestamp for liveness.
            file_mtime=None,
            source="ephemeral_logs",
        )
        try:
            with sqlite3.connect(db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT ts, ts_nanos, target, feedback_log_body
                    FROM logs
                    WHERE thread_id = ?
                      AND (
                        feedback_log_body LIKE '%Submission sub=Submission%'
                        OR feedback_log_body LIKE '%OutputText { text:%'
                      )
                    ORDER BY ts ASC, ts_nanos ASC, id ASC
                    """,
                    (thread_id,),
                ).fetchall()
        except sqlite3.Error:
            return None

        for ts, ts_nanos, target, body in rows:
            summary.raw_event_count += 1
            timestamp = timestamp_from_log(int(ts), int(ts_nanos))
            summary.updated_at = timestamp
            body_text = str(body or "")
            if not summary.cwd:
                cwd = parse_debug_string_after(body_text, "legacy_fallback_cwd: AbsolutePathBuf(")
                if cwd:
                    summary.cwd = cwd
            if not summary.model:
                model_match = re.search(r"model=([a-zA-Z0-9._-]+)", body_text)
                if model_match:
                    summary.model = model_match.group(1)

            if "Submission sub=Submission" in body_text and "op: UserInput {" in body_text:
                user_text = parse_debug_string_after(body_text, "Text { text: ")
                if user_text:
                    summary.events.append(Event(timestamp, "message", "user", user_text))
            elif "Submission sub=Submission" in body_text and "op: DynamicToolResponse {" in body_text:
                tool_text = parse_debug_string_after(body_text, "InputText { text: ")
                if tool_text:
                    summary.events.append(Event(timestamp, "tool_output", "tool", tool_text))
            elif "OutputText { text:" in body_text:
                assistant_text = parse_debug_string_after(body_text, "OutputText { text: ")
                if assistant_text:
                    phase = ""
                    if "phase: Some(Commentary)" in body_text:
                        phase = "commentary"
                    elif "phase: Some(FinalAnswer)" in body_text:
                        phase = "final_answer"
                    summary.events.append(Event(timestamp, "message", "assistant", assistant_text, phase=phase))

        if summary.events:
            summary.delegated_tasks = extract_delegated_tasks(summary.events, summary.id)
            return summary

    return None


def latest_message_event(summary: SessionSummary, role: str | None = None) -> Event | None:
    for event in reversed(summary.events):
        if event.kind == "message" and (role is None or event.role == role):
            return event
    return None


def marker_state(event: Event | None) -> tuple[str, str] | None:
    if not event:
        return None
    text = re.sub(r"\b(?:no|zero|0)\s+(?:errors?|failures?|failed checks?)\b", "", event.text, flags=re.I)
    if re.search(r"\b(blocked|failed|error|cannot|can't)\b", text, re.I):
        return "blocked; waiting for user", "The completed turn reports a blocker or error."
    if text.rstrip().endswith("?") or re.search(r"\b(please|need|confirm|clarify|approval)\b", text, re.I):
        return "waiting for user", "The latest assistant message requests input or confirmation."
    return None


def heuristic_state(summary: SessionSummary) -> tuple[str, str]:
    messages = [event for event in summary.events if event.kind == "message"]
    lifecycle = [event for event in summary.events if event.kind in LIFECYCLE_KINDS]
    _, age = last_activity(summary)
    recently_active = age is not None and age <= ACTIVE_WINDOW_SECONDS

    if lifecycle:
        latest = lifecycle[-1]
        latest_user = latest_message_event(summary, "user")
        user_after_lifecycle = bool(latest_user and latest_user.timestamp > latest.timestamp)

        if latest.kind == "task_complete" and not user_after_lifecycle:
            marker = marker_state(latest_message_event(summary, "assistant") or latest)
            if marker:
                return marker
            return (
                "turn complete; waiting for user",
                "Codex emitted task_complete for the latest turn. Recent file activity does not override completion.",
            )
        if latest.kind == "turn_aborted" and not user_after_lifecycle:
            return "turn interrupted; waiting for user", "Codex emitted turn_aborted for the latest turn."
        if latest.kind == "task_started":
            if recently_active:
                return "running", "The latest Codex lifecycle event is task_started and the transcript is active."
            return (
                "possibly stalled or stopped mid-turn",
                f"The latest lifecycle event is task_started, but the transcript has been idle for "
                f"{humanize_age(age) if age is not None else 'an unknown time'}.",
            )
        if user_after_lifecycle:
            return "queued or starting", "A user message arrived after the latest completed/interrupted turn."

    if not messages:
        return "unknown", "No user/assistant messages or usable lifecycle boundary were found in the transcript."

    if recently_active:
        return (
            "likely running",
            f"No Codex lifecycle events were available; recent transcript activity ({humanize_age(age)}) suggests it may be live.",
        )

    if summary.events and summary.events[-1].kind in {"tool_call", "tool_output"}:
        return (
            "possibly running tools or stopped mid-turn",
            "The latest visible event is tool activity after the latest assistant/user message, "
            f"but the transcript has been idle for {humanize_age(age) if age is not None else 'an unknown time'}.",
        )

    marker = marker_state(latest_message_event(summary, "assistant"))
    if marker:
        return marker

    last_message = messages[-1]
    if last_message.role == "assistant":
        return "likely waiting or complete", "The latest visible message is from the assistant and the transcript is idle."
    return "possibly running or awaiting assistant", "The latest visible message is from the user."


def recent_marker_events(summary: SessionSummary) -> list[Event]:
    messages = [event for event in summary.events if event.kind == "message"]
    latest_user_timestamp = ""
    for event in messages:
        if event.role == "user":
            latest_user_timestamp = event.timestamp

    markers = [
        event
        for event in summary.events[-80:]
        if event.role == "assistant"
        and event.kind == "message"
        and (not latest_user_timestamp or event.timestamp >= latest_user_timestamp)
        and MARKER_RE.search(event.text)
    ]
    return markers[-5:]


def filter_events(
    events: list[Event],
    roles: set[str] | None,
    since: datetime | None,
    conversation: bool = False,
    current_turn: bool = False,
) -> list[Event]:
    selected = events
    if current_turn and selected:
        task_starts = [event for event in selected if event.kind == "task_started"]
        start = task_starts[-1].timestamp if task_starts else ""
        if not start:
            users = [event for event in selected if event.kind == "message" and event.role == "user"]
            start = users[-1].timestamp if users else ""
        if start:
            selected = [event for event in selected if event.timestamp >= start]
    if conversation:
        selected = [event for event in selected if event.kind == "message" and event.role in {"user", "assistant"}]
    if roles is not None:
        selected = [event for event in selected if event.role in roles]
    if since is not None:
        selected = [
            event
            for event in selected
            if (stamp := parse_iso(event.timestamp)) is not None and stamp > since
        ]
    return selected


def list_sessions(home: Path, index: list[SessionIndexEntry], limit: int, as_json: bool) -> None:
    files_by_id = {path_id(path): path for path in session_files(home) if path_id(path)}
    now = datetime.now(timezone.utc)
    deduped: dict[str, SessionIndexEntry] = {}
    for entry in sorted(index, key=lambda item: item.updated_at):
        deduped[entry.id] = entry
    rows = []
    for entry in sorted(deduped.values(), key=lambda item: item.updated_at, reverse=True)[:limit]:
        path = files_by_id.get(entry.id)
        age_seconds: float | None = None
        stamps = [stamp for stamp in (parse_iso(entry.updated_at), file_mtime(path) if path else None) if stamp]
        if stamps:
            age_seconds = (now - max(stamps)).total_seconds()
        rows.append(
            {
                "id": entry.id,
                "thread_name": entry.thread_name,
                "updated_at": entry.updated_at,
                "age_seconds": round(age_seconds) if age_seconds is not None else None,
                "age": humanize_age(age_seconds) if age_seconds is not None else "unknown",
                "path": str(path) if path else "",
            }
        )

    if as_json:
        print(json.dumps(rows, indent=2))
        return

    for row in rows:
        print(f"{row['updated_at']}  ({row['age']})  {row['id']}  {row['thread_name']}")
        if row["path"]:
            print(f"  {row['path']}")


def summary_to_json(
    summary: SessionSummary,
    limit: int,
    roles: set[str] | None,
    since: datetime | None,
    max_chars: int,
    conversation: bool,
    current_turn: bool,
    raw_context: bool,
) -> dict[str, Any]:
    state, reason = heuristic_state(summary)
    markers = recent_marker_events(summary)
    newest, age = last_activity(summary)
    events = filter_events(summary.events, roles, since, conversation, current_turn)
    current_request = latest_message_event(summary, "user")
    latest_assistant = latest_message_event(summary, "assistant")
    latest_final = latest_message(summary, "final")
    latest_lifecycle = next((event for event in reversed(summary.events) if event.kind in LIFECYCLE_KINDS), None)
    return {
        "id": summary.id,
        "task_id": summary.id,
        "thread_name": summary.thread_name,
        "indexed_title": summary.thread_name,
        "current_request": compact(display_text(current_request, raw_context), max_chars) if current_request else "",
        "latest_assistant_message": compact(latest_assistant.text, max_chars) if latest_assistant else "",
        "latest_assistant_phase": latest_assistant.phase if latest_assistant else "",
        "latest_final_answer": compact(latest_final.text, max_chars) if latest_final else "",
        "cwd": summary.cwd,
        "model": summary.model,
        "updated_at": summary.updated_at,
        "last_activity": newest.isoformat() if newest else "",
        "age_seconds": round(age) if age is not None else None,
        "active_recently": age is not None and age <= ACTIVE_WINDOW_SECONDS,
        "turn_active": state == "running" or state == "likely running",
        "path": str(summary.path),
        "source": summary.source,
        "state": state,
        "state_reason": reason,
        "state_authority": "lifecycle" if latest_lifecycle else "heuristic",
        "latest_lifecycle": {
            "kind": latest_lifecycle.kind,
            "timestamp": latest_lifecycle.timestamp,
            "turn_id": latest_lifecycle.turn_id,
        }
        if latest_lifecycle
        else None,
        "raw_event_count": summary.raw_event_count,
        "delegated_tasks": summary.delegated_tasks,
        "recent_events": [
            {
                "timestamp": event.timestamp,
                "kind": event.kind,
                "role": event.role,
                "phase": event.phase,
                "turn_id": event.turn_id,
                "text": compact(display_text(event, raw_context), max_chars),
            }
            for event in events[-limit:]
        ],
        "recent_markers": [
            {
                "timestamp": event.timestamp,
                "role": event.role,
                "text": compact(event.text, max_chars),
            }
            for event in markers
        ],
    }


def print_summary(
    summary: SessionSummary,
    limit: int,
    roles: set[str] | None,
    since: datetime | None,
    max_chars: int,
    conversation: bool,
    current_turn: bool,
    raw_context: bool,
) -> None:
    state, reason = heuristic_state(summary)
    newest, age = last_activity(summary)
    title = summary.thread_name or "(untitled)"
    print(f"Task: {title} ({summary.id or 'unknown id'})")
    print(f"State: {state}")
    print(f"Reason: {reason}")
    if newest:
        print(f"Last activity: {newest.isoformat()} ({humanize_age(age)})")
    else:
        print("Last activity: unknown")
    if summary.cwd:
        print(f"CWD: {summary.cwd}")
    if summary.model:
        print(f"Model: {summary.model}")
    current_request = latest_message_event(summary, "user")
    if current_request:
        print(f"Current request: {compact(display_text(current_request, raw_context), 240)}")
    print(f"Path: {summary.path}")
    if summary.source != "transcript":
        print(f"Source: {summary.source}")
    if summary.delegated_tasks:
        print("Delegated tasks:")
        for task in summary.delegated_tasks:
            details = " — ".join(
                detail
                for detail in (
                    str(task.get("status") or ""),
                    str(task.get("title") or ""),
                    str(task.get("cwd") or ""),
                )
                if detail
            )
            suffix = f" — {details}" if details else ""
            print(f"- {task['id']}{suffix}")
    print("")

    markers = recent_marker_events(summary)
    if markers:
        print("Recent blocker/request markers:")
        for event in markers[-5:]:
            print(f"- {event.timestamp} {compact(event.text, 240)}")
        print("")

    events = filter_events(summary.events, roles, since, conversation, current_turn)
    shown = events[-limit:]
    label = "Recent events"
    qualifiers = []
    if roles is not None:
        qualifiers.append(f"roles: {','.join(sorted(roles))}")
    if since is not None:
        qualifiers.append(f"since {since.isoformat()}")
    if conversation:
        qualifiers.append("conversation only")
    if current_turn:
        qualifiers.append("current turn")
    if qualifiers:
        label += f" ({'; '.join(qualifiers)})"
    print(f"{label}:")
    if not shown:
        print("- (no matching events)")
    for event in shown:
        phase = f"/{event.phase}" if event.phase else ""
        header = f"{event.timestamp} {event.role}/{event.kind}{phase}".strip()
        print(f"- {header}: {compact(display_text(event, raw_context), max_chars)}")


def latest_message(summary: SessionSummary, role: str) -> Event | None:
    for event in reversed(summary.events):
        if event.kind != "message":
            continue
        if role == "final" and event.role == "assistant" and event.phase == "final_answer":
            return event
        if role == "any" or event.role == role:
            return event
    return None


def search_events(summary: SessionSummary, query: str) -> list[Event]:
    query_lower = query.lower()
    return [event for event in summary.events if query_lower in event.text.lower()]


def print_full_message(summary: SessionSummary, role: str, as_json: bool, raw_context: bool) -> None:
    event = latest_message(summary, role)
    if not event:
        print(f"No {role} message found in {summary.path}", file=sys.stderr)
        raise SystemExit(1)

    newest, age = last_activity(summary)
    payload = {
        "session_id": summary.id,
        "thread_name": summary.thread_name,
        "path": str(summary.path),
        "source": summary.source,
        "timestamp": event.timestamp,
        "role": event.role,
        "phase": event.phase,
        "session_last_activity": newest.isoformat() if newest else "",
        "session_age_seconds": round(age) if age is not None else None,
        "text": display_text(event, raw_context),
    }
    if as_json:
        print(json.dumps(payload, indent=2))
        return

    print(f"Task: {summary.thread_name or '(untitled)'} ({summary.id or 'unknown id'})")
    label = "final_answer" if role == "final" else event.role
    print(f"Message: latest {label}")
    print(f"Timestamp: {event.timestamp}")
    if newest:
        print(f"Session last activity: {newest.isoformat()} ({humanize_age(age)})")
    print("")
    print(display_text(event, raw_context))


def print_search_results(
    summary: SessionSummary,
    query: str,
    limit: int,
    as_json: bool,
    full: bool,
    roles: set[str] | None,
    since: datetime | None,
    max_chars: int,
    conversation: bool,
    current_turn: bool,
    raw_context: bool,
) -> None:
    matches = filter_events(search_events(summary, query), roles, since, conversation, current_turn)[-limit:]
    rows = [
        {
            "timestamp": event.timestamp,
            "kind": event.kind,
            "role": event.role,
            "phase": event.phase,
            "text": display_text(event, raw_context) if full else compact(display_text(event, raw_context), max_chars),
        }
        for event in matches
    ]
    if as_json:
        print(
            json.dumps(
                {
                    "session_id": summary.id,
                    "thread_name": summary.thread_name,
                    "path": str(summary.path),
                    "source": summary.source,
                    "query": query,
                    "matches": rows,
                },
                indent=2,
            )
        )
        return

    print(f"Task: {summary.thread_name or '(untitled)'} ({summary.id or 'unknown id'})")
    print(f"Search: {query}")
    print(f"Matches: {len(matches)}")
    print("")
    for row in rows:
        phase = f"/{row['phase']}" if row["phase"] else ""
        print(f"- {row['timestamp']} {row['role']}/{row['kind']}{phase}")
        print(row["text"])
        print("")


def main() -> int:
    args = parse_args()
    home = Path(args.home).expanduser() if args.home else codex_home()
    index = load_index(home)
    roles = parse_roles(args.role)
    since = parse_iso(args.since) if args.since else None
    if args.since and since is None:
        print(f"Could not parse --since timestamp: {args.since}", file=sys.stderr)
        return 2
    max_chars = 0 if args.full else args.max_chars

    if args.list:
        list_sessions(home, index, args.limit, args.json)
        return 0

    path = resolve_session_path(home, args, index)
    if not path:
        summary = inspect_ephemeral_thread(home, args.query.strip()) if args.query else None
        if not summary:
            print("No session selected. Use --last, --query, --path, or --list.", file=sys.stderr)
            return 2
    elif not path.exists():
        print(f"Session transcript not found: {path}", file=sys.stderr)
        return 2
    else:
        summary = inspect_path(path, index)

    if args.last_message:
        print_full_message(summary, args.last_message, args.json, args.raw_context)
    elif args.search:
        print_search_results(
            summary,
            args.search,
            args.limit,
            args.json,
            args.full,
            roles,
            since,
            max_chars,
            args.conversation,
            args.current_turn,
            args.raw_context,
        )
    elif args.json:
        print(
            json.dumps(
                summary_to_json(
                    summary,
                    args.limit,
                    roles,
                    since,
                    max_chars,
                    args.conversation,
                    args.current_turn,
                    args.raw_context,
                ),
                indent=2,
            )
        )
    else:
        print_summary(
            summary,
            args.limit,
            roles,
            since,
            max_chars,
            args.conversation,
            args.current_turn,
            args.raw_context,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
