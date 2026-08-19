---
name: codex-automation
description: Create, update, inspect, pause, resume, or delete Codex automations on the local machine or a connected remote Codex machine. Use when the user asks to start, schedule, install, change, test, or remove a recurring Codex job, especially when they name another machine or host such as Eve. Also use when an originating Codex task needs one bounded, task-owned follow-up monitor that returns actionable or terminal results to that same task. Resolve the target host and project explicitly; remote automations are installed by a short-lived Codex thread running on the owning host because automation state is host-local.
---

# Codex Automation

Manage Codex automations on the machine that will actually run them. Automation
state is host-local. A remote project appearing in `list_projects` does not make
the caller's `automation_update` remote-aware.

Use `dispatch` for one-time child work sessions. Use this skill for recurring
jobs, scheduled checks, reminders, and automation lifecycle changes. If an
automation later dispatches implementation agents, its prompt may load
`dispatch`; that does not make the automation itself a dispatch ledger entry.

## Automation Classes

Keep these three classes distinct:

- **Task-owned follow-up monitor**: one bounded heartbeat attached to the exact
  originating Codex task. Its lifecycle follows the versioned contract in
  `references/task-owned-follow-up-monitor-v1.md`.
- **Operator-created standing monitor**: a recurring automation that an
  operator intentionally maintains beyond one task. It is not task-owned merely
  because it targets a thread.
- **Active-turn watcher lane**: a temporary `$monitor` watcher subagent. It ends
  with the active parent turn and is not an automation.

Never adopt, update, or delete a standing monitor as the implementation of a
task-owned request. Never describe a watcher lane as persistent monitoring.

## Ownership Model

Treat these as separate identities:

- **Host**: the Codex machine that owns the automation and executes future runs.
- **Project**: the saved project on that host used as the automation target.
- **Automation**: the host-local recurring job, identified by its automation id.
- **Installer thread**: a temporary thread used only to manage automation state
  on a remote host.

Never silently substitute the local host when the requested remote host is
unavailable. The same repo path or project label may be registered on multiple
hosts; choose by `hostId`, not path alone.

## Task-Owned Follow-Up Monitor V1

Use the normative spec and receipt in
`references/task-owned-follow-up-monitor-v1.md`. Example documents live in
`examples/task-owned-follow-up-monitor-v1/`.

This is a narrow adapter over the existing host-owned `automation_update` API,
not a scheduler or workflow engine. The owner may register, inspect, update, or
cancel one heartbeat. Do not build a daemon, dashboard, task fleet, scheduler,
runtime adapter, or detached replacement task.

### Registration

1. Resolve the exact originating Codex `taskId`, owning `hostId`, and project
   identity. The heartbeat must use `destination = "thread"` and
   `targetThreadId = owner.taskId`.
2. Validate the complete `codex.task-owned-follow-up-monitor.spec/v1` document.
   Default `allowedActions` to the three monitor actions in the reference.
   Reject implicit merge, deploy, production repair, provider resolution,
   tracker closure, or unrelated mutation authority.
3. Treat the exact owner task plus host/project as a single V1 monitor slot.
   Before creation, inspect host-local automation TOML read-only for any active
   task-owned monitor in that slot, then compare `monitorKey`, spec digest,
   prompt marker, name, ticket, target, and query. Update the slot's existing
   monitor when the owner requested an update. If registration requests a
   different monitor while the slot is occupied, return `owner_slot_occupied`
   and require inspect, update, or cancel; never create a second heartbeat,
   duplicate a match, adopt a standing monitor, or build a task fleet.
4. Compare the requested trigger with the live host. V1 accepts an event
   trigger only as a capability request; the current heartbeat API exposes only
   recurrence schedules. Return `capability_blocked` before mutation unless an
   event trigger is actually represented, persisted, and proven on that host.
5. Compare requested lifecycle bounds with fields the live
   `automation_update` schema and scheduler actually persist and enforce.
   A bound copied only into the prompt is declarative, not host-enforced.
   Recurrence `COUNT` or `UNTIL` is supported only after create/update
   read-back retains it and an actual disposable run proves its behavior on
   that host. If required bounds cannot be represented, return
   `capability_blocked` without creating a phantom monitor. Offer the smallest
   honest substitute, such as a manually cancelled heartbeat, only when the
   owner explicitly accepts the weaker lifecycle.
6. Create through `automation_update` only. Put the schema version,
   `monitorKey`, originating context, target/query, conditions, allowed actions,
   result destination, and lifecycle bounds in the prompt so persisted intent
   can be inspected. Do not create or edit raw TOML.
7. Immediately call `automation_update` in view mode. When view mode does not
   return fields, inspect the matching TOML read-only. Compare id, kind, name,
   status, schedule, prompt marker/key, destination, and target task with the
   spec. Record both the canonical owner-facing `specDigest` and the SHA-256 of
   the exact persisted prompt as `persistedIntentDigest`. Return
   `persistence_failed` and clean up any partial creation when the comparison
   fails.
8. Return a `codex.task-owned-follow-up-monitor.receipt/v1` document. Set
   `installed = true` only after read-back matches. Report lifecycle support
   field by field; never infer support from requested input.

### Inspect, Update, And Cancel

- **Inspect**: resolve by receipt automation id plus `monitorKey`, view through
  `automation_update`, and read matching TOML only when view lacks fields.
  Return a fresh receipt with the observed state and SHA-256 of the exact
  persisted prompt as `persistedIntentDigest`.
- **Update**: first read the current state, preserve unspecified fields, send a
  full heartbeat update, then immediately read it back. Increment the receipt
  revision only after verified persistence.
- **Cancel**: delete by exact automation id through `automation_update`, then
  verify that view no longer resolves it and no matching host-local automation
  remains. Return terminal state `cancelled`.
- A missing id, owner mismatch, key mismatch, host mismatch, unsupported bound,
  failed mutation, or failed read-back stops the lifecycle. Never write TOML to
  recover.

### Tick And Result Rules

Every prompt must carry these rules:

1. Read only the exact target/query and the monitor's durable prior result.
2. Compare a stable evidence fingerprint with the prior observation.
3. On no material change, update only host-supported durable monitor state and
   emit no owner message, handoff, tracker comment, or new task.
4. Wake the same owner task only for a new actionable finding, a required
   decision, terminal success, or exhausted observation/retry budget. Include
   the originating ticket, target/query, bounded evidence, condition reached,
   and smallest next decision.
5. If first-party same-task resumption is unavailable or ambiguous, emit at
   most one concise handoff to the declared fallback destination and stop.
6. A result never expands `allowedActions`. External mutation still requires
   separate explicit authority.

The scheduler topology itself is part of verification: a heartbeat must target
the originating task and repeated ticks must not create sidebar tasks. Do not
claim notification silence, automatic expiry, maximum-run enforcement, or
same-task callback behavior beyond what was actually observed.

## Same-Task Pull-Request Recovery

When an automation reconciles an open PR owned by a Codex or Claude task, it is
a recovery coordinator, not a replacement worker. Its prompt must receive or
resolve a durable owner record containing the provider, exact task/session id,
owning host, repository, PR number, and last known head SHA.

Use `orchestrate`'s canonical `prOwner` shape and shared `prDisposition` enum.
On each run:

1. Read the live PR and owner record. If `prDisposition` is
   `waiting_for_bradley`, `blocked`, `merged`, `closed`, or `superseded`, do not
   resume. Only `working` is recoverable, and only while the PR is open.
2. Resolve lifecycle on the owning host immediately before acting. Prefer
   first-party task/agent state. Otherwise use `inspect-codex-session` for Codex
   or `inspect-claude-session` for Claude, and require authoritative lifecycle
   evidence rather than transcript age alone.
3. If the recorded owner is known active, leave it alone.
4. If the recorded owner is known inactive while the PR is non-terminal, resume
   that exact task/session with the current PR number and head SHA. The resumed
   task continues `orchestrate`'s pull-request ownership loop, including
   same-task remediation and exact-head refresh after every push.
5. If lifecycle, owner id, or owner host is unknown, ambiguous, unreachable, or
   only heuristic, fail closed: report `blocked` and do not mutate code or PR
   state.

V1 must never create, fork, dispatch, or cold-start a replacement task for a
recoverable PR. A resume failure is a blocker, not permission to substitute a
new task. Do not claim that a second liveness check prevents overlapping wakes;
it does not. Recovery is supported only when the provider's first-party resume
primitive serializes turns for the exact owner id. If that guarantee is absent
or unknown, block without resuming. Worklog status, recent file activity, and a
previous task final are not substitutes for current lifecycle evidence.

Provider contract:

| Provider | Exact owner id | Authoritative active/inactive evidence | Same-task resume | Unsupported, fail-closed cases |
| --- | --- | --- | --- | --- |
| Codex | Full task/thread id plus owning `hostId` | Host-qualified first-party task state. If unavailable, load `$inspect-codex-session` and run its resolved `scripts/inspect_codex_session.py --query <id> --json --conversation --current-turn`; accept only `state_authority: "lifecycle"` and its `turn_active` field | `send_message_to_thread` for that exact task and host. Local `codex exec resume` is allowed only when the owner record captured the original sandbox/approval restrictions and the command reapplies them exactly | Heuristic transcript state, disconnected/unknown host, ambiguous id, missing original execution restrictions, unavailable inspector helper, or no proven same-task turn serialization |
| Claude | Full resumable `sessionId` plus owning host | Matching `claude agents --json --all` native state; only `busy` is active and `state: done` is resumable inactive | `claude -p --resume <sessionId>` with the original permission restrictions | Transcript-age-only state, interactive/blocked/ambiguous native state, unknown original permissions, remote host unavailable, or no proven same-session serialization |

Immediately before resume, repeat the authoritative query and require the same
inactive owner, open PR, `working` disposition, and owned head. Derive the
stable recovery key from the owner-authored revision/epoch fields and include it
in the resume payload. Do not increment those fields in the reconciler. The
serialized owner records the key before processing; duplicate queued payloads
then no-op. Provider serialization plus the stable key prevents duplicate
turns.

## Core Flow

1. Resolve the request.
   - Capture action: create, update, view, pause, resume, delete, or smoke-test.
   - For a task-owned follow-up monitor, capture and validate the versioned V1
     spec before selecting an automation action.
   - Capture host, project, schedule, prompt, status, model/reasoning only when
     specified, and notification policy.
   - Make reasonable schedule assumptions when they are harmless and state
     them in ordinary language. Ask only when timing, timezone, host, or project
     ambiguity would materially change the result.
2. Resolve the destination.
   - Use `list_projects` and retain `projectId`, `projectKind`, `path`, `hostId`,
     and `hostDisplayName`.
   - Prefer an exact host plus project/path match.
   - If duplicate project registrations exist on one machine, prefer the
     Codex Desktop-controlled host for app automations unless the user names
     the SSH-discovered host explicitly.
3. Choose the execution path.
   - Local host: call `automation_update` directly.
   - Remote host: a project thread on the exact remote `projectId` with
     `environment.type = "local"` is only a capability probe. Ask it to confirm
     that host-local `automation_update` exists before requesting mutation.
     Some remote bridges, including the observed Eve bridge, do not expose this
     app-owned tool.
   - If the probe lacks `automation_update`, stop. The fallback is to open the
     project from the owning machine's local Codex Desktop app and run the
     installer task there; do not pretend the remote caller installed it.
   - Do not create a worktree for automation administration. It changes app
     state, not repository source.
4. Deduplicate before mutation.
   - On the owning host, inspect `$CODEX_HOME/automations/*/automation.toml` for
     an existing automation with the same id, name, or clearly equivalent
     prompt and project.
   - Prefer updating an existing automation over creating a duplicate.
   - For a task-owned follow-up monitor, first enforce the one-monitor slot for
     the exact owner task plus host/project, then compare `monitorKey`, spec
     digest, ticket, target/query, and automation class. A standing monitor is
     not an equivalent match and an occupied task-owned slot cannot create a
     second monitor.
   - Treat the TOML files as read-only evidence. Never create or edit them by
     hand; all mutations go through `automation_update`.
5. Apply the requested mutation.
   - Preserve unspecified fields on updates.
   - Keep notification preferences in the automation fields, not its prompt.
   - New recurring jobs should use `kind = cron`. Use a heartbeat only for a
     follow-up attached to the current local thread.
   - Do not trust a requested `PAUSED` status on the create call. New cron
     creation may persist as `ACTIVE` even when `PAUSED` was supplied. When a
     new job must start paused, create it with a safely distant schedule,
     immediately send a full update with `status = PAUSED`, and verify the
     persisted state before doing anything else.
   - Do not expose raw recurrence-rule strings to the user; describe schedules
     in normal language.
6. Verify on the owning host.
   - Call `automation_update` in view mode after create or update.
   - If view mode renders a card without returning its fields, read the owning
     host's matching `automation.toml` as read-only verification evidence.
   - Confirm id, name, host, project, schedule, status, prompt intent, model,
     reasoning effort, execution environment, and notification policy.
   - For deletion, confirm the delete result and that a subsequent lookup no
     longer finds the automation.
   - For a task-owned follow-up monitor, emit the versioned receipt and record
     each lifecycle field as requested, persisted, and enforced, plus separate
     digests for the canonical spec and exact persisted prompt.
7. Close the installer lane.
   - Read the remote installer thread's final receipt.
   - If it is complete, archive the installer thread when the tool is
     available. Do not archive the automation's future run threads.
   - Report the owning host and whether verification was direct or supplied by
     the host-local installer.

## Remote Installer Prompt

For a remote destination, create one short-lived thread in the remote project
with `environment.type = "local"` as a capability probe. The user's request to
create or manage a remote automation authorizes this probe; it does not
authorize unrelated repo changes. Proceed as an installer only if that task
actually exposes host-local `automation_update`. Otherwise return the exact
project/host receipt needed to launch the installer from the owning machine's
local Codex Desktop app.

Use this prompt shape:

```text
Manage one Codex automation on this machine. This is automation administration,
not repository implementation.

Owning host: <host display name and host id>
Project: <label, path, and project id>
Requested action: <create/update/view/pause/resume/delete/smoke-test>
Name or id: <automation name/id>
Schedule: <plain-language schedule and timezone>
Prompt: <exact automation prompt or requested prompt change>
Requested fields:
- status: <status or preserve>
- model: <model or preserve/default>
- reasoning effort: <value or preserve/default>
- execution environment: <local/worktree; normally local>
- notification policy: <value or preserve/default>

First confirm that this task exposes the Codex `automation_update` tool. If it
does not, stop and return `capability_blocked`; do not edit the repo or raw
automation files. If it does, use that tool and first inspect this
machine's $CODEX_HOME/automations/*/automation.toml read-only and update an
equivalent existing automation instead of duplicating it. Preserve unspecified
fields. If creating a paused automation, do not trust the create call to retain
PAUSED: use a safely distant schedule, immediately update the created automation
to PAUSED with its full fields, and verify persisted status before continuing.
After mutation, view the automation and, when needed, read its automation.toml
as read-only verification evidence. Return a concise receipt with:
action, automation id, name, host, project, schedule in plain language, status,
model, reasoning effort, execution environment, notification policy, and
verification result. Do not edit the repo, run the automation prompt, or make
any other changes.
```

Wait for the probe/installer to finish with the thread wait/read tools. If it
reports that `automation_update` is unavailable on that host, stop and report
the capability blocker plus the local-Desktop fallback. Do not work around it
by writing TOML over SSH.

## Existing Automation Operations

For view, update, pause, resume, or delete:

- Use the supplied automation id when available.
- Otherwise resolve by exact name on the owning host.
- If several matches remain, ask rather than guessing.
- Preserve the original host. An automation id from another machine will not
  necessarily resolve through the local automation tool.
- A local non-match means **not visible from this host**, not **does not
  exist**.

When only a remote session/thread id is provided as context, load
`inspect-codex-session` and resolve that thread's host before selecting the
automation path.

## Smoke Test

Use a reversible smoke test when the user asks to test remote installation:

1. Resolve the exact remote host and project.
2. Probe a remote local-environment task for `automation_update`. If absent,
   stop and return the owning-Desktop fallback; do not attempt creation.
3. Only after a successful probe, create a uniquely named automation with
   a safely distant schedule and a harmless prompt that performs no mutation if
   it is accidentally run.
4. Immediately update it to `PAUSED`, then view it on the owning host and
   verify the persisted status and every requested field.
5. Delete it through `automation_update`.
6. Confirm it is no longer present.
7. Archive the installer thread after its receipt is captured.

Never activate a smoke-test automation. If cleanup fails, report the exact
automation id, host, and remaining status prominently.

## Permission Boundaries

- Creating, updating, pausing, resuming, or deleting an automation is an
  external state change and requires clear user intent.
- Authorization to install an automation does not expand what its future runs
  may do. Encode explicit read-only, tracker-write, implementation, delivery,
  deploy, or destructive-action boundaries in the prompt.
- Do not copy secrets into prompts, installer threads, receipts, or reports.
- Do not move or hand off an unrelated thread merely to gain remote access.
- Do not use SSH to edit automation state. SSH is acceptable for read-only host
  diagnosis when separately authorized or already within scope.

## Reporting Shape

```text
Automation: <name> (<id>)
Host: <host display name> (<host id>)
Project: <label> — <path>
Action: <created/updated/viewed/paused/resumed/deleted/tested>
Schedule: <plain language, including timezone>
Status: <active/paused/deleted>
Execution: <local/worktree>, <model>, <reasoning effort>
Notifications: <policy>
Verification: <viewed on owning host / installer receipt / blocker>
Installer thread: <thread id, archived or retained>
```

Do not claim a remote automation exists based only on creating the installer
thread. The verified automation receipt is the completion boundary.
