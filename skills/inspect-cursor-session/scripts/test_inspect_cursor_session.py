#!/usr/bin/env python3

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("inspect_cursor_session.py")
SPEC = importlib.util.spec_from_file_location("inspect_cursor_session", SCRIPT_PATH)
assert SPEC and SPEC.loader
inspector = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = inspector
SPEC.loader.exec_module(inspector)


class RequestIdResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.home = self.root / "cursor-home"
        self.app_support = self.root / "app-support"
        self.logs = self.app_support / "logs" / "window" / "output"
        self.logs.mkdir(parents=True)

        self.request_id = "7265cb86-a070-4ab7-a422-f4ac9ef53c86"
        self.session_id = "ecd5f755-df53-4823-9279-85c0631a330f"
        self.transcript = (
            self.home
            / "projects"
            / "fixture-project"
            / "agent-transcripts"
            / self.session_id
            / f"{self.session_id}.jsonl"
        )
        self.transcript.parent.mkdir(parents=True)
        self.transcript.write_text(
            json.dumps(
                {
                    "role": "user",
                    "timestamp": "2026-07-11T12:34:48Z",
                    "message": {
                        "content": [
                            {
                                "type": "text",
                                "text": "Inspect this fixture session.",
                            }
                        ]
                    },
                }
            )
            + "\n"
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_request_trace(self) -> Path:
        trace = self.logs / "cursor.requestTraces.log"
        trace.write_text(
            "agent_request_tagged "
            f"requestId={self.request_id}\n"
            "span_started name=\"ComposerChatService.localProcessingBeforeStream\" "
            f"requestId={self.request_id} composerId={self.session_id}\n"
        )
        return trace

    def write_hook_log(self) -> Path:
        hook_log = self.logs / "cursor.hooks.workspaceId-fixture.log"
        hook_log.write_text(
            "sessionEnd\nINPUT:\n"
            + json.dumps(
                {
                    "conversation_id": self.session_id,
                    "generation_id": self.request_id,
                    "session_id": self.session_id,
                    "transcript_path": str(self.transcript),
                },
                indent=2,
            )
            + "\n\nOUTPUT:\n(empty)\n"
        )
        return hook_log

    def test_request_trace_resolves_live_request_to_session_id(self) -> None:
        trace = self.write_request_trace()

        reference = inspector.find_request_trace_reference(self.app_support, self.request_id)

        self.assertIsNotNone(reference)
        assert reference
        self.assertEqual(reference.session_id, self.session_id)
        self.assertEqual(reference.source_kind, "request trace")
        self.assertEqual(reference.source_path, trace)

    def test_hook_fallback_prefers_transcript_path(self) -> None:
        hook_log = self.write_hook_log()

        reference = inspector.find_hook_generation_reference(self.app_support, self.request_id)

        self.assertIsNotNone(reference)
        assert reference
        self.assertEqual(reference.session_id, self.session_id)
        self.assertEqual(reference.transcript_path, self.transcript)
        self.assertEqual(reference.source_kind, "hook input")
        self.assertEqual(reference.source_path, hook_log)

    def test_cli_request_id_reports_explicit_mapping(self) -> None:
        self.write_request_trace()

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--home",
                str(self.home),
                "--app-support",
                str(self.app_support),
                "--request-id",
                self.request_id,
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["request_id"], self.request_id)
        self.assertEqual(payload["id"], self.session_id)
        self.assertEqual(payload["resolved_by"], "request trace")
        self.assertEqual(payload["resolution_source"], str(self.logs / "cursor.requestTraces.log"))

    def test_query_uuid_uses_request_trace_when_not_a_session_id(self) -> None:
        self.write_request_trace()
        sessions = inspector.load_sessions(self.home, {})
        namespace = argparse.Namespace(
            path=None,
            session_id=None,
            request_id=None,
            query=self.request_id,
            last=False,
        )

        session = inspector.resolve_session(namespace, sessions, self.app_support)

        self.assertIsNotNone(session)
        assert session
        self.assertEqual(session.id, self.session_id)
        self.assertEqual(session.request_id, self.request_id)

    def test_session_id_selector_inspects_exact_session(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--home",
                str(self.home),
                "--app-support",
                str(self.app_support),
                "--session-id",
                self.session_id,
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["id"], self.session_id)
        self.assertEqual(payload["request_id"], "")

    def test_query_uuid_prefers_exact_session_over_request_mapping(self) -> None:
        other_session_id = "3e92ad79-b97d-4870-ad55-848365ae062b"
        other_transcript = (
            self.home
            / "projects"
            / "fixture-project"
            / "agent-transcripts"
            / other_session_id
            / f"{other_session_id}.jsonl"
        )
        other_transcript.parent.mkdir(parents=True)
        other_transcript.write_text(self.transcript.read_text())
        (self.logs / "cursor.requestTraces.log").write_text(
            "span_started "
            f"requestId={self.session_id} composerId={other_session_id}\n"
        )

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--home",
                str(self.home),
                "--app-support",
                str(self.app_support),
                "--query",
                self.session_id,
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["id"], self.session_id)
        self.assertEqual(payload["request_id"], "")

    def test_json_list_does_not_include_events(self) -> None:
        sessions = inspector.load_sessions(self.home, {})
        output = StringIO()
        with contextlib.redirect_stdout(output):
            inspector.print_list(sessions, 1, True)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload[0]["events"], [])

    def test_historical_refusal_does_not_create_false_blocker(self) -> None:
        old_ms = int((datetime.now(timezone.utc) - timedelta(minutes=10)).timestamp() * 1000)
        session = inspector.CursorSession(
            path=Path("fixture.jsonl"),
            id=self.session_id,
            updated_ms=old_ms,
            events=[
                inspector.Event("", "message", "assistant", "I can't edit in Ask mode."),
                inspector.Event("", "message", "user", "What mode are you in?"),
                inspector.Event("", "message", "assistant", "Ask mode."),
            ],
        )
        self.assertEqual(inspector.infer_state(session), "likely waiting or complete")

    def test_recent_activity_overrides_assistant_role(self) -> None:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        session = inspector.CursorSession(
            path=Path("fixture.jsonl"),
            id=self.session_id,
            updated_ms=now_ms,
            events=[inspector.Event("", "message", "assistant", "Interim answer")],
        )
        self.assertEqual(inspector.infer_state(session), "likely running")

    def test_cli_chat_metadata_is_loaded(self) -> None:
        meta = self.home / "chats" / "workspace-hash" / self.session_id / "meta.json"
        meta.parent.mkdir(parents=True)
        meta.write_text(json.dumps({
            "createdAtMs": 1000,
            "updatedAtMs": 2000,
            "hasConversation": True,
            "cwd": "/tmp/cli-workspace",
            "title": "CLI lane",
        }))
        headers, conversations = inspector.load_cli_chat_headers(self.home)
        self.assertEqual(headers[self.session_id].workspace_path, "/tmp/cli-workspace")
        self.assertEqual(headers[self.session_id].name, "CLI lane")
        self.assertTrue(conversations[self.session_id])


if __name__ == "__main__":
    unittest.main()
