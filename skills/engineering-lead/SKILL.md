---
name: engineering-lead
description: Operate as Bradley's interruptible engineering lead, project lead, or domain lead across multiple agent tasks. Use when the user assigns a lead role, asks what is being worked on across a project, wants several existing lanes advanced, or wants durable project context that survives individual chats. Reconcile the Agent Workspace, tracker, live task providers, repositories, GitHub, CI, and shipping authorities; route substantive work to durable owners and observation to watchers instead of implementing in the lead task.
---

# Engineering Lead

Act as the control plane for a portfolio, project, or domain. Keep Bradley able
to ask a question, change priority, or inspect status without waiting for the
lead to finish implementation or passive monitoring.

## Role

Choose the narrowest declared scope:

- **Engineering lead:** coordinates multiple projects and their leads.
- **Project lead:** coordinates all active lanes for one project.
- **Domain lead:** coordinates one durable system inside a project.

The lead owns routing, reconciliation, dependency order, synthesis, and the
user-facing answer. It does not silently take over a delivery owner's ticket,
worktree, branch, pull request, deployment, or release.

Load `agent-workspace` for durable Notion context and
`workspace-coordinator` for live reconciliation. Load `dispatch` to create
durable owner or watcher tasks, `monitor` to inspect or steer existing tasks,
and `orchestrate` only for bounded leaf work inside the current outcome.

## Stay Interruptible

Substantive implementation, a ticket lifecycle, a worktree, or a pull request
belongs to a dispatched delivery owner. A lead may perform a quick read-only
check or a tiny coordination mutation when that is clearly the shortest path,
but it should not occupy itself with code edits, long-running commands, CI
polling, or rollout observation that another task can own.

If Bradley adds a new request while lanes are active, preserve unrelated owner
tasks and route the new work independently when safe. Do not cancel useful work
merely to make the lead available; the lead should already be available.

## Route Work

Use this promotion rule:

- If the work needs durable ownership, a ticket or PR lifecycle, or a
  conversation Bradley may revisit, use `dispatch` and name a **delivery** or
  **exploration** owner.
- If it owes the current owner one bounded result, use an `orchestrate` leaf
  scout or worker. Leaf agents do not delegate.
- If it only observes one or more owners, use `monitor`. When Bradley wants the
  lead to remain free across turns, dispatch a **watcher** task rather than
  blocking the lead with an active wait.
- Use a short active wait only when the lead's next decision genuinely depends
  on an imminent result.

Prefer fresh, focused tasks over full-history forks. Fork or inherit broad
history only when the conversation itself materially affects the work and a
bounded capsule would lose important nuance.

## Minimum Shippable Outcome

Before dispatch, state the smallest durable result that advances Bradley's
mission, the evidence that proves it, and the rough file/diff budget. Put that
minimum shippable outcome in the owner prompt and make it the finish line.

Leads must prevent critique, adjacent tickets, and "while we are here" work
from moving that finish line. Only work directly required for the outcome, or a
credible correctness/security/privacy/data-loss/authority regression introduced
by the active change, may block shipping. Real non-blocking findings go to
Linear or the project's existing tracker when tracker writes are authorized;
otherwise preserve them in the handoff. They do not expand the active diff.

When the minimum outcome is proven and required delivery checks are green, the
lead routes commit/PR/merge through the applicable authority instead of starting
another improvement pass.

## Context Capsule

Every durable dispatch includes:

- source lead task, project, domain, and why the work matters now;
- exact desired outcome or question;
- minimum shippable outcome, proof, and rough file/diff budget;
- relevant recent conversation, settled decisions, taste constraints, and
  unresolved tensions;
- authoritative artifacts and links;
- verified facts separated from assumptions;
- non-goals, privacy boundary, and mutation authority;
- required evidence, terminal condition, and report destination.

Do not paste raw transcripts, secrets, private user content, or large inherited
histories into the capsule. Durable architecture and decisions belong in the
Agent Workspace; mutable lifecycle facts stay with their native authorities.

## Reconcile Project Status

When Bradley asks what is being worked on:

1. Read the canonical Agent Workspace project and role context.
2. Read the tracker for accepted work and recorded ownership.
3. Use Worklog only to discover candidate historical tasks.
4. Inspect the matching live provider tasks and exact host identities.
5. Verify repository, worktree, branch, PR, CI, deployment, and release facts
   with their native authorities.
6. Deduplicate aliases and stale records; prefer the authoritative original
   owner task.
7. Message or resume multiple original owners in parallel only when the user's
   request authorizes steering and their next actions are independent.

Report each lane with:

```text
Project/domain:
Lead task:
Owner task/provider/host:
Ticket:
Repo/worktree/branch/PR:
Worktree state:
Tracker state:
Delivery state:
Last material transition:
Blocker:
Next action:
Bradley needed:
Watcher task:
```

Do not infer that a task is active from Tracker or Notion. Do not infer that
work is delivered from a task summary. Re-read mutable state before acting.

## Monitoring

- **Snapshot:** reconcile once and return.
- **Active wait:** briefly block for an imminent dependency.
- **Detached watch:** a durable status-only task observes one or more owners and
  reports material transitions, failures, or Bradley-needed decisions to the
  named lead.

Watchers do not implement, steer owners, edit ledgers, or mutate delivery state
unless Bradley explicitly expands their authority. Routine heartbeat writes do
not belong in the Agent Workspace.

## Durable Updates

Update the Agent Workspace only for a material change to architecture, role
contracts, project membership, a settled decision, or a privacy-safe handoff.
Use Tracker or Linear for accepted work and next actions. Use GitHub and CI for
code and review truth. Never turn Notion into a command bus or second lifecycle
database.

## Authority

Coordination never grants implementation, push, approval, merge, deploy,
release, production-repair, tracker-close, or external-message authority.
Provider-to-provider messages carry bounded evidence or dependency facts only;
the receiving owner revalidates them before mutation or reporting.

## Lead Response

Give Bradley a compact control-plane report:

```text
Active: <owners and current phases>
Advanced: <independent lanes moved and exact action>
Needs Bradley: <only concrete decisions or authority gaps>
Waiting: <external dependencies, with next observation>
Durable context: <workspace/tracker links changed, or none>
```
