# Task-Owned Follow-Up Monitor V1

This reference defines the owner-facing contract for one bounded follow-up
monitor implemented through the host-owned Codex `automation_update` API.
Normative keywords such as MUST, MUST NOT, and MAY are intentional.

## Scope

A V1 monitor is one `heartbeat` automation attached to the exact originating
Codex task. It is not a cron job, child task, watcher subagent, workflow engine,
standing operator monitor, or runtime-specific adapter.

Raw automation TOML is read-only evidence. Every create, update, and delete MUST
use `automation_update`. Every mutation MUST be followed immediately by a
read-back. A receipt MUST NOT claim installation, persistence, lifecycle
enforcement, callback delivery, silence, or cleanup that was not observed.

## Spec

`schemaVersion` MUST be
`codex.task-owned-follow-up-monitor.spec/v1`.

| Field | Required | Meaning |
| --- | --- | --- |
| `schemaVersion` | yes | Exact version string above. |
| `monitorKey` | yes | Stable opaque key for the owner task's one monitor slot; it remains stable across verified updates. |
| `name` | yes | Human-readable automation name, unique enough for host inspection. |
| `owner` | yes | `provider` (`codex`), exact `taskId`, `hostId`, and project identity (`id` and/or absolute `path`). |
| `ticket` | yes | Tracker `system`, exact `id`, and optional URL. |
| `target` | yes | Target `kind`, exact `ref`, and exact read-only `query`. |
| `trigger` | yes | `kind` (`schedule` or `event`), exact plain-language `description`, and `timezone` when scheduled. An event request requires a capability gate. |
| `bounds` | yes | Requested `expiresAt` and/or positive `maxRuns`, plus `requireHostEnforcement`. |
| `conditions` | yes | Explicit `success`, `finding`, `timeout`, and `cancel` conditions. |
| `allowedActions` | yes | Closed list of authority granted to ticks. |
| `resultDestination` | yes | Same owner task plus a durable record destination and one fallback handoff destination. |

The default implied authority is:

```json
[
  "read_exact_target",
  "record_monitor_state",
  "wake_same_owner"
]
```

Any merge, deploy, production repair, provider resolution, Linear closure,
unrelated code or tracker mutation, new task creation, or implementation
dispatch requires separate explicit authority and MUST NOT be inferred from
monitor registration.

`monitorKey` is an opaque stable identifier, not a content digest. The exact
owner task plus host/project is the cardinality key: at most one active
task-owned V1 monitor may occupy that slot. Ticket, target, query, trigger,
bounds, conditions, actions, and destinations are mutable only through a
verified update and are fenced by `specDigest`. A registration in an occupied
slot MUST return `owner_slot_occupied` unless it is an explicit update of the
existing task-owned monitor. An operator-created standing monitor is a separate
class and MUST NOT be adopted, updated, or cancelled through this contract.

Extra lifecycle actions such as inspecting or cancelling the exact monitor MAY
appear in `allowedActions` only when the owner explicitly authorizes them. They
grant no authority over the target or any other automation.

## Lifecycle Capability Gate

The owner asks for bounds; the host decides what it can enforce.

- An event trigger MUST return `capability_blocked` before mutation unless the
  live heartbeat API and scheduler can represent, persist, and execute that
  exact event on the owning host.
- A field persisted only inside the automation prompt is declarative.
- A field accepted by a mutation but absent or changed on read-back is not
  persisted.
- A recurrence `COUNT` or `UNTIL` value is not proven enforced merely because a
  recurrence string was accepted. Disposable execution proof on that host is
  required before the receipt may mark it enforced.
- If `requireHostEnforcement` is true and the live host cannot enforce every
  required bound, registration MUST stop with `capability_blocked` and
  `installed = false`.
- A weaker manually cancelled or prompt-checked substitute MAY be described in
  `limitations`, but MUST NOT be installed without explicit owner acceptance
  and MUST NOT be labelled bounded by the host.
- When that weaker proof is explicitly accepted, the spec SHOULD include
  `manualCancellation` with the exact automation id, terminal condition, and
  authorized owner lifecycle action. Its receipt MUST say `manually bounded`;
  this proves lifecycle plumbing, not host-enforced expiry or maximum runs.

## Receipt

`schemaVersion` MUST be
`codex.task-owned-follow-up-monitor.receipt/v1`.

Required fields:

| Field | Meaning |
| --- | --- |
| `schemaVersion` | Exact receipt version. |
| `specSchemaVersion` | Spec version consumed. |
| `monitorKey` | Opaque owner-slot key from the spec. |
| `specDigest` | SHA-256 of the RFC 8785 JSON Canonicalization Scheme serialization of the owner-facing spec described by this receipt. |
| `persistedIntentDigest` | SHA-256 of the exact UTF-8 prompt read back from host persistence, or `null` only when no persisted prompt was observed. |
| `owner` | Exact provider, task id, host id, and project identity from the spec. |
| `requestedAutomation` | Requested kind, name, destination, target task, and schedule; useful even when creation is blocked. |
| `revision` | Verified owner receipt revision, starting at 1. |
| `operation` | `register`, `inspect`, `update`, or `cancel`. |
| `state` | One lifecycle state from the enum below. |
| `installed` | True only after matching host read-back. |
| `automation` | Observed automation state, or `null` when no automation was created or found. |
| `bounds` | Per bound: requested value, persisted representation, enforcement status, and evidence. |
| `authority` | Exact allowed actions and explicit denied action families. |
| `resultRouting` | Same owner task, durable record, fallback, and observed callback proof if any. |
| `verification` | Dedupe result, mutation result, read-back time/match, normalized-spec exact-match and semantic-projection status, raw-TOML-write flag, and cleanup proof. |
| `limitations` | Exact unsupported, unobserved, or substituted behavior. |

Lifecycle states:

```text
capability_blocked
owner_slot_occupied
persistence_failed
active
paused
finding
decision_required
succeeded
timed_out
cancelled
cleanup_failed
```

Only `active`, `paused`, `finding`, `decision_required`, `succeeded`, and
`timed_out` may have `installed = true`. `cancelled` requires verified absence.
`cleanup_failed` MUST name the residual automation id and observed status.

`specDigest` uses RFC 8785 JCS: recursively sort object keys, retain array order,
emit no insignificant whitespace or trailing newline, encode as UTF-8, then
apply SHA-256. The V1 schema permits only ordinary JSON values and finite
integers for numeric fields.

`automation_update` persists a prompt rather than the owner-facing JSON.
Therefore `specDigest` and `persistedIntentDigest` prove different boundaries.
The receipt MUST also state whether the normalized spec was persisted exactly
and whether its semantic projection matched read-back. A post-proof normalized
spec may preserve runtime evidence only when the exact persisted prompt digest
is recorded and the receipt explicitly says the normalized spec was not
reinstalled. Never substitute one digest for the other.

`semanticProjectionMatched = true` means behavior-level equivalence across
owner binding, ticket, target behavior, trigger, conditions, authority,
destinations, and lifecycle bounds. Nominal field or action-name differences
MUST be listed in `limitations`. Both match fields MUST be `null` when
`persistedIntentDigest` is `null`.

## Operation Contract

### Register

1. Validate the full spec and authority.
2. Enforce the one-monitor owner slot and deduplicate on the owning host.
3. Prove trigger and required lifecycle capability.
4. Create or update exactly one heartbeat through `automation_update`.
5. Read it back immediately.
6. Return a receipt.

### Inspect

View the exact receipt automation id, verify the monitor key and owner binding,
hash the exact persisted prompt into `persistedIntentDigest`, and return a new
observed receipt. A missing or mismatched automation is a persistence failure,
not proof of cancellation.

### Update

Read current state, preserve unspecified fields, apply one full update through
`automation_update`, read back immediately, and increment the receipt revision
only after a match.

### Cancel

Delete the exact id through `automation_update`, confirm a later view does not
resolve it, and confirm no equivalent task-owned automation remains. Return
`cancelled`. If any residual remains, return `cleanup_failed`.

## Tick Contract

Each tick MUST:

1. Read only the declared target/query and prior durable monitor state.
2. Compute a stable evidence fingerprint.
3. Stay silent when that fingerprint and condition classification are
   unchanged.
4. Return to the same owner only for a new actionable finding, required
   decision, terminal success, or exhausted observation/retry budget.
5. Include the originating ticket and context in every owner result.
6. Emit at most one concise fallback handoff and stop if same-task resumption is
   unavailable.
7. Never expand authority based on a finding.

For proof, distinguish:

- no new sidebar task observed;
- no duplicate owner result observed;
- no-change tick actually executed or not executed;
- notification behavior observed;
- automatic bound enforcement observed.

Evidence for one item does not prove the others.
