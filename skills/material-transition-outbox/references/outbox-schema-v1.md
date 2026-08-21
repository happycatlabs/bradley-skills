# Material Transition Outbox V1

Normative keywords such as MUST and MUST NOT are intentional.

## Boundary

The outbox is a flat, local, privacy-safe delivery ledger. The Agent
Organization Directory remains the only role, identity, reportsTo, observer,
and contact-capability registry. The live provider owns task lifecycle and
message transport; Linear owns fallback issue/comment truth; Notion remains
durable architecture context and receives no routine heartbeat writes.

Versions:

- Policy: `bradley.material-transition-policy/v1`
- Event: `bradley.material-transition/v1`
- State: `bradley.material-transition-outbox/v1`
- Entry: `bradley.material-transition-entry/v1`
- Chronology fixture: `bradley.material-transition-chronologies/v1`

Unknown versions, fields, event kinds, states, and transport outcomes fail
closed. V1 bounds the outbox to 4,096 entries and strings to 4 KiB. The caller
owns terminal-entry retention/compaction under its local storage policy; this
skill does not create a second task or liveness lifecycle.

## Policy And Quiet Inspection

The only V1 mode is `material_transitions`. Defaults are:

```json
{
  "schemaVersion": "bradley.material-transition-policy/v1",
  "mode": "material_transitions",
  "cadenceSeconds": 300,
  "quietThresholdSeconds": 1200,
  "maxAttempts": 3,
  "maxFallbackAttempts": 3,
  "maxHopCount": 4
}
```

`cadenceSeconds` is the configurable polling/retry cadence. At 20 minutes with
no material event, the caller may perform one read-only inspection subject to
that cadence. The last inspection timestamp is volatile scheduler input, not
outbox state. If inspection discovers no transition, the decision has
`writeRequired: false`; the caller MUST NOT touch the durable outbox or emit a
message.

## Material Event

An event contains the exact source identity, one of `progress`, `blocker`,
`needs_user_input`, or `terminal`, a privacy-safe native authority artifact,
SHA-256 material-state hash, opaque summary/next-action codes, causal key,
bounded hop count, trigger, and observation time.

`trigger: reply` is acknowledged as non-escalating and creates no entry. The
outbox never interprets replies as fresh authority or recursively escalates
them. Hop counts above the configured maximum are rejected without a write.

## Exact Recipient And Dedupe Fence

Enqueue MUST verify the supplied snapshot against the same cached validated
directory. It resolves the exact active source binding and its one active
primary `reportsTo` binding. Root sources have no task recipient and fail
closed. The entry freezes:

- source identity, reportsTo binding revision, execution epoch, and host;
- recipient identity, binding revision, execution epoch, and host;
- directory revision and exact advertised route; and
- an optional observer subscription revision.

Before every native provider action, the planner MUST revalidate the frozen
source reportsTo edge and both current bindings. It MUST NOT silently retarget a
moved edge, changed host, superseding revision, missing task, or unsupported
route. A primary becomes `fallback_pending`; an observer copy becomes `failed`.

The dedupe key is SHA-256 over exactly:

```json
{
  "bindingRevision": "source reportsTo binding revision",
  "recipientIdentity": "exact provider + taskId + hostScope",
  "eventKind": "material event kind",
  "nativeAuthorityArtifact": "kind + privacy-safe native ref",
  "materialStateHash": "lowercase SHA-256"
}
```

The entry and message IDs are deterministic derivatives of that key. Existing
keys are never re-enqueued, including after delivery, fallback, failure, or
restart. Pending progress and blocker entries with the same source, recipient,
kind, and authority artifact are marked `coalesced` when a newer material hash
arrives. User-input events are once per exact fingerprint and are not collapsed
across different material states.

## Flat Entry State

Each entry stores one recipient delivery. There is no run, worker, task, or
provider registry nested around it. Core fields are deterministic IDs; source
and recipient binding fences; optional observer subscription revision; event
metadata; `notify` and literal `authority: false`; route; state; bounded attempt
counts; next attempt; privacy-safe error/receipt codes; and timestamps.

States are:

| State | Meaning |
| --- | --- |
| `pending` | Exact native send is eligible. |
| `retry_wait` | A typed non-acceptance waits for the next bounded attempt. |
| `readback_pending` | Acceptance was ambiguous; inspect the same deterministic message ID. |
| `fallback_pending` | Primary delivery must use the deterministic Linear fallback. |
| `delivered` | Exact native message-ID readback confirmed delivery. |
| `fallback_delivered` | Linear returned a deterministic fallback receipt. |
| `failed` | Bounded delivery ended without a confirmed receipt. |
| `coalesced` | A newer pending progress/blocker state replaced this entry. |

Every state decision returns the complete candidate state and an explicit
`writeRequired`. `persist_decision` performs an atomic replace only when that
flag is true. One serialized caller owns the file; V1 does not add leases or a
liveness platform.

## Transport Interface

`plan_actions` returns plain actions. It does not call a provider:

- `message_existing_task`: send the deterministic message ID through the exact
  frozen route and request notification when marked;
- `readback_existing_task`: query that same recipient and exact message ID;
- `linear_fallback`: create/update the privacy-safe fallback using the
  deterministic fallback ID.

Every action declares `authority: false`. A recipient revalidates native
authority before acting. Primary blocker and user-input actions request a
notification; progress and all observer copies do not.

Native delivery becomes `delivered` only from an exact message-ID receipt with
`readbackConfirmed: true`. Ambiguous acceptance schedules readback. Busy,
unavailable, not-found readback, stale binding, and terminal recipient outcomes
are bounded; the primary falls back rather than spinning forever. Linear
fallback has its own bounded retry count. Observer copies never fall back and
never affect primary delivery.

This contract intentionally does not provide provider substitution,
cross-provider transport, broadcast, task creation, approval, merge, deploy,
release, tracker-close, or production-mutation authority.
