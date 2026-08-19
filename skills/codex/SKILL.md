---
name: codex
description: Dispatch the Codex CLI (gpt-5.5) as a subagent — one-shot consults on hard questions, scoped worker lanes (implementation, research, browser/computer-use tasks), and resumed follow-ups. Formerly `ask-codex`. Use when the user invokes /codex or /ask-codex, says "ask codex" / "use codex" / "delegate to codex", when an orchestration plan routes a lane to Codex, or when a browser-driving task suits Codex's native browser_use. Supports `resume` for follow-up turns in the same session.
---

# Codex

One gateway for using the local Codex CLI (gpt-5.5) from a Claude-hosted
session, in two modes:

- **Consult** — the IM-a-senior-colleague question: "here's my problem and my
  thinking, tell me what I'm missing." The original `ask-codex` flow.
- **Worker lane** — a scoped delegated task inside an orchestrated workflow:
  implementation in a worktree, read-only research, browser/GUI automation,
  structured extraction. Pair with the `orchestrate` skill's lane discipline
  (ownership, evidence contract, friction log, model-feedback logging).

This skill was renamed from `ask-codex`; old resume sessions still work
(sessions live on the Codex side, keyed by session id, not by this skill).
For provider-neutral "get a second opinion" requests, `consult` remains the
user-facing entry point and routes here for the Codex leg.

## When to route a lane to Codex (vs a Claude subagent)

Good fits:

- Browser and GUI tasks — this install has `browser_use`,
  `browser_use_external`, `browser_use_full_cdp_access`, and `computer_use`
  features stable and enabled, with the bundled `node_repl` (browser-use
  backends) and `computer-use` MCP plugins. Codex drives a browser natively,
  no agent-browser required.
- Scoped implementation with crisp instructions — Codex is a strong
  instruction-follower for well-bounded diffs.
- Independent second-provider review/critique lanes (different failure modes
  than Claude reviewing Claude).
- Structured extraction where `--output-schema` guarantees parseable results.
- Codex's self-reported sweet spots: browser verification and UI repros,
  codebase archaeology with exact file/line evidence, focused implementation
  in a worktree, test/debug loops with concrete commands, review/risk/
  regression hunting, "find the true failure mode then patch narrowly".

Keep on Claude: lanes needing this conversation's context (Codex starts cold
every time), cross-repo integration owned by the lead, product-judgment
calls that belong to the user, human-approval choreography, and ambiguous
"go figure out everything" scopes without a crisp deliverable.

## Requirements

1. `codex` CLI on PATH (verified against codex-cli 0.144.1; earlier notes
   from 0.142.5 re-verified where marked).
2. No REVIEW.md needed. Codex reads `CLAUDE.md` / `AGENTS.md` if present.

## Machine facts that bite (verified on this install)

- `~/.codex/config.toml` sets `approval_policy = "never"` and
  `sandbox_mode = "danger-full-access"` **globally**. The exec "read-only
  default" documented upstream does NOT apply here — always pass `-s
  <mode>` explicitly on every `codex exec`, and set sandbox on resume via
  `-c` (see flag notes).
- Cursor verification on 2026-07-11 found `~/.codex/config.toml` now sets
  `model = "gpt-5.6-sol"` and `model_reasoning_effort = "ultra"`; all six
  benchmark session rollouts (seven exec calls including one resume)
  reported gpt-5.6-sol. This supersedes the earlier Claude-driver observation
  of gpt-5.5/high. Pass an effort override for bounded worker lanes instead
  of inheriting ultra.
- OAuth-backed MCP servers (Datadog, Figma, Linear, Notion, Sentry) may fail
  headless with `AuthorizationRequired` transport errors on stderr. Harmless
  noise unless the task needs that server; a `required = true` MCP server
  that fails kills the exec run.
- A trivial exec run costs ~24k input tokens (~10k cached) and ~7-8s of
  harness/skill overhead on this install (measured 2026-07-11 via `--json`
  `turn.completed.usage`; grows with installed skills/plugins — the JSON
  stream even warns skill descriptions were truncated to a 2% context
  budget). Don't burn a Codex lane on one-line lookups; batch small
  questions into one call. Effort tier doesn't change trivial-call latency
  (low vs medium: 7s vs 6s — startup dominates), so pick effort by task
  difficulty, not speed.
- Codex has its OWN subagents (`multi_agent` enabled): built-in `default` /
  `worker` / `explorer` agents, custom ones in `~/.codex/agents/*.toml`, max
  6 concurrent threads, plus an experimental `spawn_agents_on_csv` batch
  tool. A single Codex lane can therefore fan out internally — tell it
  explicitly whether that's allowed (default for orchestrated lanes: no).

## Arguments

The slash-command body is the question or task. Reserved tokens when they
lead the args: `resume` continues the most recent session; `resume
<SESSION_ID>` resumes a specific one; remaining tokens become the new prompt.

## Execution model

Single background subagent (`run_in_background: true`, `subagent_type:
general-purpose`) wrapping `codex exec` calls. Rules learned the hard way:

- Run `codex exec` as a FOREGROUND Bash command inside the (already
  backgrounded) subagent with a long timeout (600000ms). Do not nest
  background tasks or monitors inside the subagent.
- Always `< /dev/null` (codex blocks on stdin reads in non-interactive
  parents) unless deliberately piping context via stdin. Verified on
  0.144.1: an open stdin hangs the run FOREVER even when the prompt is an
  argument — no session id is ever printed and no `-o` file is created, so
  the hung work is unrecoverable. Signature of a hung run: last stderr line
  is `Reading additional input from stdin...` with no `session id:` line.
- `rm -f` the `-o` file and stderr log before EVERY run. Verified: failed
  runs neither create nor truncate the `-o` file, so stale output from a
  previous run silently masquerades as fresh results.
- Capture the exit code IMMEDIATELY after the codex command (`RC=$?`)
  before any timestamp or other command. Judge success by exit code plus
  `-o` content, never by grepping stderr for `ERROR`: exit 0 = success,
  2 = CLI parse error (bad flag), 1 = runtime error (e.g. bad resume id);
  all error text lands on stderr, stdout stays empty.
- Capture stderr to a log; extract the session id from the `session id:`
  line (or with `--json`:
  `jq -r 'select(.type=="thread.started") | .thread_id' events.jsonl`) and
  report it — that's the resume handle.
- For long scripted prompts, prefer a heredoc over fighting shell quoting:
  `codex ... exec - <<'PROMPT' ... PROMPT` (the `-` reads the prompt from
  stdin; single/double quotes, `$VAR`, and backticks pass through verbatim
  with the quoted delimiter). Do NOT also append `< /dev/null` to the
  heredoc form — in bash the later redirect overrides the heredoc and
  delivers an empty prompt (zsh multios happens to concatenate them, which
  masks the bug). The two stdin patterns are mutually exclusive.
- `-o <file>` for the final message; return it verbatim. The main thread
  relays without re-synthesizing.
- Pre-check host tooling (`which jq python3 bun pytest ...`) before writing
  lane prompts and bake findings in ("pytest is NOT installed, use plain
  asserts") — Codex complies, and it prevents wasted install attempts.

The main thread does a fast preflight (≤2 tool calls: `command -v codex`,
parse args), spawns the orchestrator, tells the user Codex is thinking, and
does NOT poll.

### Driving from Cursor

Verified 2026-07-11 from the Cursor harness against codex-cli 0.144.1:

- Cursor's shell tool ran `/bin/zsh` and persisted cwd between calls. After
  one call used `/tmp/cursor-codex-bench/build` as its working directory, the
  next call without an explicit working directory started there (reported as
  `/private/tmp/cursor-codex-bench/build`).
- A shell call configured with `block_until_ms: 600000` kept a 74s
  workspace-write build in the foreground. It exited 0, produced the `-o`
  file, and its independently rerun 4-test suite passed. Resuming the same
  session with `-c sandbox_mode="workspace-write"` took 29s, echoed the same
  session id, exited 0, and its independently rerun 6-test suite passed. No
  Cursor-specific Codex flag changes were needed.
- `block_until_ms: 0` returned immediately with a background shell job and
  output-file path. The tested low-effort exec finished in 6.754s with exit
  0; after completion, both the shell transcript and the requested `-o` file
  were readable.
- One zsh call launched three isolated read-only execs with `( codex ... ) &`
  and `wait`. They exited 0 in 11s, 10s, and 10s; concurrent wall time was
  11s versus a 31s sum, a 2.8x wall-clock win. Each lane used its own `-C`,
  `-o`, and stderr path.

## Mode 1 — Consult (fresh question)

Use the fresh-run orchestrator prompt below. Replace `{{QUESTION}}`
(shell-escaped), `{{REPO}}` (repo root or cwd).

```bash
(
  CODEX_RUN_DIR="$(mktemp -d "${TMPDIR:-/tmp}/codex-skill.XXXXXX")" || exit 1
  chmod 700 "$CODEX_RUN_DIR"
  CODEX_OUTPUT="$CODEX_RUN_DIR/output.md"
  CODEX_STDERR="$CODEX_RUN_DIR/stderr.log"
  cleanup_codex_run() {
    unlink "$CODEX_OUTPUT" 2>/dev/null || true
    unlink "$CODEX_STDERR" 2>/dev/null || true
    rmdir -- "$CODEX_RUN_DIR" 2>/dev/null || true
  }
  trap cleanup_codex_run EXIT

  ASK_PROMPT='You are answering a hard question from a senior engineer working in this repo. They have access to the same tools and codebase you do — they are asking YOU because they want an independent, thoughtful take, not a restatement of the obvious.

## The question

{{QUESTION}}

## How to think about this

1. Read enough code to answer well, but do not exhaustively explore. CLAUDE.md / AGENTS.md and docs/ are worth a quick read when project context matters. Skip repo exploration if the question is self-contained.
2. Think before answering. What can you add that a less-informed answer would miss?
3. Take a position. If the question is "A or B?", pick one and say why. Never end at "it depends" without naming the dependencies.
4. Name what you are not sure about and what to check.
5. Brief beats thorough: a crisp 200-word answer with one sharp insight beats 800 words of hedge.

## House rules

- Answer the question asked, not an adjacent one.
- Code is the source of truth.
- Push back if the question has a flawed premise.
- READ-ONLY POLICY: do not write, edit, patch, or format files; no git add/commit/stash; no package installs or codegen. Describe code instead of applying it.

## Output format

Direct answer, no preamble. Cite files as path/to/file.ts:LINE. If the question was vague, one sentence clarifying what you are answering — then answer it.'

  codex -a never -C {{REPO}} exec \
    -s read-only \
    --skip-git-repo-check \
    --output-last-message "$CODEX_OUTPUT" \
    "$ASK_PROMPT" \
    < /dev/null 2> "$CODEX_STDERR"
  CODEX_EXIT=$?
  echo "EXIT=$CODEX_EXIT"
  grep -m1 "session id:" "$CODEX_STDERR" || true
  if [[ -s "$CODEX_OUTPUT" ]]; then
    cat "$CODEX_OUTPUT"
  else
    tail -n 80 "$CODEX_STDERR"
  fi
  exit "$CODEX_EXIT"
)
```

The subshell prints the final output (or the last 80 stderr lines), preserves
the Codex exit status, and removes its private invocation directory on exit.

## Mode 2 — Worker lane (delegated task)

Same execution model, different prompt and sandbox. Compose the lane prompt
per the `orchestrate` skill (goal, owned scope, forbidden files, validation,
output contract, friction log) and add Codex-specific instructions:

- **Read-only denial is silent:** a read-only lane asked (or tempted) to
  write still exits 0 — codex's patch is rejected in-sandbox (stderr:
  `patch rejected: writing is blocked by read-only sandbox`) and it
  gracefully degrades to describing the fix as diffs. Verify no-write with
  `git status --porcelain` after any read-only lane whose task might imply
  writes; never infer sandbox enforcement from the exit code.
- **Sandbox by lane type:** research/review lanes `-s read-only`;
  implementation lanes `-s workspace-write` pointed at an isolated worktree
  via `-C <worktree>` (never two write lanes in one checkout; `--add-dir`
  for extra writable roots). Do not use `danger-full-access` unless the user
  explicitly authorized that specific task shape.
- **No commits by default.** Tell Codex explicitly: no git add/commit/push,
  leave changes in the working tree for the lead to integrate.
- **Browser lanes:** state the target URL(s), that Codex should use its
  browser tooling, and the evidence contract (network requests observed,
  page state, screenshots to a named path). Empirically validated lane
  shape on this install (2026-07-08, codex-cli 0.142.5 — navigated, read
  page state, reported console errors, saved a screenshot):

  ```bash
  codex -a never -C "$WORKDIR" exec \
    -s danger-full-access \
    --enable browser_use --enable browser_use_external \
    --enable browser_use_full_cdp_access \
    --skip-git-repo-check \
    -o "$OUT" "$PROMPT" < /dev/null 2> "$ERR"
  ```

  FALSIFIED alternative: `-s workspace-write` +
  `sandbox_workspace_write.network_access=true` does NOT work for browser
  lanes here — browser process launches abort inside the sandbox, the
  in-app browser is unavailable under exec, and computer-use approvals
  auto-fail under `-a never`. Browser lanes on this machine require
  `danger-full-access` (which is also the user's own global default), so
  compensate in the briefing: observe-only instructions, explicit "do not
  log in / click / submit" bounds when appropriate, prefer a fresh isolated
  browser context over the user's logged-in Chrome tabs, and never grant a
  browser lane git/commit permissions in the same run. Prerequisites:
  logged-in Mac GUI session (no headless SSH/CI) and Chrome already running
  for the chrome backend. Do NOT pass `--ignore-user-config` (it can drop
  the plugin/MCP setup that provides browser control). Weak spots to avoid
  assigning: CAPTCHAs, fresh OAuth logins, irreversible UI actions. Reuse
  the hypothesis-first briefing pattern from
  `orchestrate/playbooks/local-browser-verification.md`.
- **Structured results:** when the lead needs machine-readable output, write
  a JSON Schema to a temp file and pass `--output-schema <file>` plus `-o
  <file>` — the final message then validates against the schema. Write the
  schema OpenAI-strict (`additionalProperties: false`, every property in
  `required`, enums for closed sets) — loose schemas risk rejection.
  Benchmarked 2026-07-11: a read-only audit lane with a strict schema
  validated on the first try and scored 2/2 planted bugs with exact
  file:line and zero false positives in 19s. Parse the `-o` file, not
  stdout (the JSON also streams to stdout where it mixes with your own
  echoes), and validate with a real JSON parse before trusting it.
- **Internal fan-out:** say whether Codex may use its own subagents. Default
  no for orchestrated lanes (keeps evidence auditable); allow it
  deliberately for wide read-only sweeps.
- **Follow-ups:** capture the session id so review feedback can go back to
  the same lane via resume instead of a cold start.

## Mode 3 — Resume

`--full-auto` is deprecated and `exec resume` accepts neither `--full-auto`
nor `-s` (re-verified on 0.144.1) — set sandbox through `-c`. Two traps:
misspelled `-c` keys are NOT rejected (a typo silently drops your sandbox
choice, falling back to the config default of danger-full-access), and a
bogus session id fails fast with exit 1 / `no rollout found ... (code
-32600)` on stderr:

```bash
(
  CODEX_RUN_DIR="$(mktemp -d "${TMPDIR:-/tmp}/codex-skill.XXXXXX")" || exit 1
  chmod 700 "$CODEX_RUN_DIR"
  CODEX_OUTPUT="$CODEX_RUN_DIR/output.md"
  CODEX_STDERR="$CODEX_RUN_DIR/stderr.log"
  cleanup_codex_run() {
    unlink "$CODEX_OUTPUT" 2>/dev/null || true
    unlink "$CODEX_STDERR" 2>/dev/null || true
    rmdir -- "$CODEX_RUN_DIR" 2>/dev/null || true
  }
  trap cleanup_codex_run EXIT

  codex -a never -C {{REPO}} exec resume {{SESSION_SELECTOR}} \
    -c sandbox_mode="read-only" \
    --skip-git-repo-check \
    --output-last-message "$CODEX_OUTPUT" \
    "{{FOLLOW_UP}}" \
    < /dev/null 2> "$CODEX_STDERR"
  CODEX_EXIT=$?
  if [[ -s "$CODEX_OUTPUT" ]]; then
    cat "$CODEX_OUTPUT"
  else
    tail -n 80 "$CODEX_STDERR"
  fi
  exit "$CODEX_EXIT"
)
```

`{{SESSION_SELECTOR}}` is `--last` or the session id. Match `sandbox_mode`
to the original lane type (`workspace-write` for implementation follow-ups).
Resume prompt shape: engage the specific pushback, update explicitly on new
information ("given X, I now say Y because Z"), or re-examine the prior
answer if the follow-up is empty. If resume errors with "no resumable
session", stop and tell the user — do not silently fall back to a fresh run.

Resume is cheap and genuinely stateful (benchmarked 2026-07-11): a
follow-up turn on a build lane cost 25.7k tokens and 28s vs 53s for the
original build, read exact file paths without re-exploring, and echoed the
SAME session id (resume does not fork). Don't restate the project layout in
resume prompts — just the delta and the new acceptance criteria.

## Flag notes (verified on codex-cli 0.142.5; re-verified 0.144.1 where noted)

- `-a never` and `-C <dir>` go on TOP-LEVEL `codex`, not on `exec`.
- `-s read-only|workspace-write|danger-full-access` on `exec` — mandatory
  here because the user config defaults to danger-full-access.
- `--skip-git-repo-check` on exec/resume; `-o/--output-last-message <file>`
  captures the final message.
- `--json` streams JSONL events to stdout (`thread.started` carries
  `thread_id` = session id; `turn.completed` carries token usage). Use for
  programmatic monitoring; otherwise stderr + `-o` is simpler.
- `--output-schema <file>` constrains the final message to a JSON Schema.
- `--ephemeral` skips session persistence — it BREAKS resume; never use it
  for lanes that might get follow-ups. Trap (verified 0.144.1): an
  ephemeral run STILL prints a `session id:` line on stderr, but the id is
  not resumable (no rollout under `~/.codex/sessions`; resume fails in ~1s
  with exit 1). Do not harvest ephemeral ids as resume handles.
- `-c model_reasoning_effort="low"|"medium"` accepted on exec (verified
  0.144.1); medium is sufficient for small scaffold+test lanes (53s for a
  CLI with passing tests). Rough wall-time budgets at medium: trivial
  answer ~7s, read-only audit of a small module ~20s, small build lane
  15-55s — a 600s Bash timeout comfortably covers all of these.
- MCP noise is not failure: on a host with OAuth MCP servers configured,
  every run's stderr carries `rmcp::transport::worker ...
  AuthorizationRequired` errors and sometimes a session-cleanup
  `DELETE returned HTTP 400` — all observed on runs that exited 0 with
  correct artifacts. Never grep stderr for `ERROR` as a failure signal;
  filter this noise before parsing the log (it can be 20+KB per run).
- stdin: `codex exec -` reads the whole prompt from stdin; piping data while
  passing a prompt argument appends stdin as a `<stdin>` block.
- `-i/--image <file>` attaches images (screenshots for visual tasks).
- Parallelism (benchmarked 2026-07-11): three concurrent workspace-write
  lanes launched from ONE foreground Bash call — `( codex ... ) &` per lane
  plus `wait` — completed with zero cross-lane interference and a 2.4x
  wall-clock win (30s concurrent vs 72s serial sum) when each lane had its
  own `-C` dir, `-o` file, and stderr log. 2-4 concurrent exec workers are
  fine for read/code lanes in separate worktrees. Hard rules: ONE browser/computer-use
  lane at a time (they share the Mac GUI, Chrome profile, tabs, and focus);
  explicit port assignments when lanes start dev servers; one worktree per
  write lane; expect OAuth/remote MCP flakiness to multiply with worker
  count. Session rollout files accumulate under `~/.codex` (gigabytes over
  time) — occasional cleanup is fair game.

## After the run

Relay the orchestrator's report verbatim; add your own take only after,
separately. If Codex returned findings the main agent later addresses,
resume the SAME session for the re-check before final synthesis, including
what changed and validation results. For orchestrated lanes, log the outcome
to `~/.agents/skills/orchestrate/model-feedback.jsonl` with
`agent_surface: "codex-cli"` and the concrete model, and follow the
orchestrate skill's exploration policy — occasionally trial a different
model/effort tier on comparable low-risk lanes so routing keeps improving.

## Adapting for a new project

Drop-in. No config needed. Codex reads whatever project context exists
(CLAUDE.md, AGENTS.md, docs/) when the task warrants.
