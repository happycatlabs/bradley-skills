---
name: inspect-codex-session
description: Inspect local or connected-remote Codex Desktop or CLI tasks, threads, sessions, and rollout transcripts to find current work, reconstruct conversation, determine lifecycle state, summarize blockers, monitor progress, or recover handoff context. Use when a user gives a Codex task/thread/session id, asks what another Codex agent is doing, wants the latest or final message, asks whether a task is running or blocked, or needs read-only evidence from Codex app tools or host-local JSONL/log storage. Supports Codex-specific lifecycle semantics plus conservative fallbacks for other agent harnesses; interact with a task only when explicitly requested.
---

# Inspect Codex Session

Inspect another Codex task read-only and report the smallest useful operational briefing. Use the bundled helper instead of grepping raw rollout files first; ids and copied context frequently create false-positive text matches.

## Fast path

Run commands from this skill directory so the path works in any installation. If your harness resets the shell working directory between commands (Claude Code does), invoke the helper by absolute path instead — the skill's base directory is announced when the skill loads:

```bash
python3 <skill-base-dir>/scripts/inspect_codex_session.py --query 01900000 --conversation --current-turn
```

```bash
# Best default for a supplied task/thread/session id
python3 scripts/inspect_codex_session.py --query 01900000 --conversation --current-turn

# Stable machine-readable briefing for an agent or monitor
python3 scripts/inspect_codex_session.py --query 01900000 --json --conversation --current-turn

# Exact messages and transcript-local search
python3 scripts/inspect_codex_session.py --query 01900000 --last-message final
python3 scripts/inspect_codex_session.py --query 01900000 --last-message user
python3 scripts/inspect_codex_session.py --query 01900000 --search "context.unsubscribeUrl" --full

# Discovery and repeated checks
python3 scripts/inspect_codex_session.py --last --conversation --current-turn
python3 scripts/inspect_codex_session.py --list --limit 20
python3 scripts/inspect_codex_session.py --query 01900000 --since 2026-07-11T09:36:37Z --json
```

Use `--conversation`, not `--role user,assistant`, when the goal is the human-visible exchange. Role filtering also includes assistant reasoning because reasoning has the assistant role. `--current-turn` begins at the latest `task_started` event, or at the latest user message when lifecycle events are unavailable.

Known Codex Desktop ambient browser context is removed from displayed user messages by default. Add `--raw-context` only when the wrapper itself is evidence. `--last-message` always returns full text; choose `final` to avoid confusing interim commentary with the completed answer.

## State contract

Trust state evidence in this order:

1. `task_started`, `task_complete`, or `turn_aborted` lifecycle events.
2. A user message newer than the latest lifecycle boundary.
3. Recent file/log activity and trailing tool/message roles for formats without lifecycle events.

Do not call a task running merely because its transcript was written recently. A recent `task_complete` means the turn is complete and waiting for the user. Conversely, an assistant commentary message does not mean an active turn is finished.

In JSON output:

- `state` and `state_reason` provide the interpretation and evidence.
- `state_authority` distinguishes explicit `lifecycle` evidence from a `heuristic` fallback.
- `turn_active` answers whether an agent appears to own an active turn.
- `active_recently` only describes transcript recency; never substitute it for `turn_active`.
- `latest_lifecycle` exposes the authoritative event, timestamp, and turn id when available.
- `indexed_title` is the saved sidebar/index title and may be stale.
- `current_request` is the latest cleaned user request and usually describes the real current work better than the title.
- `phase` distinguishes assistant `commentary` from `final_answer` in recent events.
- `latest_final_answer` provides direct programmatic access without scanning recent events.
- `delegated_tasks` lists app-managed child tasks whose `codex_delegation` points back to an
  ephemeral side chat. Each entry includes the child id plus any observed host, status, title,
  cwd, and update timestamp.

Recheck state immediately before editing, committing, cleaning, or otherwise touching a task's cwd. If `turn_active` is true, assume the other agent can write at any moment and keep the inspection read-only.

## Codex-specific guidance

Codex Desktop calls the user-visible object a **task**. APIs may call it a **thread**, the CLI commonly calls it a **session**, and local storage calls its append-only history a **rollout**. Treat these as layers of the same object unless evidence shows a fork or worker lane. Use “task” in user-facing reports and preserve the supplied id.

When Codex has first-party task/thread tools:

1. Prefer `read_thread` or the equivalent for live app-managed inspection when it exposes the needed history and state.
2. Use this skill for local transcript truth, exact lifecycle evidence, older/archived history, CLI workers, or when first-party tools are unavailable.
3. Prefer `send_message_to_thread` or its equivalent when the user explicitly asks to contact a task.
4. Fall back to `codex resume` only when no first-party messaging tool is available.

For Codex-to-Codex coordination, start with:

```bash
python3 scripts/inspect_codex_session.py --query <id> --json --conversation --current-turn
```

Read `state`, `turn_active`, `current_request`, `latest_lifecycle`, and `recent_events` before inspecting raw JSONL. A stale indexed title is context, not a resolver failure. If a task has just completed, report completion even when the file age is only seconds.

## Session ids from another machine

Treat the machine that owns the task as part of its identity. The helper searches only files visible to the process running it, so a valid remote session id will not resolve through the observer's local `$CODEX_HOME` unless the remote home is mounted locally. A local miss means **not visible from this host**, not **session does not exist**.

When Codex first-party tools can see connected remote hosts:

1. Use `list_threads` without a query first to discover recent tasks and their host ids. Add a query only when the supplied id or title is old enough to be absent from the recent results.
2. Call `read_thread` with the full thread id and the owning `hostId`. Prefer the host-qualified result over a repo-path match because the same project may be registered on multiple machines.
3. If the task does not resolve, check which hosts are currently connected. Report the owning host as disconnected, unavailable, or still unknown; do not fall back to a local non-match as proof that the id is invalid.

When first-party remote tools are unavailable but SSH access is already configured and authorized, execute the helper on the owning machine:

```bash
ssh <host> 'python3 <remote-skill-base-dir>/scripts/inspect_codex_session.py --query <full-id> --json --conversation --current-turn'
```

Resolve the skill path on that machine instead of assuming the local installation path exists there. `--home` accepts a filesystem path visible to the process running the helper; it is not an SSH host selector. It is appropriate for a mounted or copied Codex home, but prefer remote execution over copying transcript or SQLite state solely for inspection.

Use the full id across hosts. Prefixes that are unique on one machine may be ambiguous when several hosts are searched. Keep remote inspection read-only: do not hand off, move, or resume a task merely to make it locally inspectable. If the owner machine cannot be determined, ask which machine produced the id or ask the user to reconnect that host.

## Observing from Claude Code (and other non-Codex harnesses)

When the observer is Claude Code rather than Codex, the object being inspected is foreign — do not map Codex semantics onto your own session model:

- **The helper script is the only path.** `read_thread` and `send_message_to_thread` are Codex Desktop tools; Claude never has them. Skip the first-party decision ladder in the section above and go straight to the script.
- **Codex lifecycle state outranks your instincts.** Claude's own session inspection is recency-heuristic, so Claude observers tend to reason from file age. Here that is wrong: when `state_authority` is `lifecycle`, `turn_active` and `state` are authoritative even if the rollout was written seconds ago. Only fall back to age-based reasoning when the output explicitly says `heuristic`.
- **Vocabulary is Codex's, not yours.** A Codex "turn" spans `task_started` → `task_complete` and may contain many `commentary` messages; do not report an interim commentary as the answer the way a Claude assistant message might be. Use `--last-message final` for the completed answer.
- **`--last` is safe from Claude.** Unlike inspecting your own harness's transcripts, you never appear in `~/.codex`, so the newest rollout is genuinely the newest Codex task — no self-inspection trap.
- **Messaging a task needs the non-interactive form.** Plain `codex resume <id> "prompt"` opens a TUI and will hang a non-interactive shell. From Claude, use the `codex exec resume` form in the Interaction boundary section (keep the `< /dev/null`), and account for your shell timeout: a resumed turn can easily exceed a 2-minute default, so raise the timeout or run it in the background and read the `-o` output file when it exits. If the user wants a live interactive resume, have them run `codex resume <id>` themselves.
- `$CODEX_HOME` is typically inherited by Claude's shell from the user profile; the helper already falls back to `~/.codex` when it is not.

Cursor-specific observations (verified 2026-07-11):

- Cursor's shell ran `/bin/zsh` and persisted cwd across calls. After a call
  changed into a scratch project, a helper invocation without an explicit
  working directory also started there. The absolute helper path worked from
  that scratch cwd.
- Cursor's native parallel tool kept helper outputs separate. Five concurrent
  absolute-path invocations against fresh CLI sessions all exited 0 in
  0.55-0.66s and reported lifecycle-authoritative `turn complete` state,
  including the resumed session's current turn.

## Cross-harness guidance

Keep the observer workflow portable:

- Resolve from `$CODEX_HOME` when set, otherwise `~/.codex`; use `--home` for another installation visible on the same filesystem. For another machine, use connected-host tools or run the helper on that host.
- Accept full ids, unique id prefixes, indexed title substrings, or rollout paths through `--query`.
- Normal tasks live under `sessions/**/rollout-*.jsonl`; archived tasks under `archived_sessions/`.
- Ephemeral side chats may exist only in `logs_2.sqlite`; the helper automatically falls back there when an id does not resolve to a rollout.
- Side-chat app tool responses are stored as submissions too. The helper keeps only
  `op: UserInput` records in the user conversation, classifies `DynamicToolResponse` records as
  tool output, and extracts explicitly linked child tasks into `delegated_tasks`.
- With `--current-turn`, a side chat without lifecycle events still begins at its latest real
  user input. Use the always-present `delegated_tasks` summary to resolve references such as
  "that session"; inspect the selected child through `read_thread` or the helper before acting.
- `codex exec --ephemeral` workers leave no rollout. If neither transcript nor log fallback resolves a known worker id, check whether it was intentionally ephemeral.
- Older and third-party-emitted transcripts may lack Codex lifecycle events. Treat the resulting recency-based state as explicitly heuristic.
- Prefer `--json` for programmatic consumers. Human output labels the object “Task,” while backward-compatible JSON retains `id` and `thread_name` alongside `task_id` and `indexed_title`.

Do not assume this skill's absolute installation path. It may be mounted under `.agents`, `.claude`, `.codex`, or another harness-specific root.

## Workflow

1. If the id came from another machine, identify the owning host first. Then resolve the supplied id on that host; use `--last` only when the user clearly means that host's newest task.
2. Run `--conversation --current-turn` to understand the latest exchange.
3. Use `--last-message final`, `--search`, or unfiltered recent events only when exact evidence is needed.
4. Report the task id/title, lifecycle state, last activity, current request, latest useful exchange, blockers, and the next safe action.
5. Separate observed transcript facts from inference. Say when state is heuristic because lifecycle data is absent.
6. Keep inspection read-only unless the user explicitly asks to send a prompt.

For repeated checks, pass the prior `last_activity` value to `--since`. This limits displayed events, though the helper still scans the transcript to reconstruct authoritative lifecycle state.

## Interaction boundary

Never edit transcript JSONL or SQLite log files; they are evidence, not an inbox.

If the user explicitly asks to send a prompt and no first-party task messaging tool is available:

```bash
codex resume <SESSION_ID_OR_THREAD_NAME> "your prompt"

# Non-interactive worker follow-up; resume needs sandbox configuration via -c
(
  CODEX_RESUME_DIR="$(mktemp -d "${TMPDIR:-/tmp}/codex-resume.XXXXXX")" || exit 1
  chmod 700 "$CODEX_RESUME_DIR"
  CODEX_RESUME_OUTPUT="$CODEX_RESUME_DIR/output.md"
  cleanup_codex_resume() {
    unlink "$CODEX_RESUME_OUTPUT" 2>/dev/null || true
    rmdir -- "$CODEX_RESUME_DIR" 2>/dev/null || true
  }
  trap cleanup_codex_resume EXIT

  codex -a never exec resume <SESSION_ID> \
    -c sandbox_mode="read-only" \
    -o "$CODEX_RESUME_OUTPUT" "your prompt" < /dev/null
  CODEX_EXIT=$?
  [[ -s "$CODEX_RESUME_OUTPUT" ]] && cat "$CODEX_RESUME_OUTPUT"
  exit "$CODEX_EXIT"
)
```

Before sending, state the selected task and prompt unless the user already specified both unambiguously.

## Reporting shape

```text
Task: <indexed title> (<id>)
Host: <local or remote host name/id>
State: <state> — <brief evidence>
Last activity: <timestamp> (<age>)
Current request: <latest actual request>
Latest useful context:
- User: ...
- Assistant [commentary/final]: ...
Blocker or next safe action: ...
```

Avoid transcript dumps. Rollouts can contain sensitive prompts, environment details, and large tool outputs.

## Validation

After changing the helper, run:

```bash
python3 scripts/test_inspect_codex_session.py
python3 -m py_compile scripts/inspect_codex_session.py
```
