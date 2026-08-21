#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("agent_directory.py")
SPEC = importlib.util.spec_from_file_location("agent_directory", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

FIXTURES = Path(__file__).parent.parent / "fixtures"
DIRECTORY_FIXTURE = FIXTURES / "directory-v1.json"
CONFORMANCE_FIXTURE = FIXTURES / "conformance-v1.json"
SNAPSHOT_FIXTURE = FIXTURES / "snapshot-v1.json"
REPARENT_PROPOSAL_FIXTURE = FIXTURES / "reparent-proposal-v1.json"
DESTINATION_READBACK_FIXTURE = FIXTURES / "destination-readback-v1.json"
REPARENTED_DIRECTORY_FIXTURE = FIXTURES / "directory-reparented-v1.json"
REPARENTED_SNAPSHOT_FIXTURE = FIXTURES / "snapshot-reparented-v1.json"


class DirectoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = MODULE.load_json(DIRECTORY_FIXTURE)
        self.root = MODULE.parse_identity("codex:019fabe3-6424-7583-997d-0b93afc18972:local")
        self.domain = MODULE.parse_identity("codex:01a0233b-65c0-7972-9ced-3e9b55ef6486:local")
        self.independent = MODULE.parse_identity("codex:01900000-0000-7000-8000-000000000099:local")

    def assert_error(self, code: str, callback) -> MODULE.DirectoryError:
        with self.assertRaises(MODULE.DirectoryError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code, caught.exception.as_dict())
        return caught.exception

    def readback(self, proposal: dict, *, accepted: bool = True) -> dict:
        proposed = proposal["proposedBinding"]
        return {
            "schemaVersion": MODULE.READBACK_VERSION,
            "proposalDigest": proposal["proposalDigest"],
            "bindingDigest": MODULE._binding_revision_digest(proposed),
            "identity": copy.deepcopy(proposed["identity"]),
            "destinationHostId": proposed["placement"]["currentHostId"],
            "bindingRevision": proposed["bindingRevision"],
            "executionEpoch": proposed["executionEpoch"],
            "observedAt": "2026-08-21T09:30:01Z",
            "accepted": accepted,
        }

    def test_canonical_directory_and_snapshot_read_back(self) -> None:
        MODULE.validate_directory(self.directory)
        snapshot = MODULE.build_snapshot(self.directory)
        MODULE.validate_snapshot(snapshot)
        self.assertEqual(snapshot["directoryRevision"], 1)
        self.assertEqual(len(snapshot["bindings"]), 3)
        self.assertTrue(all(item["state"] == "active" for item in snapshot["bindings"]))
        self.assertEqual(
            MODULE.lookup_binding(snapshot, self.domain, self.directory)["role"],
            "domain_lead",
        )
        self.assertEqual(snapshot["sourceReadback"]["pageId"], "00000000-0000-4000-8000-000000000003")
        self.assertEqual(snapshot, MODULE.load_json(SNAPSHOT_FIXTURE))

    def test_reparent_requires_matching_destination_readback_and_supersedes_prior(self) -> None:
        proposal = MODULE.propose_reparent(
            self.directory,
            self.domain,
            self.independent,
            "local-moved",
            "2026-08-21T09:30:00Z",
        )
        denied = self.readback(proposal, accepted=False)
        self.assert_error(
            "destination_readback_failed",
            lambda: MODULE.apply_reparent(self.directory, proposal, denied),
        )
        mismatched = self.readback(proposal)
        mismatched["destinationHostId"] = "wrong-host"
        self.assert_error(
            "destination_readback_mismatch",
            lambda: MODULE.apply_reparent(self.directory, proposal, mismatched),
        )
        predating = self.readback(proposal)
        predating["observedAt"] = "2026-08-21T09:29:59Z"
        self.assert_error(
            "destination_readback_mismatch",
            lambda: MODULE.apply_reparent(self.directory, proposal, predating),
        )

        updated = MODULE.apply_reparent(self.directory, proposal, self.readback(proposal))
        self.assertEqual(updated["directoryRevision"], 2)
        history = [item for item in updated["bindings"] if MODULE.identity_key(item["identity"]) == MODULE.identity_key(self.domain)]
        self.assertEqual([item["state"] for item in history], ["superseded", "active"])
        active = history[-1]
        self.assertEqual(active["reportsTo"], self.independent)
        self.assertEqual(active["placement"]["currentHostId"], "local-moved")
        self.assertEqual(active["bindingRevision"], 2)
        self.assertEqual(active["executionEpoch"], 2)
        MODULE.validate_snapshot(MODULE.build_snapshot(updated))

    def test_reparent_proposal_rejects_noop_and_cycle_before_readback(self) -> None:
        self.assert_error(
            "no_binding_change",
            lambda: MODULE.propose_reparent(
                self.directory,
                self.domain,
                self.root,
                "local",
                "2026-08-21T09:30:00Z",
            ),
        )

    def test_reparent_proposal_cannot_change_role_scope_root_or_capabilities(self) -> None:
        base = MODULE.propose_reparent(
            self.directory,
            self.domain,
            self.independent,
            "local-moved",
            "2026-08-21T09:30:00Z",
        )
        mutations = {
            "root": lambda binding: binding.update(
                {"root": True, "role": "machine_engineering_lead", "reportsTo": None}
            ),
            "scope": lambda binding: binding["scope"].update({"authorityRef": "user:forged"}),
            "capabilities": lambda binding: binding["advertisedCapabilities"].append(
                {
                    "capability": "resume_task",
                    "status": "live_proven",
                    "routeRef": "codex:resume-task",
                }
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                proposal = copy.deepcopy(base)
                mutate(proposal["proposedBinding"])
                core = {
                    key: copy.deepcopy(value)
                    for key, value in proposal.items()
                    if key != "proposalDigest"
                }
                proposal["proposalDigest"] = MODULE.digest(core)
                self.assert_error(
                    "proposal_changes_unowned_fields",
                    lambda proposal=proposal: MODULE.apply_reparent(
                        self.directory, proposal, self.readback(proposal)
                    ),
                )

        with_child = copy.deepcopy(self.directory)
        child_identity = MODULE.parse_identity("codex:01900000-0000-7000-8000-000000000088:local")
        child = copy.deepcopy(with_child["bindings"][1])
        child["identity"] = child_identity
        child["role"] = "delivery_owner"
        child["reportsTo"] = copy.deepcopy(self.domain)
        child["scope"]["domain"] = "fixture child"
        with_child["bindings"].append(child)
        MODULE.validate_directory(with_child)
        self.assert_error(
            "cycle",
            lambda: MODULE.propose_reparent(
                with_child,
                self.domain,
                child_identity,
                "local-moved",
                "2026-08-21T09:30:00Z",
            ),
        )

    def test_stale_revisions_fail_closed(self) -> None:
        proposal = MODULE.propose_reparent(
            self.directory,
            self.domain,
            self.independent,
            "local-moved",
            "2026-08-21T09:30:00Z",
        )
        changed = copy.deepcopy(self.directory)
        changed["directoryRevision"] += 1
        self.assert_error(
            "stale_directory_revision",
            lambda: MODULE.apply_reparent(changed, proposal, self.readback(proposal)),
        )

        changed_binding = copy.deepcopy(self.directory)
        changed_binding["bindings"][1]["scope"]["domain"] = "changed without revision"
        self.assert_error(
            "stale_binding_revision",
            lambda: MODULE.apply_reparent(
                changed_binding, proposal, self.readback(proposal)
            ),
        )

        duplicate = copy.deepcopy(self.directory)
        duplicate["bindings"].append(copy.deepcopy(duplicate["bindings"][1]))
        self.assert_error("duplicate_active_binding", lambda: MODULE.validate_directory(duplicate))

        skipped = copy.deepcopy(self.directory)
        record = copy.deepcopy(skipped["bindings"][1])
        skipped["bindings"][1]["state"] = "superseded"
        record["bindingRevision"] = 3
        record["executionEpoch"] = 2
        record["supersedes"] = {
            "bindingRevision": 1,
            "executionEpoch": 1,
            "bindingDigest": MODULE._binding_revision_digest(skipped["bindings"][1]),
        }
        skipped["bindings"].append(record)
        self.assert_error("stale_revision", lambda: MODULE.validate_directory(skipped))

        wrong_epoch = MODULE.load_json(REPARENTED_DIRECTORY_FIXTURE)
        wrong_epoch["bindings"][-1]["executionEpoch"] = 7
        self.assert_error("stale_epoch", lambda: MODULE.validate_directory(wrong_epoch))

        backdated = MODULE.load_json(REPARENTED_DIRECTORY_FIXTURE)
        backdated["bindings"][-1]["issuedAt"] = "2026-08-21T09:00:00Z"
        self.assert_error("stale_issued_at", lambda: MODULE.validate_directory(backdated))

    def test_cycle_missing_parent_and_multiple_parents_fail_closed(self) -> None:
        cycle = copy.deepcopy(self.directory)
        root = cycle["bindings"][0]
        root["root"] = False
        root["reportsTo"] = copy.deepcopy(self.domain)
        self.assert_error("cycle", lambda: MODULE.validate_directory(cycle))

        missing = copy.deepcopy(self.directory)
        missing["bindings"][1]["reportsTo"]["taskId"] = "missing-task"
        self.assert_error("missing_recipient", lambda: MODULE.validate_directory(missing))

        revoked_parent = copy.deepcopy(self.directory)
        revoked_parent["bindings"][0]["state"] = "revoked"
        self.assert_error(
            "missing_recipient", lambda: MODULE.validate_directory(revoked_parent)
        )

        multiple = copy.deepcopy(self.directory)
        multiple["bindings"][1]["reportsTo"] = [self.root, self.independent]
        self.assert_error("multiple_primary_parents", lambda: MODULE.validate_directory(multiple))

    def test_identity_is_exact_and_not_inferred(self) -> None:
        wildcard = copy.deepcopy(self.directory)
        wildcard["bindings"][1]["identity"]["hostScope"] = "*"
        self.assert_error("ambiguous_identity", lambda: MODULE.validate_directory(wildcard))

        implicit = copy.deepcopy(self.directory)
        implicit["bindings"][1]["identity"]["title"] = "Cloud lead"
        self.assert_error("unknown_field", lambda: MODULE.validate_directory(implicit))

        absent_host = copy.deepcopy(self.directory)
        del absent_host["bindings"][1]["identity"]["hostScope"]
        self.assert_error("missing_field", lambda: MODULE.validate_directory(absent_host))

    def test_observer_subscription_and_messages_never_grant_authority(self) -> None:
        snapshot = MODULE.build_snapshot(self.directory)
        route = MODULE.resolve_contact(
            snapshot, self.domain, "message_existing_task", self.directory
        )
        self.assertFalse(route["authority"])
        self.assertTrue(route["recipientMustRevalidate"])
        self.assert_error(
            "capability_unsupported",
            lambda: MODULE.resolve_contact(
                snapshot, self.domain, "archive_task", self.directory
            ),
        )

        invalid = copy.deepcopy(self.directory)
        invalid["observerSubscriptions"][0]["authority"] = True
        self.assert_error("observer_is_authority", lambda: MODULE.validate_directory(invalid))

        duplicate = copy.deepcopy(self.directory)
        second_revision = copy.deepcopy(duplicate["observerSubscriptions"][0])
        second_revision["revision"] = 2
        duplicate["observerSubscriptions"].append(second_revision)
        self.assert_error(
            "duplicate_active_subscription", lambda: MODULE.validate_directory(duplicate)
        )

        duplicate_snapshot = MODULE.build_snapshot(self.directory)
        duplicate_snapshot["observerSubscriptions"].append(second_revision)
        self.assert_error(
            "duplicate_active_subscription",
            lambda: MODULE.validate_snapshot(duplicate_snapshot),
        )

    def test_startup_compact_and_resume_reassert_same_snapshot_revision(self) -> None:
        snapshot = MODULE.build_snapshot(self.directory)
        before = MODULE.digest(snapshot)
        revisions = []
        for _source in ("startup", "compact", "resume"):
            binding = MODULE.lookup_binding(snapshot, self.domain, self.directory)
            revisions.append((snapshot["directoryRevision"], binding["bindingRevision"], binding["executionEpoch"]))
        self.assertEqual(revisions, [(1, 1, 1)] * 3)
        self.assertEqual(MODULE.digest(snapshot), before)

    def test_fork_and_revoked_bindings_are_unbound(self) -> None:
        snapshot = MODULE.build_snapshot(self.directory)
        fork = MODULE.parse_identity("codex:01900000-0000-7000-8000-000000000404:local")
        self.assert_error(
            "unbound", lambda: MODULE.lookup_binding(snapshot, fork, self.directory)
        )

        revoked = copy.deepcopy(self.directory)
        revoked["bindings"][1]["state"] = "revoked"
        revoked["observerSubscriptions"][0]["state"] = "revoked"
        revoked_snapshot = MODULE.build_snapshot(revoked)
        self.assert_error(
            "unbound",
            lambda: MODULE.lookup_binding(revoked_snapshot, self.domain, revoked),
        )

    def test_snapshot_is_bounded_and_deterministic(self) -> None:
        first = MODULE.build_snapshot(self.directory)
        reversed_directory = copy.deepcopy(self.directory)
        reversed_directory["bindings"].reverse()
        second = MODULE.build_snapshot(reversed_directory)
        self.assertEqual(
            [MODULE.identity_string(item["identity"]) for item in first["bindings"]],
            [MODULE.identity_string(item["identity"]) for item in second["bindings"]],
        )
        self.assertLessEqual(len(MODULE.canonical_bytes(first)), MODULE.MAX_SNAPSHOT_BYTES)
        self.assertLessEqual(len(MODULE.snapshot_bytes(first)), MODULE.MAX_SNAPSHOT_BYTES)

        with tempfile.TemporaryDirectory() as temp:
            oversized_path = Path(temp) / "oversized-snapshot.json"
            oversized_path.write_bytes(
                b" " * (MODULE.MAX_SNAPSHOT_BYTES + 1)
                + SNAPSHOT_FIXTURE.read_bytes()
            )
            self.assertGreater(oversized_path.stat().st_size, MODULE.MAX_SNAPSHOT_BYTES)
            self.assert_error(
                "snapshot_too_large", lambda: MODULE.load_snapshot(oversized_path)
            )
            self.assertEqual(
                MODULE.main(
                    [
                        "lookup",
                        str(oversized_path),
                        "--directory",
                        str(DIRECTORY_FIXTURE),
                        "--identity",
                        MODULE.identity_string(self.domain),
                    ]
                ),
                2,
            )

    def test_snapshot_lookup_rejects_stale_or_edited_projection(self) -> None:
        snapshot = MODULE.build_snapshot(self.directory)
        stale_directory = copy.deepcopy(self.directory)
        stale_directory["directoryRevision"] += 1
        self.assert_error(
            "stale_snapshot",
            lambda: MODULE.lookup_binding(snapshot, self.domain, stale_directory),
        )

        edited = copy.deepcopy(snapshot)
        domain = next(
            item
            for item in edited["bindings"]
            if MODULE.identity_key(item["identity"]) == MODULE.identity_key(self.domain)
        )
        domain["role"] = "engineering_lead"
        domain["placement"]["currentHostId"] = "edited-host"
        self.assert_error(
            "snapshot_projection_mismatch",
            lambda: MODULE.lookup_binding(edited, self.domain, self.directory),
        )

    def test_cli_round_trip_and_error_exit(self) -> None:
        self.assertEqual(MODULE.main(["validate", str(DIRECTORY_FIXTURE)]), 0)
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "snapshot.json"
            self.assertEqual(
                MODULE.main(["snapshot", str(DIRECTORY_FIXTURE), "--output", str(target)]),
                0,
            )
            self.assertEqual(
                MODULE.main(
                    [
                        "lookup",
                        str(target),
                        "--directory",
                        str(DIRECTORY_FIXTURE),
                        "--identity",
                        MODULE.identity_string(self.domain),
                    ]
                ),
                0,
            )
            self.assertEqual(
                MODULE.main(
                    [
                        "lookup",
                        str(target),
                        "--directory",
                        str(DIRECTORY_FIXTURE),
                        "--identity",
                        "codex:missing:local",
                    ]
                ),
                2,
            )

    def test_cli_reparent_serialization_and_readback_fixtures(self) -> None:
        source_bytes = DIRECTORY_FIXTURE.read_bytes()
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            proposal_path = temp_path / "proposal.json"
            updated_path = temp_path / "updated.json"
            snapshot_path = temp_path / "snapshot.json"
            self.assertEqual(
                MODULE.main(
                    [
                        "propose-reparent",
                        str(DIRECTORY_FIXTURE),
                        "--target",
                        MODULE.identity_string(self.domain),
                        "--new-parent",
                        MODULE.identity_string(self.independent),
                        "--destination-host",
                        "local-moved",
                        "--issued-at",
                        "2026-08-21T09:30:00Z",
                        "--output",
                        str(proposal_path),
                    ]
                ),
                0,
            )
            self.assertEqual(MODULE.load_json(proposal_path), MODULE.load_json(REPARENT_PROPOSAL_FIXTURE))
            self.assertEqual(
                MODULE.main(
                    [
                        "apply-reparent",
                        str(DIRECTORY_FIXTURE),
                        str(proposal_path),
                        str(DESTINATION_READBACK_FIXTURE),
                        "--output",
                        str(updated_path),
                    ]
                ),
                0,
            )
            self.assertEqual(MODULE.load_json(updated_path), MODULE.load_json(REPARENTED_DIRECTORY_FIXTURE))
            self.assertEqual(
                MODULE.main(["snapshot", str(updated_path), "--output", str(snapshot_path)]),
                0,
            )
            self.assertEqual(MODULE.load_json(snapshot_path), MODULE.load_json(REPARENTED_SNAPSHOT_FIXTURE))
            moved = MODULE.lookup_binding(
                MODULE.load_json(snapshot_path), self.domain, MODULE.load_json(updated_path)
            )
            self.assertEqual(moved["bindingRevision"], 2)
            self.assertEqual(moved["reportsTo"], self.independent)

            denied = MODULE.load_json(DESTINATION_READBACK_FIXTURE)
            denied["accepted"] = False
            denied_path = temp_path / "denied.json"
            denied_output = temp_path / "denied-output.json"
            MODULE.write_json(denied_path, denied)
            self.assertEqual(
                MODULE.main(
                    [
                        "apply-reparent",
                        str(DIRECTORY_FIXTURE),
                        str(proposal_path),
                        str(denied_path),
                        "--output",
                        str(denied_output),
                    ]
                ),
                2,
            )
            self.assertFalse(denied_output.exists())

            stale = copy.deepcopy(self.directory)
            stale["directoryRevision"] += 1
            stale_path = temp_path / "stale.json"
            stale_output = temp_path / "stale-output.json"
            MODULE.write_json(stale_path, stale)
            self.assertEqual(
                MODULE.main(
                    [
                        "apply-reparent",
                        str(stale_path),
                        str(proposal_path),
                        str(DESTINATION_READBACK_FIXTURE),
                        "--output",
                        str(stale_output),
                    ]
                ),
                2,
            )
            self.assertFalse(stale_output.exists())
        self.assertEqual(DIRECTORY_FIXTURE.read_bytes(), source_bytes)

    def test_local_lookup_latency_is_measurable(self) -> None:
        result = MODULE.benchmark_lookup(
            MODULE.build_snapshot(self.directory), self.directory, self.domain, 100
        )
        self.assertEqual(result["iterations"], 100)
        self.assertGreaterEqual(result["p50Ms"], 0)
        self.assertLess(result["p95Ms"], 500)


class ConformanceFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = MODULE.load_json(DIRECTORY_FIXTURE)

    def assert_error(self, code: str, callback) -> MODULE.DirectoryError:
        with self.assertRaises(MODULE.DirectoryError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code, caught.exception.as_dict())
        return caught.exception

    def readback(self, proposal: dict, *, accepted: bool = True) -> dict:
        proposed = proposal["proposedBinding"]
        return {
            "schemaVersion": MODULE.READBACK_VERSION,
            "proposalDigest": proposal["proposalDigest"],
            "bindingDigest": MODULE._binding_revision_digest(proposed),
            "identity": copy.deepcopy(proposed["identity"]),
            "destinationHostId": proposed["placement"]["currentHostId"],
            "bindingRevision": proposed["bindingRevision"],
            "executionEpoch": proposed["executionEpoch"],
            "observedAt": "2026-08-21T09:30:01Z",
            "accepted": accepted,
        }

    def test_declared_conformance_cases(self) -> None:
        fixture = MODULE.load_json(CONFORMANCE_FIXTURE)
        self.assertEqual(fixture["schemaVersion"], "bradley.agent-organization-conformance/v1")
        identities = {name: MODULE.parse_identity(value) for name, value in fixture["identities"].items()}
        snapshot = MODULE.build_snapshot(self.directory)

        for case in fixture["cases"]:
            with self.subTest(case=case["name"]):
                expected = case["expected"]

                def run_case():
                    operation = case["operation"]
                    if operation in {"lookup", "repeat-lookup"}:
                        repetitions = case.get("repetitions", 1)
                        result = None
                        for _ in range(repetitions):
                            result = MODULE.lookup_binding(
                                snapshot, identities[case["identity"]], self.directory
                            )
                        return result
                    if operation == "contact":
                        return MODULE.resolve_contact(
                            snapshot,
                            identities[case["identity"]],
                            case["capability"],
                            self.directory,
                        )
                    if operation == "reparent":
                        proposal = MODULE.propose_reparent(
                            self.directory,
                            identities[case["target"]],
                            identities[case["newParent"]],
                            case["destinationHostId"],
                            "2026-08-21T09:30:00Z",
                        )
                        directory = copy.deepcopy(self.directory)
                        if case.get("mutateDirectoryRevisionAfterProposal"):
                            directory["directoryRevision"] += 1
                        readback = self.readback(proposal, accepted=case["readback"] == "exact-accepted")
                        return MODULE.apply_reparent(directory, proposal, readback)
                    if operation == "mutate-target-after-proposal":
                        proposal = MODULE.load_json(REPARENT_PROPOSAL_FIXTURE)
                        directory = copy.deepcopy(self.directory)
                        directory["bindings"][1]["scope"]["domain"] = "changed without revision"
                        return MODULE.apply_reparent(
                            directory,
                            proposal,
                            MODULE.load_json(DESTINATION_READBACK_FIXTURE),
                        )
                    if operation == "skew-reparented-epoch":
                        value = MODULE.load_json(REPARENTED_DIRECTORY_FIXTURE)
                        value["bindings"][-1]["executionEpoch"] = 7
                        return MODULE.validate_directory(value)
                    if operation == "backdate-reparented-binding":
                        value = MODULE.load_json(REPARENTED_DIRECTORY_FIXTURE)
                        value["bindings"][-1]["issuedAt"] = "2026-08-21T09:00:00Z"
                        return MODULE.validate_directory(value)
                    if operation == "mutate-root-under-domain-lead":
                        value = copy.deepcopy(self.directory)
                        value["bindings"][0]["root"] = False
                        value["bindings"][0]["reportsTo"] = copy.deepcopy(identities["domainLead"])
                        return MODULE.validate_directory(value)
                    if operation == "set-two-primary-parents":
                        value = copy.deepcopy(self.directory)
                        value["bindings"][1]["reportsTo"] = [identities["root"], identities["independentRoot"]]
                        return MODULE.validate_directory(value)
                    if operation == "set-observer-authority-true":
                        value = copy.deepcopy(self.directory)
                        value["observerSubscriptions"][0]["authority"] = True
                        return MODULE.validate_directory(value)
                    if operation == "add-active-observer-revision":
                        value = copy.deepcopy(self.directory)
                        second = copy.deepcopy(value["observerSubscriptions"][0])
                        second["revision"] = 2
                        value["observerSubscriptions"].append(second)
                        return MODULE.validate_directory(value)
                    if operation == "revoke-and-lookup":
                        value = copy.deepcopy(self.directory)
                        value["bindings"][1]["state"] = "revoked"
                        value["observerSubscriptions"][0]["state"] = "revoked"
                        return MODULE.lookup_binding(
                            MODULE.build_snapshot(value), identities[case["identity"]], value
                        )
                    if operation == "revoke-parent-with-active-child":
                        value = copy.deepcopy(self.directory)
                        value["bindings"][0]["state"] = "revoked"
                        return MODULE.validate_directory(value)
                    self.fail(f"unsupported fixture operation: {operation}")

                if expected == "ok":
                    self.assertIsNotNone(run_case())
                else:
                    self.assert_error(expected, run_case)


if __name__ == "__main__":
    unittest.main()
