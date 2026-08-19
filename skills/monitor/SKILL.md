---
name: monitor
description: Monitor existing Codex child threads with a lead monitor and optional watcher subagents. Use when the user asks to monitor, check progress, get status, wait on child sessions, inspect dispatched work, decide whether a child is clean, send steering or wrap-up instructions, push/deploy/close after a child finishes, supervise multiple Codex worktree sessions, or use a dispatch ledger. Do not use for creating new sessions; use dispatch for that.
---

# Monitor

Use this skill to supervise existing child Codex threads without turning every
dispatch into background polling. The main agent is the lead monitor: it owns
the board, chooses watcher lanes when useful, aggregates findings, and keeps
plain monitoring read-only.

Status-only is the default. Send follow-up prompts, update ledgers, commit,
push, deploy, or close trackers only when the user explicitly asks for steering,
wrap-up, ledger refresh, or durable closeout.

For a quick status snapshot of one child thread, the lead monitor may inspect it
directly. For parent-owned active monitoring, dispatch+monitor requests, or any
request that asks for a subagent/watcher, spawn watcher subagents even if there
is only one child. For multiple child threads, fan out to read-only watcher
subagents when subagent tools are available.

Watcher subagents are work inside the current monitor turn. They are not a
background service unless an explicit automation or thread wakeup was created.
The best default for active orchestration is to keep the parent turn open until
the task agents reach terminal states, watcher agents report back, and the lead
monitor gives the final aggregate report.

When the lead monitor sends material steering or wrap-up prompts, the prompt is
not the outcome. Start or resume monitoring afterward unless the user explicitly
asked only to deliver the note. End by saying whether monitoring is still active,
stopped, or handed to an explicit automation/thread wakeup.

## Pull-Request Owners

When a target task opened or adopted a pull request, use `orchestrate`'s
pull-request ownership loop as the completion contract. The exact originating
task remains the owner: CI or review in progress, an open PR, and actionable
findings are all non-terminal. Send findings back to that same task, require it
to validate and push the fix, then monitor the new exact head again.

After every push, discard prior-head evidence and read back the current PR head,
required CI, automated review, conversations, and disposition. Stop only when
the PR is merged, closed, explicitly superseded, blocked with no safe agent
action, or waiting for a specific Bradley decision after all agent-actionable
work is complete. A scheduled recovery may resume the recorded same task only
when first-party lifecycle proves it inactive. Unknown lifecycle blocks; never
create or dispatch a replacement PR owner in V1.

Verify the canonical `prOwner` record from `orchestrate` before treating a task
as recoverable. The originating owner must write and read it back at PR
adoption and after every push; this write is part of PR ownership, not optional
monitor-ledger bookkeeping. A status-only monitor remains read-only and reports
a missing or stale record as `blocked`. A steering/wrap monitor tells the same
owner to repair the record and then verifies the readback.

When a parent coordinator has just dispatched `N` child Codex sessions and the
user asked to monitor them, the expected shape is `N` child sessions plus `N`
monitor watcher subagents running under the parent turn, one watcher per child.
`N` includes one: one dispatched child plus monitor means one watcher lane. For
example, three dispatched tickets should have three watcher lanes while the
parent remains active. The parent should not send its final answer until the
task agents are done, the monitor watchers have stopped, and the monitor report
has been folded into the parent final.

## Lead-Safe Monitoring

An `engineering-lead`, project lead, or domain lead should not be held open by
passive monitoring when Bradley wants it available for conversation and new
priorities. Choose explicitly:

- `snapshot`: the lead reconciles once and returns.
- `active wait`: the current turn waits only because its next decision depends
  on an imminent result.
- `detached watch`: use `dispatch` with intent `watcher` to create a durable,
  status-only task that can observe one or more named owners across turns.

A watcher subagent created by this skill is attached to the current turn and is
not a detached service. A detached watcher reports material transitions,
failures, or Bradley-needed decisions to the exact named lead. It does not take
over implementation, steer owners, edit ledgers, or mutate delivery state
unless Bradley explicitly grants that authority. Prefer a fast economical
model when the provider supports it, but treat the watcher's report as evidence
to revalidate rather than lifecycle truth.

When monitoring several project lanes, aggregate by project/domain and preserve
the original owner task for each ticket, worktree, branch, and PR. The lead may
advance several owners when explicitly asked to steer and their next actions
are independent; it must not replace them with a new lifecycle.

## Core Flow

1. Identify targets.
   - Prefer explicit thread ids from the user or a dispatch ledger JSON file.
   - Dispatch ledgers normally live under
     `~/.agents/dispatch-ledgers/<dispatch-id>.json`.
   - If the user gives titles, tickets, or pending worktree ids, use thread
     listing/search tools to resolve them.
   - If the user gives a Codex session id instead of a live thread id, use
     `inspect-codex-session` as context acquisition.
2. Choose topology, lifetime, and permission.
   - Topology `single`: one child thread. Use direct inspection only for quick
     `snapshot` status checks. Use one watcher subagent for `run-to-terminal`,
     dispatch+monitor, or explicit subagent/watcher requests.
   - Topology `fanout`: two or more child threads; spawn watcher subagents when
     available unless the user asked for a one-shot snapshot.
   - Topology `fallback`: if watcher subagents are unavailable, monitor directly
     with a bounded polling plan and say that fanout was unavailable.
   - Lifetime `snapshot`: one status pass, then stop.
   - Lifetime `bounded-watch`: keep this turn open and poll until the stop
     condition or requested window is reached.
   - Lifetime `run-to-terminal`: keep this parent turn open until every target
     reaches a terminal state, then stop watcher lanes and report. This is the
     default when the user combines dispatch with monitor or says to keep
     monitoring until the task agents are done.
   - Lifetime `persistent`: only when the user explicitly asks for
     background/ongoing monitoring and an automation or thread-wakeup tool is
     available. If no persistence mechanism is available, say so and offer
     `bounded-watch` or a manual resume path.
   - Permission `status-only`: default; no follow-up prompts or ledger writes.
   - Permission `steer` or `wrap`: use only when the user explicitly asks for
     steering, waiting, wrap-up, push/deploy, tracker closeout, or ledger update.
3. Assign watcher lanes for fanout.
   - Actually spawn watcher subagents for 2+ targets when subagent tools are
     available. For a fresh dispatch ledger, default to one watcher per active
     child thread. If they cannot be spawned, switch to `fallback`; do not
     describe the run as watcher-backed.
   - Give each watcher one thread by default, or a small group only when the
     group is truly lightweight.
   - Watchers are read-only by default. They may inspect thread state and
     outputs, but must not send follow-up prompts, commit, push, deploy, close
     trackers, or edit ledgers.
   - Ask each watcher to return only the status card described below.
4. Snapshot each target.
   - Use `read_thread` with a small `turnLimit` first.
   - Include outputs only when needed to inspect validation, diffs, blockers,
     commits, deploys, or tracker updates.
   - Do not paste raw transcripts; summarize operational facts.
5. Classify status.
   - `running`: work is active or commands are still executing.
   - `waiting`: the child asks for user/parent input.
   - `idle-local`: the child finished a local patch but did not make durable
     delivery.
   - `ready-to-wrap`: scoped work, validation evidence, critique/review handled
     or clearly unnecessary, no unresolved blocker.
   - `durable-done`: commit/merge/push/deploy/tracker proof is present as
     applicable.
   - `blocked`: missing dependency, failing validation, unclear acceptance, or
     unsafe/unrelated changes.
   - `stale`: no meaningful movement after the requested monitoring window.
     This is terminal only for non-PR work; a PR owner still requires
     authoritative lifecycle classification.
   - Also separate three axes when the user asks whether something is "done" or
     "closeable":
     - `worktreeState`: running, clean-diff, committed, merged-local, pushed.
     - `trackerState`: active, blocked-by-children, ready-to-close, closed.
     - `deliveryState`: local-only, PR-opened, pushed, deployed, released,
       post-rollout-monitoring.
     A child can be `ready-to-wrap` while its parent tracker remains
     `blocked-by-children`; say that explicitly.
   - A PR owner cannot be `ready-to-wrap` or `durable-done` merely because its
     patch is pushed. Pending CI/review is `running`; actionable findings remain
     `running`; Bradley-only disposition is `waiting`; merged, closed, or
     superseded is `durable-done`; an unsafe or unreachable owner is `blocked`.
6. Aggregate watcher results.
   - The lead monitor compares watcher cards against the dispatch ledger and
     user request.
   - Resolve conflicts or uncertainty by doing one direct read of the affected
     thread.
   - Do not let watcher summaries become proof of durable completion unless
     they cite commit, push/PR, deploy/build, validation, and tracker evidence
     when those are in scope.
7. Report status before acting when the next action is not obvious.
   - For simple user requests like "have it wrap up if clean", you may inspect
     and then send the wrap-up prompt if the ready criteria are met.
   - For ambiguous or risky states, report the classification and recommend the
     next move instead of guessing.
8. Send steering only when useful.
   - Use `send_message_to_thread` only when the permission mode is `steer` or
     `wrap`.
   - Send only concrete corrections, narrower scope, missing validation, or
     durable wrap-up instructions.
   - Do not send generic "status?" prompts unless the thread is waiting and a
     nudge is the requested action.
   - Keep mutation authority centralized in the lead monitor unless the user
     explicitly grants a watcher permission for one specific follow-up.
   - After sending material steering or wrap-up prompts, keep this turn open and
     monitor the affected lanes with `bounded-watch` or `run-to-terminal` unless
     the user clearly asked for prompt delivery only.
9. Poll boundedly.
   - For status-only checks, do one snapshot pass and stop unless the user asked
     to wait.
   - If the same request used `$dispatch` and `$monitor`, or the user says
     "subagent monitor", "watch", "keep monitoring", "constantly monitor", or
     "don't stop until the task agent is done", use watcher-backed
     `run-to-terminal` by default, not a parent-only snapshot or timed window.
   - After sending a wrap-up or steering prompt, default to at most 3 poll
     rounds per target, starting around 30 seconds and increasing only for known
     slow checks such as full tests, builds, deploys, or external services.
   - For `bounded-watch`, stop after about 10 minutes total unless the user
     explicitly asks for a longer watch.
   - For `run-to-terminal`, do not stop merely because the monitor has been open
     for a while. Stop only when every child is terminal, the user interrupts, or
     the system cannot continue the active turn.
   - Stop when the child is done, blocked, waiting for parent/user input, or
     still running after the requested `bounded-watch` window; report the latest
     state instead of silently looping.
   - Do not send the final response while watcher subagents are still running.
     Wait for or close them first, then report that monitoring is no longer
     active unless a persistence mechanism exists.

## Parent-Owned Lifecycle

For active orchestration, the parent thread owns the lifecycle:

1. Dispatch or identify child task sessions.
2. Start monitor watcher subagents, one per active child when possible.
3. Keep the parent turn open while watchers poll and report.
4. When a watcher reports `ready-to-wrap`, the lead monitor decides whether to
   send a wrap-up prompt, ask the user, or leave a handoff.
5. If the lead sends a steering prompt, either restart watcher coverage for that
   lane or state that this was a note-only handoff with no active monitoring.
6. If the user adds a new priority while a monitor is active, keep unrelated
   watcher lanes running unless the user explicitly cancels them. Add or steer
   the new lane in parallel, and report both lanes.
7. When every child is terminal, stop/close the watcher agents.
8. Aggregate watcher reports, verify any durable proof needed, then send the
   parent final answer.

Terminal child states for non-PR work are `durable-done`, `blocked`, `waiting`,
or `stale`. `running` and `idle-local` are not terminal for a
`run-to-terminal` monitor unless the user accepts a handoff.

For a PR owner, `stale` is non-terminal. Inspect first-party lifecycle and
either resume that same known-inactive task through the scheduled recovery
contract, preserve `waiting_for_bradley`, or classify unknown/unreachable state
as `blocked`. Use `orchestrate`'s shared `prDisposition` enum and action table;
do not invent a second terminal-state vocabulary for PR recovery.

## Watcher Subagents

Watcher agents are useful when a dispatch ledger has multiple active children.
Use them like a status room, not like extra implementers.

When watcher agents are spawned, record their ids in your notes and final
response. A watcher id is runtime evidence that fanout actually happened; a
ledger flag by itself is not.

Watcher prompt shape:

```text
You are MONITOR_WATCHER_<n>. Read-only monitor this Codex child thread:

Thread: <thread id>
Title/ticket: <title or ticket>
Mode: <snapshot | bounded-watch | run-to-terminal>
Ledger expectations:
- Repo/worktree: <path if known>
- Closeout policy: <policy>
- Expected validation: <commands/checks>
- Tracker policy: <policy>

Task:
1. Snapshot the recent child thread state.
2. If Mode is bounded-watch, keep polling this thread until it becomes
   actionable, the monitor window expires, or the lead monitor stops you. If
   Mode is run-to-terminal, keep polling until this child reaches a terminal
   state. Do not return after the first healthy running snapshot.
3. Include outputs only when needed for validation, diff, commit, push, deploy,
   or tracker proof.
4. Classify the state as one of: running, waiting, idle-local, ready-to-wrap,
   durable-done, blocked, stale.
5. Do not send messages to the child, edit files, commit, push, deploy, update
   trackers, or write the ledger.

Return exactly:
- thread:
- classification:
- worktreeState:
- trackerState:
- deliveryState:
- evidence:
- blocker:
- recommended_next_action:
- confidence:
```

If watcher subagents cannot access thread tools, the lead monitor should fetch
thread snapshots itself and may ask watchers to classify those snapshots.

## Dispatch Ledger

When a ledger path is provided, read it first and use it as the target list.
Treat the ledger as coordination metadata, not ground truth. Live thread state,
repo state, and tracker state win over stale ledger fields.

`monitoringRequested: true` only means someone asked for monitoring. It does not
prove watchers exist or that monitoring is still active. Prefer explicit fields
such as `monitoringMode`, `monitoringStatus`, `watcherAgentIds`, and
`lastMonitorAt` when present. Use `monitoringMode` for lifetime values:
`none`, `snapshot`, `bounded-watch`, `run-to-terminal`, or `persistent`. Use
`monitoringPermission` for values such as `status-only`, `steer`, or `wrap`.

Ledger files are read-only during status checks. Update a ledger only when the
user explicitly asks to refresh/write the ledger, or when the monitor request
clearly includes durable closeout bookkeeping.

If updating a ledger, write only compact status metadata and use an atomic write
pattern: write a temp file in the same directory, then rename it into place. Do
not store raw transcript text, secrets, environment values, or long command
output.

Useful status fields:

```json
{
  "threadId": "019...",
  "status": "ready-to-wrap",
  "monitoringMode": "run-to-terminal",
  "monitoringPermission": "status-only",
  "monitoringStatus": "stopped",
  "watcherAgentIds": ["019..."],
  "lastCheckedAt": "2026-06-20T07:12:00Z",
  "worktreeState": "clean-diff",
  "trackerState": "blocked-by-children",
  "deliveryState": "local-only",
  "prOwner": null,
  "evidence": ["validation passed", "no commit yet"],
  "recommendedNextAction": "send wrap-up prompt"
}
```

## Ready-To-Wrap Criteria

Before asking a child to commit, push, deploy, or close a tracker, verify from
the thread state that:

- The patch or plan is narrow enough to understand.
- Validation passed or the remaining failure is clearly unrelated and accepted.
- Non-trivial code or risky decisions had critique/review, or the child explains
  why critique is not applicable.
- No unexpected tracked files, dependency churn, generated artifacts, or repo
  session logs are present unless explicitly expected.
- Tracker closeout is in scope for this project and this user request.
- Deploy/build steps are known when runtime boundaries are touched.
- Parent-ticket blockers are resolved. Do not close an umbrella or parent
  tracker merely because its own child thread produced a clean local slice.

If any item is uncertain, ask the child for a focused status or leave the
tracker active with a handoff note.

## Worktree Proof

For `ready-to-wrap` or `durable-done` decisions, inspect live state when the
child thread exposes a `cwd` or worktree path and doing so will not interfere
with an active command.

Useful read-only checks:

```sh
git -C <worktree> status --short --branch
git -C <worktree> diff --stat
git -C <worktree> log --oneline -5
```

Use thread output for command/deploy/tracker evidence, but do not rely on thread
text alone when the local worktree is available and the decision affects commit,
push, deploy, or tracker closeout.

## Wrap-Up Prompt Template

Use a concrete prompt like this when the user asks for durable closeout:

```text
Clean and wrap up <ticket/title> if the current patch is still as described.

Please do the durable closeout now:
1. Re-check the worktree status, branch, and diff. Stop if unrelated or
   unexpected tracked changes exist.
2. Bring the branch up to date with current <base branch> if needed, preserving
   other work.
3. Re-run the necessary validation for the final tree: <commands>.
4. Run the critique/review gate if non-trivial work changed since the last
   review, or explain why it is already satisfied.
5. Stage exact intended files only, inspect the cached diff, and commit with a
   concise message.
6. Merge/push/open PR only as requested: <delivery policy>.
7. Deploy/build only if required: <deploy/build commands and target>.
8. Update <tracker> only if durable delivery succeeds. Otherwise leave it active
   with a handoff comment.

Report commit hash, push/PR proof, deploy/build proof, validation, tracker
state, and residual risks. Do not broaden scope.
```

## Merge Captain

When multiple child lanes converge on shared branches, the parent lead should be
the merge captain unless a child was explicitly granted merge authority. Children
may critique, validate, stage, commit, or prepare branches when allowed, but the
parent should sequence merges into shared bases such as `master`, `next`, or
`release`, run integrated validation after each meaningful merge, and verify the
branch that must remain untouched really stayed untouched.

Do not let two children race the same shared branch. If one child must wait for
another branch to land first, record that as `trackerState: active` or
`deliveryState: local-only` until the parent performs the merge and proof checks.

## Post-Turn Rollout Monitoring

Watcher subagents end with the parent turn. For after-the-fact rollout watching,
use an explicit automation or thread wakeup when the user asks for ongoing checks.
Keep these monitors short-lived, read-only, and scoped to concrete signals such
as production logs, Sentry issues, Axiom queries, Convex errors, build health, or
specific API paths touched by the rollout.

When the originating task must own that follow-up lifecycle, stop this active
watcher flow and load `codex-automation`'s
`task-owned-follow-up-monitor/v1` contract. A task-owned heartbeat must bind the
exact owner task and host, deduplicate before creation, read back after every
mutation, and return a versioned receipt. Do not adopt an operator-created
standing monitor or describe the current watcher lane as that heartbeat.

Template:

```text
Create a short-lived read-only rollout monitor for <ticket/change>.

Duration: <count/window>. Schedule: <time/timezone>.
Repo/cwd: <path>.
Signals:
- <service/log/query/error family>
- <specific functions/routes/build ids>

Rules:
- Do not edit code, deploy, push, merge, or close trackers.
- Report suspicious findings with timestamps, affected paths, counts, and
  whether they look new since the rollout.
- If nothing is suspicious, report "no findings" and the checked window.
```

## Steering Prompts

For a blocked or drifting child, send one narrow correction:

```text
Pause broad work. Return only:
- current branch/worktree:
- changed files:
- last validation command and result:
- blocker:
- the smallest next step you recommend:
```

```text
Stay read-only. Do not edit, commit, push, deploy, or close the tracker. Inspect
only <files/area> and report whether the current patch is safe to wrap.
```

## Final Response Shape

Keep the final compact:

```text
Checked two child threads:

- `HAPPY-145`: durable-done. Commit `<hash>` pushed, production deploy passed,
  Linear moved to Done.
- `HAPPY-149`: blocked. Validation passed, but push failed because `<reason>`;
  handoff note posted and tracker left active.

- Status axes:
  - worktreeState: `<state>`
  - trackerState: `<state>`
  - deliveryState: `<state>`

Watcher lanes used: 2. Both watcher agents reported terminal states and were
closed before this final.

Monitoring mode: `run-to-terminal`.
Watcher agent ids: `<id-1>`, `<id-2>`.
Still monitoring after this answer: no.
```

## Guardrails

- Do not create child sessions; use `$dispatch` for that.
- Default to status-only. Do not send child prompts or write ledgers unless the
  user asked for steering, wrap-up, durable closeout, or ledger refresh.
- Do not monitor without terminal criteria. Long active watches must still have
  clear stop states and periodic progress updates.
- Do not satisfy a dispatch+monitor request with only parent-thread
  `read_thread` calls when watcher subagent tools are available.
- Do not send a final answer from a `run-to-terminal` parent while any child is
  still `running` or `idle-local` unless the user accepts that handoff.
- Do not close an unrelated active watcher merely because the user adds another
  task, closeout, or deployment request. Keep it running or restart it unless
  the user explicitly cancels that monitor.
- Do not imply monitoring continues after the final answer unless an explicit
  automation or thread wakeup exists and you name it.
- Do not treat `monitoringRequested` in a ledger as active monitoring.
- Do not claim durable completion from a child summary alone; look for commit,
  push/PR, deploy/build, validation, and tracker proof when those are in scope.
- Do not close trackers unless the user asked for closeout and durable proof is
  present.
- Do not let multiple watcher agents send competing prompts to the same child.
- Do not paste raw transcript text, secrets, or sensitive env values.
