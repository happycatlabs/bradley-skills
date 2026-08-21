#!/usr/bin/env python3

from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REPO_ROOT = SKILL_DIR.parents[1]
DIRECTORY_SKILL = REPO_ROOT / "skills" / "agent-organization-directory"
DIRECTORY_FIXTURE = DIRECTORY_SKILL / "fixtures" / "directory-v1.json"
SNAPSHOT_FIXTURE = DIRECTORY_SKILL / "fixtures" / "snapshot-v1.json"
REPARENTED_DIRECTORY_FIXTURE = DIRECTORY_SKILL / "fixtures" / "directory-reparented-v1.json"
REPARENTED_SNAPSHOT_FIXTURE = DIRECTORY_SKILL / "fixtures" / "snapshot-reparented-v1.json"
CHRONOLOGIES_FIXTURE = SKILL_DIR / "fixtures" / "chronologies-v1.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = load_module("material_outbox", SCRIPT_DIR / "material_outbox.py")


class MaterialOutboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = json.loads(DIRECTORY_FIXTURE.read_text())
        self.snapshot = json.loads(SNAPSHOT_FIXTURE.read_text())
        self.policy = MODULE.default_policy(cadenceSeconds=60)
        self.source = copy.deepcopy(self.directory["bindings"][1]["identity"])
        self.root = copy.deepcopy(self.directory["bindings"][0]["identity"])

    def event(
        self,
        *,
        kind: str = "blocker",
        material: str = "blocked-v1",
        trigger: str = "material_transition",
        hop_count: int = 0,
        observed_at: str = "2026-08-21T12:00:00.000Z",
    ) -> dict:
        return {
            "schemaVersion": MODULE.EVENT_VERSION,
            "sourceIdentity": copy.deepcopy(self.source),
            "eventKind": kind,
            "nativeAuthorityArtifact": {
                "kind": "linear_issue",
                "ref": "https://linear.app/happycat/issue/FABLE-411",
            },
            "materialStateHash": MODULE.digest({"material": material}),
            "summaryCode": material,
            "nextActionCode": "inspect_or_wait",
            "causalKey": "fable-411-owner-chain",
            "hopCount": hop_count,
            "trigger": trigger,
            "observedAt": observed_at,
        }

    def enqueue(self, state: dict | None = None, **event_overrides) -> dict:
        return MODULE.enqueue_event(
            state or MODULE.empty_state(),
            self.event(**event_overrides),
            self.policy,
            self.snapshot,
            self.directory,
        )

    def actions(self, state: dict, now: str = "2026-08-21T12:00:00.000Z") -> dict:
        return MODULE.plan_actions(
            state, self.policy, self.snapshot, self.directory, now
        )

    def result(
        self,
        state: dict,
        entry: dict,
        *,
        action: str,
        outcome: str,
        now: str,
        **extra,
    ) -> dict:
        payload = {"action": action, "outcome": outcome, **extra}
        if action in {"send", "readback"}:
            payload["messageId"] = entry["messageId"]
        elif action == "fallback":
            payload["fallbackId"] = MODULE.digest(
                {"messageId": entry["messageId"], "transport": "linear"}
            )
        return MODULE.record_result(
            state, entry["entryId"], payload, self.policy, now
        )["state"]

    def test_default_policy_and_quiet_read_only_inspection(self) -> None:
        policy = MODULE.default_policy()
        self.assertEqual(policy["mode"], "material_transitions")
        self.assertEqual(policy["quietThresholdSeconds"], 1200)

        before = MODULE.quiet_inspection(
            now="2026-08-21T12:19:59.000Z",
            last_material_at="2026-08-21T12:00:00.000Z",
            volatile_last_inspection_at=None,
            policy=policy,
        )
        self.assertFalse(before["inspectionRequired"])
        self.assertFalse(before["writeRequired"])

        due = MODULE.quiet_inspection(
            now="2026-08-21T12:20:00.000Z",
            last_material_at="2026-08-21T12:00:00.000Z",
            volatile_last_inspection_at=None,
            policy=policy,
        )
        self.assertTrue(due["inspectionRequired"])
        self.assertEqual(due["inspectionMode"], "read_only")
        self.assertFalse(due["writeRequired"])

        cadence_suppressed = MODULE.quiet_inspection(
            now="2026-08-21T12:20:00.000Z",
            last_material_at="2026-08-21T12:00:00.000Z",
            volatile_last_inspection_at="2026-08-21T12:16:00.000Z",
            policy=policy,
        )
        self.assertFalse(cadence_suppressed["inspectionRequired"])

    def test_exact_primary_binding_and_deterministic_key(self) -> None:
        event = self.event()
        decision = MODULE.enqueue_event(
            MODULE.empty_state(), event, self.policy, self.snapshot, self.directory
        )
        self.assertTrue(decision["writeRequired"])
        self.assertEqual(len(decision["state"]["entries"]), 1)
        entry = decision["state"]["entries"][0]
        self.assertEqual(entry["recipientBinding"]["identity"], self.root)
        self.assertEqual(entry["recipientBinding"]["bindingRevision"], 1)
        self.assertTrue(entry["notify"])
        self.assertFalse(entry["authority"])
        self.assertEqual(
            entry["dedupeKey"],
            MODULE.digest(
                {
                    "bindingRevision": self.directory["bindings"][1]["bindingRevision"],
                    "recipientIdentity": self.root,
                    "eventKind": event["eventKind"],
                    "nativeAuthorityArtifact": event["nativeAuthorityArtifact"],
                    "materialStateHash": event["materialStateHash"],
                }
            ),
        )
        action = self.actions(decision["state"])["actions"][0]
        self.assertEqual(action["action"], "message_existing_task")
        self.assertEqual(action["messageId"], entry["messageId"])
        self.assertTrue(action["readbackRequired"])

    def test_duplicate_restart_causes_no_write_or_message(self) -> None:
        first = self.enqueue()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "outbox.json"
            self.assertTrue(MODULE.persist_decision(path, first))
            stat_before = path.stat()
            restarted = MODULE.load_state(path)
            duplicate = self.enqueue(restarted)
            self.assertFalse(duplicate["writeRequired"])
            self.assertEqual(duplicate["reason"], "duplicate_material_state")
            self.assertFalse(MODULE.persist_decision(path, duplicate))
            self.assertEqual(path.stat().st_ino, stat_before.st_ino)
            self.assertEqual(path.stat().st_mtime_ns, stat_before.st_mtime_ns)
            self.assertEqual(len(self.actions(duplicate["state"])["actions"]), 1)

    def test_ambiguous_acceptance_converges_by_exact_readback(self) -> None:
        state = self.enqueue()["state"]
        entry = state["entries"][0]
        state = self.result(
            state,
            entry,
            action="send",
            outcome="ambiguous",
            now="2026-08-21T12:00:01.000Z",
        )
        self.assertEqual(state["entries"][0]["status"], "readback_pending")
        self.assertEqual(
            self.actions(state, "2026-08-21T12:00:30.000Z")["actions"], []
        )
        readback = self.actions(state, "2026-08-21T12:01:01.000Z")["actions"][0]
        self.assertEqual(readback["action"], "readback_existing_task")
        state = self.result(
            state,
            state["entries"][0],
            action="readback",
            outcome="found",
            now="2026-08-21T12:01:02.000Z",
            readbackConfirmed=True,
            remoteReceiptId="turn-accepted-v1",
        )
        self.assertEqual(state["entries"][0]["status"], "delivered")
        self.assertEqual(self.actions(state, "2026-08-21T12:02:00.000Z")["actions"], [])

    def test_last_ambiguous_send_still_gets_one_exact_readback(self) -> None:
        state = self.enqueue()["state"]
        for attempt in range(1, self.policy["maxAttempts"] + 1):
            entry = state["entries"][0]
            state = self.result(
                state,
                entry,
                action="send",
                outcome="ambiguous",
                now=f"2026-08-21T12:0{attempt}:00.000Z",
            )
            self.assertEqual(state["entries"][0]["status"], "readback_pending")
            if attempt < self.policy["maxAttempts"]:
                state = self.result(
                    state,
                    state["entries"][0],
                    action="readback",
                    outcome="not_found",
                    now=f"2026-08-21T12:0{attempt}:01.000Z",
                )
        entry = state["entries"][0]
        self.assertEqual(entry["attempts"], self.policy["maxAttempts"])
        state = self.result(
            state,
            entry,
            action="readback",
            outcome="found",
            now="2026-08-21T12:03:01.000Z",
            readbackConfirmed=True,
            remoteReceiptId="turn-after-final-ambiguity",
        )
        self.assertEqual(state["entries"][0]["status"], "delivered")

    def test_busy_readback_retries_readback_without_resending(self) -> None:
        state = self.enqueue()["state"]
        state = self.result(
            state,
            state["entries"][0],
            action="send",
            outcome="ambiguous",
            now="2026-08-21T12:00:01.000Z",
        )
        state = self.result(
            state,
            state["entries"][0],
            action="readback",
            outcome="busy",
            now="2026-08-21T12:01:01.000Z",
        )
        entry = state["entries"][0]
        self.assertEqual(entry["status"], "readback_pending")
        action = self.actions(state, "2026-08-21T12:02:01.000Z")["actions"][0]
        self.assertEqual(action["action"], "readback_existing_task")
        state = self.result(
            state,
            entry,
            action="readback",
            outcome="provider_unavailable",
            now="2026-08-21T12:02:02.000Z",
        )
        self.assertEqual(state["entries"][0]["status"], "fallback_pending")
        self.assertEqual(state["entries"][0]["attempts"], self.policy["maxAttempts"])

    def test_busy_recipient_retries_three_times_then_falls_back_once(self) -> None:
        state = self.enqueue()["state"]
        for attempt, moment in enumerate(
            (
                "2026-08-21T12:00:01.000Z",
                "2026-08-21T12:01:01.000Z",
                "2026-08-21T12:02:01.000Z",
            ),
            start=1,
        ):
            entry = state["entries"][0]
            state = self.result(
                state, entry, action="send", outcome="busy", now=moment
            )
            self.assertEqual(state["entries"][0]["attempts"], attempt)
        entry = state["entries"][0]
        self.assertEqual(entry["status"], "fallback_pending")
        fallback = self.actions(state, "2026-08-21T12:02:01.000Z")["actions"][0]
        self.assertEqual(fallback["action"], "linear_fallback")
        self.assertTrue(fallback["notify"])
        state = self.result(
            state,
            entry,
            action="fallback",
            outcome="fallback_delivered",
            now="2026-08-21T12:02:02.000Z",
            fallbackReceiptId="linear-comment-v1",
        )
        self.assertEqual(state["entries"][0]["status"], "fallback_delivered")
        self.assertFalse(self.enqueue(state)["writeRequired"])

    def test_provider_unavailable_is_bounded(self) -> None:
        state = self.enqueue()["state"]
        for moment in (
            "2026-08-21T12:00:01.000Z",
            "2026-08-21T12:01:01.000Z",
            "2026-08-21T12:02:01.000Z",
        ):
            state = self.result(
                state,
                state["entries"][0],
                action="send",
                outcome="provider_unavailable",
                now=moment,
            )
        self.assertEqual(state["entries"][0]["status"], "fallback_pending")

    def test_terminal_owner_fails_closed_immediately(self) -> None:
        state = self.enqueue()["state"]
        state = self.result(
            state,
            state["entries"][0],
            action="send",
            outcome="recipient_terminal",
            now="2026-08-21T12:00:01.000Z",
        )
        self.assertEqual(state["entries"][0]["status"], "fallback_pending")
        self.assertEqual(state["entries"][0]["lastErrorCode"], "recipient_terminal")

    def test_moved_binding_falls_back_instead_of_retargeting(self) -> None:
        state = self.enqueue()["state"]
        moved_directory = json.loads(REPARENTED_DIRECTORY_FIXTURE.read_text())
        moved_snapshot = json.loads(REPARENTED_SNAPSHOT_FIXTURE.read_text())
        decision = MODULE.plan_actions(
            state,
            self.policy,
            moved_snapshot,
            moved_directory,
            "2026-08-21T12:00:01.000Z",
        )
        self.assertTrue(decision["writeRequired"])
        entry = decision["state"]["entries"][0]
        self.assertEqual(entry["status"], "fallback_pending")
        self.assertEqual(entry["lastErrorCode"], "moved_binding")
        self.assertEqual(decision["actions"][0]["action"], "linear_fallback")
        self.assertEqual(
            decision["actions"][0]["event"]["recipientIdentity"], self.root
        )

    def test_stale_snapshot_fails_closed_to_original_primary_fallback(self) -> None:
        state = self.enqueue()["state"]
        changed_directory = copy.deepcopy(self.directory)
        changed_directory["directoryRevision"] += 1
        decision = MODULE.plan_actions(
            state,
            self.policy,
            self.snapshot,
            changed_directory,
            "2026-08-21T12:00:01.000Z",
        )
        self.assertTrue(decision["writeRequired"])
        self.assertEqual(decision["reason"], "stale_directory_snapshot")
        self.assertEqual(decision["state"]["entries"][0]["status"], "fallback_pending")
        self.assertEqual(decision["actions"][0]["action"], "linear_fallback")

    def test_unsupported_primary_contact_starts_in_fallback(self) -> None:
        unsupported = copy.deepcopy(self.directory)
        root = unsupported["bindings"][0]
        message_capability = next(
            item
            for item in root["advertisedCapabilities"]
            if item["capability"] == "message_existing_task"
        )
        message_capability["status"] = "unsupported"
        message_capability["routeRef"] = None
        snapshot = MODULE.DIRECTORY.build_snapshot(unsupported)
        decision = MODULE.enqueue_event(
            MODULE.empty_state(), self.event(), self.policy, snapshot, unsupported
        )
        entry = decision["state"]["entries"][0]
        self.assertEqual(entry["status"], "fallback_pending")
        self.assertEqual(entry["lastErrorCode"], "capability_unsupported")

    def test_linear_fallback_retries_are_bounded(self) -> None:
        state = self.enqueue()["state"]
        entry = state["entries"][0]
        state = self.result(
            state,
            entry,
            action="send",
            outcome="recipient_terminal",
            now="2026-08-21T12:00:01.000Z",
        )
        for moment in (
            "2026-08-21T12:00:02.000Z",
            "2026-08-21T12:01:02.000Z",
            "2026-08-21T12:02:02.000Z",
        ):
            state = self.result(
                state,
                state["entries"][0],
                action="fallback",
                outcome="fallback_unavailable",
                now=moment,
            )
        self.assertEqual(state["entries"][0]["fallbackAttempts"], 3)
        self.assertEqual(state["entries"][0]["status"], "failed")
        self.assertEqual(self.actions(state, "2026-08-21T13:00:00.000Z")["actions"], [])

    def test_observer_copy_is_non_authority_and_never_blocks_primary(self) -> None:
        directory = copy.deepcopy(self.directory)
        directory["observerSubscriptions"][0]["purpose"] = "material_transition"
        snapshot = MODULE.DIRECTORY.build_snapshot(directory)
        decision = MODULE.enqueue_event(
            MODULE.empty_state(),
            self.event(kind="progress", material="implementation-v1"),
            self.policy,
            snapshot,
            directory,
        )
        self.assertEqual(len(decision["state"]["entries"]), 2)
        primary = next(
            item for item in decision["state"]["entries"] if item["deliveryRole"] == "primary"
        )
        observer = next(
            item for item in decision["state"]["entries"] if item["deliveryRole"] == "observer"
        )
        self.assertFalse(observer["authority"])
        self.assertFalse(observer["notify"])
        state = decision["state"]
        for moment in (
            "2026-08-21T12:00:01.000Z",
            "2026-08-21T12:01:01.000Z",
            "2026-08-21T12:02:01.000Z",
        ):
            state = self.result(
                state,
                next(item for item in state["entries"] if item["entryId"] == observer["entryId"]),
                action="send",
                outcome="busy",
                now=moment,
            )
        current_primary = next(
            item for item in state["entries"] if item["entryId"] == primary["entryId"]
        )
        current_observer = next(
            item for item in state["entries"] if item["entryId"] == observer["entryId"]
        )
        self.assertEqual(current_observer["status"], "failed")
        self.assertEqual(current_primary["status"], "pending")

    def test_progress_and_blocker_coalesce_but_fingerprint_is_once_only(self) -> None:
        for kind in ("progress", "blocker"):
            with self.subTest(kind=kind):
                first = self.enqueue(kind=kind, material=f"{kind}-v1")["state"]
                second = self.enqueue(first, kind=kind, material=f"{kind}-v2")["state"]
                self.assertEqual(
                    [item["status"] for item in second["entries"]],
                    ["coalesced", "pending"],
                )
                duplicate = self.enqueue(second, kind=kind, material=f"{kind}-v2")
                self.assertFalse(duplicate["writeRequired"])

        user_input = self.enqueue(kind="needs_user_input", material="choice-a")["state"]
        duplicate = self.enqueue(
            user_input, kind="needs_user_input", material="choice-a"
        )
        self.assertFalse(duplicate["writeRequired"])
        changed = self.enqueue(
            user_input, kind="needs_user_input", material="choice-b"
        )
        self.assertEqual(len(changed["state"]["entries"]), 2)

    def test_reply_does_not_escalate_and_hop_count_is_bounded(self) -> None:
        reply = self.enqueue(trigger="reply")
        self.assertFalse(reply["writeRequired"])
        self.assertEqual(reply["state"], MODULE.empty_state())
        with self.assertRaises(MODULE.OutboxError) as context:
            self.enqueue(hop_count=self.policy["maxHopCount"] + 1)
        self.assertEqual(context.exception.code, "hop_limit_exceeded")

    def test_receipt_must_match_deterministic_message_id(self) -> None:
        state = self.enqueue()["state"]
        entry = state["entries"][0]
        with self.assertRaises(MODULE.OutboxError) as context:
            MODULE.record_result(
                state,
                entry["entryId"],
                {
                    "action": "send",
                    "outcome": "delivered",
                    "messageId": "0" * 64,
                    "readbackConfirmed": True,
                    "remoteReceiptId": "turn-v1",
                },
                self.policy,
                "2026-08-21T12:00:01.000Z",
            )
        self.assertEqual(context.exception.code, "message_id_mismatch")

    def test_fixture_covers_required_chronologies(self) -> None:
        fixture = json.loads(CHRONOLOGIES_FIXTURE.read_text())
        self.assertEqual(
            {item["name"] for item in fixture["cases"]},
            {
                "duplicate-delivery-and-restart",
                "ambiguous-acceptance-readback",
                "busy-recipient-bounded-fallback",
                "quiet-no-change",
                "moved-binding",
                "unavailable-provider",
                "linear-fallback-bounded",
                "terminal-owner",
                "observer-subscription-copy",
                "blocker-once-per-fingerprint",
                "reply-does-not-escalate",
                "bounded-causal-hop",
            },
        )


if __name__ == "__main__":
    unittest.main()
