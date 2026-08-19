---
name: inspect-cursor-session
description: Inspect Cursor composer/session IDs directly or resolve Cursor UI request IDs, then read local agent transcripts to summarize, monitor, or wait on another session. Use whenever the user provides a Cursor session, composer, conversation, request, generation, or invocation ID; asks "inspect Cursor session", "what is this Cursor agent doing?", "find the latest Cursor composer", or "is Cursor blocked?". Reads Cursor request traces, hook logs, JSONL transcripts, and composer metadata. Read-only by default.
metadata:
  short-description: Resolve request IDs and inspect Cursor sessions
---

# Inspect Cursor Session

Read local Cursor composer/agent transcripts and summarize what another Cursor session is doing. This skill is for observation: find the composer, inspect recent messages/events, identify likely blocked/waiting states, and report enough context for another agent to continue.

## Quick Start

Use the bundled script from this skill directory:

```bash
python3 scripts/inspect_cursor_session.py --last
python3 scripts/inspect_cursor_session.py --session-id 140494c9-f45f-4506-839c-803f3089753e
python3 scripts/inspect_cursor_session.py --request-id 7265cb86-a070-4ab7-a422-f4ac9ef53c86
python3 scripts/inspect_cursor_session.py --query "title, workspace, request id, prompt, or composer id"
python3 scripts/inspect_cursor_session.py --query 916e7b45 --limit 12
python3 scripts/inspect_cursor_session.py --query 916e7b45 --last-message assistant
python3 scripts/inspect_cursor_session.py --query 916e7b45 --search "blocked" --full
python3 scripts/inspect_cursor_session.py --list --limit 20
```

If running from outside the skill directory, use the absolute script path:

```bash
python3 ~/.agents/skills/inspect-cursor-session/scripts/inspect_cursor_session.py --last
```

## UUID identity selection

Cursor exposes several UUID-shaped identifiers. Choose the selector from the
identity the user names:

- Composer, conversation, or session ID: use `--session-id`.
- Request, generation, or invocation ID: use `--request-id`.
- Unlabeled UUID: use `--query`. It prefers an exact local session/composer ID,
  then falls back to request-ID resolution.

For a Cursor composer/session ID such as the value shown in a transcript path
or Cursor's composer metadata, use:

```bash
python3 scripts/inspect_cursor_session.py \
  --session-id 140494c9-f45f-4506-839c-803f3089753e
```

## Request ID fast path

When the user supplies a Cursor UI request ID, use the explicit selector:

```bash
python3 scripts/inspect_cursor_session.py \
  --request-id 7265cb86-a070-4ab7-a422-f4ac9ef53c86
```

The output names the request ID, resolved session/composer ID, resolution
source, transcript, and current context. Use `--request-id` only when the value
is known to be a request/generation ID; it gives a precise error when
resolution fails.

Resolution order:

1. `cursor.requestTraces.log`: lines for an active request carry both
   `requestId=<request-id>` and `composerId=<session-id>`. This works before
   session-end hooks run.
2. `cursor.hooks.workspaceId-*.log`: hook `INPUT` JSON carries
   `generation_id`, `conversation_id` / `session_id`, and sometimes the exact
   `transcript_path`.
3. The resolved composer ID is matched to the local transcript or composer
   index. If the transcript has not appeared yet, report metadata-only state.

Verified with Cursor 3.8.20: `cursor agent` exposes chat `--resume`, `ls`, and
`resume` commands, but no command that maps an IDE request ID to its composer
ID. Use the local request-trace lookup; do not open the interactive CLI merely
to discover the ID.

## Workflow

1. Resolve the target session:
   - Prefer `--session-id` for a known composer/conversation/session ID and `--request-id` for a known Cursor UI request/generation ID. Use `--query` for an unlabeled UUID, JSONL path, title/name, workspace path, project key, or prompt substring.
   - If none is supplied, use `--last` for the most recently updated transcript.
   - Use `--list` when the user needs to choose among candidates.

2. Inspect the transcript:
   - Read from `$CURSOR_HOME` if set, otherwise `~/.cursor`.
   - Main agent transcripts normally live under `projects/<project-key>/agent-transcripts/<composer-id>/<composer-id>.jsonl`.
   - Subagent logs can live under `projects/<project-key>/agent-transcripts/<parent-composer-id>/subagents/<subagent-id>.jsonl`.
   - Composer metadata is indexed in Cursor's VS Code-style app storage, usually `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb` under the `composer.composerHeaders` key.
   - Headless CLI sessions use a separate store under
     `~/.cursor/chats/<workspace-hash>/<session-id>/meta.json` plus `store.db`.
     The helper merges `meta.json` so CLI cwd/title/liveness and metadata-only
     sessions remain visible even when no mirrored JSONL exists.
     `agent create-chat` returns a valid future resume id, but the corresponding
     `meta.json`/JSONL may not materialize immediately. During a live launch,
     retry explicit `--query <session_id>` for a bounded window; absence in the
     first few seconds is not proof that the session failed to start.
   - Cursor UI request IDs appear as `requestId` in `cursor.requestTraces.log` and as `generation_id` in hook logs. Request traces provide the live `composerId`; hook payloads can additionally provide `conversation_id`, `session_id`, and `transcript_path`.
   - The `request_id` returned by headless `agent -p` is not the same identity
     surface as a Cursor IDE generation id and is not locally resolvable. Save
     and inspect the headless result's `session_id`.
   - Use `--last-message assistant|user|any` when you need the latest full message without dumping recent tool noise.
   - Use `--search "<text>"` to find where a session mentioned a term; add `--full` when the compact snippet loses important context.
   - Do not include thinking blocks, hidden prompt payloads, or long tool outputs in the response.

3. Report concisely:
   - Composer id, name/title, workspace/project, path, last activity time.
   - Heuristic state: likely waiting, possibly running, blocked, or unknown.
   - Last few user/assistant/tool/attachment events.
   - Any explicit blocker/request markers found in recent assistant messages.

4. Keep inspection read-only. Do not edit Cursor JSONL files or SQLite databases.

## Output Style

For a waiting/coordination use case, prefer:

```text
Session: <name> (<composer-id>)
State: likely waiting for user / likely still running / blocked / unknown
Last activity: <timestamp>
Latest useful context:
- User: ...
- Assistant: ...
Next suggested action: ...
```

Avoid dumping full transcripts unless the user asks. Session files can contain sensitive tool output, prompts, attached docs, and local code context.

## Validation

After changing the helper, run:

```bash
python3 scripts/test_inspect_cursor_session.py
python3 -m py_compile scripts/inspect_cursor_session.py
```
