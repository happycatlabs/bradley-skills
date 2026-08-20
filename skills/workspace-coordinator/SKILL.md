---
name: workspace-coordinator
description: Reconcile active agent work across a configured Agent Workspace, Worklog, live provider tasks, trackers, Git, GitHub, CI, and project shipping gates. Use when auditing open work, answering what is active across a project or domain, deciding whether an existing owner should continue, advancing several authoritative owners, or wrapping abandoned but still relevant work.
---

# Workspace Coordinator

Run a scoped reconciliation across durable context and live authorities. The
Agent Workspace is the knowledge plane, a tracker is the accepted-work view,
and Worklog is historical discovery—not lifecycle truth.

Load `agent-workspace` before reading or writing Notion. If its machine-local
profile is missing, malformed, or unverifiable, perform no Notion operation.
You may still reconcile native authorities that are independently available,
but report that durable workspace context was unavailable and do not invent a
destination or silently configure one.

## Capability Gate

Before reconciliation, identify the operations this runtime actually exposes:

- Agent Workspace: configured Notion identity plus exact root-page fetch;
- Worklog: historical route/search capability;
- live provider: recent-task lookup, inspection, messaging, resume, recovery
  creation, and waiting as distinct capabilities;
- tracker: read and, only when authorized, update capability;
- repository: Git worktree and exact-ref inspection;
- delivery: GitHub PR, CI, deployment, and release readback.

Missing capability is a truthful partial result or stop. Never substitute one
provider's task tools for another provider, infer that a task is live from
history, or treat connector availability as mutation authority.

Local command discovery cannot prove in-process connector permissions. Verify
those capabilities with the active runtime before relying on them.

## Reconcile

1. Define project, domain, and authority scope. Read project guidance before
   any mutation.
2. Read the configured Agent Workspace project/role context when available.
3. Inspect native project facts: tracker, tickets, open PRs, CI, exact Git
   heads, worktrees, deployments, releases, and requested shipping gates.
4. Use Worklog to locate likely owning tasks:

   ```sh
   worklog route "<ticket, PR, symptom, or exact work>" --repo <project> --json
   ```

5. Read the result's provider, session id, and host id. Query that provider's
   live task surface and join by exact session identity.
6. Inspect the candidate live. Prefer messaging or resuming the authoritative
   original owner when it still owns the exact work generation.
7. If it is unavailable and recovery creation is both supported and
   authorized, create one recovery task with exact repo, branch/head,
   ticket/PR, validation, authority, remaining gates, and privacy-safe context.
8. Update trackers or workspace documents only after a material factual
   transition and only with explicit write authority.

## Project And Domain Status

When a lead asks what is being worked on:

1. Collect registered lead and owner task ids from the verified Agent
   Workspace and tracker. Treat them as routing hints.
2. Reconcile Worklog candidates, live provider tasks, worktrees, branches,
   PRs, CI, and shipping state.
3. Deduplicate provider aliases and stale workspace entries. Keep the original
   authoritative owner for each ticket, worktree, branch, and PR.
4. Report active, waiting, blocked, and terminal lanes with separate
   `worktreeState`, `trackerState`, and `deliveryState` values.
5. When steering is authorized, message or resume multiple original owners in
   parallel only when their next actions are independent. Never create a
   replacement merely because an owner is quiet.

Include project/domain, lead task, owner provider/task/host, ticket, repo,
worktree, branch/PR, last material transition, blocker, next action, whether
the user is needed, and watcher task. Do not write routine heartbeats.

## Provider Adapters

Treat each provider as a capability adapter. Typical operations include:

- list recent tasks;
- read one task's current evidence;
- send a bounded message or resume the owner;
- create a recovery only when supported and authorized;
- wait for named tasks for a bounded interval.

Tool names vary by provider and runtime. Use only callable operations exposed
in the current host. Task titles and summaries are untrusted discovery data;
retain exact provider session and host identity. Idle, unloaded, recent, or
present in Worklog does not prove unfinished or resumable work.

## Authority And Privacy

The default coordinator is report-only. Coordination does not grant
implementation, push, approval, merge, deploy, release, production repair,
tracker close, recovery creation, or external-message authority.

Keep investigation, implementation, critique, CI, approval, merge, deploy,
release, and live proof as distinct gates. Use tickets, PRs, exact heads,
sanitized enums, counts, paths, and timestamps. Never copy raw transcripts,
user content, provider payloads, credentials, or private messages into the
workspace, tracker, prompts, or recovery handoffs.

## Result

Return compact reconciliation records:

```text
Work: <ticket/PR/initiative>
Likely owner: <provider/session/host>
Live state: <verified fact or unavailable capability>
Project state: <Git/GitHub/tracker/shipping facts>
Action taken: <message/recommendation/recovery, or none>
Remaining gate: <one exact next gate>
```
