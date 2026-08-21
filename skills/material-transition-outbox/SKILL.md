---
name: material-transition-outbox
description: Plan and persist privacy-safe material progress, blocker, user-input, and terminal event delivery to the exact current primary reportsTo binding. Use for quiet inspection, deterministic restart dedupe, bounded provider retry/readback, observer copies, or Linear fallback. This skill does not own provider transport, task lifecycle, or routine heartbeats.
---

# Material Transition Outbox

Deliver only meaningful owner transitions through the Agent Organization
Directory. The normative state and transport contract is
[`references/outbox-schema-v1.md`](references/outbox-schema-v1.md).

Use the stdlib helper as a state function. The caller remains the one serialized
writer and supplies provider or Linear results back as typed receipts:

```python
decision = enqueue_event(state, event, policy, snapshot, directory)
persist_decision(outbox_path, decision)  # no-op when writeRequired is false

plan = plan_actions(decision["state"], policy, snapshot, directory, now)
# Execute only plan["actions"] through the named route, then record_result(...).
```

The CLI exposes local validation, enqueue, and quiet-inspection decisions:

```sh
python3 scripts/material_outbox.py validate /path/to/outbox.json
python3 scripts/material_outbox.py quiet \
  --now 2026-08-21T12:20:00.000Z \
  --last-material-at 2026-08-21T12:00:00.000Z
```

## Working Rules

- Default policy is `material_transitions`, a configurable 300-second cadence,
  and a 20-minute quiet threshold. Quiet expiry requests read-only inspection;
  a no-change inspection never mutates the outbox.
- Resolve the sender through a verified directory/snapshot pair. A non-root
  sender targets only the exact active `reportsTo` identity and freezes the
  source reportsTo binding revision plus the recipient binding revision, epoch,
  and host. Revalidate all of them before every provider action.
- The deterministic dedupe key contains the source reportsTo binding revision,
  recipient identity, event kind, native authority artifact, and material-state
  hash. Equal fingerprints cause no message and no write after restart.
- Pending progress and blocker entries for the same artifact and recipient
  coalesce to the newest material-state hash. A blocker or user-input need sets
  `notify: true` for the primary recipient exactly once per fingerprint.
- Provider send and readback actions reuse only the exact directory-advertised
  `message_existing_task` route and deterministic message ID. Ambiguous
  acceptance becomes exact message-ID readback, never a new ID.
- Retry provider and Linear fallback delivery only to configured bounds. A
  missing route, moved/stale binding, terminal recipient, or exhausted primary
  route fails closed to the deterministic privacy-safe Linear action. Observer
  failure never creates authority or blocks the primary.
- Carry the causal key and hop count unchanged. Reject hops beyond the policy
  bound. Events triggered by replies intentionally create no outbox entry.
- Treat action payloads as privacy-safe metadata. Native references, summary
  codes, next-action codes, receipt IDs, and error codes must not contain raw
  transcripts, prompts, user content, provider payloads, or secrets.

## Ownership Boundaries

This skill owns deterministic outbox state and action planning. It does not
contact Codex, Claude, another provider, Linear, or Notion; create or recover
tasks; infer lifecycle; grant action authority; broadcast; substitute a
provider; merge; deploy; release; or close a tracker. The caller executes an
action only through its named native authority and records a bounded receipt.
No routine Notion write is part of this flow.
