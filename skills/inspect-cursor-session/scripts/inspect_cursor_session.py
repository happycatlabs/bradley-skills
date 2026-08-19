#!/usr/bin/env python3
"""Inspect local Cursor composer/agent JSONL transcripts.

This is intentionally read-only. It combines Cursor's global composer index
with transcripts stored below $CURSOR_HOME or ~/.cursor.
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
from urllib.parse import unquote, urlparse


UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
COMPOSER_ID_RE = re.compile(
    rf"\bcomposerId=(?P<id>{UUID_RE.pattern})\b",
    re.IGNORECASE,
)
MARKER_RE = re.compile(
    r"\b(blocked|waiting for|need(?:s|ed)? (?:you|input|approval|confirmation|clarification)|"
    r"please (?:confirm|clarify|approve|provide)|question for you|approval|confirm|clarify|"
    r"cannot|can't|failed|error|what would you like|want me to|should i)\b",
    re.IGNORECASE,
)
ASK_RE = re.compile(r"(\?|want me to|should i|please confirm|please choose)", re.IGNORECASE)


@dataclass
class ComposerHeader:
    id: str
    name: str = ""
    workspace_id: str = ""
    workspace_path: str = ""
    created_at_ms: int = 0
    updated_at_ms: int = 0
    mode: str = ""
    force_mode: str = ""
    archived: bool = False
    draft: bool = False
    pending_plan: bool = False
    blocking_pending_actions: bool = False
    subtitle: str = ""


@dataclass
class Event:
    timestamp: str
    kind: str
    role: str
    text: str


@dataclass(frozen=True)
class RequestReference:
    request_id: str
    session_id: str = ""
    transcript_path: Path | None = None
    source_kind: str = ""
    source_path: Path | None = None


@dataclass
class CursorSession:
    path: Path
    id: str
    project_key: str = ""
    parent_id: str = ""
    is_subagent: bool = False
    name: str = ""
    workspace_id: str = ""
    workspace_path: str = ""
    mode: str = ""
    updated_at: str = ""
    updated_ms: int = 0
    state: str = "unknown"
    events: list[Event] = field(default_factory=list)
    raw_event_count: int = 0
    blocking_pending_actions: bool = False
    pending_plan: bool = False
    request_id: str = ""
    resolved_by: str = ""
    resolution_source: str = ""
    metadata_source: str = ""
    has_conversation: bool | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect local Cursor agent/composer transcripts from $CURSOR_HOME or ~/.cursor."
    )
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--last", action="store_true", help="Inspect the most recently updated session.")
    selector.add_argument("--query", "-q", help="Composer id, request id, title, workspace, prompt substring, or JSONL path.")
    selector.add_argument("--session-id", help="Inspect an exact Cursor composer/session id.")
    selector.add_argument("--request-id", help="Resolve a Cursor UI request id to its composer/session.")
    selector.add_argument("--path", help="Direct path to a Cursor transcript JSONL file.")
    selector.add_argument("--list", action="store_true", help="List recent Cursor sessions.")
    parser.add_argument("--limit", "-n", type=int, default=10, help="Number of recent events/sessions to show.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--home", help="Override Cursor home directory.")
    parser.add_argument("--app-support", help="Override Cursor application support directory.")
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
        "--full",
        action="store_true",
        help="With --search, print full matching event text instead of compact snippets.",
    )
    return parser.parse_args()


def cursor_home(args: argparse.Namespace) -> Path:
    return Path(args.home or os.environ.get("CURSOR_HOME", "~/.cursor")).expanduser()


def cursor_app_support(args: argparse.Namespace) -> Path:
    default = "~/Library/Application Support/Cursor"
    return Path(args.app_support or os.environ.get("CURSOR_APP_SUPPORT", default)).expanduser()


def ms_to_iso(ms: int) -> str:
    if not ms:
        return ""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def mtime_ms(path: Path) -> int:
    try:
        return int(path.stat().st_mtime * 1000)
    except OSError:
        return 0


def file_uri_to_path(uri: str) -> str:
    if not uri:
        return ""
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return uri
    return unquote(parsed.path)


def load_sqlite_value(db_path: Path, key: str) -> str:
    if not db_path.exists():
        return ""
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = con.execute("select value from ItemTable where key = ?", (key,)).fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return ""
    if not row:
        return ""
    value = row[0]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def load_workspace_map(app_support: Path) -> dict[str, str]:
    workspace_paths: dict[str, str] = {}
    storage_root = app_support / "User" / "workspaceStorage"
    if storage_root.exists():
        for workspace_json in storage_root.glob("*/workspace.json"):
            try:
                data = json.loads(workspace_json.read_text(errors="replace"))
            except (OSError, json.JSONDecodeError):
                continue
            uri = str(data.get("folder") or data.get("workspace") or "")
            path = file_uri_to_path(uri)
            if path:
                workspace_paths[workspace_json.parent.name] = path

    global_db = app_support / "User" / "globalStorage" / "state.vscdb"
    raw = load_sqlite_value(global_db, "workspaceMetadata.entries")
    if raw:
        try:
            data = json.loads(raw)
            for entry in data.get("entries", []):
                if not isinstance(entry, dict):
                    continue
                workspace_id = str(entry.get("workspaceId") or "")
                uri = str(entry.get("folderUri") or "")
                display_path = str(entry.get("displayPath") or "")
                path = file_uri_to_path(uri) or display_path
                if workspace_id and path:
                    workspace_paths.setdefault(workspace_id, path)
        except json.JSONDecodeError:
            pass
    return workspace_paths


def load_composer_headers(app_support: Path, workspace_paths: dict[str, str]) -> dict[str, ComposerHeader]:
    global_db = app_support / "User" / "globalStorage" / "state.vscdb"
    raw = load_sqlite_value(global_db, "composer.composerHeaders")
    if not raw:
        return {}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}

    headers: dict[str, ComposerHeader] = {}
    for item in data.get("allComposers", []):
        if not isinstance(item, dict):
            continue
        composer_id = str(item.get("composerId") or "")
        if not composer_id:
            continue

        workspace_identifier = item.get("workspaceIdentifier")
        workspace_id = ""
        workspace_path = ""
        if isinstance(workspace_identifier, dict):
            workspace_id = str(workspace_identifier.get("id") or "")
            uri = workspace_identifier.get("uri")
            if isinstance(uri, dict):
                workspace_path = str(uri.get("fsPath") or file_uri_to_path(str(uri.get("external") or "")))

        workspace_path = workspace_path or workspace_paths.get(workspace_id, "")
        updated = int(item.get("lastUpdatedAt") or item.get("conversationCheckpointLastUpdatedAt") or 0)
        created = int(item.get("createdAt") or 0)

        headers[composer_id] = ComposerHeader(
            id=composer_id,
            name=str(item.get("name") or ""),
            workspace_id=workspace_id,
            workspace_path=workspace_path,
            created_at_ms=created,
            updated_at_ms=updated or created,
            mode=str(item.get("unifiedMode") or ""),
            force_mode=str(item.get("forceMode") or ""),
            archived=bool(item.get("isArchived")),
            draft=bool(item.get("isDraft")),
            pending_plan=bool(item.get("hasPendingPlan")),
            blocking_pending_actions=bool(item.get("hasBlockingPendingActions")),
            subtitle=str(item.get("subtitle") or ""),
        )
    return headers


def load_cli_chat_headers(home: Path) -> tuple[dict[str, ComposerHeader], dict[str, bool]]:
    """Load headless Cursor Agent metadata from ~/.cursor/chats.

    CLI sessions do not appear in the IDE composerHeaders index. Their public
    local metadata is enough to recover identity, cwd, title, and liveness even
    when a mirrored JSONL transcript is absent.
    """
    headers: dict[str, ComposerHeader] = {}
    conversations: dict[str, bool] = {}
    chats_root = home / "chats"
    if not chats_root.exists():
        return headers, conversations
    for meta_path in chats_root.glob("*/*/meta.json"):
        data = load_json_file(meta_path)
        if not data:
            continue
        session_id = meta_path.parent.name
        if not UUID_RE.fullmatch(session_id):
            continue
        created = int(data.get("createdAtMs") or 0)
        updated = int(data.get("updatedAtMs") or created)
        headers[session_id] = ComposerHeader(
            id=session_id,
            name=str(data.get("title") or ""),
            workspace_path=str(data.get("cwd") or ""),
            created_at_ms=created,
            updated_at_ms=updated,
        )
        conversations[session_id] = bool(data.get("hasConversation"))
    return headers, conversations


def load_json_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def transcript_files(home: Path) -> list[Path]:
    root = home / "projects"
    if not root.exists():
        return []
    return sorted(root.glob("*/agent-transcripts/**/*.jsonl"))


def find_request_trace_reference(app_support: Path, request_id: str) -> RequestReference | None:
    """Resolve an active or completed request from Cursor's request trace logs."""
    logs_root = app_support / "logs"
    if not logs_root.exists():
        return None

    needle = f"requestid={request_id.lower()}"
    trace_logs = sorted(logs_root.rglob("cursor.requestTraces.log"), key=mtime_ms, reverse=True)
    for log_path in trace_logs:
        try:
            with log_path.open(errors="replace") as log_file:
                for line in log_file:
                    if needle not in line.lower():
                        continue
                    composer_match = COMPOSER_ID_RE.search(line)
                    if composer_match:
                        return RequestReference(
                            request_id=request_id,
                            session_id=composer_match.group("id"),
                            source_kind="request trace",
                            source_path=log_path,
                        )
        except OSError:
            continue
    return None


def json_object_after_input(text: str, match_index: int) -> dict[str, Any]:
    input_index = text.rfind("INPUT:", max(0, match_index - 100_000), match_index)
    if input_index < 0:
        return {}
    object_start = text.find("{", input_index, match_index + 1)
    if object_start < 0:
        return {}
    try:
        data, _ = json.JSONDecoder().raw_decode(text[object_start:])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def find_hook_generation_reference(app_support: Path, generation_id: str) -> RequestReference | None:
    """Resolve a request from hook INPUT payloads, preferring a transcript path."""
    if not UUID_RE.fullmatch(generation_id):
        return None
    logs_root = app_support / "logs"
    if not logs_root.exists():
        return None

    fallback: RequestReference | None = None
    for log_path in sorted(logs_root.rglob("cursor.hooks*.log"), key=mtime_ms, reverse=True):
        try:
            text = log_path.read_text(errors="replace")
        except OSError:
            continue
        start_search = 0
        while True:
            index = text.find(generation_id, start_search)
            if index < 0:
                break
            data = json_object_after_input(text, index)
            if str(data.get("generation_id") or "").lower() == generation_id.lower():
                transcript = str(data.get("transcript_path") or "")
                session_id = str(data.get("session_id") or data.get("conversation_id") or "")
                reference = RequestReference(
                    request_id=generation_id,
                    session_id=session_id,
                    transcript_path=Path(transcript).expanduser() if transcript else None,
                    source_kind="hook input",
                    source_path=log_path,
                )
                if reference.transcript_path:
                    return reference
                if reference.session_id and fallback is None:
                    fallback = reference
            start_search = index + len(generation_id)
    return fallback


def find_generation_reference(app_support: Path, generation_id: str) -> RequestReference | None:
    """Resolve a Cursor UI request id/generation_id to a transcript or session."""
    if not UUID_RE.fullmatch(generation_id):
        return None
    return find_request_trace_reference(app_support, generation_id) or find_hook_generation_reference(
        app_support, generation_id
    )


def ids_from_path(path: Path) -> tuple[str, str, bool, str]:
    parts = path.parts
    project_key = ""
    parent_id = ""
    is_subagent = "subagents" in parts
    try:
        projects_index = parts.index("projects")
        project_key = parts[projects_index + 1]
    except (ValueError, IndexError):
        pass
    ids = UUID_RE.findall(str(path))
    session_id = ids[-1] if ids else path.stem
    if is_subagent and len(ids) >= 2:
        parent_id = ids[-2]
    return session_id, parent_id, is_subagent, project_key


def compact(text: str, max_chars: int = 600) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "..."


def clean_text(text: str) -> str:
    text = re.sub(r"<timestamp>.*?</timestamp>", "", text, flags=re.DOTALL)
    text = text.replace("<user_query>", "").replace("</user_query>", "")
    text = re.sub(r"<manually_attached_skills>.*?</manually_attached_skills>", "", text, flags=re.DOTALL)
    return text.strip()


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
            if part.get("type") == "text" and isinstance(part.get("text"), str):
                chunks.append(part["text"])
            elif isinstance(part.get("text"), str):
                chunks.append(part["text"])
    return "\n".join(chunk for chunk in chunks if chunk)


def event_timestamp(raw: dict[str, Any], fallback_ms: int = 0) -> str:
    for key in ("timestamp", "createdAt", "time"):
        value = raw.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, (int, float)) and value:
            ms = int(value if value > 10_000_000_000 else value * 1000)
            return ms_to_iso(ms)
    return ms_to_iso(fallback_ms)


def extract_events(raw: dict[str, Any], fallback_ms: int = 0) -> list[Event]:
    timestamp = event_timestamp(raw, fallback_ms)
    role = str(raw.get("role") or raw.get("type") or "")
    message = raw.get("message") if isinstance(raw.get("message"), dict) else raw
    content = message.get("content") if isinstance(message, dict) else None
    events: list[Event] = []

    if isinstance(content, list):
        text_chunks: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            part_type = str(part.get("type") or "")
            if part_type == "text":
                text = clean_text(str(part.get("text") or ""))
                if text:
                    text_chunks.append(text)
            elif part_type == "tool_use":
                name = str(part.get("name") or "tool")
                tool_input = part.get("input")
                detail = ""
                if isinstance(tool_input, dict):
                    detail = json.dumps(tool_input, ensure_ascii=False, sort_keys=True)
                elif tool_input:
                    detail = str(tool_input)
                events.append(Event(timestamp, "tool_call", "tool", compact(f"{name}: {detail}", 320)))
            elif part_type in {"tool_result", "tool_output"}:
                text = content_text(part.get("content")) or str(part.get("content") or "")
                events.append(Event(timestamp, "tool_output", "tool", compact(text, 320)))
        if text_chunks:
            events.insert(0, Event(timestamp, "message", role or "assistant", "\n".join(text_chunks)))
        return events

    text = clean_text(content_text(content))
    if text:
        return [Event(timestamp, "message", role or "unknown", text)]

    if "tool" in role.lower() or "result" in role.lower():
        text = clean_text(json.dumps(raw, ensure_ascii=False, sort_keys=True))
        return [Event(timestamp, "tool_output", "tool", compact(text, 320))]

    return []


def inspect_path(path: Path, headers: dict[str, ComposerHeader]) -> CursorSession:
    session_id, parent_id, is_subagent, project_key = ids_from_path(path)
    header = headers.get(parent_id if is_subagent else session_id) or headers.get(session_id)
    file_ms = mtime_ms(path)
    session = CursorSession(
        path=path,
        id=session_id,
        parent_id=parent_id,
        is_subagent=is_subagent,
        project_key=project_key,
        updated_ms=file_ms,
        updated_at=ms_to_iso(file_ms),
    )
    if header:
        session.name = header.name
        session.workspace_id = header.workspace_id
        session.workspace_path = header.workspace_path
        session.mode = header.mode
        session.blocking_pending_actions = header.blocking_pending_actions
        session.pending_plan = header.pending_plan
        if header.updated_at_ms:
            session.updated_ms = max(file_ms, header.updated_at_ms)
            session.updated_at = ms_to_iso(session.updated_ms)

    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError as exc:
        raise SystemExit(f"Could not read {path}: {exc}") from exc

    for raw_line in lines:
        if not raw_line.strip():
            continue
        try:
            raw = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        session.raw_event_count += 1
        session.events.extend(extract_events(raw, session.updated_ms))

    if session.events:
        session.updated_at = session.events[-1].timestamp or session.updated_at
    session.state = infer_state(session)
    return session


def infer_state(session: CursorSession) -> str:
    if session.blocking_pending_actions:
        return "blocked or waiting for pending action"
    age_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000) - session.updated_ms
    if session.updated_ms and age_ms <= 2 * 60 * 1000:
        # Cursor streams assistant chunks into the transcript mid-turn. Recent
        # activity is safer and more useful than last-message role inference.
        return "likely running"
    messages = [event for event in session.events if event.kind == "message" and event.role in {"user", "assistant"}]
    if not messages:
        return "unknown"
    latest = messages[-1]
    if latest.role == "assistant" and re.search(
        r"\b(i(?: am|'m) blocked|blocked by|cannot proceed|can't proceed|failed with|fatal error)\b",
        latest.text,
        re.IGNORECASE,
    ):
        return "blocked or errored"
    if latest.role == "assistant" and (ASK_RE.search(latest.text) or MARKER_RE.search(latest.text)):
        return "likely waiting for user"
    if latest.role == "assistant":
        return "likely waiting or complete"
    if latest.role == "user":
        if age_ms < 5 * 60 * 1000:
            return "possibly still running"
        return "unknown; latest message is from user"
    return "unknown"


def newest_session(sessions: Iterable[CursorSession]) -> CursorSession | None:
    candidates = list(sessions)
    if not candidates:
        return None
    return max(candidates, key=lambda session: session.updated_ms)


def has_transcript(session: CursorSession) -> bool:
    return session.path.suffix == ".jsonl"


def load_sessions(
    home: Path,
    headers: dict[str, ComposerHeader],
    cli_conversations: dict[str, bool] | None = None,
) -> list[CursorSession]:
    cli_conversations = cli_conversations or {}
    sessions = [inspect_path(path, headers) for path in transcript_files(home)]
    for session in sessions:
        if session.id in cli_conversations:
            session.metadata_source = "cli-chat"
            session.has_conversation = cli_conversations[session.id]
    session_ids = {session.id for session in sessions}
    for composer_id, header in headers.items():
        if composer_id in session_ids:
            continue
        metadata_source = "cli-chat" if composer_id in cli_conversations else "ide-index"
        sessions.append(
            CursorSession(
                path=Path(""),
                id=composer_id,
                name=header.name,
                workspace_id=header.workspace_id,
                workspace_path=header.workspace_path,
                mode=header.mode,
                updated_ms=header.updated_at_ms,
                updated_at=ms_to_iso(header.updated_at_ms),
                state="indexed only; transcript not found",
                blocking_pending_actions=header.blocking_pending_actions,
                pending_plan=header.pending_plan,
                metadata_source=metadata_source,
                has_conversation=cli_conversations.get(composer_id),
            )
        )
    sessions.sort(key=lambda session: session.updated_ms, reverse=True)
    return sessions


def session_haystack(session: CursorSession) -> str:
    recent_text = "\n".join(event.text for event in session.events[-20:])
    return "\n".join(
        [
            session.id,
            session.parent_id,
            session.name,
            session.workspace_id,
            session.workspace_path,
            session.project_key,
            str(session.path),
            recent_text,
        ]
    ).lower()


def attach_request_reference(session: CursorSession, reference: RequestReference) -> CursorSession:
    session.request_id = reference.request_id
    session.resolved_by = reference.source_kind
    session.resolution_source = str(reference.source_path or "")
    return session


def session_from_request_reference(
    reference: RequestReference,
    sessions: list[CursorSession],
) -> CursorSession | None:
    if reference.transcript_path and reference.transcript_path.exists():
        for session in sessions:
            if session.path == reference.transcript_path:
                return attach_request_reference(session, reference)
        return attach_request_reference(inspect_path(reference.transcript_path, {}), reference)

    if reference.session_id:
        request_matches = [
            session
            for session in sessions
            if reference.session_id.lower() in {session.id.lower(), session.parent_id.lower()}
        ]
        match = newest_session(request_matches)
        if match:
            return attach_request_reference(match, reference)
    return None


def load_session_from_request_reference(
    home: Path,
    headers: dict[str, ComposerHeader],
    reference: RequestReference,
) -> CursorSession | None:
    """Load only the transcript identified by a request reference."""
    if reference.transcript_path and reference.transcript_path.exists():
        return attach_request_reference(inspect_path(reference.transcript_path, headers), reference)

    if not reference.session_id:
        return None

    session_id = reference.session_id.lower()
    matching_paths: list[Path] = []
    for path in transcript_files(home):
        path_session_id, parent_id, _, _ = ids_from_path(path)
        if session_id in {path_session_id.lower(), parent_id.lower()}:
            matching_paths.append(path)
    if matching_paths:
        sessions = [inspect_path(path, headers) for path in matching_paths]
        match = newest_session(sessions)
        if match:
            return attach_request_reference(match, reference)

    header = headers.get(reference.session_id)
    if header:
        return attach_request_reference(
            CursorSession(
                path=Path(""),
                id=header.id,
                name=header.name,
                workspace_id=header.workspace_id,
                workspace_path=header.workspace_path,
                mode=header.mode,
                updated_ms=header.updated_at_ms,
                updated_at=ms_to_iso(header.updated_at_ms),
                state="indexed only; transcript not found",
                blocking_pending_actions=header.blocking_pending_actions,
                pending_plan=header.pending_plan,
            ),
            reference,
        )
    return None


def load_session_by_id(
    home: Path,
    headers: dict[str, ComposerHeader],
    cli_conversations: dict[str, bool],
    session_id: str,
) -> CursorSession | None:
    """Load an exact composer/session id without treating it as a request id."""
    normalized = session_id.lower()
    matching_paths: list[Path] = []
    for path in transcript_files(home):
        path_session_id, parent_id, _, _ = ids_from_path(path)
        if normalized in {path_session_id.lower(), parent_id.lower()}:
            matching_paths.append(path)

    if matching_paths:
        match = newest_session(inspect_path(path, headers) for path in matching_paths)
        if match and match.id in cli_conversations:
            match.metadata_source = "cli-chat"
            match.has_conversation = cli_conversations[match.id]
        return match

    header = next((item for key, item in headers.items() if key.lower() == normalized), None)
    if not header:
        return None
    metadata_source = "cli-chat" if header.id in cli_conversations else "ide-index"
    return CursorSession(
        path=Path(""),
        id=header.id,
        name=header.name,
        workspace_id=header.workspace_id,
        workspace_path=header.workspace_path,
        mode=header.mode,
        updated_ms=header.updated_at_ms,
        updated_at=ms_to_iso(header.updated_at_ms),
        state="indexed only; transcript not found",
        blocking_pending_actions=header.blocking_pending_actions,
        pending_plan=header.pending_plan,
        metadata_source=metadata_source,
        has_conversation=cli_conversations.get(header.id),
    )


def resolve_session(args: argparse.Namespace, sessions: list[CursorSession], app_support: Path) -> CursorSession | None:
    if args.path:
        path = Path(args.path).expanduser()
        for session in sessions:
            if session.path == path:
                return session
        return inspect_path(path, {})

    if args.request_id:
        request_id = args.request_id.strip().lower()
        if not UUID_RE.fullmatch(request_id):
            raise SystemExit(f"Invalid Cursor request id: {args.request_id}")
        reference = find_generation_reference(app_support, request_id)
        if reference:
            session = session_from_request_reference(reference, sessions)
            if session:
                return session
            hook_reference = find_hook_generation_reference(app_support, request_id)
            if hook_reference and hook_reference != reference:
                return session_from_request_reference(hook_reference, sessions)
        return None

    if args.session_id:
        session_id = args.session_id.strip().lower()
        if not UUID_RE.fullmatch(session_id):
            raise SystemExit(f"Invalid Cursor session id: {args.session_id}")
        exact = [session for session in sessions if session_id in {session.id.lower(), session.parent_id.lower()}]
        return newest_session(exact)

    if args.query:
        query = args.query.strip()
        maybe_path = Path(query).expanduser()
        if maybe_path.exists():
            for session in sessions:
                if session.path == maybe_path:
                    return session
            return inspect_path(maybe_path, {})

        lowered = query.lower()
        exact = [session for session in sessions if lowered in {session.id.lower(), session.parent_id.lower()}]
        if exact:
            return newest_session(exact)

        id_matches = [session for session in sessions if lowered in session.id.lower()]
        if len(id_matches) == 1:
            return id_matches[0]

        reference = find_generation_reference(app_support, lowered)
        if reference:
            session = session_from_request_reference(reference, sessions)
            if session:
                return session
            hook_reference = find_hook_generation_reference(app_support, lowered)
            if hook_reference and hook_reference != reference:
                session = session_from_request_reference(hook_reference, sessions)
                if session:
                    return session

        matches = [session for session in sessions if lowered in session_haystack(session)]
        return newest_session(matches)

    if args.last:
        with_transcripts = [session for session in sessions if has_transcript(session)]
        return newest_session(with_transcripts or sessions)

    return None


def event_to_json(event: Event) -> dict[str, str]:
    return {
        "timestamp": event.timestamp,
        "kind": event.kind,
        "role": event.role,
        "text": event.text,
    }


def session_to_json(session: CursorSession, limit: int) -> dict[str, Any]:
    age_seconds = max(
        0,
        round(datetime.now(tz=timezone.utc).timestamp() - session.updated_ms / 1000),
    ) if session.updated_ms else None
    return {
        "id": session.id,
        "parent_id": session.parent_id,
        "is_subagent": session.is_subagent,
        "name": session.name,
        "workspace_id": session.workspace_id,
        "workspace_path": session.workspace_path,
        "project_key": session.project_key,
        "path": str(session.path) if has_transcript(session) else "",
        "updated_at": session.updated_at,
        "age_seconds": age_seconds,
        "active_recently": age_seconds is not None and age_seconds <= 120,
        "state": session.state,
        "mode": session.mode,
        "raw_event_count": session.raw_event_count,
        "request_id": session.request_id,
        "resolved_by": session.resolved_by,
        "resolution_source": session.resolution_source,
        "metadata_source": session.metadata_source,
        "has_conversation": session.has_conversation,
        "events": [event_to_json(event) for event in (session.events[-limit:] if limit > 0 else [])],
    }


def print_list(sessions: list[CursorSession], limit: int, as_json: bool) -> None:
    shown = sessions[:limit]
    if as_json:
        print(json.dumps([session_to_json(session, 0) for session in shown], indent=2, ensure_ascii=False))
        return
    for session in shown:
        name = session.name or "(untitled)"
        workspace = session.workspace_path or session.project_key or session.workspace_id or "(unknown workspace)"
        marker = " subagent" if session.is_subagent else ""
        print(f"{session.updated_at or '-'}  {session.id}{marker}  {name}  [{workspace}]  {session.state}")


def print_session(session: CursorSession, limit: int, as_json: bool) -> None:
    if as_json:
        print(json.dumps(session_to_json(session, limit), indent=2, ensure_ascii=False))
        return

    name = session.name or "(untitled)"
    print(f"Session: {name} ({session.id})")
    if session.request_id:
        print(f"Request ID: {session.request_id}")
        print(f"Session ID: {session.id}")
        source = f" ({session.resolution_source})" if session.resolution_source else ""
        print(f"Resolved via: {session.resolved_by}{source}")
    if session.is_subagent:
        print(f"Parent: {session.parent_id}")
    print(f"State: {session.state}")
    print(f"Last activity: {session.updated_at or '-'}")
    if session.workspace_path or session.project_key:
        print(f"Workspace: {session.workspace_path or session.project_key}")
    if has_transcript(session):
        print(f"Path: {session.path}")
    else:
        print("Path: transcript not found; metadata only")

    events = session.events[-limit:]
    if events:
        print("Latest useful context:")
        for event in events:
            label = event.role.capitalize() if event.role != "tool" else event.kind.replace("_", " ").title()
            print(f"- {label}: {compact(event.text)}")

    recent_assistant = "\n".join(
        event.text for event in session.events[-8:] if event.kind == "message" and event.role == "assistant"
    )
    markers = MARKER_RE.findall(recent_assistant)
    if markers:
        print(f"Recent markers: {', '.join(sorted({str(marker).lower() for marker in markers})[:6])}")

    if "waiting" in session.state or "blocked" in session.state:
        print("Next suggested action: inspect the last assistant request and answer or clear the pending action.")
    elif session.state.startswith("indexed only"):
        print("Next suggested action: search by workspace/project or check Cursor's transcript directory for this composer id.")
    else:
        print("Next suggested action: use the latest context above to decide whether to resume, verify, or leave it alone.")


def latest_message(session: CursorSession, role: str) -> Event | None:
    for event in reversed(session.events):
        if event.kind != "message":
            continue
        if role == "any" or event.role == role:
            return event
    return None


def search_events(session: CursorSession, query: str) -> list[Event]:
    query_lower = query.lower()
    return [event for event in session.events if query_lower in event.text.lower()]


def print_full_message(session: CursorSession, role: str, as_json: bool) -> None:
    event = latest_message(session, role)
    if not event:
        print(f"No {role} message found in {session.path}", file=sys.stderr)
        raise SystemExit(1)

    payload = {
        "session_id": session.id,
        "request_id": session.request_id,
        "resolved_by": session.resolved_by,
        "resolution_source": session.resolution_source,
        "parent_id": session.parent_id,
        "name": session.name,
        "workspace_path": session.workspace_path,
        "path": str(session.path) if has_transcript(session) else "",
        "timestamp": event.timestamp,
        "role": event.role,
        "text": event.text,
    }
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    print(f"Session: {session.name or '(untitled)'} ({session.id})")
    if session.request_id:
        print(f"Request ID: {session.request_id}")
        print(f"Resolved via: {session.resolved_by}")
    print(f"Message: latest {event.role}")
    print(f"Timestamp: {event.timestamp}")
    print("")
    print(event.text)


def print_search_results(
    session: CursorSession,
    query: str,
    limit: int,
    as_json: bool,
    full: bool,
) -> None:
    matches = search_events(session, query)[-limit:]
    rows = [
        {
            "timestamp": event.timestamp,
            "kind": event.kind,
            "role": event.role,
            "text": event.text if full else compact(event.text),
        }
        for event in matches
    ]
    if as_json:
        print(
            json.dumps(
                {
                    "session_id": session.id,
                    "request_id": session.request_id,
                    "resolved_by": session.resolved_by,
                    "resolution_source": session.resolution_source,
                    "parent_id": session.parent_id,
                    "name": session.name,
                    "workspace_path": session.workspace_path,
                    "path": str(session.path) if has_transcript(session) else "",
                    "query": query,
                    "matches": rows,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    print(f"Session: {session.name or '(untitled)'} ({session.id})")
    if session.request_id:
        print(f"Request ID: {session.request_id}")
        print(f"Resolved via: {session.resolved_by}")
    print(f"Search: {query}")
    print(f"Matches: {len(matches)}")
    print("")
    for row in rows:
        print(f"- {row['timestamp']} {row['role']}/{row['kind']}")
        print(row["text"])
        print("")


def main() -> int:
    args = parse_args()
    home = cursor_home(args)
    app_support = cursor_app_support(args)
    workspace_paths = load_workspace_map(app_support)
    headers = load_composer_headers(app_support, workspace_paths)
    cli_headers, cli_conversations = load_cli_chat_headers(home)
    # CLI metadata is the ground truth for CLI sessions; IDE metadata remains
    # authoritative for all non-overlapping composers.
    headers.update(cli_headers)

    session_candidate = args.session_id
    if not session_candidate and args.query and UUID_RE.fullmatch(args.query.strip()):
        session_candidate = args.query.strip()
    if session_candidate:
        session_id = session_candidate.lower()
        if not UUID_RE.fullmatch(session_id):
            raise SystemExit(f"Invalid Cursor session id: {session_candidate}")
        session = load_session_by_id(home, headers, cli_conversations, session_id)
        if session:
            if args.last_message:
                print_full_message(session, args.last_message, args.json)
            elif args.search:
                print_search_results(session, args.search, args.limit, args.json, args.full)
            else:
                print_session(session, args.limit, args.json)
            return 0
        if args.session_id:
            print(
                f"No Cursor session found for session id {args.session_id}. "
                "Try --list or use --request-id if this is a request/generation id.",
                file=sys.stderr,
            )
            return 1

    request_candidate = args.request_id
    if not request_candidate and args.query and UUID_RE.fullmatch(args.query.strip()):
        request_candidate = args.query.strip()
    if request_candidate:
        request_id = request_candidate.lower()
        if args.request_id and not UUID_RE.fullmatch(request_id):
            raise SystemExit(f"Invalid Cursor request id: {args.request_id}")
        reference = find_generation_reference(app_support, request_id)
        if reference:
            session = load_session_from_request_reference(home, headers, reference)
            if not session and reference.source_kind == "request trace":
                hook_reference = find_hook_generation_reference(app_support, request_id)
                if hook_reference:
                    session = load_session_from_request_reference(home, headers, hook_reference)
            if session:
                if args.last_message:
                    print_full_message(session, args.last_message, args.json)
                elif args.search:
                    print_search_results(session, args.search, args.limit, args.json, args.full)
                else:
                    print_session(session, args.limit, args.json)
                return 0

    sessions = load_sessions(home, headers, cli_conversations)

    if args.list:
        print_list(sessions, args.limit, args.json)
        return 0

    session = resolve_session(args, sessions, app_support)
    if not session:
        if args.request_id:
            print(
                f"No Cursor session found for request id {args.request_id}. "
                "Searched Cursor IDE request traces and hook logs. If this is a composer/session id, use --session-id. "
                "Headless `agent -p` request_id values are not locally resolvable; pass the result's session_id instead.",
                file=sys.stderr,
            )
        else:
            print(
                "No Cursor session found. Try --list or pass --query with a composer id, "
                "request id, title, or workspace.",
                file=sys.stderr,
            )
        return 1

    if args.last_message:
        print_full_message(session, args.last_message, args.json)
    elif args.search:
        print_search_results(session, args.search, args.limit, args.json, args.full)
    else:
        print_session(session, args.limit, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
