---
name: consult
description: One-shot cross-agent consultation for an independent second opinion, design call, debugging hypothesis, architecture tradeoff, implementation plan check, or "am I thinking about this right?" question. Use when the user asks to consult another agent, get Claude/Codex's opinion, validate an approach, or compare model perspectives without running a full brainstorm or critique. Prefer `brainstorm` for multi-lane idea generation and `critique` for reviewing concrete work.
---

# Consult

Use this skill for one focused outside opinion. It is intentionally smaller than `brainstorm` and less formal than `critique`: one other agent, one question, concise synthesis.

## Routing

- If you are Codex, load and follow `~/.agents/skills/claude/SKILL.md`.
- If you are Claude, load and follow `~/.agents/skills/codex/SKILL.md`. `codex (formerly ask-codex)` is the provider-specific backend for asking Codex until all callers migrate to `consult`.
- If the needed provider tool is unavailable, say so and answer from your own reasoning instead of pretending a second opinion happened.

## Workflow

1. Build a self-contained brief:
   - User goal or question.
   - Relevant constraints, files, snippets, command output, or session facts.
   - What has already been checked or ruled out.
   - The desired answer shape: recommendation, tradeoffs, risks, debugging hypotheses, or yes/no call.

2. Ask exactly one outside agent:
   - Keep the prompt read-only unless the user explicitly asked for action.
   - Use project-aware modes only when the adviser truly needs local project context.
   - Do not fan out to multiple subagents. Use `brainstorm` or `critique` for that.

3. Adjudicate:
   - Treat the outside answer as input, not authority.
   - Compare it against current code, current command output, and user constraints.
   - Summarize the useful part. Do not blindly paste a long answer unless the user asked for raw output.

4. Close the loop when feedback is addressed:
   - Record the outside agent's session id or continuation handle from the first call.
   - If you apply, reject, or otherwise address concrete feedback from that agent, resume the same session and present the follow-up: original feedback, what changed or why it was rejected, and current validation.
   - Ask that same agent whether its original concern is resolved and whether the response introduced any new focused issue.
   - Use a fresh outside agent only if the original session cannot be resumed, and disclose that loss of continuity.

## Output Shape

Prefer:

```text
I asked <agent>. My read:
- Recommendation: ...
- Useful point from <agent>: ...
- Where I agree/disagree: ...
- Next move: ...
```

For simple questions, a short paragraph is enough.
