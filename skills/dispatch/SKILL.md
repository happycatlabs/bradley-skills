---
name: dispatch
description: Create and hand off Codex worktree sessions for Linear-ticket or repo work. Use when the user asks to fork, dispatch, spin up, start background sessions, create worktree-backed Codex threads, seed child sessions with orchestrate, prepare multiple ticket-specific agents, or hand off work from a coordinating chat. Pair with monitor only when the user asks to watch, check, steer, or wrap child sessions. For scheduled or recurring Codex jobs, including jobs owned by another machine, use codex-automation instead.
---

# Dispatch

Use this skill to turn a coordinating chat into one or more durable child Codex
worktree sessions. Dispatch creates focused children and a clear JSON
delegation ledger; it does not automatically monitor every child forever.

Ledger monitoring fields describe intent and last-known state, not a live
service. Dispatch must not mark monitoring active unless `$monitor` was actually
run and produced watcher ids or an explicit persistence mechanism.

If the user later asks to check progress, watch, steer, or wrap existing child
sessions, use `$monitor`.

If the user asks to create, schedule, update, test, pause, resume, or delete a
recurring Codex automation, use `codex-automation`. A remote automation may use
a short-lived remote installer thread, but it is not a dispatched work session
and does not need a dispatch ledger or worktree.

If the user asks you to send follow-up instructions to already-created children,
that is monitor `steer` work. After sending material steering, default to
watching the affected lanes again unless the user clearly asked only to deliver
the note.

If a dispatched child later returns findings, concerns, or feedback and the
parent addresses or rejects that feedback, the follow-up must go back to the
same child thread whenever possible. Do not create a fresh child to judge
whether the original child's concern was addressed unless the original thread is
unavailable; disclose that loss of continuity.

If the user names `$dispatch` and `$monitor` together, dispatch is only the
setup phase. After the child threads and ledger exist, immediately start
`$monitor` in fanout `run-to-terminal` mode unless the user asked for a
snapshot/window. For `N` dispatched child threads, expect `N` watcher subagents
under the parent coordinator while the parent turn remains active. The parent
should not send its final answer until the task agents are terminal, the monitor
watchers have stopped, and their report is folded into the parent final.

## Dispatch Intents

Choose and record one intent for every created task:

- `delivery`: durable ownership of an accepted outcome, ticket, worktree,
  branch, or pull-request lifecycle.
- `exploration`: a durable investigation or brainstorm Bradley may want to
  revisit directly; it does not acquire delivery authority by implication.
- `watcher`: status-only observation of named owner tasks. It reports material
  transitions and user-input needs to the named lead and does not take over the
  work.

When the parent is an engineering, project, or domain lead, load
`engineering-lead` and keep that parent interruptible. Dispatch substantive
work instead of turning the lead into its implementation lane.

## Context Capsule

Prefer a fresh, focused task with a concise capsule over a full-history fork.
Include the source lead/task, project/domain, why the work matters now, exact
outcome or question, relevant recent conversation and settled decisions,
taste constraints and unresolved tensions, authoritative links, verified facts
versus assumptions, the minimum shippable outcome and rough file/diff budget,
non-goals, privacy and mutation authority, evidence, stop condition, and report
destination. Use broader history only when the
conversation itself is material and cannot be represented faithfully.

Every delivery child must be told that non-blocking findings do not expand its
diff. When tracker writes are authorized, it records useful follow-ups in the
existing tracker; otherwise it returns them in the handoff. It ships once the
minimum outcome and required checks are satisfied.

## Core Flow

1. Load explicitly named companion skills.
   - Route scheduled or recurring jobs to `codex-automation`; do not model them
     as durable child work sessions.
   - Use `inspect-codex-session` only when the user gives Codex session ids or
     the source state lives in another Codex thread.
   - Use `orchestrate` when child sessions should run as lead-agent workflows.
   - Use tracker skills such as `linear` only when tickets need live details,
     constraints, comments, or state updates.
2. Acquire source context.
   - If session ids are provided, run the session inspector and extract only
     operational facts: JSONL path, title, cwd/worktree, latest request,
     latest completion, commits, pushes, deploys, tracker state, and blockers.
   - If no session id is provided, skip session inspection. Do not turn
     inspection into a required dispatch step.
   - Prefer live tracker data over memory or old transcript summaries.
   - Build the context capsule above. Do not make the child rediscover settled
     decisions merely because the dispatch starts with fresh context.
3. Reconcile tracker state before dispatch.
   - Fetch relevant tickets live.
   - Update ticket descriptions/comments when the user gives new durable
     constraints.
   - Confirm completed tickets are actually completed before treating them as
     done.
4. Create each child thread as a project worktree when work may run in
   parallel.
   - Use `list_projects` to resolve the project id.
   - Prefer a saved project whose checkout is the actual implementation repo.
     If that repo is not registered on the target host, use the nearest
     legitimate project only as task context and state this explicitly in the
     prompt. Require the child to create a dedicated git worktree for the real
     repo before editing; never let it modify a shared checkout merely because
     Codex could not create the desired project worktree directly.
   - Use `create_thread` with `target.type = "project"` and
     `environment.type = "worktree"`.
   - Start from the appropriate branch, normally current `master` unless the
     user names a different base.
   - Put the full work request in the initial prompt.
5. Seed child prompts with the right workflow.
   - If the user asked for orchestrated work, start the prompt with:
     `[$orchestrate](<target-home>/.agents/skills/orchestrate/SKILL.md)` after
     resolving `<target-home>` on the machine that will run the child. Never
     paste the dispatcher's local home path into a remote child prompt.
   - Include repo path, ticket id/title, base branch/worktree expectation,
     relevant docs/skills, user constraints, suggested slices, validation, and
     closeout rules.
   - Include source thread/session context when material, but summarize it.
     Do not paste raw transcripts.
   - Name the dispatch intent, parent lead task, report destination, and exact
     terminal condition.
   - Tell the child not to stage, commit, push, deploy, or close the tracker
     unless explicitly asked in that child thread or a later monitor wrap-up.
   - Tell the child that if it is later authorized to open or adopt a PR, its
     exact task id remains the owner through `orchestrate`'s pull-request
     ownership loop. Do not dispatch a separate closer for CI or review fixes.
   - Tell the child not to add local agent session logs to the repo unless the
     repo explicitly requires them.
6. Rename created threads.
   - Match the user's existing title style when known.
   - For Linear tickets, prefer:
     `HAPPY-149 — Evaluate Anthropic web search/web fetch for chat agent`
   - If `create_thread` returns `pendingWorktreeId`, wait briefly and use
     `list_threads` to find the materialized child thread before renaming.
   - Connected remote machines may expose one task through both a Desktop
     `remote-control` host and an SSH-discovered alias. When `id`, `cwd`, and
     creation time identify the same task, treat those entries as aliases, not
     separate children. Prefer the connected active Desktop entry as the
     owning host and record the aliases in the ledger when useful.
   - If `set_thread_title` or `read_thread` rejects that duplicated id as
     ambiguous, do not redispatch, hand off, or create a replacement merely to
     make the API call succeed. Keep the generated title if necessary and use
     `inspect-codex-session` on the owning host over SSH for the materialization
     check. The task's existence and lifecycle matter more than a cosmetic
     rename.
7. Record the delegation ledger.
   - Capture source thread/session id, ticket id, child thread id,
     pending worktree id if any, title, cwd/worktree, base branch, expected
     validation, closeout permissions, tracker policy, and explicit monitoring
     fields.
   - Use `monitoringRequested` for user intent only. Use `monitoringMode`,
     `monitoringStatus`, `watcherAgentIds`, and `lastMonitorAt` for actual
     monitoring state. Use `monitoringPermission` to record whether the last
     monitor run was status-only, steering, or wrap-up.
   - Use per-child status axes when useful:
     `worktreeState`, `trackerState`, and `deliveryState`.
   - For a PR-producing child, use `orchestrate`'s canonical `prOwner` record.
     The originating child must write and read it back when it opens/adopts the
     PR and after every push. The dispatch ledger may mirror that record for
     discovery, but it is never the authoritative fallback store. These fields
     support same-task recovery; they do not prove that monitoring is active.
   - Write the ledger to `~/.agents/dispatch-ledgers/<dispatch-id>.json` when
     filesystem writes are available.
   - Also print a compact human-readable ledger in the final response.
8. Stop after dispatch by default.
   - Do a short materialization check when needed to confirm thread ids/titles.
   - Do not keep polling created children unless the user asks to monitor,
     wait, steer, or wrap them.
   - If the same request included `$monitor`, do not stop here; hand the ledger
     to monitor and spawn watcher lanes for the children.

## Delegation Ledger

Store ledgers as small JSON files outside the repo. Do not use SQLite until the
workflow needs historical queries, dashboards, or concurrent writers.

Default directory:

```text
~/.agents/dispatch-ledgers/
```

Use a readable id such as:

```text
2026-06-20-lumen-happy-145-149.json
```

Write atomically when possible: write a temp file in the same directory, then
rename it into place.

Schema shape:

```json
{
  "schemaVersion": 1,
  "dispatchId": "2026-06-20-lumen-happy-145-149",
  "createdAt": "2026-06-20T06:45:00Z",
  "sourceThreadId": "01900000-0000-7000-8000-000000000005",
  "repo": "<target-home>/dev/pom",
  "baseBranch": "master",
  "monitoringRequested": false,
  "monitoringMode": "none",
  "monitoringPermission": "status-only",
  "monitoringStatus": "not_started",
  "watcherAgentIds": [],
  "lastMonitorAt": null,
  "children": [
    {
      "ticketId": "HAPPY-145",
      "title": "Improve entry processing pipeline throughput and maintainability",
      "threadId": "019...",
      "pendingWorktreeId": null,
      "worktree": "<target-home>/.codex/worktrees/.../pom",
      "status": "dispatched",
      "worktreeState": "not_started",
      "trackerState": "active",
      "deliveryState": "not_started",
      "prOwner": null,
      "promptIntent": "orchestrated implementation/investigation",
      "closeoutPolicy": "no commit/push/deploy/tracker close unless requested",
      "tracker": {
        "type": "linear",
        "id": "HAPPY-145",
        "closeOnlyWithDurableProof": true
      },
      "validation": [
        "bun run format:check",
        "bun run lint",
        "bunx convex dev --once"
      ]
    }
  ]
}
```

Keep the final answer ledger compact enough to paste into a future `$monitor`
request, but prefer the JSON path when one was written.

## Child Prompt Template

Use this shape for each created thread:

```text
[$orchestrate](<target-home>/.agents/skills/orchestrate/SKILL.md) Work on Linear ticket <ID>: <title>.

Repo: <repo path>. Start from <branch> in your own worktree. Read AGENTS.md and
the repo skill before changing code. Use the Linear app to read <ID> before
implementation.

Source context:
- Parent thread/session: <id if relevant>
- Prior facts: <short operational summary, no raw transcript>

User constraints:
- <constraint 1>
- <constraint 2>

Goal: run this as an orchestrated <investigation/prototype/implementation>.
Establish baseline, choose safe slices, and use subagents where they reduce
risk or cycle time.

Minimum shippable outcome: <smallest durable result, proof, and rough file/diff
budget>. Stop adding work and ship when this is proven. Classify review or
discovery output as blocking, tracked follow-up, or rejected; never implement a
non-blocking finding in this diff.

Suggested slices:
- <slice 1>
- <slice 2>
- <slice 3>

Closeout rules:
- Run the repo-appropriate validation.
- For non-trivial code or risky decisions, follow orchestrate's critique gate.
- Do not stage, commit, push, deploy, or close Linear unless explicitly
  requested in this thread or by a later monitor/wrap-up instruction.
- If you are authorized to open or adopt a PR, you own it through
  `orchestrate`'s pull-request ownership loop. Monitor CI and review, remediate
  in this same task, refresh exact-head evidence after every push, and stop only
  at a defined terminal disposition. Write and read back the canonical
  `prOwner` record at adoption and after every push.
- Do not add local agent session logs to the repo unless repo instructions
  explicitly require them.

Deliverable expectation: focused code/docs if warranted, validation evidence,
changed files, remaining risks, and whether the ticket is ready for durable
closeout.
```

## Handoff To Monitor

Use `$monitor` after dispatch when the user asks to:

- check progress or status,
- watch one or more child sessions,
- decide whether a child is clean and ready,
- send steering instructions,
- have a child wrap up, commit, push, deploy, or update a tracker,
- verify that a dispatched child really finished.

Pass the delegation ledger to monitor. Dispatch should not invent monitoring
state or claim a child is running unless thread tools confirm it.

If the user asks to start monitoring immediately after dispatch, invoke
`$monitor` after the child threads and ledger exist. For multiple children,
that means one watcher subagent per child unless the user asks for a snapshot or
subagents are unavailable. Use `run-to-terminal` so the parent remains open
until every child reaches `durable-done`, `blocked`, `waiting`, or `stale`.
For a PR-owning child, `durable-done` requires `merged`, `closed`, or
`superseded`; `waiting` requires a specific Bradley action after all
agent-actionable work is done. PR opened, CI/review pending, or findings awaiting
remediation are non-terminal. `stale` is non-terminal for a PR owner until
authoritative lifecycle reclassifies it as resumed/`working`,
`waiting_for_bradley`, or `blocked`.
Otherwise end with monitoring state `not_started` and say that monitoring is
not active.

When the parent sends material steering to existing child threads, hand the
ledger to `$monitor` afterward unless the user explicitly asked for note-only
delivery. Do not treat `lastSteeredAt` or `status: steered` as evidence that the
new work is complete.

## Tracker Updates

When the user adds a new constraint while dispatching:

- Update the ticket before creating child threads so the child can read it from
  the source of truth.
- Prefer editing the description when the constraint is durable acceptance
  criteria.
- Prefer a comment when the constraint is context, a handoff note, or a
  temporary warning.
- In the final answer, say exactly which ticket changed.

For capability constraints, write them as explicit gates:

```text
Provider-defined Anthropic web tools may only be attached when the resolved
provider is Anthropic and the selected model supports that specific tool. Do not
attach Anthropic web tools for non-Anthropic providers, fallback models, or
unsupported Anthropic models.
```

## Thread Tool Notes

- Use `create_thread` when the user explicitly asks for new sessions or
  background threads.
- Use project worktrees for parallel implementation; same-directory forks are
  only appropriate for read-only continuation or serial follow-up.
- `create_thread` may return a `pendingWorktreeId`. In that case, do not invent
  a thread id. Poll `list_threads` for the child thread and then call
  `set_thread_title`.
- `fork_thread` is useful when the new thread should inherit a specific source
  thread history. `create_thread` is usually cleaner for ticket dispatch because
  the initial prompt can be intentionally scoped.
- Use `send_message_to_thread` only when an already-created child needs an
  initial correction before monitoring starts. For later steering of active
  children, use `$monitor` with `steer` permission and resume watcher coverage
  afterward unless the user asked for a one-shot note.
- Do not leave unclear whether a child was actually created. Check recent
  threads if creation was asynchronous.

## Safety Checks

- Before dispatching repo work, check whether the current branch and tracker
  state have changed recently enough to affect the prompt.
- Do not close trackers from the parent dispatch chat unless the user
  explicitly asks and durable completion is already proven.
- Do not claim a child thread has a worktree until the thread list shows its
  `cwd`.
- Do not include secrets, raw transcript dumps, or sensitive env values in child
  prompts.
- Do not create repo session logs by default; durable status belongs in the
  parent final answer, child final answer, and tracker/PR comments when those
  systems are in scope.

## Good Final Shape

```text
Created two worktree-backed sessions:

Ledger: `~/.agents/dispatch-ledgers/2026-06-20-lumen-happy-145-149.json`

- `HAPPY-149 — Evaluate Anthropic web search/web fetch for chat agent`
  - Thread: `<thread id>`
  - Worktree: `<path>`
  - Closeout: no commit/push/deploy/tracker close unless later requested

- `HAPPY-145 — Improve entry processing pipeline throughput and maintainability`
  - Thread: `<thread id>`
  - Worktree: `<path>`
  - Closeout: no commit/push/deploy/tracker close unless later requested

Updated `HAPPY-149` with the provider/model gating constraint.

I am not monitoring these yet; use `$monitor` with the thread ids when you want
status or wrap-up.

Monitoring: `not_started`; watcher lanes: 0.

::created-thread{threadId="<thread id>"}
::created-thread{threadId="<thread id>"}
```
