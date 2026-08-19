---
name: claude
description: Dispatch Claude Code (`claude -p`) as a subagent — one-shot consults for an independent second opinion, scoped worker lanes (implementation in a worktree, read-only research, structured extraction), and resumed follow-ups. Use when the user invokes `/claude`, says "ask Claude" / "use claude" / "delegate to claude", when an orchestration plan routes a lane to Claude, or when a lane benefits from Claude's skills/CLAUDE.md/subagent ecosystem. Supports resume for follow-up turns in the same session.
---

# Claude

One gateway for using the local Claude Code CLI from another agent (typically
a Codex host), in two modes:

- **Consult** — a narrow advisory question: second opinion, critique, review,
  debugging hypothesis. Claude's answer is useful input, not authority.
- **Worker lane** — a scoped delegated task inside an orchestrated workflow:
  implementation in an isolated worktree, read-only research, structured
  extraction. Pair with the `orchestrate` skill's lane discipline (ownership,
  evidence contract, friction log, model-feedback logging).

## When to route a lane to Claude (vs keeping it on Codex)

Good fits:

- Repo-scale reasoning and multi-file implementation with judgment calls —
  strongest with project context loaded (CLAUDE.md, project skills, memory).
- Lanes that benefit from Claude's ecosystem: project skills (e.g. repo dev
  skills, `agent-browser` for browser work), CLAUDE.md conventions,
  persistent memory, and Claude's own subagent fan-out (Agent tool, plus
  `--agents` to define custom ones inline).
- Independent second-provider review (different failure modes than Codex
  reviewing Codex).
- Structured extraction where `--json-schema` guarantees a parseable object.
- Cost-tiered work: `--model haiku|sonnet` + `--effort low` make cheap
  mechanical lanes; `fable`/`opus` for hard reasoning.

Keep on the host: lanes needing the current conversation's context (Claude
starts cold each dispatch), final integration owned by the lead, and
product-judgment calls that belong to the user.

## Machine facts that bite (verified on claude 2.1.207)

- **Native background lifecycle:** `claude --bg --name <name> "prompt"`
  returns in under a second with a short agent id. Monitor with `claude agents
  --json --all`; it reports background and interactive (Desktop/TUI) sessions
  with the full `sessionId`, cwd, kind, status, and state. `claude logs
  <short-id>` emits ANSI terminal replay, not parseable JSON; `claude attach
  <short-id>` requires a TTY; `claude stop <short-id>` stops the process but
  preserves its conversation.

- **Default `-p` mode is NOT read-only** — file edits are permitted. For a
  read-only lane use `--permission-mode plan` (verified: reads work, Edit is
  blocked). For write lanes use `--permission-mode acceptEdits` (verified:
  edits and workspace-mutating commands like mkdir run without prompts).
  Plan mode can still decline a harmless shell command such as `sleep` because
  it is not part of planning; do not use synthetic sleeps as proof that plan
  mode's Bash surface is available.
- **Variadic-flag trap:** `--allowedTools`, `--disallowedTools`, `--tools`,
  `--add-dir` are space/comma-variadic and will SWALLOW a positional prompt
  that follows them (symptom: `Permission deny rule "..." matches no known
  tool`). Put the prompt before variadic flags, or pass it via stdin.
- `--disallowedTools "Bash(git commit*)"` hard-blocks matching commands even
  inside compound commands (verified: `git add ... && git commit ...` denied
  atomically). Use it to make no-commit lanes structural, not just prompted.
- `-w <name>` works with `-p`: creates `.claude/worktrees/<name>` on branch
  `worktree-<name>` inside the repo and runs the session there. Clean up
  with `git worktree remove` after integrating.
- `--dangerously-skip-permissions` is a last resort: spawning it from
  another agent can itself be blocked by safety classifiers, and
  `acceptEdits` + tool scoping covers implementation lanes anyway. Do not
  make it the default lane shape.
- `--output-format json` returns one object: `result` (final text),
  `session_id` (the resume handle), `is_error`, `num_turns`,
  `total_cost_usd`, `usage`. With `--json-schema '<schema>'` the validated
  object lands in `structured_output`.
- `--session-id <uuid>` lets the orchestrator pre-choose the session id (no
  output parsing needed); `--fork-session` branches a resumed session.
- `--no-session-persistence` BREAKS resume — never use it for lanes that
  might get follow-ups.
- `-p` skips the workspace trust dialog — only point lanes at directories
  you trust. Invalid settings files are silently ignored in print mode.
- A trivial consult costs roughly $0.10 in API terms; don't burn a lane on
  one-line lookups. Bound cost with a narrow prompt, `--model sonnet`, or
  `--effort` before reaching for `--max-budget-usd` (a lane killed by
  `error_max_budget_usd` is not a completed review).
- Context modes: `--safe-mode` = normal auth, no customizations (no
  CLAUDE.md/skills/hooks/MCP — deterministic, good for consults);
  `--bare` = same but auth strictly via ANTHROPIC_API_KEY; project-aware
  (neither flag) = full ecosystem, required when the lane should use project
  skills like `agent-browser` or repo dev conventions.

## Execution model (from the host agent)

- Run `claude -p` as a FOREGROUND shell command with a long timeout; it can
  take minutes on real questions. Do not poll. For worker lanes redirect the
  JSON to a file; for quick consults reading the wrapper's stdout directly
  is fine.
- For an intentionally detached long-running lane, use native `--bg` instead
  of shell `&`, `nohup`, or process polling. Capture the short id at launch and
  the full resume id from `claude agents --json --all`. Native background
  sessions survive the host shell call returning and remain visible across
  Codex Desktop turns.
- When dispatching FROM Codex: `claude -p` works inside a plain
  `workspace-write` exec sandbox (verified) — no elevated sandbox needed,
  unlike browser lanes.
- Pass long prompts via a heredoc or another non-interactive stdin source that
  reaches EOF in the same foreground shell call. The wrapper reads stdin until
  EOF. Do not start it in a PTY and try to finish the prompt later with
  `write_stdin` plus a literal Ctrl-D; a PTY can echo that control character
  instead of closing stdin, leaving the wrapper blocked in `sys.stdin.read()`.
- Capture `session_id` from the JSON output (or pre-set it with
  `--session-id`) and report it with the lane result — that's the follow-up
  handle.
- Give Claude a self-contained brief: it does not see the host conversation.
  Include the goal, relevant paths/snippets/command output, what you already
  ruled out, and the answer shape you want. Do not send secrets.

## Mode 1 — Consult

The wrapper handles mode selection, the advisory system prompt, and output
normalization:

```bash
python3 ~/.agents/skills/claude/scripts/ask_claude.py --cwd "$PWD" <<'PROMPT'
We are considering extracting auth rate limiting into a shared package.
Review the tradeoffs and identify the main risks. Do not modify files.
PROMPT
```

It auto-selects `--bare` when `ANTHROPIC_API_KEY` is set, else `--safe-mode`,
and prints normalized JSON with `result`, `session_id`, and cost metadata.
The wrapper runs the user's default model (fable) — right for real
consults; for quick factual checks pass `--model sonnet --effort low`
instead of paying frontier prices for one sentence.
Useful wrapper flags: `--project` (full project context), `--schema
<json-or-path>` (structured output), `--model` / `--effort`, `--resume <id>`,
`--continue-latest`, `--session-id <uuid>`, `--budget <usd>` (only for
deliberately capped smoke checks), `--dry-run` (print the claude command).

If the wrapper returns an authentication-looking error, do not report that the
user is logged out from that result alone. Verify the installed binary and real
CLI state first:

```bash
command -v claude
claude auth status
claude -p 'Reply only with OK.' --output-format json --model sonnet --effort low
```

When `auth status` says `loggedIn: true` and the direct non-interactive smoke
works, classify the wrapper failure as an invocation or wrapper-path failure.
Inspect `ask_claude.py --dry-run`, rerun once with a foreground heredoc, and
preserve the exact failing command/output. Never turn a lane error into a claim
about the user's account without this verification.

## Mode 2 — Worker lane

Raw CLI, composed per the `orchestrate` skill (goal, owned scope, forbidden
files, validation, output contract, friction log). Pick the permission tier
to match the lane:

- **Read-only research/review lane:**

  ```bash
  echo "$PROMPT" | claude -p --permission-mode plan \
    --output-format json > "$OUT" 2> "$ERR"
  ```

- **Implementation lane** — isolated worktree, commits structurally blocked:

  ```bash
  echo "$PROMPT" | claude -p -w "$LANE_NAME" \
    --permission-mode acceptEdits \
    --disallowedTools "Bash(git commit*)" "Bash(git push*)" \
    --output-format json > "$OUT" 2> "$ERR"
  ```

  Run from the target repo root; the lane works in
  `.claude/worktrees/$LANE_NAME`. The lead inspects the diff there,
  integrates, and removes the worktree. Alternatively `-C`-style: cd to an
  existing worktree you created and omit `-w`.
- **Structured extraction lane:** add
  `--json-schema "$(cat schema.json)"` and read `.structured_output` from
  the JSON result.
- **Browser lane:** Claude drives browsers via the `agent-browser` CLI —
  requires project-aware mode (no `--safe-mode`, which disables skills) or
  an explicit instruction to run `agent-browser` commands directly. Needs a
  logged-in GUI session. Reuse the hypothesis-first briefing pattern from
  `orchestrate/playbooks/local-browser-verification.md`; one browser lane at
  a time.
- **Model/effort routing:** `--model haiku|sonnet` + `--effort low` for
  mechanical lanes; `--model fable` (or the user default) for hard
  reasoning, review, and integration-adjacent work. `--fallback-model` adds
  overload resilience for long unattended lanes.
- **Internal fan-out:** Claude has its own Agent tool and can spawn
  subagents; `--agents '<json>'` defines custom ones for the session. Say
  explicitly whether fan-out is allowed (default for orchestrated lanes:
  no — keeps evidence auditable).

Parallelism: multiple `claude -p` lanes are fine when each owns its own
worktree/directory; never two write lanes in one checkout; one browser lane
at a time; watch aggregate cost (each lane is a full Claude session).

## Native background lanes (2.1.207+)

Use this when the caller explicitly wants a detached agent that can keep
running after the current shell/tool call returns:

```bash
claude --bg \
  --name "lane-auth-review" \
  --permission-mode plan \
  --model haiku \
  --effort low \
  "Review auth boundaries. Do not modify files."

claude agents --json --all
```

Launch output looks like `backgrounded · 4b60bc74 · lane-auth-review` and
prints the `logs`, `attach`, and `stop` commands. For automation, do not parse
`claude logs`: it replays the full terminal UI with control sequences even to
redirected stdout. Use the JSON registry for lifecycle and the
`inspect-claude-session` helper (full `sessionId`) for transcript content and
child workflows.

Observed native states:

- interactive `status: busy` — a Desktop/TUI session is actively working;
- interactive `status: idle` — the terminal session is open but waiting;
- background `status: idle, state: done` — the turn finished and can resume;
- background `state: blocked` — intervention is needed.

`--bg` is not `-p`: it starts a daemon-managed interactive-style session. Keep
permission/model flags explicit. Use foreground `-p --output-format json` for
an atomic result envelope, structured output, or precise cost metadata; use
`--bg` when detachment and cross-turn monitoring matter more.

## Mode 3 — Continuity / resume

Follow-up in an existing lane (preferred over a cold re-ask when addressing
that lane's findings):

```bash
echo "$FOLLOW_UP" | claude -p --resume "$SESSION_ID" \
  --output-format json > "$OUT" 2> "$ERR"
```

Or via the wrapper: `--resume <id>` / `--continue-latest` (only when exactly
one Claude lane ran in this cwd). Keep the permission flags consistent with
the original lane. `--fork-session` branches instead of continuing.

When the host addresses Claude's findings, resume the SAME session for the
re-check before final synthesis: include the original finding, what changed
(paths, diff summary, validation), what was rejected and why, and ask
whether the concern is resolved and whether the fix introduced new focused
issues. Only fall back to a fresh session if resume fails — and say so.

## Safety

- Verify `command -v claude` before assuming the CLI exists.
- Do not let a consult modify files; do not let any lane commit or push
  unless the user explicitly granted it (enforce with `--disallowedTools`,
  not just prompt text).
- If Claude's output conflicts with local code or current command output,
  trust the code and mention the disagreement.
- Summarize Claude's useful points for the user instead of pasting a wall.

## After the run

For orchestrated lanes, log the outcome to
`~/.agents/skills/orchestrate/model-feedback.jsonl` with
`agent_surface: "claude-cli"` and the concrete model alias used, and follow
the orchestrate skill's exploration policy — occasionally trial a different
model/effort tier (haiku/sonnet with low effort vs fable) on comparable
low-risk lanes so routing keeps improving.
