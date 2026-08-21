#!/usr/bin/env python3
"""Plan restart-safe material-transition delivery without owning provider transport."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NoReturn


POLICY_VERSION = "bradley.material-transition-policy/v1"
STATE_VERSION = "bradley.material-transition-outbox/v1"
ENTRY_VERSION = "bradley.material-transition-entry/v1"
EVENT_VERSION = "bradley.material-transition/v1"

EVENT_KINDS = {"progress", "blocker", "needs_user_input", "terminal"}
ENTRY_STATES = {
    "pending",
    "retry_wait",
    "readback_pending",
    "fallback_pending",
    "delivered",
    "fallback_delivered",
    "failed",
    "coalesced",
}
OPEN_STATES = {"pending", "retry_wait", "readback_pending", "fallback_pending"}
COALESCING_KINDS = {"progress", "blocker"}
IMMEDIATE_KINDS = {"blocker", "needs_user_input"}
RETRYABLE_OUTCOMES = {"busy", "provider_unavailable"}
FAIL_CLOSED_OUTCOMES = {"recipient_terminal", "stale_binding"}
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
SAFE_CODE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,255}$")
MAX_ENTRIES = 4096
MAX_STRING_LENGTH = 4096


def _load_directory_module() -> Any:
    module_path = (
        Path(__file__).resolve().parents[2]
        / "agent-organization-directory"
        / "scripts"
        / "agent_directory.py"
    )
    spec = importlib.util.spec_from_file_location("bradley_agent_directory", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Agent Organization Directory helper: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DIRECTORY = _load_directory_module()


class OutboxError(ValueError):
    def __init__(self, code: str, path: str, message: str):
        super().__init__(message)
        self.code = code
        self.path = path
        self.message = message

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


def fail(code: str, path: str, message: str) -> NoReturn:
    raise OutboxError(code, path, message)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _object(
    value: Any, path: str, allowed: set[str], required: set[str]
) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail("invalid_type", path, "expected object")
    unknown = set(value) - allowed
    if unknown:
        fail("unknown_field", path, f"unknown fields: {', '.join(sorted(unknown))}")
    missing = required - set(value)
    if missing:
        fail("missing_field", path, f"missing fields: {', '.join(sorted(missing))}")
    return value


def _string(
    value: Any,
    path: str,
    *,
    choices: set[str] | None = None,
    safe_code: bool = False,
) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_STRING_LENGTH:
        fail("invalid_string", path, "expected non-empty bounded string")
    if "\n" in value or "\r" in value or "\x00" in value:
        fail("invalid_string", path, "control characters are not allowed")
    if choices is not None and value not in choices:
        fail("invalid_value", path, f"unsupported value: {value}")
    if safe_code and not SAFE_CODE.fullmatch(value):
        fail("invalid_code", path, "expected a lowercase opaque code")
    return value


def _int(value: Any, path: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        fail("invalid_integer", path, f"expected integer >= {minimum}")
    return value


def _timestamp(value: Any, path: str) -> str:
    result = _string(value, path)
    try:
        parsed = datetime.fromisoformat(result.replace("Z", "+00:00"))
    except ValueError:
        fail("invalid_timestamp", path, "expected UTC ISO-8601 timestamp")
    if parsed.tzinfo != timezone.utc or not result.endswith("Z"):
        fail("invalid_timestamp", path, "expected UTC ISO-8601 timestamp")
    return result


def _timestamp_value(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _timestamp_after(value: str, seconds: int) -> str:
    moment = _timestamp_value(value) + timedelta(seconds=seconds)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def default_policy(**overrides: Any) -> dict[str, Any]:
    policy = {
        "schemaVersion": POLICY_VERSION,
        "mode": "material_transitions",
        "cadenceSeconds": 300,
        "quietThresholdSeconds": 20 * 60,
        "maxAttempts": 3,
        "maxFallbackAttempts": 3,
        "maxHopCount": 4,
    }
    policy.update(overrides)
    return validate_policy(policy)


def validate_policy(value: Any) -> dict[str, Any]:
    policy = _object(
        value,
        "$",
        {
            "schemaVersion",
            "mode",
            "cadenceSeconds",
            "quietThresholdSeconds",
            "maxAttempts",
            "maxFallbackAttempts",
            "maxHopCount",
        },
        {
            "schemaVersion",
            "mode",
            "cadenceSeconds",
            "quietThresholdSeconds",
            "maxAttempts",
            "maxFallbackAttempts",
            "maxHopCount",
        },
    )
    if policy["schemaVersion"] != POLICY_VERSION:
        fail("unsupported_version", "$.schemaVersion", "unsupported policy version")
    if policy["mode"] != "material_transitions":
        fail("unsupported_mode", "$.mode", "v1 supports material_transitions only")
    _int(policy["cadenceSeconds"], "$.cadenceSeconds", minimum=1)
    _int(policy["quietThresholdSeconds"], "$.quietThresholdSeconds", minimum=1)
    _int(policy["maxAttempts"], "$.maxAttempts", minimum=1)
    _int(policy["maxFallbackAttempts"], "$.maxFallbackAttempts", minimum=1)
    _int(policy["maxHopCount"], "$.maxHopCount", minimum=1)
    return policy


def empty_state() -> dict[str, Any]:
    return {"schemaVersion": STATE_VERSION, "entries": []}


def _validate_binding_ref(value: Any, path: str) -> None:
    item = _object(
        value,
        path,
        {"identity", "bindingRevision", "executionEpoch", "currentHostId"},
        {"identity", "bindingRevision", "executionEpoch", "currentHostId"},
    )
    DIRECTORY.validate_identity(item["identity"], f"{path}.identity")
    _int(item["bindingRevision"], f"{path}.bindingRevision", minimum=1)
    _int(item["executionEpoch"], f"{path}.executionEpoch", minimum=1)
    _string(item["currentHostId"], f"{path}.currentHostId")


def _validate_artifact(value: Any, path: str) -> None:
    artifact = _object(value, path, {"kind", "ref"}, {"kind", "ref"})
    _string(artifact["kind"], f"{path}.kind", safe_code=True)
    _string(artifact["ref"], f"{path}.ref")


def validate_event(value: Any, policy: dict[str, Any]) -> dict[str, Any]:
    event = _object(
        value,
        "$",
        {
            "schemaVersion",
            "sourceIdentity",
            "eventKind",
            "nativeAuthorityArtifact",
            "materialStateHash",
            "summaryCode",
            "nextActionCode",
            "causalKey",
            "hopCount",
            "trigger",
            "observedAt",
        },
        {
            "schemaVersion",
            "sourceIdentity",
            "eventKind",
            "nativeAuthorityArtifact",
            "materialStateHash",
            "summaryCode",
            "nextActionCode",
            "causalKey",
            "hopCount",
            "trigger",
            "observedAt",
        },
    )
    if event["schemaVersion"] != EVENT_VERSION:
        fail("unsupported_version", "$.schemaVersion", "unsupported event version")
    DIRECTORY.validate_identity(event["sourceIdentity"], "$.sourceIdentity")
    _string(event["eventKind"], "$.eventKind", choices=EVENT_KINDS)
    _validate_artifact(event["nativeAuthorityArtifact"], "$.nativeAuthorityArtifact")
    if not isinstance(event["materialStateHash"], str) or not HEX_64.fullmatch(
        event["materialStateHash"]
    ):
        fail("invalid_hash", "$.materialStateHash", "expected lowercase SHA-256")
    _string(event["summaryCode"], "$.summaryCode", safe_code=True)
    _string(event["nextActionCode"], "$.nextActionCode", safe_code=True)
    _string(event["causalKey"], "$.causalKey", safe_code=True)
    hop_count = _int(event["hopCount"], "$.hopCount")
    if hop_count > policy["maxHopCount"]:
        fail("hop_limit_exceeded", "$.hopCount", "event exceeds the configured hop limit")
    _string(event["trigger"], "$.trigger", choices={"material_transition", "reply"})
    _timestamp(event["observedAt"], "$.observedAt")
    return event


def validate_state(value: Any) -> dict[str, Any]:
    state = _object(value, "$", {"schemaVersion", "entries"}, {"schemaVersion", "entries"})
    if state["schemaVersion"] != STATE_VERSION:
        fail("unsupported_version", "$.schemaVersion", "unsupported outbox version")
    entries = state["entries"]
    if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
        fail("invalid_entries", "$.entries", f"expected at most {MAX_ENTRIES} entries")
    seen_ids: set[str] = set()
    seen_dedupe: set[str] = set()
    for index, raw in enumerate(entries):
        path = f"$.entries[{index}]"
        entry = _object(
            raw,
            path,
            {
                "schemaVersion",
                "entryId",
                "messageId",
                "dedupeKey",
                "sourceBinding",
                "recipientBinding",
                "deliveryRole",
                "observerSubscriptionRevision",
                "eventKind",
                "nativeAuthorityArtifact",
                "materialStateHash",
                "summaryCode",
                "nextActionCode",
                "causalKey",
                "hopCount",
                "notify",
                "authority",
                "directoryRevision",
                "routeRef",
                "status",
                "attempts",
                "fallbackAttempts",
                "nextAttemptAt",
                "lastErrorCode",
                "remoteReceiptId",
                "fallbackReceiptId",
                "createdAt",
                "updatedAt",
            },
            {
                "schemaVersion",
                "entryId",
                "messageId",
                "dedupeKey",
                "sourceBinding",
                "recipientBinding",
                "deliveryRole",
                "observerSubscriptionRevision",
                "eventKind",
                "nativeAuthorityArtifact",
                "materialStateHash",
                "summaryCode",
                "nextActionCode",
                "causalKey",
                "hopCount",
                "notify",
                "authority",
                "directoryRevision",
                "routeRef",
                "status",
                "attempts",
                "fallbackAttempts",
                "nextAttemptAt",
                "lastErrorCode",
                "remoteReceiptId",
                "fallbackReceiptId",
                "createdAt",
                "updatedAt",
            },
        )
        if entry["schemaVersion"] != ENTRY_VERSION:
            fail("unsupported_version", f"{path}.schemaVersion", "unsupported entry version")
        for field in ("entryId", "messageId", "dedupeKey"):
            value = _string(entry[field], f"{path}.{field}")
            if not HEX_64.fullmatch(value):
                fail("invalid_hash", f"{path}.{field}", "expected lowercase SHA-256")
        if entry["entryId"] in seen_ids or entry["dedupeKey"] in seen_dedupe:
            fail("duplicate_entry", path, "entry and dedupe identifiers must be unique")
        seen_ids.add(entry["entryId"])
        seen_dedupe.add(entry["dedupeKey"])
        _validate_binding_ref(entry["sourceBinding"], f"{path}.sourceBinding")
        _validate_binding_ref(entry["recipientBinding"], f"{path}.recipientBinding")
        _string(entry["deliveryRole"], f"{path}.deliveryRole", choices={"primary", "observer"})
        subscription_revision = entry["observerSubscriptionRevision"]
        if entry["deliveryRole"] == "observer":
            _int(subscription_revision, f"{path}.observerSubscriptionRevision", minimum=1)
        elif subscription_revision is not None:
            fail("invalid_subscription", f"{path}.observerSubscriptionRevision", "primary delivery cannot carry an observer revision")
        _string(entry["eventKind"], f"{path}.eventKind", choices=EVENT_KINDS)
        _validate_artifact(entry["nativeAuthorityArtifact"], f"{path}.nativeAuthorityArtifact")
        if not isinstance(entry["materialStateHash"], str) or not HEX_64.fullmatch(
            entry["materialStateHash"]
        ):
            fail("invalid_hash", f"{path}.materialStateHash", "expected lowercase SHA-256")
        for field in ("summaryCode", "nextActionCode", "causalKey"):
            _string(entry[field], f"{path}.{field}", safe_code=True)
        _int(entry["hopCount"], f"{path}.hopCount")
        if not isinstance(entry["notify"], bool) or entry["authority"] is not False:
            fail("invalid_authority", path, "notify must be boolean and delivery authority must be false")
        _int(entry["directoryRevision"], f"{path}.directoryRevision", minimum=1)
        if entry["routeRef"] is not None:
            _string(entry["routeRef"], f"{path}.routeRef", safe_code=True)
        _string(entry["status"], f"{path}.status", choices=ENTRY_STATES)
        _int(entry["attempts"], f"{path}.attempts")
        _int(entry["fallbackAttempts"], f"{path}.fallbackAttempts")
        _timestamp(entry["nextAttemptAt"], f"{path}.nextAttemptAt")
        for field in ("lastErrorCode", "remoteReceiptId", "fallbackReceiptId"):
            if entry[field] is not None:
                _string(entry[field], f"{path}.{field}", safe_code=True)
        _timestamp(entry["createdAt"], f"{path}.createdAt")
        _timestamp(entry["updatedAt"], f"{path}.updatedAt")
    return state


def _binding_ref(binding: dict[str, Any]) -> dict[str, Any]:
    return {
        "identity": copy.deepcopy(binding["identity"]),
        "bindingRevision": binding["bindingRevision"],
        "executionEpoch": binding["executionEpoch"],
        "currentHostId": binding["placement"]["currentHostId"],
    }


def _dedupe_key(
    event: dict[str, Any], source: dict[str, Any], recipient: dict[str, Any]
) -> str:
    return digest(
        {
            "bindingRevision": source["bindingRevision"],
            "recipientIdentity": recipient["identity"],
            "eventKind": event["eventKind"],
            "nativeAuthorityArtifact": event["nativeAuthorityArtifact"],
            "materialStateHash": event["materialStateHash"],
        }
    )


def _route_for(
    snapshot: dict[str, Any], directory: dict[str, Any], identity: dict[str, str]
) -> str | None:
    try:
        return DIRECTORY.resolve_contact(
            snapshot, identity, "message_existing_task", directory
        )["routeRef"]
    except DIRECTORY.DirectoryError as error:
        if error.code == "capability_unsupported":
            return None
        raise


def _observer_recipients(
    snapshot: dict[str, Any],
    directory: dict[str, Any],
    source_identity: dict[str, str],
    primary_identity: dict[str, str],
) -> list[tuple[dict[str, Any], int, str | None]]:
    recipients: list[tuple[dict[str, Any], int, str | None]] = []
    source_key = DIRECTORY.identity_key(source_identity)
    primary_key = DIRECTORY.identity_key(primary_identity)
    for subscription in snapshot["observerSubscriptions"]:
        if subscription["purpose"] != "material_transition":
            continue
        if DIRECTORY.identity_key(subscription["observes"]) != source_key:
            continue
        if DIRECTORY.identity_key(subscription["subscriber"]) == primary_key:
            continue
        binding = DIRECTORY.lookup_binding(snapshot, subscription["subscriber"], directory)
        recipients.append(
            (
                binding,
                subscription["revision"],
                _route_for(snapshot, directory, binding["identity"]),
            )
        )
    return sorted(recipients, key=lambda item: DIRECTORY.identity_string(item[0]["identity"]))


def enqueue_event(
    state: dict[str, Any],
    event: dict[str, Any],
    policy: dict[str, Any],
    snapshot: dict[str, Any],
    directory: dict[str, Any],
) -> dict[str, Any]:
    validate_state(state)
    validate_policy(policy)
    validate_event(event, policy)
    DIRECTORY.verify_snapshot(snapshot, directory)
    if event["trigger"] == "reply":
        return _decision(state, False, "reply_not_escalated")

    source = DIRECTORY.lookup_binding(snapshot, event["sourceIdentity"], directory)
    if source["root"] or source["reportsTo"] is None:
        fail("missing_primary_recipient", "$.sourceIdentity", "source has no task reportsTo binding")
    primary = DIRECTORY.lookup_binding(snapshot, source["reportsTo"], directory)
    recipients = [
        ("primary", primary, None, _route_for(snapshot, directory, primary["identity"]))
    ]
    recipients.extend(
        ("observer", binding, revision, route)
        for binding, revision, route in _observer_recipients(
            snapshot, directory, source["identity"], primary["identity"]
        )
    )

    result = copy.deepcopy(state)
    appended = 0
    for delivery_role, recipient, subscription_revision, route_ref in recipients:
        dedupe_key = _dedupe_key(event, source, recipient)
        if any(item["dedupeKey"] == dedupe_key for item in result["entries"]):
            continue
        if event["eventKind"] in COALESCING_KINDS:
            _coalesce_pending(result, source, recipient, event, event["observedAt"])
        entry_id = digest({"dedupeKey": dedupe_key, "deliveryRole": delivery_role})
        entry = {
            "schemaVersion": ENTRY_VERSION,
            "entryId": entry_id,
            "messageId": digest({"entryId": entry_id, "protocol": ENTRY_VERSION}),
            "dedupeKey": dedupe_key,
            "sourceBinding": _binding_ref(source),
            "recipientBinding": _binding_ref(recipient),
            "deliveryRole": delivery_role,
            "observerSubscriptionRevision": subscription_revision,
            "eventKind": event["eventKind"],
            "nativeAuthorityArtifact": copy.deepcopy(event["nativeAuthorityArtifact"]),
            "materialStateHash": event["materialStateHash"],
            "summaryCode": event["summaryCode"],
            "nextActionCode": event["nextActionCode"],
            "causalKey": event["causalKey"],
            "hopCount": event["hopCount"],
            "notify": delivery_role == "primary" and event["eventKind"] in IMMEDIATE_KINDS,
            "authority": False,
            "directoryRevision": directory["directoryRevision"],
            "routeRef": route_ref,
            "status": "pending" if route_ref else ("fallback_pending" if delivery_role == "primary" else "failed"),
            "attempts": 0,
            "fallbackAttempts": 0,
            "nextAttemptAt": event["observedAt"],
            "lastErrorCode": None if route_ref else "capability_unsupported",
            "remoteReceiptId": None,
            "fallbackReceiptId": None,
            "createdAt": event["observedAt"],
            "updatedAt": event["observedAt"],
        }
        result["entries"].append(entry)
        appended += 1
    if not appended:
        return _decision(state, False, "duplicate_material_state")
    validate_state(result)
    return _decision(result, True, "material_transition_enqueued")


def _coalesce_pending(
    state: dict[str, Any],
    source: dict[str, Any],
    recipient: dict[str, Any],
    event: dict[str, Any],
    observed_at: str,
) -> None:
    source_key = DIRECTORY.identity_key(source["identity"])
    recipient_key = DIRECTORY.identity_key(recipient["identity"])
    for entry in state["entries"]:
        if entry["status"] not in OPEN_STATES:
            continue
        if entry["eventKind"] != event["eventKind"]:
            continue
        if DIRECTORY.identity_key(entry["sourceBinding"]["identity"]) != source_key:
            continue
        if DIRECTORY.identity_key(entry["recipientBinding"]["identity"]) != recipient_key:
            continue
        if entry["nativeAuthorityArtifact"] != event["nativeAuthorityArtifact"]:
            continue
        entry["status"] = "coalesced"
        entry["lastErrorCode"] = "superseded_material_state"
        entry["updatedAt"] = observed_at


def _decision(state: dict[str, Any], write_required: bool, reason: str) -> dict[str, Any]:
    return {
        "writeRequired": write_required,
        "reason": reason,
        "state": copy.deepcopy(state),
    }


def quiet_inspection(
    *,
    now: str,
    last_material_at: str,
    volatile_last_inspection_at: str | None,
    policy: dict[str, Any],
) -> dict[str, Any]:
    validate_policy(policy)
    current = _timestamp_value(_timestamp(now, "now"))
    last_material = _timestamp_value(_timestamp(last_material_at, "lastMaterialAt"))
    quiet = (current - last_material).total_seconds() >= policy["quietThresholdSeconds"]
    cadence_ready = True
    if volatile_last_inspection_at is not None:
        last_inspection = _timestamp_value(
            _timestamp(volatile_last_inspection_at, "volatileLastInspectionAt")
        )
        cadence_ready = (current - last_inspection).total_seconds() >= policy["cadenceSeconds"]
    return {
        "inspectionRequired": quiet and cadence_ready,
        "inspectionMode": "read_only" if quiet and cadence_ready else None,
        "writeRequired": False,
        "reason": "quiet_threshold_reached" if quiet and cadence_ready else "no_quiet_inspection",
    }


def plan_actions(
    state: dict[str, Any],
    policy: dict[str, Any],
    snapshot: dict[str, Any],
    directory: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    validate_state(state)
    validate_policy(policy)
    now_value = _timestamp_value(_timestamp(now, "now"))
    result = copy.deepcopy(state)
    changed = False
    actions: list[dict[str, Any]] = []
    try:
        DIRECTORY.verify_snapshot(snapshot, directory)
    except DIRECTORY.DirectoryError as error:
        if error.code not in {
            "stale_snapshot",
            "snapshot_digest_mismatch",
            "snapshot_projection_mismatch",
        }:
            raise
        for entry in result["entries"]:
            if entry["status"] in OPEN_STATES:
                changed |= _fail_closed(entry, "stale_directory_snapshot", now)
        actions = [
            _fallback_action(entry)
            for entry in result["entries"]
            if entry["status"] == "fallback_pending"
        ]
        validate_state(result)
        return {
            "writeRequired": changed,
            "reason": "stale_directory_snapshot",
            "state": result,
            "actions": actions,
        }
    for entry in result["entries"]:
        if entry["status"] not in OPEN_STATES:
            continue
        if _timestamp_value(entry["nextAttemptAt"]) > now_value:
            continue
        target_error = _target_error(entry, snapshot, directory)
        if target_error is not None:
            changed |= _fail_closed(entry, target_error, now)
        if entry["status"] == "failed":
            continue
        if entry["status"] == "fallback_pending":
            actions.append(_fallback_action(entry))
        elif entry["status"] == "readback_pending":
            actions.append(_provider_action(entry, "readback_existing_task"))
        else:
            actions.append(_provider_action(entry, "message_existing_task"))
    validate_state(result)
    return {
        "writeRequired": changed,
        "reason": "delivery_actions_ready" if actions else "no_delivery_action",
        "state": result,
        "actions": actions,
    }


def _target_error(
    entry: dict[str, Any], snapshot: dict[str, Any], directory: dict[str, Any]
) -> str | None:
    if entry["deliveryRole"] == "primary":
        try:
            source = DIRECTORY.lookup_binding(
                snapshot, entry["sourceBinding"]["identity"], directory
            )
            recipient = DIRECTORY.lookup_binding(
                snapshot, entry["recipientBinding"]["identity"], directory
            )
        except DIRECTORY.DirectoryError:
            return "stale_binding"
        if source["root"] or source["reportsTo"] is None:
            return "stale_binding"
        if (
            source["bindingRevision"] != entry["sourceBinding"]["bindingRevision"]
            or source["executionEpoch"] != entry["sourceBinding"]["executionEpoch"]
            or source["placement"]["currentHostId"]
            != entry["sourceBinding"]["currentHostId"]
        ):
            return "moved_binding"
        if DIRECTORY.identity_key(source["reportsTo"]) != DIRECTORY.identity_key(
            recipient["identity"]
        ):
            return "moved_binding"
        if (
            recipient["bindingRevision"] != entry["recipientBinding"]["bindingRevision"]
            or recipient["executionEpoch"] != entry["recipientBinding"]["executionEpoch"]
            or recipient["placement"]["currentHostId"]
            != entry["recipientBinding"]["currentHostId"]
        ):
            return "moved_binding"
        return None

    try:
        source = DIRECTORY.lookup_binding(
            snapshot, entry["sourceBinding"]["identity"], directory
        )
        recipient = DIRECTORY.lookup_binding(
            snapshot, entry["recipientBinding"]["identity"], directory
        )
    except DIRECTORY.DirectoryError:
        return "observer_binding_stale"
    if (
        source["bindingRevision"] != entry["sourceBinding"]["bindingRevision"]
        or source["executionEpoch"] != entry["sourceBinding"]["executionEpoch"]
        or source["placement"]["currentHostId"]
        != entry["sourceBinding"]["currentHostId"]
        or recipient["bindingRevision"] != entry["recipientBinding"]["bindingRevision"]
        or recipient["executionEpoch"] != entry["recipientBinding"]["executionEpoch"]
        or recipient["placement"]["currentHostId"]
        != entry["recipientBinding"]["currentHostId"]
    ):
        return "observer_binding_stale"
    for subscription in snapshot["observerSubscriptions"]:
        if subscription["purpose"] != "material_transition":
            continue
        if subscription["revision"] != entry["observerSubscriptionRevision"]:
            continue
        if DIRECTORY.identity_key(subscription["observes"]) != DIRECTORY.identity_key(
            entry["sourceBinding"]["identity"]
        ):
            continue
        if DIRECTORY.identity_key(subscription["subscriber"]) == DIRECTORY.identity_key(
            entry["recipientBinding"]["identity"]
        ):
            return None
    return "observer_subscription_stale"


def _fail_closed(entry: dict[str, Any], error_code: str, now: str) -> bool:
    if entry["deliveryRole"] == "primary":
        if entry["status"] == "fallback_pending" and entry["lastErrorCode"] == error_code:
            return False
        entry["status"] = "fallback_pending"
    else:
        entry["status"] = "failed"
    entry["lastErrorCode"] = error_code
    entry["nextAttemptAt"] = now
    entry["updatedAt"] = now
    return True


def _provider_action(entry: dict[str, Any], action_type: str) -> dict[str, Any]:
    return {
        "action": action_type,
        "entryId": entry["entryId"],
        "messageId": entry["messageId"],
        "recipient": copy.deepcopy(entry["recipientBinding"]),
        "routeRef": entry["routeRef"],
        "notify": entry["notify"],
        "authority": False,
        "readbackRequired": True,
        "event": {
            "eventKind": entry["eventKind"],
            "nativeAuthorityArtifact": copy.deepcopy(entry["nativeAuthorityArtifact"]),
            "materialStateHash": entry["materialStateHash"],
            "summaryCode": entry["summaryCode"],
            "nextActionCode": entry["nextActionCode"],
            "causalKey": entry["causalKey"],
            "hopCount": entry["hopCount"],
        },
    }


def _fallback_action(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": "linear_fallback",
        "entryId": entry["entryId"],
        "fallbackId": digest({"messageId": entry["messageId"], "transport": "linear"}),
        "notify": entry["notify"],
        "authority": False,
        "event": {
            "eventKind": entry["eventKind"],
            "nativeAuthorityArtifact": copy.deepcopy(entry["nativeAuthorityArtifact"]),
            "materialStateHash": entry["materialStateHash"],
            "summaryCode": entry["summaryCode"],
            "nextActionCode": entry["nextActionCode"],
            "causalKey": entry["causalKey"],
            "hopCount": entry["hopCount"],
            "recipientIdentity": copy.deepcopy(entry["recipientBinding"]["identity"]),
            "recipientBindingRevision": entry["recipientBinding"]["bindingRevision"],
            "lastErrorCode": entry["lastErrorCode"],
        },
    }


def record_result(
    state: dict[str, Any],
    entry_id: str,
    result: dict[str, Any],
    policy: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    validate_state(state)
    validate_policy(policy)
    _timestamp(now, "now")
    _object(
        result,
        "result",
        {
            "action",
            "outcome",
            "messageId",
            "readbackConfirmed",
            "remoteReceiptId",
            "fallbackId",
            "fallbackReceiptId",
        },
        {"action", "outcome"},
    )
    updated = copy.deepcopy(state)
    matches = [entry for entry in updated["entries"] if entry["entryId"] == entry_id]
    if len(matches) != 1:
        fail("entry_not_found", "entryId", "expected one exact outbox entry")
    entry = matches[0]
    if entry["status"] not in OPEN_STATES:
        return _decision(state, False, "entry_already_terminal")
    action = _string(
        result.get("action"), "result.action", choices={"send", "readback", "fallback"}
    )
    outcome = _string(result.get("outcome"), "result.outcome", safe_code=True)
    expected_statuses = {
        "send": {"pending", "retry_wait"},
        "readback": {"readback_pending"},
        "fallback": {"fallback_pending"},
    }
    if entry["status"] not in expected_statuses[action]:
        fail(
            "result_state_mismatch",
            "result.action",
            f"{action} cannot complete an entry in state {entry['status']}",
        )
    if action == "fallback":
        _record_fallback_result(entry, result, outcome, policy, now)
    else:
        _record_provider_result(entry, result, action, outcome, policy, now)
    entry["updatedAt"] = now
    validate_state(updated)
    return _decision(updated, True, "delivery_result_recorded")


def _record_provider_result(
    entry: dict[str, Any],
    result: dict[str, Any],
    action: str,
    outcome: str,
    policy: dict[str, Any],
    now: str,
) -> None:
    if result.get("messageId") != entry["messageId"]:
        fail("message_id_mismatch", "result.messageId", "result must bind the deterministic message ID")
    if action == "send":
        entry["attempts"] += 1
    if (action == "send" and outcome == "delivered") or (
        action == "readback" and outcome == "found"
    ):
        if result.get("readbackConfirmed") is not True:
            fail("missing_readback", "result.readbackConfirmed", "provider delivery requires exact client-ID readback")
        receipt = _string(result.get("remoteReceiptId"), "result.remoteReceiptId", safe_code=True)
        entry["status"] = "delivered"
        entry["remoteReceiptId"] = receipt
        entry["lastErrorCode"] = None
        return
    if action == "send" and outcome == "ambiguous":
        entry["status"] = "readback_pending"
        entry["lastErrorCode"] = "ambiguous_acceptance"
        entry["nextAttemptAt"] = _timestamp_after(now, policy["cadenceSeconds"])
        return
    if action == "readback" and outcome in {"busy", "provider_unavailable"}:
        entry["attempts"] += 1
        if entry["attempts"] >= policy["maxAttempts"]:
            _exhaust_provider(entry, f"readback_{outcome}", now)
        else:
            entry["status"] = "readback_pending"
            entry["lastErrorCode"] = f"readback_{outcome}"
            entry["nextAttemptAt"] = _timestamp_after(now, policy["cadenceSeconds"])
        return
    if action == "readback" and outcome == "not_found":
        if entry["attempts"] >= policy["maxAttempts"]:
            _exhaust_provider(entry, "readback_not_found", now)
        else:
            entry["status"] = "retry_wait"
            entry["lastErrorCode"] = "readback_not_found"
            entry["nextAttemptAt"] = _timestamp_after(now, policy["cadenceSeconds"])
        return
    if action == "send" and outcome in RETRYABLE_OUTCOMES:
        if entry["attempts"] >= policy["maxAttempts"]:
            _exhaust_provider(entry, outcome, now)
        else:
            entry["status"] = "retry_wait"
            entry["lastErrorCode"] = outcome
            entry["nextAttemptAt"] = _timestamp_after(now, policy["cadenceSeconds"])
        return
    if outcome in FAIL_CLOSED_OUTCOMES:
        _exhaust_provider(entry, outcome, now)
        return
    fail("invalid_outcome", "result.outcome", f"unsupported {action} outcome: {outcome}")


def _exhaust_provider(entry: dict[str, Any], error_code: str, now: str) -> None:
    entry["status"] = "fallback_pending" if entry["deliveryRole"] == "primary" else "failed"
    entry["lastErrorCode"] = error_code
    entry["nextAttemptAt"] = now


def _record_fallback_result(
    entry: dict[str, Any],
    result: dict[str, Any],
    outcome: str,
    policy: dict[str, Any],
    now: str,
) -> None:
    if entry["deliveryRole"] != "primary" or entry["status"] != "fallback_pending":
        fail("invalid_fallback", "result.action", "only a primary fallback-pending entry may use Linear")
    expected_id = digest({"messageId": entry["messageId"], "transport": "linear"})
    if result.get("fallbackId") != expected_id:
        fail("fallback_id_mismatch", "result.fallbackId", "result must bind the deterministic fallback ID")
    entry["fallbackAttempts"] += 1
    if outcome == "fallback_delivered":
        entry["fallbackReceiptId"] = _string(
            result.get("fallbackReceiptId"), "result.fallbackReceiptId", safe_code=True
        )
        entry["status"] = "fallback_delivered"
        return
    if outcome == "fallback_unavailable":
        entry["lastErrorCode"] = "fallback_unavailable"
        if entry["fallbackAttempts"] >= policy["maxFallbackAttempts"]:
            entry["status"] = "failed"
        else:
            entry["nextAttemptAt"] = _timestamp_after(now, policy["cadenceSeconds"])
        return
    fail("invalid_outcome", "result.outcome", f"unsupported fallback outcome: {outcome}")


def load_json(path: str | Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail("invalid_json", str(path), str(error))


def load_state(path: str | Path) -> dict[str, Any]:
    return validate_state(load_json(path))


def persist_decision(path: str | Path, decision: dict[str, Any]) -> bool:
    if decision.get("writeRequired") is not True:
        return False
    state = validate_state(decision.get("state"))
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    descriptor, temporary_path = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, target)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)
    return True


def _emit(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("state")

    enqueue_parser = subparsers.add_parser("enqueue")
    enqueue_parser.add_argument("state")
    enqueue_parser.add_argument("event")
    enqueue_parser.add_argument("snapshot")
    enqueue_parser.add_argument("directory")
    enqueue_parser.add_argument("--output")

    quiet_parser = subparsers.add_parser("quiet")
    quiet_parser.add_argument("--now", required=True)
    quiet_parser.add_argument("--last-material-at", required=True)
    quiet_parser.add_argument("--last-inspection-at")
    quiet_parser.add_argument("--cadence-seconds", type=int, default=300)
    quiet_parser.add_argument("--quiet-threshold-seconds", type=int, default=1200)

    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            state = load_state(args.state)
            _emit({"ok": True, "entries": len(state["entries"])})
        elif args.command == "enqueue":
            decision = enqueue_event(
                load_state(args.state),
                load_json(args.event),
                default_policy(),
                DIRECTORY.load_snapshot(args.snapshot),
                DIRECTORY.load_json(args.directory),
            )
            if args.output:
                decision["persisted"] = persist_decision(args.output, decision)
            _emit(decision)
        elif args.command == "quiet":
            _emit(
                quiet_inspection(
                    now=args.now,
                    last_material_at=args.last_material_at,
                    volatile_last_inspection_at=args.last_inspection_at,
                    policy=default_policy(
                        cadenceSeconds=args.cadence_seconds,
                        quietThresholdSeconds=args.quiet_threshold_seconds,
                    ),
                )
            )
        return 0
    except (OutboxError, DIRECTORY.DirectoryError) as error:
        print(json.dumps({"ok": False, "error": error.as_dict()}, sort_keys=True), file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
