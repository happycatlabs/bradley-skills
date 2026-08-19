#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("inspect_codex_session.py")
SPEC = importlib.util.spec_from_file_location("inspect_codex_session", SCRIPT_PATH)
assert SPEC and SPEC.loader
inspector = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = inspector
SPEC.loader.exec_module(inspector)


def record(timestamp: str, record_type: str, payload: dict[str, object]) -> dict[str, object]:
    return {"timestamp": timestamp, "type": record_type, "payload": payload}


def message(timestamp: str, role: str, text: str, phase: str = "") -> dict[str, object]:
    payload: dict[str, object] = {
        "type": "message",
        "role": role,
        "content": [{"type": "output_text", "text": text}],
    }
    if phase:
        payload["phase"] = phase
    return record(timestamp, "response_item", payload)


class InspectCodexSessionTests(unittest.TestCase):
    def inspect(self, rows: list[dict[str, object]]) -> object:
        temp = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
        with temp:
            for row in rows:
                temp.write(json.dumps(row) + "\n")
        self.addCleanup(Path(temp.name).unlink, missing_ok=True)
        return inspector.inspect_path(Path(temp.name), [])

    def test_task_complete_beats_recent_file_activity(self) -> None:
        summary = self.inspect(
            [
                record("2026-07-11T09:00:00Z", "event_msg", {"type": "task_started", "turn_id": "turn-1"}),
                message("2026-07-11T09:00:01Z", "user", "Do the thing"),
                message("2026-07-11T09:00:02Z", "assistant", "Done", "final_answer"),
                record(
                    "2026-07-11T09:00:03Z",
                    "event_msg",
                    {"type": "task_complete", "turn_id": "turn-1", "last_agent_message": "Done"},
                ),
            ]
        )

        state, reason = inspector.heuristic_state(summary)
        self.assertEqual(state, "turn complete; waiting for user")
        self.assertIn("task_complete", reason)

    def test_task_started_is_running_when_transcript_is_recent(self) -> None:
        summary = self.inspect(
            [
                record("2099-07-11T09:00:00Z", "event_msg", {"type": "task_started", "turn_id": "turn-2"}),
                message("2099-07-11T09:00:01Z", "user", "Keep going"),
            ]
        )

        state, _ = inspector.heuristic_state(summary)
        self.assertEqual(state, "running")

    def test_lifecycle_state_does_not_require_messages(self) -> None:
        summary = self.inspect(
            [record("2099-07-11T09:00:00Z", "event_msg", {"type": "task_started", "turn_id": "turn-only"})]
        )

        state, _ = inspector.heuristic_state(summary)
        self.assertEqual(state, "running")

    def test_conversation_current_turn_excludes_reasoning_and_old_turn(self) -> None:
        summary = self.inspect(
            [
                message("2026-07-11T08:59:00Z", "user", "Old request"),
                record("2026-07-11T09:00:00Z", "event_msg", {"type": "task_started", "turn_id": "turn-3"}),
                message(
                    "2026-07-11T09:00:01Z",
                    "user",
                    '<in-app-browser-context source="ambient-ui-state">noise</in-app-browser-context>\n'
                    "## My request for Codex:\nActual request",
                ),
                record("2026-07-11T09:00:02Z", "event_msg", {"type": "agent_reasoning", "text": "secret reasoning"}),
                message("2026-07-11T09:00:03Z", "assistant", "Working", "commentary"),
            ]
        )

        events = inspector.filter_events(summary.events, None, None, conversation=True, current_turn=True)
        self.assertEqual([event.kind for event in events], ["message", "message"])
        self.assertEqual(inspector.display_text(events[0]), "Actual request")

    def test_latest_final_answer_ignores_later_commentary(self) -> None:
        summary = self.inspect(
            [
                message("2026-07-11T09:00:01Z", "assistant", "Final", "final_answer"),
                message("2026-07-11T09:00:02Z", "assistant", "Later commentary", "commentary"),
            ]
        )

        event = inspector.latest_message(summary, "final")
        self.assertIsNotNone(event)
        self.assertEqual(event.text, "Final")

    def test_new_user_after_completion_is_queued_or_starting(self) -> None:
        summary = self.inspect(
            [
                record("2026-07-11T09:00:00Z", "event_msg", {"type": "task_started", "turn_id": "turn-4"}),
                record("2026-07-11T09:00:01Z", "event_msg", {"type": "task_complete", "turn_id": "turn-4"}),
                message("2026-07-11T09:00:02Z", "user", "One more thing"),
            ]
        )

        state, _ = inspector.heuristic_state(summary)
        self.assertEqual(state, "queued or starting")

    def test_success_language_does_not_create_false_blocker(self) -> None:
        summary = self.inspect(
            [
                record("2026-07-11T09:00:00Z", "event_msg", {"type": "task_started", "turn_id": "turn-5"}),
                message("2026-07-11T09:00:01Z", "assistant", "Finished with no errors", "final_answer"),
                record("2026-07-11T09:00:02Z", "event_msg", {"type": "task_complete", "turn_id": "turn-5"}),
            ]
        )

        state, _ = inspector.heuristic_state(summary)
        self.assertEqual(state, "turn complete; waiting for user")

    def test_event_message_fallback_is_supported_and_mirrors_are_deduplicated(self) -> None:
        summary = self.inspect(
            [
                message("2026-07-11T09:00:00Z", "user", "Same request"),
                record("2026-07-11T09:00:00Z", "event_msg", {"type": "user_message", "message": "Same request"}),
                record(
                    "2026-07-11T09:00:01Z",
                    "event_msg",
                    {"type": "agent_message", "message": "Fallback answer", "phase": "final_answer"},
                ),
                message("2026-07-11T09:00:01.500Z", "assistant", "Fallback answer", "final_answer"),
            ]
        )

        messages = [event for event in summary.events if event.kind == "message"]
        self.assertEqual([event.text for event in messages], ["Same request", "Fallback answer"])
        self.assertEqual(messages[-1].phase, "final_answer")

    def test_custom_tool_calls_are_visible(self) -> None:
        event = inspector.extract_event(
            record(
                "2026-07-11T09:00:00Z",
                "response_item",
                {"type": "custom_tool_call", "name": "exec", "status": "completed", "input": "do work"},
            )
        )

        self.assertIsNotNone(event)
        self.assertEqual(event.kind, "tool_call")
        self.assertIn("do work", event.text)

    def test_ephemeral_side_chat_separates_tool_responses_and_surfaces_delegated_tasks(self) -> None:
        thread_id = "01900000-0000-7000-8000-000000000006"
        child_id = "01900000-0000-7000-8000-000000000007"
        home = Path(tempfile.mkdtemp())
        self.addCleanup(home.rmdir)
        db_path = home / "logs_2.sqlite"
        self.addCleanup(db_path.unlink, missing_ok=True)
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER NOT NULL,
                    ts_nanos INTEGER NOT NULL,
                    target TEXT NOT NULL,
                    feedback_log_body TEXT,
                    thread_id TEXT
                )
                """
            )
            delegated_task = json.dumps(
                {
                    "schemaVersion": 2,
                    "threads": [
                        {
                            "id": child_id,
                            "hostId": "local",
                            "status": "idle",
                            "cwd": "/tmp/emails",
                            "title": "MXA-5372",
                            "preview": (
                                "<codex_delegation>"
                                f"<source_thread_id>{thread_id}</source_thread_id>"
                                "<input>Do the work</input>"
                                "</codex_delegation>"
                            ),
                        }
                    ],
                }
            )
            rows = [
                (
                    1,
                    0,
                    "codex_core::session::handlers",
                    'Submission sub=Submission { op: UserInput { items: [Text { text: "Start the work" }] } }',
                    thread_id,
                ),
                (
                    2,
                    0,
                    "codex_core::session::handlers",
                    (
                        "Submission sub=Submission { op: DynamicToolResponse { "
                        f"content_items: [InputText {{ text: {json.dumps(delegated_task)} }}] "
                        "} }"
                    ),
                    thread_id,
                ),
                (
                    3,
                    0,
                    "codex_core::session::handlers",
                    'Submission sub=Submission { op: UserInput { items: [Text { text: "Open it in Cursor" }] } }',
                    thread_id,
                ),
            ]
            conn.executemany(
                """
                INSERT INTO logs (ts, ts_nanos, target, feedback_log_body, thread_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                rows,
            )

        summary = inspector.inspect_ephemeral_thread(home, thread_id)

        self.assertIsNotNone(summary)
        messages = [event for event in summary.events if event.kind == "message"]
        self.assertEqual([event.text for event in messages], ["Start the work", "Open it in Cursor"])
        self.assertEqual([event.role for event in summary.events], ["user", "tool", "user"])
        self.assertEqual(
            summary.delegated_tasks,
            [
                {
                    "id": child_id,
                    "host_id": "local",
                    "title": "MXA-5372",
                    "status": "idle",
                    "cwd": "/tmp/emails",
                    "updated_at": None,
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
