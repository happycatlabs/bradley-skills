#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCRIPT = Path(__file__).with_name("inspect_claude_session.py")
SPEC = importlib.util.spec_from_file_location("inspect_claude_session", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


class ChildActivityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.session_id = "11111111-1111-4111-8111-111111111111"
        self.parent = self.home / "projects" / "-tmp-project" / f"{self.session_id}.jsonl"
        old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        write_jsonl(
            self.parent,
            [
                {"type": "user", "timestamp": old, "sessionId": self.session_id, "message": {"role": "user", "content": "do work"}},
                {"type": "assistant", "timestamp": old, "sessionId": self.session_id, "message": {"role": "assistant", "content": "workflow launched"}},
            ],
        )
        old_epoch = (datetime.now(timezone.utc) - timedelta(minutes=10)).timestamp()
        os.utime(self.parent, (old_epoch, old_epoch))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def workflow_paths(self) -> tuple[Path, Path, Path]:
        root = self.parent.with_suffix("")
        workflow = root / "subagents" / "workflows" / "wf_test"
        journal = workflow / "journal.jsonl"
        child = workflow / "agent-a1.jsonl"
        result = root / "workflows" / "wf_test.json"
        return journal, child, result

    def test_recent_child_overrides_idle_parent(self) -> None:
        journal, child, _ = self.workflow_paths()
        write_jsonl(journal, [{"type": "started", "key": "lane", "agentId": "a1"}])
        write_jsonl(child, [{"type": "assistant", "timestamp": datetime.now(timezone.utc).isoformat(), "message": {"role": "assistant", "content": "working"}}])
        summary = MODULE.inspect_path(self.parent, self.home)
        state, _ = MODULE.heuristic_state(summary)
        self.assertEqual(state, "likely running background work")
        self.assertEqual(summary.child_activity[0]["unfinished_lanes"], 1)

    def test_terminal_workflow_does_not_override_parent(self) -> None:
        journal, child, result = self.workflow_paths()
        write_jsonl(journal, [{"type": "started", "key": "lane", "agentId": "a1"}])
        write_jsonl(child, [{"type": "assistant", "message": {"role": "assistant", "content": "done"}}])
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text(json.dumps({"status": "completed"}))
        summary = MODULE.inspect_path(self.parent, self.home)
        state, _ = MODULE.heuristic_state(summary)
        self.assertEqual(state, "likely waiting or complete")
        self.assertEqual(summary.child_activity[0]["state"], "completed")

    def test_stale_unfinished_workflow_is_not_reported_complete(self) -> None:
        journal, child, _ = self.workflow_paths()
        write_jsonl(journal, [{"type": "started", "key": "lane", "agentId": "a1"}])
        write_jsonl(child, [{"type": "assistant", "message": {"role": "assistant", "content": "last tool"}}])
        old_epoch = (datetime.now(timezone.utc) - timedelta(minutes=10)).timestamp()
        os.utime(journal, (old_epoch, old_epoch))
        os.utime(child, (old_epoch, old_epoch))
        summary = MODULE.inspect_path(self.parent, self.home)
        state, _ = MODULE.heuristic_state(summary)
        self.assertEqual(state, "background work unfinished or stalled")

    def test_include_subagents_excludes_journals_and_prefers_parent_uuid(self) -> None:
        journal, child, _ = self.workflow_paths()
        write_jsonl(journal, [{"type": "started", "key": "lane", "agentId": "a1"}])
        write_jsonl(child, [{"type": "assistant", "sessionId": self.session_id, "message": {"role": "assistant", "content": "working"}}])
        files = MODULE.session_files(self.home, include_subagents=True)
        self.assertIn(self.parent, files)
        self.assertIn(child, files)
        self.assertNotIn(journal, files)

        args = type("Args", (), {"include_subagents": True, "path": None, "query": self.session_id, "last": False})()
        self.assertEqual(MODULE.resolve_session_path(self.home, args), self.parent)


if __name__ == "__main__":
    unittest.main()
