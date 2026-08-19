---
name: cursor
description: Ask or delegate to Cursor CLI Agent — Composer 2.5 for fast advisory/review, Grok 4.5 for long-running coding lanes — read-only advice, plan review, code review, or scoped implementation. Use when the user invokes /cursor, says ask Cursor, check with Cursor, use Composer or Grok, delegate to Cursor, or wants a Cursor CLI lane inside an orchestrated workflow.
---

# Cursor

Use this skill to run the local Cursor CLI Agent (`agent` / `cursor-agent`).
Default to read-only advisory or planning mode. Cursor's answer is useful input,
not authority; compare it against the repo and current command output before
acting.

Cursor CLI is strongest when it gets clear instructions, narrow ownership, and
a concrete validation target. Composer 2.5 Fast is a good first choice for fast
advisory, review, and well-scoped execution work; Grok 4.5 (jointly trained by
Cursor and xAI for long-running coding, fast at high quality) is the one to try
on implementation and review lanes — log how it does (see Model Feedback below).

## Machine facts that bite (verified on cursor-agent 2026.06.19; headless facts re-verified 2026-07-11 on 2026.07.09-a3815c0)

- **`agent status` can lie.** It reports "Login successful" from cached auth
  while every real request (including `agent models`) fails with
  "Authentication required". Preflight with `agent models`, a cheap real
  backend call that does not spend inference tokens. Distinguish auth errors
  from network failures such as `ENOTFOUND`; only ask the user to run `agent
  login` for an actual auth failure (the browser flow is interactive).
- Headless default mode is the full agent — `-p` without `--mode` has write
  and shell access. Always pass `--mode=ask` or `--mode=plan` for read-only
  lanes.
- Parameterized model overrides use bracket syntax:
  `--model 'claude-opus-4-8[context=1m,effort=high,fast=false]'` — this is
  how you set thinking/effort tiers per lane.
- `-w/--worktree [name]` creates the worktree under
  `~/.cursor/worktrees/<reponame>/<name>` (not inside the repo);
  `--worktree-base <branch>` picks the base ref; `--skip-worktree-setup`
  skips `.cursor/worktrees.json` setup scripts.
- `--continue` is shorthand for `--resume=-1` (most recent session).
- `--trust` is required for headless runs in not-yet-trusted workspaces.
  Verified: missing `--trust` does NOT hang `-p` — it fails fast (exit 1,
  ~2s, "Workspace Trust Required" on stderr, empty stdout).
- **`--resume` with an unknown/mistyped session id fails SILENTLY**: exit 0,
  `subtype: success`, and a brand-new session is created under the bogus id
  (which is echoed back as `session_id`). The response cannot tell you the
  resume missed; verify against
  `~/.cursor/chats/<md5-of-cwd>/<session_id>/meta.json` (`hasConversation`,
  `updatedAtMs`) when continuity matters.
- **Branch on exit code before parsing stdout.** A bogus `--model` exits 1
  with EMPTY stdout (no JSON error envelope; the error + available-models
  list is on stderr). The JSON envelope only exists on successful runs.
- `duration_ms` and `duration_api_ms` are always identical, and neither
  includes client startup/indexing. Real wall time is ~2-2.5x duration_ms
  for work lanes; the FIRST call in a fresh workspace pays a 30-100s
  cold-start (indexing), warm trivial calls run 5-10s wall (~2-4s api,
  ~13.4k input tokens). Time wall clock yourself.
- stderr always carries one benign `cursor-retrieval: tracing to ...` line
  even on clean runs — nonempty stderr is not an error signal.
- With `-w/--worktree`, stdout is NOT pure JSON: a `Using worktree: <path>`
  banner precedes the object — parse the LAST line. `-w` also auto-creates
  a branch named after the worktree in the source repo; cleanup needs
  `git worktree remove --force <path>` AND `git branch -D <name>`.
- `agent ls` is an interactive Ink TUI. Under Codex Desktop's piped shell it
  prints "Raw mode is not supported", enters alternate-screen mode, and then
  HANGS until killed; never invoke it headlessly, even as a discovery probe.
  There is no headless session-listing command.
  Observe sessions by reading `~/.cursor/chats/<md5-of-cwd>/<id>/`
  (`meta.json` lifecycle, sqlite `store.db` transcript) — the
  `inspect-cursor-session` skill's approach.
- CLI `request_id` and `session_id` are different identity surfaces. The
  headless result's `session_id` is the resume/inspection handle. Its
  `request_id` is not recorded in Cursor IDE request traces and cannot be
  resolved by `inspect-cursor-session --request-id`; that selector is for IDE
  generation/request IDs.
- Prompt delivery: a multi-KB prompt passes fine as a positional arg via
  `"$(cat prompt.txt)"`, and stdin works too (`echo "prompt" | agent -p ...`
  — no hang). For early session-id harvest on long runs use
  `--output-format stream-json`: `session_id` is on the first line
  (`type: system, subtype: init`); event vocabulary is system/init, user,
  thinking/delta, thinking/completed, assistant, result/success.

## Quick Start

Verify the CLI and auth:

```bash
command -v agent
agent status --format json
agent models
```

Ask Cursor a read-only question:

```bash
agent -p \
  --mode=ask \
  --model "composer-2.5-fast" \
  --output-format json \
  --trust \
  "Review this approach. Do not modify files."
```

Ask Cursor to critique or improve a plan without editing:

```bash
agent -p \
  --mode=plan \
  --model "composer-2.5-fast" \
  --output-format json \
  --trust \
  "Given this implementation plan, identify missing steps and risks. Do not modify files."
```

The JSON result includes `result`, `session_id`, `request_id`, and token usage.
Persist `session_id`; `request_id` is request-scoped telemetry, not continuity.

### Structured output caveat

Cursor's `--output-format json` wraps the run; it does **not** schema-constrain
the model's `result`. Even when prompted for one JSON object, Composer 2.5 Fast
has been observed to prepend progress prose inside `result` while returning
`is_error: false`. For machine contracts:

1. Ask for exactly one JSON value and no prose/fences.
2. Parse the outer envelope first, then use a real JSON decoder to locate the
   inner value (do not use regex for nested JSON).
3. Validate the inner value against the required schema/keys.
4. If the result contains extra text or fails validation, resume the **same
   session once** with the concrete validation error and demand a corrected
   value. Verify the returned session id is unchanged.

If strict server-side schema enforcement is mandatory, route that extraction
lane to Claude's `--json-schema` instead; Cursor currently has no equivalent
flag.
Summarize the useful parts for the user instead of pasting long raw output.

## Modes

### Read-Only Ask Mode

Use for:

- second opinions
- debugging hypotheses
- architecture tradeoffs
- code-review prompts
- "what would Cursor do here?" questions

Command shape:

```bash
agent -p --mode=ask --model "composer-2.5-fast" --output-format json --trust "$PROMPT"
```

### Read-Only Plan Mode

Use for plan critique or to turn a ticket into a sharper execution plan. Plan
mode is read-only and should not edit files.

```bash
agent -p --mode=plan --model "composer-2.5-fast" --output-format json --trust "$PROMPT"
```

### Scoped Execution Mode

Use only when the user explicitly wants Cursor to edit or execute. Headless
print mode has access to write and shell tools unless `--mode=ask` or
`--mode=plan` is set.

Prefer an isolated worktree for risky or broad implementation:

```bash
agent -p \
  --model "composer-2.5-fast" \
  --output-format json \
  --trust \
  --worktree "cursor-$(date +%Y%m%d-%H%M)" \
  "$PROMPT"
```

Use `--force` or `--yolo` only after the prompt is scoped and the user clearly
wants autonomous execution:

```bash
agent -p \
  --model "composer-2.5-fast" \
  --output-format json \
  --trust \
  --force \
  "$PROMPT"
```

Do not add `--sandbox disabled` unless the user explicitly asks for it.

## Prompting Rules

Cursor sees the repo and the prompt, but not this conversation unless you pass
the relevant context. Make the prompt self-contained.

Include:

- Repo path and branch.
- User goal and what "done" means.
- Exact files, directories, or systems in scope.
- Files or areas that are off-limits.
- Current dirty-tree constraints.
- Decisions already made.
- Required validation commands.
- Output format you want.
- Whether Cursor is read-only or may edit.

For read-only calls, include:

```text
Do not modify files, run mutating commands, stage, commit, reset, or revert.
Report findings and suggested patches only.
```

For execution calls, include:

```text
Treat pre-existing dirty changes as user-owned.
Do not stage, commit, reset, or revert unrelated work.
Keep changes inside the stated scope.
If you discover a cross-scope issue, report it instead of expanding scope.
Run the requested validation and report results.
```

## Headless lane benchmarks (verified 2026-07-11, composer-2.5-fast)

Measured driving `agent -p` from Claude Code in tmp projects:

- **Execution lifecycle works end-to-end**: a `--force --trust` lane built a
  Bun+TS module with passing tests in 99s wall (39.8s duration_ms, ~27k
  input tokens); `--resume=<session_id>` follow-up ran 48s, returned the
  SAME session_id, edited existing files in place matching its own earlier
  style without re-exploring, and honored a no-commit instruction (verify
  with `git log` anyway — it's free).
- **`--workspace <dir>` ≡ cd'ing into the dir first** (same answers, same
  tokens). Prefer `--workspace` from Claude Code since Bash cwd resets
  between calls.
- **Concurrency is safe**: three simultaneous `--force` execution lanes
  (own dirs, own stdout/stderr files, `( ... ) & + wait` in one Bash call)
  showed zero lock/auth/rate-limit errors and a 2.9x wall win (105s batch
  vs ~304s serial). Budget ~100s wall per small write+test lane.
- **Ask-mode held read-only** when asked to modify a file (file untouched,
  git clean) — but the transcript shows the model declined rather than a
  tool being hard-rejected, so treat ask-mode as strong-but-not-proven-hard
  isolation.
- **Nested Cursor→Codex works**: a headless Cursor lane faithfully executed
  a fully-specified `codex exec` template (rm -f, sandbox flags, -o,
  stderr session-id harvest) with zero approval stalls under `--force`, at
  ~1.8-2.5x the cost of dispatching codex directly (160s vs 60-90s). Only
  worth it when Cursor adds real orchestration value in the middle. Give it
  a labeled-fields output contract (e.g. `CODEX_SESSION_ID=...`) — it
  reproduces the labels verbatim in `result`, making the JSON parseable.

## Orchestration Pattern

When `$orchestrate` needs a Cursor lane, use Cursor for one of these roles:

- **Plan critic:** read-only `--mode=plan`, reviewing the main task breakdown.
- **Review lane:** read-only `--mode=ask`, checking security, regressions, UX, or
  architecture against a supplied diff or file list.
- **Implementation lane:** scoped execution mode in a separate worktree or a
  clearly owned file set, only when the user wants Cursor to write.

Keep the main agent accountable:

- Check the dirty tree before launching Cursor.
- Give Cursor disjoint ownership from other agents.
- Inspect Cursor's output and diffs before trusting them.
- Run integrated validation yourself.
- Do not leave long-running Cursor processes unmanaged unless the user asked
  for a background handoff.

## Model Notes

Useful model ids (run `agent models` before relying on one in scripts — the
list changes, and ids below the first two are unverified against the live
list):

- `composer-2.5-fast` - fast Composer 2.5; speed king for advisory/review.
- `composer-2.5` - current Composer 2.5.
- Grok 4.5 - Cursor+xAI joint model, positioned for long-running coding at
  near-frontier quality with high speed. Strong candidate for implementation
  and review lanes; deliberately try it on comparable lanes and log results.
- `auto` - let Cursor pick.
- Cross-provider models (Claude, GPT, Gemini) are also exposed; bracket
  overrides set context/effort/fast per lane.

## Model Feedback (self-optimizing routing)

Cursor lanes participate in the same routing loop as Codex/Claude lanes: log
every meaningful lane outcome to
`~/.agents/skills/orchestrate/model-feedback.jsonl` with
`agent_surface: "cursor-cli"` and the concrete model id (including bracket
overrides). Follow the orchestrate skill's exploration policy — when risk
allows, route one comparable lane to an unproven model (Grok 4.5 is the
current one to build evidence on) instead of always defaulting to the known
quantity.

## Sessions

Resume prior Cursor conversations:

```bash
agent ls        # interactive TTY only — hangs headless (see machine facts)
agent resume
agent --continue -p "Follow up on your previous answer..."
agent --resume="<chat-id>" -p "Continue from this session..."
```

For a known JSON result, save or mention the `session_id` if the user may want
to continue the same Cursor thread.

When Cursor returns findings, risks, or concrete feedback and the main agent
later addresses any of it, resume the same Cursor session for a focused
re-check before final synthesis whenever possible. Include the original
feedback, what changed or why a finding was rejected, and current validation.
Ask whether the original concern is resolved and whether the response introduced
any new focused issue. Use a fresh Cursor session only if the original cannot be
resumed, and say so.

## Safety

- Verify `command -v agent` before assuming Cursor CLI exists.
- Use `agent login` only when auth is missing and the user wants setup.
- Do not run `agent update`, `agent install-shell-integration`, or
  `agent uninstall-shell-integration` unless the user explicitly asks.
- Do not send secrets, private tokens, or unnecessary large diffs.
- Do not use `--force`, `--yolo`, write mode, worktrees, or sandbox changes for
  ordinary advisory questions.
- Cursor findings can be stale or wrong; verify against local files and command
  output before making claims to the user.
