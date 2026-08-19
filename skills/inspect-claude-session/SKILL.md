---
name: inspect-claude-session
description: Inspect local Claude Code session transcripts when the user wants to find, summarize, monitor, or wait on another Claude session. Use for requests like "inspect Claude session", "what is this Claude agent doing?", "find the latest Claude session", "is Claude blocked?", "Codex is waiting on a Claude agent", or when coordinating work by reading Claude session JSONL files under ~/.claude. Read-only by default.
metadata:
  short-description: Inspect local Claude session transcripts
---

# Inspect Claude Session

Read local Claude Code transcripts and summarize what another Claude session or subagent is doing. This skill is for observation: find the session, inspect recent messages/events, identify likely blocked/waiting states, and report enough context for another agent to continue.

## Quick Start

Run the bundled script from this skill's base directory (the directory shown when the skill loads). It is installed under both `~/.claude/skills/inspect-claude-session` and `~/.agents/skills/inspect-claude-session` — either path works:

```bash
python3 scripts/inspect_claude_session.py --last
python3 scripts/inspect_claude_session.py --query "title, prompt, project, or session id"
python3 scripts/inspect_claude_session.py --query 86d3536f --limit 12
python3 scripts/inspect_claude_session.py --query 86d3536f --role user,assistant --limit 12
python3 scripts/inspect_claude_session.py --query 86d3536f --last-message assistant
python3 scripts/inspect_claude_session.py --query 86d3536f --search "blocked" --full
python3 scripts/inspect_claude_session.py --list --limit 20
```

Key flags:

- `--role user,assistant` — show just the conversation, without tool/hook/attachment noise. The fastest way to reconstruct the recent back-and-forth. Valid roles: `user`, `assistant`, `tool`, `system` (pure tool-use and tool-result messages are reclassified as role `tool` even though the raw transcript stores them under user/assistant).
- `--last-message assistant|user|any` — print the latest full message verbatim. Use this for exact wording; do not hand-parse JSONL.
- `--since <ISO timestamp>` — only show events newer than a timestamp. For repeated checks ("check that session again"), pass the `Last activity` value from your previous run to see only what changed.
- `--full` — disable truncation in summary/search views. `--max-chars N` adjusts the per-event budget instead (default 600).
- `--json` — machine-readable output everywhere, including `state`, `age_seconds`, and `active_recently` for programmatic liveness checks.
- `--search "<text>"` — find prior context anywhere in the transcript. Combines with `--role`, `--since`, `--full`.
- `--include-subagents` — also consider `subagents/agent-*.jsonl` files when listing or resolving.

Top-level session views automatically summarize companion Agent/Workflow
artifacts below `<session-id>/subagents/`. This is deliberately independent of
`--include-subagents`: that flag controls session selection, while child
activity prevents an idle parent transcript from hiding live background work.
On Claude 2.1.207+, the helper also consults the public
`claude agents --json --all` registry. A matching native `busy`, `blocked`, or
`done` state takes precedence over transcript-age heuristics. Set
`INSPECT_CLAUDE_SKIP_NATIVE_AGENTS=1` only for isolated fixture tests or when
the CLI itself is unavailable/broken.

## Liveness: read the age before acting

Every view reports `Last activity` with a relative age, computed from the newer of the last transcript timestamp and the file mtime. This is the single most important field:

- **Age within ~2 minutes → the session is live.** The state will read `likely running`. Treat the other agent as actively writing: do not edit, commit, or clean up files in its working directory, and expect your snapshot of its repo state to go stale immediately. Claude Code writes interim assistant messages mid-turn, so "the last message is from the assistant" does NOT mean the turn is over.
- **Idle for minutes+ with a final assistant message → likely waiting or complete.** Safe to review its output; report the state heuristic and the latest message.
- **Idle parent plus live child activity → likely running background work.**
  Claude Desktop/CLI workflows can outlive the parent turn. Inspect the printed
  `Child activity` section; a workflow with started lanes but no terminal result
  is reported as unfinished/stalled rather than complete.
- **Idle with a trailing attachment/hook event → possibly stopped mid-turn.** The session may have been killed or hit an error; say so rather than guessing.

The state line is a heuristic, not ground truth. When the decision matters (e.g. "is it safe to modify these files?"), check the age again right before acting. If you are inspecting from within a Claude session yourself, note that your own session's transcript is always the most recently modified — `--last` will usually resolve to you; prefer an explicit `--query`.

Claude 2.1.207 added a native background lifecycle that is more authoritative
than transcript scraping:

```bash
claude --bg --name my-lane "prompt"
claude agents --json --all
claude logs <short-id>   # terminal-rendered ANSI output, not clean JSON
claude attach <short-id> # requires a TTY
claude stop <short-id>
```

`--bg` prints a short native agent id immediately; the registry also exposes
the full resumable `sessionId`, cwd, kind, status, and state. Prefer the JSON
registry for monitoring. `claude logs` replays terminal control sequences even
when stdout is redirected, so it is for humans, not parsers.

## Workflow

1. Resolve the target session:
   - Prefer an explicit session id, JSONL path, title, project, or prompt substring from the user. Prefixes of the id work.
   - If none is supplied, use `--last` for the most recently modified transcript (but see the self-inspection caveat above).
   - Use `--list` when the user needs to choose among candidates; it shows per-session ages.

2. Inspect the transcript:
   - Read from `$CLAUDE_HOME` if set, otherwise `~/.claude` (`--home` overrides).
   - Main sessions normally live under `projects/<project-key>/<session-id>.jsonl`.
   - Subagent logs can live under `projects/<project-key>/<parent-session>/subagents/agent-*.jsonl`.
   - Workflow agents live under
     `projects/<project-key>/<parent-session>/subagents/workflows/wf_*/`, with
     lane starts/results in `journal.jsonl`; a terminal aggregate is normally
     written to `<parent-session>/workflows/<workflow-id>.json`. The helper
     correlates these automatically for top-level session views.
   - Worker lanes dispatched via `claude -p` (see the `claude` skill) also
     write transcripts here, keyed by the lane's cwd: a `-w <name>` worktree
     lane files under the project key for `.claude/worktrees/<name>`, NOT the
     repo root — resolve by session id (`--query <id>`), which the
     dispatching agent should have captured, rather than by project path.
   - A lane run with `--no-session-persistence` leaves NO transcript; if a
     known-dispatched session id resolves nowhere, check for that flag before
     concluding the lane never ran.
   - Start with the default summary, then `--role user,assistant` for the conversation arc, then `--last-message`/`--search` for exact text. Do not pipe transcript tails into ad hoc JSON scripts unless the helper cannot answer the question.
   - Do not include `thinking` blocks or signatures in output.

3. Report concisely:
   - Session id, title, project, cwd, path, last activity with age.
   - Heuristic state: likely running, likely waiting for user, blocked, likely waiting or complete, or unknown.
   - The recent user/assistant exchange that explains what it is doing and why.
   - Any explicit blocker/request markers found after the latest user message.

4. Monitor with `--since` when asked to check repeatedly:
   - Record `Last activity` from each run; pass it as `--since` on the next run to see only new events.
   - For scripted polling, use `--json` and branch on `active_recently` / `age_seconds`.

5. Keep inspection read-only. Do not edit Claude JSONL files.

## Validation

After changing the helper, run:

```bash
python3 scripts/test_inspect_claude_session.py
python3 -m py_compile scripts/inspect_claude_session.py
```

## Interaction Boundary

Transcripts are logs, not an inbox. If the user explicitly wants to send a
prompt into an inspected session, use the CLI:

```bash
echo "your prompt" | claude -p --resume <SESSION_ID> --output-format json
```

Match the original lane's permission flags (`--permission-mode`,
`--disallowedTools`) when resuming a worker lane — resume does not remember
them. Before sending, tell the user which session you selected and what you
will send, unless they already specified both unambiguously.

## Output Style

For a waiting/coordination use case, prefer:

```text
Session: <title> (<id>)
State: likely running / likely waiting for user / blocked / likely waiting or complete / unknown
Last activity: <timestamp> (<age>)
Latest useful context:
- User: ...
- Assistant: ...
Next suggested action: ...
```

Avoid dumping full transcripts unless the user asks. Session files can contain sensitive tool output, hook output, prompt content, and instructions.
