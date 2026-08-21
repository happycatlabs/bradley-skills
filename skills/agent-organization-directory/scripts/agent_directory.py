#!/usr/bin/env python3
"""Validate and project the provider-neutral Agent Organization Directory v1."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn


DIRECTORY_VERSION = "bradley.agent-organization-directory/v1"
BINDING_VERSION = "bradley.agent-organization-binding/v1"
SUBSCRIPTION_VERSION = "bradley.agent-observer-subscription/v1"
SNAPSHOT_VERSION = "bradley.agent-organization-snapshot/v1"
PROPOSAL_VERSION = "bradley.agent-organization-reparent-proposal/v1"
READBACK_VERSION = "bradley.agent-organization-destination-readback/v1"

MAX_BINDING_RECORDS = 256
MAX_ACTIVE_BINDINGS = 128
MAX_SUBSCRIPTIONS = 512
MAX_CAPABILITIES = 32
MAX_STRING_LENGTH = 4096
MAX_SNAPSHOT_BYTES = 256 * 1024

ROLES = {
    "machine_engineering_lead",
    "engineering_lead",
    "project_lead",
    "domain_lead",
    "delivery_owner",
    "exploration_owner",
    "watcher",
    "leaf_worker",
    "leaf_scout",
}
BINDING_STATES = {"active", "superseded", "revoked"}
PRIVACY_CLASSES = {"public_metadata", "internal_metadata", "restricted_metadata"}
CAPABILITIES = {
    "inspect_task",
    "message_existing_task",
    "resume_task",
    "create_recovery_task",
    "interrupt_task",
    "archive_task",
}
CAPABILITY_STATUSES = {
    "live_proven",
    "source_proven",
    "documented_only",
    "desired",
    "unsupported",
}
SUBSCRIPTION_STATES = {"active", "revoked"}
SUBSCRIPTION_PURPOSES = {
    "portfolio_visibility",
    "matrix_visibility",
    "material_transition",
}
ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
SAFE_ROUTE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,255}$")


class DirectoryError(ValueError):
    def __init__(self, code: str, path: str, message: str):
        super().__init__(message)
        self.code = code
        self.path = path
        self.message = message

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


def fail(code: str, path: str, message: str) -> NoReturn:
    raise DirectoryError(code, path, message)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _object(value: Any, path: str, allowed: set[str], required: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail("invalid_type", path, "expected object")
    unknown = set(value) - allowed
    if unknown:
        fail("unknown_field", path, f"unknown fields: {', '.join(sorted(unknown))}")
    missing = required - set(value)
    if missing:
        fail("missing_field", path, f"missing fields: {', '.join(sorted(missing))}")
    return value


def _list(value: Any, path: str, limit: int) -> list[Any]:
    if not isinstance(value, list):
        fail("invalid_type", path, "expected array")
    if len(value) > limit:
        fail("limit_exceeded", path, f"maximum length is {limit}")
    return value


def _string(value: Any, path: str, *, choices: set[str] | None = None) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_STRING_LENGTH:
        fail("invalid_string", path, "expected non-empty bounded string")
    if "\n" in value or "\r" in value or "\x00" in value:
        fail("invalid_string", path, "control characters are not allowed")
    if choices is not None and value not in choices:
        fail("invalid_value", path, f"unsupported value: {value}")
    return value


def _positive_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        fail("invalid_integer", path, "expected positive integer")
    return value


def _timestamp(value: Any, path: str) -> str:
    result = _string(value, path)
    if not ISO_UTC.fullmatch(result):
        fail("invalid_timestamp", path, "expected UTC ISO-8601 timestamp")
    return result


def _timestamp_value(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_identity(value: Any, path: str) -> dict[str, str]:
    identity = _object(
        value,
        path,
        {"provider", "taskId", "hostScope"},
        {"provider", "taskId", "hostScope"},
    )
    for field in ("provider", "taskId", "hostScope"):
        item = _string(identity[field], f"{path}.{field}")
        if "*" in item or ":" in item or item.strip() != item:
            fail("ambiguous_identity", f"{path}.{field}", "wildcards, colons, and surrounding whitespace are forbidden")
    return identity


def identity_key(identity: dict[str, str]) -> tuple[str, str, str]:
    return identity["provider"], identity["taskId"], identity["hostScope"]


def identity_string(identity: dict[str, str]) -> str:
    return ":".join(identity_key(identity))


def parse_identity(value: str) -> dict[str, str]:
    parts = value.split(":", 2)
    if len(parts) != 3 or not all(parts):
        fail("ambiguous_identity", "identity", "expected provider:taskId:hostScope")
    return validate_identity(
        {"provider": parts[0], "taskId": parts[1], "hostScope": parts[2]}, "identity"
    )


def _validate_source_readback(value: Any, path: str) -> None:
    source = _object(
        value,
        path,
        {"provider", "workspaceId", "rootPageId", "pageId", "pageUrl", "observedAt"},
        {"provider", "workspaceId", "rootPageId", "pageId", "pageUrl", "observedAt"},
    )
    if _string(source["provider"], f"{path}.provider") != "notion":
        fail("invalid_source", f"{path}.provider", "v1 durable source must be notion")
    for field in ("workspaceId", "rootPageId", "pageId"):
        _string(source[field], f"{path}.{field}")
    page_url = _string(source["pageUrl"], f"{path}.pageUrl")
    if not page_url.startswith("https://app.notion.com/p/"):
        fail("invalid_source", f"{path}.pageUrl", "expected canonical Notion page URL")
    _timestamp(source["observedAt"], f"{path}.observedAt")


def _validate_scope(value: Any, path: str) -> None:
    scope = _object(
        value,
        path,
        {"team", "project", "domain", "contractRef", "authorityRef", "privacyClass"},
        {"team", "project", "contractRef", "authorityRef", "privacyClass"},
    )
    for field in ("team", "project", "contractRef", "authorityRef"):
        _string(scope[field], f"{path}.{field}")
    if "domain" in scope and scope["domain"] is not None:
        _string(scope["domain"], f"{path}.domain")
    _string(scope["privacyClass"], f"{path}.privacyClass", choices=PRIVACY_CLASSES)


def _validate_capabilities(value: Any, path: str) -> None:
    items = _list(value, path, MAX_CAPABILITIES)
    seen: set[str] = set()
    for index, raw in enumerate(items):
        item_path = f"{path}[{index}]"
        item = _object(raw, item_path, {"capability", "status", "routeRef"}, {"capability", "status", "routeRef"})
        capability = _string(item["capability"], f"{item_path}.capability", choices=CAPABILITIES)
        if capability in seen:
            fail("duplicate_capability", item_path, f"duplicate capability: {capability}")
        seen.add(capability)
        status = _string(item["status"], f"{item_path}.status", choices=CAPABILITY_STATUSES)
        route = item["routeRef"]
        if status == "live_proven":
            checked_route = _string(route, f"{item_path}.routeRef")
            if not SAFE_ROUTE.fullmatch(checked_route):
                fail("unsafe_contact_route", f"{item_path}.routeRef", "route must be an opaque capability identifier without credentials or content")
        elif route is not None:
            fail("unproven_contact_route", f"{item_path}.routeRef", "only live_proven capabilities may advertise a route")


def _binding_revision_digest(binding: dict[str, Any]) -> str:
    projection = copy.deepcopy(binding)
    projection.pop("state", None)
    return digest(projection)


def _validate_binding(value: Any, path: str) -> dict[str, Any]:
    binding = _object(
        value,
        path,
        {
            "schemaVersion",
            "identity",
            "bindingRevision",
            "executionEpoch",
            "state",
            "root",
            "role",
            "scope",
            "placement",
            "reportsTo",
            "issuedAt",
            "supersedes",
            "advertisedCapabilities",
        },
        {
            "schemaVersion",
            "identity",
            "bindingRevision",
            "executionEpoch",
            "state",
            "root",
            "role",
            "scope",
            "placement",
            "reportsTo",
            "issuedAt",
            "supersedes",
            "advertisedCapabilities",
        },
    )
    if binding["schemaVersion"] != BINDING_VERSION:
        fail("unsupported_version", f"{path}.schemaVersion", "unsupported binding version")
    validate_identity(binding["identity"], f"{path}.identity")
    _positive_int(binding["bindingRevision"], f"{path}.bindingRevision")
    _positive_int(binding["executionEpoch"], f"{path}.executionEpoch")
    _string(binding["state"], f"{path}.state", choices=BINDING_STATES)
    if not isinstance(binding["root"], bool):
        fail("invalid_type", f"{path}.root", "expected boolean")
    _string(binding["role"], f"{path}.role", choices=ROLES)
    _validate_scope(binding["scope"], f"{path}.scope")
    placement = _object(binding["placement"], f"{path}.placement", {"currentHostId"}, {"currentHostId"})
    _string(placement["currentHostId"], f"{path}.placement.currentHostId")
    reports_to = binding["reportsTo"]
    if binding["root"]:
        if reports_to is not None:
            fail("root_has_parent", f"{path}.reportsTo", "root binding must report to the user, not another task")
    elif reports_to is None:
        fail("missing_primary_parent", f"{path}.reportsTo", "non-root binding requires exactly one primary parent")
    elif isinstance(reports_to, list):
        fail("multiple_primary_parents", f"{path}.reportsTo", "non-root binding cannot have multiple primary parents")
    else:
        validate_identity(reports_to, f"{path}.reportsTo")
    _timestamp(binding["issuedAt"], f"{path}.issuedAt")
    supersedes = binding["supersedes"]
    if binding["bindingRevision"] == 1:
        if supersedes is not None:
            fail("unexpected_supersedes", f"{path}.supersedes", "revision 1 must not supersede another revision")
    else:
        prior = _object(
            supersedes,
            f"{path}.supersedes",
            {"bindingRevision", "executionEpoch", "bindingDigest"},
            {"bindingRevision", "executionEpoch", "bindingDigest"},
        )
        _positive_int(prior["bindingRevision"], f"{path}.supersedes.bindingRevision")
        _positive_int(prior["executionEpoch"], f"{path}.supersedes.executionEpoch")
        if not isinstance(prior["bindingDigest"], str) or not HEX_64.fullmatch(prior["bindingDigest"]):
            fail("invalid_digest", f"{path}.supersedes.bindingDigest", "expected lowercase SHA-256")
    _validate_capabilities(binding["advertisedCapabilities"], f"{path}.advertisedCapabilities")
    return binding


def _validate_subscription(value: Any, path: str) -> dict[str, Any]:
    item = _object(
        value,
        path,
        {"schemaVersion", "subscriber", "observes", "revision", "state", "purpose", "authority"},
        {"schemaVersion", "subscriber", "observes", "revision", "state", "purpose", "authority"},
    )
    if item["schemaVersion"] != SUBSCRIPTION_VERSION:
        fail("unsupported_version", f"{path}.schemaVersion", "unsupported subscription version")
    validate_identity(item["subscriber"], f"{path}.subscriber")
    validate_identity(item["observes"], f"{path}.observes")
    _positive_int(item["revision"], f"{path}.revision")
    _string(item["state"], f"{path}.state", choices=SUBSCRIPTION_STATES)
    _string(item["purpose"], f"{path}.purpose", choices=SUBSCRIPTION_PURPOSES)
    if item["authority"] is not False:
        fail("observer_is_authority", f"{path}.authority", "observer subscription must declare authority false")
    return item


def subscription_key(item: dict[str, Any]) -> tuple[tuple[str, str, str], tuple[str, str, str], str]:
    return (
        identity_key(item["subscriber"]),
        identity_key(item["observes"]),
        item["purpose"],
    )


def validate_directory(value: Any) -> dict[str, Any]:
    directory = _object(
        value,
        "$",
        {"schemaVersion", "directoryRevision", "sourceReadback", "bindings", "observerSubscriptions"},
        {"schemaVersion", "directoryRevision", "sourceReadback", "bindings", "observerSubscriptions"},
    )
    if directory["schemaVersion"] != DIRECTORY_VERSION:
        fail("unsupported_version", "$.schemaVersion", "unsupported directory version")
    _positive_int(directory["directoryRevision"], "$.directoryRevision")
    _validate_source_readback(directory["sourceReadback"], "$.sourceReadback")
    bindings = _list(directory["bindings"], "$.bindings", MAX_BINDING_RECORDS)
    subscriptions = _list(directory["observerSubscriptions"], "$.observerSubscriptions", MAX_SUBSCRIPTIONS)

    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for index, raw in enumerate(bindings):
        binding = _validate_binding(raw, f"$.bindings[{index}]")
        groups.setdefault(identity_key(binding["identity"]), []).append(binding)

    active: dict[tuple[str, str, str], dict[str, Any]] = {}
    for key, history in groups.items():
        if sum(item["state"] == "active" for item in history) > 1:
            fail("duplicate_active_binding", "$.bindings", f"duplicate active binding for {':'.join(key)}")
        ordered = sorted(history, key=lambda item: item["bindingRevision"])
        revisions = [item["bindingRevision"] for item in ordered]
        if revisions != list(range(1, len(ordered) + 1)):
            fail("stale_revision", "$.bindings", f"non-contiguous revisions for {':'.join(key)}")
        for index, item in enumerate(ordered):
            if index < len(ordered) - 1 and item["state"] != "superseded":
                fail("stale_revision", "$.bindings", f"historical revision remains {item['state']} for {':'.join(key)}")
            if index:
                previous = ordered[index - 1]
                expected = {
                    "bindingRevision": previous["bindingRevision"],
                    "executionEpoch": previous["executionEpoch"],
                    "bindingDigest": _binding_revision_digest(previous),
                }
                if item["supersedes"] != expected:
                    fail("stale_revision", "$.bindings", f"supersedes mismatch for {':'.join(key)} revision {item['bindingRevision']}")
                if item["executionEpoch"] != previous["executionEpoch"] + 1:
                    fail("stale_epoch", "$.bindings", f"execution epoch must increment once for {':'.join(key)}")
                if _timestamp_value(item["issuedAt"]) <= _timestamp_value(previous["issuedAt"]):
                    fail("stale_issued_at", "$.bindings", f"issued time must increase for {':'.join(key)}")
        current = ordered[-1]
        if current["state"] == "superseded":
            fail("stale_revision", "$.bindings", f"latest revision cannot be superseded for {':'.join(key)}")
        if current["state"] == "active":
            if key in active:
                fail("duplicate_active_binding", "$.bindings", f"duplicate active binding for {':'.join(key)}")
            active[key] = current

    if len(active) > MAX_ACTIVE_BINDINGS:
        fail("limit_exceeded", "$.bindings", f"maximum active bindings is {MAX_ACTIVE_BINDINGS}")

    _validate_active_forest(active, "$.bindings")

    subscription_groups: dict[
        tuple[tuple[str, str, str], tuple[str, str, str], str], list[dict[str, Any]]
    ] = {}
    for index, raw in enumerate(subscriptions):
        item = _validate_subscription(raw, f"$.observerSubscriptions[{index}]")
        subscription_groups.setdefault(subscription_key(item), []).append(item)
    for key, history in subscription_groups.items():
        if sum(item["state"] == "active" for item in history) > 1:
            fail("duplicate_active_subscription", "$.observerSubscriptions", "observer relationship has multiple active revisions")
        ordered = sorted(history, key=lambda item: item["revision"])
        revisions = [item["revision"] for item in ordered]
        if revisions != list(range(1, len(ordered) + 1)):
            fail("stale_subscription_revision", "$.observerSubscriptions", "observer revisions must be contiguous")
        if any(item["state"] != "revoked" for item in ordered[:-1]):
            fail("stale_subscription_revision", "$.observerSubscriptions", "historical observer revisions must be revoked")
        current = ordered[-1]
        if current["state"] == "active" and (key[0] not in active or key[1] not in active):
            fail("missing_recipient", "$.observerSubscriptions", "active subscription identities must resolve")

    return directory


def _validate_active_forest(
    active: dict[tuple[str, str, str], dict[str, Any]], path: str
) -> None:
    edges: dict[tuple[str, str, str], tuple[str, str, str]] = {}
    for key, binding in active.items():
        if binding["root"]:
            continue
        parent_key = identity_key(binding["reportsTo"])
        if parent_key not in active:
            fail("missing_recipient", path, f"primary parent is not active: {':'.join(parent_key)}")
        edges[key] = parent_key
    for start in edges:
        seen: set[tuple[str, str, str]] = set()
        cursor = start
        while cursor in edges:
            if cursor in seen:
                fail("cycle", path, f"cycle includes {':'.join(cursor)}")
            seen.add(cursor)
            cursor = edges[cursor]


def build_snapshot(directory: dict[str, Any]) -> dict[str, Any]:
    validate_directory(directory)
    active_bindings = [copy.deepcopy(item) for item in directory["bindings"] if item["state"] == "active"]
    active_bindings.sort(key=lambda item: identity_key(item["identity"]))
    active_subscriptions = [
        copy.deepcopy(item) for item in directory["observerSubscriptions"] if item["state"] == "active"
    ]
    active_subscriptions.sort(
        key=lambda item: (identity_key(item["subscriber"]), identity_key(item["observes"]), item["purpose"])
    )
    snapshot = {
        "schemaVersion": SNAPSHOT_VERSION,
        "directorySchemaVersion": directory["schemaVersion"],
        "directoryRevision": directory["directoryRevision"],
        "directoryDigest": digest(directory),
        "sourceReadback": copy.deepcopy(directory["sourceReadback"]),
        "bindings": active_bindings,
        "observerSubscriptions": active_subscriptions,
    }
    validate_snapshot(snapshot)
    return snapshot


def validate_snapshot(value: Any) -> dict[str, Any]:
    snapshot = _object(
        value,
        "$",
        {"schemaVersion", "directorySchemaVersion", "directoryRevision", "directoryDigest", "sourceReadback", "bindings", "observerSubscriptions"},
        {"schemaVersion", "directorySchemaVersion", "directoryRevision", "directoryDigest", "sourceReadback", "bindings", "observerSubscriptions"},
    )
    if snapshot["schemaVersion"] != SNAPSHOT_VERSION or snapshot["directorySchemaVersion"] != DIRECTORY_VERSION:
        fail("unsupported_version", "$.schemaVersion", "unsupported snapshot or directory version")
    _positive_int(snapshot["directoryRevision"], "$.directoryRevision")
    if not isinstance(snapshot["directoryDigest"], str) or not HEX_64.fullmatch(snapshot["directoryDigest"]):
        fail("invalid_digest", "$.directoryDigest", "expected lowercase SHA-256")
    _validate_source_readback(snapshot["sourceReadback"], "$.sourceReadback")
    bindings = _list(snapshot["bindings"], "$.bindings", MAX_ACTIVE_BINDINGS)
    seen: set[tuple[str, str, str]] = set()
    active: dict[tuple[str, str, str], dict[str, Any]] = {}
    for index, raw in enumerate(bindings):
        binding = _validate_binding(raw, f"$.bindings[{index}]")
        if binding["state"] != "active":
            fail("snapshot_contains_history", f"$.bindings[{index}].state", "snapshot may contain active bindings only")
        key = identity_key(binding["identity"])
        if key in seen:
            fail("duplicate_active_binding", "$.bindings", f"duplicate active binding for {':'.join(key)}")
        seen.add(key)
        active[key] = binding
    _validate_active_forest(active, "$.bindings")
    subscriptions = _list(snapshot["observerSubscriptions"], "$.observerSubscriptions", MAX_SUBSCRIPTIONS)
    subscription_keys: set[tuple[tuple[str, str, str], tuple[str, str, str], str]] = set()
    for index, raw in enumerate(subscriptions):
        item = _validate_subscription(raw, f"$.observerSubscriptions[{index}]")
        if item["state"] != "active":
            fail("snapshot_contains_history", f"$.observerSubscriptions[{index}].state", "snapshot may contain active subscriptions only")
        if identity_key(item["subscriber"]) not in active or identity_key(item["observes"]) not in active:
            fail("missing_recipient", "$.observerSubscriptions", "snapshot subscription identities must resolve")
        key = subscription_key(item)
        if key in subscription_keys:
            fail("duplicate_active_subscription", "$.observerSubscriptions", "snapshot repeats an active observer relationship")
        subscription_keys.add(key)
    if len(canonical_bytes(snapshot)) > MAX_SNAPSHOT_BYTES:
        fail("snapshot_too_large", "$", f"snapshot exceeds {MAX_SNAPSHOT_BYTES} bytes")
    return snapshot


def verify_snapshot(snapshot: dict[str, Any], directory: dict[str, Any]) -> dict[str, Any]:
    validate_snapshot(snapshot)
    validate_directory(directory)
    if snapshot["directoryRevision"] != directory["directoryRevision"]:
        fail("stale_snapshot", "$.directoryRevision", "snapshot and directory revisions differ")
    if snapshot["directoryDigest"] != digest(directory):
        fail("snapshot_digest_mismatch", "$.directoryDigest", "snapshot is not bound to this directory")
    if snapshot != build_snapshot(directory):
        fail("snapshot_projection_mismatch", "$", "snapshot contents differ from the validated directory projection")
    return snapshot


def lookup_binding(
    snapshot: dict[str, Any], identity: dict[str, str], directory: dict[str, Any]
) -> dict[str, Any]:
    verify_snapshot(snapshot, directory)
    wanted = identity_key(validate_identity(identity, "identity"))
    matches = [item for item in snapshot["bindings"] if identity_key(item["identity"]) == wanted]
    if not matches:
        fail("unbound", "identity", f"no active binding for {':'.join(wanted)}")
    if len(matches) != 1:
        fail("ambiguous_binding", "identity", f"multiple active bindings for {':'.join(wanted)}")
    return copy.deepcopy(matches[0])


def resolve_contact(
    snapshot: dict[str, Any],
    identity: dict[str, str],
    capability: str,
    directory: dict[str, Any],
) -> dict[str, Any]:
    requested = _string(capability, "capability", choices=CAPABILITIES)
    binding = lookup_binding(snapshot, identity, directory)
    for item in binding["advertisedCapabilities"]:
        if item["capability"] == requested and item["status"] == "live_proven" and item["routeRef"]:
            return {
                "identity": copy.deepcopy(binding["identity"]),
                "currentHostId": binding["placement"]["currentHostId"],
                "capability": requested,
                "routeRef": item["routeRef"],
                "authority": False,
                "recipientMustRevalidate": True,
            }
    fail("capability_unsupported", "capability", f"recipient has no live-proven route for {requested}")


def propose_reparent(
    directory: dict[str, Any],
    target_identity: dict[str, str],
    new_parent_identity: dict[str, str],
    destination_host_id: str,
    issued_at: str,
) -> dict[str, Any]:
    validate_directory(directory)
    target = _active_binding(directory, target_identity)
    _active_binding(directory, new_parent_identity)
    if target["root"]:
        fail("cannot_reparent_root", "targetIdentity", "root bindings report directly to the user")
    _string(destination_host_id, "destinationHostId")
    _timestamp(issued_at, "issuedAt")
    if (
        identity_key(target["reportsTo"]) == identity_key(new_parent_identity)
        and target["placement"]["currentHostId"] == destination_host_id
    ):
        fail("no_binding_change", "targetIdentity", "parent and destination host are unchanged")
    proposed = _expected_proposed_binding(
        target, new_parent_identity, destination_host_id, issued_at
    )
    core = {
        "schemaVersion": PROPOSAL_VERSION,
        "baseDirectoryRevision": directory["directoryRevision"],
        "targetIdentity": copy.deepcopy(target_identity),
        "previousBindingDigest": _binding_revision_digest(target),
        "proposedBinding": proposed,
    }
    proposal = {**core, "proposalDigest": digest(core)}
    _validate_proposal(proposal)
    candidate = _apply_proposed_binding(directory, proposal)
    validate_directory(candidate)
    return proposal


def _expected_proposed_binding(
    current: dict[str, Any],
    new_parent_identity: dict[str, str],
    destination_host_id: str,
    issued_at: str,
) -> dict[str, Any]:
    proposed = copy.deepcopy(current)
    proposed["bindingRevision"] += 1
    proposed["executionEpoch"] += 1
    proposed["reportsTo"] = copy.deepcopy(new_parent_identity)
    proposed["placement"]["currentHostId"] = destination_host_id
    proposed["issuedAt"] = issued_at
    proposed["state"] = "active"
    proposed["supersedes"] = {
        "bindingRevision": current["bindingRevision"],
        "executionEpoch": current["executionEpoch"],
        "bindingDigest": _binding_revision_digest(current),
    }
    return proposed


def _validate_proposal(value: Any) -> dict[str, Any]:
    proposal = _object(
        value,
        "$",
        {"schemaVersion", "baseDirectoryRevision", "targetIdentity", "previousBindingDigest", "proposedBinding", "proposalDigest"},
        {"schemaVersion", "baseDirectoryRevision", "targetIdentity", "previousBindingDigest", "proposedBinding", "proposalDigest"},
    )
    if proposal["schemaVersion"] != PROPOSAL_VERSION:
        fail("unsupported_version", "$.schemaVersion", "unsupported proposal version")
    _positive_int(proposal["baseDirectoryRevision"], "$.baseDirectoryRevision")
    validate_identity(proposal["targetIdentity"], "$.targetIdentity")
    for field in ("previousBindingDigest", "proposalDigest"):
        if not isinstance(proposal[field], str) or not HEX_64.fullmatch(proposal[field]):
            fail("invalid_digest", f"$.{field}", "expected lowercase SHA-256")
    proposed = _validate_binding(proposal["proposedBinding"], "$.proposedBinding")
    if identity_key(proposed["identity"]) != identity_key(proposal["targetIdentity"]):
        fail("identity_mismatch", "$.proposedBinding.identity", "proposal target identity changed")
    core = {key: copy.deepcopy(item) for key, item in proposal.items() if key != "proposalDigest"}
    if digest(core) != proposal["proposalDigest"]:
        fail("proposal_digest_mismatch", "$.proposalDigest", "proposal contents do not match digest")
    return proposal


def _validate_readback(value: Any) -> dict[str, Any]:
    readback = _object(
        value,
        "$",
        {"schemaVersion", "proposalDigest", "bindingDigest", "identity", "destinationHostId", "bindingRevision", "executionEpoch", "observedAt", "accepted"},
        {"schemaVersion", "proposalDigest", "bindingDigest", "identity", "destinationHostId", "bindingRevision", "executionEpoch", "observedAt", "accepted"},
    )
    if readback["schemaVersion"] != READBACK_VERSION:
        fail("unsupported_version", "$.schemaVersion", "unsupported destination readback version")
    for field in ("proposalDigest", "bindingDigest"):
        if not isinstance(readback[field], str) or not HEX_64.fullmatch(readback[field]):
            fail("invalid_digest", f"$.{field}", "expected lowercase SHA-256")
    validate_identity(readback["identity"], "$.identity")
    _string(readback["destinationHostId"], "$.destinationHostId")
    _positive_int(readback["bindingRevision"], "$.bindingRevision")
    _positive_int(readback["executionEpoch"], "$.executionEpoch")
    _timestamp(readback["observedAt"], "$.observedAt")
    if not isinstance(readback["accepted"], bool):
        fail("invalid_type", "$.accepted", "expected boolean")
    return readback


def apply_reparent(directory: dict[str, Any], proposal: dict[str, Any], readback: dict[str, Any]) -> dict[str, Any]:
    validate_directory(directory)
    _validate_proposal(proposal)
    _validate_readback(readback)
    if proposal["baseDirectoryRevision"] != directory["directoryRevision"]:
        fail("stale_directory_revision", "$.baseDirectoryRevision", "directory changed after proposal")
    current = _active_binding(directory, proposal["targetIdentity"])
    if _binding_revision_digest(current) != proposal["previousBindingDigest"]:
        fail("stale_binding_revision", "$.previousBindingDigest", "target binding changed after proposal")
    proposed = proposal["proposedBinding"]
    expected_proposed = _expected_proposed_binding(
        current,
        proposed["reportsTo"],
        proposed["placement"]["currentHostId"],
        proposed["issuedAt"],
    )
    if proposed != expected_proposed:
        fail(
            "proposal_changes_unowned_fields",
            "$.proposedBinding",
            "reparent proposal may change only parent, current host, issuance, revision, epoch, state, and supersession fencing",
        )
    candidate = _apply_proposed_binding(directory, proposal)
    validate_directory(candidate)
    expected = {
        "proposalDigest": proposal["proposalDigest"],
        "bindingDigest": _binding_revision_digest(proposed),
        "identity": proposed["identity"],
        "destinationHostId": proposed["placement"]["currentHostId"],
        "bindingRevision": proposed["bindingRevision"],
        "executionEpoch": proposed["executionEpoch"],
    }
    if readback["accepted"] is not True:
        fail("destination_readback_failed", "$.accepted", "destination did not accept proposed binding")
    if _timestamp_value(readback["observedAt"]) < _timestamp_value(proposed["issuedAt"]):
        fail("destination_readback_mismatch", "$.observedAt", "destination readback predates the proposal")
    for field, value in expected.items():
        observed = readback[field]
        if field == "identity":
            matches = identity_key(observed) == identity_key(value)
        else:
            matches = observed == value
        if not matches:
            fail("destination_readback_mismatch", f"$.{field}", "destination readback does not match proposal")

    result = _apply_proposed_binding(directory, proposal)
    validate_directory(result)
    return result


def _apply_proposed_binding(directory: dict[str, Any], proposal: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(directory)
    target_key = identity_key(proposal["targetIdentity"])
    for item in result["bindings"]:
        if identity_key(item["identity"]) == target_key and item["state"] == "active":
            item["state"] = "superseded"
    result["bindings"].append(copy.deepcopy(proposal["proposedBinding"]))
    result["directoryRevision"] += 1
    return result


def _active_binding(directory: dict[str, Any], identity: dict[str, str]) -> dict[str, Any]:
    wanted = identity_key(validate_identity(identity, "identity"))
    matches = [
        item
        for item in directory["bindings"]
        if item["state"] == "active" and identity_key(item["identity"]) == wanted
    ]
    if not matches:
        fail("unbound", "identity", f"no active binding for {':'.join(wanted)}")
    if len(matches) != 1:
        fail("ambiguous_binding", "identity", f"multiple active bindings for {':'.join(wanted)}")
    return matches[0]


def load_json(path: str | Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail("invalid_json", str(path), str(error))


def load_snapshot(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    try:
        with target.open("rb") as stream:
            raw = stream.read(MAX_SNAPSHOT_BYTES + 1)
    except OSError as error:
        fail("invalid_json", str(path), str(error))
    if len(raw) > MAX_SNAPSHOT_BYTES:
        fail("snapshot_too_large", str(path), f"serialized snapshot exceeds {MAX_SNAPSHOT_BYTES} bytes")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        fail("invalid_json", str(path), str(error))
    return validate_snapshot(value)


def write_json(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def snapshot_bytes(value: dict[str, Any]) -> bytes:
    validate_snapshot(value)
    serialized = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    if len(serialized) > MAX_SNAPSHOT_BYTES:
        fail("snapshot_too_large", "$", f"serialized snapshot exceeds {MAX_SNAPSHOT_BYTES} bytes")
    return serialized


def write_snapshot(path: str | Path, value: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(snapshot_bytes(value))


def benchmark_lookup(
    snapshot: dict[str, Any],
    directory: dict[str, Any],
    identity: dict[str, str],
    iterations: int,
) -> dict[str, Any]:
    _positive_int(iterations, "iterations")
    verify_snapshot(snapshot, directory)
    timings: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        lookup_binding(snapshot, identity, directory)
        timings.append((time.perf_counter_ns() - started) / 1_000_000)
    ordered = sorted(timings)
    p95_index = min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))
    return {
        "iterations": iterations,
        "p50Ms": round(statistics.median(ordered), 6),
        "p95Ms": round(ordered[p95_index], 6),
        "maxMs": round(max(ordered), 6),
        "boundary": "local directory-correspondence verification plus exact snapshot identity lookup; no provider or Notion call",
    }


def _emit(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("directory")

    snapshot_parser = subparsers.add_parser("snapshot")
    snapshot_parser.add_argument("directory")
    snapshot_parser.add_argument("--output")

    lookup_parser = subparsers.add_parser("lookup")
    lookup_parser.add_argument("snapshot")
    lookup_parser.add_argument("--directory", required=True)
    lookup_parser.add_argument("--identity", required=True)
    lookup_parser.add_argument("--capability")

    propose_parser = subparsers.add_parser("propose-reparent")
    propose_parser.add_argument("directory")
    propose_parser.add_argument("--target", required=True)
    propose_parser.add_argument("--new-parent", required=True)
    propose_parser.add_argument("--destination-host", required=True)
    propose_parser.add_argument("--issued-at", required=True)
    propose_parser.add_argument("--output")

    apply_parser = subparsers.add_parser("apply-reparent")
    apply_parser.add_argument("directory")
    apply_parser.add_argument("proposal")
    apply_parser.add_argument("readback")
    apply_parser.add_argument("--output")

    benchmark_parser = subparsers.add_parser("benchmark")
    benchmark_parser.add_argument("snapshot")
    benchmark_parser.add_argument("--directory", required=True)
    benchmark_parser.add_argument("--identity", required=True)
    benchmark_parser.add_argument("--iterations", type=int, default=100)

    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            directory = validate_directory(load_json(args.directory))
            _emit({"ok": True, "directoryRevision": directory["directoryRevision"], "activeBindings": sum(item["state"] == "active" for item in directory["bindings"])})
        elif args.command == "snapshot":
            directory = load_json(args.directory)
            value = build_snapshot(directory)
            if args.output:
                write_snapshot(args.output, value)
                verify_snapshot(load_snapshot(args.output), directory)
            else:
                sys.stdout.buffer.write(snapshot_bytes(value))
        elif args.command == "lookup":
            snapshot = load_snapshot(args.snapshot)
            directory = load_json(args.directory)
            identity = parse_identity(args.identity)
            value = (
                resolve_contact(snapshot, identity, args.capability, directory)
                if args.capability
                else lookup_binding(snapshot, identity, directory)
            )
            _emit(value)
        elif args.command == "propose-reparent":
            value = propose_reparent(load_json(args.directory), parse_identity(args.target), parse_identity(args.new_parent), args.destination_host, args.issued_at)
            if args.output:
                write_json(args.output, value)
            else:
                _emit(value)
        elif args.command == "apply-reparent":
            value = apply_reparent(load_json(args.directory), load_json(args.proposal), load_json(args.readback))
            if args.output:
                write_json(args.output, value)
            else:
                _emit(value)
        elif args.command == "benchmark":
            _emit(
                benchmark_lookup(
                    load_snapshot(args.snapshot),
                    load_json(args.directory),
                    parse_identity(args.identity),
                    args.iterations,
                )
            )
        return 0
    except DirectoryError as error:
        print(json.dumps({"ok": False, "error": error.as_dict()}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
